# LLM Gateway, Prompt Assembly, and Guardrails Architecture (Phase 7)
**Document Status:** Final Verification Pass Complete  
**Authoritative Reference:** Controlled Model Execution, Provider Abstraction, and Fallback Policies  

---

## 1. Phase Boundary

Phase 7 introduces the first controlled model execution layer in OpsGraph AI. It sits between the Deterministic Context Builder (Phase 6) and the future Bounded LangGraph Investigation Engine (Phase 8).

The flow is strictly unidirectional: **context-in → structured-response-out**. The only authoritative model input is a validated `InvestigationContext` transformed through the Prompt Assembly layer. Raw telemetry, repositories, tools, vector stores, and evaluation truth are inaccessible to model providers.

---

## 2. Actual Output Pipeline (Verified from Code)

The following is the **exact call sequence** as implemented in `gateway.py`:

```
InvestigationContext
    |
    v  PromptAssembler.assemble()
ModelRequest  (immutable Pydantic, context_references tuple)
    |
    v  DeterministicInputGuard.evaluate()  +  NeMoInputGuard.evaluate() (deferred)
Validated ModelRequest
    |
    v  BoundedRetryHandler.execute(provider.generate)
Raw provider string  (may contain markdown fences or surrounding prose)
    |
    v  extract_json_payload()  [gateway.py module function]
Clean JSON string
    |
    v  DeterministicOutputGuard.evaluate()  [façade — see §5]
       + NeMoOutputGuard.evaluate() (deferred)
Policy-validated JSON string
    |
    v  json.loads() + Pydantic RCADecisionResponse(**parsed_data)
Typed Pydantic model  (field_validator deduplicates citation lists)
    |
    v  ValidatedModelResponse  (typed response + LLMExecutionMetadata)
```

---

## 3. Prompt Assembly Layer

- **Service**: `PromptAssembler` (`app/services/prompting/assembler.py`)
- **Input**: `InvestigationContext`
- **Output**: Immutable `ModelRequest`
- **Template Registry**: `PromptRegistry` loads templates from `prompts/rca/` by version key.

### Injection Risk-Reduction Boundary
The assembler separates instruction from data at compile time:
1. System instructions (`system_v1.txt`) define the strict SRE role constraints before any user data is seen.
2. Retrieved operational knowledge is wrapped inside structural XML tags `<untrusted_knowledge_context>` in the user message.
3. The system prompt explicitly instructs the model to treat this block as read-only data.

> **Note**: This provides structural instruction-data separation. It is not a cryptographic or mathematical injection prevention guarantee.

---

## 4. Provider-Agnostic LLM Gateway

- **Protocol**: `LLMProvider` (`app/services/gateway/provider.py`) — `generate(request: ModelRequest) -> str`
- **Configuration Validation**: `LLMGateway.validate_configuration()` runs at construction and before each `generate()` call.

### Provider Capability Matrix (Verified Against Adapter Code)

| Category | Groq Adapter | Gemini Adapter |
| :--- | :--- | :--- |
| **Config Key** | `LLM_DEFAULT_PROVIDER = "groq"` | `LLM_DEFAULT_PROVIDER = "gemini"` |
| **Model Config** | `settings.GROQ_MODEL` (default: `llama-3.3-70b-versatile`) | `settings.GEMINI_MODEL` (default: `gemini-2.5-flash`) |
| **SDK** | `groq` (Groq Python SDK) | `google-genai` (Migrated successfully) |
| **Structured Output Mode** | `response_format={"type": "json_object"}` | `response_mime_type="application/json"` |
| **Temperature** | `0.0` (hardcoded deterministic) | `0.0` (hardcoded deterministic) |
| **Timeout** | `request.timeout_configuration` → Groq SDK `timeout=` param | `request.timeout_configuration` → types.GenerateContentConfig |
| **Usage Metadata** | Not extracted by adapter | Not extracted by adapter |
| **Provider Request ID** | Not extracted by adapter | Not extracted by adapter |
| **Finish Reason** | Not extracted; hardcoded `"stop"` in gateway | Not extracted; hardcoded `"stop"` in gateway |
| **Rate-Limit Mapping** | `APIStatusError` HTTP 429 → `ProviderRateLimitError` | `RESOURCE_EXHAUSTED` → `ProviderRateLimitError` |
| **Auth Failure Mapping** | `APIStatusError` HTTP 401/403 → `ProviderAuthenticationError` | `401/403/permission` → `ProviderAuthenticationError` |
| **Timeout Mapping** | `APITimeoutError` → `ProviderTimeoutError` | `timeout/deadline` → `ProviderTimeoutError` |
| **Connection Error Mapping** | `APIConnectionError` → `ProviderUnavailableError` | `GoogleAPIError` → `ProviderUnavailableError` |
| **Mock Mode** | Returns deterministic JSON when `LLM_PROVIDER = "mock"` | Returns deterministic JSON when `LLM_PROVIDER = "mock"` |
| **Live Smoke-Test Status** | **PASSED** (2.73s) | **PASSED** (8.05s) |

