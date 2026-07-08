import os
import pytest
from app.config import settings
from app.schemas.prompting import ModelRequest
from app.services.gateway import LLMGateway
from app.services.gateway.providers.groq_provider import GroqProvider
from app.services.gateway.providers.gemini_provider import GeminiProvider

RUN_LIVE = os.environ.get("RUN_LIVE_TESTS", "").lower() in ("true", "1", "yes")

# Mark all tests in this file as live_api and skip if not RUN_LIVE
pytestmark = [
    pytest.mark.live_api,
    pytest.mark.skipif(not RUN_LIVE, reason="Live API tests not enabled. Set RUN_LIVE_TESTS=true to run them.")
]

@pytest.fixture
def minimal_request():
    return ModelRequest(
        request_id="REQ-LIVE-SMOKE-TEST",
        task_type="rca",
        prompt_template_id="investigation",
        prompt_version="v1",
        system_message="You are a JSON producer. You must return exactly a JSON object.",
        user_message=(
            "Generate a JSON complying with schema:\n"
            "{\n"
            '  "response_id": "RCA-LIVE-1",\n'
            '  "task_type": "rca",\n'
            '  "summary": "Live smoke test successful.",\n'
            '  "observations": ["Observation 1 [CTX-1]"],\n'
            '  "hypotheses": ["Hypothesis 1"],\n'
            '  "supporting_evidence_references": ["CTX-1"],\n'
            '  "contradicting_evidence_references": [],\n'
            '  "knowledge_references": [],\n'
            '  "uncertainty_statements": [],\n'
            '  "recommended_next_steps": []\n'
            "}"
        ),
        context_references=("CTX-1",)
    )

@pytest.mark.skipif(not os.environ.get("GROQ_API_KEY"), reason="GROQ_API_KEY not set in environment.")
def test_live_groq_smoke(minimal_request):
    # Temporarily set provider config to live to bypass mock checks.
    # Disable fallback so validate_configuration does not require the fallback provider key.
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(settings, "LLM_PROVIDER", "live")
        mp.setattr(settings, "LLM_DEFAULT_PROVIDER", "groq")
        mp.setattr(settings, "LLM_FALLBACK_ENABLED", False)

        gateway = LLMGateway()
        response = gateway.generate(minimal_request)

        assert response.response_id == "RCA-LIVE-1"
        assert response.task_type == "rca"
        assert response.execution_metadata.final_provider == "groq"
        assert response.execution_metadata.latency_ms > 0
        assert "CTX-1" in response.parsed_response.supporting_evidence_references
        assert response.execution_metadata.fallback_attempted is False

@pytest.mark.skipif(not os.environ.get("GEMINI_API_KEY"), reason="GEMINI_API_KEY not set in environment.")
def test_live_gemini_smoke(minimal_request):
    # Temporarily set provider config to live to bypass mock checks.
    # Disable fallback so validate_configuration does not require the fallback provider key.
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(settings, "LLM_PROVIDER", "live")
        mp.setattr(settings, "LLM_DEFAULT_PROVIDER", "gemini")
        mp.setattr(settings, "LLM_FALLBACK_ENABLED", False)

        gateway = LLMGateway()
        response = gateway.generate(minimal_request)

        assert response.response_id == "RCA-LIVE-1"
        assert response.task_type == "rca"
        assert response.execution_metadata.final_provider == "gemini"
        assert response.execution_metadata.latency_ms > 0
        assert "CTX-1" in response.parsed_response.supporting_evidence_references
        assert response.execution_metadata.fallback_attempted is False
