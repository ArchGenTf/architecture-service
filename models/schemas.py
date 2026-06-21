from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

class RequirementInput(BaseModel):
    app_description: str
    expected_users: str
    monthly_budget: str
    cloud_provider: str
    additional_notes: Optional[str] = None
    application_type: Optional[str] = None
    scalability_preference: Optional[str] = None
    security_level: Optional[str] = None
    database_type: Optional[str] = None
    traffic_expectation: Optional[str] = None
    architecture_preference: Optional[str] = None
    projectName: Optional[str] = None
    region: Optional[str] = None
    availability_target: Optional[str] = None
    rto: Optional[str] = None
    rpo: Optional[str] = None
    resourceGroup: Optional[str] = None
    vnetCIDR: Optional[str] = None
    computeType: Optional[str] = None

    @field_validator('app_description')
    @classmethod
    def validate_app_description(cls, v: str) -> str:
        if len(v.strip()) < 15:
            raise ValueError('Application description must be at least 15 characters long to ensure adequate context.')
        return v

    @field_validator('monthly_budget')
    @classmethod
    def validate_monthly_budget(cls, v: str) -> str:
        import re
        cleaned = re.sub(r'[^\d.]', '', v)
        if not cleaned:
            raise ValueError('Monthly budget must contain a valid numeric amount.')
        try:
            val = float(cleaned)
            if val <= 0:
                raise ValueError('Monthly budget must be a positive number.')
        except ValueError:
            raise ValueError('Monthly budget must be a valid number.')
        return v

    @field_validator('cloud_provider')
    @classmethod
    def validate_cloud_provider(cls, v: str) -> str:
        provider = v.strip().lower()
        if provider not in ['aws', 'azure', 'gcp']:
            raise ValueError('Cloud provider must be one of: aws, azure, or gcp.')
        return provider


class ArchitectureResponse(BaseModel):
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]
    services: List[Dict[str, Any]]
    cloud_provider: str
    active_provider: str
    active_model: str
    fallback_trigger: str
    cost_estimate: float
    cost_breakdown: List[Any]
    optimization_recommendations: List[Any]
    complexity_score: int
    operational_overhead_score: int
    overengineered: bool
    warnings: List[Any]
    security_score: int
    security_findings: List[Any]
    compliance_checks: List[Any]
    explanation: str
    alternatives_considered: str
    justification_for_choices: str
    terraform_modules: List[str]
    execution_time_ms: int
    generation_source: Optional[str] = "deterministic+ollama"
    provider: Optional[str] = "azure"
    node_count: Optional[int] = 0
    edge_count: Optional[int] = 0
    subnet_count: Optional[int] = 0
    response_summary: Optional[Dict[str, Any]] = None
    requirement_coverage_score: Optional[int] = 100

class NodeModel(BaseModel):
    id: str
    type: Optional[str] = "default"
    data: Dict[str, Any]
    position: Optional[Dict[str, Any]] = None
    parentNode: Optional[str] = None

    model_config = {"extra": "allow"}

class EdgeModel(BaseModel):
    id: Optional[str] = None          # Auto-generated if not provided
    source: str
    target: str
    animated: Optional[bool] = False
    description: Optional[str] = None  # Present in AI-generated edges
    label: Optional[str] = None

    model_config = {"extra": "allow"}

    def model_post_init(self, __context: Any) -> None:
        # Auto-generate edge ID from source+target if not provided
        if not self.id:
            self.id = f"edge-{self.source}-{self.target}"

class ServiceModel(BaseModel):
    name: Optional[str] = ""
    category: Optional[str] = ""
    description: Optional[str] = ""

    model_config = {"extra": "allow"}

class TerraformRequest(BaseModel):
    nodes: List[NodeModel]
    edges: List[EdgeModel]
    services: Optional[List[Any]] = []
    cloud_provider: str
    force_regenerate: Optional[bool] = False

class TerraformResponse(BaseModel):
    main_tf: str
    variables_tf: str
    outputs_tf: str
    terraform_tfvars: str
    instructions: str
    warnings: Optional[List[str]] = []

class AiAssistRequest(BaseModel):
    nodes: List[NodeModel]
    edges: List[EdgeModel]
    services: Optional[List[Any]] = []
    action: str