### Workload Configuration Separation
`GeminiProvider` is used exclusively for LLM text generation. It does **not** import, invoke, or depend on any embedding models or Qdrant collection management. 
- **LLM Generation Model**: Configured via `settings.GEMINI_MODEL` (default: `gemini-2.5-flash`).
- **Embedding Model**: Configured separately via `settings.GEMINI_EMBEDDING_MODEL` (default: `models/gemini-embedding-2-preview`).
A Pydantic `model_validator` in `config.py` prevents accidental reuse or config leakage between the two workloads.

---

## 5. Output Guard Responsibility (Verified Façade)

`DeterministicOutputGuard.evaluate(content, request)` is a **pipeline façade** that performs all of the following in sequence:

1. **Empty check** — raises `GuardrailRejectedError` if content is empty.
2. **JSON format validation** — `json.loads(content)`; raises `GuardrailRejectedError` on `JSONDecodeError`.
3. **Text-level citation scan** — `re.findall(r"\[(CTX-[a-zA-Z0-9_\-]+)\]", content)` against all raw JSON text; raises `CitationValidationError` for any hallucinated reference not in `ModelRequest.context_references`.
4. **Typed list citation validation** — iterates `supporting_evidence_references`, `contradicting_evidence_references`, and `knowledge_references` lists from the parsed JSON dict; raises `CitationValidationError` for any reference absent from `ModelRequest.context_references`.
5. **RCA empty-citation policy** — for `task_type == "rca"`, at least one of: observations, supporting evidence references, or uncertainty statements must be non-empty; raises `CitationValidationError` otherwise.
6. **Response-size policy** — raises `GuardrailRejectedError` if `len(content) > 100000`.

> **Architecture note**: Citation validation occurs **before** Pydantic schema parsing. This means the output guard operates on the raw cleaned JSON string. Pydantic `RCADecisionResponse` provides a second deduplication pass via `@field_validator` after parsing, but citation membership is fully validated by the output guard.

---

## 6. Citation Validation Architecture

**Citation validation is hybrid**: text-level regex scan + typed list field validation.

**Source of truth**: `ModelRequest.context_references` — the exact set of citation IDs included in the assembled prompt. This is not the full Phase 6 context, not all repository evidence IDs, and not all knowledge chunk IDs in storage. If the Context Builder excluded some items from the prompt budget, those IDs are absent from `context_references` and will correctly fail validation if referenced in model output.

**Validated citation types**:
- `[CTX-...]` patterns embedded in any string field (observations, summaries, hypotheses)
- `supporting_evidence_references` list
- `contradicting_evidence_references` list
- `knowledge_references` list

**Pydantic-level deduplication**: `RCADecisionResponse` and `CriticDecisionResponse` carry `@field_validator` that deduplicates reference lists preserving original order before schema validation.

---

## 7. Retry and Fallback Policies

### Retryable Exceptions (Transient)
Retried with exponential backoff up to `LLM_MAX_RETRIES` (default: 3):
- `ProviderRateLimitError`
- `ProviderTimeoutError`
- `ProviderUnavailableError`

