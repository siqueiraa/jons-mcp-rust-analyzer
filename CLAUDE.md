# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A FastMCP server that exposes rust-analyzer LSP features through the Model Context Protocol (MCP). It manages rust-analyzer as a subprocess and translates between MCP and LSP protocols, enabling AI assistants to interact with Rust code using rust-analyzer's language intelligence.

## Build and Development Commands

```bash
# Install dependencies
uv pip install -e .

# Install with dev dependencies
uv pip install -e ".[dev]"

# Run the server
uv run jons-mcp-rust-analyzer

# Run all tests
uv run pytest

# Run a single test file
uv run pytest tests/test_lsp_client.py

# Run a single test
uv run pytest tests/test_lsp_client.py::test_name

# Run integration tests (requires rust-analyzer installed)
uv run pytest tests/test_integration.py -m integration

# Type check
uv run mypy src/jons_mcp_rust_analyzer

# Format code
uv run black src tests

# Lint code
uv run ruff check src tests
```

## Architecture

### Package Structure

```
src/jons_mcp_rust_analyzer/
├── __init__.py          # Package exports
├── constants.py         # Magic numbers, timeouts, LSP method constants
├── exceptions.py        # Custom exception classes
├── utils.py             # Pagination, file URI helpers, sort keys
├── lsp_client.py        # RustAnalyzerClient - LSP subprocess management
├── server.py            # FastMCP server setup, lifespan, main()
└── tools/
    ├── __init__.py      # Re-exports all tools
    ├── language.py      # hover, completion, definition, references, etc.
    ├── intelligence.py  # diagnostics, code_actions, rename, semantic_tokens
    ├── formatting.py    # format_document, format_range
    └── extensions.py    # expand_macro, syntax_tree, analyzer_status, etc.
```

### Core Components

- **`lsp_client.py`**: `RustAnalyzerClient` - AsyncIO-based LSP client that manages rust-analyzer subprocess, handles LSP message framing (Content-Length headers), and maintains pending request futures

- **`server.py`**: FastMCP server with lifespan context manager for rust-analyzer lifecycle. Contains global `rust_analyzer` client and `current_diagnostics` dict storing published diagnostics per file URI

- **`tools/`**: MCP tool functions organized by domain. Each tool validates context, translates MCP requests to LSP, and formats responses

### Key Patterns

- **File URI handling**: `ensure_file_uri()` in `utils.py` converts paths to `file://` URIs, supporting both absolute and relative paths (relative to cwd)

- **Pagination**: `apply_pagination()` provides consistent limit/offset handling across list-returning tools (`completion`, `references`, `document_symbols`, `workspace_symbols`, `diagnostics`) with stable sorting

- **LSP message protocol**: Messages use JSON-RPC 2.0 with `Content-Length` headers over stdio

- **Context validation**: All tools accept `ctx: Context | None = None` and validate the rust-analyzer is initialized before proceeding

- **Custom exceptions**: `LSPRequestError`, `RustAnalyzerNotInitializedError`, `RustAnalyzerNotFoundError` provide specific error handling

### Test Structure

- `tests/test_lsp_client.py`: Unit tests for the LSP client message parsing/sending
- `tests/test_mcp_tools.py`: Unit tests for MCP tool wrappers with mocked rust-analyzer
- `tests/test_integration.py`: Integration tests requiring real rust-analyzer process (marked with `@pytest.mark.integration`)

## Configuration

- `RUST_ANALYZER_PATH`: Override rust-analyzer executable path
- `LOG_LEVEL`: Set logging level (default: INFO)
- Server must be launched from a Rust project root containing `Cargo.toml`
