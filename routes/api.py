import asyncio
import json
import logging
import re
import uuid
from typing import Dict, Any, List

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
import os


# Shared schemas
from models.schemas import (
    RequirementInput,
    ArchitectureResponse,
    TerraformRequest,
    TerraformResponse,
    AiAssistRequest,
)

# Core engines
from terraform.engine import TerraformEngine
from utils.reasoning_engine import InfrastructureReasoningEngine
from utils.cache_manager import CacheManager
from utils.performance_logger import PerformanceLogger

# Agent imports (Only for enrichment)
from agents.security_optimization import SecurityOptimizationAgent
from agents.complexity_auditor import ComplexityAuditorAgent
from agents.cost_optimization import CostOptimizationAgent
from agents.architecture_explanation import ArchitectureExplanationAgent

logger = logging.getLogger('api_routes')
router = APIRouter()
tf_engine = TerraformEngine()
cache_manager = CacheManager()
perf_logger = PerformanceLogger()

from utils.provider_manager import ProviderManager
from typing import List, Dict, Any

def flatten_nested_nodes(nodes: List[Dict[str, Any]], parent_id: str = None) -> List[Dict[str, Any]]:
    """
    Flatten a nested node tree (nodes with 'children' arrays) into a flat list.
    The AI sometimes returns a nested tree instead of the flat list specified in the schema.
    This converts it to a flat list and assigns parentNode from the nesting structure.
    Handles wrapper nodes without IDs (anonymous containers) by recursing into their children.
    Also lifts resource_id from data{} to top-level id when the AI omits the top-level id.
    """
    flat = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        children = node.pop("children", None)  # Remove children key before adding to flat list

        # Lift resource_id from data{} to top-level id if missing
        node_id = node.get("id")
        if (node_id is None or str(node_id).strip() == "") and isinstance(node.get("data"), dict):
            node_id = node["data"].get("resource_id")
            if node_id:
                node["id"] = node_id

        if node_id is not None and str(node_id).strip() not in ("", "none", "null"):
            # Valid node — assign parentNode if needed and add to flat list
            if parent_id and not node.get("parentNode"):
                node["parentNode"] = parent_id
            flat.append(node)
            # Recurse into children using this node's ID as parent
            if children and isinstance(children, list):
                flat.extend(flatten_nested_nodes(children, parent_id=str(node_id)))
        else:
            # No ID — this is an anonymous wrapper (e.g. the topology root).
            # Don't add it to flat list, but DO recurse into its children.
            if children and isinstance(children, list):
                flat.extend(flatten_nested_nodes(children, parent_id=parent_id))
    return flat


def ensure_container_nodes(nodes: List[Dict[str, Any]], provider: str, requirements: Any) -> List[Dict[str, Any]]:
    node_ids = {str(n.get("id")).lower() for n in nodes if n.get("id")}
    
    compute_type = "AKS"
    if requirements:
        compute_type = getattr(requirements, "computeType", None) or getattr(requirements, "application_type", None) or "AKS"
    
    containers = [
        {
            "id": "region-group",
            "type": "RegionGroupNode",
            "parentNode": None,
            "position": {"x": 0.0, "y": 0.0},
            "style": {"width": 2900.0, "height": 2280.0},
            "data": {"label": f"Cloud Region: {requirements.region.upper() if requirements.region else 'EAST US'}", "provider": provider, "resource_type": "region"}
        },
        {
            "id": "rg-group",
            "type": "ResourceGroupNode",
            "parentNode": "region-group",
            "position": {"x": 30.0, "y": 45.0},
            "style": {"width": 2840.0, "height": 2190.0},
            "data": {"label": f"Resource Scope: {requirements.resourceGroup or 'rg-production'}", "provider": provider, "resource_type": "resourcegroup"}
        },
        {
            "id": "vnet-group",
            "type": "VNetGroupNode",
            "parentNode": "rg-group",
            "position": {"x": 30.0, "y": 45.0},
            "style": {"width": 2780.0, "height": 2100.0},
            "data": {"label": f"Virtual Network (VPC): {requirements.vnetCIDR or '10.0.0.0/16'}", "provider": provider, "resource_type": "vnet"}
        },
        {
            "id": "subnet-ingress",
            "type": "SubnetGroupNode",
            "parentNode": "vnet-group",
            "position": {"x": 40.0, "y": 60.0},
            "style": {"width": 2180.0, "height": 280.0},
            "data": {"label": "Ingress Subnet (10.0.1.0/24)", "subnet": "subnet-ingress", "provider": provider, "resource_type": "subnet"}
        },
        {
            "id": "subnet-mgmt",
            "type": "SubnetGroupNode",
            "parentNode": "vnet-group",
            "position": {"x": 40.0, "y": 380.0},
            "style": {"width": 2180.0, "height": 280.0},
            "data": {"label": "Management Subnet (10.0.4.0/24)", "subnet": "subnet-mgmt", "provider": provider, "resource_type": "subnet"}
        },
        {
            "id": "subnet-pe",
            "type": "SubnetGroupNode",
            "parentNode": "vnet-group",
            "position": {"x": 40.0, "y": 1620.0},
            "style": {"width": 2180.0, "height": 420.0},
            "data": {"label": "Private Endpoint Subnet (10.0.5.0/24)", "subnet": "subnet-pe", "provider": provider, "resource_type": "subnet"}
        },
        {
            "id": "subnet-app",
            "type": "SubnetGroupNode",
            "parentNode": "vnet-group",
            "position": {"x": 40.0, "y": 700.0},
            "style": {"width": 2180.0, "height": 420.0},
            "data": {"label": "Application Subnet (10.0.2.0/24)", "subnet": "subnet-app", "provider": provider, "resource_type": "subnet"}
        },
        {
            "id": "subnet-data",
            "type": "SubnetGroupNode",
            "parentNode": "vnet-group",
            "position": {"x": 40.0, "y": 1160.0},
            "style": {"width": 2180.0, "height": 420.0},
            "data": {"label": "Data Subnet (10.0.3.0/24)", "subnet": "subnet-data", "provider": provider, "resource_type": "subnet"}
        },
        {
            "id": "shared-services-group",
            "type": "SubnetGroupNode",
            "parentNode": "vnet-group",
            "position": {"x": 2200.0, "y": 60.0},
            "style": {"width": 500.0, "height": 1200.0},
            "data": {"label": "Shared Services Group", "provider": provider, "resource_type": "subnet"}
        }
    ]

    if str(compute_type).upper() == "AKS":
        containers.append({
            "id": "aks-cluster-group",
            "type": "SubnetGroupNode",
            "parentNode": "subnet-app",
            "position": {"x": 350.0, "y": 40.0},
            "style": {"width": 1780.0, "height": 340.0},
            "data": {"label": "AKS Cluster Group", "provider": provider, "resource_type": "subnet"}
        })

    container_parent_map = {
        "region-group": None,
        "rg-group": "region-group",
        "vnet-group": "rg-group",
        "subnet-ingress": "vnet-group",
        "subnet-mgmt": "vnet-group",
        "subnet-pe": "vnet-group",
        "subnet-app": "vnet-group",
        "subnet-data": "vnet-group",
        "shared-services-group": "vnet-group",
        "aks-cluster-group": "subnet-app"
    }

    nodes_map = {str(n.get("id")).lower(): n for n in nodes if n.get("id")}
    injected = list(nodes)

    for container in containers:
        c_id = container["id"]
        c_id_lower = c_id.lower()
        if c_id_lower not in node_ids:
            injected.insert(0, container)
            nodes_map[c_id_lower] = container
        else:
            existing_node = nodes_map[c_id_lower]
            existing_node["parentNode"] = container_parent_map[c_id]
            existing_node["position"] = container["position"]
            existing_node["style"] = container["style"]

    # Inject missing compute node if not present
    compute_type_lower = str(compute_type).lower()
    if "app service" in compute_type_lower or "web app" in compute_type_lower:
        target_compute_id = "app-service-plan"
        target_node = {
            "id": "app-service-plan",
            "type": "BackendNode",
            "parentNode": "subnet-app",
            "position": {"x": 100.0, "y": 60.0},
            "style": {"width": 100.0, "height": 50.0},
            "data": {
                "label": "App Service Plan",
                "typeSubText": "azurerm_service_plan",
                "subnet": "subnet-app",
                "provider": provider,
                "cost": "$75/month",
                "monthly_cost": "$75/month",
                "estimated_monthly_cost": 75.0,
                "public": False,
                "private": True,
                "resource_type": "azurerm_service_plan",
                "terraform_resource": "azurerm_service_plan"
            }
        }
    elif "container app" in compute_type_lower:
        target_compute_id = "container-app-env"
        target_node = {
            "id": "container-app-env",
            "type": "BackendNode",
            "parentNode": "subnet-app",
            "position": {"x": 100.0, "y": 60.0},
            "style": {"width": 100.0, "height": 50.0},
            "data": {
                "label": "Container Apps Environment",
                "typeSubText": "azurerm_container_app_environment",
                "subnet": "subnet-app",
                "provider": provider,
                "cost": "$50/month",
                "monthly_cost": "$50/month",
                "estimated_monthly_cost": 50.0,
                "public": False,
                "private": True,
                "resource_type": "azurerm_container_app_environment",
                "terraform_resource": "azurerm_container_app_environment"
            }
        }
    else:
        target_compute_id = "aks-cluster"
        target_node = {
            "id": "aks-cluster",
            "type": "BackendNode",
            "parentNode": "aks-cluster-group",
            "position": {"x": 10.0, "y": 20.0},
            "style": {"width": 100.0, "height": 50.0},
            "data": {
                "label": "AKS Cluster",
                "typeSubText": "azurerm_kubernetes_cluster",
                "subnet": "aks-cluster-group",
                "provider": provider,
                "cost": "$250/month",
                "monthly_cost": "$250/month",
                "estimated_monthly_cost": 250.0,
                "public": False,
                "private": True,
                "resource_type": "azurerm_kubernetes_cluster",
                "terraform_resource": "azurerm_kubernetes_cluster"
            }
        }

    if target_compute_id.lower() not in {str(n.get("id")).lower() for n in injected if n.get("id")}:
        injected.append(target_node)
        
    return injected


