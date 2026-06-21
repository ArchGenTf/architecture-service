import json
from agents.base import BaseAgent
from prompts.templates import TOPOLOGY_GENERATION_PROMPT
from typing import Dict, Any, Optional, List
from utils.llm_provider import AIProvider

class TopologyGenerationAgent(BaseAgent):
    def __init__(self, client: Optional[AIProvider] = None):
        super().__init__(
            name="TopologyGenerationAgent",
            system_prompt=TOPOLOGY_GENERATION_PROMPT,
            client=client
        )

    async def generate(
        self,
        analyzed_requirements: Dict[str, Any],
        plan: Dict[str, Any],
        validation_findings: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Generates the visual React Flow topology, including nodes, edges, and service registry entries.
        Optionally accepts validation findings to correct the topology dynamically.
        """
        user_prompt = (
            f"Analyzed Requirements:\n{json.dumps(analyzed_requirements, indent=2)}\n\n"
            f"Architecture Plan:\n{json.dumps(plan, indent=2)}"
        )

        if validation_findings:
            user_prompt += (
                f"\n\nCRITICAL: The previous topology failed validation. "
                f"You MUST correct all of the following validation findings in the new topology:\n"
                + "\n".join(f"- {finding}" for finding in validation_findings)
            )

        return await self.execute(user_prompt)
