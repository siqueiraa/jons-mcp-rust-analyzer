"""Custom exceptions for the MCP rust-analyzer server."""


class LSPRequestError(Exception):
    """Raised when an LSP request fails.

    Attributes:
        message: Human-readable error description
        code: LSP error code (if available)
        is_retryable: Whether the error might succeed on retry
    """

    def __init__(
        self,
        message: str,
        code: int | None = None,
        is_retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.is_retryable = is_retryable

    def __str__(self) -> str:
        if self.code is not None:
            return f"{self.message} (code: {self.code})"
        return self.message


class RustAnalyzerNotInitializedError(Exception):
    """Raised when rust-analyzer is not initialized."""

    def __init__(self, message: str = "rust-analyzer is not initialized") -> None:
        super().__init__(message)


class RustAnalyzerNotFoundError(Exception):
    """Raised when rust-analyzer executable cannot be found."""

    def __init__(self, message: str = "rust-analyzer not found") -> None:
        super().__init__(message)
