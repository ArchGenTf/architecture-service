import logging
from typing import Dict, Any, Optional
from utils.llm_provider import AIProvider, get_llm_provider

logger = logging.getLogger("base_agent")

class BaseAgent:
    def __init__(self, name: str, system_prompt: str, client: Optional[AIProvider] = None):
        self.name = name
        self.system_prompt = system_prompt
        self.client = client or get_llm_provider()

    async def execute(self, user_prompt: str, expected_schema: Optional[Any] = None) -> Dict[str, Any]:
        """
        Executes the agent's specific reasoning cycle.
        """
        provider_name = getattr(self.client, "provider_name", self.client.__class__.__name__)
        model_name = getattr(self.client, "model_name", "unknown")
        logger.info(f"Running agent: {self.name} | Active Provider: {provider_name} | Model Name: {model_name}")
        try:
            result = await self.client.generate_json(
                system_prompt=self.system_prompt,
                user_prompt=user_prompt,
                schema=expected_schema
            )
            return result
        except Exception as e:
            logger.error(f"Error executing agent {self.name}: {e}")
            raise e
