# OpsGraph AI — Phase 7 Final Migration Report
**Document Status:** Phase 7 Verification and Release Gate Complete  
**Phase:** Phase 7 — Prompt Assembly, Guardrails, and Provider-Agnostic LLM Gateway  
**Execution Date:** 2026-07-09  
**Python Runtime:** CPython 3.14.0 (Windows)  
**Live Verification Status:** PASSED — Groq and Gemini Successfully Verified  

---

## 1. Executive Summary

Phase 7 delivers the first controlled model execution layer in OpsGraph AI. It provides a unified, provider-agnostic bridge for structured model execution between the Deterministic Context Builder (Phase 6) and the future Bounded LangGraph Investigation Engine (Phase 8). Prompt Assembly reduces prompt injection risk by structurally isolating untrusted retrieved knowledge from system instructions. Template versioning is managed via a registry. The LLM Gateway orchestrates input/output safety guards, exponential-backoff retries, one-transition provider fallback, JSON extraction, citation validation, and structured response parsing. NeMo Guardrails operates as a deferred adapter boundary; deterministic application guards are fully active.

**Default offline-safe suite**: 98 collected, **96 passed**, 0 failed, 2 skipped (opt-in live tests).
**Full live-enabled suite**: 98 collected, **98 passed**, 0 failed, 0 skipped.
**Groq live smoke test**: **PASSED** (2.73s, using `llama-3.3-70b-versatile`).
**Gemini live smoke test**: **PASSED** (8.05s, using `gemini-2.5-flash`).  
**Merge status**: **UNBLOCKED** — both live Groq and Gemini generation successfully verified.

---

## 2. Repository State

- **Active Branch**: `feature/phase-7-prompt-guardrails-gateway`
- **Working Tree State**: Clean — no uncommitted modifications (after tracking conftest and embedding safety files)
- **Python Runtime**: CPython 3.14.0 (Windows x64)

---

## 3. Secret Safety Verification

- `.env` is listed in `.gitignore` (exact match)
- `.env.*` variants are listed in `.gitignore` with `!.env.example` exclusion
- `git check-ignore .env` confirms `.env` is ignored
- `.env.example` is tracked and contains only placeholder empty strings — no real credentials
- `GROQ_API_KEY` available in current execution environment: **True**
- `GEMINI_API_KEY` available in current execution environment: **True**
- No API key values appear in any source file, test file, migration report, or architecture document
- Search of tracked files confirms no real credentials are staged or committed

---

## 4. File Ledger

### Files Created (Phase 7 & Verification Pass)

| Path | Purpose |
| :--- | :--- |
| `app/schemas/prompting.py` | `ModelRequest` and `Message` schemas |
| `app/schemas/model_response.py` | `ValidatedModelResponse`, `RCADecisionResponse`, `CriticDecisionResponse`, `LLMExecutionMetadata` |
| `prompts/rca/system_v1.txt` | System prompt v1 |
| `prompts/rca/investigation_v1.txt` | Investigation user prompt v1 |
| `prompts/rca/critic_v1.txt` | Critic user prompt v1 |
| `app/services/prompting/templates.py` | Versioned prompt registry |
| `app/services/prompting/assembler.py` | `PromptAssembler` — context-to-request compilation |
| `app/services/prompting/__init__.py` | Package export |
| `app/services/guardrails/base.py` | `InputGuard` and `OutputGuard` ABCs |
| `app/services/guardrails/input_guard.py` | `DeterministicInputGuard` |
| `app/services/guardrails/output_guard.py` | `DeterministicOutputGuard` (pipeline façade) |
| `app/services/guardrails/nemo_adapter.py` | `NeMoInputGuard` and `NeMoOutputGuard` (deferred) |
| `app/services/guardrails/__init__.py` | Package export |
| `app/services/gateway/errors.py` | `GatewayError` hierarchy |
| `app/services/gateway/provider.py` | `LLMProvider` protocol |
| `app/services/gateway/providers/groq_provider.py` | Groq SDK adapter |
| `app/services/gateway/providers/gemini_provider.py` | Gemini SDK adapter (google-genai) |
| `app/services/gateway/providers/__init__.py` | Package export |
| `app/services/gateway/retry.py` | `BoundedRetryHandler` |
| `app/services/gateway/gateway.py` | `LLMGateway` orchestrator + `extract_json_payload()` |
| `app/services/gateway/__init__.py` | Package export |
| `PROJECT_CONTEXT/LLM_GATEWAY_ARCHITECTURE.md` | Architecture reference |
| `tests/unit/test_prompt_gateway.py` | Unit test suite |
| `tests/unit/test_embedding_safety.py` | Embedding safety and configuration unit tests |
| `tests/integration/test_live_gateway.py` | Opt-in live provider smoke tests |
| `tests/integration/conftest.py` | Collection-time test-gating conftest |
| `pytest.ini` | Custom marker registration (`live_api`) |

