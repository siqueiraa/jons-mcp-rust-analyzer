# Jons MCP rust-analyzer

A FastMCP server that exposes rust-analyzer LSP features through the Model Context Protocol (MCP). This allows AI assistants like Claude to interact with Rust code using rust-analyzer's powerful language intelligence.

## Features

Exposes rust-analyzer capabilities as MCP tools:

### Core Language Features
- **symbol_info** - Get type signature and documentation for any symbol at a position
- **definition** - Jump to definition of symbols
- **implementation** - Find trait implementations
- **references** - Find all usages of a symbol (paginated)
- **document_symbols** - List all symbols in a file (paginated)
- **workspace_symbols** - Search symbols across the workspace (paginated)
- **type_info** - Get complete type information including fields and methods for a type

### Code Intelligence
- **diagnostics** - Get compiler errors and warnings (paginated)
- **rename** - Rename symbols across the project

### Formatting
- **format_document** - Format entire files
- **format_range** - Format specific ranges

### rust-analyzer Extensions
- **expand_macro** - Expand Rust macros

## Requirements

- Python 3.10+
- rust-analyzer (installed via rustup or available in PATH)
- A Rust project (the server should be started from the project root)

## Local Installation

```bash
# Clone the repository
git clone https://github.com/jonmmease/jons-mcp-rust-analyzer
cd jons-mcp-rust-analyzer

# Install with uv
uv pip install -e .

# Run the server (from a Rust project directory)
cd /path/to/your/rust/project
uv run --directory /path/to/jons-mcp-rust-analyzer jons-mcp-rust-analyzer
```

## Adding to Claude Code

### Local Installation (recommended for development)

```bash
# Navigate to your Rust project first
cd /path/to/your/rust/project

# Register the MCP server with Claude Code, passing the current directory as the project path
claude mcp add jons-mcp-rust-analyzer -- uv run --directory /path/to/jons-mcp-rust-analyzer jons-mcp-rust-analyzer "$(pwd)"
```

### Using uvx (direct from GitHub)

```bash
# Navigate to your Rust project first
cd /path/to/your/rust/project

# Run directly from GitHub with project path
claude mcp add jons-mcp-rust-analyzer -- uvx --from git+https://github.com/jonmmease/jons-mcp-rust-analyzer jons-mcp-rust-analyzer "$(pwd)"
```

### With environment variables

```bash
# Navigate to your Rust project first
cd /path/to/your/rust/project

# Add with custom rust-analyzer path
claude mcp add jons-mcp-rust-analyzer \
  -e RUST_ANALYZER_PATH=/custom/path/to/rust-analyzer \
  -e LOG_LEVEL=DEBUG \
  -- uv run --directory /path/to/jons-mcp-rust-analyzer jons-mcp-rust-analyzer "$(pwd)"
```

### Managing MCP servers

```bash
# List configured MCP servers
claude mcp list

# Remove an MCP server
claude mcp remove jons-mcp-rust-analyzer

# Check MCP server status while in Claude Code
# Type: /mcp
```

## Configuration

- **Project Path**: Pass as CLI argument (e.g., `jons-mcp-rust-analyzer /path/to/rust/project`) or set via `RUST_PROJECT_PATH` environment variable. Defaults to current working directory.
- **rust-analyzer Path**: Can be configured via `RUST_ANALYZER_PATH` environment variable
- **Logging**: Set `LOG_LEVEL` environment variable (default: INFO)

## Development

### Running Tests

```bash
# Install dev dependencies
uv pip install -e ".[dev]"

# Run all tests
uv run pytest

# Run only unit tests
uv run pytest tests/test_lsp_client.py tests/test_mcp_tools.py

# Run integration tests (requires rust-analyzer)
uv run pytest tests/test_integration.py -m integration

# Type check
uv run mypy src/jons_mcp_rust_analyzer

# Run with coverage
uv run pytest --cov=src
```

### Project Structure

```
jons-mcp-rust-analyzer/
├── src/
│   ├── __init__.py
│   └── jons_mcp_rust_analyzer/
│       ├── __init__.py          # Package exports
│       ├── constants.py         # Timeouts, LSP method constants
│       ├── exceptions.py        # Custom exception classes
│       ├── utils.py             # Pagination, file URI helpers
│       ├── lsp_client.py        # RustAnalyzerClient
│       ├── server.py            # FastMCP server setup
│       └── tools/
│           ├── __init__.py      # Re-exports all tools
│           ├── language.py      # hover, completion, definition, etc.
│           ├── intelligence.py  # diagnostics, code_actions, rename
│           ├── formatting.py    # format_document, format_range
│           └── extensions.py    # expand_macro, analyzer_status, etc.
├── tests/
│   ├── conftest.py              # Pytest fixtures
│   ├── test_lsp_client.py       # Unit tests for LSP client
│   ├── test_mcp_tools.py        # Unit tests for MCP tools
│   └── test_integration.py      # Integration tests
├── pyproject.toml               # Python project configuration
└── README.md                    # This file
```

## Example Usage in Claude Code

Once configured, you can use natural language to interact with your Rust code. Claude Code will automatically use the appropriate rust-analyzer tools:

```bash
# Navigate to your Rust project
cd /path/to/your/rust/project

# Basic usage examples
claude "what does the function at line 42 in src/main.rs do?"
claude "find all implementations of the Display trait in this project"
claude "show me all usages of the process_data function"
claude "what errors are in my project?"
claude "rename the Config struct to Configuration throughout the codebase"
claude "format all files in the src directory"
claude "expand the vec! macro at line 15 in main.rs"
claude "find all tests related to the Parser struct"
```

## How It Works

1. **Server Initialization**: When the MCP server starts, it launches rust-analyzer as a subprocess
2. **LSP Communication**: Uses a custom asyncio-based LSP client to communicate with rust-analyzer via stdio
3. **Tool Mapping**: Each LSP capability is exposed as an MCP tool that Claude can call
4. **Project Scope**: rust-analyzer analyzes the Rust project in the current working directory

## Limitations

- Each instance is tied to a single Rust project (the working directory)
- Requires rust-analyzer to be installed separately
- File paths in tool calls can be absolute or relative to the project root

## Troubleshooting

### rust-analyzer not found

Install rust-analyzer:
```bash
rustup component add rust-analyzer
```

Or set the path explicitly:
```bash
export RUST_ANALYZER_PATH=/path/to/rust-analyzer
```

### No Cargo.toml found

The server must be started from a Rust project root containing `Cargo.toml`. Ensure the working directory is your Rust project.

### Debugging

Enable debug logging:
```bash
LOG_LEVEL=DEBUG uv run --directory /path/to/jons-mcp-rust-analyzer jons-mcp-rust-analyzer
```

### Pagination

List-returning tools support `limit` and `offset` parameters for pagination. The response includes:
- Each item has an `offset` field for direct retrieval
- `totalItems`: Total number of available items
- `hasMore`: Whether more items are available
- `nextOffset`: Offset to use for the next page

## License

MIT License - see LICENSE file for details

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
