from app.schemas.evidence import Evidence
from app.schemas.knowledge import KnowledgeChunk
from app.schemas.context import ContextItem
from app.services.context.identity import generate_deterministic_id

class ContextItemNormalizer:
    """
    Normalizes Evidence and KnowledgeChunk objects into canonical ContextItem models
    using deterministic identity generation.
    """
    @staticmethod
    def generate_deterministic_id(scenario_id: str, incident_id: str, source_kind: str, source_id: str) -> str:
        return generate_deterministic_id(scenario_id, incident_id, source_kind, source_id)

    @classmethod
    def from_evidence(cls, evidence: Evidence) -> ContextItem:
        item_id = cls.generate_deterministic_id(
            scenario_id=evidence.scenario_id,
            incident_id=evidence.incident_id,
            source_kind="evidence",
            source_id=evidence.evidence_id
        )
        
        # Word-based cost approximation
        word_count = len(evidence.observation.split())
        cost = max(word_count, 1)

        # Extract timestamp
        timestamp = None
        if evidence.time_window:
            timestamp = evidence.time_window.start

        # Put validation and provenance details inside metadata
        metadata = {
            "validation_status": "valid",
            "provenance_dataset": evidence.provenance.dataset,
            "record_reference": evidence.provenance.record_reference,
            "source_record_ids": list(evidence.source_record_ids)
        }
        if evidence.retrieval:
            metadata["retrieval_tool"] = evidence.retrieval.tool_name
            metadata["retrieval_relevance"] = evidence.retrieval.relevance_score

        return ContextItem(
            item_id=item_id,
            source_kind="evidence",
            source_id=evidence.evidence_id,
            scenario_id=evidence.scenario_id,
            incident_id=evidence.incident_id,
            service=evidence.service,
            component=None,  # Not defined on raw Evidence schema
            timestamp=timestamp,
            category=evidence.source_type.value,
            content=evidence.observation,
            priority_score=0.0,  # Will be computed by the prioritizer
            citation_reference=f"cite:evidence:{evidence.evidence_id}",
            provenance_reference=f"prov:evidence:{evidence.evidence_id}",
            estimated_budget_cost=cost,
            selection_reason="Authoritative telemetry observation",
            metadata=metadata
        )

    @classmethod
    def from_knowledge(cls, chunk: KnowledgeChunk, scenario_id: str, incident_id: str) -> ContextItem:
        item_id = cls.generate_deterministic_id(
            scenario_id=scenario_id,
            incident_id=incident_id,
            source_kind="knowledge",
            source_id=chunk.chunk_id
        )

        word_count = len(chunk.content.split())
        cost = max(word_count, 1)

        service_scope = chunk.metadata.get("service_scope", [])
        service = service_scope[0] if service_scope else None

        # Build metadata dictionary preserving scores and references
        metadata = {
            "document_id": chunk.document_id,
            "heading": chunk.heading,
            "section": chunk.section,
            "version": chunk.metadata.get("version", "1.0"),
            "original_metadata": chunk.metadata
        }
        
        # Populate scores if provenance exists
        if chunk.provenance:
            metadata["dense_rank"] = chunk.provenance.dense_rank
            metadata["dense_score"] = chunk.provenance.dense_score
            metadata["lexical_rank"] = chunk.provenance.lexical_rank
            metadata["lexical_score"] = chunk.provenance.lexical_score
            metadata["fusion_score"] = chunk.provenance.fusion_score
            metadata["retrieval_channels"] = list(chunk.provenance.retrieval_channels)

        return ContextItem(
            item_id=item_id,
            source_kind="knowledge",
            source_id=chunk.chunk_id,
            scenario_id=scenario_id,
            incident_id=incident_id,
            service=service,
            component=chunk.metadata.get("component"),
            timestamp=None,
            category=chunk.metadata.get("document_type", "runbook"),
            content=chunk.content,
            priority_score=0.0,
            citation_reference=f"cite:knowledge:{chunk.chunk_id}",
            provenance_reference=f"prov:knowledge:{chunk.chunk_id}",
            estimated_budget_cost=cost,
            selection_reason="Supporting operational knowledge",
            metadata=metadata
        )
