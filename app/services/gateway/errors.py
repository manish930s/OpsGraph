class GatewayError(Exception):
    """Base exception for all Gateway operations."""
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

class ProviderConfigurationError(GatewayError):
    """Raised when provider configuration is invalid or missing."""
    pass

class ProviderAuthenticationError(GatewayError):
    """Raised on authentication failures (e.g. invalid API key)."""
    pass

class ProviderRateLimitError(GatewayError):
    """Raised when rate limits or quotas are exhausted."""
    pass

class ProviderTimeoutError(GatewayError):
    """Raised when a request exceeds its allotted duration."""
    pass

class ProviderUnavailableError(GatewayError):
    """Raised when a provider is temporarily down or offline."""
    pass

class ProviderResponseError(GatewayError):
    """Raised when a provider returns an empty or invalid response payload."""
    pass

class StructuredOutputError(GatewayError):
    """Raised when structured response parsing or schema validation fails."""
    pass

class GuardrailRejectedError(GatewayError):
    """Raised when an input or output safety policy is violated."""
    pass

class CitationValidationError(GatewayError):
    """Raised when the model references invalid or hallucinated citations."""
    pass