### Files Modified (Phase 7 & Verification Pass)

| Path | Change |
| :--- | :--- |
| `app/config.py` | Added LLM/Embedding configuration fields, validation constraints, and settings model validator |
| `app/services/retrieval/embedding.py` | Dynamically use settings-driven models and dimensions; Strategy A collection routing |
| `app/services/retrieval/qdrant_service.py` | Route retrieval to Strategy A collection name |
| `app/ingestion/processor.py` | Create, wipe, and insert points to Strategy A dynamic collection names |
| `app/schemas/__init__.py` | Exported prompting and response models |
| `requirements.txt` | Declared dependencies, replacing `google-generativeai` with `google-genai` |
| `.gitignore` | Added `.env.*` and `!.env.example` |
| `DOCS/00_MIGRATION_REPORT.md` | Updated (this document) |
| `README.md` | Updated Phase 7 roadmap status |

---

## 5. Actual Output Pipeline (Verified from `gateway.py`)

```
InvestigationContext
    ↓  PromptAssembler.assemble()
ModelRequest  [immutable Pydantic, context_references tuple]
    ↓  DeterministicInputGuard.evaluate()
    ↓  NeMoInputGuard.evaluate()  [deferred — no-op]
Validated ModelRequest
    ↓  BoundedRetryHandler.execute(provider.generate)
Raw provider string  [may contain markdown fences]
    ↓  extract_json_payload()  [module function in gateway.py]
Clean JSON string
    ↓  DeterministicOutputGuard.evaluate()  [façade]
    ↓  NeMoOutputGuard.evaluate()  [deferred — no-op]
Policy-validated JSON string
    ↓  json.loads() + Pydantic RCADecisionResponse(**data) or CriticDecisionResponse(**data)
Typed Pydantic model  [field_validator deduplicates citation lists]
    ↓
ValidatedModelResponse  [typed response + LLMExecutionMetadata]
```

---

## 6. Prompt Assembly Boundary

- `PromptAssembler.assemble(context, task_type, prompt_version)` produces an immutable `ModelRequest`.
- System instructions are compiled into `system_message` from versioned templates.
- User message contains structured telemetry observations and retrieved knowledge.
- Retrieved knowledge is isolated inside `<untrusted_knowledge_context>` XML tags with explicit instructions to treat it as read-only data.
- `ModelRequest.context_references` is populated with the exact citation IDs present in the compiled prompt. This tuple becomes the citation validation source of truth.

---

## 7. Output Guard Responsibility (Façade — Verified)

`DeterministicOutputGuard.evaluate()` performs all of the following in order:

1. Empty content check → `GuardrailRejectedError`
2. JSON format validation → `GuardrailRejectedError`
3. Regex text-level citation scan (`[CTX-...]` patterns) → `CitationValidationError`
4. Typed list citation validation (`supporting_evidence_references`, `contradicting_evidence_references`, `knowledge_references`) → `CitationValidationError`
5. RCA empty-citation policy (for `task_type == "rca"`) → `CitationValidationError`
6. Response size limit (> 100,000 chars) → `GuardrailRejectedError`

---

## 8. Citation Validation Architecture

**Style**: Hybrid — text-level regex scan AND typed list field validation.  
**Stage**: Occurs **before** Pydantic schema parsing, inside `DeterministicOutputGuard`.  
**Source of Truth**: `ModelRequest.context_references` (the exact prompt-included citation set).

---

## 9. Provider Interface

- **Protocol**: `LLMProvider` in `app/services/gateway/provider.py`
- **Contract**: `generate(request: ModelRequest) -> str`
- **Properties**: `provider_name: str`, `model_id: str`
- **Mock mode**: Both adapters return deterministic JSON when `settings.LLM_PROVIDER == "mock"`, allowing fully offline unit testing.

---

## 10. Verified Provider Capability Matrix

