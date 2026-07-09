from pydantic import BaseModel, Field, field_validator
from typing import Any

class RCADecisionResponse(BaseModel):
    model_config = {"frozen": True, "extra": "forbid"}
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

    @field_validator(
        "supporting_evidence_references",
        "contradicting_evidence_references",
        "knowledge_references",
        mode="before"
    )
    @classmethod
    def deduplicate_references(cls, v: Any) -> Any:
        if isinstance(v, (list, tuple)):
            seen = set()
            return tuple(x for x in v if not (x in seen or seen.add(x)))
        return v

from typing import Literal

class CriticDecisionResponse(BaseModel):
    model_config = {"frozen": True, "extra": "forbid"}
    response_id: str
    task_type: str = Field(default="critic")
    is_valid: bool
    findings: tuple[str, ...] = Field(default_factory=tuple)
    suggestions: tuple[str, ...] = Field(default_factory=tuple)
    decision: Literal["ACCEPT", "CONTINUE_INVESTIGATION", "HUMAN_REVIEW", "REJECT"] = Field(default="ACCEPT")
    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0)
    evidence_gaps: tuple[str, ...] = Field(default_factory=tuple)
    reasoning_summary: str = Field(default="")
    required_next_evidence_category: str | None = Field(default=None)

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
