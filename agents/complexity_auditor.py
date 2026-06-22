import json
from agents.base import BaseAgent
from prompts.templates import COMPLEXITY_AUDITOR_PROMPT
from typing import Dict, Any, Optional
from utils.llm_provider import AIProvider


class ComplexityAuditorAgent(BaseAgent):
    def __init__(self, client: Optional[AIProvider] = None):
        super().__init__(
            name="ComplexityAuditorAgent",
            system_prompt=COMPLEXITY_AUDITOR_PROMPT,
            client=client
        )

    async def audit(self, plan: Dict[str, Any], raw_requirements: Dict[str, Any]) -> Dict[str, Any]:
        """
        Audits architecture complexity and flags overengineering.
        """
        user_prompt = (
            f"Planned Architecture:\n{json.dumps(plan, indent=2)}\n\n"
            f"Raw User Requirements:\n{json.dumps(raw_requirements, indent=2)}"
        )
        return await self.execute(user_prompt)
