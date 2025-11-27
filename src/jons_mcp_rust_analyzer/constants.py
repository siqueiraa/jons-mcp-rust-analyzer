"""Constants used throughout the MCP rust-analyzer server."""

# Timeouts (in seconds)
REQUEST_TIMEOUT: float = 30.0
SHUTDOWN_TIMEOUT: float = 5.0
INDEXING_TIMEOUT: float = 300.0  # 5 minutes max wait for indexing

# Buffer sizes
READ_BUFFER_SIZE: int = 4096

# LSP Protocol
CONTENT_LENGTH_HEADER: str = "Content-Length: "
HEADER_SEPARATOR: bytes = b"\r\n\r\n"

# Pagination defaults
DEFAULT_PAGINATION_LIMIT: int = 20
DEFAULT_PAGINATION_OFFSET: int = 0


# LSP Method names
class LSPMethods:
    """LSP method name constants."""

    # Lifecycle
    INITIALIZE = "initialize"
    INITIALIZED = "initialized"
    SHUTDOWN = "shutdown"
    EXIT = "exit"

    # Text Document Sync
    DID_OPEN = "textDocument/didOpen"
    DID_CHANGE = "textDocument/didChange"
    DID_CLOSE = "textDocument/didClose"

    # Text Document
    HOVER = "textDocument/hover"
    COMPLETION = "textDocument/completion"
    DEFINITION = "textDocument/definition"
    TYPE_DEFINITION = "textDocument/typeDefinition"
    IMPLEMENTATION = "textDocument/implementation"
    REFERENCES = "textDocument/references"
    DOCUMENT_SYMBOL = "textDocument/documentSymbol"
    CODE_ACTION = "textDocument/codeAction"
    RENAME = "textDocument/rename"
    PREPARE_RENAME = "textDocument/prepareRename"
    FORMATTING = "textDocument/formatting"
    RANGE_FORMATTING = "textDocument/rangeFormatting"
    SEMANTIC_TOKENS_FULL = "textDocument/semanticTokens/full"
    PUBLISH_DIAGNOSTICS = "textDocument/publishDiagnostics"

    # Workspace
    WORKSPACE_SYMBOL = "workspace/symbol"

    # rust-analyzer extensions
    EXPAND_MACRO = "rust-analyzer/expandMacro"
    ANALYZER_STATUS = "rust-analyzer/analyzerStatus"
    RELATED_TESTS = "rust-analyzer/relatedTests"
    RUNNABLES = "rust-analyzer/runnables"

    # Progress notifications
    PROGRESS = "$/progress"


# rust-analyzer progress tokens (all phases we need to wait for)
PROGRESS_TOKENS = {
    "rustAnalyzer/Fetching",
    "rustAnalyzer/indexing",
    "rustAnalyzer/Building CrateGraph",
    "rustAnalyzer/Roots Scanned",
}
