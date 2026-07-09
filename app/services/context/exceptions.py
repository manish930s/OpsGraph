class ContextBuilderError(Exception):
    """Base exception for all Context Builder errors."""
    pass

class ContextValidationError(ContextBuilderError):
    """Raised when context bundles fail structure or reference validation."""
    pass

class ContextScopeMismatchError(ContextBuilderError):
    """Raised when evidence or knowledge bundles belong to mismatched scenarios or incidents."""
    pass

class ContextBudgetError(ContextBuilderError):
    """Raised when critical context exceeds physical budgets or allocation strategies fail."""
    pass

class ContextProvenanceError(ContextBuilderError):
    """Raised when lineage tracking or citation maps are missing or broken."""
    pass

class ContextBuildError(ContextBuilderError):
    """General error representing a failure during the context assembly phase."""
    pass
