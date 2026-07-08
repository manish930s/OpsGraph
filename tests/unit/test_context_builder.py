import pytest
from datetime import datetime, timezone
from pydantic import ValidationError as PydanticValidationError
from app.schemas.common import TimeWindow
from app.schemas.evidence import Evidence, EvidenceProvenance, EvidenceBundle, ConfidenceSummary, ConfidenceComponents
from app.common.enums import SourceType
from app.schemas.knowledge import KnowledgeChunk, KnowledgeBundle, RetrievalExecutionMetadata, RetrievalChannelProvenance
from app.schemas.context import ContextItem, InvestigationContext
from app.services.context import ContextBuilder, ContextPriorityPolicy, ContextBudgetPolicy
from app.services.context.exceptions import ContextValidationError, ContextScopeMismatchError
from app.services.context.normalizer import ContextItemNormalizer
from app.services.context.deduplicator import ContextDeduplicator
from app.services.context.prioritizer import ContextPrioritizer
from app.services.context.budget import BudgetManager, WordCountBudgetEstimator

@pytest.fixture
def sample_evidence_bundle():
    conf = ConfidenceSummary(
        score=0.9,
        band="HIGH",
        explanation=["Good data"],
        components=ConfidenceComponents(
            source_reliability=1.0, cross_source_agreement=1.0, timeline_consistency=1.0,
            topology_consistency=1.0, evidence_coverage=1.0, deployment_consistency=1.0,
            observation_completeness=1.0, contradictions=0.0
        ),
        supporting_evidence_count=2,
        conflicting_evidence_count=0,
        missing_evidence_categories=[]
    )
    
    ev1 = Evidence(
        evidence_id="LOG-EV-SCN-0001",
        incident_id="INC-1234",
        scenario_id="SCN-001",
        source_type=SourceType.LOG,
        service="checkout-service",
        observation="Database pool latency is saturated at 80%",
        source_record_ids=["r1"],
        provenance=EvidenceProvenance(dataset="logs", record_reference="r1"),
        time_window=TimeWindow(start="2026-01-15T14:00:00Z", end="2026-01-15T14:00:00Z")
    )
    
    ev2 = Evidence(
        evidence_id="MET-EV-SCN-0002",
        incident_id="INC-1234",
        scenario_id="SCN-001",
        source_type=SourceType.METRIC,
        service="checkout-service",
        observation="Transaction failure rate spike",
        source_record_ids=["r2"],
        provenance=EvidenceProvenance(dataset="metrics", record_reference="r2"),
        time_window=TimeWindow(start="2026-01-15T14:00:00Z", end="2026-01-15T14:00:00Z")
    )

    return EvidenceBundle(
        evidence_list=(ev1, ev2),
        timeline=(ev1, ev2),
        confidence_summary=conf,
        validation_status="valid",
        coverage_summary={"checkout-service": ["log", "metric"]}
    )

@pytest.fixture
def sample_knowledge_bundle():
    chunk1 = KnowledgeChunk(
        chunk_id="chunk-1",
        document_id="RB-DB-001",
        section="Symptoms",
        heading="High latency",
        content="Verify database pool connections. Latency spikes occur when threads await connections.",
        metadata={"service_scope": ["checkout-service"], "document_type": "runbook", "version": "1.0"},
        provenance=RetrievalChannelProvenance(
            chunk_id="chunk-1",
            dense_rank=1,
            dense_score=0.95,
            lexical_rank=1,
            lexical_score=8.5,
            fusion_score=0.032,
            retrieval_channels=["dense", "lexical"]
        )
    )
    
    exec_meta = RetrievalExecutionMetadata(
        vector_store_mode="memory",
        embedding_mode="mock",
        reranker_mode="lexical-fallback",
        degraded_mode=True,
        fallback_reasons=["Vector store falls back to in-memory"]
    )
    
    return KnowledgeBundle(
        chunks=(chunk1,),
        metadata={"scenario_id": "SCN-001"},
        retrieval_scores={"chunk-1": 0.032},
        rerank_scores={"chunk-1": 0.88},
        applied_filters={"service_scope": ["checkout-service"]},
        evidence_references=["LOG-EV-SCN-0001"],
        search_summary="Retrieved chunks",
        execution_metadata=exec_meta
    )

# --- 1. Input Validation Tests ---

def test_validation_success(sample_evidence_bundle, sample_knowledge_bundle):
    # Should build without error
    builder = ContextBuilder()
    context = builder.build(sample_evidence_bundle, sample_knowledge_bundle)
    assert context.incident_id == "INC-1234"
    assert context.scenario_id == "SCN-001"

