import re
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

        # 2. Extract and check all citation references in the JSON body against ModelRequest
        valid_citations = set(request.context_references or ())
        
        # Scan entire raw content string for any [CTX-...] pattern to catch hidden hallucinations
        citations_found = re.findall(r"\[(CTX-[a-zA-Z0-9_\-]+)\]", content)
        for citation in citations_found:
            if citation not in valid_citations:
                raise CitationValidationError(
                    f"Output validation failed: Hallucinated citation ID '{citation}' found in text "
                    f"is not present in the supplied InvestigationContext."
                )

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
                            f"Output validation failed: Hallucinated citation ID '{ref}' in list '{key}' "
                            f"is not present in the supplied InvestigationContext."
                        )
            elif refs is not None:
                raise GuardrailRejectedError(f"Output key '{key}' must be a list of references.")

        # 3. Policy on empty citations vs uncertainty-only responses
        if request.task_type == "rca":
            has_observations = bool(parsed.get("observations"))
            has_evidence = bool(parsed.get("supporting_evidence_references"))
            has_uncertainty = bool(parsed.get("uncertainty_statements"))
            
            if not has_observations and not has_evidence and not has_uncertainty:
                raise CitationValidationError(
                    "Output validation failed: RCA response must contain either observations/supporting evidence "
                    "references, or uncertainty statements (uncertainty-only response)."
                )

        # 4. Simple length sanity check
        if len(content) > 100000:
            raise GuardrailRejectedError("Output validation rejected: response size exceeds allowed limits.")
