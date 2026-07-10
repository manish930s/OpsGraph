from enum import Enum
from typing import Any, Literal
from datetime import datetime
from pydantic import BaseModel, Field, field_validator, model_validator

# --- EVALUATION ENUMS ---

class DatasetSplit(str, Enum):
    DEV = "dev"
    VALIDATION = "validation"
    TEST = "test"

class ScenarioAmbiguity(str, Enum):
    UNAMBIGUOUS = "unambiguous"
    PARTIALLY_AMBIGUOUS = "partially_ambiguous"
    IRREDUCIBLY_AMBIGUOUS = "irreducibly_ambiguous"

class ExpectedTerminalOutcome(str, Enum):
    FINALIZE_RCA = "finalize_rca"
    HUMAN_REVIEW = "human_review"
    FAILURE = "failure"

class EvaluationMode(str, Enum):
    METRIC_ONLY = "metric_only"
    MOCK_GRAPH = "mock_graph"
    OFFLINE_COMPONENT = "offline_component"
    LIVE = "live"

class MetricStatus(str, Enum):
    SUCCESS = "success"
    NOT_APPLICABLE = "not_applicable"
    FAILED = "failed"


# --- GOLDEN CONTRACT SCHEMAS ---

class GoldenRCALabels(BaseModel):
    affected_service: str
    fault_category: str
    root_cause_code: str
    root_cause_summary: str
    acceptable_equivalent_root_cause_codes: list[str] = Field(default_factory=list)
    forbidden_unsupported_cause_codes: list[str] = Field(default_factory=list)

    @field_validator("acceptable_equivalent_root_cause_codes", "forbidden_unsupported_cause_codes")
    @classmethod
    def reject_duplicates(cls, v: list[str]) -> list[str]:
        if v:
            seen = set()
            dups = [x for x in v if x in seen or seen.add(x)]
            if dups:
                raise ValueError(f"Duplicate values not allowed: {dups}")
        return v


class GoldenScenario(BaseModel):
    schema_version: str = Field(default="1.0")
    scenario_id: str
    incident_id: str
    split: DatasetSplit
    ambiguity: ScenarioAmbiguity
    expected_terminal_outcome: ExpectedTerminalOutcome
    acceptable_terminal_outcomes: list[ExpectedTerminalOutcome] = Field(default_factory=list)
    labels: GoldenRCALabels
    required_evidence_ids: list[str] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)
    acceptable_tools: list[str] = Field(default_factory=list)
    forbidden_tools: list[str] = Field(default_factory=list)
    acceptable_root_cause_codes: list[str] = Field(default_factory=list)
    forbidden_unsupported_causes: list[str] = Field(default_factory=list)
    acceptable_remediation_codes: list[str] = Field(default_factory=list)
    difficulty: str | None = None
    tags: list[str] = Field(default_factory=list)

    @field_validator(
        "acceptable_terminal_outcomes",
        "required_evidence_ids",
        "required_tools",
        "acceptable_tools",
        "forbidden_tools",
        "acceptable_root_cause_codes",
        "forbidden_unsupported_causes",
        "acceptable_remediation_codes",
        "tags"
    )
    @classmethod
    def reject_duplicates(cls, v: list[Any]) -> list[Any]:
        if v:
            seen = set()
            dups = [x for x in v if x in seen or seen.add(x)]
            if dups:
                raise ValueError(f"Duplicate values not allowed: {dups}")
        return v

    @model_validator(mode="after")
    def validate_terminal_outcomes(self) -> "GoldenScenario":
        if self.expected_terminal_outcome not in self.acceptable_terminal_outcomes:
            raise ValueError(
                f"expected_terminal_outcome '{self.expected_terminal_outcome}' "
                f"must be present in acceptable_terminal_outcomes: {self.acceptable_terminal_outcomes}"
            )
        return self

    @model_validator(mode="after")
    def validate_tool_categories(self) -> "GoldenScenario":
        req = set(self.required_tools)
        acc = set(self.acceptable_tools)
        forb = set(self.forbidden_tools)

        overlap_req_forb = req.intersection(forb)
        if overlap_req_forb:
            raise ValueError(f"required_tools and forbidden_tools overlap: {overlap_req_forb}")

        overlap_acc_forb = acc.intersection(forb)
        if overlap_acc_forb:
            raise ValueError(f"acceptable_tools and forbidden_tools overlap: {overlap_acc_forb}")

        return self


# --- TRACE PERSISTENCE SCHEMAS ---

class NodeTimingRecord(BaseModel):
    node_name: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: float | None = Field(default=None, ge=0.0)

    @model_validator(mode="after")
    def validate_timing_order(self) -> "NodeTimingRecord":
        if self.started_at is not None and self.finished_at is not None:
            if self.finished_at < self.started_at:
                raise ValueError(
                    f"finished_at '{self.finished_at}' cannot be earlier than started_at '{self.started_at}'"
                )
        return self


