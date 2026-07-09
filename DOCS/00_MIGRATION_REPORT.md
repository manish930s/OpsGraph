# OpsGraph AI — Phase 7 Final Migration Report
**Document Status:** Final Verification Pass Complete  
**Phase:** Phase 7 — Prompt Assembly, Guardrails, and Provider-Agnostic LLM Gateway  
**Execution Date:** 2026-07-09  
**Python Runtime:** CPython 3.14.0 (Windows)  
**Live Verification Status:** BLOCKED — provider API keys not present in execution environment  

---

## 1. Executive Summary

Phase 7 delivers the first controlled model execution layer in OpsGraph AI. It provides a unified, provider-agnostic bridge for structured model execution between the Deterministic Context Builder (Phase 6) and the future Bounded LangGraph Investigation Engine (Phase 8). Prompt Assembly reduces prompt injection risk by structurally isolating untrusted retrieved knowledge from system instructions. Template versioning is managed via a registry. The LLM Gateway orchestrates input/output safety guards, exponential-backoff retries, one-transition provider fallback, JSON extraction, citation validation, and structured response parsing. NeMo Guardrails operates as a deferred adapter boundary; deterministic application guards are fully active.

**Default offline-safe suite**: 88 collected, **86 passed**, 0 failed, 2 skipped (opt-in live tests).  
**Groq live smoke test**: NOT EXECUTED — `GROQ_API_KEY` not present in execution environment.  
**Gemini live smoke test**: NOT EXECUTED — `GEMINI_API_KEY` not present in execution environment.  
**Merge status**: BLOCKED — live provider verification is a required pre-merge gate condition.

---

## 2. Repository State

- **Active Branch**: `feature/phase-7-prompt-guardrails-gateway`
- **Working Tree State**: Clean — no uncommitted modifications
- **Python Runtime**: CPython 3.14.0 (Windows x64)

---

## 3. Secret Safety Verification

- `.env` is listed in `.gitignore` (exact match)
- `.env.*` variants are now also listed in `.gitignore` with `!.env.example` exclusion (added in this pass)
- `git check-ignore .env` confirms `.env` is ignored
- `.env.example` is tracked and contains only placeholder empty strings — no real credentials
- `GROQ_API_KEY` available in current execution environment: **False**
- `GEMINI_API_KEY` available in current execution environment: **False**
- No API key values appear in any source file, test file, migration report, or architecture document
- Search of tracked files confirms no real credentials are staged or committed

---

## 4. File Ledger

### Files Created (Phase 7)

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
| `app/services/gateway/providers/gemini_provider.py` | Gemini SDK adapter |
| `app/services/gateway/providers/__init__.py` | Package export |
| `app/services/gateway/retry.py` | `BoundedRetryHandler` |
| `app/services/gateway/gateway.py` | `LLMGateway` orchestrator + `extract_json_payload()` |
| `app/services/gateway/__init__.py` | Package export |
| `PROJECT_CONTEXT/LLM_GATEWAY_ARCHITECTURE.md` | Architecture reference |
| `tests/unit/test_prompt_gateway.py` | Unit test suite |
| `tests/integration/test_live_gateway.py` | Opt-in live provider smoke tests |
| `pytest.ini` | Custom marker registration (`live_api`) |

### Files Modified (Phase 7)

| Path | Change |
| :--- | :--- |
| `app/config.py` | Added `LLM_PROVIDER`, `LLM_DEFAULT_PROVIDER`, `GROQ_MODEL`, `GEMINI_MODEL`, `LLM_REQUEST_TIMEOUT_SECONDS`, `LLM_MAX_RETRIES`, `LLM_FALLBACK_ENABLED`, `LLM_FALLBACK_PROVIDER` |
| `app/schemas/__init__.py` | Exported prompting and response models |
| `app/schemas/model_response.py` | Added `extra="forbid"` and citation deduplication validators |
| `requirements.txt` | Added `groq` and `google-generativeai` |
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

> **Injection Risk-Reduction Note**: This provides structural instruction-data separation. It is not a cryptographic prevention guarantee.

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

**What is validated**:
- Any `[CTX-...]` pattern anywhere in the JSON string (catches hallucinations in observation text)
- `supporting_evidence_references` list values
- `contradicting_evidence_references` list values
- `knowledge_references` list values

**What post-Pydantic validates**: `@field_validator` on `RCADecisionResponse` deduplicates reference lists preserving insertion order. This is a correctness pass, not a security pass.

---

## 9. Provider Interface

- **Protocol**: `LLMProvider` in `app/services/gateway/provider.py`
- **Contract**: `generate(request: ModelRequest) -> str`
- **Properties**: `provider_name: str`, `model_id: str`
- **Mock mode**: Both adapters return deterministic JSON when `settings.LLM_PROVIDER == "mock"`, allowing fully offline unit testing without any credentials.

---

## 10. Verified Provider Capability Matrix