### Non-Retryable Exceptions (Permanent — propagate immediately)
- `ProviderConfigurationError`
- `ProviderAuthenticationError`
- `GuardrailRejectedError`
- `CitationValidationError`
- `StructuredOutputError`

### Fallback Policy
- Fallback triggers only after: retry policy exhausted on a **transient** error, `LLM_FALLBACK_ENABLED=True`, a fallback provider is configured, and it differs from the initial provider.
- **Maximum transitions: 1**. If the fallback provider also fails, the error propagates without further retry.
- Fallback is availability-oriented, not quality-oriented. No cost-based or latency-based routing exists.

---

## 8. Execution Metadata Fields

| Field | Truthful Population |
| :--- | :--- |
| `request_id` | From `ModelRequest.request_id` |
| `task_type` | From `ModelRequest.task_type` |
| `prompt_template_id` | From `ModelRequest.prompt_template_id` |
| `prompt_version` | From `ModelRequest.prompt_version` |
| `requested_provider` | From `ModelRequest.provider_preference` (may be `None`) |
| `initial_provider` | Provider name resolved at start of execution |
| `final_provider` | Provider name after possible fallback transition |
| `model_id` | From `provider.model_id` property |
| `retry_count` | Actual retry attempts (0 = success on first try) |
| `fallback_attempted` | `True` only if a provider transition occurred |
| `fallback_reason` | Exception class + message if fallback occurred, else `None` |
| `latency_ms` | Measured via `time.perf_counter()` |
| `finish_reason` | Hardcoded `"stop"` — **not extracted from provider SDK** (limitation) |
| `usage_metadata` | Always `{}` — **not extracted from provider SDK** (limitation) |
| `input_guardrail_status` | `"passed"` (only success path reaches this point) |
| `output_guardrail_status` | `"passed"`, `"rejected"`, or `"citation_failed"` |
| `schema_validation_status` | `"passed"` (only success path reaches this point) |
| `citation_validation_status` | `"passed"` (only success path reaches this point) |
| `degraded_mode` | From `request.request_metadata.get("degraded_mode", False)` |

---

## 9. NeMo Guardrails Status

- **Runtime Status**: Deferred. `nemoguardrails` requires native extension compilation that fails on Python 3.14.0 on Windows.
- **Adapter Boundary**: `NeMoInputGuard` and `NeMoOutputGuard` exist in `app/services/guardrails/nemo_adapter.py` and are instantiated in `LLMGateway.__init__`. They gracefully log a warning and pass through without enforcement.
- **Active Guards**: `DeterministicInputGuard` and `DeterministicOutputGuard` are fully active.
- **Production requirement**: Standardize on Python 3.11 before enabling NeMo runtime.

---

## 10. Technical Debt and Operational Limitations

### Token Estimation — *Current Limitation*
Context budget limits are estimated using word-splitting (`len(prompt.split())`). Model-native tokenizers (e.g., tiktoken) are required for production accuracy. Word counts diverge from BPE token counts depending on vocabulary and language.

### google-genai SDK Migration — *Completed*
The Gemini adapter was successfully migrated from the deprecated `google-generativeai` package to the modern, supported `google-genai` SDK. The old `google-generativeai` SDK deprecation warning is fully resolved.

### google-genai Internals warning — *Python Compatibility Warning*
The new `google-genai` SDK (specifically `google/genai/types.py`) emits a `DeprecationWarning` under Python 3.14.0 regarding `_UnionGenericAlias` which is slated for removal in Python 3.17. This warning is internal to the SDK's types submodule and has no functional impact on runtime execution.

### Live Provider Verification Status — *Operational Status (2026-07-09)*
- **Groq (Llama 3.3)**: **PASSED** (2.73s, using key in `.env`). Basic connectivity, response formatting, extraction, and validation are verified.
- **Gemini (Gemini 2.5 Flash)**: **PASSED** (8.05s, using key in `.env`). Full generation, structured parsing, extraction, and validation are verified.

### Usage Metadata and Finish Reason Not Extracted — *Current Limitation*
Neither the Groq nor Gemini adapter currently extracts `usage_metadata` (token counts) or `finish_reason` from the actual provider SDK response. These fields exist in `LLMExecutionMetadata` but are populated with defaults. Extracting them would improve observability and token-cost accounting.

