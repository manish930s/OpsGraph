import time
import json
import logging
from typing import Any
from app.config import settings
from app.schemas.prompting import ModelRequest
from app.schemas.model_response import (
    ValidatedModelResponse,
    LLMExecutionMetadata,
    RCADecisionResponse,
    CriticDecisionResponse
)
from app.services.gateway.providers.groq_provider import GroqProvider
from app.services.gateway.providers.gemini_provider import GeminiProvider
from app.services.gateway.retry import BoundedRetryHandler
from app.services.gateway.errors import (
    GatewayError,
    ProviderConfigurationError,
    ProviderResponseError,
    StructuredOutputError,
    GuardrailRejectedError,
    CitationValidationError
)
logger = logging.getLogger(__name__)

def extract_json_payload(text: str) -> str:
    """
    Extracts JSON substring if wrapped in markdown code blocks or surrounding text.
    """
    text = text.strip()
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        pass

    import re
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        candidate = match.group(1).strip()
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            pass

    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        candidate = text[first_brace:last_brace + 1].strip()
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            pass

    return text

class LLMGateway:
    """
    Unified, provider-agnostic model gateway orchestrating validation, guards, retries,
    fallback routing, and structured schema conversions.
    """
    def __init__(self, retry_handler_factory=None):
        from app.services.guardrails.input_guard import DeterministicInputGuard
        from app.services.guardrails.output_guard import DeterministicOutputGuard
        from app.services.guardrails.nemo_adapter import NeMoInputGuard, NeMoOutputGuard

        self.input_guards = [DeterministicInputGuard(), NeMoInputGuard()]
        self.output_guards = [DeterministicOutputGuard(), NeMoOutputGuard()]
        self.retry_handler_factory = retry_handler_factory or (
            lambda: BoundedRetryHandler(max_retries=settings.LLM_MAX_RETRIES)
        )
        self.validate_configuration()

    def validate_configuration(self):
        """
        Validates central model settings for timeouts, retries, and credential existence.
        """
        if settings.LLM_DEFAULT_PROVIDER not in ("groq", "gemini", "mock"):
            raise ProviderConfigurationError(f"Unknown default provider: '{settings.LLM_DEFAULT_PROVIDER}'")
        
        if settings.LLM_FALLBACK_ENABLED:
            if not settings.LLM_FALLBACK_PROVIDER:
                raise ProviderConfigurationError("Fallback is enabled but LLM_FALLBACK_PROVIDER is not set.")
            if settings.LLM_FALLBACK_PROVIDER not in ("groq", "gemini", "mock"):
                raise ProviderConfigurationError(f"Unknown fallback provider: '{settings.LLM_FALLBACK_PROVIDER}'")
            if settings.LLM_FALLBACK_PROVIDER == settings.LLM_DEFAULT_PROVIDER:
                raise ProviderConfigurationError(
                    f"Fallback provider '{settings.LLM_FALLBACK_PROVIDER}' cannot be equal to "
                    f"default provider '{settings.LLM_DEFAULT_PROVIDER}'."
                )

        if settings.LLM_REQUEST_TIMEOUT_SECONDS <= 0:
            raise ProviderConfigurationError(
                f"LLM_REQUEST_TIMEOUT_SECONDS must be positive, got {settings.LLM_REQUEST_TIMEOUT_SECONDS}"
            )
        if settings.LLM_MAX_RETRIES < 0:
            raise ProviderConfigurationError(
                f"LLM_MAX_RETRIES must be non-negative, got {settings.LLM_MAX_RETRIES}"
            )

        if settings.LLM_PROVIDER != "mock":
            if settings.LLM_DEFAULT_PROVIDER == "groq" and (not settings.GROQ_API_KEY or settings.GROQ_API_KEY == "mock"):
                raise ProviderConfigurationError("GROQ_API_KEY is required for default provider 'groq'.")
            if settings.LLM_DEFAULT_PROVIDER == "gemini" and (not settings.GEMINI_API_KEY or settings.GEMINI_API_KEY == "mock"):
                raise ProviderConfigurationError("GEMINI_API_KEY is required for default provider 'gemini'.")
            
            if settings.LLM_FALLBACK_ENABLED:
                if settings.LLM_FALLBACK_PROVIDER == "groq" and (not settings.GROQ_API_KEY or settings.GROQ_API_KEY == "mock"):
                    raise ProviderConfigurationError("GROQ_API_KEY is required for fallback provider 'groq'.")
                if settings.LLM_FALLBACK_PROVIDER == "gemini" and (not settings.GEMINI_API_KEY or settings.GEMINI_API_KEY == "mock"):
                    raise ProviderConfigurationError("GEMINI_API_KEY is required for fallback provider 'gemini'.")

    def _get_provider_instance(self, provider_name: str) -> Any:
        if provider_name == "groq":
            return GroqProvider()
        elif provider_name == "gemini":
            return GeminiProvider()
        else:
            raise ProviderConfigurationError(f"Unsupported provider: '{provider_name}'")

    def generate(self, request: ModelRequest) -> ValidatedModelResponse:
        self.validate_configuration()
        start_time = time.perf_counter()
        
        # 1. Run Input Guardrails
        logger.info(f"LLMGateway: Evaluating input guardrails for request: {request.request_id}")
        for guard in self.input_guards:
            guard.evaluate(request)

        # 2. Determine initial and fallback providers
        initial_provider_name = request.provider_preference or settings.LLM_DEFAULT_PROVIDER
        fallback_provider_name = settings.LLM_FALLBACK_PROVIDER

        provider_name = initial_provider_name
        provider = self._get_provider_instance(provider_name)

        raw_content = ""
        retry_count = 0
        fallback_attempted = False
        fallback_reason = None
        finish_reason = "stop"
        usage_metadata = {}

        # 3. Request execution loop with retry & fallback
        try:
            retry_handler = self.retry_handler_factory()
            raw_content, retry_count = retry_handler.execute(lambda: provider.generate(request))
        except Exception as e:
            from app.services.gateway.errors import ProviderRateLimitError, ProviderTimeoutError, ProviderUnavailableError
            is_transient = isinstance(e, (ProviderRateLimitError, ProviderTimeoutError, ProviderUnavailableError))

            # Check if fallback is enabled and we have a different fallback provider
            if is_transient and settings.LLM_FALLBACK_ENABLED and fallback_provider_name != initial_provider_name:
                logger.warning(
                    f"Initial provider '{provider_name}' failed after {retry_count} retries. "
                    f"Initiating fallback to '{fallback_provider_name}' due to error: {str(e)}"
                )
                fallback_attempted = True
                fallback_reason = f"{type(e).__name__}: {str(e)}"
                
                # Switch to fallback provider
                provider_name = fallback_provider_name
                provider = self._get_provider_instance(provider_name)
                
                # Execute fallback request (exactly 1 transition permitted, no fallback-on-fallback)
                fallback_retry_handler = self.retry_handler_factory()
                raw_content, fallback_retries = fallback_retry_handler.execute(lambda: provider.generate(request))
                retry_count += fallback_retries
            else:
                logger.error(f"Gateway request failed on '{provider_name}' and fallback is disabled/unavailable/ineligible.")
                raise e

        # 4. Run Output Guardrails
        logger.info("LLMGateway: Evaluating output guardrails")
        cleaned_content = extract_json_payload(raw_content)
        try:
            for guard in self.output_guards:
                guard.evaluate(cleaned_content, request)
            output_guard_status = "passed"
        except GuardrailRejectedError as e:
            output_guard_status = "rejected"
            raise e
        except CitationValidationError as e:
            output_guard_status = "citation_failed"
            raise e

        # 5. Parse and Validate Response Schema
        try:
            parsed_data = json.loads(cleaned_content)
            if request.task_type == "rca":
                parsed_response = RCADecisionResponse(**parsed_data)
                response_id = parsed_response.response_id
            elif request.task_type == "critic":
                parsed_response = CriticDecisionResponse(**parsed_data)
                response_id = parsed_response.response_id
            elif request.task_type == "tool_selection":
                from app.schemas.orchestration import ToolSelectionDecision
                parsed_response = ToolSelectionDecision(**parsed_data)
                response_id = parsed_response.response_id
            else:
                parsed_response = parsed_data
                response_id = parsed_data.get("response_id", "UNKNOWN")
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            raise StructuredOutputError(f"Response failed Pydantic schema validation: {str(e)}")

        latency_ms = (time.perf_counter() - start_time) * 1000.0

        # Build Execution Metadata
        execution_metadata = LLMExecutionMetadata(
            request_id=request.request_id,
            task_type=request.task_type,
            prompt_template_id=request.prompt_template_id,
            prompt_version=request.prompt_version,
            requested_provider=request.provider_preference,
            initial_provider=initial_provider_name,
            final_provider=provider_name,
            model_id=provider.model_id,
            retry_count=retry_count,
            fallback_attempted=fallback_attempted,
            fallback_reason=fallback_reason,
            latency_ms=round(latency_ms, 2),
            finish_reason=finish_reason,
            usage_metadata=usage_metadata,
            input_guardrail_status="passed",
            output_guardrail_status=output_guard_status,
            schema_validation_status="passed",
            citation_validation_status="passed",
            degraded_mode=request.request_metadata.get("degraded_mode", False)
        )

        return ValidatedModelResponse(
            response_id=response_id,
            task_type=request.task_type,
            raw_content=raw_content,
            parsed_response=parsed_response,
            execution_metadata=execution_metadata
        )
