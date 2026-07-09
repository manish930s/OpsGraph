from app.schemas.evidence import EvidenceBundle
from app.schemas.knowledge import KnowledgeBundle
from app.services.context.exceptions import ContextValidationError, ContextScopeMismatchError

class InputValidator:
    """
    Validates scenario consistency, incident consistency, and model integrity
    between input EvidenceBundle and KnowledgeBundle.
    """
    @staticmethod
    def validate(evidence_bundle: EvidenceBundle, knowledge_bundle: KnowledgeBundle | None) -> None:
        if not evidence_bundle:
            raise ContextValidationError("Evidence bundle is required.")

        ev_list = evidence_bundle.evidence_list
        if not ev_list:
            raise ContextValidationError("Evidence list is empty.")

        # Verify incident and scenario consistency across all evidence items
        first_incident = ev_list[0].incident_id
        first_scenario = ev_list[0].scenario_id

        if not first_incident:
            raise ContextValidationError("Incident ID is missing in evidence.")
        if not first_scenario:
            raise ContextValidationError("Scenario ID is missing in evidence.")

        for ev in ev_list:
            if ev.incident_id != first_incident:
                raise ContextScopeMismatchError(
                    f"Mismatched incident IDs in evidence bundle: '{ev.incident_id}' vs '{first_incident}'"
                )
            if ev.scenario_id != first_scenario:
                raise ContextScopeMismatchError(
                    f"Mismatched scenario IDs in evidence bundle: '{ev.scenario_id}' vs '{first_scenario}'"
                )

        # Validate Knowledge Bundle if present
        if knowledge_bundle:
            kb_scenario = knowledge_bundle.metadata.get("scenario_id")
            if kb_scenario and kb_scenario != first_scenario:
                raise ContextScopeMismatchError(
                    f"Mismatched scenario between EvidenceBundle ({first_scenario}) and KnowledgeBundle ({kb_scenario})"
                )

            # Validate that every evidence reference resolves to a valid evidence item
            valid_evidence_ids = {ev.evidence_id for ev in ev_list}
            if knowledge_bundle.evidence_references:
                seen_refs = set()
                for ref in knowledge_bundle.evidence_references:
                    if not ref:
                        raise ContextValidationError("Malformed empty evidence reference found in KnowledgeBundle.")
                    if ref in seen_refs:
                        raise ContextValidationError(f"Duplicate evidence reference found in KnowledgeBundle: '{ref}'")
                    seen_refs.add(ref)
                    if ref not in valid_evidence_ids:
                        raise ContextValidationError(
                            f"Orphan knowledge evidence reference: '{ref}' is not present in EvidenceBundle."
                        )
