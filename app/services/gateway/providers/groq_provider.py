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

class GroqProvider(LLMProvider):
    """
    Adapter for Groq LLM API. normalizes request/response mapping and wraps SDK exceptions.
    """
    def __init__(self, api_key: str | None = None, model_name: str | None = None):
        self._api_key = api_key or settings.GROQ_API_KEY
        self._model_id = model_name or settings.GROQ_MODEL

    @property
    def provider_name(self) -> str:
        return "groq"

    @property
    def model_id(self) -> str:
        return self._model_id

    def generate(self, request: ModelRequest) -> str:
        # Check for mock setting for safety in tests/offline sandbox
        if settings.LLM_PROVIDER == "mock":
            time.sleep(0.01)
            ref_str = request.context_references[0] if request.context_references else "CTX-E1"
            return (
                '{\n'
                '  "response_id": "RCA-MOCK-12345",\n'
                '  "task_type": "rca",\n'
                '  "summary": "Mocked analysis showing database connection saturation.",\n'
                f'  "observations": ["Checkout-service database thread pool saturated ({ref_str})"],\n'
                '  "hypotheses": ["Surge in user traffic exhausting db resources."],\n'
                f'  "supporting_evidence_references": ["{ref_str}"],\n'
                '  "contradicting_evidence_references": [],\n'
                '  "knowledge_references": [],\n'
                '  "uncertainty_statements": ["Network layer packet drops unknown."],\n'
                '  "recommended_next_steps": ["Scale connection pool count."]\n'
                '}'
            )

        if not self._api_key or self._api_key == "mock":
            raise ProviderConfigurationError("Groq API key is missing or invalid.")

        from groq import Groq, APIConnectionError, APITimeoutError, APIStatusError

        try:
            client = Groq(api_key=self._api_key)
            response = client.chat.completions.create(
                model=self._model_id,
                messages=[
                    {"role": "system", "content": request.system_message},
                    {"role": "user", "content": request.user_message}
                ],
                temperature=0.0,
                response_format={"type": "json_object"},
                timeout=request.timeout_configuration
            )
            if not response.choices or not response.choices[0].message.content:
                raise ProviderResponseError("Groq API returned an empty choices payload.")
            return response.choices[0].message.content

        except APITimeoutError as e:
            raise ProviderTimeoutError(f"Groq API call timed out: {str(e)}")
        except APIConnectionError as e:
            raise ProviderUnavailableError(f"Groq service is unreachable: {str(e)}")
        except APIStatusError as e:
            if e.status_code in (401, 403):
                raise ProviderAuthenticationError(f"Groq authentication failed: {str(e)}")
            elif e.status_code == 429:
                raise ProviderRateLimitError(f"Groq rate limit exceeded: {str(e)}")
            else:
                raise ProviderUnavailableError(f"Groq API returned status code {e.status_code}: {str(e)}")
        except Exception as e:
            raise ProviderUnavailableError(f"Unexpected Groq adapter error: {str(e)}")
