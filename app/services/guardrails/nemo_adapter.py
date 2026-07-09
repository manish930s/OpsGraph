import logging
from app.schemas.prompting import ModelRequest
from app.services.guardrails.base import InputGuard, OutputGuard

logger = logging.getLogger(__name__)

class NeMoInputGuard(InputGuard):
    """
    NeMo Guardrails input adapter with deferred execution fallback checks.
    """
    def __init__(self):
        self.is_compatible = False
        try:
            import nemoguardrails
            self.is_compatible = True
        except ImportError:
            logger.warning(
                "NeMo Guardrails package not found. NeMoInputGuard operates in deferred fallback mode."
            )

    def evaluate(self, request: ModelRequest) -> None:
        if not self.is_compatible:
            # Fallback to deterministic guards (handled in gateway)
            logger.info("NeMoInputGuard: Skipped (deferred mode). Fallback to DeterministicInputGuard active.")
            return
        # Live NeMo Guardrails evaluation would happen here in Python 3.11 environment.
        pass

class NeMoOutputGuard(OutputGuard):
    """
    NeMo Guardrails output adapter with deferred execution fallback checks.
    """
    def __init__(self):
        self.is_compatible = False
        try:
            import nemoguardrails
            self.is_compatible = True
        except ImportError:
            logger.warning(
                "NeMo Guardrails package not found. NeMoOutputGuard operates in deferred fallback mode."
            )

    def evaluate(self, content: str, request: ModelRequest) -> None:
        if not self.is_compatible:
            logger.info("NeMoOutputGuard: Skipped (deferred mode). Fallback to DeterministicOutputGuard active.")
            return
        # Live NeMo Guardrails evaluation would happen here.
        pass