def test_validation_mismatched_scenarios(sample_evidence_bundle):
    # Alter knowledge bundle scenario
    kb = KnowledgeBundle(
        chunks=(),
        metadata={"scenario_id": "SCN-999"}, # mismatched
        retrieval_scores={},
        rerank_scores={},
        applied_filters={},
        evidence_references=[],
        search_summary="",
        execution_metadata=RetrievalExecutionMetadata(
            vector_store_mode="memory", embedding_mode="mock", reranker_mode="lexical-fallback", degraded_mode=True
        )
    )
    builder = ContextBuilder()
    with pytest.raises(ContextScopeMismatchError):
        builder.build(sample_evidence_bundle, kb)

def test_validation_mismatched_incident_in_evidence():
    conf = ConfidenceSummary(
        score=0.9, band="HIGH", explanation=[], components=ConfidenceComponents(
            source_reliability=1., cross_source_agreement=1., timeline_consistency=1.,
            topology_consistency=1., evidence_coverage=1., deployment_consistency=1.,
            observation_completeness=1., contradictions=0.
        ),
        supporting_evidence_count=2, conflicting_evidence_count=0, missing_evidence_categories=[]
    )
    # Different incident IDs
    ev1 = Evidence(
        evidence_id="LOG-EV-SCN-0001", incident_id="INC-1111", scenario_id="SCN-001",
        source_type=SourceType.LOG, service="checkout", observation="obs",
        provenance=EvidenceProvenance(dataset="logs"),
        time_window=TimeWindow(start="2026-01-15T14:00:00Z", end="2026-01-15T14:00:00Z")
    )
    ev2 = Evidence(
        evidence_id="LOG-EV-SCN-0002", incident_id="INC-2222", scenario_id="SCN-001",
        source_type=SourceType.LOG, service="checkout", observation="obs",
        provenance=EvidenceProvenance(dataset="logs"),
        time_window=TimeWindow(start="2026-01-15T14:00:00Z", end="2026-01-15T14:00:00Z")
    )
    bundle = EvidenceBundle(
        evidence_list=(ev1, ev2), timeline=(ev1, ev2), confidence_summary=conf,
        validation_status="valid"
    )
    builder = ContextBuilder()
    with pytest.raises(ContextScopeMismatchError):
        builder.build(bundle, None)

# --- 2. Normalization & Identity Tests ---

def test_normalization_and_identity_determinism(sample_evidence_bundle):
    ev = sample_evidence_bundle.evidence_list[0]
    ctx_item = ContextItemNormalizer.from_evidence(ev)
    
    assert ctx_item.source_kind == "evidence"
    assert ctx_item.source_id == "LOG-EV-SCN-0001"
    assert ctx_item.content == "Database pool latency is saturated at 80%"
    assert ctx_item.service == "checkout-service"
    
    # Deterministic ID generation check
    expected_id = ContextItemNormalizer.generate_deterministic_id(
        scenario_id="SCN-001", incident_id="INC-1234", source_kind="evidence", source_id="LOG-EV-SCN-0001"
    )
    assert ctx_item.item_id == expected_id

# --- 3. Deduplication Tests ---

def test_context_deduplication():
    # Construct identical items
    item1 = ContextItem(
        item_id="id1", source_kind="evidence", source_id="LOG-1", scenario_id="SCN-001",
        content="Connection pool spike", priority_score=0.8, citation_reference="cite",
        provenance_reference="prov", estimated_budget_cost=3, selection_reason="reason",
        metadata={"dense_score": 0.5}
    )
    item2 = ContextItem(
        item_id="id1", source_kind="evidence", source_id="LOG-1", scenario_id="SCN-001",
        content="Connection pool spike", priority_score=0.9, citation_reference="cite",
        provenance_reference="prov", estimated_budget_cost=3, selection_reason="reason",
        metadata={"dense_score": 0.7, "fusion_score": 0.05}
    )
    
    deduped, removed = ContextDeduplicator.deduplicate([item1, item2])
    assert len(deduped) == 1
    assert removed == 1
    # Check score and metadata merge
    assert deduped[0].priority_score == 0.9
    assert deduped[0].metadata["dense_score"] == 0.7
    assert deduped[0].metadata["fusion_score"] == 0.05

# --- 4. Prioritization Tests ---