| Category | Groq Adapter | Gemini Adapter |
| :--- | :--- | :--- |
| **Model Config** | `settings.GROQ_MODEL` | `settings.GEMINI_MODEL` |
| **Default Model** | `llama-3.3-70b-versatile` | `gemini-1.5-flash` |
| **SDK** | `groq` (Python SDK) | `google-generativeai` (**deprecated** — see limitations) |
| **Structured Output** | `response_format={"type": "json_object"}` | `response_mime_type="application/json"` |
| **Temperature** | `0.0` hardcoded | `0.0` hardcoded |
| **Timeout** | Passed to Groq SDK `timeout=` | Passed via `request_options={"timeout": ...}` |
| **Usage Metadata** | Not extracted — default `{}` | Not extracted — default `{}` |
| **Provider Request ID** | Not extracted — default `None` | Not extracted — default `None` |
| **Finish Reason** | Not extracted — hardcoded `"stop"` | Not extracted — hardcoded `"stop"` |
| **Rate-Limit** | HTTP 429 → `ProviderRateLimitError` | `ResourceExhausted` → `ProviderRateLimitError` |
| **Auth Failure** | HTTP 401/403 → `ProviderAuthenticationError` | `PermissionDenied` → `ProviderAuthenticationError` |
| **Timeout Mapping** | `APITimeoutError` → `ProviderTimeoutError` | `DeadlineExceeded` → `ProviderTimeoutError` |
| **Connection Error** | `APIConnectionError` → `ProviderUnavailableError` | `GoogleAPIError` → `ProviderUnavailableError` |
| **Live Smoke-Test** | NOT EXECUTED — API key unavailable | NOT EXECUTED — API key unavailable |

---

## 11. Retry Policy

- **Handler**: `BoundedRetryHandler` (`app/services/gateway/retry.py`)
- **Max retries**: `settings.LLM_MAX_RETRIES` (default: 3)
- **Backoff**: Exponential, initial 0.5s, factor 2.0x
- **Retryable**: `ProviderRateLimitError`, `ProviderTimeoutError`, `ProviderUnavailableError`
- **Non-retryable**: `ProviderConfigurationError`, `ProviderAuthenticationError`, `GuardrailRejectedError`, `CitationValidationError`, `StructuredOutputError`

---

## 12. Fallback Policy

- **Trigger condition**: Transient error, retries exhausted, `LLM_FALLBACK_ENABLED=True`, fallback provider configured and differs from initial
- **Maximum transitions**: **1** (no ping-pong)
- **Orientation**: Availability-only — no quality, latency, or cost routing
- **Metadata**: `fallback_attempted`, `fallback_reason`, `final_provider` truthfully reflect any transition

---

## 13. NeMo Runtime Status

- **Status**: Deferred — `nemoguardrails` fails to compile on Python 3.14.0 / Windows
- **Active guards**: `DeterministicInputGuard` and `DeterministicOutputGuard` are fully active
- **Adapter boundary**: `NeMoInputGuard` and `NeMoOutputGuard` exist, are instantiated, log a warning, and pass through
- **Production requirement**: Python 3.11 environment before enabling NeMo

---

## 14. Default Test Suite

**Command**: `.\venv\Scripts\python.exe -m pytest`  
**Config file**: `pytest.ini`  

| Metric | Count |
| :--- | :--- |
| Collected | 88 |
| Passed | 86 |
| Failed | 0 |
| Skipped | 2 |
| Warnings | 1 |

**Warning**: `FutureWarning` from `google-generativeai` — the SDK is fully deprecated and will be replaced by `google-genai`. Functional impact: none today.

**Skipped tests**: Both are in `tests/integration/test_live_gateway.py`. They skip when `GROQ_API_KEY` / `GEMINI_API_KEY` is absent from the environment, regardless of `RUN_LIVE_TESTS` value. The outer `pytestmark` `skipif` fires when `RUN_LIVE_TESTS` is unset; the inner `@pytest.mark.skipif` fires when the specific key is absent.

---

## 15. Live Smoke Tests

**Groq live test command**: `$env:RUN_LIVE_TESTS="true"; .\venv\Scripts\python.exe -m pytest tests/integration/test_live_gateway.py::test_live_groq_smoke -v`  
**Groq live test — executed**: 2026-07-09. `RUN_LIVE_TESTS=true` was set. `GROQ_API_KEY` was absent from the execution environment (no `.env` file present, key not in `os.environ`).  
**GROQ LIVE SMOKE TEST: NOT EXECUTED — API key unavailable in execution environment** (1 skipped, 0 passed, 0 failed)

**Gemini live test command**: `$env:RUN_LIVE_TESTS="true"; .\venv\Scripts\python.exe -m pytest tests/integration/test_live_gateway.py::test_live_gemini_smoke -v`  
**Gemini live test — executed**: 2026-07-09. `RUN_LIVE_TESTS=true` was set. `GEMINI_API_KEY` was absent from the execution environment.  
**GEMINI LIVE SMOKE TEST: NOT EXECUTED — API key unavailable in execution environment** (1 skipped, 0 passed, 0 failed)

