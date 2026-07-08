import json
from app.schemas.prompting import ModelRequest
from app.services.guardrails.base import OutputGuard
from app.services.gateway.errors import GuardrailRejectedError, CitationValidationError

class DeterministicOutputGuard(OutputGuard):
    """
    Applies strict citation map validation and structured format safety checks on the raw model output.
    """
    def evaluate(self, content: str, request: ModelRequest) -> None:
        if not content:
            raise GuardrailRejectedError("Output evaluation rejected: response content is empty.")

        # 1. Verify JSON validity
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as e:
            raise GuardrailRejectedError(f"Output evaluation rejected: invalid JSON format returned: {str(e)}")

        # 2. Schema-specific citation reference checking
        # Only validate if this request includes context references (e.g. RCA task)
        if request.context_references:
            valid_citations = set(request.context_references)
            
            # Keys that contain lists of citation references
            citation_keys = [
                "supporting_evidence_references",
                "contradicting_evidence_references",
                "knowledge_references"
            ]
            
            for key in citation_keys:
                refs = parsed.get(key, [])
                if isinstance(refs, (list, tuple)):
                    for ref in refs:
                        if ref not in valid_citations:
                            raise CitationValidationError(
                                f"Output validation failed: Hallucinated citation ID '{ref}' in key '{key}' "
                                f"is not present in the supplied InvestigationContext."
                            )
                elif refs is not None:
                    raise GuardrailRejectedError(f"Output key '{key}' must be a list of references.")
                    
        # 3. Simple length sanity check
        if len(content) > 100000:
            raise GuardrailRejectedError("Output validation rejected: response size exceeds allowed limits.")