def test_context_prioritization(sample_evidence_bundle):
    policy = ContextPriorityPolicy(
        evidence_base_weight=1.0,
        confidence_score_weight=0.5,
        knowledge_base_weight=0.5,
        rerank_weight=0.4
    )
    prioritizer = ContextPrioritizer(policy)
    
    # Create mock items
    item1 = ContextItem(
        item_id="id1", source_kind="evidence", source_id="LOG-1", scenario_id="SCN-001",
        content="Telemetries", priority_score=0.0, citation_reference="cite",
        provenance_reference="prov", estimated_budget_cost=3, selection_reason="reason"
    )
    item2 = ContextItem(
        item_id="id2", source_kind="knowledge", source_id="chunk-1", scenario_id="SCN-001",
        content="Runbook content", priority_score=0.0, citation_reference="cite",
        provenance_reference="prov", estimated_budget_cost=3, selection_reason="reason",
        metadata={"rerank_score": 0.9}
    )

    prioritized = prioritizer.prioritize_items([item1, item2], sample_evidence_bundle)
    assert len(prioritized) == 2
    
    # Evidence score: base (1.0) + confidence_contrib (0.9 * 0.5) + reliability (1.0 * 0.3) = 1.75
    assert prioritized[0].source_id == "LOG-1"
    assert prioritized[0].priority_score == 1.75

    # Knowledge score: base (0.5) + rerank_contrib (0.9 * 0.4) = 0.86
    assert prioritized[1].source_id == "chunk-1"
    assert prioritized[1].priority_score == 0.86

# --- 5. Budget Allocation Tests ---

def test_budget_allocation_redistribution():
    # policy total=10, 50% for evidence (limit=5), 30% for knowledge (limit=3)
    policy = ContextBudgetPolicy(total_budget=10, evidence_ratio=0.5, knowledge_ratio=0.3, reserved_ratio=0.2)
    manager = BudgetManager(policy)

    # 3 evidence items (cost=1 each), 4 knowledge items (cost=2 each)
    ev_items = [
        ContextItem(
            item_id=f"e{i}", source_kind="evidence", source_id=f"LOG-{i}", scenario_id="SCN-001",
            content="word", priority_score=0.9, citation_reference="cite",
            provenance_reference="prov", estimated_budget_cost=1, selection_reason="reason"
        ) for i in range(3)
    ]
    kn_items = [
        ContextItem(
            item_id=f"k{i}", source_kind="knowledge", source_id=f"chunk-{i}", scenario_id="SCN-001",
            content="word word", priority_score=0.8, citation_reference="cite",
            provenance_reference="prov", estimated_budget_cost=2, selection_reason="reason"
        ) for i in range(4)
    ]

    selected, dropped, summary = manager.allocate_and_select(ev_items + kn_items)
    
    # Evidence spent = 3 (limit was 5)
    # Remaining 2 gets added to knowledge limit (3 + 2 = 5)
    # Knowledge items selected: chunk-0 (cost 2), chunk-1 (cost 2) -> total 4 (fits in 5)
    assert summary["evidence_cost"] == 3
    assert summary["knowledge_cost"] == 4
    assert len(selected) == 5 # 3 evidence + 2 knowledge
    assert summary["dropped_by_budget_count"] == 2 # 2 knowledge chunks dropped

# --- 6. Citation and Provenance Trace Tests ---

def test_lineage_and_metadata_propagation(sample_evidence_bundle, sample_knowledge_bundle):
    builder = ContextBuilder()
    context = builder.build(sample_evidence_bundle, sample_knowledge_bundle)
    
    assert len(context.citation_map) > 0
    assert len(context.provenance_map) > 0

    # Assert trace metadata
    assert context.execution_metadata.upstream_degraded_mode is True
    assert "Vector store falls back to in-memory" in context.execution_metadata.upstream_fallback_reasons

    # Assert immutability
    with pytest.raises((PydanticValidationError, TypeError)):
        context.incident_id = "INC-CHANGED"

# --- 7. Stabilization & Edge-Case Tests ---

def test_cross_bundle_validation_orphan_references(sample_evidence_bundle):
    # Knowledge references an evidence item not in evidence bundle
    kb = KnowledgeBundle(
        chunks=(),
        metadata={"scenario_id": "SCN-001"},
        retrieval_scores={},
        rerank_scores={},
        applied_filters={},
        evidence_references=["NON_EXISTENT_EV_REF"],
        search_summary="",
        execution_metadata=RetrievalExecutionMetadata(
            vector_store_mode="memory", embedding_mode="mock", reranker_mode="lexical-fallback", degraded_mode=True
        )
    )
    builder = ContextBuilder()
    with pytest.raises(ContextValidationError) as excinfo:
        builder.build(sample_evidence_bundle, kb)
    assert "Orphan knowledge evidence reference" in str(excinfo.value)

