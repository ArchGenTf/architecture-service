import re
from typing import Dict, Any, List, Set

class InfrastructureReasoningEngine:
    """
    Deterministic Infrastructure Reasoning Engine for ArchGen.
    Eliminates template fallbacks and direct AI-hallucinated structural topologies.
    """

    WORKLOAD_TYPES = [
        "ott",
        "banking",
        "ecommerce",
        "ai_platform",
        "saas_platform",
        "gaming_backend",
        "crud",
        "analytics",
        "microservices"
    ]

    def __init__(self, cloud_provider: str = "azure", requirements: Any = None):
        self.cloud_provider = cloud_provider.lower()
        self.projectName = "Enterprise Stack"
        self.region = "East US"
        self.resource_group = "rg-production"
        self.vnet_cidr = "10.0.0.0/16"
        self.compute_type = "AKS"
        self.database_type = "PostgreSQL"
        
        if requirements:
            self.projectName = getattr(requirements, "projectName", None) or "Enterprise Stack"
            self.region = getattr(requirements, "region", None) or "East US"
            self.resource_group = getattr(requirements, "resourceGroup", None) or "rg-production"
            self.vnet_cidr = getattr(requirements, "vnetCIDR", None) or "10.0.0.0/16"
            self.compute_type = getattr(requirements, "computeType", None) or getattr(requirements, "application_type", None) or "AKS"
            self.database_type = getattr(requirements, "database_type", None) or "PostgreSQL"

    def classify_workload(self, app_description: str, expected_users: str) -> str:
        desc = app_description.lower()
        users = expected_users.lower()

        if any(w in desc for w in ["bank", "fintech", "payment", "transaction", "ledger", "pci", "banking", "finance"]):
            return "banking"
        if any(w in desc for w in ["ott", "streaming", "video", "broadcast", "live", "media", "netflix", "youtube", "audio"]):
            return "ott"
        if any(w in desc for w in ["ai", "ml", "gpu", "llm", "deep learning", "inference", "training", "model", "openai", "gpt"]):
            return "ai_platform"
        if any(w in desc for w in ["ecommerce", "e-commerce", "shop", "retail", "cart", "store", "product catalog", "checkout"]):
            return "ecommerce"
        if any(w in desc for w in ["saas", "multi-tenant", "b2b saas", "subscription portal", "tenant"]):
            return "saas_platform"
        if any(w in desc for w in ["game", "gaming", "multiplayer", "matchmaking", "lobby", "leaderboard", "unreal", "unity"]):
            return "gaming_backend"
        if any(w in desc for w in ["analytics", "big data", "data warehouse", "lakehouse", "spark", "hadoop", "bi tool", "dashboard", "telemetry"]):
            return "analytics"
        if any(w in desc for w in ["microservices", "kubernetes", "aks", "eks", "gke", "service mesh", "istio", "event-driven"]):
            return "microservices"
        if any(w in desc for w in ["simple", "crud", "basic", "portfolio", "hobby", "internal tool", "small database"]):
            return "crud"
        
        if "million" in users or "100k" in users or "100,000" in users:
            return "saas_platform"
        
        return "crud"

    def get_cloud_resource_name(self, generic_type: str) -> str:
        generic_key = generic_type.lower().strip()
        mapping = {
            "azure": {
                "cdn": "Azure Front Door / CDN",
                "waf": "Azure WAF",
                "appgw": "Azure Application Gateway",
                "firewall": "Azure Firewall",
                "aks": "Azure Kubernetes Service (AKS)",
                "vmss": "Azure VM Scale Set (VMSS)",
                "app service": "Azure App Service (PaaS)",
                "azure functions": "Azure Functions (Serverless)",
                "container apps": "Azure Container Apps (Microservices)",
                "postgres": "Azure Database for PostgreSQL",
                "postgresql": "Azure Database for PostgreSQL",
                "mysql": "Azure Database for MySQL",
                "mongodb": "MongoDB Atlas on Azure",
                "cosmosdb": "Azure Cosmos DB API",
                "redis": "Azure Cache for Redis",
                "keyvault": "Azure Key Vault",
                "blob": "Azure Blob Storage",
                "acr": "Azure Container Registry",
                "log_analytics": "Azure Log Analytics Workspace",
                "app_insights": "Application Insights",
                "bastion": "Azure Bastion",
                "backup": "Azure Backup Vault",
                "iam": "Microsoft Entra ID",
                "pe": "Azure Private Endpoint",
                "nsg": "Network Security Group (NSG)",
                "rt": "Route Table (RT)",
                "internet": "Public Internet Gateway",
                "front_door": "Azure Front Door",
                "ddos": "Azure DDoS Protection Plan",
                "waf_policy": "Web Application Firewall (WAF) Policy",
                "azure_firewall": "Azure Firewall",
                "firewall_policy": "Azure Firewall Policy",
                "aks_cluster": "Azure Kubernetes Service (AKS) Cluster",
                "aks_system": "AKS System Node Pool",
                "aks_user": "AKS User Node Pool",
                "ingress_controller": "AKS Ingress Controller",
                "managed_identity": "User Assigned Managed Identity",
                "role_assignment": "Azure Role Assignment",
                "azure_monitor": "Azure Monitor Dashboard",
                "alerts": "Azure Monitor Alerts",
                "diagnostic_settings": "Diagnostic Settings",
                "backup_policy": "PostgreSQL Backup Policy",
                "backup_vault": "Azure Backup Vault",
                "recovery_vault": "Recovery Services Vault",
                "dns": "Azure DNS Zone"
            },
            "aws": {
                "cdn": "AWS CloudFront",
                "waf": "AWS WAF",
                "appgw": "Application Load Balancer (ALB)",
                "firewall": "AWS Network Firewall",
                "aks": "Amazon Elastic Kubernetes Service (EKS)",
                "vmss": "AWS EC2 Auto Scaling Group",
                "app service": "AWS Elastic Beanstalk (PaaS)",
                "azure functions": "AWS Lambda (Serverless)",
                "container apps": "Amazon ECS / Fargate (Microservices)",
                "postgres": "Amazon RDS for PostgreSQL",
                "postgresql": "Amazon RDS for PostgreSQL",
                "mysql": "Amazon RDS for MySQL",
                "mongodb": "MongoDB Atlas on AWS",
                "cosmosdb": "Amazon DynamoDB (NoSQL)",
                "redis": "Amazon ElastiCache",
                "keyvault": "AWS Secrets Manager",
                "blob": "Amazon S3",
                "acr": "Amazon ECR",
                "log_analytics": "Amazon CloudWatch Logs",
                "app_insights": "AWS X-Ray",
                "bastion": "AWS Session Manager / Bastion",
                "backup": "AWS Backup",
                "iam": "AWS IAM",
                "pe": "VPC Endpoint",
                "nsg": "VPC Security Group",
                "rt": "VPC Route Table",
                "internet": "AWS Internet Gateway",
                "front_door": "AWS CloudFront CDN",
                "ddos": "AWS Shield Advanced",
                "waf_policy": "AWS WAF WebACL",
                "azure_firewall": "AWS Network Firewall",
                "firewall_policy": "AWS Firewall Rule Group",
                "aks_cluster": "Amazon EKS Cluster",
                "aks_system": "EKS System Node Group",
                "aks_user": "EKS User Node Group",
                "ingress_controller": "EKS Ingress Controller",
                "managed_identity": "AWS IAM Role",
                "role_assignment": "IAM Policy Attachment",
                "azure_monitor": "Amazon CloudWatch Dashboard",
                "alerts": "CloudWatch Alarm Rules",
                "diagnostic_settings": "CloudWatch Subscription Filter",
                "backup_policy": "AWS Backup Plan",
                "backup_vault": "AWS Backup Vault",
                "recovery_vault": "AWS Backup Vault (DR)",
                "dns": "Route53 Hosted Zone"
            },
            "gcp": {
                "cdn": "Cloud CDN",
                "waf": "Cloud Armor",
                "appgw": "Global HTTPS Load Balancer",
                "firewall": "Cloud Next-Gen Firewall",
                "aks": "Google Kubernetes Engine (GKE)",
                "vmss": "GCP Managed Instance Group",
                "app service": "Google App Engine (PaaS)",
                "azure functions": "Google Cloud Functions (Serverless)",
                "container apps": "Google Cloud Run (Microservices)",
                "postgres": "Cloud SQL for PostgreSQL",
                "postgresql": "Cloud SQL for PostgreSQL",
                "mysql": "Cloud SQL for MySQL",
                "mongodb": "MongoDB Atlas on GCP",
                "cosmosdb": "Cloud Firestore / Bigtable",
                "redis": "MemoryStore for Redis",
                "keyvault": "Secret Manager",
                "blob": "Cloud Storage",
                "acr": "Artifact Registry",
                "log_analytics": "Cloud Logging",
                "app_insights": "Cloud Trace",
                "bastion": "IAP / Bastion Host",
                "backup": "Cloud Backup and DR",
                "iam": "Cloud IAM",
                "pe": "Private Service Connect",
                "dns": "Cloud DNS",
                "nsg": "VPC Firewall Rules",
                "rt": "VPC Route Table",
                "internet": "Google Cloud Cloud NAT",
                "front_door": "Google Cloud CDN",
                "ddos": "Google Cloud Armor DDoS",
                "waf_policy": "Cloud Armor WAF Policy",
                "azure_firewall": "Cloud Next-Gen Firewall",
                "firewall_policy": "Firewall Policy",
                "aks_cluster": "Google GKE Cluster",
                "aks_system": "GKE System Node Pool",
                "aks_user": "GKE User Node Pool",
                "ingress_controller": "GKE Ingress Controller",
                "managed_identity": "GCP Service Account",
                "role_assignment": "IAM Policy Binding",
                "azure_monitor": "Google Cloud Monitoring",
                "alerts": "Cloud Monitoring Alerts",
                "diagnostic_settings": "Google Cloud Log Sink",
                "backup_policy": "Cloud SQL Backup Plan",
                "backup_vault": "Google Cloud Backup Vault",
                "recovery_vault": "Google Cloud Backup Vault (DR)"
            }
        }
        provider = self.cloud_provider if self.cloud_provider in mapping else "azure"
        return mapping[provider].get(generic_key, generic_type.capitalize())

    def synthesize_from_intent(self) -> Dict[str, Any]:
        """
        Synthesizes a highly detailed, enterprise-grade production-ready visual topology graph.
        Returns 50+ nodes and 50+ edges strictly covering all network/security boundaries,
        supporting HA layouts, diagnostic monitor sinks, and explicit Private Endpoints.
        """
        nodes = []
        edges = []
        services = ["identity", "compute", "storage", "database", "networking", "security"]

        # Extract IP prefix from VNet CIDR (e.g. "10.0" from "10.0.0.0/16")
        import re
        prefix_match = re.match(r'^(\d{1,3}\.\d{1,3})\.', self.vnet_cidr)
        ip_prefix = prefix_match.group(1) if prefix_match else "10.0"

        # 1. Outer Nesting Structure Node definitions
        nodes.append({
            "id": "region-group",
            "type": "RegionGroupNode",
            "position": {"x": 50, "y": 50},
            "data": {"label": f"Cloud Region: {self.region}"},
            "style": {"width": 2900, "height": 2280}
        })

        nodes.append({
            "id": "rg-group",
            "type": "ResourceGroupNode",
            "parentNode": "region-group",
            "position": {"x": 30, "y": 60},
            "data": {"label": f"Resource Scope: {self.resource_group}"},
            "style": {"width": 2840, "height": 2190}
        })

        nodes.append({
            "id": "vnet-group",
            "type": "VNetGroupNode",
            "parentNode": "rg-group",
            "position": {"x": 30, "y": 60},
            "data": {"label": f"Virtual Network (VPC): {self.vnet_cidr}"},
            "style": {"width": 2780, "height": 2100}
        })

        # 2. Subnet Nodes definitions (Updated grid placement coordinates to avoid overlapping)
        subnets = {
            "subnet-ingress": {"label": "Ingress Subnet", "cidr": f"{ip_prefix}.1.0/24", "x": 40, "y": 60, "width": 2180, "height": 280},
            "subnet-mgmt": {"label": "Management Subnet", "cidr": f"{ip_prefix}.4.0/24", "x": 40, "y": 380, "width": 2180, "height": 280},
            "subnet-app": {"label": "Application Subnet", "cidr": f"{ip_prefix}.2.0/24", "x": 40, "y": 700, "width": 2180, "height": 420},
            "subnet-data": {"label": "Data Subnet", "cidr": f"{ip_prefix}.3.0/24", "x": 40, "y": 1160, "width": 2180, "height": 420},
            "subnet-pe": {"label": "Private Endpoint Subnet", "cidr": f"{ip_prefix}.5.0/24", "x": 40, "y": 1620, "width": 2180, "height": 420},
        }

        for sub_id, cfg in subnets.items():
            nodes.append({
                "id": sub_id,
                "type": "SubnetGroupNode",
                "parentNode": "vnet-group",
                "position": {"x": cfg["x"], "y": cfg["y"]},
                "data": {
                    "label": cfg["label"],
                    "subnet": cfg["cidr"],
                    "provider": self.cloud_provider
                },
                "style": {"width": cfg["width"], "height": cfg["height"]}
            })

        # Helper to inject nested resources
        def add_nested_node(id_val: str, n_type: str, label: str, x: int, y: int, parent_subnet: str, detail: str, cost: int, is_public: bool = False):
            nodes.append({
                "id": id_val,
                "type": n_type,
                "parentNode": parent_subnet,
                "position": {"x": x, "y": y},
                "data": {
                    "label": label,
                    "typeSubText": detail,
                    "subnet": parent_subnet,
                    "provider": self.cloud_provider,
                    "cost": f"${cost}/month",
                    "monthly_cost": f"${cost}/month",
                    "estimated_monthly_cost": cost,
                    "public": is_public,
                    "private": not is_public,
                    "resource_type": detail
                }
            })

        def add_edge(source: str, target: str, animated: bool = False):
            edges.append({
                "id": f"e-{source}-{target}",
                "source": source,
                "target": target,
                "animated": animated
            })

        # --- 3. Subnet NSG and Route Tables (Required for every subnet) ---
        for sub_id, cfg in subnets.items():
            short_name = sub_id.replace("subnet-", "")
            add_nested_node(f"nsg-{short_name}", "SecurityNode", f"{self.get_cloud_resource_name('nsg')} - {cfg['label']}", 30, 60, sub_id, "azurerm_network_security_group", 0, is_public=False)
            add_nested_node(f"rt-{short_name}", "GatewayNode", f"{self.get_cloud_resource_name('rt')} - {cfg['label']}", 30, 180, sub_id, "azurerm_route_table", 0, is_public=False)

        # --- 4. Edge Layer Nodes (Internet, Front Door, DDoS, WAF, App Gateway, Firewall) ---
        # Put internet and front door at the resource group level (y: 10 sits above VNet-group y: 60)
        nodes.append({
            "id": "internet",
            "type": "GatewayNode",
            "parentNode": "rg-group",
            "position": {"x": 40, "y": 10},
            "data": {
                "label": self.get_cloud_resource_name("internet"),
                "typeSubText": "public_gateway",
                "provider": self.cloud_provider,
                "cost": "$0/month",
                "monthly_cost": "$0/month",
                "estimated_monthly_cost": 0,
                "public": True,
                "private": False,
                "resource_type": "public_gateway"
            }
        })
        nodes.append({
            "id": "front-door",
            "type": "GatewayNode",
            "parentNode": "rg-group",
            "position": {"x": 340, "y": 10},
            "data": {
                "label": self.get_cloud_resource_name("front_door"),
                "typeSubText": "azurerm_cdn_frontdoor_profile",
                "provider": self.cloud_provider,
                "cost": "$35/month",
                "monthly_cost": "$35/month",
                "estimated_monthly_cost": 35,
                "public": True,
                "private": False,
                "resource_type": "azurerm_cdn_frontdoor_profile"
            }
        })
        nodes.append({
            "id": "ddos-protection",
            "type": "SecurityNode",
            "parentNode": "rg-group",
            "position": {"x": 640, "y": 10},
            "data": {
                "label": self.get_cloud_resource_name("ddos"),
                "typeSubText": "azurerm_network_ddos_protection_plan",
                "provider": self.cloud_provider,
                "cost": "$50/month",
                "monthly_cost": "$50/month",
                "estimated_monthly_cost": 50,
                "public": False,
                "private": True,
                "resource_type": "azurerm_network_ddos_protection_plan"
            }
        })
        nodes.append({
            "id": "waf-policy",
            "type": "SecurityNode",
            "parentNode": "rg-group",
            "position": {"x": 940, "y": 10},
            "data": {
                "label": self.get_cloud_resource_name("waf_policy"),
                "typeSubText": "azurerm_web_application_firewall_policy",
                "provider": self.cloud_provider,
                "cost": "$20/month",
                "monthly_cost": "$20/month",
                "estimated_monthly_cost": 20,
                "public": True,
                "private": False,
                "resource_type": "azurerm_web_application_firewall_policy"
            }
        })

        # Add Gateway & Firewall inside Ingress Subnet
        add_nested_node("app-gateway", "GatewayNode", self.get_cloud_resource_name("appgw"), 360, 60, "subnet-ingress", "azurerm_application_gateway", 40, is_public=True)
        add_nested_node("azure-firewall", "GatewayNode", self.get_cloud_resource_name("azure_firewall"), 720, 60, "subnet-ingress", "azurerm_firewall", 900, is_public=True)

        # Connect Edge Layer Flow
        add_edge("internet", "front-door", True)
        add_edge("front-door", "ddos-protection", False)
        add_edge("ddos-protection", "waf-policy", False)
        add_edge("waf-policy", "app-gateway", True)
        add_edge("app-gateway", "azure-firewall", True)

        compute_upper = str(self.compute_type).upper().replace("_", " ").replace("-", " ")

        # Create Shared Services and AKS Cluster Group containers in nodes list
        nodes.append({
            "id": "shared-services-group",
            "type": "SubnetGroupNode",
            "parentNode": "vnet-group",
            "position": {"x": 2200.0, "y": 60.0},
            "data": {"label": "Shared Services Group", "provider": self.cloud_provider, "resource_type": "subnet"},
            "style": {"width": 500, "height": 1200}
        })

        if "AKS" in compute_upper or "KUBERNETES" in compute_upper:
            nodes.append({
                "id": "aks-cluster-group",
                "type": "SubnetGroupNode",
                "parentNode": "subnet-app",
                "position": {"x": 350.0, "y": 40.0},
                "data": {"label": "AKS Cluster Group", "provider": self.cloud_provider, "resource_type": "subnet"},
                "style": {"width": 1780, "height": 340}
            })

            # --- 5. AKS Compute Layer Expansion (System/User Node pools, Ingress, APIs) ---
            add_nested_node("aks-cluster", "BackendNode", self.get_cloud_resource_name("aks_cluster"), 10, 20, "aks-cluster-group", "azurerm_kubernetes_cluster", 250, is_public=False)
            add_nested_node("aks-system-node-pool", "BackendNode", self.get_cloud_resource_name("aks_system"), 10, 120, "aks-cluster-group", "azurerm_kubernetes_cluster_node_pool", 100, is_public=False)
            add_nested_node("aks-user-node-pool", "BackendNode", self.get_cloud_resource_name("aks_user"), 10, 220, "aks-cluster-group", "azurerm_kubernetes_cluster_node_pool", 150, is_public=False)
            add_nested_node("aks-ingress-controller", "GatewayNode", self.get_cloud_resource_name("ingress_controller"), 300, 20, "aks-cluster-group", "nginx_ingress", 30, is_public=False)
            
            # Deploy microservices inside the AKS cluster group
            add_nested_node("svc-api-gateway", "GatewayNode", "API Gateway Controller", 300, 120, "aks-cluster-group", "api_gateway_service", 40, is_public=False)
            add_nested_node("aks-hpa", "MonitoringNode", "Horizontal Pod Autoscaler (HPA)", 300, 220, "aks-cluster-group", "kubernetes_horizontal_pod_autoscaler", 0, is_public=False)
            add_nested_node("svc-auth", "BackendNode", "Auth Service", 590, 20, "aks-cluster-group", "auth_microservice", 40, is_public=False)
            add_nested_node("svc-product", "BackendNode", "Product Service", 590, 120, "aks-cluster-group", "product_microservice", 40, is_public=False)
            add_nested_node("svc-order", "BackendNode", "Order Service", 880, 20, "aks-cluster-group", "order_microservice", 40, is_public=False)
            add_nested_node("svc-payment", "BackendNode", "Payment Service", 880, 120, "aks-cluster-group", "payment_microservice", 40, is_public=False)
            add_nested_node("svc-inventory", "BackendNode", "Inventory Service", 1170, 20, "aks-cluster-group", "inventory_microservice", 40, is_public=False)
            add_nested_node("svc-notification", "BackendNode", "Notification Service", 1170, 120, "aks-cluster-group", "notification_microservice", 30, is_public=False)

            # Connect ingress to compute
            add_edge("azure-firewall", "aks-ingress-controller", True)
            add_edge("aks-ingress-controller", "svc-api-gateway", True)
            add_edge("aks-cluster", "aks-system-node-pool", False)
            add_edge("aks-cluster", "aks-user-node-pool", False)

            # Microservice communication edges
            add_edge("svc-api-gateway", "svc-auth", True)
            add_edge("svc-api-gateway", "svc-product", True)
            add_edge("svc-api-gateway", "svc-order", True)
            add_edge("svc-api-gateway", "svc-payment", True)
            add_edge("svc-api-gateway", "svc-inventory", True)
            add_edge("svc-api-gateway", "svc-notification", True)

        elif "APP SERVICE" in compute_upper or "WEB APP" in compute_upper:
            # --- 5. App Service Compute Layer (Service Plan + Web Apps) ---
            add_nested_node("app-service-plan", "BackendNode", "App Service Plan", 100, 60, "subnet-app", "azurerm_service_plan", 75, is_public=False)
            add_nested_node("web-app", "BackendNode", "API Web App Gateway", 400, 60, "subnet-app", "azurerm_linux_web_app", 55, is_public=False)
            add_nested_node("svc-auth", "BackendNode", "Auth Service", 400, 180, "subnet-app", "azurerm_linux_web_app", 40, is_public=False)
            add_nested_node("svc-product", "BackendNode", "Product Service", 700, 60, "subnet-app", "azurerm_linux_web_app", 40, is_public=False)
            add_nested_node("svc-order", "BackendNode", "Order Service", 700, 180, "subnet-app", "azurerm_linux_web_app", 40, is_public=False)
            add_nested_node("svc-payment", "BackendNode", "Payment Service", 1000, 60, "subnet-app", "azurerm_linux_web_app", 40, is_public=False)
            add_nested_node("svc-inventory", "BackendNode", "Inventory Service", 1000, 180, "subnet-app", "azurerm_linux_web_app", 40, is_public=False)
            add_nested_node("svc-notification", "BackendNode", "Notification Service", 1300, 60, "subnet-app", "azurerm_linux_web_app", 30, is_public=False)

            # Ingress to App Service
            add_edge("azure-firewall", "web-app", True)
            add_edge("web-app", "svc-auth", True)
            add_edge("web-app", "svc-product", True)
            add_edge("web-app", "svc-order", True)
            add_edge("web-app", "svc-payment", True)
            add_edge("web-app", "svc-inventory", True)
            add_edge("web-app", "svc-notification", True)

        else:
            # --- 5. Container Apps Compute Layer ---
            add_nested_node("container-app-env", "BackendNode", "Container Apps Environment", 100, 60, "subnet-app", "azurerm_container_app_environment", 50, is_public=False)
            add_nested_node("svc-auth", "BackendNode", "Auth Service", 400, 60, "subnet-app", "azurerm_container_app", 40, is_public=False)
            add_nested_node("svc-product", "BackendNode", "Product Service", 400, 180, "subnet-app", "azurerm_container_app", 40, is_public=False)
            add_nested_node("svc-order", "BackendNode", "Order Service", 700, 60, "subnet-app", "azurerm_container_app", 40, is_public=False)
            add_nested_node("svc-payment", "BackendNode", "Payment Service", 700, 180, "subnet-app", "azurerm_container_app", 40, is_public=False)
            add_nested_node("svc-inventory", "BackendNode", "Inventory Service", 1000, 60, "subnet-app", "azurerm_container_app", 40, is_public=False)
            add_nested_node("svc-notification", "BackendNode", "Notification Service", 1000, 180, "subnet-app", "azurerm_container_app", 30, is_public=False)

            # Ingress to Container Apps
            add_edge("azure-firewall", "svc-auth", True)
            add_edge("svc-auth", "svc-product", True)
            add_edge("svc-auth", "svc-order", True)
            add_edge("svc-auth", "svc-payment", True)
            add_edge("svc-auth", "svc-inventory", True)
            add_edge("svc-auth", "svc-notification", True)

        # --- 6. Data Layer Expansion (PostgreSQL, HA standby, Redis, Storage) ---
        add_nested_node("db-primary", "DatabaseNode", self.get_cloud_resource_name("postgresql"), 360, 60, "subnet-data", "azurerm_postgresql_flexible_server", 115, is_public=False)
        add_nested_node("db-replica", "DatabaseNode", f"{self.get_cloud_resource_name('postgresql')} Replica", 360, 180, "subnet-data", "azurerm_postgresql_flexible_server_replica", 115, is_public=False)
        add_nested_node("db-backup-policy", "SecurityNode", self.get_cloud_resource_name("backup_policy"), 720, 60, "subnet-data", "azurerm_backup_policy_postgresql", 10, is_public=False)
        
        add_nested_node("redis", "CacheNode", self.get_cloud_resource_name("redis"), 1080, 60, "subnet-data", "azurerm_redis_cache", 45, is_public=False)
        add_nested_node("redis-replica", "CacheNode", f"{self.get_cloud_resource_name('redis')} Replica", 1080, 180, "subnet-data", "azurerm_redis_cache_replica", 45, is_public=False)

        add_nested_node("storage-account", "StorageNode", self.get_cloud_resource_name("blob"), 1440, 60, "subnet-data", "azurerm_storage_account", 25, is_public=False)
        add_nested_node("storage-replica", "StorageNode", f"{self.get_cloud_resource_name('blob')} GRS Replica", 1440, 180, "subnet-data", "azurerm_storage_account_replica", 25, is_public=False)
        add_nested_node("blob-container", "StorageNode", "Blob Containers", 1800, 60, "subnet-data", "azurerm_storage_container", 0, is_public=False)

        # Database replicas & backup links
        add_edge("db-primary", "db-replica", True)
        add_edge("db-primary", "db-backup-policy", False)
        add_edge("redis", "redis-replica", True)
        add_edge("storage-account", "storage-replica", True)
        add_edge("storage-account", "blob-container", False)

        # --- 7. Security Layer (Managed Identity, Role Assignment, Firewall Policy, Bastion, Jumpbox) ---
        add_nested_node("bastion", "GatewayNode", self.get_cloud_resource_name("bastion"), 360, 60, "subnet-mgmt", "azurerm_bastion_host", 95, is_public=True)
        add_nested_node("jumpbox", "BackendNode", "Management Jumpbox VM", 360, 180, "subnet-mgmt", "azurerm_linux_virtual_machine", 60, is_public=False)
        add_nested_node("managed-identity", "SecurityNode", self.get_cloud_resource_name("managed_identity"), 720, 60, "subnet-mgmt", "azurerm_user_assigned_identity", 0, is_public=False)
        add_nested_node("role-assignment", "SecurityNode", self.get_cloud_resource_name("role_assignment"), 720, 180, "subnet-mgmt", "azurerm_role_assignment", 0, is_public=False)
        add_nested_node("firewall-policy", "SecurityNode", self.get_cloud_resource_name("firewall_policy"), 1080, 60, "subnet-mgmt", "azurerm_firewall_policy", 30, is_public=False)

        add_edge("azure-firewall", "firewall-policy", False)
        add_edge("managed-identity", "role-assignment", False)

        if "AKS" in compute_upper or "KUBERNETES" in compute_upper:
            add_edge("role-assignment", "aks-cluster", False)
        elif "APP SERVICE" in compute_upper or "WEB APP" in compute_upper:
            add_edge("role-assignment", "web-app", False)
        else:
            add_edge("role-assignment", "container-app-env", False)

        # --- 8. Private Endpoint Subnet Resources ---
        add_nested_node("pe-db", "SecurityNode", "PE PostgreSQL DB", 360, 60, "subnet-pe", "azurerm_private_endpoint_db", 10, is_public=False)
        add_nested_node("pe-redis", "SecurityNode", "PE Redis Cache", 720, 60, "subnet-pe", "azurerm_private_endpoint_redis", 10, is_public=False)
        add_nested_node("pe-storage", "SecurityNode", "PE Blob Storage", 1080, 60, "subnet-pe", "azurerm_private_endpoint_storage", 10, is_public=False)
        add_nested_node("pe-kv", "SecurityNode", "PE Key Vault", 1440, 60, "subnet-pe", "azurerm_private_endpoint_kv", 10, is_public=False)

        # --- 9. Shared Environment Resources (Scoped to shared-services-group) ---
        add_nested_node("keyvault", "SecurityNode", self.get_cloud_resource_name("keyvault"), 50, 60, "shared-services-group", "azurerm_key_vault", 20, is_public=False)
        add_nested_node("log-analytics", "MonitoringNode", self.get_cloud_resource_name("log_analytics"), 50, 160, "shared-services-group", "azurerm_log_analytics_workspace", 100, is_public=False)
        add_nested_node("app-insights", "MonitoringNode", self.get_cloud_resource_name("app_insights"), 50, 260, "shared-services-group", "azurerm_application_insights", 50, is_public=False)
        add_nested_node("azure-monitor", "MonitoringNode", self.get_cloud_resource_name("azure_monitor"), 50, 360, "shared-services-group", "azurerm_monitor", 25, is_public=False)
        add_nested_node("alerts", "MonitoringNode", self.get_cloud_resource_name("alerts"), 50, 460, "shared-services-group", "azurerm_monitor_metric_alert", 5, is_public=False)
        add_nested_node("diagnostic-settings", "MonitoringNode", self.get_cloud_resource_name("diagnostic_settings"), 50, 560, "shared-services-group", "azurerm_monitor_diagnostic_setting", 5, is_public=False)
        add_nested_node("backup-vault", "StorageNode", self.get_cloud_resource_name("backup_vault"), 50, 660, "shared-services-group", "azurerm_data_protection_backup_vault", 20, is_public=False)
        add_nested_node("recovery-vault", "SecurityNode", self.get_cloud_resource_name("recovery_vault"), 50, 760, "shared-services-group", "azurerm_recovery_services_vault", 30, is_public=False)
        add_nested_node("acr", "BackendNode", self.get_cloud_resource_name("acr"), 50, 860, "shared-services-group", "azurerm_container_registry", 50, is_public=False)
        add_nested_node("cost-management", "MonitoringNode", "Cost Management Billing Profile", 50, 960, "shared-services-group", "azurerm_billing_profile", 0, is_public=False)

        # Private Endpoint Connection Edges
        add_edge("pe-db", "db-primary", False)
        add_edge("pe-redis", "redis", False)
        add_edge("pe-storage", "storage-account", False)
        add_edge("pe-kv", "keyvault", False)

        # Microservice Private Link consumption routes
        add_edge("svc-auth", "pe-kv", True)
        add_edge("svc-product", "pe-db", True)
        add_edge("svc-order", "pe-db", True)
        add_edge("svc-payment", "pe-db", True)
        add_edge("svc-inventory", "pe-db", True)
        add_edge("svc-product", "pe-redis", True)
        add_edge("svc-notification", "pe-storage", True)

        # Backup vault links
        add_edge("db-primary", "backup-vault", False)
        add_edge("storage-account", "backup-vault", False)
        add_edge("backup-vault", "recovery-vault", False)

        # Monitoring reduced path connection edges
        add_edge("svc-auth", "app-insights", False)
        add_edge("svc-product", "app-insights", False)
        add_edge("svc-order", "app-insights", False)
        add_edge("svc-payment", "app-insights", False)
        add_edge("svc-inventory", "app-insights", False)
        add_edge("svc-notification", "app-insights", False)

        if "AKS" in compute_upper or "KUBERNETES" in compute_upper:
            add_edge("svc-api-gateway", "app-insights", False)

        add_edge("app-insights", "log-analytics", False)
        add_edge("log-analytics", "azure-monitor", False)
        add_edge("azure-monitor", "alerts", False)

        # Diagnostic settings forwarded to Log Analytics
        if "AKS" in compute_upper or "KUBERNETES" in compute_upper:
            add_edge("aks-cluster", "diagnostic-settings", False)
        elif "APP SERVICE" in compute_upper or "WEB APP" in compute_upper:
            add_edge("app-service-plan", "diagnostic-settings", False)
        else:
            add_edge("container-app-env", "diagnostic-settings", False)

        add_edge("db-primary", "diagnostic-settings", False)
        add_edge("app-gateway", "diagnostic-settings", False)
        add_edge("diagnostic-settings", "log-analytics", False)

        # Subnet association edges (Visual connectivity representing NSG & Route Table binding)
        for sub_id in subnets.keys():
            short_name = sub_id.replace("subnet-", "")
            add_edge(f"nsg-{short_name}", sub_id, False)
            add_edge(f"rt-{short_name}", sub_id, False)

        return {
            "nodes": nodes,
            "edges": edges,
            "services": services
        }

    def normalize_topology(self, topology: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sanitizes topology payloads coming back from synthesis, preserving parentNode references and styles.
        """
        nodes = topology.get("nodes") or []
        edges = topology.get("edges") or []
        services = topology.get("services") or []

        if not isinstance(nodes, list) or not isinstance(edges, list) or not isinstance(services, list):
            return {"nodes": [], "edges": [], "services": []}

        allowed_types = {
            "GatewayNode",
            "FrontendNode",
            "BackendNode",
            "DatabaseNode",
            "CacheNode",
            "StorageNode",
            "SecurityNode",
            "MonitoringNode",
            "RegionGroupNode",
            "ResourceGroupNode",
            "VNetGroupNode",
            "SubnetGroupNode",
        }

        normalized_nodes = []
        seen_nodes: Set[str] = set()
        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_id = str(node.get("id", "")).strip()
            node_type = str(node.get("type", "")).strip()
            if not node_id or node_id in seen_nodes or node_type not in allowed_types:
                continue
            data = node.get("data") if isinstance(node.get("data"), dict) else {}
            position = node.get("position") if isinstance(node.get("position"), dict) else {}
            style = node.get("style") if isinstance(node.get("style"), dict) else {}
            
            # Map cost and public metadata fields robustly
            cost_val = data.get("cost") or data.get("monthly_cost") or "$0/month"
            is_public = bool(data.get("public", False))
            
            normalized_node = {
                "id": node_id,
                "type": node_type,
                "data": {
                    "label": str(data.get("label", node_id)),
                    "status": str(data.get("status", "active")),
                    "cost": cost_val,
                    "monthly_cost": cost_val,
                    "typeSubText": data.get("typeSubText") or data.get("resource_type", ""),
                    "subnet": str(data.get("subnet", "")),
                    "layer": str(data.get("layer", "")),
                    "public": is_public,
                    "private": not is_public,
                    "provider": str(data.get("provider", self.cloud_provider)),
                    "resource_type": data.get("resource_type") or data.get("typeSubText") or ""
                },
                "position": {
                    "x": float(position.get("x", 0)),
                    "y": float(position.get("y", 0)),
                }
            }
            
            # Critical: Preserve hierarchical properties
            if "parentNode" in node:
                normalized_node["parentNode"] = node["parentNode"]
            if style:
                normalized_node["style"] = style
            if "width" in node:
                normalized_node["width"] = node["width"]
            if "height" in node:
                normalized_node["height"] = node["height"]

            normalized_nodes.append(normalized_node)
            seen_nodes.add(node_id)

        node_ids = {node["id"] for node in normalized_nodes}
        normalized_edges = []
        seen_edges: Set[str] = set()
        for edge in edges:
            if not isinstance(edge, dict):
                continue
            edge_id = str(edge.get("id", "")).strip()
            source = str(edge.get("source", "")).strip()
            target = str(edge.get("target", "")).strip()
            if not edge_id or edge_id in seen_edges or source not in node_ids or target not in node_ids:
                continue
            normalized_edges.append({
                "id": edge_id,
                "source": source,
                "target": target,
                "animated": bool(edge.get("animated", False))
            })
            seen_edges.add(edge_id)

        normalized_services = []
        seen_services: Set[str] = set()
        for service in services:
            if not isinstance(service, dict):
                continue
            service_name = str(service.get("name", "")).strip()
            if not service_name or service_name in seen_services:
                continue
            normalized_services.append({
                "name": service_name,
                "category": str(service.get("category", "backend")),
                "description": str(service.get("description", service_name)),
            })
            seen_services.add(service_name)

        if not normalized_nodes:
            return {"nodes": [], "edges": [], "services": []}

        return {
            "nodes": normalized_nodes,
            "edges": normalized_edges,
            "services": normalized_services,
        }
