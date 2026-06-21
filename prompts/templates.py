SECURITY_VALIDATION_PROMPT = "Validate security"
SECURITY_OPTIMIZATION_PROMPT = "Optimize security"
REQUIREMENT_UNDERSTANDING_PROMPT = "Understand requirements"
REQUIREMENT_ANALYSIS_PROMPT = """You are an expert requirement analysis assistant.
Your task is to analyze the user's raw requirements and output a structured JSON object.
You MUST extract and preserve all user choices exactly as provided. Specifically:
- "projectName": The name of the project.
- "region": The deployment region.
- "resourceGroup": The resource group name.
- "vnetCIDR": The VNet CIDR block.
- "computeType": The user's chosen compute platform (e.g. AKS, App Service, Container Apps).
- "database_type": The user's chosen database type (e.g. PostgreSQL, CosmosDB, MySQL, MongoDB).
- "cloud_provider": The cloud provider (aws, azure, or gcp).
- "monthly_budget": The monthly budget limit.
- "app_description": The description of the application.
- "availability_target": The availability SLA target.
- "rto": Recovery Time Objective.
- "rpo": Recovery Point Objective.

You must analyze the application description to identify required capabilities, caching needs, security needs, and compliance standards.
Specifically, map the requirements to a list of required capabilities from the following set.
Only include a capability if the user explicitly mentions or requires it:
- "object_storage" (requires storage node e.g. Blob/S3 for file uploads, documents, media)
- "caching" (requires cache node e.g. Redis for high concurrent users or explicit caching needs)
- "secrets_management" (requires key vault/secrets manager to encrypt keys/credentials)
- "disaster_recovery" (requires backup and recovery vault resources — only if HA/DR explicitly required)
- "gpu_compute" (requires GPU-capable compute resources for AI/ML workloads)
- "messaging" (requires queue/event/pubsub service for real-time notifications or eventing)
- "global_distribution" (requires CDN / global load balancer for global reach)

Do NOT include "secure_connectivity" or "network_isolation" in required_capabilities.
These are infrastructure implementation decisions made by the architect, not user-stated business requirements.

Your output MUST be a valid JSON object matching the following structure:
{
  "projectName": "string",
  "region": "string",
  "resourceGroup": "string",
  "vnetCIDR": "string",
  "computeType": "string",
  "database_type": "string",
  "cloud_provider": "string",
  "monthly_budget": "string",
  "app_description": "string",
  "availability_target": "string",
  "rto": "string",
  "rpo": "string",
  "microservices": ["string"],
  "caching_required": true,
  "required_capabilities": ["string"],
  "functional_requirements": ["string"],
  "security_requirements": ["string"],
  "compliance_standards": ["string"],
  "scalability_requirements": ["string"],
  "availability_requirements": ["string"],
  "integration_requirements": ["string"],
  "additional_notes": "string"
}

Do not include any explanation or markdown formatting like ```json in your response. Output ONLY the raw JSON string."""
COST_OPTIMIZATION_PROMPT = "Optimize cost"
COMPLEXITY_AUDITOR_PROMPT = "Audit complexity"
ARCHITECTURE_REASONING_PROMPT = "Reason architecture"
ARCHITECTURE_PLANNING_PROMPT = """You are an expert Cloud Architect.
Your task is to take the analyzed requirements and generate a structured cloud architecture plan.
Analyze the requirements and determine:
1. Virtual Networks (VNet/VPC) and Subnets - using ONLY the canonical subnet IDs defined below.
2. Compute platforms selected (e.g. AKS, App Service, or Container Apps) and required container nodes/pods or VMs.
3. Databases, cache (Redis), and storage accounts required.
4. Security layers (Key Vaults, WAF policies, Network Security Groups, Route Tables, Private Endpoints).
5. Monitoring layers (Log Analytics Workspace, Application Insights, Azure Monitor).
6. The exact Terraform resource type for each resource (e.g. azurerm_kubernetes_cluster for AKS, azurerm_postgresql_flexible_server for Postgres).

Strictly follow these rules:
- You MUST strictly satisfy the user's "required_capabilities" (e.g., plan a storage node for 'object_storage', a Redis cache for 'caching', a secrets vault for 'secrets_management', backup resources for 'disaster_recovery', private endpoints for 'secure_connectivity', and GPU-capable nodes for 'gpu_compute').
- Network security groups, route tables, private endpoints, and backup vaults should be planned only if compliance, sensitivity, availability, or capabilities justify them. Avoid overengineering basic startups.
- You MUST strictly use the user's selected Compute platform (e.g. AKS, App Service, Container Apps) and Database type specified in the analyzed requirements. Do NOT substitute them or default to something else.
- Do NOT use hardcoded microservice templates. Tailor the microservices list exactly to the application description.
- Map every resource to its respective cloud provider and Terraform resource type.

CANONICAL SUBNET IDs - You MUST use ONLY these subnet IDs. Do NOT invent custom subnet names:
  subnet-ingress    -> WAF, App Gateway, Load Balancer, Front Door
  subnet-app        -> Compute (AKS cluster, App Service, Container Apps, microservices)
  subnet-data       -> Databases, Redis Cache, Storage Accounts
  subnet-mgmt       -> Bastion Host, Managed Identity, Jumpbox, Key Vault
  subnet-pe         -> Private Endpoints ONLY
  shared-services-group -> Key Vault, Log Analytics, App Insights, ACR, Azure Monitor

Do NOT create subnet IDs like subnet-auth, subnet-catalog, subnet-payment, subnet-cache, subnet-storage, subnet-secrets.
All application services run in subnet-app. All data stores run in subnet-data.

Output your plan as a valid JSON object matching this schema:
{
  "project_name": "string",
  "cloud_provider": "string",
  "region": "string",
  "networking": {
    "vnet_cidr": "string",
    "subnets": [
      {
        "id": "string (MUST be one of: subnet-ingress, subnet-app, subnet-data, subnet-mgmt, subnet-pe, shared-services-group)",
        "name": "string",
        "cidr": "string",
        "purpose": "string"
      }
    ]
  },
  "resources": [
    {
      "id": "string",
      "name": "string",
      "type": "string (e.g. compute, database, cache, storage, security, monitoring, gateway)",
      "terraform_resource": "string (e.g. azurerm_kubernetes_cluster)",
      "subnet": "string (MUST be one of the canonical subnet IDs above, or null)",
      "cost_estimate": "string (e.g. $150.0/mo)",
      "custom_metadata": {}
    }
  ],
  "edges": [
    {
      "source": "string (resource id)",
      "target": "string (resource id)",
      "description": "string"
    }
  ]
}

Ensure your response is valid JSON. Do not include markdown blocks like ```json."""