def test_cross_bundle_validation_duplicate_references(sample_evidence_bundle):
    kb = KnowledgeBundle(
        chunks=(),
        metadata={"scenario_id": "SCN-001"},
        retrieval_scores={},
        rerank_scores={},
        applied_filters={},
        evidence_references=["LOG-EV-SCN-0001", "LOG-EV-SCN-0001"], # duplicate reference
        search_summary="",
        execution_metadata=RetrievalExecutionMetadata(
            vector_store_mode="memory", embedding_mode="mock", reranker_mode="lexical-fallback", degraded_mode=True
        )
    )
    builder = ContextBuilder()
    with pytest.raises(ContextValidationError) as excinfo:
        builder.build(sample_evidence_bundle, kb)
    assert "Duplicate evidence reference found" in str(excinfo.value)

def test_tiered_deduplication_tier_3():
    # Same content but different source IDs (Tier 3 content equivalent)
    item1 = ContextItem(
        item_id="id1", source_kind="knowledge", source_id="chunk-1", scenario_id="SCN-001",
        content="Identical runbook content warning", priority_score=0.8, citation_reference="cite1",
        provenance_reference="prov1", estimated_budget_cost=3, selection_reason="reason",
        metadata={"document_id": "DocA", "version": "1.0"}
    )
    item2 = ContextItem(
        item_id="id2", source_kind="knowledge", source_id="chunk-2", scenario_id="SCN-001",
        content="Identical runbook content warning", priority_score=0.7, citation_reference="cite2",
        provenance_reference="prov2", estimated_budget_cost=3, selection_reason="reason",
        metadata={"document_id": "DocB", "version": "2.0"}
    )
    
    deduped, removed = ContextDeduplicator.deduplicate([item1, item2])
    
    # Under Tier 3 policy, we preserve them as separate items
    assert len(deduped) == 2
    assert removed == 0
    assert deduped[0].metadata["content_equivalence_group"] == deduped[1].metadata["content_equivalence_group"]
    assert "chunk-2" in deduped[0].metadata["content_equivalent_to"]
    assert "chunk-1" in deduped[1].metadata["content_equivalent_to"]

def test_stable_priority_tie_breaking(sample_evidence_bundle):
    prioritizer = ContextPrioritizer()
    item1 = ContextItem(
        item_id="id1", source_kind="evidence", source_id="LOG-EV-SCN-0009", scenario_id="SCN-001",
        content="Telemetry check", priority_score=0.0, citation_reference="cite",
        provenance_reference="prov", estimated_budget_cost=2, selection_reason="reason"
    )
    item2 = ContextItem(
        item_id="id2", source_kind="evidence", source_id="LOG-EV-SCN-0001", scenario_id="SCN-001",
        content="Telemetry check", priority_score=0.0, citation_reference="cite",
        provenance_reference="prov", estimated_budget_cost=2, selection_reason="reason"
    )
    
    # Both will get identical priority scores. ascending source_id tie-breaker should place LOG-EV-SCN-0001 first!
    prioritized = prioritizer.prioritize_items([item1, item2], sample_evidence_bundle)
    assert prioritized[0].source_id == "LOG-EV-SCN-0001"
    assert prioritized[1].source_id == "LOG-EV-SCN-0009"

def test_oversized_item_exclusion():
    # item cost = 15 words. Category limit is 10.
    policy = ContextBudgetPolicy(total_budget=20, evidence_ratio=0.5, knowledge_ratio=0.3, reserved_ratio=0.2)
    manager = BudgetManager(policy)
    
    item = ContextItem(
        item_id="id1", source_kind="evidence", source_id="LOG-1", scenario_id="SCN-001",
        content="one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen", # 15 words
        priority_score=0.9, citation_reference="cite", provenance_reference="prov",
        estimated_budget_cost=15, selection_reason="reason"
    )
    
    selected, dropped, summary = manager.allocate_and_select([item])
    assert len(selected) == 0
    assert len(dropped) == 1
    assert len(summary["excluded_oversized_items"]) == 1
    assert "LOG-1" in summary["excluded_oversized_items"][0]
    assert "OVERSIZED_ITEM_EXCLUDED" in summary["excluded_oversized_items"][0]