def post_process_nodes(nodes: List[Dict[str, Any]], provider: str, requirements: Any, edges: List[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    # Post-process live/enhanced/deterministic topology to enforce user's custom inputs
    try:
        # Align microservice node IDs to start with 'svc-'
        if edges is not None:
            PROTECTED_COMPUTE_IDS = {
                "aks-cluster", "aks-cluster-group", "aks-system-node-pool", "aks-user-node-pool", "aks-ingress-controller", "aks-hpa", 
                "app-service-plan", "container-app-env", "container-app-env-group"
            }
            id_mapping = {}
            for n in nodes:
                n_id = str(n.get("id", ""))
                n_id_lower = n_id.lower()
                matched_prefix = None
                for prefix in ["container-app-", "app-service-", "web-app-", "aks-"]:
                    if n_id_lower.startswith(prefix):
                        matched_prefix = prefix
                        break
                if matched_prefix and n_id_lower not in PROTECTED_COMPUTE_IDS and n.get("type") in ["BackendNode", "FrontendNode"]:
                    new_id = "svc-" + n_id[len(matched_prefix):]
                    id_mapping[n_id] = new_id
                    n["id"] = new_id
                    if "data" in n and isinstance(n["data"], dict):
                        n["data"]["resource_id"] = new_id
            if id_mapping:
                id_mapping_lower = {k.lower(): v for k, v in id_mapping.items()}
                for e in edges:
                    src = e.get("source")
                    tgt = e.get("target")
                    src_lower = str(src).lower() if src else ""
                    tgt_lower = str(tgt).lower() if tgt else ""
                    if src_lower in id_mapping_lower:
                        e["source"] = id_mapping_lower[src_lower]
                    if tgt_lower in id_mapping_lower:
                        e["target"] = id_mapping_lower[tgt_lower]
                    new_src = e.get("source")
                    new_tgt = e.get("target")
                    e["id"] = f"e-{new_src}-{new_tgt}"

        compute_type = "AKS"
        if requirements:
            compute_type = getattr(requirements, "computeType", None) or getattr(requirements, "application_type", None) or "AKS"
        compute_upper = str(compute_type).upper().replace("_", " ").replace("-", " ")

        # Filter out forbidden nodes based on locked compute platform
        AKS_FORBIDDEN = {"app-service-plan", "web-app", "container-app-env", "container-app-env-group"}
        APPSERVICE_FORBIDDEN = {"aks-cluster", "aks-cluster-group", "aks-system-node-pool", "aks-user-node-pool", "aks-ingress-controller", "aks-hpa", "container-app-env"}
        CONTAINERAPPS_FORBIDDEN = {"aks-cluster", "aks-cluster-group", "aks-system-node-pool", "aks-user-node-pool", "aks-ingress-controller", "aks-hpa", "app-service-plan", "web-app"}

        forbidden_nodes = set()
        if "AKS" in compute_upper or "KUBERNETES" in compute_upper:
            forbidden_nodes = AKS_FORBIDDEN
        elif "APP SERVICE" in compute_upper or "WEB APP" in compute_upper:
            forbidden_nodes = APPSERVICE_FORBIDDEN
        else:
            forbidden_nodes = CONTAINERAPPS_FORBIDDEN

        nodes = [n for n in nodes if str(n.get("id", "")).lower() not in forbidden_nodes]

        # -----------------------------------------------------------------------
        # Canonical Subnet Enforcement
        # Strip any AI-invented non-canonical SubnetGroupNodes and remap resources.
        # -----------------------------------------------------------------------
        CANONICAL_SUBNETS = {
            "subnet-ingress", "subnet-app", "subnet-data",
            "subnet-mgmt", "subnet-pe", "shared-services-group",
            # Container-group subnets managed by ensure_container_nodes
            "aks-cluster-group",
            # Top-level container groups
            "region-group", "rg-group", "vnet-group",
        }

        def _canonical_subnet_for_node(node: Dict[str, Any]) -> str:
            """Return the correct canonical subnet for a resource node."""
            nid_l = str(node.get("id", "")).lower()
            lbl_l = str(node.get("data", {}).get("label", "")).lower()
            ntype = str(node.get("type", ""))
            if any(x in nid_l or x in lbl_l for x in ["keyvault", "vault", "log-analytics", "log analytics",
                                                        "app-insights", "app insights", "azure-monitor", "monitor",
                                                        "backup-vault", "recovery-vault", "acr", "cost-management"]):
                return "shared-services-group"
            if any(x in nid_l or x in lbl_l for x in ["pe-", "private endpoint", "private-endpoint"]):
                return "subnet-pe"
            if ntype in ["DatabaseNode", "CacheNode", "StorageNode"] or \
               any(x in nid_l or x in lbl_l for x in ["db-", "database", "postgresql", "postgres", "mysql",
                                                        "cosmos", "redis", "cache", "storage", "blob", "bucket"]):
                return "subnet-data"
            if any(x in nid_l or x in lbl_l for x in ["gateway", "app-gateway", "appgw", "waf", "firewall",
                                                        "front-door", "frontdoor", "loadbalancer", "load-balancer"]):
                return "subnet-ingress"
            if any(x in nid_l or x in lbl_l for x in ["bastion", "jumpbox", "managed-identity", "role-assignment"]):
                return "subnet-mgmt"
            # Compute / microservices → subnet-app (or aks-cluster-group handled later)
            return "subnet-app"

        # Collect all custom (non-canonical) subnet IDs from AI output
        custom_subnet_ids = set()
        for n in nodes:
            if str(n.get("type", "")) == "SubnetGroupNode":
                nid_l = str(n.get("id", "")).lower()
                if nid_l not in CANONICAL_SUBNETS:
                    custom_subnet_ids.add(nid_l)

        if custom_subnet_ids:
            logger.info(f"Stripping non-canonical subnet nodes: {custom_subnet_ids}")
            # Remap children of custom subnets to their canonical equivalent
            for n in nodes:
                parent_l = str(n.get("parentNode", "")).lower()
                if parent_l in custom_subnet_ids:
                    canonical = _canonical_subnet_for_node(n)
                    n["parentNode"] = canonical
                    if "data" in n and isinstance(n["data"], dict):
                        n["data"]["subnet"] = canonical
            # Remove the custom subnet nodes entirely (ensure_container_nodes injects canonical ones)
            nodes = [n for n in nodes if str(n.get("id", "")).lower() not in custom_subnet_ids]

        # Also fix any resource node that still points to a non-canonical parentNode
        for n in nodes:
            parent_l = str(n.get("parentNode", "")).lower()
            if parent_l and parent_l not in CANONICAL_SUBNETS and \
               str(n.get("type", "")) not in {"RegionGroupNode", "ResourceGroupNode", "VNetGroupNode", "SubnetGroupNode"}:
                canonical = _canonical_subnet_for_node(n)
                n["parentNode"] = canonical
                if "data" in n and isinstance(n["data"], dict):
                    n["data"]["subnet"] = canonical
        # -----------------------------------------------------------------------

        vnet_cidr_val = requirements.vnetCIDR or "10.0.0.0/16"
        ip_prefix = "10.0"
        match_cidr = re.match(r"^(\d+\.\d+)", vnet_cidr_val)
        if match_cidr:
            ip_prefix = match_cidr.group(1)

        reasoning_engine = InfrastructureReasoningEngine(cloud_provider=provider, requirements=requirements)
        compute_name = reasoning_engine.get_cloud_resource_name(requirements.computeType or "AKS")
        db_name = reasoning_engine.get_cloud_resource_name(requirements.database_type or "PostgreSQL")

        # Determine specific terraform resource names based on selected database and compute
        prov_lower = provider.lower()
        db_type_lower = (requirements.database_type or "").lower()
        if prov_lower == "azure":
            db_tf_resource = "azurerm_postgresql_flexible_server"
            if "cosmos" in db_type_lower:
                db_tf_resource = "azurerm_cosmosdb_account"
            elif "mysql" in db_type_lower:
                db_tf_resource = "azurerm_mysql_flexible_server"
            elif "mongo" in db_type_lower:
                db_tf_resource = "mongodbatlas_cluster"
        elif prov_lower == "aws":
            db_tf_resource = "aws_db_instance"
            if "cosmos" in db_type_lower:
                db_tf_resource = "aws_dynamodb_table"
        else: # GCP
            db_tf_resource = "google_sql_database_instance"
            if "cosmos" in db_type_lower:
                db_tf_resource = "google_firestore_db"

        compute_type_lower = (requirements.computeType or "").lower()
        if prov_lower == "azure":
            compute_tf_resource = "azurerm_kubernetes_cluster"
            if "app service" in compute_type_lower or "web app" in compute_type_lower:
                compute_tf_resource = "azurerm_linux_web_app"
            elif "container app" in compute_type_lower:
                compute_tf_resource = "azurerm_container_app"
        elif prov_lower == "aws":
            compute_tf_resource = "aws_eks_cluster"
            if "app service" in compute_type_lower or "web app" in compute_type_lower:
                compute_tf_resource = "aws_elastic_beanstalk_environment"
            elif "container app" in compute_type_lower:
                compute_tf_resource = "aws_ecs_service"
        else: # GCP
            compute_tf_resource = "google_container_cluster"
            if "app service" in compute_type_lower or "web app" in compute_type_lower:
                compute_tf_resource = "google_app_engine_standard_app_version"
            elif "container app" in compute_type_lower:
                compute_tf_resource = "google_cloud_run_service"

        for node in nodes:
            n_id = str(node.get("id", "")).lower()
            n_type = str(node.get("type", ""))
            
            # Fallback type mapping for unregistered node types (blank rectangles fix)
            ALLOWED_TYPES = {
                "GatewayNode", "FrontendNode", "BackendNode", "DatabaseNode", "CacheNode", 
                "StorageNode", "SecurityNode", "MonitoringNode", "RegionGroupNode", 
                "ResourceGroupNode", "VNetGroupNode", "SubnetGroupNode"
            }
            if n_type not in ALLOWED_TYPES:
                lbl_lower = str(node.get("data", {}).get("label", "")).lower()
                mapped_type = "BackendNode"
                if "pe-" in n_id or "private endpoint" in lbl_lower or "private-endpoint" in lbl_lower:
                    mapped_type = "SecurityNode"
                elif "backup" in n_id or "backup" in lbl_lower:
                    mapped_type = "StorageNode"
                elif "recovery" in n_id or "recovery" in lbl_lower:
                    mapped_type = "SecurityNode"
                elif any(x in n_id or x in lbl_lower for x in ["vault", "keyvault", "identity", "role", "waf", "ddos"]):
                    mapped_type = "SecurityNode"
                elif any(x in n_id or x in lbl_lower for x in ["db-", "database", "postgres", "mysql", "sql", "cosmos"]):
                    mapped_type = "DatabaseNode"
                elif any(x in n_id or x in lbl_lower for x in ["redis", "cache"]):
                    mapped_type = "CacheNode"
                elif any(x in n_id or x in lbl_lower for x in ["storage", "blob", "bucket"]):
                    mapped_type = "StorageNode"
                elif any(x in n_id or x in lbl_lower for x in ["log-analytics", "insights", "monitor", "alert", "diagnostic"]):
                    mapped_type = "MonitoringNode"
                elif any(x in n_id or x in lbl_lower for x in ["gateway", "firewall", "ingress", "loadbalancer", "lb"]):
                    mapped_type = "GatewayNode"
                elif any(x in n_id or x in lbl_lower for x in ["frontend", "web", "spa"]):
                    mapped_type = "FrontendNode"
                
                node["type"] = mapped_type
                n_type = mapped_type

            # Enforce Route Tables, NSGs, WAF policies, and Firewalls to be SecurityNode to prevent them from rendering as GatewayNode (Application Gateways)
            lbl_lower = str(node.get("data", {}).get("label", "")).lower()
            if "rt-" in n_id or "route table" in lbl_lower or "route-table" in lbl_lower:
                node["type"] = "SecurityNode"
                n_type = "SecurityNode"
                node["data"] = node.get("data") or {}
                if prov_lower == "azure":
                    node["data"]["terraform_resource"] = "azurerm_route_table"
                    node["data"]["typeSubText"] = "azurerm_route_table"
                elif prov_lower == "aws":
                    node["data"]["terraform_resource"] = "aws_route_table"
                    node["data"]["typeSubText"] = "aws_route_table"
                else:
                    node["data"]["terraform_resource"] = "google_compute_route"
                    node["data"]["typeSubText"] = "google_compute_route"
            elif "nsg" in n_id or "nsg" in lbl_lower or "security group" in lbl_lower or "security-group" in lbl_lower:
                node["type"] = "SecurityNode"
                n_type = "SecurityNode"
                node["data"] = node.get("data") or {}
                if prov_lower == "azure":
                    node["data"]["terraform_resource"] = "azurerm_network_security_group"
                    node["data"]["typeSubText"] = "azurerm_network_security_group"
                elif prov_lower == "aws":
                    node["data"]["terraform_resource"] = "aws_security_group"
                    node["data"]["typeSubText"] = "aws_security_group"
                else:
                    node["data"]["terraform_resource"] = "google_compute_firewall"
                    node["data"]["typeSubText"] = "google_compute_firewall"
            elif "waf" in n_id or "waf" in lbl_lower:
                node["type"] = "SecurityNode"
                n_type = "SecurityNode"
                node["data"] = node.get("data") or {}
                if prov_lower == "azure":
                    node["data"]["terraform_resource"] = "azurerm_web_application_firewall_policy"
                    node["data"]["typeSubText"] = "azurerm_web_application_firewall_policy"
                elif prov_lower == "aws":
                    node["data"]["terraform_resource"] = "aws_wafv2_web_acl"
                    node["data"]["typeSubText"] = "aws_wafv2_web_acl"
                else:
                    node["data"]["terraform_resource"] = "google_compute_security_policy"
                    node["data"]["typeSubText"] = "google_compute_security_policy"
            elif "firewall" in n_id or "firewall" in lbl_lower:
                node["type"] = "SecurityNode"
                n_type = "SecurityNode"
                node["data"] = node.get("data") or {}
                if prov_lower == "azure":
                    node["data"]["terraform_resource"] = "azurerm_firewall"
                    node["data"]["typeSubText"] = "azurerm_firewall"
                elif prov_lower == "aws":
                    node["data"]["terraform_resource"] = "aws_networkfirewall_firewall"
                    node["data"]["typeSubText"] = "aws_networkfirewall_firewall"
                else:
                    node["data"]["terraform_resource"] = "google_compute_firewall"
                    node["data"]["typeSubText"] = "google_compute_firewall"

            # A. Update Region Node Label
            if n_type == "RegionGroupNode" or "region" in n_id:
                node["data"] = node.get("data") or {}
                node["data"]["label"] = f"Cloud Region: {requirements.region.upper() if requirements.region else 'EAST US'}"
                
            # B. Update Resource Group Node Label
            elif n_type == "ResourceGroupNode" or "rg-" in n_id or n_id == "rg-group":
                node["data"] = node.get("data") or {}
                node["data"]["label"] = f"Resource Scope: {requirements.resourceGroup or 'rg-production'}"
                
            # C. Update Virtual Network Node Label
            elif n_type == "VNetGroupNode" or "vnet" in n_id or "vpc" in n_id:
                node["data"] = node.get("data") or {}
                node["data"]["label"] = f"Virtual Network (VPC): {vnet_cidr_val}"
                
            # D. Update Subnet Node Labels
            elif n_type == "SubnetGroupNode" or "subnet" in n_id:
                node["data"] = node.get("data") or {}
                lbl = str(node["data"].get("label", "")).lower()
                if "ingress" in n_id or "ingress" in lbl:
                    node["data"]["label"] = f"Ingress Subnet ({ip_prefix}.1.0/24)"
                elif "mgmt" in n_id or "mgmt" in lbl or "management" in lbl:
                    node["data"]["label"] = f"Management Subnet ({ip_prefix}.4.0/24)"
                elif "pe" in n_id or "pe" in lbl or "private endpoint" in lbl or "private-endpoint" in lbl:
                    node["data"]["label"] = f"Private Endpoint Subnet ({ip_prefix}.5.0/24)"
                elif "app" in n_id or "app" in lbl or "application" in lbl:
                    node["data"]["label"] = f"Application Subnet ({ip_prefix}.2.0/24)"
                elif "data" in n_id or "data" in lbl or "database" in lbl:
                    node["data"]["label"] = f"Data Subnet ({ip_prefix}.3.0/24)"
                    
            # E. Update Compute engine Node Label
            elif n_id in ["aks-cluster", "container-app-env", "app-service-plan", "compute", "cluster"] or (n_type == "BackendNode" and ("cluster" in n_id or "container-app-env" in n_id or "app-service-plan" in n_id) and not any(x in n_id for x in ["pool", "ingress", "controller", "system", "user", "svc-"])):
                node["data"] = node.get("data") or {}
                node["data"]["label"] = f"{compute_name} Engine"
                node["data"]["terraform_resource"] = compute_tf_resource
                node["data"]["typeSubText"] = compute_tf_resource
                node["data"]["resource_type"] = "compute"
                
            # F. Update Primary/Replica DB Node Labels
            elif n_id == "db-primary" or n_id == "database" or (n_type == "DatabaseNode" and "replica" not in n_id):
                node["data"] = node.get("data") or {}
                node["data"]["label"] = db_name
                node["data"]["terraform_resource"] = db_tf_resource
                node["data"]["typeSubText"] = db_tf_resource
                node["data"]["resource_type"] = "database"
                
            # G. Update DB Replica Node Label
            elif n_id == "db-replica" or (n_type == "DatabaseNode" and "replica" in n_id):
                node["data"] = node.get("data") or {}
                node["data"]["label"] = f"{db_name} Replica"
                node["data"]["terraform_resource"] = db_tf_resource
                node["data"]["typeSubText"] = db_tf_resource
                node["data"]["resource_type"] = "database"
    except Exception as pe:
        logger.warning(f"Failed to post-process node labels: {pe}")
        
    # Ensure position, style, and data dictionary structures exist to prevent frontend crash
    container_defaults = {
        "region-group": {"x": 0.0, "y": 0.0},
        "rg-group": {"x": 30.0, "y": 45.0},
        "vnet-group": {"x": 30.0, "y": 45.0},
        "subnet-ingress": {"x": 40.0, "y": 60.0},
        "subnet-mgmt": {"x": 40.0, "y": 380.0},
        "subnet-app": {"x": 40.0, "y": 700.0},
        "subnet-data": {"x": 40.0, "y": 1160.0},
        "subnet-pe": {"x": 40.0, "y": 1620.0},
        "shared-services-group": {"x": 2200.0, "y": 60.0},
        "aks-cluster-group": {"x": 350.0, "y": 40.0}
    }

    compute_type = "AKS"
    if requirements:
        compute_type = getattr(requirements, "computeType", None) or getattr(requirements, "application_type", None) or "AKS"

    for idx, node in enumerate(nodes):
        node['data'] = node.get('data') or {}
        n_id = str(node.get("id", ""))
        n_id_lower = n_id.lower()
        lbl_lower = str(node['data'].get("label", "")).lower()
        n_type = str(node.get("type", ""))

        if 'position' not in node or not isinstance(node['position'], dict):
            node['position'] = {'x': float((idx % 5) * 200), 'y': float((idx // 5) * 150)}

        # Coordinate healing for container groups themselves
        if n_id_lower in container_defaults:
            pos = node.get("position", {})
            try:
                x_val = float(pos.get("x", 0) if pos.get("x") is not None else 0)
                y_val = float(pos.get("y", 0) if pos.get("y") is not None else 0)
            except (ValueError, TypeError):
                x_val, y_val = 0.0, 0.0
            
            default_pos = container_defaults[n_id_lower]
            if abs(x_val - default_pos["x"]) > 500 or abs(y_val - default_pos["y"]) > 500:
                node["position"] = dict(default_pos)
            continue

        # Force snap parentNode based on resource type / category
        is_shared = (
            "keyvault" in n_id_lower or "vault" in n_id_lower or
            "log-analytics" in n_id_lower or "log analytics" in lbl_lower or
            "app-insights" in n_id_lower or "app insights" in lbl_lower or
            "azure-monitor" in n_id_lower or "azure monitor" in lbl_lower or
            "backup-vault" in n_id_lower or "backup vault" in lbl_lower or
            "recovery-vault" in n_id_lower or "recovery services vault" in lbl_lower or
            "alerts" in n_id_lower or "alert" in lbl_lower or
            "diagnostic" in n_id_lower or "diagnostic" in lbl_lower or
            "acr" in n_id_lower or "acr" in lbl_lower or
            "cost-management" in n_id_lower or "cost management" in lbl_lower
        ) and not any(x in n_id_lower or x in lbl_lower for x in ["pe-", "private endpoint", "private-endpoint", "backup-policy"])

        is_pe = ("pe-" in n_id_lower or "private endpoint" in lbl_lower or "private-endpoint" in lbl_lower) and n_type != "SubnetGroupNode"
        
        is_storage_resource = (
            n_type in ["DatabaseNode", "CacheNode", "StorageNode"] or
            any(db_kw in n_id_lower or db_kw in lbl_lower for db_kw in ["db-", "database", "postgresql", "mysql", "redis", "storage-account", "blob", "replica"])
        ) and not is_pe and n_id_lower not in ["backup-vault", "recovery-vault"]

        is_ingress_resource = any(x in n_id_lower or x in lbl_lower for x in ["app-gateway", "appgw", "azure-firewall", "firewall", "front-door", "frontdoor", "waf-policy", "waf"]) and not is_pe and not is_shared

        is_compute_resource = any(x in n_id_lower for x in ["svc-", "aks-", "cluster", "pool", "ingress-controller"])

        is_mgmt_resource = any(x in n_id_lower or x in lbl_lower for x in ["bastion", "jumpbox", "managed-identity", "role-assignment", "firewall-policy"]) and not is_shared

        if is_shared:
            node["parentNode"] = "shared-services-group"
        elif is_pe:
            node["parentNode"] = "subnet-pe"
        elif is_storage_resource:
            node["parentNode"] = "subnet-data"
        elif is_ingress_resource:
            node["parentNode"] = "subnet-ingress"
        elif is_compute_resource:
            if str(compute_type).upper() == "AKS":
                node["parentNode"] = "aks-cluster-group"
            else:
                node["parentNode"] = "subnet-app"
        elif is_mgmt_resource:
            node["parentNode"] = "subnet-mgmt"

        # Apply specific coordinate mappings relative to parents to avoid overlaps
        parent = node.get("parentNode")
        node["data"]["subnet"] = parent or ""

        if parent == "aks-cluster-group":
            aks_positions = {
                "aks-cluster": {"x": 10.0, "y": 20.0},
                "aks-system-node-pool": {"x": 10.0, "y": 120.0},
                "aks-system": {"x": 10.0, "y": 120.0},
                "aks-user-node-pool": {"x": 10.0, "y": 220.0},
                "aks-user": {"x": 10.0, "y": 220.0},
                "aks-ingress-controller": {"x": 300.0, "y": 20.0},
                "svc-api-gateway": {"x": 300.0, "y": 120.0},
                "aks-hpa": {"x": 300.0, "y": 220.0},
                "svc-auth": {"x": 590.0, "y": 20.0},
                "svc-product": {"x": 590.0, "y": 120.0},
                "svc-order": {"x": 880.0, "y": 20.0},
                "svc-payment": {"x": 880.0, "y": 120.0},
                "svc-inventory": {"x": 1170.0, "y": 20.0},
                "svc-notification": {"x": 1170.0, "y": 120.0},
            }
            pos_assigned = False
            for kw, default_pos in aks_positions.items():
                if kw in n_id_lower:
                    node["position"] = dict(default_pos)
                    pos_assigned = True
                    break
            if not pos_assigned:
                node["position"] = {"x": 1460.0, "y": float(20 + (idx % 3) * 100)}

        elif parent == "shared-services-group":
            y_map = {
                "keyvault": 60.0,
                "log-analytics": 160.0,
                "app-insights": 260.0,
                "azure-monitor": 360.0,
                "alerts": 460.0,
                "diagnostic-settings": 560.0,
                "backup-vault": 660.0,
                "recovery-vault": 760.0,
                "acr": 860.0,
                "cost-management": 960.0
            }
            default_y = 60.0
            for kw, y_pos in y_map.items():
                if kw in n_id_lower or kw in lbl_lower:
                    default_y = y_pos
                    break
            node["position"] = {"x": 50.0, "y": default_y}

        elif parent and parent.startswith("subnet-"):
            pos = node.get("position", {})
            try:
                x_val = float(pos.get("x", 0) if pos.get("x") is not None else 0)
                y_val = float(pos.get("y", 0) if pos.get("y") is not None else 0)
            except (ValueError, TypeError):
                x_val, y_val = 0.0, 0.0
            
            if x_val < 0 or x_val > 1800 or y_val < 0 or y_val > 600:
                node["position"] = {"x": float(30 + (idx % 4) * 250), "y": float(60 + (idx // 4) * 110)}

        # Metadata Normalization: strip customMetadata from infrastructure nodes
        is_infra = False
        if (
            "nsg" in n_id_lower or "nsg" in lbl_lower or 
            "rt-" in n_id_lower or "-rt" in n_id_lower or "route table" in lbl_lower or "route-table" in lbl_lower or
            "keyvault" in n_id_lower or "vault" in n_id_lower or
            "pe-" in n_id_lower or "private endpoint" in lbl_lower or "private-endpoint" in lbl_lower or
            "role-assignment" in n_id_lower or "role assignment" in lbl_lower or
            n_type in ["SecurityNode", "MonitoringNode"]
        ):
            is_infra = True

        if is_infra and "customMetadata" in node['data']:
            node['data'].pop("customMetadata", None)

        if 'style' not in node or not isinstance(node['style'], dict):
            node['style'] = {}
            
        if 'provider' not in node['data']:
            node['data']['provider'] = provider
        if 'subnet' not in node['data']:
            node['data']['subnet'] = node.get('parentNode', '')
        if 'resource_type' not in node['data']:
            node['data']['resource_type'] = str(node.get('type', 'resource')).lower()
        if 'cost' not in node['data']:
            node['data']['cost'] = "~$25/mo"
        if 'estimated_monthly_cost' not in node['data']:
            node['data']['estimated_monthly_cost'] = 25.0
        if 'public' not in node['data']:
            node['data']['public'] = False
        if 'private' not in node['data']:
            node['data']['private'] = True
        if 'resource_id' not in node['data']:
            node['data']['resource_id'] = node.get('id', '')
        if 'terraform_resource' not in node['data']:
            node['data']['terraform_resource'] = ''
        if 'cost_estimate' not in node['data']:
            node['data']['cost_estimate'] = node['data'].get('cost', '') or ''
            
    # Sanitize parentNode references to prevent frontend crash
    existing_node_ids = {str(n.get("id")).lower() for n in nodes if n.get("id")}
    for node in nodes:
        parent = node.get("parentNode")
        if parent:
            parent_lower = str(parent).lower()
            if parent_lower not in existing_node_ids:
                if parent_lower == "aks-cluster-group":
                    node["parentNode"] = "subnet-app"
                    node["data"]["subnet"] = "subnet-app"
                else:
                    node["parentNode"] = None
                    node["data"]["subnet"] = ""
            
    return nodes


def normalize_and_validate_ai_topology(nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]], provider: str, requirements: Any) -> tuple:
    """
    Non-mutating validation and normalization layer for Pure AI generated topologies.
    Applies node type mapping, edge filtering, and required metadata normalization
    without mutating position (coordinates), parentNode mappings, or container scopes.
    """
    ALLOWED_TYPES = {
        "GatewayNode", "FrontendNode", "BackendNode", "DatabaseNode", "CacheNode", 
        "StorageNode", "SecurityNode", "MonitoringNode", "RegionGroupNode", 
        "ResourceGroupNode", "VNetGroupNode", "SubnetGroupNode"
    }

    # Filter out malformed nodes returned by the AI (no id, no type, non-dict)
    nodes = [n for n in nodes if isinstance(n, dict) and n.get("id") is not None and str(n.get("id", "")).strip() != ""]

    prov_lower = provider.lower()
    node_ids = {str(n.get("id")) for n in nodes if n.get("id")}
    
    # Extract VNet CIDR to align subnets
    vnet_cidr_val = "10.0.0.0/16"
    if requirements:
        vnet_cidr_val = getattr(requirements, "vnetCIDR", None) or getattr(requirements, "vnet_cidr", None) or "10.0.0.0/16"
    
    for n in nodes:
        nid_l = str(n.get("id", "")).lower()
        ntype = str(n.get("type", ""))
        if ntype == "VNetGroupNode" or "vnet" in nid_l or "vpc" in nid_l:
            lbl = str(n.get("data", {}).get("label", ""))
            match_ip = re.search(r"(\d+\.\d+\.\d+\.\d+/\d+)", lbl)
            if match_ip:
                vnet_cidr_val = match_ip.group(1)
                break
                
    ip_prefix = "10.0"
    match_cidr = re.match(r"^(\d+\.\d+)", vnet_cidr_val)
    if match_cidr:
        ip_prefix = match_cidr.group(1)
        
    for idx, node in enumerate(nodes):
        node['data'] = node.get('data') or {}
        n_id = str(node.get("id", ""))
        n_id_lower = n_id.lower()
        lbl_lower = str(node['data'].get("label", "")).lower()
        n_type = str(node.get("type", ""))
        
        # 1. Node Type Normalization
        if n_type not in ALLOWED_TYPES:
            mapped_type = "BackendNode"
            if "pe-" in n_id or "private endpoint" in lbl_lower or "private-endpoint" in lbl_lower:
                mapped_type = "SecurityNode"
            elif "backup" in n_id or "backup" in lbl_lower:
                mapped_type = "StorageNode"
            elif "recovery" in n_id or "recovery" in lbl_lower:
                mapped_type = "SecurityNode"
            elif any(x in n_id or x in lbl_lower for x in ["vault", "keyvault", "identity", "role", "waf", "ddos"]):
                mapped_type = "SecurityNode"
            elif any(x in n_id or x in lbl_lower for x in ["db-", "database", "postgres", "mysql", "sql", "cosmos"]):
                mapped_type = "DatabaseNode"
            elif any(x in n_id or x in lbl_lower for x in ["redis", "cache"]):
                mapped_type = "CacheNode"
            elif any(x in n_id or x in lbl_lower for x in ["storage", "blob", "bucket"]):
                mapped_type = "StorageNode"
            elif any(x in n_id or x in lbl_lower for x in ["log-analytics", "insights", "monitor", "alert", "diagnostic"]):
                mapped_type = "MonitoringNode"
            elif any(x in n_id or x in lbl_lower for x in ["gateway", "firewall", "ingress", "loadbalancer", "lb"]):
                mapped_type = "GatewayNode"
            elif any(x in n_id or x in lbl_lower for x in ["frontend", "web", "spa"]):
                mapped_type = "FrontendNode"
            
            node["type"] = mapped_type
            n_type = mapped_type

        # Align VNet and Subnet CIDR prefixes to guarantee consistency
        if n_type == "VNetGroupNode" or "vnet" in n_id_lower or "vpc" in n_id_lower:
            node["data"] = node.get("data") or {}
            node["data"]["label"] = f"Virtual Network (VPC): {vnet_cidr_val}"
        elif n_type == "SubnetGroupNode" or "subnet" in n_id_lower or "snet" in n_id_lower:
            node["data"] = node.get("data") or {}
            lbl = str(node["data"].get("label", "")).lower()
            if "ingress" in n_id_lower or "ingress" in lbl:
                node["data"]["label"] = f"Ingress Subnet ({ip_prefix}.1.0/24)"
            elif "mgmt" in n_id_lower or "mgmt" in lbl or "management" in lbl:
                node["data"]["label"] = f"Management Subnet ({ip_prefix}.4.0/24)"
            elif "pe" in n_id_lower or "pe" in lbl or "private endpoint" in lbl or "private-endpoint" in lbl:
                node["data"]["label"] = f"Private Endpoint Subnet ({ip_prefix}.5.0/24)"
            elif "app" in n_id_lower or "app" in lbl or "application" in lbl:
                node["data"]["label"] = f"Application Subnet ({ip_prefix}.2.0/24)"
            elif "data" in n_id_lower or "data" in lbl or "database" in lbl:
                node["data"]["label"] = f"Data Subnet ({ip_prefix}.3.0/24)"
            else:
                label = str(node["data"].get("label", ""))
                match_sub_ip = re.search(r"(\d+\.\d+)\.(\d+\.\d+/\d+)", label)
                if match_sub_ip:
                    node["data"]["label"] = label.replace(match_sub_ip.group(1), ip_prefix)

        # Enforce Route Tables, NSGs, WAF policies, and Firewalls to be SecurityNode
        if "rt-" in n_id or "route table" in lbl_lower or "route-table" in lbl_lower:
            node["type"] = "SecurityNode"
            n_type = "SecurityNode"
            node["data"] = node.get("data") or {}
            if prov_lower == "azure":
                node["data"]["terraform_resource"] = "azurerm_route_table"
                node["data"]["typeSubText"] = "azurerm_route_table"
            elif prov_lower == "aws":
                node["data"]["terraform_resource"] = "aws_route_table"
                node["data"]["typeSubText"] = "aws_route_table"
            else:
                node["data"]["terraform_resource"] = "google_compute_route"
                node["data"]["typeSubText"] = "google_compute_route"
        elif "nsg" in n_id or "nsg" in lbl_lower or "security group" in lbl_lower or "security-group" in lbl_lower:
            node["type"] = "SecurityNode"
            n_type = "SecurityNode"
            node["data"] = node.get("data") or {}
            if prov_lower == "azure":
                node["data"]["terraform_resource"] = "azurerm_network_security_group"
                node["data"]["typeSubText"] = "azurerm_network_security_group"
            elif prov_lower == "aws":
                node["data"]["terraform_resource"] = "aws_security_group"
                node["data"]["typeSubText"] = "aws_security_group"
            else:
                node["data"]["terraform_resource"] = "google_compute_firewall"
                node["data"]["typeSubText"] = "google_compute_firewall"
        elif "waf" in n_id or "waf" in lbl_lower:
            node["type"] = "SecurityNode"
            n_type = "SecurityNode"
            node["data"] = node.get("data") or {}
            if prov_lower == "azure":
                node["data"]["terraform_resource"] = "azurerm_web_application_firewall_policy"
                node["data"]["typeSubText"] = "azurerm_web_application_firewall_policy"
            elif prov_lower == "aws":
                node["data"]["terraform_resource"] = "aws_wafv2_web_acl"
                node["data"]["typeSubText"] = "aws_wafv2_web_acl"
            else:
                node["data"]["terraform_resource"] = "google_compute_security_policy"
                node["data"]["typeSubText"] = "google_compute_security_policy"
        elif "firewall" in n_id or "firewall" in lbl_lower:
            node["type"] = "SecurityNode"
            n_type = "SecurityNode"
            node["data"] = node.get("data") or {}
            if prov_lower == "azure":
                node["data"]["terraform_resource"] = "azurerm_firewall"
                node["data"]["typeSubText"] = "azurerm_firewall"
            elif prov_lower == "aws":
                node["data"]["terraform_resource"] = "aws_networkfirewall_firewall"
                node["data"]["typeSubText"] = "aws_networkfirewall_firewall"
            else:
                node["data"]["terraform_resource"] = "google_compute_firewall"
                node["data"]["typeSubText"] = "google_compute_firewall"

        # 2. Metadata Normalization
        # Strip customMetadata from infrastructure nodes
        is_infra = False
        if (
            "nsg" in n_id_lower or "nsg" in lbl_lower or 
            "rt-" in n_id_lower or "-rt" in n_id_lower or "route table" in lbl_lower or "route-table" in lbl_lower or
            "keyvault" in n_id_lower or "vault" in n_id_lower or
            "pe-" in n_id_lower or "private endpoint" in lbl_lower or "private-endpoint" in lbl_lower or
            "role-assignment" in n_id_lower or "role assignment" in lbl_lower or
            n_type in ["SecurityNode", "MonitoringNode"]
        ):
            is_infra = True

        if is_infra and "customMetadata" in node['data']:
            node['data'].pop("customMetadata", None)

        if 'style' not in node or not isinstance(node['style'], dict):
            node['style'] = {}
            
        if 'position' not in node or not isinstance(node['position'], dict):
            node['position'] = {'x': float((idx % 5) * 200), 'y': float((idx // 5) * 150)}
        else:
            node['position']['x'] = float(node['position'].get('x', 0.0))
            node['position']['y'] = float(node['position'].get('y', 0.0))

        # Populate required metadata fields (without changing coordinates or parentNode)
        node['data']['resource_id'] = node['data'].get('resource_id') or node.get('id', '')
        node['data']['resource_type'] = node['data'].get('resource_type') or str(node.get('type', 'resource')).lower()
        if 'terraform_resource' not in node['data']:
            node['data']['terraform_resource'] = ''
        node['data']['provider'] = node['data'].get('provider') or provider
        node['data']['subnet'] = node['data'].get('subnet') or node.get('parentNode', '') or ''
        node['data']['cost_estimate'] = node['data'].get('cost_estimate') or node['data'].get('cost', '') or ''
        
        if 'estimated_monthly_cost' not in node['data']:
            try:
                cost_val = float(re.sub(r'[^\d.]', '', str(node['data'].get('cost_estimate', '25'))))
                node['data']['estimated_monthly_cost'] = cost_val
            except Exception:
                node['data']['estimated_monthly_cost'] = 25.0
        if 'public' not in node['data']:
            node['data']['public'] = False
        if 'private' not in node['data']:
            node['data']['private'] = True

    # 3. Edge Validation (Filter out orphan edges)
    valid_edges = []
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        # Normalize 'from' and 'to' fields if 'source' or 'target' is missing
        if "from" in edge and "source" not in edge:
            edge["source"] = edge["from"]
        if "to" in edge and "target" not in edge:
            edge["target"] = edge["to"]
            
        src = edge.get("source")
        tgt = edge.get("target")
        if src in node_ids and tgt in node_ids:
            if "id" not in edge or not edge.get("id"):
                edge["id"] = f"edge-{src}-{tgt}"
            valid_edges.append(edge)
            
    return nodes, valid_edges


def rebuild_services_registry(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # Map node types to service categories
    category_map = {
        "GatewayNode": "gateway",
        "FrontendNode": "frontend",
        "BackendNode": "backend",
        "DatabaseNode": "database",
        "CacheNode": "cache",
        "StorageNode": "storage",
        "SecurityNode": "security",
        "MonitoringNode": "monitoring",
    }
    services = []
    seen = set()
    for node in nodes:
        n_type = node.get("type")
        if n_type in ["RegionGroupNode", "ResourceGroupNode", "VNetGroupNode", "SubnetGroupNode"]:
            continue
        
        node_id = node.get("id")
        if not node_id:
            continue
            
        label = node.get("data", {}).get("label") or node_id
        service_name = label
        
        if service_name.lower() in seen:
            continue
            
        seen.add(service_name.lower())
        
        category = category_map.get(n_type, "infrastructure")
        description = f"Managed {label} resource deployed in the topology."
        
        services.append({
            "name": service_name,
            "category": category,
            "description": description
        })
    return services


def deduplicate_shared_resources(nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> tuple:
    # Categories and matchers for global env-wide shared resources
    categories = {
        "front-door": lambda nid, lbl: ("frontdoor" in nid or "front-door" in nid or "front door" in lbl or "cdn_frontdoor" in nid or "front_door" in nid) and not any(x in nid or x in lbl for x in ["pe-", "private-endpoint", "private endpoint"]),
        "ddos-protection": lambda nid, lbl: ("ddos" in nid or "ddos" in lbl) and not any(x in nid or x in lbl for x in ["pe-", "private-endpoint", "private endpoint"]),
        "waf-policy": lambda nid, lbl: ("waf" in nid or "waf" in lbl) and not any(x in nid or x in lbl for x in ["pe-", "private-endpoint", "private endpoint"]),
        "app-gateway": lambda nid, lbl: ("app-gateway" in nid or "app gateway" in lbl or "appgw" in nid or "application_gateway" in nid or "application_gateway" in lbl) and not any(x in nid or x in lbl for x in ["pe-", "private-endpoint", "private endpoint"]),
        "azure-firewall": lambda nid, lbl: ("firewall" in nid or "firewall" in lbl) and not any(x in nid or x in lbl for x in ["pe-", "private-endpoint", "private endpoint", "policy"]),
        "keyvault": lambda nid, lbl: ("vault" in nid or "keyvault" in nid or "vault" in lbl or "key vault" in lbl or "key_vault" in nid or "key_vault" in lbl) and not any(x in nid or x in lbl for x in ["backup", "recovery", "pe-kv", "pe-", "private-endpoint", "private endpoint"]),
        "azure-monitor": lambda nid, lbl: ("monitor" in nid or "monitor" in lbl) and not any(x in nid or x in lbl for x in ["log-analytics", "log analytics", "log_analytics", "app-insights", "app insights", "app_insights", "insights", "alerts", "diagnostic", "pe-", "private-endpoint", "private endpoint"]),
        "log-analytics": lambda nid, lbl: ("log-analytics" in nid or "log analytics" in lbl or "loganalytics" in nid or "log_analytics" in nid or "log_analytics" in lbl) and not any(x in nid or x in lbl for x in ["pe-", "private-endpoint", "private endpoint"]),
        "app-insights": lambda nid, lbl: ("app-insights" in nid or "app insights" in lbl or "insights" in nid or "insights" in lbl or "application_insights" in nid or "application_insights" in lbl) and not any(x in nid or x in lbl for x in ["pe-", "private-endpoint", "private endpoint"]),
        "backup-vault": lambda nid, lbl: ("backup-vault" in nid or "backup vault" in lbl or "backup_vault" in nid or "data_protection" in nid) and not any(x in nid or x in lbl for x in ["pe-", "private-endpoint", "private endpoint"]),
        "recovery-vault": lambda nid, lbl: ("recovery-vault" in nid or "recovery services vault" in lbl or "recovery-services-vault" in nid or "recovery_services_vault" in nid) and not any(x in nid or x in lbl for x in ["pe-", "private-endpoint", "private endpoint"]),
        "storage-account": lambda nid, lbl: ("storage-account" in nid or "storage account" in lbl or "blob" in nid or "blob" in lbl or "storage_account" in nid or "storage_account" in lbl) and not any(x in nid or x in lbl for x in ["replica", "pe-", "private-endpoint", "private endpoint", "backup", "container"]),
        "acr": lambda nid, lbl: ("acr" in nid or "container-registry" in nid or "container registry" in lbl or "container_registry" in nid or "container_registry" in lbl) and not any(x in nid or x in lbl for x in ["pe-", "private-endpoint", "private endpoint"]),
        "redis-cache": lambda nid, lbl: ("redis" in nid or "redis" in lbl) and not any(x in nid or x in lbl for x in ["replica", "pe-", "private-endpoint", "private endpoint"]),
        "postgresql": lambda nid, lbl: ("postgresql" in nid or "postgres" in nid or "postgresql" in lbl or "postgres" in lbl) and not any(x in nid or x in lbl for x in ["replica", "pe-", "private-endpoint", "private endpoint"]),
        "container-app": lambda nid, lbl: ("container-app" in nid or "container app" in lbl or "containerapp" in nid or "container_app" in nid or "container_app" in lbl) and not any(x in nid or x in lbl for x in ["pe-", "private-endpoint", "private endpoint", "registry"])
    }
    
    retained_nodes = {}  # category -> node_id
    nodes_to_remove = set()
    node_id_map = {}     # duplicate_node_id -> retained_node_id
    
    # First pass: identify duplicates
    for node in nodes:
        n_type = node.get("type", "")
        if n_type in ["RegionGroupNode", "ResourceGroupNode", "VNetGroupNode", "SubnetGroupNode", "shared-services-group", "aks-cluster-group"]:
            continue
        nid = str(node.get("id", "")).lower()
        lbl = str(node.get("data", {}).get("label", "")).lower()
        
        matched_category = None
        for cat, matcher in categories.items():
            if matcher(nid, lbl):
                matched_category = cat
                break
        
        if matched_category:
            if matched_category in retained_nodes:
                nodes_to_remove.add(node.get("id"))
                node_id_map[node.get("id")] = retained_nodes[matched_category]
            else:
                retained_nodes[matched_category] = node.get("id")
                
    if not nodes_to_remove:
        return nodes, edges
        
    new_nodes = [n for n in nodes if n.get("id") not in nodes_to_remove]
    
    new_edges = []
    seen_edges = set()
    node_id_map_lower = {k.lower(): v for k, v in node_id_map.items()}
    for edge in edges:
        src = edge.get("source")
        tgt = edge.get("target")
        
        src_lower = str(src).lower() if src else ""
        tgt_lower = str(tgt).lower() if tgt else ""
        new_src = node_id_map_lower.get(src_lower, src)
        new_tgt = node_id_map_lower.get(tgt_lower, tgt)
        
        if new_src == new_tgt:
            continue
        edge_key = (str(new_src).lower(), str(new_tgt).lower())
        if edge_key in seen_edges:
            continue
            
        seen_edges.add(edge_key)
        new_edge = dict(edge)
        new_edge["source"] = new_src
        new_edge["target"] = new_tgt
        new_edge["id"] = f"e-{new_src}-{new_tgt}"
        new_edges.append(new_edge)
        
    return new_nodes, new_edges


def _count_real_subnets(nodes: List[Dict[str, Any]]) -> int:
    """Count subnets dynamically based on node type or ID pattern."""
    return len([
        n for n in nodes
        if str(n.get("type", "")) == "SubnetGroupNode" or "subnet" in str(n.get("id", "")).lower() or "snet" in str(n.get("id", "")).lower()
    ])


def validate_and_gate_architecture(nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]], complexity_warnings: List[str] = None, compute_type: str = None, database_type: str = None, provider: str = None, requirements: Any = None) -> List[str]:
    if complexity_warnings is None:
        complexity_warnings = []
    
    validation_findings = []
    consistency_warnings = []
    
    node_ids = {n.get("id") for n in nodes if n.get("id") is not None}
    node_labels = {str(n.get("data", {}).get("label") or "").lower() for n in nodes}
    node_types = {n.get("type") for n in nodes if n.get("type") is not None}
    subnet_count = _count_real_subnets(nodes)
    
    # 1. Quality Gate Checks
    # Validate dynamic subnets exist
    if subnet_count == 0:
        validation_findings.append("Quality Gate: Virtual Network subnets are missing. At least one subnet node (SubnetGroupNode) is required.")

    # Validate VNet exists
    has_vnet = "VNetGroupNode" in node_types or any("vnet" in str(nid).lower() or "vpc" in str(nid).lower() for nid in node_ids)
    if not has_vnet:
        validation_findings.append("Quality Gate: VNet/VPC group node is missing.")

    # Validate Compute platform exists
    has_compute = any(
        n_type in ["BackendNode", "FrontendNode"] or 
        any(x in str(nid).lower() for x in ["cluster", "env", "plan", "aks", "compute"])
        for nid, n_type in zip(node_ids, node_types)
    )
    if not has_compute:
        validation_findings.append("Quality Gate: Compute engine platform node is missing.")

    # 1e. Assess Workload Risk
    def get_req_val(key, default=None):
        if not requirements:
            return default
        if isinstance(requirements, dict):
            return requirements.get(key, default)
        return getattr(requirements, key, default)

    app_desc = str(get_req_val("app_description", "") or get_req_val("appDescription", "")).lower()
    app_type = str(get_req_val("application_type", "") or get_req_val("applicationType", "")).lower()
    workload_profile = str(get_req_val("workload_profile", "")).lower()

    compliance_str = str(get_req_val("security_level", "") or get_req_val("compliance_standards", "")).lower()
    sensitivity_str = str(get_req_val("security_level", "") or get_req_val("data_sensitivity", "")).lower()
    availability_target = str(get_req_val("availability_target", "") or get_req_val("availability_requirements", "")).lower()
    budget_str = str(get_req_val("monthly_budget", "")).lower()
    
    has_pci_or_sensitive = any(c in compliance_str or c in sensitivity_str for c in ["pci", "hipaa", "gdpr", "soc2", "iso27001", "high", "critical"])
    is_enterprise = any(b in budget_str for b in ["enterprise", "unlimited", "5000", "50000"])
    is_mission_critical = any(a in availability_target for a in ["high availability", "mission critical"])
    
    requires_advanced_security = has_pci_or_sensitive or is_enterprise
    requires_backup_dr = is_mission_critical or any(s in sensitivity_str for s in ["high", "critical"])

    # 1f. Extract Required Capabilities
    app_desc = str(get_req_val("app_description", "") or get_req_val("appDescription", "")).lower()
    notes = str(get_req_val("additional_notes", "") or get_req_val("additionalNotes", "")).lower()
    raw_user_text = app_desc + " " + notes

    explicit_caps = set()
    if "upload" in raw_user_text or "file" in raw_user_text or "document" in raw_user_text or "bucket" in raw_user_text or "blob" in raw_user_text or "s3" in raw_user_text:
        explicit_caps.add("object_storage")
    if "cache" in raw_user_text or "redis" in raw_user_text:
        explicit_caps.add("caching")
    if "secret" in raw_user_text or "vault" in raw_user_text or "credential" in raw_user_text:
        explicit_caps.add("secrets_management")
    if "backup" in raw_user_text or "recovery" in raw_user_text or "disaster recovery" in raw_user_text or "dr" in raw_user_text:
        explicit_caps.add("disaster_recovery")
    if "private endpoint" in raw_user_text or "private connect" in raw_user_text or "private link" in raw_user_text:
        explicit_caps.add("secure_connectivity")
    if "nsg" in raw_user_text or "security group" in raw_user_text or "network isolation" in raw_user_text:
        explicit_caps.add("network_isolation")
    if "gpu" in raw_user_text or "cuda" in raw_user_text:
        explicit_caps.add("gpu_compute")
    if "queue" in raw_user_text or "message" in raw_user_text or "eventing" in raw_user_text or "servicebus" in raw_user_text or "pubsub" in raw_user_text or "messaging" in raw_user_text:
        explicit_caps.add("messaging")
    if "cdn" in raw_user_text or "cloudfront" in raw_user_text or "frontdoor" in raw_user_text or "global distribution" in raw_user_text or "global users" in raw_user_text:
        explicit_caps.add("global_distribution")

    capabilities_raw = get_req_val("required_capabilities")
    if isinstance(capabilities_raw, list):
        for c in capabilities_raw:
            explicit_caps.add(str(c).lower().strip())

    required_caps = list(explicit_caps)
    if not required_caps:
        # Heuristically derive capabilities if not explicitly passed
        if "upload" in app_desc or "file" in app_desc or "document" in app_desc or "model storage" in app_desc:
            required_caps.append("object_storage")
        if "caching" in app_desc or "redis" in app_desc or "cache" in app_desc or "100k" in app_desc or "10k" in app_desc:
            required_caps.append("caching")
        if "secret" in app_desc or "vault" in app_desc or "credential" in app_desc or "password" in app_desc or requires_advanced_security:
            required_caps.append("secrets_management")
        if requires_backup_dr or "backup" in app_desc or "recovery" in app_desc:
            required_caps.append("disaster_recovery")
        if requires_advanced_security or "private connect" in app_desc or "private endpoint" in app_desc:
            required_caps.append("secure_connectivity")
        if "ai" in app_desc or "gpu" in app_desc or "inference" in app_desc or "ml" in app_desc:
            required_caps.append("gpu_compute")
        if "notification" in app_desc or "message" in app_desc or "event" in app_desc or "queue" in app_desc:
            required_caps.append("messaging")
        if "global" in app_desc or "cdn" in app_desc or "traffic manager" in app_desc or "cloudfront" in app_desc:
            required_caps.append("global_distribution")

    # 1g. Capability-Based Validation Checks
    node_ids_lower = {str(n.get("id", "")).lower() for n in nodes}
    node_types_lower = {str(n.get("type", "")).lower() for n in nodes}

    has_db_node = any(t == "databasenode" or any(db_kw in nid for db_kw in ["db", "database", "postgres", "mysql", "cosmos", "sql"]) for nid, t in zip(node_ids_lower, node_types_lower))
    has_storage_node = any(t == "storagenode" or any(st_kw in nid for st_kw in ["storage", "blob", "bucket", "s3"]) for nid, t in zip(node_ids_lower, node_types_lower))
    has_cache_node = any(t == "cachenode" or "cache" in nid or "redis" in nid for nid, t in zip(node_ids_lower, node_types_lower))
    has_cdn_node = any("cdn" in nid or "frontdoor" in nid or "front-door" in nid or "cloudfront" in nid for nid in node_ids_lower)
    has_auth_vault = any(str(n.get("type", "")).lower() == "securitynode" and any(k in str(n.get("id", "")).lower() or k in str(n.get("data", {}).get("label", "")).lower() for k in ["vault", "keyvault", "secret", "identity", "auth"]) for n in nodes)
    has_monitoring_node = any(t == "monitoringnode" or any(m_kw in nid for m_kw in ["monitor", "insights", "analytics", "log-analytics"]) for nid, t in zip(node_ids_lower, node_types_lower))
    has_backup = any(any(k in nid for k in ["backup", "recovery", "vault"]) and "key" not in nid for nid in node_ids_lower)
    has_nsgs = any(any(k in nid for k in ["nsg", "security-group", "security_group", "firewall"]) for nid in node_ids_lower)
    has_rt = any(any(k in nid for k in ["rt-", "route-table", "routetable", "route_table"]) for nid in node_ids_lower)
    has_pe = any("pe-" in nid or "pe_" in nid or "private-endpoint" in nid or "privateendpoint" in nid or "private endpoint" in str(n.get("data", {}).get("label", "")).lower() for n in nodes for nid in [str(n.get("id", "")).lower()])
    has_messaging = any(any(m in nid for m in ["queue", "event", "bus", "pubsub", "sns", "sqs", "messaging", "servicebus"]) for nid in node_ids_lower)
    
    has_gpu = any(
        "gpu" in str(n.get("id", "")).lower() or 
        "gpu" in str(n.get("data", {}).get("label", "")).lower() or 
        "gpu" in str((n.get("data", {}).get("customMetadata") or {}).get("pricingTier", "")).lower() or
        "gpu" in str((n.get("data", {}).get("customMetadata") or {}).get("vmSize", "")).lower()
        for n in nodes
    )

    # Validate against capabilities
    def add_finding(capability_key, msg_fail, msg_recommend):
        if capability_key in explicit_caps:
            validation_findings.append(msg_fail)
        else:
            validation_findings.append(msg_recommend)

    if "object_storage" in required_caps:
        if not has_storage_node:
            add_finding(
                "object_storage",
                "Missing Capability: Object Storage. Reason: Application requires file upload/storage capability.",
                "Recommendation: Object storage may be beneficial because application requires file upload/storage capability."
            )
            
    if "caching" in required_caps:
        if not has_cache_node:
            add_finding(
                "caching",
                "Missing Capability: Caching. Reason: Expected scale or workload caching capability is missing.",
                "Recommendation: Caching/Redis may improve performance for high concurrent user load."
            )
            
    if "secrets_management" in required_caps or requires_advanced_security:
        if not has_auth_vault:
            add_finding(
                "secrets_management",
                "Missing Capability: Secrets Management. Reason: Sensitive credentials/keys vault security is missing.",
                "Recommendation: Secrets management (Key Vault/Secrets Manager) is recommended to secure sensitive credentials."
            )
            
    if "disaster_recovery" in required_caps or requires_backup_dr:
        if not has_backup:
            validation_findings.append(
                "Recommendation: Disaster Recovery may be beneficial because availability requirements are high. Reason: Backup and recovery strategies are not represented in the architecture."
            )
            
    if "secure_connectivity" in required_caps or requires_advanced_security:
        if not has_pe:
            # Always advisory — private endpoints are AI architectural decisions, not hard gates
            validation_findings.append(
                "Recommendation: Private connectivity (Private Endpoints) may improve security posture for sensitive workloads."
            )
        if requires_advanced_security and (not has_nsgs or not has_rt):
            # Always advisory — NSGs/Route Tables are AI architectural decisions
            validation_findings.append(
                "Recommendation: Subnet-level network isolation (NSGs/Route Tables) is recommended to restrict traffic flow between layers."
            )

    if "gpu_compute" in required_caps:
        if not has_gpu:
            add_finding(
                "gpu_compute",
                "Missing Capability: GPU Compute. Reason: AI inference or GPU-capable compute resources are required.",
                "Recommendation: GPU compute resources may be beneficial for AI inference workloads."
            )
            
    if "messaging" in required_caps:
        if not has_messaging:
            validation_findings.append(
                "Recommendation: Messaging/Eventing may improve scalability for asynchronous workloads. Reason: Queuing, message queuing, or eventing service is missing for notifications or async tasks."
            )
            
    if "global_distribution" in required_caps:
        if not has_cdn_node:
            add_finding(
                "global_distribution",
                "Missing Capability: Global Content Distribution. Reason: CDN or global traffic distribution service is missing for low latency global reach.",
                "Recommendation: Global content distribution (CDN/Traffic Manager) may improve latency for global users."
            )

    # Fail validation if node renderer cannot resolve a node type
    ALLOWED_TYPES = {
        "GatewayNode", "FrontendNode", "BackendNode", "DatabaseNode", "CacheNode", 
        "StorageNode", "SecurityNode", "MonitoringNode", "RegionGroupNode", 
        "ResourceGroupNode", "VNetGroupNode", "SubnetGroupNode"
    }
    for node in nodes:
        n_type = node.get("type")
        if n_type not in ALLOWED_TYPES:
            validation_findings.append(f"Quality Gate: Node renderer cannot resolve node type '{n_type}' for node '{node.get('id')}'.")

    # 1b. Provider Locking Rules
    # Detect provider from nodes or default
    prov_detect = (provider or next((str(n.get("data", {}).get("provider")).lower() for n in nodes if n.get("data", {}).get("provider")), "azure")).lower()
    
    if prov_detect == "azure":
        forbidden_keywords = ["eks", "rds", "s3", "cloudfront", "alb", "cloudwatch", "aws_", "gke", "cloud-sql", "cloudsql", "cloud-storage", "google_"]
        for n in nodes:
            n_id = str(n.get("id", "")).lower()
            n_tf = str(n.get("data", {}).get("terraform_resource", "")).lower()
            if any(kw in n_id or kw in n_tf for kw in forbidden_keywords):
                validation_findings.append(f"Provider Locking: Azure is selected, but forbidden resource '{n_id}' or type '{n_tf}' was generated.")
    elif prov_detect == "aws":
        forbidden_keywords = ["aks", "azurerm_", "app-gateway", "appgateway", "appgw", "keyvault", "key-vault", "azure-monitor", "gke", "cloud-sql", "cloudsql", "cloud-storage", "google_"]
        for n in nodes:
            n_id = str(n.get("id", "")).lower()
            n_tf = str(n.get("data", {}).get("terraform_resource", "")).lower()
            if any(kw in n_id or kw in n_tf for kw in forbidden_keywords):
                validation_findings.append(f"Provider Locking: AWS is selected, but forbidden resource '{n_id}' or type '{n_tf}' was generated.")
    elif prov_detect == "gcp":
        forbidden_keywords = ["aks", "azurerm_", "app-gateway", "appgateway", "appgw", "keyvault", "key-vault", "azure-monitor", "eks", "rds", "s3", "cloudfront", "alb", "cloudwatch", "aws_"]
        for n in nodes:
            n_id = str(n.get("id", "")).lower()
            n_tf = str(n.get("data", {}).get("terraform_resource", "")).lower()
            if any(kw in n_id or kw in n_tf for kw in forbidden_keywords):
                validation_findings.append(f"Provider Locking: GCP is selected, but forbidden resource '{n_id}' or type '{n_tf}' was generated.")

    # 1c. Compute Platform Locking Rules
    if compute_type:
        comp_lower = str(compute_type).lower()
        if "kubernetes" in comp_lower or "aks" in comp_lower or "eks" in comp_lower or "gke" in comp_lower:
            # Kubernetes allowed. App Service, Container Apps forbidden.
            forbidden = ["app-service", "appservice", "web-app", "webapp", "container-app", "containerapp", "azurerm_linux_web_app", "azurerm_container_app", "aws_elastic_beanstalk", "aws_ecs", "google_cloud_run"]
            for n in nodes:
                n_id = str(n.get("id", "")).lower()
                n_tf = str(n.get("data", {}).get("terraform_resource", "")).lower()
                if any(f in n_id or f in n_tf for f in forbidden):
                    validation_findings.append(f"Compute Locking: Kubernetes is selected, but forbidden compute resource '{n_id}' or type '{n_tf}' was generated.")
        elif "app service" in comp_lower or "web app" in comp_lower:
            # App Service allowed. Kubernetes, Container Apps forbidden.
            forbidden = ["aks-", "eks-", "gke-", "kubernetes", "node-pool", "nodepool", "container-app", "containerapp", "azurerm_kubernetes_cluster", "azurerm_container_app", "aws_eks", "aws_ecs", "google_container_cluster", "google_cloud_run"]
            for n in nodes:
                n_id = str(n.get("id", "")).lower()
                n_tf = str(n.get("data", {}).get("terraform_resource", "")).lower()
                if any(f in n_id or f in n_tf for f in forbidden):
                    validation_findings.append(f"Compute Locking: App Service is selected, but forbidden compute resource '{n_id}' or type '{n_tf}' was generated.")
        elif "container app" in comp_lower:
            # Container Apps allowed. Kubernetes, App Service forbidden.
            forbidden = ["aks-", "eks-", "gke-", "kubernetes", "node-pool", "nodepool", "app-service", "appservice", "web-app", "webapp", "azurerm_kubernetes_cluster", "azurerm_linux_web_app", "aws_eks", "aws_elastic_beanstalk", "google_container_cluster", "google_app_engine"]
            for n in nodes:
                n_id = str(n.get("id", "")).lower()
                n_tf = str(n.get("data", {}).get("terraform_resource", "")).lower()
                if any(f in n_id or f in n_tf for f in forbidden):
                    validation_findings.append(f"Compute Locking: Container Apps is selected, but forbidden compute resource '{n_id}' or type '{n_tf}' was generated.")

    # 1d. Edge Source/Target Existence Validation
    for edge in edges:
        src = edge.get("source")
        tgt = edge.get("target")
        if src not in node_ids:
            consistency_warnings.append(f"Edge Validation: Edge '{edge.get('id')}' references non-existent source node '{src}'.")
        if tgt not in node_ids:
            consistency_warnings.append(f"Edge Validation: Edge '{edge.get('id')}' references non-existent target node '{tgt}'.")

    # 2. Consistency Gate Checks
    non_replica_labels = {}
    for node in nodes:
        n_id = str(node.get("id", ""))
        n_id_lower = n_id.lower()
        lbl = str(node.get("data", {}).get("label", ""))
        lbl_lower = lbl.lower()
        n_type = str(node.get("type", ""))

        # Check duplicate labels (excluding replica/standby)
        is_replica = "replica" in n_id_lower or "standby" in n_id_lower or "replica" in lbl_lower or "standby" in lbl_lower or "backup" in n_id_lower or "backup" in lbl_lower
        
        if not is_replica and n_type not in ["RegionGroupNode", "ResourceGroupNode", "VNetGroupNode", "SubnetGroupNode"]:
            if lbl_lower in non_replica_labels:
                consistency_warnings.append(f"Advisory: Consistency Gate: Duplicate node label '{lbl}' detected (node IDs: '{non_replica_labels[lbl_lower]}' and '{n_id}').")
            else:
                non_replica_labels[lbl_lower] = n_id

        # Check matching parentNode and subnet metadata
        parent = node.get("parentNode")
        subnet_meta = node.get("data", {}).get("subnet", "")
        if parent:
            if parent not in node_ids:
                consistency_warnings.append(f"Advisory: Consistency Gate: Node '{n_id}' references non-existent parentNode '{parent}'.")
            elif parent.startswith("subnet-") or parent.startswith("snet-"):
                if subnet_meta and subnet_meta != parent:
                    consistency_warnings.append(f"Advisory: Consistency Gate: Node '{n_id}' has parentNode '{parent}' but subnet metadata '{subnet_meta}' mismatch.")

    return validation_findings + consistency_warnings + complexity_warnings


# ==========================================
# PHASE 3: Dynamic Cost + Completeness Scores + AI Validation
# ==========================================

def compute_node_cost(node: Dict[str, Any], region: str = "eastus") -> float:
    """Compute monthly cost estimate for a single node based on its type, SKU, replicas, and storage."""
    n_type = str(node.get("type", ""))
    n_id = str(node.get("id", "")).lower()
    data = node.get("data", {})
    meta = data.get("customMetadata") or {}
    
    # Base cost catalog by node type
    base_costs = {
        "GatewayNode": 60.0,
        "FrontendNode": 30.0,
        "BackendNode": 75.0,
        "DatabaseNode": 115.0,
        "CacheNode": 45.0,
        "StorageNode": 25.0,
        "SecurityNode": 15.0,
        "MonitoringNode": 20.0,
    }
    
    # Skip group/container nodes
    if n_type in ("RegionGroupNode", "ResourceGroupNode", "VNetGroupNode", "SubnetGroupNode"):
        return 0.0
    
    base = base_costs.get(n_type, 25.0)
    
    # SKU tier adjustments
    tier = str(meta.get("pricingTier", "Standard"))
    if tier == "Premium":
        base *= 2.0
    elif tier == "Basic":
        base *= 0.5
    
    # Replica multiplier
    replicas = 1
    try:
        replicas = int(meta.get("maxReplicas", 1))
    except (ValueError, TypeError):
        pass
    if replicas > 1 and n_type == "BackendNode":
        base *= min(replicas, 5)  # cap at 5x for cost
    
    # Special overrides
    estimated = data.get("estimated_monthly_cost")
    if estimated and isinstance(estimated, (int, float)) and estimated > 0:
        return float(estimated)
    
    # NSG and Route Table nodes are free
    if any(x in n_id for x in ["nsg-", "rt-", "role-assignment", "managed-identity", "backup-policy"]):
        return 0.0
    
    return round(base, 2)


def compute_architecture_scores(nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]], warnings: List[str], provider: str = "azure", requirements: Any = None) -> Dict[str, Any]:
    """
    Calculate 6 completeness scores + overall architecture score:
    - requirement_coverage_score: Starts at 100, drops for missing profile-specific required nodes / capabilities
    - security_score: Starts at 100, drops for missing vault, WAF, PE, NSGs if required by workload risk
    - reliability_score: Drops for missing replicas, backups, HA if required by workload risk
    - scalability_score: Drops for missing autoscale, load balancing, caching if required by workload risk
    - cost_efficiency_score: Based on total cost and overengineering/budget alignment
    - terraform_alignment_score: Drops for round-trip drift warnings
    - architecture_score: Weighted average of the above (highest weight on requirement coverage)
    """
    node_ids_lower = {str(n.get("id", "")).lower() for n in nodes}
    node_labels_lower = {str(n.get("data", {}).get("label", "")).lower() for n in nodes}
    node_types_lower = {str(n.get("type", "")).lower() for n in nodes}

    # Classify workload profile and extract requirements
    def get_req_val(key, default=None):
        if not requirements:
            return default
        if isinstance(requirements, dict):
            return requirements.get(key, default)
        return getattr(requirements, key, default)

    app_desc = str(get_req_val("app_description", "") or get_req_val("appDescription", "")).lower()
    app_type = str(get_req_val("application_type", "") or get_req_val("applicationType", "")).lower()
    workload_profile = str(get_req_val("workload_profile", "")).lower()

    compliance_str = str(get_req_val("security_level", "") or get_req_val("compliance_standards", "")).lower()
    sensitivity_str = str(get_req_val("security_level", "") or get_req_val("data_sensitivity", "")).lower()
    availability_target = str(get_req_val("availability_target", "") or get_req_val("availability_requirements", "")).lower()
    budget_str = str(get_req_val("monthly_budget", "")).lower()
    
    has_pci_or_sensitive = any(c in compliance_str or c in sensitivity_str for c in ["pci", "hipaa", "gdpr", "soc2", "iso27001", "high", "critical"])
    is_enterprise = any(b in budget_str for b in ["enterprise", "unlimited", "5000", "50000"])
    is_mission_critical = any(a in availability_target for a in ["high availability", "mission critical"])
    
    requires_advanced_security = has_pci_or_sensitive or is_enterprise
    requires_backup_dr = is_mission_critical or any(s in sensitivity_str for s in ["high", "critical"])

    capabilities_raw = get_req_val("required_capabilities")
    required_caps = []
    if isinstance(capabilities_raw, list):
        required_caps = [str(c).lower().strip() for c in capabilities_raw]

    if not required_caps:
        # Heuristically derive capabilities
        if "upload" in app_desc or "file" in app_desc or "document" in app_desc or "model storage" in app_desc:
            required_caps.append("object_storage")
        if "caching" in app_desc or "redis" in app_desc or "cache" in app_desc or "100k" in app_desc or "10k" in app_desc:
            required_caps.append("caching")
        if "secret" in app_desc or "vault" in app_desc or "credential" in app_desc or "password" in app_desc or requires_advanced_security:
            required_caps.append("secrets_management")
        if requires_backup_dr or "backup" in app_desc or "recovery" in app_desc:
            required_caps.append("disaster_recovery")
        if requires_advanced_security or "private connect" in app_desc or "private endpoint" in app_desc:
            required_caps.append("secure_connectivity")
        if "ai" in app_desc or "gpu" in app_desc or "inference" in app_desc or "ml" in app_desc:
            required_caps.append("gpu_compute")
        if "notification" in app_desc or "message" in app_desc or "event" in app_desc or "queue" in app_desc:
            required_caps.append("messaging")
        if "global" in app_desc or "cdn" in app_desc or "traffic manager" in app_desc or "cloudfront" in app_desc:
            required_caps.append("global_distribution")

    # Identify nodes
    has_db = any(t == "databasenode" or any(db_kw in nid for db_kw in ["db", "database", "postgres", "mysql", "cosmos", "sql"]) for nid, t in zip(node_ids_lower, node_types_lower))
    has_storage = any(t == "storagenode" or any(st_kw in nid for st_kw in ["storage", "blob", "bucket", "s3"]) for nid, t in zip(node_ids_lower, node_types_lower))
    has_cache = any(t == "cachenode" or "cache" in nid or "redis" in nid for nid, t in zip(node_ids_lower, node_types_lower))
    has_cdn = any("cdn" in nid or "frontdoor" in nid or "front-door" in nid or "cloudfront" in nid for nid in node_ids_lower)
    has_vault = any(str(n.get("type", "")).lower() == "securitynode" and any(k in str(n.get("id", "")).lower() or k in str(n.get("data", {}).get("label", "")).lower() for k in ["vault", "keyvault", "secret", "identity", "auth"]) for n in nodes)
    has_backup = any(any(k in nid for k in ["backup", "recovery", "vault"]) and "key" not in nid for nid in node_ids_lower)
    has_nsgs = any(any(k in nid for k in ["nsg", "security-group", "security_group", "firewall"]) for nid in node_ids_lower)
    has_rt = any(any(k in nid for k in ["rt-", "route-table", "routetable", "route_table"]) for nid in node_ids_lower)
    has_pe = any("pe-" in nid or "pe_" in nid or "private-endpoint" in nid or "privateendpoint" in nid or "private endpoint" in str(n.get("data", {}).get("label", "")).lower() for n in nodes for nid in [str(n.get("id", "")).lower()])
    has_messaging = any(any(m in nid for m in ["queue", "event", "bus", "pubsub", "sns", "sqs", "messaging", "servicebus"]) for nid in node_ids_lower)
    has_gpu = any(
        "gpu" in str(n.get("id", "")).lower() or 
        "gpu" in str(n.get("data", {}).get("label", "")).lower() or 
        "gpu" in str((n.get("data", {}).get("customMetadata") or {}).get("pricingTier", "")).lower() or
        "gpu" in str((n.get("data", {}).get("customMetadata") or {}).get("vmSize", "")).lower()
        for n in nodes
    )
    has_compute = any(
        n_type in ["backendnode", "frontendnode"] or 
        any(x in nid.lower() for x in ["cluster", "env", "plan", "aks", "compute"])
        for nid, n_type in zip(node_ids_lower, node_types_lower)
    )

    cap_fulfillment = {
        "object_storage": has_storage,
        "caching": has_cache,
        "secrets_management": has_vault,
        "disaster_recovery": has_backup,
        "secure_connectivity": has_pe,
        "gpu_compute": has_gpu,
        "messaging": has_messaging,
        "global_distribution": has_cdn
    }

    # Requirement Coverage Checklist
    checklist = []
    db_type_val = get_req_val("database_type") or get_req_val("databaseType")
    if db_type_val and str(db_type_val).lower() not in ["none", "no database", ""]:
        checklist.append(("database", has_db))
    compute_type_val = get_req_val("computeType") or get_req_val("compute_type") or get_req_val("application_type") or get_req_val("applicationType")
    if compute_type_val and str(compute_type_val).lower() not in ["none", ""]:
        checklist.append(("compute", has_compute))
        
    for cap in required_caps:
        if cap in cap_fulfillment:
            checklist.append((cap, cap_fulfillment[cap]))
            
    if checklist:
        satisfied_count = sum(1 for item, met in checklist if met)
        req_cov_score = int((satisfied_count / len(checklist)) * 100)
    else:
        req_cov_score = 100

    # Security Score (appropriate for workload risk)
    sec_score = 100
    if requires_advanced_security:
        if not has_vault:
            sec_score -= 15
        if not has_pe:
            sec_score -= 10
        if not has_nsgs:
            sec_score -= 10
        if not has_rt:
            sec_score -= 10
    else:
        if "secrets_management" in required_caps and not has_vault:
            sec_score -= 15
        if "secure_connectivity" in required_caps and not has_pe:
            sec_score -= 10
    sec_score = max(0, sec_score)
    
    # Reliability Score (availability & recovery)
    rel_score = 100
    if requires_backup_dr:
        if not has_backup:
            rel_score -= 15
        # If DB exists, it should have replicas
        has_replica = any("replica" in nid or "standby" in nid or "replica" in lbl for nid in node_ids_lower for lbl in node_labels_lower)
        db_nodes = [n for n in nodes if n.get("type") == "DatabaseNode"]
        if has_db and (not has_replica or len(db_nodes) < 2):
            rel_score -= 15
    else:
        if "disaster_recovery" in required_caps and not has_backup:
            rel_score -= 15
    rel_score = max(0, rel_score)
    
    # Scalability Score
    scal_score = 100
    users_scale = str(get_req_val("expected_users") or get_req_val("expectedUsers") or "").lower()
    is_high_scale = "100k" in users_scale or "1m" in users_scale or "high" in users_scale or "caching" in required_caps or "global_distribution" in required_caps
    
    has_hpa = any("hpa" in nid or "autoscaler" in lbl or "autoscale" in lbl for nid in node_ids_lower for lbl in node_labels_lower)
    has_lb = any(x in nid or "loadbalancer" in lbl or "lb" in lbl or "gateway" in lbl or "alb" in lbl for nid in node_ids_lower for lbl in node_labels_lower for x in ["app-gateway", "appgw", "alb", "ingress-controller"])
    
    if is_high_scale:
        if "caching" in required_caps and not has_cache:
            scal_score -= 15
        if not has_hpa:
            scal_score -= 15
        if not has_lb:
            scal_score -= 15
    else:
        if "caching" in required_caps and not has_cache:
            scal_score -= 15
    scal_score = max(0, scal_score)

    # Cost Efficiency Score (budget alignment & overengineering checks)
    total_cost = sum(compute_node_cost(n) for n in nodes)
    cost_score = 100
    
    budget_limit = None
    budget_val = get_req_val("monthly_budget") or get_req_val("monthlyBudget")
    if budget_val:
        match_digits = re.findall(r'\d+', str(budget_val).replace(",", ""))
        if match_digits:
            try:
                budget_limit = float(match_digits[0])
            except ValueError:
                pass
                
    if budget_limit and budget_limit > 0:
        if total_cost > budget_limit:
            pct_over = ((total_cost - budget_limit) / budget_limit) * 100
            cost_score -= min(60, int(pct_over / 2))
    else:
        # Default budget thresholds
        if total_cost > 2000:
            cost_score -= 20
        if total_cost > 5000:
            cost_score -= 20
            
    if not requires_advanced_security and total_cost > 800:
        cost_score -= 20
    if len(nodes) > 40:
        cost_score -= 10
        
    cost_score = max(0, cost_score)
    
    # Terraform Alignment Score
    tf_score = 100
    tf_drift_warnings = [w for w in warnings if "Terraform Drift" in w]
    tf_score -= len(tf_drift_warnings) * 15
    tf_score = max(0, tf_score)
    
    # Weighted average architecture score
    arch_score = int(
        req_cov_score * 0.30 +
        sec_score * 0.20 +
        rel_score * 0.15 +
        scal_score * 0.15 +
        cost_score * 0.10 +
        tf_score * 0.10
    )
    
    return {
        "requirement_coverage_score": req_cov_score,
        "security_score": sec_score,
        "reliability_score": rel_score,
        "scalability_score": scal_score,
        "cost_efficiency_score": cost_score,
        "terraform_alignment_score": tf_score,
        "architecture_score": arch_score,
        "total_estimated_cost": round(total_cost, 2)
    }


def run_ai_validation_agent(nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]], provider: str = "azure") -> List[str]:
    """
    Advisory AI Validation Agent that inspects the generated architecture topology
    and returns actionable recommendations (non-blocking warnings).
    """
    recommendations = []
    node_ids_lower = {str(n.get("id", "")).lower() for n in nodes}
    node_labels_lower = {str(n.get("data", {}).get("label", "")).lower() for n in nodes}
    
    # 1. Private Endpoint coverage
    pe_targets = set()
    for nid in node_ids_lower:
        if nid.startswith("pe-"):
            target = nid.replace("pe-", "")
            pe_targets.add(target)
    
    if "db-primary" in node_ids_lower and "db" not in pe_targets:
        recommendations.append("Advisory: Private Endpoint missing for PostgreSQL database. Consider adding PE-DB for secure connectivity.")
    if "redis" in node_ids_lower and "redis" not in pe_targets:
        recommendations.append("Advisory: Private Endpoint missing for Redis Cache. Consider adding PE-Redis for secure connectivity.")
    if "storage-account" in node_ids_lower and "storage" not in pe_targets:
        recommendations.append("Advisory: Private Endpoint missing for Storage Account. Consider adding PE-Storage for secure connectivity.")
    
    # 2. AKS best practices
    if "aks-cluster" in node_ids_lower:
        if "aks-hpa" not in node_ids_lower:
            recommendations.append("Advisory: AKS cluster should have Horizontal Pod Autoscaler (HPA) configured for production workloads.")
        if "acr" not in node_ids_lower:
            recommendations.append("Advisory: AKS cluster should use Azure Container Registry (ACR) for container image storage.")
        if not any("availability" in lbl or "zone" in lbl for lbl in node_labels_lower):
            recommendations.append("Advisory: AKS cluster should use Availability Zones for high availability in production.")
    
    # 3. Redis tier
    for n in nodes:
        nid = str(n.get("id", "")).lower()
        if nid == "redis" and n.get("type") == "CacheNode":
            meta = n.get("data", {}).get("customMetadata") or {}
            if meta.get("pricingTier") != "Premium":
                recommendations.append("Advisory: Redis should use Premium tier for HA features like persistence and geo-replication.")
    
    # 4. Database HA
    db_count = len([n for n in nodes if n.get("type") == "DatabaseNode"])
    has_replica = any("replica" in str(n.get("id", "")).lower() for n in nodes if n.get("type") == "DatabaseNode")
    if db_count > 0 and not has_replica:
        recommendations.append("Advisory: Database HA read-replica is missing. Deploy a standby replica for zero-downtime failover.")
    
    # 5. Monitoring completeness
    if "log-analytics" not in node_ids_lower:
        recommendations.append("Advisory: Log Analytics Workspace is missing. Centralized logging is essential for observability.")
    if "app-insights" not in node_ids_lower:
        recommendations.append("Advisory: Application Insights is missing. APM telemetry is critical for performance monitoring.")
    if "diagnostic-settings" not in node_ids_lower:
        recommendations.append("Advisory: Diagnostic Settings are missing. Enable diagnostics for AKS, databases, and gateways.")
    
    # 6. Backup coverage
    if "backup-vault" not in node_ids_lower and "recovery-vault" not in node_ids_lower:
        recommendations.append("Advisory: No Backup or Recovery Vault detected. Critical data should have automated backup policies.")
    
    # 7. Edge validation
    valid_node_ids = {str(n.get("id")) for n in nodes if n.get("id")}
    orphan_edges = [e for e in edges if e.get("source") not in valid_node_ids or e.get("target") not in valid_node_ids]
    if orphan_edges:
        recommendations.append(f"Advisory: {len(orphan_edges)} edge(s) reference non-existent nodes. Verify topology connectivity.")
    
    return recommendations


def heal_topology_gates(nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]], provider: str, requirements: Any) -> tuple:
    node_ids = {str(n.get("id")).lower() for n in nodes if n.get("id")}
    node_labels = {str(n.get("id")).lower(): str(n.get("data", {}).get("label", "")).lower() for n in nodes}
    node_types = {str(n.get("id")).lower(): str(n.get("type", "")) for n in nodes}
    
    # 1. Ensure VNet/Subnets exist
    nodes = ensure_container_nodes(nodes, provider, requirements)
    node_ids = {str(n.get("id")).lower() for n in nodes if n.get("id")}

    # Assess Workload Risk & Capabilities
    def get_req_val(key, default=None):
        if not requirements:
            return default
        if isinstance(requirements, dict):
            return requirements.get(key, default)
        return getattr(requirements, key, default)

    app_desc = str(get_req_val("app_description", "") or get_req_val("appDescription", "")).lower()
    app_type = str(get_req_val("application_type", "") or get_req_val("applicationType", "")).lower()
    workload_profile = str(get_req_val("workload_profile", "")).lower()

    compliance_str = str(get_req_val("security_level", "") or get_req_val("compliance_standards", "")).lower()
    sensitivity_str = str(get_req_val("security_level", "") or get_req_val("data_sensitivity", "")).lower()
    availability_target = str(get_req_val("availability_target", "") or get_req_val("availability_requirements", "")).lower()
    budget_str = str(get_req_val("monthly_budget", "")).lower()
    
    has_pci_or_sensitive = any(c in compliance_str or c in sensitivity_str for c in ["pci", "hipaa", "gdpr", "soc2", "iso27001", "high", "critical"])
    is_enterprise = any(b in budget_str for b in ["enterprise", "unlimited", "5000", "50000"])
    is_mission_critical = any(a in availability_target for a in ["high availability", "mission critical"])
    
    requires_advanced_security = has_pci_or_sensitive or is_enterprise
    requires_backup_dr = is_mission_critical or any(s in sensitivity_str for s in ["high", "critical"])

    capabilities_raw = get_req_val("required_capabilities")
    required_caps = []
    if isinstance(capabilities_raw, list):
        required_caps = [str(c).lower().strip() for c in capabilities_raw]

    if not required_caps:
        if "upload" in app_desc or "file" in app_desc or "document" in app_desc or "model storage" in app_desc:
            required_caps.append("object_storage")
        if "caching" in app_desc or "redis" in app_desc or "cache" in app_desc or "100k" in app_desc or "10k" in app_desc:
            required_caps.append("caching")
        if "secret" in app_desc or "vault" in app_desc or "credential" in app_desc or "password" in app_desc or requires_advanced_security:
            required_caps.append("secrets_management")
        if requires_backup_dr or "backup" in app_desc or "recovery" in app_desc:
            required_caps.append("disaster_recovery")
        if requires_advanced_security or "private connect" in app_desc or "private endpoint" in app_desc:
            required_caps.append("secure_connectivity")
        if "ai" in app_desc or "gpu" in app_desc or "inference" in app_desc or "ml" in app_desc:
            required_caps.append("gpu_compute")
        if "notification" in app_desc or "message" in app_desc or "event" in app_desc or "queue" in app_desc:
            required_caps.append("messaging")
        if "global" in app_desc or "cdn" in app_desc or "traffic manager" in app_desc or "cloudfront" in app_desc:
            required_caps.append("global_distribution")

    # 2. Conditionally Ensure Route Tables and NSGs exist for subnets (ONLY if requires_advanced_security is true)
    if requires_advanced_security:
        REAL_SUBNET_IDS = {"subnet-ingress", "subnet-mgmt", "subnet-app", "subnet-data", "subnet-pe"}
        subnet_nodes = [
            n for n in nodes
            if str(n.get("id", "")).lower() in REAL_SUBNET_IDS
        ]
        
        for sub_node in subnet_nodes:
            sub_node_id = sub_node.get("id")
            sub_node_id_lower = str(sub_node_id).lower()
            
            # Determine clean prefix/suffix for nsg and rt naming
            if sub_node_id_lower.startswith("subnet-"):
                sub_name = sub_node_id[7:]
            elif sub_node_id_lower.startswith("subnet_"):
                sub_name = sub_node_id[7:]
            else:
                sub_name = sub_node_id
                
            # Check NSG in this subnet
            has_nsg = any(
                (parent == sub_node_id_lower and ("nsg" in nid or "nsg" in node_labels.get(nid, "")))
                for nid, parent in [(str(n.get("id")).lower(), str(n.get("parentNode", "")).lower()) for n in nodes]
            )
            if not has_nsg:
                nsg_id = f"nsg-{sub_name}"
                if nsg_id.lower() not in node_ids:
                    nodes.append({
                        "id": nsg_id,
                        "type": "SecurityNode",
                        "parentNode": sub_node_id,
                        "position": {"x": 30.0, "y": 60.0},
                        "data": {"label": f"Security Group ({sub_name.upper()})", "subnet": sub_node_id, "provider": provider}
                    })
                
            # Check RT in this subnet
            has_rt = any(
                (parent == sub_node_id_lower and ("rt-" in nid or "-rt" in nid or "route table" in node_labels.get(nid, "") or "route-table" in node_labels.get(nid, "")))
                for nid, parent in [(str(n.get("id")).lower(), str(n.get("parentNode", "")).lower()) for n in nodes]
            )
            if not has_rt:
                rt_id = f"rt-{sub_name}"
                if rt_id.lower() not in node_ids:
                    nodes.append({
                        "id": rt_id,
                        "type": "SecurityNode",
                        "parentNode": sub_node_id,
                        "position": {"x": 200.0, "y": 60.0},
                        "data": {"label": f"Route Table ({sub_name.upper()})", "subnet": sub_node_id, "provider": provider}
                    })
                
        # Update node collections after NSG/RT injections
        node_ids = {str(n.get("id")).lower() for n in nodes if n.get("id")}
        node_labels = {str(n.get("id")).lower(): str(n.get("data", {}).get("label", "")).lower() for n in nodes}
        node_types = {str(n.get("id")).lower(): str(n.get("type", "")) for n in nodes}

    # 3. Ensure Key Vault exists if required by capabilities
    if "secrets_management" in required_caps or requires_advanced_security:
        has_kv = any(
            t == "SecurityNode" and any(x in nid or x in node_labels.get(nid, "") for x in ["vault", "keyvault", "secret"])
            for nid, t in node_types.items()
        )
        if not has_kv:
            nodes.append({
                "id": "keyvault",
                "type": "SecurityNode",
                "parentNode": "shared-services-group",
                "position": {"x": 50.0, "y": 60.0},
                "data": {"label": "Key Vault (Secrets)", "provider": provider}
            })
            node_ids.add("keyvault")
            node_labels["keyvault"] = "key vault (secrets)"
            node_types["keyvault"] = "SecurityNode"
            
    # 4. Ensure Monitoring Node exists conditionally
    if requires_advanced_security or requires_backup_dr or "monitoring" in required_caps or any(t == "monitoringnode" for t in node_types.values()):
        has_mon = any(
            t == "MonitoringNode" or any(x in nid or x in node_labels.get(nid, "") for x in ["monitor", "insights", "analytics"])
            for nid, t in node_types.items()
        )
        if not has_mon:
            nodes.append({
                "id": "log-analytics",
                "type": "MonitoringNode",
                "parentNode": "shared-services-group",
                "position": {"x": 50.0, "y": 160.0},
                "data": {"label": "Log Analytics Workspace", "provider": provider}
            })
            node_ids.add("log-analytics")
            node_labels["log-analytics"] = "log analytics workspace"
            node_types["log-analytics"] = "MonitoringNode"
            
    # 5. Ensure Backup Vault exists if required
    if "disaster_recovery" in required_caps or requires_backup_dr:
        has_backup = any(
            any(x in nid for x in ["backup", "recovery", "vault"]) and "key" not in nid
            for nid in node_ids
        )
        if not has_backup:
            nodes.append({
                "id": "backup-vault",
                "type": "StorageNode",
                "parentNode": "shared-services-group",
                "position": {"x": 50.0, "y": 660.0},
                "data": {"label": "Backup Vault (Recovery)", "provider": provider}
            })
            node_ids.add("backup-vault")
            node_labels["backup-vault"] = "backup vault (recovery)"
            node_types["backup-vault"] = "StorageNode"
            
    # 5b. Ensure WAF Policy exists if referenced in edges
    has_waf = any(
        t == "SecurityNode" and any(x in nid or x in node_labels.get(nid, "") for x in ["waf", "waf-policy", "waf_policy"])
        for nid, t in node_types.items()
    )
    if not has_waf:
        referenced_waf = any("waf" in str(e.get("source")).lower() or "waf" in str(e.get("target")).lower() for e in edges)
        if referenced_waf:
            nodes.append({
                "id": "waf-policy",
                "type": "SecurityNode",
                "parentNode": "subnet-ingress",
                "position": {"x": 100.0, "y": 60.0},
                "data": {"label": "WAF Policy", "subnet": "subnet-ingress", "provider": provider}
            })
            # Update collections
            node_ids.add("waf-policy")
            node_labels["waf-policy"] = "waf policy"
            node_types["waf-policy"] = "SecurityNode"

    # 6. Ensure Private Endpoints exist conditionally
    if "secure_connectivity" in required_caps or requires_advanced_security:
        has_pe = any(
            "pe-" in nid or "pe_" in nid or "private endpoint" in node_labels.get(nid, "")
            for nid in node_ids
        )
        if not has_pe:
            # Create private endpoints for database and storage if they exist
            db_nodes = [nid for nid, t in node_types.items() if t == "DatabaseNode"]
            storage_nodes = [nid for nid, t in node_types.items() if t == "StorageNode" and "backup" not in nid]
            
            pe_count = 0
            if db_nodes:
                pe_id = "pe-db"
                nodes.append({
                    "id": pe_id,
                    "type": "SecurityNode",
                    "parentNode": "subnet-pe",
                    "position": {"x": 50.0 + pe_count * 200, "y": 60.0},
                    "data": {"label": "PE Database Connection", "subnet": "subnet-pe", "provider": provider}
                })
                edges.append({
                    "id": f"e-pe-db-{db_nodes[0]}",
                    "source": pe_id,
                    "target": db_nodes[0],
                    "animated": False
                })
                pe_count += 1
                node_ids.add(pe_id)
                node_labels[pe_id] = "pe database connection"
                node_types[pe_id] = "SecurityNode"
                
            if storage_nodes:
                pe_id = "pe-storage"
                nodes.append({
                    "id": pe_id,
                    "type": "SecurityNode",
                    "parentNode": "subnet-pe",
                    "position": {"x": 50.0 + pe_count * 200, "y": 60.0},
                    "data": {"label": "PE Storage Connection", "subnet": "subnet-pe", "provider": provider}
                })
                edges.append({
                    "id": f"e-pe-storage-{storage_nodes[0]}",
                    "source": pe_id,
                    "target": storage_nodes[0],
                    "animated": False
                })
                pe_count += 1
                node_ids.add(pe_id)
                node_labels[pe_id] = "pe storage connection"
                node_types[pe_id] = "SecurityNode"
                
            if not pe_count:
                # Inject a fallback PE to make sure subnet-pe is not empty
                pe_id = "pe-fallback"
                nodes.append({
                    "id": pe_id,
                    "type": "SecurityNode",
                    "parentNode": "subnet-pe",
                    "position": {"x": 50.0, "y": 60.0},
                    "data": {"label": "Private Endpoint Connection", "subnet": "subnet-pe", "provider": provider}
                })
                node_ids.add(pe_id)
                node_labels[pe_id] = "private endpoint connection"
                node_types[pe_id] = "SecurityNode"

    # Clean up orphan edges
    node_ids = {str(n.get("id")).lower() for n in nodes if n.get("id")}
    edges = [e for e in edges if str(e.get("source")).lower() in node_ids and str(e.get("target")).lower() in node_ids]

    return nodes, edges


@router.get('/provider-status')
async def get_provider_status():
    manager = ProviderManager()
    provider = await manager.get_available_provider()
    return {
        "active_provider": provider.lower(),
        "model": manager.active_model,
        "fallback_count": len(manager.fallback_chain) if manager.fallback_chain else 0,
        "last_error": None # For now just return None
    }

@router.post('/generate-architecture', response_model=ArchitectureResponse)
async def generate_architecture(requirements: RequirementInput, request: Request):
    request_id = str(uuid.uuid4())
    start_time = asyncio.get_event_loop().time()
    provider = requirements.cloud_provider.lower()
    
    logger.info(f"Pipeline Stage: Requirements Received. Request ID: {request_id}. Payload: {requirements.model_dump()}")
    
    # 1. Check Cache
    cached = cache_manager.get(requirements)
    if cached:
        c_nodes = cached.get('nodes', [])
        if len(c_nodes) > 0:
            # Heal legacy/incomplete cached entry to ensure required containers exist
            c_nodes = ensure_container_nodes(c_nodes, cached.get('cloud_provider', provider), requirements)
            
            # Perform ID alignment for compute engine node
            compute_type = getattr(requirements, "computeType", None) or getattr(requirements, "application_type", None) or "AKS"
            compute_type_lower = str(compute_type).lower()
            compute_target_id = "aks-cluster"
            if "app service" in compute_type_lower or "web app" in compute_type_lower:
                compute_target_id = "app-service-plan"
            elif "container app" in compute_type_lower:
                compute_target_id = "container-app-env"

            if compute_target_id != "aks-cluster":
                for n in c_nodes:
                    if str(n.get("id")).lower() == "aks-cluster":
                        n["id"] = compute_target_id
                c_edges = cached.get('edges', [])
                for e in c_edges:
                    if str(e.get("source")).lower() == "aks-cluster":
                        e["source"] = compute_target_id
                    if str(e.get("target")).lower() == "aks-cluster":
                        e["target"] = compute_target_id
                cached['edges'] = c_edges

            c_edges = cached.get('edges', [])
            c_nodes = post_process_nodes(c_nodes, cached.get('cloud_provider', provider), requirements, c_edges)
            c_nodes, c_edges = deduplicate_shared_resources(c_nodes, c_edges)
            
            # Heal missing edges in the cached entry if edge count is low
            if len(c_edges) < 35:
                reasoning_engine = InfrastructureReasoningEngine(cloud_provider=provider, requirements=requirements)
                raw_topology = reasoning_engine.synthesize_from_intent()
                topology = reasoning_engine.normalize_topology(raw_topology)
                det_edges = topology.get('edges', [])
                
                c_node_ids = {str(n.get("id")).lower() for n in c_nodes if n.get("id")}
                existing_edge_keys = {
                    (str(e.get("source")).lower(), str(e.get("target")).lower())
                    for e in c_edges if e.get("source") and e.get("target")
                }
                
                merged_edges = list(c_edges)
                for det_edge in det_edges:
                    src = str(det_edge.get("source", "")).lower()
                    tgt = str(det_edge.get("target", "")).lower()
                    if src in c_node_ids and tgt in c_node_ids:
                        if (src, tgt) not in existing_edge_keys and (tgt, src) not in existing_edge_keys:
                            merged_edges.append(det_edge)
                            existing_edge_keys.add((src, tgt))
                c_edges = merged_edges
                cached['edges'] = c_edges
            
            valid_node_ids = {n.get("id") for n in c_nodes if n.get("id")}
            c_edges = [e for e in c_edges if e.get("source") in valid_node_ids and e.get("target") in valid_node_ids]

            cached['services'] = rebuild_services_registry(c_nodes)
            cached['warnings'] = validate_and_gate_architecture(c_nodes, c_edges, cached.get('warnings', []), compute_type=getattr(requirements, 'computeType', None), database_type=getattr(requirements, 'database_type', None), requirements=requirements)
            cached['nodes'] = c_nodes
            cached['node_count'] = len(c_nodes)
            cached['subnet_count'] = _count_real_subnets(c_nodes)
            cached['edge_count'] = len(c_edges)
            cached['edges'] = c_edges
            cached['response_summary'] = {
                "raw_ai_nodes": len(c_nodes),
                "raw_ai_edges": len(c_edges),
                "post_processed_nodes": len(c_nodes),
                "post_processed_edges": len(c_edges),
                "deduplicated_nodes": len(c_nodes),
                "deduplicated_edges": len(c_edges)
            }
            
            exec_ms = int((asyncio.get_event_loop().time() - start_time) * 1000)
            perf_logger.log(request_id, 'Cache', exec_ms / 1000.0, True, [], [])
            cached['execution_time_ms'] = exec_ms
            return ArchitectureResponse(**cached)

    # 2. Pure AI Pipeline (Primary Generator)
    llm_client = request.app.state.provider_manager
    provider = requirements.cloud_provider.lower()
    active_provider = getattr(llm_client, 'active_provider', 'None')
    
    generation_mode = os.getenv('ARCHGEN_GENERATION_MODE', 'AI_ONLY')
    ai_enhanced = False
    
    # Initialize variables that must be in outer scope
    nodes = []
    edges = []
    services = []
    validation_findings = []
    
    raw_ai_nodes_count = 0
    raw_ai_edges_count = 0
    post_processed_nodes_count = 0
    post_processed_edges_count = 0
    deduplicated_nodes_count = 0
    deduplicated_edges_count = 0
    
    # Check if provider exists
    if active_provider is None or active_provider.lower() in ['none', 'mock']:
        if generation_mode == 'AI_ONLY':
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "No available LLM providers",
                    "recommendation": "Configure OpenAI, DeepSeek, Azure OpenAI, or Ollama."
                }
            )
        else:
            logger.info("No active LLM provider. Bypassing AI pipeline and using Deterministic Engine.")
    else:
        try:
            from agents.requirement_analysis import RequirementAnalysisAgent
            from agents.architecture_planning import ArchitecturePlanningAgent
            from agents.topology_generation import TopologyGenerationAgent
            
            req_agent = RequirementAnalysisAgent(client=llm_client)
            plan_agent = ArchitecturePlanningAgent(client=llm_client)
            topology_agent = TopologyGenerationAgent(client=llm_client)
            
            logger.info("Starting Pure AI Requirement Analysis")
            analysis = await req_agent.analyze(requirements)
            if not isinstance(analysis, dict):
                analysis = {}
            # Inject raw user requirements explicitly to guarantee the planning agent and topology agent get them properly
            analysis["projectName"] = requirements.projectName or analysis.get("projectName") or "Enterprise Stack"
            analysis["region"] = requirements.region or analysis.get("region") or analysis.get("deploymentRegion") or "East US"
            analysis["resourceGroup"] = requirements.resourceGroup or analysis.get("resourceGroup") or "rg-production"
            analysis["vnetCIDR"] = requirements.vnetCIDR or analysis.get("vnetCIDR") or "10.0.0.0/16"
            analysis["computeType"] = requirements.computeType or analysis.get("computeType") or "AKS"
            analysis["database_type"] = requirements.database_type or analysis.get("database_type") or analysis.get("databaseType") or "PostgreSQL"
            analysis["cloud_provider"] = requirements.cloud_provider or analysis.get("cloud_provider") or "azure"
            analysis["monthly_budget"] = requirements.monthly_budget or analysis.get("monthly_budget") or "500"
            
            logger.info(f"Pipeline Stage: Requirement Analysis Completed. Result: {analysis}")
            
            logger.info("Starting Pure AI Architecture Planning")
            plan = await plan_agent.plan(analysis)
            logger.info(f"Pipeline Stage: Architecture Planning Completed. Plan: {plan}")
            
            max_attempts = 3
            for attempt in range(1, max_attempts + 1):
                logger.info(f"Topology Generation Attempt {attempt}/{max_attempts}")
                try:
                    topology_result = await topology_agent.generate(
                        analyzed_requirements=analysis,
                        plan=plan,
                        validation_findings=validation_findings if validation_findings else None
                    )
                    
                    logger.info(f"Pipeline Stage: Raw AI Response Received on attempt {attempt}")
                    print(f"ai_topology: {json.dumps(topology_result, indent=2) if isinstance(topology_result, dict) else str(topology_result)}")
                    
                    nodes = topology_result.get('nodes', [])
                    edges = topology_result.get('edges', [])
                    services = topology_result.get('services', [])
                    logger.info(f"Pre-flatten node count: {len(nodes) if isinstance(nodes, list) else 'non-list'}")
                    # Flatten nested-tree responses from the AI (children arrays)
                    nodes = flatten_nested_nodes(nodes) if isinstance(nodes, list) else []
                    logger.info(f"Post-flatten node count: {len(nodes)}, ids: {[n.get('id') for n in nodes[:5]]}")


                except Exception as e:
                    logger.error(f"Topology Generation Agent failed on attempt {attempt}: {e}")
                    if attempt == max_attempts:
                        raw_resp = getattr(e, 'raw_response', None)
                        if generation_mode == 'AI_ONLY':
                            return JSONResponse(
                                status_code=400,
                                content={
                                    "success": False,
                                    "error": "Topology generation failed",
                                    "details": str(e),
                                    "raw_ai_response": raw_resp
                                }
                            )
                        else:
                            raise e
                    continue
                    
                if not isinstance(nodes, list):
                    nodes = []
                if not isinstance(edges, list):
                    edges = []
                if not isinstance(services, list):
                    services = []
                    
                raw_ai_nodes_count = len(nodes)
                raw_ai_edges_count = len(edges)
                logger.info(f"Pipeline Stage - Raw AI counts: nodes={raw_ai_nodes_count}, edges={raw_ai_edges_count}, services={len(services)}")
                
                # Log unregistered node types
                ALLOWED_TYPES = {
                    "GatewayNode", "FrontendNode", "BackendNode", "DatabaseNode", "CacheNode", 
                    "StorageNode", "SecurityNode", "MonitoringNode", "RegionGroupNode", 
                    "ResourceGroupNode", "VNetGroupNode", "SubnetGroupNode"
                }
                for raw_node in nodes:
                    raw_type = raw_node.get("type")
                    if raw_type not in ALLOWED_TYPES:
                        logger.warning(f"Unknown node type: {raw_type} for node ID: {raw_node.get('id')}")
                        print(f"Unknown node type: {raw_type}")
                    
                # Perform ID alignment for compute engine node
                compute_type = getattr(requirements, "computeType", None) or getattr(requirements, "application_type", None) or "AKS"
                compute_type_lower = str(compute_type).lower()
                compute_target_id = "aks-cluster"
                if "app service" in compute_type_lower or "web app" in compute_type_lower:
                    compute_target_id = "app-service-plan"
                elif "container app" in compute_type_lower:
                    compute_target_id = "container-app-env"

                if compute_target_id != "aks-cluster":
                    for n in nodes:
                        if str(n.get("id")).lower() == "aks-cluster":
                            n["id"] = compute_target_id
                        if str(n.get("parentNode")).lower() == "aks-cluster":
                            n["parentNode"] = compute_target_id
                    for e in edges:
                        if str(e.get("source")).lower() == "aks-cluster":
                            e["source"] = compute_target_id
                        if str(e.get("target")).lower() == "aks-cluster":
                            e["target"] = compute_target_id

                # Use non-mutating validation and normalization layer instead of ensure_container_nodes/post_process_nodes
                nodes, edges = normalize_and_validate_ai_topology(nodes, edges, provider, requirements)
                
                post_processed_nodes_count = len(nodes)
                post_processed_edges_count = len(edges)
                logger.info(f"Pipeline Stage - Normalized AI counts: nodes={post_processed_nodes_count}, edges={post_processed_edges_count}")
                        
                # Deduplicate shared resources to clean up any duplicates generated by the LLM
                nodes, edges = deduplicate_shared_resources(nodes, edges)
                
                deduplicated_nodes_count = len(nodes)
                deduplicated_edges_count = len(edges)
                logger.info(f"Pipeline Stage - Deduplicated counts: nodes={deduplicated_nodes_count}, edges={deduplicated_edges_count}")
                
                # Run validation engine as source of truth
                validation_findings = validate_and_gate_architecture(
                    nodes,
                    edges,
                    compute_type=requirements.computeType,
                    database_type=requirements.database_type,
                    requirements=analysis
                )
                logger.info(f"Pipeline Stage - Validation findings on attempt {attempt}: {validation_findings}")
                
                hard_failures = [f for f in validation_findings if not f.startswith("Recommendation:") and not f.startswith("Advisory:")]
                if not hard_failures:
                    logger.info(f"Topology successfully validated on Attempt {attempt} (with {len(validation_findings) - len(hard_failures)} advisory recommendations)")
                    break
                else:
                    logger.warning(f"Validation failed on Attempt {attempt} due to hard failures: {hard_failures}")
                    
            # If validation failed after 3 attempts, run the topology healing engine to guarantee valid compileable topology
            hard_failures = [f for f in validation_findings if not f.startswith("Recommendation:") and not f.startswith("Advisory:")]
            if hard_failures:
                logger.info("Running topology healing engine to resolve validation findings")
                nodes, edges = heal_topology_gates(nodes, edges, provider, requirements)
                # Re-run post process to snap any newly injected nodes and align IDs
                nodes = post_process_nodes(nodes, provider, requirements, edges)
                
                # Update counts after healing
                post_processed_nodes_count = len(nodes)
                post_processed_edges_count = len(edges)
                deduplicated_nodes_count = len(nodes)
                deduplicated_edges_count = len(edges)
            
            ai_enhanced = True
            
        except Exception as e:
            logger.error(f"AI Generation Pipeline encountered error: {e}")
            if generation_mode == 'AI_ONLY':
                raw_resp = getattr(e, 'raw_response', None)
                return JSONResponse(
                    status_code=400,
                    content={
                        "success": False,
                        "error": "Topology generation failed",
                        "details": str(e),
                        "raw_ai_response": raw_resp
                    }
                )
            else:
                logger.warning("Falling back to Deterministic Engine.")
                ai_enhanced = False
                
    # Deterministic Engine Fallback / Direct Execution
    if not ai_enhanced:
        logger.info("Running Deterministic Engine (InfrastructureReasoningEngine)")
        reasoning_engine = InfrastructureReasoningEngine(cloud_provider=provider, requirements=requirements)
        raw_topology = reasoning_engine.synthesize_from_intent()
        topology = reasoning_engine.normalize_topology(raw_topology)
        
        nodes = topology.get('nodes', [])
        edges = topology.get('edges', [])
        
        # Ensure container nodes and coordinates snap cleanly
        nodes = ensure_container_nodes(nodes, provider, requirements)
        nodes = post_process_nodes(nodes, provider, requirements, edges)
        
        # Minimally set position, data, and style for all nodes to prevent frontend crash
        for idx, node in enumerate(nodes):
            node_data = node.get('data') or {}
            node['data'] = node_data
            
            if 'position' not in node or not isinstance(node['position'], dict):
                node['position'] = {'x': float((idx % 5) * 200), 'y': float((idx // 5) * 150)}
            else:
                node['position']['x'] = float(node['position'].get('x', 0.0))
                node['position']['y'] = float(node['position'].get('y', 0.0))
                
            if 'style' not in node or not isinstance(node['style'], dict):
                node['style'] = {}
                
            # Populate required metadata fields
            node_data['resource_id'] = node_data.get('resource_id') or node.get('id', '')
            node_data['resource_type'] = node_data.get('resource_type') or str(node.get('type', 'resource')).lower()
            node_data['terraform_resource'] = node_data.get('terraform_resource') or ''
            node_data['provider'] = node_data.get('provider') or provider
            node_data['subnet'] = node_data.get('subnet') or node.get('parentNode', '') or ''
            node_data['cost_estimate'] = node_data.get('cost_estimate') or node_data.get('cost', '') or ''
            
            # Sanitization of other properties expected by frontend
            if 'estimated_monthly_cost' not in node_data:
                try:
                    cost_val = float(re.sub(r'[^\d.]', '', str(node_data.get('cost_estimate', '25'))))
                    node_data['estimated_monthly_cost'] = cost_val
                except Exception:
                    node_data['estimated_monthly_cost'] = 25.0
            if 'public' not in node_data:
                node_data['public'] = False
            if 'private' not in node_data:
                node_data['private'] = True
                
        nodes, edges = deduplicate_shared_resources(nodes, edges)
        
        # Populate counts for deterministic run
        raw_ai_nodes_count = 0
        raw_ai_edges_count = 0
        post_processed_nodes_count = len(nodes)
        post_processed_edges_count = len(edges)
        deduplicated_nodes_count = len(nodes)
        deduplicated_edges_count = len(edges)
        
        services = rebuild_services_registry(nodes)

    # Final validation checks and warning list construction
    warnings_list = validate_and_gate_architecture(
        nodes,
        edges,
        compute_type=requirements.computeType,
        database_type=requirements.database_type,
        requirements=requirements
    )
    
    budget_val = 500.0
    try:
        budget_str = re.sub(r'[^\d.]', '', requirements.monthly_budget)
        if budget_str:
            budget_val = float(budget_str)
    except Exception:
        pass

    eval_plan = {'nodes': nodes, 'edges': edges, 'services': services, 'cloud_provider': provider}
    
    # Defaults
    cost_res, complexity_res, secured_res, explanation_res = {}, {}, {}, {}

    # 4. Optional AI Enrichment
    if ai_enhanced and active_provider and active_provider.lower() not in ['none', 'mock']:
        try:
            security_agent = SecurityOptimizationAgent(client=llm_client)
            complexity_agent = ComplexityAuditorAgent(client=llm_client)
            cost_agent = CostOptimizationAgent(client=llm_client)
            explanation_agent = ArchitectureExplanationAgent(client=llm_client)

            async def run_agent_safe(coro, default_val):
                try:
                    return await coro
                except Exception as ex:
                    logger.warning(f"Enrichment agent failed: {ex}")
                    return default_val

            async def run_enrichments():
                return await asyncio.gather(
                    run_agent_safe(security_agent.optimize_security(eval_plan, requirements.app_description), {}),
                    run_agent_safe(complexity_agent.audit(eval_plan, requirements.app_description), {}),
                    run_agent_safe(cost_agent.optimize(eval_plan, requirements.app_description), {}),
                    run_agent_safe(explanation_agent.explain(eval_plan, requirements.model_dump()), {})
                )

            # 60 seconds max enrichment time
            secured_res, complexity_res, cost_res, explanation_res = await asyncio.wait_for(run_enrichments(), timeout=60.0)
        except Exception as e:
            logger.warning(f'Optional AI Enrichment failed or timed out: {e}')

    valid_node_ids = {n.get("id") for n in nodes if n.get("id")}
    edges = [e for e in edges if e.get("source") in valid_node_ids and e.get("target") in valid_node_ids]

    terraform_modules = list(set([n.get('type', 'Module') for n in nodes]))

    end_time = asyncio.get_event_loop().time()
    exec_ms = int((end_time - start_time) * 1000)
    
    # 5. Architecture Quality Gate (Non-blocking Validation)
    warnings_list = validate_and_gate_architecture(nodes, edges, complexity_res.get('warnings', []), compute_type=requirements.computeType, database_type=requirements.database_type, requirements=requirements)
    if len(nodes) < 10:
        warnings_list.append("Architecture generation returned insufficient workload resources.")
        logger.warning("Architecture generation returned insufficient workload resources.")
        
    services = rebuild_services_registry(nodes)
    
    # 6. Phase 3: AI Validation Agent + Completeness Scores
    ai_recommendations = run_ai_validation_agent(nodes, edges, provider)
    arch_scores = compute_architecture_scores(nodes, edges, warnings_list, provider, requirements=requirements)
    
    # Dynamic cost calculation from individual nodes
    dynamic_total_cost = arch_scores.get("total_estimated_cost", budget_val * 0.8)
    
    # Build dynamic cost breakdown from nodes
    dynamic_breakdown = []
    for n in nodes:
        n_cost = compute_node_cost(n)
        if n_cost > 0:
            dynamic_breakdown.append({
                "service": n.get("data", {}).get("label", n.get("id", "Unknown")),
                "cost": n_cost,
                "reason": f"Provisioned under {(n.get('data', {}).get('customMetadata') or {}).get('pricingTier', 'Standard')} tier."
            })

    # Determine provider/model names to return (never return mock)
    active_provider_val = active_provider if ai_enhanced else 'deterministic'
    active_model_val = getattr(llm_client, 'active_model', 'Deterministic Engine') if ai_enhanced else 'Deterministic Engine'
    generation_source = f"pure_ai+{active_provider_val.lower()}"

    response_summary = {
        "raw_ai_nodes": raw_ai_nodes_count,
        "raw_ai_edges": raw_ai_edges_count,
        "post_processed_nodes": post_processed_nodes_count,
        "post_processed_edges": post_processed_edges_count,
        "deduplicated_nodes": deduplicated_nodes_count,
        "deduplicated_edges": deduplicated_edges_count
    }
    
    logger.info(f"Pipeline Stage: API Response Ready. Response Summary: {response_summary}")

    resp_dict = {
        'nodes': nodes,
        'edges': edges,
        'services': services,
        'cloud_provider': provider,
        'active_provider': active_provider_val,
        'active_model': active_model_val,
        'fallback_trigger': getattr(llm_client, 'fallback_trigger', 'none') if ai_enhanced else 'none',
        'cost_estimate': float(cost_res.get('estimated_monthly_cost', dynamic_total_cost)),
        'cost_breakdown': dynamic_breakdown if dynamic_breakdown else cost_res.get('cost_breakdown', []),
        'optimization_recommendations': cost_res.get('optimization_recommendations', []) + ai_recommendations,
        'complexity_score': int(complexity_res.get('complexity_score', 45)),
        'operational_overhead_score': int(complexity_res.get('operational_overhead_score', 30)),
        'overengineered': bool(complexity_res.get('overengineered', False)),
        'warnings': warnings_list,
        'requirement_coverage_score': arch_scores.get('requirement_coverage_score', 100),
        'security_score': arch_scores.get('security_score', int(secured_res.get('security_score', 85))),
        'security_findings': secured_res.get('security_findings', []),
        'compliance_checks': secured_res.get('compliance_checks', []),
        'explanation': explanation_res.get('explanation', 'An AI-generated cloud architecture tailored to your workload profile.'),
        'alternatives_considered': explanation_res.get('alternatives_considered', ''),
        'justification_for_choices': explanation_res.get('justification_for_choices', ''),
        'terraform_modules': terraform_modules,
        'execution_time_ms': exec_ms,
        'generation_source': generation_source,
        'provider': provider,
        'node_count': len(nodes),
        'edge_count': len(edges),
        'subnet_count': _count_real_subnets(nodes),
        'response_summary': response_summary
    }

    perf_logger.log(request_id, resp_dict['active_provider'], exec_ms / 1000.0, False, getattr(llm_client, 'fallback_chain', []), [])
    cache_manager.set(requirements, resp_dict)

    return ArchitectureResponse(**resp_dict)

@router.post('/generate-terraform', response_model=TerraformResponse)
async def generate_terraform(request: TerraformRequest):
    try:
        nodes_dict = [node.model_dump() if hasattr(node, "model_dump") else node for node in request.nodes]
        edges_dict = [edge.model_dump() if hasattr(edge, "model_dump") else edge for edge in request.edges]
        services_dict = [svc.model_dump() if hasattr(svc, "model_dump") else svc for svc in request.services]

        # Run validation engine as source of truth. Compile only approved architectures.
        # Only block on hard failures — advisory recommendations (Recommendation:/Advisory: prefix) are non-blocking.
        validation_findings = validate_and_gate_architecture(nodes_dict, edges_dict)
        hard_failures = [f for f in validation_findings if not f.startswith("Recommendation:") and not f.startswith("Advisory:")]
        if hard_failures:
            logger.warning(f"Terraform compilation blocked due to hard failures: {hard_failures}")
            raise HTTPException(
                status_code=400,
                detail=f"Architecture validation failed. Compilation blocked. Findings: {', '.join(hard_failures)}"
            )


        rendered = tf_engine.generate(
            nodes=nodes_dict,
            edges=edges_dict,
            services=services_dict,
            provider=request.cloud_provider
        )

        drift_warnings = rendered.get('warnings', [])
        # If there is any drift/incompatibility and force_regenerate is False, block compilation and return 400
        if drift_warnings and not request.force_regenerate:
            logger.warning(f"Terraform compilation blocked due to drift/incompatibilities: {drift_warnings}")
            raise HTTPException(
                status_code=400,
                detail=f"Architecture drift/incompatibilities detected. Findings: {', '.join(drift_warnings)}"
            )

        return TerraformResponse(
            main_tf=rendered.get('main_tf', ''),
            variables_tf=rendered.get('variables_tf', ''),
            outputs_tf=rendered.get('outputs_tf', ''),
            terraform_tfvars=rendered.get('terraform_tfvars', ''),
            instructions=rendered.get('instructions', ''),
            warnings=drift_warnings
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f'HCL compilation failed: {e}')
        raise HTTPException(status_code=500, detail=str(e))

@router.post('/optimize-cost')
async def optimize_cost(payload: Dict[str, Any], request: Request):
    try:
        nodes = payload.get('nodes', [])
        
        # Base pricing catalog mapping
        catalog = {
            "GatewayNode": 60.0,
            "FrontendNode": 30.0,
            "BackendNode": 75.0,
            "DatabaseNode": 115.0,
            "CacheNode": 45.0,
            "StorageNode": 25.0,
            "SecurityNode": 15.0,
            "MonitoringNode": 20.0,
        }

        breakdown = []
        total = 0.0

        for node in nodes:
            n_type = node.get("type", "")
            if n_type in ["RegionGroupNode", "ResourceGroupNode", "VNetGroupNode", "SubnetGroupNode"]:
                continue
            
            label = node.get("data", {}).get("label", n_type)
            # Check custom metadata pricing tier
            meta = node.get("data", {}).get("customMetadata") or {}
            tier = meta.get("pricingTier", "Standard")

            base_cost = catalog.get(n_type, 25.0)
            if tier == "Premium":
                base_cost *= 2.0
            elif tier == "Basic":
                base_cost *= 0.5

            total += base_cost
            breakdown.append({
                "service": label,
                "cost": base_cost,
                "reason": f"Provisioned under {tier} tier configuration rules."
            })

        recommendations = [
            "Enable Auto-scaling boundaries on the Application Container Node pool to down-scale during idle periods.",
            "Implement multi-region database replication only in production scopes to minimize dev-environment overhead.",
            "Configure cold lifecycle storage rules for logs archived in Storage Account after 15 days."
        ]

        if total > 500.0:
            recommendations.append("Consolidate multiple small databases into a single PostgreSQL Flexible Server database server.")

        return {
            "estimated_monthly_cost": total,
            "cost_breakdown": breakdown,
            "optimization_recommendations": recommendations,
            "cost_score": 90 if total < 500 else 75
        }
    except Exception as e:
        return {'error': str(e)}

@router.post('/validate-architecture')
async def validate_architecture(payload: Dict[str, Any], request: Request):
    try:
        nodes = payload.get('nodes', [])
        edges = payload.get('edges', [])
        
        findings = []
        score = 100

        # Extract node types and IDs
        node_types = {n.get("id"): n.get("type") for n in nodes}
        node_labels = {n.get("id"): str(n.get("data", {}).get("label") or "").lower() for n in nodes}

        # Detect cloud provider from node metadata
        provider = "azure"
        for n in nodes:
            p = n.get("data", {}).get("provider")
            if p:
                provider = p.lower()
                break

        # 1. Check Secrets Vault Presence
        vault_keywords = ["vault", "secret"]
        has_vault = any(t == "SecurityNode" and any(k in node_labels.get(nid, "") for k in vault_keywords) for nid, t in node_types.items())
        if not has_vault:
            score -= 15
            if provider == "aws":
                vault_name = "AWS Secrets Manager"
                remediation = "Deploy a dedicated AWS Secrets Manager node inside the management subnet to encrypt resource keys."
            elif provider == "gcp":
                vault_name = "GCP Secret Manager"
                remediation = "Deploy a dedicated Secret Manager node inside the management subnet to encrypt resource keys."
            else:
                vault_name = "Azure Key Vault"
                remediation = "Deploy a dedicated Key Vault node inside the management subnet to encrypt resource keys."
                
            findings.append({
                "severity": "High",
                "description": f"Secrets vault repository ({vault_name}) is missing.",
                "remediation": remediation
            })

        # 2. Check Database exposure and replica standby
        db_nodes = [nid for nid, t in node_types.items() if t == "DatabaseNode"]
        has_replica = any("replica" in node_labels.get(db_id, "") for db_id in db_nodes)
        
        if db_nodes and not has_replica:
            score -= 10
            findings.append({
                "severity": "Medium",
                "description": "Database high availability read-replica standby is missing.",
                "remediation": "Deploy a read-replica DatabaseNode inside the data subnet to ensure zero point of failure redundancy."
            })

        # 3. Check for public databases
        for db_id in db_nodes:
            # Check if database has incoming edge from internet or gateway without an app cluster
            incoming = [e.get("source") for e in edges if e.get("target") == db_id]
            for source in incoming:
                if node_types.get(source) in ["GatewayNode"]:
                    score -= 20
                    findings.append({
                        "severity": "High",
                        "description": f"Database '{node_labels.get(db_id)}' is directly connected to Ingress Gateway without a proxy compute layer.",
                        "remediation": "Route ingress traffic through Application backend compute clusters and establish private endpoints."
                    })

        # 4. Check for WAF at Ingress
        waf_keywords = ["waf", "armor", "firewall"]
        has_waf = any(any(k in label for k in waf_keywords) for label in node_labels.values())
        if not has_waf:
            score -= 10
            if provider == "aws":
                waf_name = "AWS WAF"
                remediation = "Inject an AWS WAF security layer before the Application Load Balancer."
            elif provider == "gcp":
                waf_name = "Google Cloud Armor"
                remediation = "Inject a Google Cloud Armor security policy before the Global HTTPS Load Balancer."
            else:
                waf_name = "Azure WAF"
                remediation = "Inject an Azure WAF security layer before the Application Gateway load balancer."
                
            findings.append({
                "severity": "Medium",
                "description": f"Web Application Firewall ({waf_name}) is not configured at ingress gateway boundaries.",
                "remediation": remediation
            })

        # 5. Check for Network Security Groups (NSGs) / Security Groups / Firewalls
        sg_keywords = ["nsg", "security group", "firewall", "-sg", "sg-", "sec-group"]
        has_nsgs = any(any(k in label for k in sg_keywords) for label in node_labels.values())
        if not has_nsgs:
            score -= 10
            if provider == "aws":
                sg_name = "Security Groups (SGs)"
                remediation = "Associate an AWS Security Group with each Subnet node to define inbound/outbound rules."
            elif provider == "gcp":
                sg_name = "VPC Firewall Rules"
                remediation = "Define Google Cloud VPC Firewall Rules for each Subnet node to control traffic flow."
            else:
                sg_name = "Network Security Groups (NSGs)"
                remediation = "Associate a Network Security Group (NSG) with each Subnet node to define inbound/outbound rules."
                
            findings.append({
                "severity": "Medium",
                "description": f"Subnet access control policies ({sg_name}) are missing from the subnets.",
                "remediation": remediation
            })

        # Compliance mapping calculations
        compliance = [
            {
                "standard": "SOC2 Type II",
                "status": "Compliant" if score >= 80 else "Partially Compliant",
                "notes": "Requires secure identity vaults and ingress firewalls."
            },
            {
                "standard": "PCI DSS Security",
                "status": "Compliant" if has_vault and has_nsgs and score >= 85 else "Non-Compliant",
                "notes": "Enforces complete encryption of transactional databases and strict subnet boundaries."
            },
            {
                "standard": "HIPAA Privacy",
                "status": "Compliant" if score >= 75 else "Partially Compliant",
                "notes": "Requires database access trace monitoring and encryption keys."
            },
            {
                "standard": "ISO 27001",
                "status": "Compliant" if score >= 90 else "Partially Compliant",
                "notes": "Information security management controls check."
            }
        ]

        return {
            "security_score": max(50, score),
            "security_findings": findings,
            "compliance_checks": compliance
        }
    except Exception as e:
        return {'error': str(e)}

@router.post('/explain-architecture')
async def explain_architecture(payload: Dict[str, Any], request: Request):
    llm_client = request.app.state.provider_manager
    try:
        nodes = payload.get('nodes', [])
        services = payload.get('services', [])
        plan = {'nodes': nodes, 'services': services}
        reqs = 'user-customized'

        explanation_agent = ArchitectureExplanationAgent(client=llm_client)
        return await explanation_agent.explain(plan, reqs)
    except Exception as e:
        return {'error': str(e)}

@router.post('/ai-assist')
async def ai_assist(payload: Dict[str, Any], request: Request):
    try:
        nodes = payload.get('nodes', [])
        edges = payload.get('edges', [])
        services = payload.get('services', [])
        action = payload.get('action', "")

        # Handle deterministic AI-assist transformations
        updated_nodes = list(nodes)
        updated_edges = list(edges)

        provider = "azure"
        for n in nodes:
            p = n.get("data", {}).get("provider")
            if p:
                provider = p
                break

        if action == "optimize_security":
            # Inject Key Vault and WAF if missing
            has_kv = any("vault" in str(n.get("id")).lower() for n in nodes)
            if not has_kv:
                kv_id = f"keyvault-{int(asyncio.get_event_loop().time())}"
                updated_nodes.append({
                    "id": kv_id,
                    "type": "SecurityNode",
                    "parentNode": "subnet-mgmt",
                    "position": {"x": 250, "y": 60},
                    "data": {"label": "Key Vault (Secure)", "subnet": "subnet-mgmt", "provider": provider}
                })
        elif action == "add_monitoring":
            # Inject Monitor and Log Analytics
            has_mon = any("monitor" in str(n.get("id")).lower() for n in nodes)
            if not has_mon:
                mon_id = f"monitor-{int(asyncio.get_event_loop().time())}"
                updated_nodes.append({
                    "id": mon_id,
                    "type": "MonitoringNode",
                    "parentNode": "subnet-mgmt",
                    "position": {"x": 250, "y": 160},
                    "data": {"label": "Azure Monitor Dashboard", "subnet": "subnet-mgmt", "provider": provider}
                })
        elif action == "add_ha":
            # Inject Database replica
            has_rep = any("replica" in str(n.get("id")).lower() for n in nodes)
            db_primary = next((n for n in nodes if n.get("type") == "DatabaseNode"), None)
            if db_primary and not has_rep:
                rep_id = f"db-replica-{int(asyncio.get_event_loop().time())}"
                updated_nodes.append({
                    "id": rep_id,
                    "type": "DatabaseNode",
                    "parentNode": "subnet-data",
                    "position": {"x": 280, "y": 60},
                    "data": {"label": "Database HA Standby Replica", "subnet": "subnet-data", "provider": provider}
                })
                updated_edges.append({
                    "id": f"e-{db_primary.get('id')}-{rep_id}",
                    "source": db_primary.get("id"),
                    "target": rep_id,
                    "animated": False
                })

        return {
            "nodes": updated_nodes,
            "edges": updated_edges,
            "services": services
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
