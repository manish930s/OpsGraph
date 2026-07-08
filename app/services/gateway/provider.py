from abc import ABC, abstractmethod
from app.schemas.prompting import ModelRequest

class LLMProvider(ABC):
    """
    Abstract contract that all model provider adapters (Groq, Gemini, etc.) must satisfy.
    """
    @abstractmethod
    def generate(self, request: ModelRequest) -> str:
        """
        Submits the prompt messages to the provider model.
        Returns the raw string output or raises independent domain exceptions.
        """
        pass

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Returns the identifier name of the provider."""
        pass

    @property
    @abstractmethod
    def model_id(self) -> str:
        """Returns the active model identifier."""
        pass
