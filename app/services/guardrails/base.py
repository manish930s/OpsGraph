from abc import ABC, abstractmethod
from app.schemas.prompting import ModelRequest

class InputGuard(ABC):
    """
    Abstract interface for evaluating safety on incoming prompt requests before dispatch.
    """
    @abstractmethod
    def evaluate(self, request: ModelRequest) -> None:
        """
        Evaluates the request. Raises GuardrailRejectedError if safety policy is breached.
        """
        pass

class OutputGuard(ABC):
    """
    Abstract interface for evaluating safety and structure on raw LLM responses before delivery.
    """
    @abstractmethod
    def evaluate(self, content: str, request: ModelRequest) -> None:
        """
        Evaluates raw response content. Raises GuardrailRejectedError if safety policy is breached.
        """
        pass
