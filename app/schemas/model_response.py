from pydantic import BaseModel, Field
from typing import Any

class RCADecisionResponse(BaseModel):
    model_config = {"frozen": True}
    response_id: str
    task_type: str = Field(default="rca")
    summary: str
    observations: tuple[str, ...] = Field(default_factory=tuple)
    hypotheses: tuple[str, ...] = Field(default_factory=tuple)
    supporting_evidence_references: tuple[str, ...] = Field(default_factory=tuple)
    contradicting_evidence_references: tuple[str, ...] = Field(default_factory=tuple)
    knowledge_references: tuple[str, ...] = Field(default_factory=tuple)
    uncertainty_statements: tuple[str, ...] = Field(default_factory=tuple)
    recommended_next_steps: tuple[str, ...] = Field(default_factory=tuple)

class CriticDecisionResponse(BaseModel):
    model_config = {"frozen": True}
    response_id: str
    task_type: str = Field(default="critic")
    is_valid: bool
    findings: tuple[str, ...] = Field(default_factory=tuple)
    suggestions: tuple[str, ...] = Field(default_factory=tuple)

class LLMExecutionMetadata(BaseModel):
    model_config = {"frozen": True}
    request_id: str
    task_type: str
    prompt_template_id: str
    prompt_version: str
    requested_provider: str | None = None
    initial_provider: str
    final_provider: str
    model_id: str
    retry_count: int
    fallback_attempted: bool
    fallback_reason: str | None = None
    latency_ms: float
    finish_reason: str | None = None
    usage_metadata: dict[str, Any] = Field(default_factory=dict)
    input_guardrail_status: str  # "passed", "rejected", "error"
    output_guardrail_status: str  # "passed", "rejected", "error"
    schema_validation_status: str  # "passed", "failed"
    citation_validation_status: str  # "passed", "failed"
    degraded_mode: bool = False

class ValidatedModelResponse(BaseModel):
    model_config = {"frozen": True}
    response_id: str
    task_type: str
    raw_content: str
    parsed_response: Any  # Union[RCADecisionResponse, CriticDecisionResponse]
    execution_metadata: LLMExecutionMetadata
