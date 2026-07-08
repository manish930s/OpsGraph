# Deterministic Context Builder Architecture (Phase 6 Stabilization)
**Document Status:** Finalized (Phase 6 Stabilization Complete)  
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
         Phase 7 Boundary (Prompt Assembly & Gateway)
```

---

## 2. In-Depth Context Processing Flow

```
Input Validation (Cross-scenario and incident consistency, Knowledge references)
          |
          v
Context Normalization (ContextItem instantiation, SHA-256 stable IDs)
          |
          v
Context Deduplication (Tiered: identity deduplication vs Content-equivalence)
          |
          v
Priority Scoring (Confidence, reliability, contradictions, reranks, fusion)
          |
          v
Context Budget Allocation (Symmetric bidirectional redistribution pass)
          |
          v
Sections Organization (Critical/Supporting/Contradictory/Runbooks/Knowledge)
          |
          v
Lineage Preservation & Citation Integrity Verification (No orphans allowed)
          |
          v
Coverage & Gaps (Analysis of covered categories and warning reports)
          |
          v
InvestigationContext (Immutable Pydantic model packaging)
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

## 4. Input & Reference Validation
Before context building starts, the `InputValidator` checks the relationship between bundles:
*   **Scenario Consistency**: Rejects mismatched scenarios between Evidence and Knowledge.
*   **Incident Consistency**: Rejects mismatched incident IDs.
*   **Evidence Reference Validation**: Every evidence reference ID list preserved in `KnowledgeBundle.evidence_references` must resolve to a valid `Evidence` object inside `EvidenceBundle.evidence_list`. Orphan or duplicate references are rejected immediately using `ContextValidationError`.

---

## 5. Tiered Deduplication Policy
To preserve source contexts, a tiered deduplication policy is executed:
*   **Tier 1 — Definite Source Duplicate**: Same `source_kind` and `source_id`. Merged, preserving all metadata and provenance.
*   **Tier 2 — Definite Knowledge Identity Duplicate**: Same `document_id` and `chunk_id`. Merged, preserving RRF fusion/rerank scores.
*   **Tier 3 — Content-Equivalent, Different Provenance**: Same content text hash, but different document IDs, sections, versions, or source IDs. These **must not** collapse into a single item. They are kept as *separate* `ContextItem` objects, and tagged with `content_equivalence_group` and `content_equivalent_to` lists.

---

## 6. Configurable Priority Scoring
Priority scores are calculated using a configurable policy without LLM involvement:
*   **Evidence priority**:
    $$\text{Priority} = \text{policy.evidence\_base\_weight} + \text{confidence\_score} \times \text{weight} + \text{reliability} \times \text{weight} - \text{contradictions} \times \text{factor}$$
*   **Knowledge priority**:
    $$\text{Priority} = \text{policy.knowledge\_base\_weight} + \text{rerank\_score} \times \text{weight} + \text{fusion\_score} \times \text{weight} + \text{service\_match\_bonus}$$
*   **Stable Tie-Breaking**: Items are sorted descending by `priority_score` and then alphabetically ascending by `source_id`.

---

## 7. Budget Allocation & Pruning
The budget manager implements a strict allocation strategy:
*   **Bidirectional Capacity Redistribution**: Budget is initially split into evidence allocation (50%), knowledge allocation (30%), and reserved overhead (20%).
    *   *First Pass*: Candidates are selected up to their initial category limit. Remaining candidates are placed in category overflow queues.
    *   *Redistribution Pass*: Any unused evidence budget is offered to remaining knowledge overflow candidates, and any unused knowledge budget is offered to remaining evidence overflow candidates.
*   **Oversized-Item Policy**: If a single item's cost exceeds the allowed category limit or remaining total budget:
    *   Do not truncate the item.
    *   Do not exceed the budget.
    *   Exclude the item and record it in `execution_metadata` under `excluded_oversized_items` with the reason `OVERSIZED_ITEM_EXCLUDED`.
    *   Report the exclusion inside `gap_summary.gaps`.
*   **Exact Boundary**: Items are accepted if `cost == remaining budget`, and rejected if `cost > remaining budget`.

---

## 8. Citation & Provenance Integrity Verification
*   **Citation Map**: Maps each selected item ID to direct references (telemetry record IDs and datasets for evidence, document paths, sections, and versions for runbooks).
*   **Provenance Map**: Maps each item to its sequential pipeline history.
*   **Integrity check**: Prior to final packaging, the builder verifies that every selected item has a corresponding citation and provenance entry, and that no orphan citations exist. Failure to pass this verification raises `ContextValidationError`.

---

## 9. Contradictory Evidence Retention
*   Contradictory evidence must not be silently discarded during deduplication or priority pruning.
*   Contradictory items are assigned to the `Contradictory Evidence` section.
*   If tight budget constraints force the exclusion of contradictory evidence, the gap reporter adds a structured gap: `"Budget excluded contradictory evidence."`

---

## 10. Degraded Mode & Runtime Signaling
*   Upstream degraded retrieval status (degraded mode boolean, vector store mode, embedding mode, reranker mode, and fallback reasons) are preserved and propagated to the final `InvestigationContext` without mutation.

---

## 11. Future Phase 7 Boundaries

### 11.1 Provider-Agnostic LLM Gateway
The LLM Gateway is designed to be provider-agnostic. It coordinates traffic routes through adapters:

```
Prompt Assembly
      |
      v
Input Guardrails
      |
      v
 LLM Gateway (Interface)
      |
      +---> Groq Adapter (First Provider implemented)
      |
      +---> Future Gemini Adapter
      |
      +---> Future OpenAI Adapter
      |
      +---> Future Local Model Adapter
      |
      v
Output Guardrails
      |
      v
Validated Response
```

*   Groq will be the first implemented adapter, but it does not define the Gateway interface.

### 11.2 Guardrail Boundary
*   **Input Guardrails**: Gates user input and generated prompt messages before routing to the LLM Gateway.
*   **Output Guardrails**: Validates the model output for safety and contradictions.
*   **Separation**: Prompt assembly does not contain provider transport parameters. Gateway adapters contain no prompt templates. LangGraph nodes do not contain large inline prompt strings.

### 11.3 Python Runtime Notice
All future dependencies (NeMo Guardrails, Portkey AI, evaluation frameworks) must be verified for compatibility under standard python runtime environments (recommended: **Python 3.11**) before commencing Phase 7 implementation.
