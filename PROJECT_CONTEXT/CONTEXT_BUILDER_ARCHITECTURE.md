# Deterministic Context Builder Architecture (Phase 6)
**Document Status:** Finalized (Phase 6 Complete)  
**Authoritative Reference:** Context Builder Design, Organizing, and Pruning Contracts  

---

## 1. High-Level Architecture & Phase Boundary

The Context Builder is a deterministic pipeline component that sits between the evidence/knowledge retrieval layers and the downstream Prompt Assembly and reasoning engine.

```
EvidenceBundle ----+
                   |
KnowledgeBundle ---+
                   |
                   v
            Context Builder
                   |
                   v
          InvestigationContext
                   |
                   v
         Phase 7 Boundary (Prompt Assembly)
```

---

## 2. In-Depth Context Processing Flow

```
Input Validation (Scenario and Incident consistency check)
          |
          v
Context Normalization (ContextItem instantiation, SHA-256 stable IDs)
          |
          v
Context Deduplication (Deterministic ID and content-hash merges)
          |
          v
Priority Scoring (Confidence, reliability, contradictions, reranks, fusion)
          |
          v
Context Budget Allocation (Redistributing unused evidence budget to knowledge)
          |
          v
Sections Organization (Critical/Supporting/Contradictory/Runbooks/Knowledge)
          |
          v
Lineage Preservation (Populating Citation maps and Provenance lists)
          |
          v
Coverage & Gaps (Analysis of covered categories and warning reports)
          |
          v
InvestigationContext (Immutable Pydantic model compilation)
```

---

## 3. Data Schema Contracts

### 3.1 ContextItem Contract
Every item in the context is normalized to a canonical `ContextItem` which retains:
*   `item_id`: Stable deterministic unique identifier.
*   `source_kind`: `"evidence"` or `"knowledge"`.
*   `source_id`: Reference back to original `evidence_id` or `chunk_id`.
*   `priority_score`: Calculated priority weight.
*   `content`: Content description or chunk body.
*   `estimated_budget_cost`: Cost of item (words/tokens count).
*   `citation_reference` & `provenance_reference`: Lineage references.
*   `metadata`: Extra source-specific metadata for tracing.

### 3.2 InvestigationContext Contract
An immutable (`frozen`) Pydantic model representing:
*   `context_id`: Alphanumeric ID composed of incident and scenario identifiers.
*   `build_timestamp`: ISO-8601 build timestamp.
*   `selected_evidence_ids` & `selected_knowledge_ids`: Tracked references.
*   `sections`: Segmented lists (`Critical Evidence`, `Supporting Evidence`, `Contradictory Evidence`, `Relevant Runbooks`, `Relevant Operational Knowledge`, `Topology Context`, `Deployment Context`).
*   `citation_map` & `provenance_map`: Dictionaries mapping item IDs to their source origins and lineage chains.
*   `budget_summary`: Usage statistics.
*   `coverage_summary` & `gap_summary`: Categorized coverage tables and rule-based gaps.
*   `execution_metadata`: Builder status report.

---

## 4. Normalization & Identity Strategy
*   **Stable ID generation**: Instead of using random UUIDs, context item IDs are computed using a SHA-256 hash of:
    `scenario_id + ":" + incident_id + ":" + source_kind + ":" + source_id`
    This ensures that identical inputs always generate identical item IDs.
*   **Cost Approximation**: Word-count estimator determines the item cost deterministically.

---

## 5. Context Deduplication Policy
*   Deduplication occurs at two levels:
    1.  *ID-Level*: Unique combination of `(source_kind, source_id)`.
    2.  *Content-Level*: Unique SHA-256 hash of stripped lowercased content text.
*   Upon merging duplicates:
    *   Strongest scores (max priority, max retrieval scores) are preserved.
    *   Metadata values are merged.
    *   The count of duplicates removed is recorded in the execution metadata.

---

## 6. Configurable Priority Scoring
Priority scores are calculated using a configurable policy without LLM involvement:
*   **Evidence priority**:
    $$\text{Priority} = \text{policy.evidence\_base\_weight} + \text{confidence\_score} \times \text{weight} + \text{reliability} \times \text{weight} - \text{contradictions} \times \text{factor}$$
*   **Knowledge priority**:
    $$\text{Priority} = \text{policy.knowledge\_base\_weight} + \text{rerank\_score} \times \text{weight} + \text{fusion\_score} \times \text{weight} + \text{service\_match\_bonus}$$
*   **Stable Tie-Breaking**: Items are sorted descending by `priority_score` and then alphabetically ascending by `source_id`.

---

## 7. Budget Allocation Strategy
The budget manager uses an allocation strategy:
1.  Divides total budget (e.g. 2000 words) into Evidence Allocation (50%), Knowledge Allocation (30%), and Reserved Prompt Overhead (20%).
2.  Selects evidence items first. If evidence items consume less than the evidence allocation, the **unused evidence budget is redistributed to the knowledge allocation**.
3.  Selects knowledge items up to the updated knowledge limit.
4.  Prunes low-priority items at the boundary, ensuring no single item exceeds the remaining allocation.

---

## 8. Lineage Preservation
*   **Citation Map**: Maps each item ID to direct references (telemetry record IDs and datasets for evidence, document paths, sections, and versions for runbooks).
*   **Provenance Map**: Maps each item to its sequential creation pipeline history.

---

## 9. Coverage and Gaps
*   **Coverage**: Identifies coverage across 8 categories (`log`, `metric`, `trace`, `deployment`, `topology`, `runbook`, `operational_procedure`, `historical_incident_knowledge`).
*   **Gap Reporting**: Reports warnings on missing trace/deployment data, degraded upstream retrievals, empty knowledge sets, and budget exclusions.

---

## 10. Phase 7 Boundary
The downstream Prompt Assembly layer (Phase 7) will consume `InvestigationContext` to populate message templates. The Context Builder exposes no LLM gateway connection and remains 100% deterministic and isolated.