| Category | Groq Adapter | Gemini Adapter |
| :--- | :--- | :--- |
| **Model Config** | `settings.GROQ_MODEL` | `settings.GEMINI_MODEL` |
| **Default Model** | `llama-3.3-70b-versatile` | `gemini-2.5-flash` |
| **SDK** | `groq` (Python SDK) | `google-genai` (Migrated successfully) |
| **Structured Output** | `response_format={"type": "json_object"}` | `response_mime_type="application/json"` |
| **Temperature** | `0.0` hardcoded | `0.0` hardcoded |
| **Timeout** | Passed to Groq SDK `timeout=` | Passed via `types.GenerateContentConfig` |
| **Rate-Limit** | HTTP 429 → `ProviderRateLimitError` | `RESOURCE_EXHAUSTED` → `ProviderRateLimitError` |
| **Auth Failure** | HTTP 401/403 → `ProviderAuthenticationError` | `401/403/permission` → `ProviderAuthenticationError` |
| **Timeout Mapping** | `APITimeoutError` → `ProviderTimeoutError` | `timeout/deadline` → `ProviderTimeoutError` |
| **Connection Error** | `APIConnectionError` → `ProviderUnavailableError` | `GoogleAPIError` → `ProviderUnavailableError` |
| **Live Smoke-Test** | **PASSED** (2.73s) | **PASSED** (8.05s) |

---

## 11. Retry Policy

- **Handler**: `BoundedRetryHandler` (`app/services/gateway/retry.py`)
- **Max retries**: `settings.LLM_MAX_RETRIES` (default: 3)
- **Backoff**: Exponential, initial 0.5s, factor 2.0x
- **Retryable**: `ProviderRateLimitError`, `ProviderTimeoutError`, `ProviderUnavailableError`

---

## 12. Fallback Policy

- **Trigger condition**: Transient error, retries exhausted, `LLM_FALLBACK_ENABLED=True`, fallback provider configured and differs from initial
- **Maximum transitions**: **1** (no ping-pong)

---

## 13. NeMo Runtime Status

- **Status**: Deferred — `nemoguardrails` fails to compile on Python 3.14.0 / Windows
- **Active guards**: `DeterministicInputGuard` and `DeterministicOutputGuard` are fully active

---

## 14. Default Test Suite

**Command**: `.\venv\Scripts\python.exe -m pytest`  
**Config file**: `pytest.ini`  

| Metric | Count (Offline Mode) | Count (Live-Enabled Mode) |
| :--- | :--- | :--- |
| Collected | 98 | 98 |
| Passed | 96 | 98 |
| Failed | 0 | 0 |
| Skipped | 2 (integration live tests) | 0 |
| Warnings | 2 | 2 |

---

## 15. Live Smoke Tests

**Groq live test command**: `$env:RUN_LIVE_TESTS="true"; .\venv\Scripts\python.exe -m pytest tests/integration/test_live_gateway.py::test_live_groq_smoke -v`  
**Groq live test — executed**: 2026-07-09. `RUN_LIVE_TESTS=true` was set.  
**GROQ LIVE SMOKE TEST: PASSED** (2.73s, `llama-3.3-70b-versatile`)

**Gemini live test command**: `$env:RUN_LIVE_TESTS="true"; .\venv\Scripts\python.exe -m pytest tests/integration/test_live_gateway.py::test_live_gemini_smoke -v`  
**Gemini live test — executed**: 2026-07-09. `RUN_LIVE_TESTS=true` was set.  
**GEMINI LIVE SMOKE TEST: PASSED** (8.05s, `gemini-2.5-flash`)

**Explanation of Gemini Success**: The replacement model `gemini-2.5-flash` was selected because the standard `gemini-2.0-flash` free tier requests were blocked with a quota limit of 0. Using the new API key and model config, the client successfully authorized and generated structured content complying with all strict schema, formatting, and citation constraints.

---

## 16. Technical Debt Assessment

- **google-genai SDK Warning**: The `google-genai` SDK emits a deprecation warning regarding `_UnionGenericAlias` on Python 3.14. Functional impact: none.
- **Word-based Tokenizer**: Word count splits used for budget calculation instead of BPE tokenizers.
- **Token Usage Metadata**: Not extracted by Groq/Gemini adapters.

---

## 17. Phase 8 Bounded Orchestration Boundary

Phase 8 (LangGraph Investigation Engine) must implement a bounded, deterministic state graph.

