from agents.base import BaseAgent
from prompts.templates import REQUIREMENT_ANALYSIS_PROMPT
from models.schemas import RequirementInput
from typing import Dict, Any, Optional
from utils.llm_provider import AIProvider

class RequirementAnalysisAgent(BaseAgent):
    def __init__(self, client: Optional[AIProvider] = None):
        super().__init__(
            name="RequirementAnalysisAgent",
            system_prompt=REQUIREMENT_ANALYSIS_PROMPT,
            client=client
        )

    async def analyze(self, requirements: RequirementInput) -> Dict[str, Any]:
        """
        Analyzes raw user requirements.
        """
        user_prompt = (
            f"Project Name: {requirements.projectName or 'None'}\n"
            f"Deployment Region: {requirements.region or 'None'}\n"
            f"Resource Group: {requirements.resourceGroup or 'None'}\n"
            f"VNet CIDR: {requirements.vnetCIDR or 'None'}\n"
            f"Compute Type: {requirements.computeType or 'None'}\n"
            f"Availability Target SLA: {requirements.availability_target or 'None'}\n"
            f"RTO Target: {requirements.rto or 'None'}\n"
            f"RPO Target: {requirements.rpo or 'None'}\n"
            f"Application Description: {requirements.app_description}\n"
            f"Application Type: {requirements.application_type}\n"
            f"Expected Users: {requirements.expected_users}\n"
            f"Cloud Provider: {requirements.cloud_provider}\n"
            f"Monthly Budget: {requirements.monthly_budget}\n"
            f"Scalability Preference: {requirements.scalability_preference}\n"
            f"Security Level: {requirements.security_level}\n"
            f"Database Type: {requirements.database_type}\n"
            f"Traffic Expectation: {requirements.traffic_expectation}\n"
            f"Architecture Preference: {requirements.architecture_preference}\n"
            f"Additional Notes: {requirements.additional_notes or 'None'}"
        )
        return await self.execute(user_prompt)
