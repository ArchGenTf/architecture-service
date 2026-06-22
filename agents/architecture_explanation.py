import json
from agents.base import BaseAgent
from prompts.templates import ARCHITECTURE_EXPLANATION_PROMPT
from typing import Dict, Any, Optional
from utils.llm_provider import AIProvider


class ArchitectureExplanationAgent(BaseAgent):
    def __init__(self, client: Optional[AIProvider] = None):
        super().__init__(
            name="ArchitectureExplanationAgent",
            system_prompt=ARCHITECTURE_EXPLANATION_PROMPT,
            client=client
        )

    async def explain(self, plan: Dict[str, Any], raw_requirements: Any) -> Dict[str, Any]:
        """
        Explains architectural trade-offs and decisions.
        """
        # Handle string or dict requirements
        app_desc = ""
        sec_reqs = ""
        perf_reqs = ""
        tech_cons = ""
        cloud_prov = plan.get("cloud_provider", "azure")

        if isinstance(raw_requirements, dict):
            app_desc = raw_requirements.get("app_description", "")
            sec_reqs = raw_requirements.get(
                "security_requirements", "") or raw_requirements.get("security_level", "")
            perf_reqs = raw_requirements.get(
                "performance_requirements", "") or f"Scalability: {raw_requirements.get('scalability_preference', '')}, Availability Target: {raw_requirements.get('availability_target', '')}, RTO: {raw_requirements.get('rto', '')}, RPO: {raw_requirements.get('rpo', '')}"
            tech_cons = raw_requirements.get(
                "technical_constraints", "") or f"Budget: {raw_requirements.get('monthly_budget', '')}, Region: {raw_requirements.get('region', '')}"
            cloud_prov = raw_requirements.get("cloud_provider", cloud_prov)
        else:
            app_desc = str(raw_requirements)

        # Format system prompt with requirements
        try:
            self.system_prompt = self.system_prompt.format(
                application_description=app_desc,
                security_requirements=sec_reqs,
                performance_requirements=perf_reqs,
                technical_constraints=tech_cons,
                cloud_provider=cloud_prov
            )
        except Exception:
            pass  # Fallback to unformatted if keys mismatch

        user_prompt = (
            f"Planned Architecture:\n{json.dumps(plan, indent=2)}\n\n"
            f"Please generate the complete production-ready cloud architecture document as specified in your instructions. "
            f"Ensure your final response includes the required JSON block for the Diagram Data."
        )
        return await self.execute(user_prompt)
