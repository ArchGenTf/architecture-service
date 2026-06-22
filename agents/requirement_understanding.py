from agents.base import BaseAgent
from prompts.templates import REQUIREMENT_UNDERSTANDING_PROMPT
from models.schemas import RequirementInput
from typing import Dict, Any, Optional
from utils.llm_provider import AIProvider


class RequirementUnderstandingAgent(BaseAgent):
    def __init__(self, client: Optional[AIProvider] = None):
        super().__init__(
            name="RequirementUnderstandingAgent",
            system_prompt=REQUIREMENT_UNDERSTANDING_PROMPT,
            client=client
        )

    async def analyze(self, requirements: RequirementInput) -> Dict[str, Any]:
        """
        Parses simplified user specifications.
        """
        user_prompt = (
            f"Expected Users: {requirements.expected_users}\n"
            f"Monthly Budget: {requirements.monthly_budget}\n"
            f"Cloud Provider: {requirements.cloud_provider}\n"
            f"Detailed App Description: {requirements.app_description}\n"
            f"Additional Notes: {requirements.additional_notes or 'None'}"
        )
        return await self.execute(user_prompt)
