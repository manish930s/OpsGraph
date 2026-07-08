import time
from datetime import datetime, timezone
from app.schemas.evidence import EvidenceBundle
from app.schemas.knowledge import KnowledgeBundle
from app.schemas.context import (
    InvestigationContext,
    ContextItem,
    ContextSection,
    CitationInfo,
    ProvenanceInfo,
    ContextBudgetSummary,
    ContextExecutionMetadata
)
from app.services.context.exceptions import ContextBuildError
from app.services.context.validator import InputValidator
from app.services.context.normalizer import ContextItemNormalizer
from app.services.context.deduplicator import ContextDeduplicator
from app.services.context.prioritizer import ContextPrioritizer, ContextPriorityPolicy
from app.services.context.budget import BudgetManager, ContextBudgetPolicy
from app.services.context.coverage import CoverageAnalyzer, GapReporter

class ContextBuilder:
    """
    Orchestrates deterministic validation, normalization, deduplication, prioritization,
    budgeting, and sectioning of incident evidence and supporting knowledge.
    """
    def __init__(
        self,
        budget_policy: ContextBudgetPolicy | None = None,
        priority_policy: ContextPriorityPolicy | None = None
    ):
        self.budget_policy = budget_policy or ContextBudgetPolicy()
        self.priority_policy = priority_policy or ContextPriorityPolicy()
        self.prioritizer = ContextPrioritizer(self.priority_policy)
        self.budget_manager = BudgetManager(self.budget_policy)

    def build(
        self,
        evidence_bundle: EvidenceBundle,
        knowledge_bundle: KnowledgeBundle | None
    ) -> InvestigationContext:
        """
        Builds a validated, deduplicated, prioritized, and budgeted InvestigationContext.
        """
        start_time = time.perf_counter()

        # 1. Input Validation
        InputValidator.validate(evidence_bundle, knowledge_bundle)

        scenario_id = evidence_bundle.evidence_list[0].scenario_id
        incident_id = evidence_bundle.evidence_list[0].incident_id

        # 2. Context Normalization
        candidates = []
        for ev in evidence_bundle.evidence_list:
            candidates.append(ContextItemNormalizer.from_evidence(ev))

        if knowledge_bundle and knowledge_bundle.chunks:
            for chunk in knowledge_bundle.chunks:
                candidates.append(
                    ContextItemNormalizer.from_knowledge(chunk, scenario_id, incident_id)
                )

        # 3. Context Deduplication
        deduped_candidates, duplicates_removed = ContextDeduplicator.deduplicate(candidates)

        # 4. Priority Scoring
        prioritized_candidates = self.prioritizer.prioritize_items(deduped_candidates, evidence_bundle)

        # 5. Budget Allocation & Pruning
        selected_items, dropped_items, budget_summary_dict = self.budget_manager.allocate_and_select(
            prioritized_candidates
        )

        # 6. Citation Map Construction
        citation_map = {}
        for item in selected_items:
            if item.source_kind == "evidence":
                # Find matching original evidence
                orig_ev = next(x for x in evidence_bundle.evidence_list if x.evidence_id == item.source_id)
                citation_map[item.item_id] = CitationInfo(
                    source_kind="evidence",
                    id=item.source_id,
                    source_type=orig_ev.source_type.value,
                    source_record_ids=tuple(orig_ev.source_record_ids),
                    evidence_provenance=orig_ev.provenance.model_dump()
                )
            else:
                # Find chunk
                orig_chunk = next(x for x in knowledge_bundle.chunks if x.chunk_id == item.source_id)
                citation_map[item.item_id] = CitationInfo(
                    source_kind="knowledge",
                    id=item.source_id,
                    document_id=orig_chunk.document_id,
                    chunk_id=orig_chunk.chunk_id,
                    source_path=orig_chunk.metadata.get("source_path"),
                    section=orig_chunk.section,
                    heading=orig_chunk.heading,
                    version=orig_chunk.metadata.get("version")
                )

        # 7. Provenance Map Construction
        provenance_map = {}
        for item in selected_items:
            if item.source_kind == "evidence":
                provenance_map[item.item_id] = ProvenanceInfo(
                    source_kind="evidence",
                    lineage=(
                        "Telemetry Record",
                        "Evidence Object",
                        "EvidenceBundle",
                        "ContextItem",
                        "InvestigationContext"
                    ),
                    details=item.metadata
                )
            else:
                provenance_map[item.item_id] = ProvenanceInfo(
                    source_kind="knowledge",
                    lineage=(
                        "Knowledge Document",
                        "KnowledgeChunk",
                        "Retrieval Channels",
                        "RRF",
                        "Reranker",
                        "KnowledgeBundle",
                        "ContextItem",
                        "InvestigationContext"
                    ),
                    details=item.metadata
                )

        # Verify citation and provenance integrity
        selected_ids = {x.item_id for x in selected_items}
        for item_id in citation_map:
            if item_id not in selected_ids:
                raise ContextValidationError(f"Orphan citation found: key '{item_id}' has no corresponding selected item.")
        
        for item in selected_items:
            if item.item_id not in citation_map:
                raise ContextValidationError(f"Selected item '{item.item_id}' is missing a citation map entry.")
            
            cite = citation_map[item.item_id]
            if item.source_kind == "evidence":
                if cite.source_kind != "evidence" or not cite.evidence_provenance:
                    raise ContextValidationError(f"Evidence item '{item.item_id}' has invalid citation details.")
            else:
                if cite.source_kind != "knowledge" or not cite.document_id or not cite.chunk_id:
                    raise ContextValidationError(f"Knowledge item '{item.item_id}' has invalid citation details.")

        for item in selected_items:
            if item.item_id not in provenance_map:
                raise ContextValidationError(f"Selected item '{item.item_id}' is missing a provenance map entry.")
            prov = provenance_map[item.item_id]
            if item.source_kind == "evidence":
                if "Telemetry Record" not in prov.lineage:
                    raise ContextValidationError(f"Evidence item '{item.item_id}' has invalid provenance lineage.")
            else:
                if "Knowledge Document" not in prov.lineage:
                    raise ContextValidationError(f"Knowledge item '{item.item_id}' has invalid provenance lineage.")

        # 8. Context Section Division
        critical_evidence = []
        supporting_evidence = []
        contradictory_evidence = []
        relevant_runbooks = []
        relevant_knowledge = []
        topology_context = []
        deployment_context = []

        for item in selected_items:
            category_lower = item.category.lower() if item.category else ""
            if item.source_kind == "evidence":
                if "topology" in category_lower:
                    topology_context.append(item)
                elif "deployment" in category_lower:
                    deployment_context.append(item)
                else:
                    is_contradictory = item.metadata.get("priority_penalties", {}).get("contradictions_penalty", 0.0) > 0.0
                    if is_contradictory:
                        contradictory_evidence.append(item)
                    elif item.priority_score >= 1.2:
                        critical_evidence.append(item)
                    else:
                        supporting_evidence.append(item)
            else:
                if "runbook" in category_lower:
                    relevant_runbooks.append(item)
                elif "topology" in category_lower:
                    topology_context.append(item)
                elif "deployment" in category_lower:
                    deployment_context.append(item)
                else:
                    relevant_knowledge.append(item)

        sections = (
            ContextSection(name="Critical Evidence", items=tuple(critical_evidence)),
            ContextSection(name="Supporting Evidence", items=tuple(supporting_evidence)),
            ContextSection(name="Contradictory Evidence", items=tuple(contradictory_evidence)),
            ContextSection(name="Relevant Runbooks", items=tuple(relevant_runbooks)),
            ContextSection(name="Relevant Operational Knowledge", items=tuple(relevant_knowledge)),
            ContextSection(name="Topology Context", items=tuple(topology_context)),
            ContextSection(name="Deployment Context", items=tuple(deployment_context)),
        )

        # 9. Coverage and Gap Analysis
        contradictory_dropped = any(
            x.source_kind == "evidence" and 
            x.metadata.get("priority_penalties", {}).get("contradictions_penalty", 0.0) > 0.0
            for x in dropped_items
        )
        oversized_exclusions = budget_summary_dict.get("excluded_oversized_items", ())

        coverage = CoverageAnalyzer.analyze(candidates, selected_items, duplicates_removed)
        gaps = GapReporter.report_gaps(
            coverage,
            evidence_bundle,
            knowledge_bundle,
            budget_summary_dict["dropped_by_budget_count"],
            contradictory_dropped=contradictory_dropped,
            oversized_exclusions=oversized_exclusions
        )

        # 10. Execution Metadata & Duration
        duration_ms = (time.perf_counter() - start_time) * 1000.0
        upstream_degraded = knowledge_bundle.execution_metadata.degraded_mode if knowledge_bundle else False
        upstream_reasons = tuple(knowledge_bundle.execution_metadata.fallback_reasons) if knowledge_bundle else ()

        execution_metadata = ContextExecutionMetadata(
            candidates_received=len(candidates),
            duplicates_removed=duplicates_removed,
            items_selected=len(selected_items),
            items_dropped_by_budget=budget_summary_dict["dropped_by_budget_count"],
            estimated_budget_used=budget_summary_dict["evidence_cost"] + budget_summary_dict["knowledge_cost"],
            build_duration_ms=round(duration_ms, 2),
            validation_status="valid",
            upstream_degraded_mode=upstream_degraded,
            upstream_fallback_reasons=upstream_reasons,
            excluded_oversized_items=oversized_exclusions
        )

        budget_summary = ContextBudgetSummary(
            total_budget=budget_summary_dict["total_budget"],
            evidence_budget=budget_summary_dict["evidence_budget"],
            knowledge_budget=budget_summary_dict["knowledge_budget"],
            evidence_cost=budget_summary_dict["evidence_cost"],
            knowledge_cost=budget_summary_dict["knowledge_cost"],
            remaining_budget=budget_summary_dict["remaining_budget"],
            dropped_by_budget_count=budget_summary_dict["dropped_by_budget_count"]
        )

        # Build stable context ID using incident ID
        context_id = f"CTX-{incident_id}-{scenario_id}"

        return InvestigationContext(
            context_id=context_id,
            scenario_id=scenario_id,
            incident_id=incident_id,
            build_timestamp=datetime.now(timezone.utc).isoformat(),
            selected_evidence_ids=tuple(x.source_id for x in selected_items if x.source_kind == "evidence"),
            selected_knowledge_ids=tuple(x.source_id for x in selected_items if x.source_kind == "knowledge"),
            sections=sections,
            citation_map=citation_map,
            provenance_map=provenance_map,
            budget_summary=budget_summary,
            coverage_summary=coverage,
            gap_summary=gaps,
            execution_metadata=execution_metadata
        )