---

## 18. Exit Checklist

- `[x]` Active branch: `feature/phase-7-prompt-guardrails-gateway`
- `[x]` `.env` verified ignored by git
- `[x]` `.env.*` variants ignored; `.env.example` tracked
- `[x]` No API key values in any source file, test, or documentation
- `[x]` GROQ_API_KEY availability checked — **True**
- `[x]` GEMINI_API_KEY availability checked — **True**
- `[x]` Output pipeline traced from actual code — documented accurately
- `[x]` Architecture diagram matches implementation
- `[x]` JSON extraction responsibility is explicit
- `[x]` Output Guard responsibility is explicit (pipeline façade)
- `[x]` Citation validation source of truth is `ModelRequest.context_references`
- `[x]` Provider capability matrix verified against adapter code
- `[x]` Test summary wording is mathematically correct
- `[x]` Technical debt section covers real operational limitations
- `[x]` NeMo status remains truthful (deferred, not active)
- `[x]` Phase 8 remains bounded orchestration — no LangGraph code introduced
- `[x]` `requirements.txt` updated with `groq` and `google-genai`
- `[x]` Live tests fixed: single-provider smoke tests disable fallback
- `[x]` Default suite: **96 passed, 2 skipped, 0 failed (offline) / 98 passed (live)**
- `[x]` Groq live smoke test: **PASSED**
- `[x]` Gemini live smoke test: **PASSED** (using `gemini-2.5-flash`)
- `[x]` Feature branch pushed to `origin/feature/phase-7-prompt-guardrails-gateway`
- `[x]` Merge into main — **UNBLOCKED**
- `[x]` v0.7.0 tag — **UNBLOCKED**

---

## 19. Gemini Workload Separation

### Shared Authentication
Both embedding generation and LLM Gateway workloads share the `GEMINI_API_KEY` configuration, but keys are routed independently to their respective SDKs/clients:
- Embedding generation uses `langchain-google-genai` `GoogleGenerativeAIEmbeddings`.
- LLM generation uses `google-genai` `genai.Client`.

### Configuration Separation
The configuration fields in `app/config.py` are strictly separated:
- **Embedding model configuration**:
  - `settings.GEMINI_EMBEDDING_MODEL` (default: `"models/gemini-embedding-2-preview"`)
  - `settings.GEMINI_EMBEDDING_DIMENSION` (default: `3072`)
- **Local fallback embedding configuration**:
  - `settings.LOCAL_EMBEDDING_MODEL` (default: `"all-mpnet-base-v2"`)
  - `settings.LOCAL_EMBEDDING_DIMENSION` (default: `768`)
- **Gateway LLM model configuration**:
  - `settings.GEMINI_MODEL` (default: `"gemini-2.5-flash"`)

A Pydantic `model_validator(mode="after")` enforces at config load time that `GEMINI_EMBEDDING_MODEL` is not equal to `GEMINI_MODEL`, preventing configuration pollution.

### Vector-Space Isolation (Strategy A)
To prevent dimension mismatch issues (e.g. writing 768 fallback vectors into a 3072 collection), Qdrant collection routing is dynamic (Strategy A). The active collection name is determined at runtime:
- Gemini active collection: `f"{settings.QDRANT_COLLECTION}_{safe_model}_3072"`
- Fallback active collection: `f"{settings.QDRANT_COLLECTION}_{safe_model}_768"`

Both the indexer (`processor.py`) and retriever (`qdrant_service.py`) call `get_active_collection_name()` to resolve the correct, dimension-matched collection name at runtime.

### Fallback Collection Readiness (Operational Limitation)
Ingestion only runs on the currently active embedding model (Gemini). The fallback collection name is dimension-safe, but is not populated during primary ingestion. If the system falls back to SentenceTransformers at query time, the resolved fallback collection will be empty unless local fallback indexing was explicitly executed separately.

### Gateway Isolation
The `LLMGateway` and its adapters do not import, invoke, or depend on the embedding generation services or Qdrant collection management.

### Release Gate Policy
The project adheres to **Policy A (Strict Dual-Provider Release Gate)**: successful live execution from both Groq and Gemini providers is mandatory. Since the Gemini live smoke test has now successfully passed with the `gemini-2.5-flash` model, the release gate is fully met, and the release status is **UNBLOCKED / PASSED**. Merge into `main` and `v0.7.0` tagging are authorized.
