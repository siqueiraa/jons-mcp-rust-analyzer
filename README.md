# rust-analyzer MCP Server

A FastMCP server that exposes all rust-analyzer LSP features through the Model Context Protocol (MCP). This allows AI assistants like Claude to interact with Rust code using rust-analyzer's powerful language intelligence.

## Features

Exposes all rust-analyzer capabilities as MCP tools:

### Core Language Features
- **hover** - Get type information and documentation at any position
- **completion** - Get code completions with auto-import support
- **definition** - Jump to definition of symbols
- **type_definition** - Jump to type definitions
- **implementation** - Find trait implementations
- **references** - Find all usages of a symbol
- **document_symbols** - List all symbols in a file
- **workspace_symbols** - Search symbols across the workspace

### Code Intelligence
- **diagnostics** - Get compiler errors and warnings
- **code_actions** - Get available fixes and refactorings
- **rename** - Rename symbols across the project
- **semantic_tokens** - Get semantic syntax highlighting

### Formatting
- **format_document** - Format entire files
- **format_range** - Format specific ranges

### rust-analyzer Extensions
- **expand_macro** - Expand Rust macros
- **syntax_tree** - View the syntax tree
- **analyzer_status** - Check analyzer status
- **view_crate_graph** - Visualize crate dependencies
- **related_tests** - Find related tests
- **runnables** - Find runnable targets (tests, binaries)
- **ssr** - Structural search and replace

## Requirements

- Python 3.10+
- rust-analyzer (installed via rustup or available in PATH)
- A Rust project (the server should be started from the project root)

## Installation

The server is designed to be run as a standalone script using `uv`:

```bash
# Clone the repository
git clone https://github.com/yourusername/rust-analyzer-mcp
cd rust-analyzer-mcp

# Make the script executable
chmod +x rust_analyzer_mcp.py

# Run with uv (installs dependencies automatically)
uv run rust_analyzer_mcp.py
```

Or install dependencies manually:

```bash
pip install fastmcp
```

## Usage

### With Claude Desktop

Add to your Claude Desktop configuration (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "rust-analyzer": {
      "command": "uv",
      "args": ["run", "/path/to/rust_analyzer_mcp.py"],
      "cwd": "/path/to/your/rust/project"
    }
  }
}
```

Or if you prefer to use the script directly:

```json
{
  "mcpServers": {
    "rust-analyzer": {
      "command": "/path/to/rust_analyzer_mcp.py",
      "cwd": "/path/to/your/rust/project"
    }
  }
}
```

### Configuration

The server uses the following configuration options:

- **Working Directory**: Must be launched from a Rust project root (containing `Cargo.toml`)
- **rust-analyzer Path**: Can be configured via `RUST_ANALYZER_PATH` environment variable
- **Logging**: Set `LOG_LEVEL` environment variable (default: INFO)

Example with environment variables:

```json
{
  "mcpServers": {
    "rust-analyzer": {
      "command": "uv",
      "args": ["run", "/path/to/rust_analyzer_mcp.py"],
      "cwd": "/path/to/your/rust/project",
      "env": {
        "RUST_ANALYZER_PATH": "/custom/path/to/rust-analyzer",
        "LOG_LEVEL": "DEBUG"
      }
    }
  }
}
```

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

# Run with coverage
uv run pytest --cov=rust_analyzer_mcp
```

### Project Structure

```
rust-analyzer-mcp/
├── rust_analyzer_mcp.py      # Main MCP server implementation
├── requirements.md           # Detailed requirements document
├── pyproject.toml           # Python project configuration
├── tests/
│   ├── conftest.py          # Pytest fixtures
│   ├── test_lsp_client.py   # Unit tests for LSP client
│   ├── test_mcp_tools.py    # Unit tests for MCP tools
│   └── test_integration.py  # Integration tests
└── README.md                # This file
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

The server must be started from a Rust project root containing `Cargo.toml`. Ensure the `cwd` in your MCP configuration points to your Rust project.

### Debugging

Enable debug logging:
```bash
export LOG_LEVEL=DEBUG
uv run rust_analyzer_mcp.py
```

## License

MIT License - see LICENSE file for details

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.