class ToolCallTraceRecord(BaseModel):
    tool_name: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    iteration: int | None = Field(default=None, ge=0)
    success: bool | None = None
    error_type: str | None = None
    evidence_ids_returned: list[str] = Field(default_factory=list)
    duration_ms: float | None = Field(default=None, ge=0.0)

    @field_validator("evidence_ids_returned")
    @classmethod
    def reject_duplicates(cls, v: list[str]) -> list[str]:
        if v:
            seen = set()
            dups = [x for x in v if x in seen or seen.add(x)]
            if dups:
                raise ValueError(f"Duplicate values not allowed: {dups}")
        return v


class CriticTraceRecord(BaseModel):
    iteration: int = Field(ge=0)
    decision: str
    confidence: float = Field(ge=0.0, le=1.0)
    is_valid: bool
    reason: str | None = None
    evidence_count_at_decision: int | None = Field(default=None, ge=0)


class EvaluationTrace(BaseModel):
    schema_version: str = Field(default="1.0")
    scenario_id: str
    investigation_id: str
    node_sequence: list[str] = Field(default_factory=list)
    node_timings: list[NodeTimingRecord] = Field(default_factory=list)
    iteration_count: int | None = Field(default=None, ge=0)
    tool_call_count: int | None = Field(default=None, ge=0)
    tool_calls: list[ToolCallTraceRecord] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    critic_records: list[CriticTraceRecord] = Field(default_factory=list)
    context_rebuild_count: int | None = Field(default=None, ge=0)
    provider_used: str | None = None
    fallback_occurrence: bool | None = None
    termination_reason: str | None = None
    final_terminal_type: str | None = None
    total_latency_ms: float | None = Field(default=None, ge=0.0)

    @field_validator("evidence_ids", "node_sequence")
    @classmethod
    def reject_duplicates(cls, v: list[Any], info: Any) -> list[Any]:
        # Duplicate nodes are allowed in sequence, but evidence IDs must be unique
        if info.field_name == "evidence_ids" and v:
            seen = set()
            dups = [x for x in v if x in seen or seen.add(x)]
            if dups:
                raise ValueError(f"Duplicate values not allowed: {dups}")
        return v


# --- RUN MANIFEST SCHEMAS ---

class EvaluationRunManifest(BaseModel):
    schema_version: str = Field(default="1.0")
    run_id: str
    evaluation_version: str
    evaluation_mode: EvaluationMode
    started_at: datetime
    finished_at: datetime | None = None
    git_commit: str | None = None
    release_tag: str | None = None
    scenario_ids: list[str] = Field(default_factory=list)
    provider: str | None = None
    generation_model: str | None = None
    embedding_model: str | None = None
    embedding_dimension: int | None = Field(default=None, ge=0)
    prompt_versions: dict[str, str] = Field(default_factory=dict)
    graph_budgets: dict[str, Any] = Field(default_factory=dict)
    retrieval_configuration: dict[str, Any] = Field(default_factory=dict)
    requested_temperature: float | None = None
    random_seed: int | None = None
    python_version: str | None = None
    platform: str | None = None

    @field_validator("scenario_ids")
    @classmethod
    def reject_duplicates(cls, v: list[str]) -> list[str]:
        if v:
            seen = set()
            dups = [x for x in v if x in seen or seen.add(x)]
            if dups:
                raise ValueError(f"Duplicate values not allowed: {dups}")
        return v


# --- METRIC ENVELOPE SCHEMAS ---

class MetricResult(BaseModel):
    metric_name: str
    status: MetricStatus
    value: float | None = None
    reason: str | None = None
    error_type: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_status_rules(self) -> "MetricResult":
        if self.status == MetricStatus.SUCCESS:
            if self.value is None:
                raise ValueError("value is required when status is SUCCESS")
            if self.error_type is not None:
                raise ValueError("error_type must be None when status is SUCCESS")
        elif self.status == MetricStatus.NOT_APPLICABLE:
            if self.value is not None:
                raise ValueError("value must be None when status is NOT_APPLICABLE")
            if not self.reason:
                raise ValueError("reason is required when status is NOT_APPLICABLE")
        elif self.status == MetricStatus.FAILED:
            if self.value is not None:
                raise ValueError("value must be None when status is FAILED")
            if not self.error_type and not self.reason:
                raise ValueError("error_type or reason must be provided when status is FAILED")
        return self


class ScenarioEvaluationResult(BaseModel):
    schema_version: str = Field(default="1.0")
    run_id: str
    scenario_id: str
    terminal_outcome: str | None = None
    metrics: list[MetricResult] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    trace: EvaluationTrace | None = None
