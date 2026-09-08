class Text2SQLError(Exception):
    """Base error for recoverable application failures."""


class ProviderError(Text2SQLError):
    pass


class SafetyError(Text2SQLError):
    pass


class ExecutionError(Text2SQLError):
    pass


class DatabaseValidationError(Text2SQLError):
    """Adapter-independent database compilation/authorization failure."""