def test_exact_budget_boundary():
    # Limit = 5.
    policy = ContextBudgetPolicy(total_budget=10, evidence_ratio=0.5, knowledge_ratio=0.3, reserved_ratio=0.2)
    manager = BudgetManager(policy)
    
    item_boundary = ContextItem(
        item_id="id1", source_kind="evidence", source_id="LOG-1", scenario_id="SCN-001",
        content="one two three four five", # exactly 5 words
        priority_score=0.9, citation_reference="cite", provenance_reference="prov",
        estimated_budget_cost=5, selection_reason="reason"
    )
    
    selected, dropped, summary = manager.allocate_and_select([item_boundary])
    assert len(selected) == 1
    assert summary["evidence_cost"] == 5

    item_oversized = ContextItem(
        item_id="id2", source_kind="evidence", source_id="LOG-2", scenario_id="SCN-001",
        content="one two three four five six", # 6 words (limit is 5)
        priority_score=0.9, citation_reference="cite", provenance_reference="prov",
        estimated_budget_cost=6, selection_reason="reason"
    )
    
    selected_over, dropped_over, summary_over = manager.allocate_and_select([item_oversized])
    assert len(selected_over) == 0
    assert len(dropped_over) == 1

def test_contradictory_evidence_retention_and_exclusion_gap():
    # Incident has contradictions component = 1.0 (high)
    conf = ConfidenceSummary(
        score=0.5, band="MODERATE", explanation=[], components=ConfidenceComponents(
            source_reliability=1., cross_source_agreement=0.5, timeline_consistency=1.,
            topology_consistency=1., evidence_coverage=1., deployment_consistency=1.,
            observation_completeness=1., contradictions=1.0 # contradictions high!
        ),
        supporting_evidence_count=1, conflicting_evidence_count=1, missing_evidence_categories=[]
    )
    
    ev1 = Evidence(
        evidence_id="LOG-EV-SCN-0001", incident_id="INC-1234", scenario_id="SCN-001",
        source_type=SourceType.LOG, service="checkout-service", observation="Normal pool state",
        provenance=EvidenceProvenance(dataset="logs"),
        time_window=TimeWindow(start="2026-01-15T14:00:00Z", end="2026-01-15T14:00:00Z")
    )
    ev2 = Evidence(
        evidence_id="LOG-EV-SCN-0002", incident_id="INC-1234", scenario_id="SCN-001",
        source_type=SourceType.LOG, service="checkout-service", observation="Exhausted pool state",
        provenance=EvidenceProvenance(dataset="logs"),
        time_window=TimeWindow(start="2026-01-15T14:00:00Z", end="2026-01-15T14:00:00Z")
    )
    
    bundle = EvidenceBundle(
        evidence_list=(ev1, ev2), timeline=(ev1, ev2), confidence_summary=conf,
        validation_status="valid"
    )
    
    # 1. Under normal budgets, both appear in Contradictory Evidence section
    builder = ContextBuilder(budget_policy=ContextBudgetPolicy(total_budget=100))
    context = builder.build(bundle, None)
    
    contradictory_section = next(x for x in context.sections if x.name == "Contradictory Evidence")
    assert len(contradictory_section.items) == 2
    assert "Evidence contradiction present." in context.gap_summary.warnings

    # 2. If budget is too tight, it will drop them and report gap
    tight_builder = ContextBuilder(budget_policy=ContextBudgetPolicy(total_budget=4, evidence_ratio=0.5, reserved_ratio=0.0))
    context_tight = tight_builder.build(bundle, None)
    assert "Budget excluded contradictory evidence." in context_tight.gap_summary.gaps

def test_context_builder_determinism(sample_evidence_bundle, sample_knowledge_bundle):
    builder = ContextBuilder()
    
    # Run twice
    ctx1 = builder.build(sample_evidence_bundle, sample_knowledge_bundle)
    ctx2 = builder.build(sample_evidence_bundle, sample_knowledge_bundle)
    
    # Exclude dynamic timestamps
    assert ctx1.context_id == ctx2.context_id
    assert ctx1.scenario_id == ctx2.scenario_id
    assert ctx1.incident_id == ctx2.incident_id
    assert ctx1.selected_evidence_ids == ctx2.selected_evidence_ids
    assert ctx1.selected_knowledge_ids == ctx2.selected_knowledge_ids
    
    # Compare sections
    assert len(ctx1.sections) == len(ctx2.sections)
    for s1, s2 in zip(ctx1.sections, ctx2.sections):
        assert s1.name == s2.name
        assert len(s1.items) == len(s2.items)
        for it1, it2 in zip(s1.items, s2.items):
            assert it1.item_id == it2.item_id
            assert it1.content == it2.content
            assert it1.priority_score == it2.priority_score
            
    # Compare gaps & summary
    assert ctx1.gap_summary == ctx2.gap_summary
    assert ctx1.coverage_summary == ctx2.coverage_summary

