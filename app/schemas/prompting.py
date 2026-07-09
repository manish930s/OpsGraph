from pydantic import BaseModel, Field
from typing import Any

class Message(BaseModel):
    model_config = {"frozen": True}
    role: str  # "system", "user", "assistant"
    content: str

class ModelRequest(BaseModel):
    model_config = {"frozen": True}
    request_id: str
    task_type: str  # e.g., "rca", "critic"
    prompt_template_id: str
    prompt_version: str
    system_message: str
    user_message: str
    context_references: tuple[str, ...] = Field(default_factory=tuple)  # list of CTX- IDs
    required_response_schema: str | None = Field(default=None)  # JSON schema description
    provider_preference: str | None = Field(default=None)  # "groq", "gemini", or None
    model_preference: str | None = Field(default=None)
    timeout_configuration: float = Field(default=30.0)
    retry_policy_reference: str = Field(default="default")
    request_metadata: dict[str, Any] = Field(default_factory=dict)