**Skip mechanism verified**: Each test skips independently with its own `@pytest.mark.skipif(not os.environ.get("GROQ_API_KEY"), ...)` guard. One provider's missing key does not block the other. The skip is clean — no error, no assertion failure.

**Credential loading verification**: `settings.GROQ_API_KEY` and `settings.GEMINI_API_KEY` both resolved to `None`. Pydantic Settings `env_file=".env"` resolved to `D:\Advance RAG\opsgraph-ai\.env` which does not exist. Neither key is set in the OS environment. No `.env` file exists anywhere in the workspace.

**Required action for live verification**: Place a `.env` file at `D:\Advance RAG\opsgraph-ai\.env` containing `GROQ_API_KEY` and `GEMINI_API_KEY`, then rerun with `$env:RUN_LIVE_TESTS="true"`.


## 16. Technical Debt Assessment

| Item | Classification | Detail |
| :--- | :--- | :--- |
| Token estimation (word-based) | Current Limitation | `len(prompt.split())` used for budget — diverges from BPE token counts |
| `google-generativeai` deprecated | Operational Concern (Active) | Must migrate to `google-genai` SDK before security updates end |
| Usage metadata not extracted | Current Limitation | `usage_metadata={}` always; token accounting unavailable |
| Finish reason not extracted | Current Limitation | `finish_reason="stop"` hardcoded; stop sequence vs. max-tokens unknown |
| Provider request ID not extracted | Current Limitation | `None` always; provider support escalation impaired |
| Live provider verification | Operational Concern | No live tests executed; real provider behavior not confirmed |
| SDK version pinning in `requirements.txt` | Deferred Decision | Unpinned in dev; pinned in `requirements-prod.txt` only |
| Gemini structured output mode | Operational Concern | `response_mime_type` requests JSON but doesn't guarantee schema compliance |
| Quota / rate-limit behavior | Operational Concern | Provider quotas are operational conditions; retry exhaustion propagates to caller |
| Fallback availability-only | Architectural Decision | No quality-based, latency-based, or cost-based routing |
| Model quality evaluation | Not Implemented | No systematic quality comparison between Groq and Gemini |
| Cost-aware routing | Not Implemented | Gateway selects by config and availability only |
| Persistent execution tracing | Current Limitation | Metadata in-memory only; no trace store persistence |
| Prompt version migration policy | Deferred Decision | No formal deprecation or migration policy for old template versions |
| NeMo runtime | Deferred Decision | Python 3.11 standardization required before activation |

---

## 17. Phase 8 Bounded Orchestration Boundary

Phase 8 (LangGraph Investigation Engine) must implement a bounded, deterministic state graph. Required design constraints:

- Typed investigation state schema
- Explicit node contracts (single responsibility per node)
- Maximum iteration count with explicit termination conditions
- Conditional deterministic routing — no open-ended autonomy
- Tool allowlist per node
- Explicit failure and uncertainty states
- Human-review routing when confidence remains below threshold after max iterations

**Phase 8 must not introduce**: FastAPI, Streamlit, evaluation frameworks, direct repository access, or direct vector store access.

---

## 18. Exit Checklist

- `[x]` Active branch: `feature/phase-7-prompt-guardrails-gateway`
- `[x]` `.env` verified ignored by git (`git check-ignore .env` → `.env`)
- `[x]` `.env.*` variants ignored; `.env.example` tracked (`git ls-files .env.example` → present)
- `[x]` No API key values in any source file, test, or documentation
- `[x]` GROQ_API_KEY availability checked — **False** (key not present in environment or `.env` file)
- `[x]` GEMINI_API_KEY availability checked — **False** (key not present in environment or `.env` file)
- `[x]` Output pipeline traced from actual code — documented accurately
- `[x]` Architecture diagram matches implementation
- `[x]` JSON extraction responsibility is explicit (`extract_json_payload` module function)
- `[x]` Output Guard responsibility is explicit (pipeline façade — documented)
- `[x]` Citation validation source of truth is `ModelRequest.context_references`
- `[x]` Provider capability matrix verified against adapter code
- `[x]` Test summary wording is mathematically correct
- `[x]` Technical debt section covers real operational limitations
- `[x]` NeMo status remains truthful (deferred, not active)
- `[x]` Phase 8 remains bounded orchestration — no LangGraph code introduced
- `[x]` `requirements.txt` updated with `groq` and `google-generativeai`
- `[x]` Live tests fixed: single-provider smoke tests disable fallback
- `[x]` Default suite: **86 passed, 2 skipped, 0 failed** (confirmed 2026-07-09)
- `[!]` Groq live smoke test: **NOT EXECUTED** — `GROQ_API_KEY` unavailable — **MERGE BLOCKER**
- `[!]` Gemini live smoke test: **NOT EXECUTED** — `GEMINI_API_KEY` unavailable — **MERGE BLOCKER**
- `[x]` Feature branch pushed to `origin/feature/phase-7-prompt-guardrails-gateway`
- `[ ]` Merge into main — **BLOCKED** — live provider tests must pass first
- `[ ]` v0.7.0 tag — **BLOCKED** — merge must complete first