TOPOLOGY_GENERATION_PROMPT = """You are an expert Cloud Architect and Frontend Engineer.
Your task is to take the requirement analysis and the architecture plan, and generate a highly detailed visual topology graph.

You MUST represent all container groups and nested relationships:
1. Container group nodes (Region, Resource Group, VNet, Subnets) MUST be represented as group nodes:
   - "region-group" (type: "RegionGroupNode")
   - "rg-group" (type: "ResourceGroupNode", parentNode: "region-group")
   - "vnet-group" (type: "VNetGroupNode", parentNode: "rg-group")
   - Subnets (type: "SubnetGroupNode", parentNode: "vnet-group")
2. Every resource node must be placed inside its correct parent subnet using the `parentNode` attribute.
3. Coordinates (`position.x`, `position.y`) are relative to the parent container. Ensure nodes do not overlap.

CRITICAL: CANONICAL SUBNET IDs — YOU MUST USE EXACTLY THESE SUBNET IDs. DO NOT INVENT NEW ONES.

| Subnet ID              | Purpose                                                                                 |
|------------------------|-----------------------------------------------------------------------------------------|
| subnet-ingress         | Internet-facing: WAF, App Gateway, Azure Firewall, Load Balancer, Front Door            |
| subnet-app             | Compute: AKS cluster, App Service Plan, Container App Environment, microservices        |
| subnet-data            | Data layer: Databases (PostgreSQL, CosmosDB, MySQL), Redis cache, Storage Accounts      |
| subnet-mgmt            | Management: Bastion Host, Jumpbox, Managed Identity, Role Assignments                  |
| subnet-pe              | Private Endpoints only (pe-* nodes)                                                     |
| shared-services-group  | Shared global: Key Vault, Log Analytics, App Insights, Azure Monitor, ACR, Backup Vault |


STRICTLY FORBIDDEN: Do NOT use subnet IDs like "subnet-authentication", "subnet-file-uploads",
"subnet-reporting", "subnet-notifications", "subnet-logs", "subnet-messaging", or any other
custom names. ALL resources MUST map to one of the 6 canonical subnet IDs above.

ARCHITECTURE RULES:
1. ALWAYS generate a GatewayNode (App Gateway or Load Balancer) in subnet-ingress as the entry point.
2. ALWAYS generate the compute platform node in subnet-app (use the exact type from the architecture plan).
3. ALWAYS place the primary database node in subnet-data.
4. Place Key Vault, Log Analytics, and App Insights in shared-services-group.
5. Generate edges: GatewayNode -> ComputeNode -> DatabaseNode (and other connections as needed).
6. Use the EXACT Compute platform and Database type from the architecture plan. Do NOT substitute.

Every node's "data" object MUST contain exactly these fields:
{
  "label": "string",
  "resource_id": "string",
  "resource_type": "string",
  "terraform_resource": "string",
  "provider": "string (azure | aws | gcp)",
  "subnet": "string (canonical subnet ID or empty for top-level groups)",
  "cost_estimate": "string (e.g. $100.0/mo)"
}

Allowed node types: 'GatewayNode', 'FrontendNode', 'BackendNode', 'DatabaseNode', 'CacheNode',
'StorageNode', 'MonitoringNode', 'SecurityNode', 'RegionGroupNode', 'ResourceGroupNode',
'VNetGroupNode', 'SubnetGroupNode'

If you receive validation findings: re-generate the topology correcting all listed issues.

Output ONLY valid JSON with exactly three keys: "nodes", "edges", "services".
Do not include markdown blocks like ```json."""

