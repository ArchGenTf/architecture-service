import json
from agents.base import BaseAgent
from prompts.templates import SECURITY_OPTIMIZATION_PROMPT
from typing import Dict, Any, Optional
from utils.llm_provider import AIProvider

class SecurityOptimizationAgent(BaseAgent):
    def __init__(self, client: Optional[AIProvider] = None):
        super().__init__(
            name="SecurityOptimizationAgent",
            system_prompt=SECURITY_OPTIMIZATION_PROMPT,
            client=client
        )

    async def optimize_security(self, plan: Dict[str, Any], raw_requirements: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enforces maximum vault security, WAF inclusions, and network subnets.
        """
        user_prompt = (
            f"Reasoned Architecture:\n{json.dumps(plan, indent=2)}\n\n"
            f"Understood Requirements:\n{json.dumps(raw_requirements, indent=2)}"
        )
        return await self.execute(user_prompt)
