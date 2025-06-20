# rust-analyzer MCP Server

A FastMCP server that exposes all rust-analyzer LSP features through the Model Context Protocol (MCP). This allows AI assistants like Claude to interact with Rust code using rust-analyzer's powerful language intelligence.

## Features

Exposes all rust-analyzer capabilities as MCP tools:

### Core Language Features
- **hover** - Get type information and documentation at any position
- **completion** - Get code completions with auto-import support
  - `limit`: Maximum completions to return (default: 50)
  - `offset`: Number of items to skip for pagination (default: 0)
  - `include_detail`: Include type signatures and details (default: true)
  - `include_documentation`: Include documentation strings (default: false)
  - Returns: Items with `label`, `kind`, and absolute `offset`
  - Each item includes its offset for direct retrieval with `limit=1`
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

### With Claude Code (CLI)

Claude Code supports MCP servers through the `claude mcp add` command. To use rust-analyzer with Claude Code:

#### Option 1: Add as a project-scoped MCP server

```bash
# Navigate to your Rust project
cd /path/to/your/rust/project

# Add rust-analyzer as an MCP server for this project
claude mcp add --scope project rust-analyzer uv run /path/to/rust_analyzer_mcp.py

# Now use Claude Code normally - it will have access to rust-analyzer tools
claude "what does the function at line 42 in src/main.rs do?"
```

#### Option 2: Add as a user-scoped MCP server (global)

```bash
# Add rust-analyzer globally (you'll need to specify project path when using)
claude mcp add --scope user rust-analyzer uv run /path/to/rust_analyzer_mcp.py

# When using, make sure you're in a Rust project directory
cd /path/to/your/rust/project
claude "find all implementations of the Display trait"
```

#### Option 3: Add with environment variables

```bash
# Add with custom rust-analyzer path
claude mcp add --scope project rust-analyzer \
  -e RUST_ANALYZER_PATH=/custom/path/to/rust-analyzer \
  -e LOG_LEVEL=DEBUG \
  -- uv run /path/to/rust_analyzer_mcp.py
```

#### Option 4: Using with --mcp-config flag

Create an MCP configuration file (`mcp-config.json`):

```json
{
  "rust-analyzer": {
    "command": "uv",
    "args": ["run", "/path/to/rust_analyzer_mcp.py"],
    "env": {
      "LOG_LEVEL": "INFO"
    }
  }
}
```

Then use it:
```bash
cd /path/to/your/rust/project
claude --mcp-config mcp-config.json "analyze my Rust code"
```

#### Managing MCP servers

```bash
# List configured MCP servers
claude mcp list

# Remove an MCP server
claude mcp remove rust-analyzer

# Check MCP server status while in Claude Code
# Type: /mcp
```

**Note**: When using MCP tools, you may need to explicitly allow them with the `--allowedTools` flag for security:

```bash
claude --allowedTools "mcp__rust-analyzer__*" "format all files in src/"
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

# More complex requests
claude "analyze the error handling in the network module and suggest improvements"
claude "explain how the lifetime parameters work in the Cache implementation"
claude "find all TODO comments and create a summary"
```

The MCP server provides Claude Code with deep understanding of your Rust code through rust-analyzer's semantic analysis.

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

### Command execution issues

If you encounter `ENOENT` errors when Claude Code tries to start the MCP server, create a wrapper script:

```bash
#!/bin/bash
# Save as run_rust_analyzer_mcp.sh
exec uv run /path/to/rust_analyzer_mcp.py
```

Make it executable and use it instead:
```bash
chmod +x run_rust_analyzer_mcp.sh
claude mcp add --scope project rust_analyzer /path/to/run_rust_analyzer_mcp.sh
```

### Token limit exceeded errors

If you get "response exceeds maximum allowed tokens" errors with the completion tool:

1. Use the `limit` parameter to reduce completions:
   ```
   "Get completions at line 42 with limit 20"
   ```

2. Disable documentation (already off by default):
   ```
   "Get completions without documentation"
   ```

3. Disable type details if needed:
   ```
   "Get completions without details"
   ```

4. Use pagination to browse through results:
   ```
   "Get next 20 completions starting at offset 20"
   ```

5. Get a specific completion using its offset:
   ```
   "Get the completion at offset 42"
   ```

The response includes:
- Each item has an `offset` field for direct retrieval
- `totalItems`: Total number of available completions
- `hasMore`: Whether more items are available
- `nextOffset`: Offset to use for the next page

## License

MIT License - see LICENSE file for details

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.