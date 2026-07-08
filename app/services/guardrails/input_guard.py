import re
from app.schemas.prompting import ModelRequest
from app.services.guardrails.base import InputGuard
from app.services.gateway.errors import GuardrailRejectedError

class DeterministicInputGuard(InputGuard):
    """
    Applies strict deterministic safety validation checks to the ModelRequest.
    """
    def evaluate(self, request: ModelRequest) -> None:
        if not request:
            raise GuardrailRejectedError("Input request object is missing.")

        # 1. Approved template validation
        approved_templates = {"investigation", "critic"}
        if request.prompt_template_id not in approved_templates:
            raise GuardrailRejectedError(
                f"Unauthorized prompt template: '{request.prompt_template_id}' is not in approved list."
            )

        # 2. Secret Leak Detection (common patterns)
        secret_patterns = [
            r"(?i)api[-_]?key\s*[:=]\s*[a-zA-Z0-9_\-\.]{16,}",
            r"(?i)bearer\s+[a-zA-Z0-9_\-\.]{16,}",
            r"(?i)secret[-_]?key\s*[:=]\s*[a-zA-Z0-9_\-\.]{16,}",
        ]
        combined = f"{request.system_message}\n{request.user_message}"
        for pattern in secret_patterns:
            if re.search(pattern, combined):
                raise GuardrailRejectedError(
                    "Input validation rejected: potential credential leak detected in the prompt content."
                )

        # 3. Context constraints
        if not request.context_references and request.prompt_template_id == "investigation":
            raise GuardrailRejectedError("Input validation rejected: context references cannot be empty for RCA tasks.")
