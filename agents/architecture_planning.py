import json
from agents.base import BaseAgent
from prompts.templates import ARCHITECTURE_PLANNING_PROMPT
from typing import Dict, Any, Optional
from utils.llm_provider import AIProvider

class ArchitecturePlanningAgent(BaseAgent):
    def __init__(self, client: Optional[AIProvider] = None):
        super().__init__(
            name="ArchitecturePlanningAgent",
            system_prompt=ARCHITECTURE_PLANNING_PROMPT,
            client=client
        )

    async def plan(self, analyzed_requirements: Dict[str, Any]) -> Dict[str, Any]:
        """
        Plans the visual canvas architecture components.
        """
        user_prompt = f"Analyzed Requirements:\n{json.dumps(analyzed_requirements, indent=2)}"
        return await self.execute(user_prompt)