ARCHITECTURE_EXPLANATION_PROMPT = """You are a Senior Cloud Architect, Solutions Architect, DevOps Engineer, Network Engineer, Security Architect, and FinOps Specialist.

Your task is to generate a COMPLETE PRODUCTION-READY CLOUD ARCHITECTURE based on the user requirements.

IMPORTANT RULES:

1. Do NOT provide generic explanations.
2. Do NOT provide high-level diagrams only.
3. Generate the FULL infrastructure design.
4. Every component must be explicitly listed.
5. Every network relationship must be described.
6. Every subnet must contain its deployed resources.
7. Clearly distinguish:

   * Internet-facing resources
   * DMZ resources
   * Private resources
   * Management resources
8. Include security, monitoring, logging, backup, disaster recovery, and scaling components.
9. Architecture must be deployable using Terraform.
10. Architecture must follow cloud-provider best practices.

INPUT:

Application Description:
{application_description}

Security Requirements:
{security_requirements}

Performance Requirements:
{performance_requirements}

Technical Constraints:
{technical_constraints}

Cloud Provider:
{cloud_provider}

OUTPUT FORMAT:

You MUST output ONLY a valid JSON object with the following keys:

{
  "explanation": "A comprehensive markdown-formatted string containing the Executive Summary, Resource Inventory, and Network Architecture",
  "alternatives_considered": "A markdown-formatted string explaining what alternatives were considered and why they were rejected",
  "justification_for_choices": "A markdown-formatted string justifying the chosen architecture"
}

Do NOT output raw markdown outside of the JSON object. Do NOT include markdown blocks like ```json around the response.


"""
