import os
import re
import logging
from typing import List, Dict, Any

from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger("terraform_engine")


class TerraformEngine:
    def __init__(self):
        # Resolve templates path relative to this file
        current_dir = os.path.dirname(os.path.abspath(__file__))
        self.templates_dir = os.path.join(current_dir, "templates")

        if not os.path.exists(self.templates_dir):
            os.makedirs(self.templates_dir, exist_ok=True)
            logger.warning(
                f"Created empty templates directory: {self.templates_dir}")

        self.env = Environment(loader=FileSystemLoader(
            self.templates_dir), trim_blocks=True, lstrip_blocks=True)

        # Add custom filter to sanitize node IDs for strict Azure/AWS naming rules
        def sanitize_id(value: str) -> str:
            # Replace hyphens with underscores (valid in HCL resource labels)
            # then remove all other non-alphanumeric chars
            safe_val = re.sub(r'[^a-z0-9_]', '',
                              str(value).lower().replace('-', '_'))
            # Truncate to 24 chars max to prevent Azure name length violations
            return safe_val[:24] if safe_val else "id"

        self.env.filters['sanitize_id'] = sanitize_id

    def _detect_compute_type(self, nodes: List[Dict[str, Any]]) -> str:
        """Auto-detect compute platform from the architecture node list."""
        node_ids_lower = {str(n.get("id", "")).lower() for n in nodes}
        if "aks-cluster" in node_ids_lower or "aks-system-node-pool" in node_ids_lower:
            return "AKS"
        elif "app-service-plan" in node_ids_lower or "web-app" in node_ids_lower:
            return "App Service"
        elif "container-app-env" in node_ids_lower:
            return "Container Apps"
        return "AKS"  # default

    def validate_terraform_drift(self, main_tf: str, nodes: List[Dict[str, Any]], compute_type: str) -> List[str]:
        """
        Compare the rendered main.tf content with the input architecture nodes to detect drift.
        Checks: resource counts, resource names, subnet placements, and compute platform consistency.
        """
        warnings = []

        # 1. Extract all Terraform resource blocks: resource "type" "name" {
        tf_resources = re.findall(r'resource\s+"([^"]+)"\s+"([^"]+)"', main_tf)
        tf_resource_types = [r[0] for r in tf_resources]
        tf_resource_names = [r[1] for r in tf_resources]

        # 3. Check compute platform alignment
        compute_upper = compute_type.upper().replace("_", " ").replace("-", " ")
        if "AKS" in compute_upper or "KUBERNETES" in compute_upper:
            if "azurerm_kubernetes_cluster" not in tf_resource_types:
                warnings.append(
                    "Terraform Drift: AKS compute selected but azurerm_kubernetes_cluster not found in HCL.")
            if any("azurerm_service_plan" in t for t in tf_resource_types):
                warnings.append(
                    "Terraform Drift: AKS compute selected but azurerm_service_plan found (App Service substitution).")
        elif "APP SERVICE" in compute_upper or "WEB APP" in compute_upper:
            if "azurerm_service_plan" not in tf_resource_types:
                warnings.append(
                    "Terraform Drift: App Service compute selected but azurerm_service_plan not found in HCL.")
            if any("azurerm_kubernetes_cluster" in t for t in tf_resource_types):
                warnings.append(
                    "Terraform Drift: App Service compute selected but azurerm_kubernetes_cluster found (AKS substitution).")
        else:
            if "azurerm_container_app_environment" not in tf_resource_types:
                warnings.append(
                    "Terraform Drift: Container Apps compute selected but azurerm_container_app_environment not found in HCL.")

        # 4. Validate subnet resource existence
        arch_subnets = [n for n in nodes if n.get("type") == "SubnetGroupNode" or str(
            n.get("id")).startswith("subnet-") or str(n.get("id")).startswith("snet-")]

        def get_possible_names(sub_id: str) -> List[str]:
            sub_id = str(sub_id).lower()
            # 1. New sanitize_id style: replace - with _
            name1 = re.sub(r'[^a-z0-9_]', '', sub_id.replace('-', '_'))[:24]
            # 2. Pure alphanumeric style
            name2 = re.sub(r'[^a-z0-9]', '', sub_id)
            # 3. Old first-6-last-4 style
            name3 = name2[:6] + name2[-4:] if len(name2) > 10 else name2
            return [name1, name2, name3]

        if arch_subnets:
            for sub_node in arch_subnets:
                sub = sub_node.get("id")
                possible = get_possible_names(sub)
                if not any(name in tf_resource_names for name in possible):
                    warnings.append(
                        f"Terraform Drift: Subnet '{sub}' not found in rendered HCL resources.")
        else:
            subnet_names = ["subnet-ingress", "subnet-app",
                            "subnet-data", "subnet-mgmt", "subnet-pe"]
            for sub in subnet_names:
                possible = get_possible_names(sub)
                if not any(name in tf_resource_names for name in possible):
                    warnings.append(
                        f"Terraform Drift: Subnet '{sub}' not found in rendered HCL resources.")

        # 5. Check for basic resource count alignment
        tf_resource_count = len(tf_resources)
        if tf_resource_count < 10:
            warnings.append(
                f"Terraform Drift: Only {tf_resource_count} Terraform resources rendered, expected at least 10.")

        # 6. Check DB resource exists
        has_db_in_arch = any(n.get("type") == "DatabaseNode" for n in nodes)
        has_db_in_tf = any(
            "postgresql" in t or "rds" in t or "cloudsql" in t or "cosmos" in t or "mysql" in t or "mongo" in t for t in tf_resource_types)
        if has_db_in_arch and not has_db_in_tf:
            warnings.append(
                "Terraform Drift: Database nodes exist in architecture but no database resource found in HCL.")

        return warnings

    def generate(self, nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]], services: List[Dict[str, Any]], provider: str) -> Dict[str, Any]:
        """
        Renders Jinja2 templates into multi-file compilable Terraform blocks based on nodes & services.
        Validates for duplicate identical modules and namespaces resources.
        Returns HCL files and optional round-trip drift warnings.
        """
        logger.info(
            f"Rendering Terraform templates for cloud provider: {provider}")
        try:
            # Pre-processing: deduplicate identical nodes (based on exact same id)
            unique_nodes = {n["id"]: n for n in nodes}.values()
            nodes = list(unique_nodes)

            # Detect compute type from architecture nodes
            compute_type = self._detect_compute_type(nodes)

            # Detect shared infrastructural needs
            has_backend = any(n.get("type") == "BackendNode" for n in nodes)
            has_frontend = any(n.get("type") == "FrontendNode" for n in nodes)
            has_database = any(n.get("type") == "DatabaseNode" for n in nodes)

            # Extract custom configurations from nodes
            project_name_val = "archgen"
            region_val = "eastus" if provider.lower() == "azure" else (
                "us-east-1" if provider.lower() == "aws" else "us-central1")
            rg_val = "rg-production"
            vnet_cidr_val = "10.0.0.0/16"

            subnet_cidrs = {
                "subnet-ingress": "10.0.1.0/24",
                "subnet-mgmt": "10.0.4.0/24",
                "subnet-pe": "10.0.5.0/24",
                "subnet-app": "10.0.2.0/24",
                "subnet-data": "10.0.3.0/24"
            }

            # Extract microservice node IDs for Kubernetes resource rendering
            microservice_nodes = [
                n for n in nodes
                if str(n.get("id", "")).lower().startswith("svc-")
            ]

            for node in nodes:
                n_id = str(node.get("id", "")).lower()
                n_type = str(node.get("type", ""))
                label = str(node.get("data", {}).get("label", ""))

                if n_type == "RegionGroupNode" or n_id == "region-group":
                    if "region:" in label.lower():
                        region_val = label.split(":", 1)[1].strip()
                    elif "cloud region:" in label.lower():
                        region_val = label.split(":", 1)[1].strip()
                    else:
                        region_val = label.strip()

                elif n_type == "ResourceGroupNode" or n_id == "rg-group":
                    if "scope:" in label.lower():
                        rg_val = label.split(":", 1)[1].strip()
                    elif "resource group:" in label.lower():
                        rg_val = label.split(":", 1)[1].strip()
                    else:
                        rg_val = label.strip()

                elif n_type == "VNetGroupNode" or n_id == "vnet-group":
                    vnet_split = re.split(r'vnet\):|vpc\):',
                                          label, flags=re.IGNORECASE)
                    if len(vnet_split) > 1:
                        vnet_cidr_val = vnet_split[1].strip()
                    elif ":" in label:
                        vnet_cidr_val = label.split(":", 1)[1].strip()
                    else:
                        vnet_cidr_val = label.strip()
                    vnet_cidr_val = vnet_cidr_val.replace(
                        "[", "").replace("]", "").strip()

                elif n_type == "SubnetGroupNode" or n_id.startswith("subnet-"):
                    cidr_match = re.search(r"(\d+\.\d+\.\d+\.\d+/\d+)", label)
                    if cidr_match:
                        subnet_cidrs[n_id] = cidr_match.group(1)

            # Sanitize project name
            project_name_val = re.sub(r'[^a-zA-Z0-9-]', '', rg_val.replace(
                "rg-", "") if rg_val.startswith("rg-") else rg_val).lower()
            if not project_name_val:
                project_name_val = "archgen"

            # Sanitize region for clouds
            region_clean = region_val.lower().strip()
            region_map = {
                "azure": {
                    "east us": "eastus",
                    "central india": "centralindia",
                    "west europe": "westeurope",
                    "us-east-1": "eastus",
                    "ap-south-1": "centralindia",
                    "eu-west-1": "westeurope",
                    "us-east1": "eastus",
                    "asia-south1": "centralindia",
                    "europe-west1": "westeurope"
                },
                "aws": {
                    "east us": "us-east-1",
                    "central india": "ap-south-1",
                    "west europe": "eu-west-1",
                    "eastus": "us-east-1",
                    "centralindia": "ap-south-1",
                    "westeurope": "eu-west-1",
                    "us-east1": "us-east-1",
                    "asia-south1": "ap-south-1",
                    "europe-west1": "eu-west-1"
                },
                "gcp": {
                    "east us": "us-east1",
                    "central india": "asia-south1",
                    "west europe": "europe-west1",
                    "eastus": "us-east1",
                    "centralindia": "asia-south1",
                    "westeurope": "europe-west1",
                    "us-east-1": "us-east1",
                    "ap-south-1": "asia-south1",
                    "eu-west-1": "europe-west1"
                }
            }

            prov_lower = provider.lower()
            if prov_lower in region_map and region_clean in region_map[prov_lower]:
                region_clean = region_map[prov_lower][region_clean]
            else:
                if prov_lower == "azure":
                    region_clean = region_clean.replace(" ", "")
                else:
                    region_clean = region_clean.replace(" ", "-")

            # Map parameters
            context = {
                "nodes": nodes,
                "edges": edges,
                "services": services,
                "provider": provider.lower(),
                "has_backend": has_backend,
                "has_frontend": has_frontend,
                "has_database": has_database,
                "project_name": project_name_val,
                "region": region_clean,
                "resource_group": rg_val,
                "vnet_cidr": vnet_cidr_val,
                "subnet_cidrs": subnet_cidrs,
                "compute_type": compute_type,
                "microservice_nodes": microservice_nodes
            }

            provider_lower = provider.lower()
            if provider_lower not in ["azure", "aws", "gcp"]:
                provider_lower = "azure"

            # Dynamically switch the Jinja loader environment based on provider
            provider_env = Environment(
                loader=FileSystemLoader(os.path.join(
                    self.templates_dir, provider_lower)),
                trim_blocks=True,
                lstrip_blocks=True
            )
            provider_env.filters['sanitize_id'] = self.env.filters['sanitize_id']

            # Load templates
            main_template = provider_env.get_template("main.tf.j2")
            variables_template = provider_env.get_template("variables.tf.j2")
            outputs_template = provider_env.get_template("outputs.tf.j2")
            tfvars_template = provider_env.get_template("terraform.tfvars.j2")

            # Render
            main_tf = main_template.render(context)
            variables_tf = variables_template.render(context)
            outputs_tf = outputs_template.render(context)
            tfvars_tf = tfvars_template.render(context)

            # Round-trip drift validation
            drift_warnings = self.validate_terraform_drift(
                main_tf, nodes, compute_type)

            # Generate deployment guide text dynamically based on provider
            cli_auth = "az login"
            if provider_lower == "aws":
                cli_auth = "aws configure"
            elif provider_lower == "gcp":
                cli_auth = "gcloud auth application-default login"

            instructions = (
                f"## Deployment Operations Guide ({provider_lower.upper()})\n\n"
                "1. Ensure you have the Terraform CLI installed (version >= 1.3.0).\n"
                f"2. Authenticate to the cloud provider via CLI: `{cli_auth}`\n"
                "3. Copy the generated files (`main.tf`, `variables.tf`, `outputs.tf`, `terraform.tfvars`) into an empty local folder.\n"
                "4. Provide sensitive values like `db_password` through environment variables (e.g. `TF_VAR_db_password`) or a secret store.\n"
                "5. Copy `terraform.tfvars` only for non-secret inputs.\n"
                "6. Execute initialization:\n"
                "   ```bash\n"
                "   terraform init\n"
                "   ```\n"
                "7. Preview deployment plan changes:\n"
                "   ```bash\n"
                "   terraform plan\n"
                "   ```\n"
                f"8. Provision infrastructure on {provider_lower.upper()}:\n"
                "   ```bash\n"
                "   terraform apply -auto-approve\n"
                "   ```"
            )

            logger.info("Successfully generated multi-file HCL templates.")
            return {
                "main_tf": main_tf,
                "variables_tf": variables_tf,
                "outputs_tf": outputs_tf,
                "terraform_tfvars": tfvars_tf,
                "instructions": instructions,
                "warnings": drift_warnings
            }
        except Exception as e:
            logger.error(f"Failed rendering Terraform HCL templates: {e}")
            raise e
