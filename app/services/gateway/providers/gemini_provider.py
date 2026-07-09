import time
from app.config import settings
from app.schemas.prompting import ModelRequest
from app.services.gateway.provider import LLMProvider
from app.services.gateway.errors import (
    ProviderConfigurationError,
    ProviderAuthenticationError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    ProviderResponseError
)


class GeminiProvider(LLMProvider):
    """
    Adapter for Google Gemini generative AI models.

    Uses the google-genai SDK (google.genai), the supported successor to the
    deprecated google-generativeai (google.generativeai) package.
    SDK version: google-genai >= 1.0.0
    """

    def __init__(self, api_key: str | None = None, model_name: str | None = None):
        self._api_key = api_key or settings.GEMINI_API_KEY
        self._model_id = model_name or settings.GEMINI_MODEL

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def model_id(self) -> str:
        return self._model_id

    def generate(self, request: ModelRequest) -> str:
        # Mock mode: return deterministic JSON without making any API call.
        if settings.LLM_PROVIDER == "mock":
            time.sleep(0.01)
            ref_str = request.context_references[0] if request.context_references else "CTX-E1"
            return (
                '{\n'
                '  "response_id": "RCA-MOCK-67890",\n'
                '  "task_type": "rca",\n'
                '  "summary": "Mocked Gemini analysis for database connection saturation.",\n'
                f'  "observations": ["Checkout-service database thread pool saturated ({ref_str})"],\n'
                '  "hypotheses": ["Slow database transactions causing thread saturation."],\n'
                f'  "supporting_evidence_references": ["{ref_str}"],\n'
                '  "contradicting_evidence_references": [],\n'
                '  "knowledge_references": [],\n'
                '  "uncertainty_statements": ["Missing detailed network latency logs."],\n'
                '  "recommended_next_steps": ["Check network layer metrics."]\n'
                '}'
            )

        if not self._api_key or self._api_key == "mock":
            raise ProviderConfigurationError("Gemini API key is missing or invalid.")

        from google import genai
        from google.genai import types

        try:
            client = genai.Client(api_key=self._api_key)

            config = types.GenerateContentConfig(
                system_instruction=request.system_message,
                response_mime_type="application/json",
                temperature=0.0,
            )

            response = client.models.generate_content(
                model=self._model_id,
                contents=request.user_message,
                config=config,
            )

            if not response.text:
                raise ProviderResponseError("Gemini API returned an empty text completion.")
            return response.text

        except (ProviderConfigurationError, ProviderResponseError):
            raise

        except Exception as e:
            # Map SDK exceptions to gateway error hierarchy.
            # The google-genai SDK surfaces errors via google.genai.errors or
            # google.api_core.exceptions; we inspect the string representation
            # to avoid importing optional sub-modules.
            error_str = str(e)
            lower = error_str.lower()

            if any(code in error_str for code in ("401", "403")) or "permission" in lower or "unauthenticated" in lower:
                raise ProviderAuthenticationError(f"Gemini authentication failed: {error_str}")
            elif "429" in error_str or "resource exhausted" in lower or "quota" in lower or "rate" in lower:
                raise ProviderRateLimitError(f"Gemini rate limit or quota exceeded: {error_str}")
            elif "timeout" in lower or "deadline exceeded" in lower or "timed out" in lower:
                raise ProviderTimeoutError(f"Gemini API request timed out: {error_str}")
            else:
                raise ProviderUnavailableError(f"Gemini service error: {error_str}")
