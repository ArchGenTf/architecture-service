import os
import json
import logging
from typing import Dict, Any, Optional
from dotenv import load_dotenv
from utils.safe_json_parser import SafeJsonParser

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("openai_client")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4o-mini")

class OpenAIClient:
    def __init__(self):
        self.api_key = OPENAI_API_KEY
        self.model = MODEL_NAME
        self.client = None
        
        if self.api_key and not self.api_key.startswith("your_") and len(self.api_key) > 5:
            try:
                from openai import AsyncOpenAI
                self.client = AsyncOpenAI(api_key=self.api_key)
                logger.info(f"OpenAI AsyncClient initialized with model: {self.model}")
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI client: {e}. OpenAI provider will be skipped.")
                self.client = None
        else:
            logger.warning("OPENAI_API_KEY not set or invalid. OpenAI provider is unavailable.")

    async def generate_json(self, system_prompt: str, user_prompt: str, schema: Optional[Any] = None) -> Dict[str, Any]:
        """
        Generates a JSON response from OpenAI.
        """
        if not self.client:
            raise RuntimeError("OpenAI unavailable: API key missing or invalid")

        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]

            response_format = {"type": "json_object"}

            logger.info(f"Sending request to OpenAI using {self.model}...")
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                response_format=response_format,
                temperature=0.2,
                max_tokens=16000
            )

            content = response.choices[0].message.content
            finish_reason = response.choices[0].finish_reason
            logger.info(f"Successfully received response from OpenAI. Finish reason: {finish_reason}. Content length: {len(content) if content else 0}")
            if not content or content.strip() in ("{}", ""):
                logger.error(f"OpenAI returned empty or trivial response. Raw content: {repr(content[:500] if content else '')}")
                return {}
            result = SafeJsonParser.parse(content)
            # If the result only has one key and its value is a list/dict, unwrap it
            if isinstance(result, dict) and len(result) == 1:
                only_val = next(iter(result.values()))
                if isinstance(only_val, (list, dict)) and not any(k in result for k in ["nodes", "edges", "services"]):
                    logger.info(f"Unwrapping single-key wrapper response. Keys: {list(result.keys())}")
                    return only_val
            return result

        except Exception as e:
            logger.error(f"OpenAI API call failed: {e}")
            raise RuntimeError(f"OpenAI request failed: {e}") from e

    @staticmethod
    def _generate_mock_response(system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        """
        Generates realistic architecture, cost, security, complexity, and HCL parameters
        by scanning description keywords inside user prompts.
        """
        logger.info("Mock engine running descriptive text intelligence scan...")
        
        def extract_json_from_text(text: str) -> Dict[str, Any]:
            try:
                start = text.find('{')
                end = text.rfind('}')
                if start != -1 and end != -1:
                    return json.loads(text[start:end+1])
            except Exception:
                pass
            return {}

        lower_prompt = user_prompt.lower()
        req_data = extract_json_from_text(user_prompt)
        
        # 1. Infer application profiles
        is_banking = "bank" in lower_prompt or "finance" in lower_prompt or "transaction" in lower_prompt
        is_streaming = "stream" in lower_prompt or "ott" in lower_prompt or "video" in lower_prompt or "media" in lower_prompt
        is_crud = "crud" in lower_prompt or "blog" in lower_prompt or "simple" in lower_prompt or "portfolio" in lower_prompt
        is_high_scale = "1m" in lower_prompt or "100k" in lower_prompt or "million" in lower_prompt or "high" in lower_prompt
        
        provider = "azure"
        if "aws" in lower_prompt:
            provider = "aws"
        elif "gcp" in lower_prompt:
            provider = "gcp"

        if req_data:
            if "cloud_provider" in req_data:
                provider = str(req_data["cloud_provider"]).lower()
            elif "provider" in req_data:
                provider = str(req_data["provider"]).lower()
                
            app_desc = str(req_data.get("app_description") or req_data.get("appDescription") or "").lower()
            if app_desc:
                is_banking = "bank" in app_desc or "finance" in app_desc or "transaction" in app_desc
                is_streaming = "stream" in app_desc or "ott" in app_desc or "video" in app_desc or "media" in app_desc
                is_crud = "crud" in app_desc or "blog" in app_desc or "simple" in app_desc or "portfolio" in app_desc
            
            users = str(req_data.get("expected_users") or "").lower()
            if users:
                is_high_scale = "1m" in users or "100k" in users or "million" in users or "high" in users

        # A. Requirement Understanding Mock
        if any(k in system_prompt.lower() for k in ["requirementunderstandingagent", "requirement understanding", "requirementanalysisagent", "requirement analysis", "analyze requirements", "understand requirements"]):
            reqs = [
                f"Design a highly responsive architecture on {provider.upper()}.",
                "Intelligently map database and hosting systems."
            ]
            if is_banking:
                reqs.append("Enforce maximum vault security encryptions.")
                reqs.append("Deploy active WAF controllers to intercept transaction routes.")
            if is_streaming:
                reqs.append("Deploy CDN gateways for media streaming endpoints.")
                reqs.append("Implement Redis caching to optimize throughput latency.")
            if is_crud:
                reqs.append("Deploy a cost-efficient lightweight VM or App Service container.")
                
            projectName = req_data.get("projectName") or req_data.get("project_name") or "Enterprise Stack"
            region = req_data.get("region") or "East US"
            resourceGroup = req_data.get("resourceGroup") or req_data.get("resource_group") or "rg-production"
            vnetCIDR = req_data.get("vnetCIDR") or req_data.get("vnet_cidr") or "10.0.0.0/16"
            computeType = req_data.get("computeType") or req_data.get("compute_type") or req_data.get("application_type") or "AKS"
            databaseType = req_data.get("database_type") or req_data.get("databaseType") or "PostgreSQL"
            app_description = req_data.get("app_description") or req_data.get("appDescription") or user_prompt

            return {
                "projectName": projectName,
                "region": region,
                "resourceGroup": resourceGroup,
                "vnetCIDR": vnetCIDR,
                "computeType": computeType,
                "database_type": databaseType,
                "app_description": app_description,
                "expected_users": "1M monthly" if is_high_scale else "10k monthly",
                "monthly_budget": "500" if is_high_scale else "50",
                "cloud_provider": provider,
                "inferred_scale_level": "high" if is_high_scale else "low",
                "extracted_requirements": reqs
            }
            
        # B. Architecture Reasoning / Planning Mock
        elif any(k in system_prompt.lower() for k in ["architectureplanningagent", "architecture planning", "architecturereasoningagent", "architecture reasoning", "reason architecture", "visual topology graph", "you are an expert cloud architect"]):
            from utils.reasoning_engine import InfrastructureReasoningEngine
            
            class DummyRequirements:
                def __init__(self, data):
                    self.projectName = data.get("projectName") or data.get("project_name") or "Enterprise Stack"
                    self.region = data.get("region") or "East US"
                    self.resourceGroup = data.get("resourceGroup") or data.get("resource_group") or "rg-production"
                    self.vnetCIDR = data.get("vnetCIDR") or data.get("vnet_cidr") or "10.0.0.0/16"
                    self.computeType = data.get("computeType") or data.get("compute_type") or data.get("application_type") or "AKS"
                    self.database_type = data.get("database_type") or data.get("databaseType") or "PostgreSQL"
                    self.app_description = data.get("app_description") or data.get("appDescription") or ""
                    self.expected_users = data.get("expected_users") or "10k monthly"
                    self.monthly_budget = data.get("monthly_budget") or "50"
            
            dummy_req = DummyRequirements(req_data)
            engine = InfrastructureReasoningEngine(cloud_provider=provider, requirements=dummy_req)
            raw_topo = engine.synthesize_from_intent()
            topo = engine.normalize_topology(raw_topo)
            
            return {
                "nodes": topo.get("nodes", []),
                "edges": topo.get("edges", []),
                "services": topo.get("services", []),
                "cloud_provider": provider
            }
            
        # C. Security Optimization Mock
        elif any(k in system_prompt.lower() for k in ["securityoptimizationagent", "security optimization", "optimize security", "securityvalidationagent", "security validation", "validate security"]):
            topo = req_data.get("current_topology") or req_data or {}
            nodes = topo.get("nodes") or topo.get("updated_nodes") or []
            edges = topo.get("edges") or topo.get("updated_edges") or []
            
            findings = [
                {"severity": "Low", "description": "Redirect all public HTTP traffic to secure HTTPS channels.", "remediation": "Set force_ssl = true."}
            ]
            score = 80
            
            if is_banking:
                findings.append({"severity": "High", "description": "Highly secure financial nodes require strict vault access controls.", "remediation": "Inject keys into container app environments."})
                score = 98
                
            return {
                "updated_nodes": nodes,
                "updated_edges": edges,
                "security_findings": findings,
                "compliance_checks": [
                    {"standard": "SOC2", "status": "Compliant", "notes": "Logging active"},
                    {"standard": "PCI-DSS", "status": "Compliant" if is_banking else "Partially Compliant", "notes": "Secure bindings active."}
                ],
                "security_score": score
            }
            
        # D. Complexity Auditor Mock
        elif any(k in system_prompt.lower() for k in ["complexityauditoragent", "complexity auditor", "audit complexity"]):
            is_overengineered = False
            warnings = []
            
            if is_crud and ("kubernetes" in lower_prompt or "aks" in lower_prompt or "k8s" in lower_prompt):
                is_overengineered = True
                warnings.append("Kubernetes container clusters selected for simple CRUD apps introduce excessive operational overhead.")
            if "service mesh" in lower_prompt:
                is_overengineered = True
                warnings.append("Service meshes are highly complex and likely unnecessary for this scale.")
                
            if not warnings:
                warnings.append("Basic networking is isolated within private subnet scopes.")
                
            return {
                "complexity_score": 90 if is_overengineered else 35,
                "overengineered": is_overengineered,
                "warnings": warnings,
                "operational_overhead_score": 85 if is_overengineered else 25
            }
            
        # E. Cost Optimization Mock
        elif any(k in system_prompt.lower() for k in ["costoptimizationagent", "cost optimization", "optimize cost"]):
            cost = 45.00
            breakdown = [
                {"service": "Core VM instances", "cost": 25.00, "reason": "Standard compute instances"},
                {"service": "Relational DB storage", "cost": 20.00, "reason": "Flexible DB engine"}
            ]
            
            if is_streaming or is_high_scale:
                cost = 420.00
                breakdown = [
                    {"service": "Secure Load Balancer / WAF", "cost": 60.00, "reason": "API WAF ingress tier"},
                    {"service": "Active Container Replicas", "cost": 150.00, "reason": "Scale container app engines"},
                    {"service": "PostgreSQL HA database", "cost": 125.00, "reason": "Managed redundant transactional DB"},
                    {"service": "Redis Cache node", "cost": 45.00, "reason": "In-memory caching"},
                    {"service": "Blob Storage CDN", "cost": 40.00, "reason": "Static content delivery edge networks"}
                ]
                
            return {
                "estimated_monthly_cost": cost,
                "cost_breakdown": breakdown,
                "optimization_recommendations": [
                    "Scale compute engines to zero during off-peak hours.",
                    "Configure auto-scaling boundaries on databases to save active memory."
                ],
                "cost_score": 90 if is_crud else 65
            }

        # F. Architecture Explanation Mock
        elif any(k in system_prompt.lower() for k in ["architectureexplanationagent", "architecture explanation", "explain architecture", "reason architecture", "senior cloud architect"]):
            expl = "A lightweight cost-efficient monolith hosting client SPA and relational database instances."
            alt = "Considered microservices, but rejected to avoid operations overhead."
            just = "Optimizes active developer velocity for simple MVP workloads."
            
            if is_streaming or is_high_scale:
                expl = "A highly scalable active-active container app system, with caching layers, blob static files storage, and secure WAF gateway routing."
                alt = "Considered serverless functions, but rejected to prevent cold-starts and maintain continuous media streaming pipeline bindings."
                just = "Delivers absolute sub-second delivery latencies for global streaming clients."
                
            return {
                "explanation": expl,
                "alternatives_considered": alt,
                "justification_for_choices": just
            }

        return {}
