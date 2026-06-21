import json
from agents.base import BaseAgent
from prompts.templates import ARCHITECTURE_REASONING_PROMPT
from typing import Dict, Any, Optional
from utils.llm_provider import AIProvider

class ArchitectureReasoningAgent(BaseAgent):
    def __init__(self, client: Optional[AIProvider] = None):
        super().__init__(
            name="ArchitectureReasoningAgent",
            system_prompt=ARCHITECTURE_REASONING_PROMPT,
            client=client
        )

    async def reason(self, understood_reqs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Intelligently decides on cloud hosting, caching, compute, and CDN nodes.
        """
        user_prompt = f"Understood Requirements:\n{json.dumps(understood_reqs, indent=2)}"
        return await self.execute(user_prompt)
