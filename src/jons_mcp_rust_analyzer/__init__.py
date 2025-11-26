"""MCP server for rust-analyzer LSP features."""

from .constants import (
    DEFAULT_PAGINATION_LIMIT,
    DEFAULT_PAGINATION_OFFSET,
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
    analyzer_status,
    code_actions,
    completion,
    definition,
    diagnostics,
    document_symbols,
    expand_macro,
    format_document,
    format_range,
    hover,
    implementation,
    references,
    related_tests,
    rename,
    runnables,
    type_definition,
    workspace_symbols,
)
from .utils import apply_pagination, ensure_file_uri

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "DEFAULT_PAGINATION_LIMIT",
    "DEFAULT_PAGINATION_OFFSET",
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
    "hover",
    "completion",
    "definition",
    "type_definition",
    "implementation",
    "references",
    "document_symbols",
    "workspace_symbols",
    "diagnostics",
    "code_actions",
    "rename",
    "format_document",
    "format_range",
    "expand_macro",
    "analyzer_status",
    "related_tests",
    "runnables",
]
