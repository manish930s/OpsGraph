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
    Adapter for Google Gemini generative AI models. wraps SDK exceptions.
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
        # Check for mock setting or missing api key for safety in tests/offline sandbox
        if settings.LLM_PROVIDER == "mock" or not self._api_key or self._api_key == "mock":
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

        import google.generativeai as genai
        from google.api_core.exceptions import GoogleAPIError, DeadlineExceeded, PermissionDenied, ResourceExhausted

        try:
            genai.configure(api_key=self._api_key)
            model = genai.GenerativeModel(
                model_name=self._model_id,
                system_instruction=request.system_message
            )
            
            generation_config = genai.types.GenerationConfig(
                response_mime_type="application/json",
                temperature=0.0
            )

            request_options = {}
            if request.timeout_configuration:
                request_options["timeout"] = request.timeout_configuration

            response = model.generate_content(
                request.user_message,
                generation_config=generation_config,
                request_options=request_options
            )
            
            if not response.text:
                raise ProviderResponseError("Gemini API returned an empty text completion.")
            return response.text

        except DeadlineExceeded as e:
            raise ProviderTimeoutError(f"Gemini API request timed out: {str(e)}")
        except PermissionDenied as e:
            raise ProviderAuthenticationError(f"Gemini API permission denied: {str(e)}")
        except ResourceExhausted as e:
            raise ProviderRateLimitError(f"Gemini API rate limit or quota exceeded: {str(e)}")
        except GoogleAPIError as e:
            raise ProviderUnavailableError(f"Gemini service error: {str(e)}")
        except Exception as e:
            raise ProviderUnavailableError(f"Unexpected Gemini adapter error: {str(e)}")