### Provider Request ID Not Extracted — *Current Limitation*
Neither adapter captures the provider-side request ID from response headers/metadata. This field exists in `LLMExecutionMetadata` but is `None` in practice. Provider request IDs are important for support escalations.

### Live Provider Verification — *Operational Status (2026-07-09)*
Live tests were executed by opting-in with `RUN_LIVE_TESTS=true`:
- **Groq (Llama 3.3)**: **PASSED**. Full content generation, structured parsing, extraction, and validation are verified.
- **Gemini (Gemini 2.5 Flash)**: **PASSED** (8.05s). Client instantiation, credential loading, connection, content generation, and deterministic output schema parsing are verified.

### Provider SDK Version Pinning — *Deferred Decision*
`requirements.txt` declares `groq` and `google-genai` without version pins. `requirements-prod.txt` pins versions for production Cloud Run. Local development reproducibility depends on pip resolution at install time.

### Structured Output Mode Differences — *Operational Concern*
- **Groq**: Uses `response_format={"type": "json_object"}`. The model is instructed to produce JSON; the API enforces JSON tokenization constraints.
- **Gemini**: Uses `response_mime_type="application/json"` in `types.GenerateContentConfig`. The API returns content typed as JSON but does not guarantee schema compliance.
- In both cases, `extract_json_payload()` strips any markdown fences before the output guard processes content.

### Quota and Rate-Limit Behavior — *Operational Concern*
Provider quotas and free-tier availability are operational conditions, not architectural guarantees. Both adapters map rate-limit responses to `ProviderRateLimitError`, which triggers retry with backoff. Quota exhaustion that persists beyond retry limits will propagate to the caller.

### Fallback Limitations — *Architectural Decision, Documented*
- Maximum 1 provider transition per request.
- Fallback is only available for transient failures.
- Fallback is availability-oriented: if Groq is unavailable, Gemini is tried. There is no quality-based routing, cost optimization, or latency-based routing.

### Model Quality Evaluation — *Not Implemented*
No systematic quality comparison between Groq (Llama 3.3) and Gemini (Gemini 2.5 Flash) exists. Provider quality routing is not implemented.

### Cost-Aware Routing — *Not Implemented*
Request-cost optimization is not implemented. The gateway selects providers based on configuration and availability only.

### Persistent Execution Tracing — *Current Limitation*
Execution metadata is returned in `ValidatedModelResponse.execution_metadata` and may be emitted to Logfire/LangSmith if configured, but is not persisted to a dedicated trace store. No structured trace query interface exists.

### Prompt Version Migration Policy — *Deferred Decision*
Templates are loaded by version string. There is no formal policy governing deprecation of old template versions, migration pathways, or backward compatibility windows. This is a deferred operational decision.

---

## 11. Phase 8 Bounded Orchestration Boundary

LangGraph is an orchestration layer for Phase 8. It must **not** be used for uncontrolled multi-agent autonomy.

The Phase 8 graph structure must remain bounded and deterministic:
1. **Typed State Schema**: Explicit `TypedDict` or Pydantic investigation state.
2. **Explicit Node Contracts**: Each node has a single responsibility (evidence collection, runbook matching, hypothesis generation, critic evaluation, decision).
3. **Bounded Iterations**: Maximum loop count parameter; termination condition on confidence threshold or evidence sufficiency.
4. **Deterministic Routing**: Conditional edges based on explicit typed flags in graph state.
5. **Tool Allowlist**: Strict control over tool parameters and per-invocation execution limits.
6. **Failure States**: Explicit failure nodes for tool errors, citation failures, and model refusals.
7. **Human-Review Boundary**: If confidence remains below threshold after max iterations, route to human-review state rather than producing an uncertain automated decision.

Phase 8 must not implement, import, or depend on:
- FastAPI
- Streamlit
- Evaluation frameworks
- Direct telemetry repository access
- Raw vector store access
- NeMo Guardrails (until Python 3.11 environment is standardized)
