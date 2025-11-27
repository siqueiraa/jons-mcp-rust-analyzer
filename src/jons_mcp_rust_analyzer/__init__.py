"""MCP server for rust-analyzer LSP features."""

from .constants import (
    DEFAULT_PAGINATION_LIMIT,
    DEFAULT_PAGINATION_OFFSET,
    INDEXING_TIMEOUT,
    PROGRESS_TOKENS,
    LSPMethods,
    READ_BUFFER_SIZE,
    REQUEST_TIMEOUT,
    SHUTDOWN_TIMEOUT,
)
from .exceptions import (
    LSPRequestError,
    RustAnalyzerNotFoundError,
    RustAnalyzerNotInitializedError,
)
from .lsp_client import RustAnalyzerClient
from .server import (
    current_diagnostics,
    ensure_rust_analyzer,
    main,
    mcp,
    rust_analyzer,
)
from .tools import (
    definition,
    diagnostics,
    document_symbols,
    expand_macro,
    format_document,
    format_range,
    implementation,
    references,
    rename,
    symbol_info,
    type_info,
    workspace_symbols,
)
from .utils import apply_pagination, ensure_file_uri

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "DEFAULT_PAGINATION_LIMIT",
    "DEFAULT_PAGINATION_OFFSET",
    "INDEXING_TIMEOUT",
    "PROGRESS_TOKENS",
    "LSPMethods",
    "READ_BUFFER_SIZE",
    "REQUEST_TIMEOUT",
    "SHUTDOWN_TIMEOUT",
    "LSPRequestError",
    "RustAnalyzerNotFoundError",
    "RustAnalyzerNotInitializedError",
    "RustAnalyzerClient",
    "current_diagnostics",
    "ensure_rust_analyzer",
    "main",
    "mcp",
    "rust_analyzer",
    "apply_pagination",
    "ensure_file_uri",
    "symbol_info",
    "type_info",
    "definition",
    "implementation",
    "references",
    "document_symbols",
    "workspace_symbols",
    "diagnostics",
    "rename",
    "format_document",
    "format_range",
    "expand_macro",
]
