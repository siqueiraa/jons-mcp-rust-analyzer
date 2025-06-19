# Requirements Document: FastMCP rust-analyzer Server

## Project Overview
Build a standalone Python script that creates a FastMCP server exposing all rust-analyzer LSP features through MCP tools. The server will manage rust-analyzer as a subprocess and translate between the MCP and LSP protocols.

## Technical Requirements

### 1. Standalone Script Architecture
- Single Python file with inline dependencies (using uv comment syntax)
- Dependencies specified as: `# /// script` block for uv
- Python version requirement: `>= 3.10` (required by FastMCP)
- Main dependencies: `fastmcp>=0.3.0`, `asyncio` (built-in)
- No external LSP client libraries required (custom implementation)

### 2. rust-analyzer Discovery
- Primary: Check if `rust-analyzer` is on PATH
- Fallback: Look in `~/.cargo/bin/rust-analyzer`
- Configurable path through environment variable: `RUST_ANALYZER_PATH`

### 3. Server Initialization
- Start rust-analyzer subprocess on MCP server startup
- Initialize LSP connection with proper capabilities
- Use current working directory as the Rust project root
- rust-analyzer will be tied to this single project/workspace
- Assumes MCP server is launched from the Rust project directory (Claude Code use case)

### 4. LSP Communication Layer
- Custom asyncio-based implementation (~300 lines total)
- Handle stdio communication with proper LSP headers
- Message parsing with Content-Length header processing
- JSON-RPC 2.0 message format with proper typing
- Request/response correlation with monotonic ID counter
- Notification handling for server-initiated messages (diagnostics)
- 30-second timeout for requests with proper cleanup
- Concurrent request support via asyncio.Future tracking

#### Why Custom Implementation Over Off-the-Shelf Libraries
After evaluating options like pygls, pylspclient, and python-lsp-jsonrpc, a custom implementation is recommended because:
- **Simplicity**: LSP client needs are straightforward (~200 lines) vs heavy dependencies
- **FastMCP Integration**: Native asyncio integration with FastMCP's event loop
- **Minimal Dependencies**: Only requires `fastmcp` for a faster, cleaner standalone script
- **Full Control**: Easy debugging, custom logging, and rust-analyzer specific optimizations
- **Maintenance**: LSP protocol is stable; no risk of upstream breaking changes

The implementation is essentially JSON-RPC over stdio with header parsing - straightforward for our focused use case.

### 5. MCP Tool Mapping

#### Core Language Features
- `hover` - Get hover information at position
- `completion` - Get code completions
- `definition` - Go to definition
- `type_definition` - Go to type definition
- `implementation` - Find implementations
- `references` - Find all references
- `document_symbols` - List symbols in document
- `workspace_symbols` - Search symbols in workspace

#### Code Intelligence
- `diagnostics` - Get current diagnostics
- `code_actions` - Get available code actions
- `rename` - Rename symbol
- `semantic_tokens` - Get semantic highlighting

#### Formatting
- `format_document` - Format entire document
- `format_range` - Format selected range

#### rust-analyzer Extensions
- `expand_macro` - Expand macro at position
- `syntax_tree` - View syntax tree
- `analyzer_status` - Get analyzer status
- `view_crate_graph` - Visualize crate dependencies
- `related_tests` - Find related tests
- `runnables` - Get runnable items (tests, binaries)
- `ssr` - Structural search and replace

### 6. File Management
- Tools must handle file URIs correctly (`file://` protocol)
- Support both absolute and relative paths
- Automatic text document synchronization

### 7. Error Handling
- Graceful handling of rust-analyzer crashes
- Automatic restart capability
- Clear error messages for MCP clients
- Timeout handling for LSP requests

### 8. Lifecycle Management
- Proper shutdown sequence (LSP shutdown → exit)
- Resource cleanup on MCP server termination
- Handle signal interrupts gracefully

## Implementation Structure

```python
#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "fastmcp>=0.3.0",
# ]
# ///

import asyncio
import json
import os
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional
from contextlib import asynccontextmanager
from fastmcp import FastMCP, Context

# Global client instance
rust_analyzer: Optional[RustAnalyzerClient] = None

# Lifecycle management using lifespan context manager
@asynccontextmanager
async def lifespan(mcp: FastMCP):
    """Manage rust-analyzer lifecycle"""
    global rust_analyzer
    # Startup: Initialize rust-analyzer
    rust_analyzer = RustAnalyzerClient(Path.cwd())
    await rust_analyzer.start()
    yield
    # Shutdown: Clean up rust-analyzer
    await rust_analyzer.shutdown()

# FastMCP server instance with lifespan
mcp = FastMCP(
    name="rust-analyzer-mcp",
    lifespan=lifespan
)

# RustAnalyzerClient class implementation
class RustAnalyzerClient:
    # ... full asyncio-based implementation ...

# MCP Tools
@mcp.tool
async def hover(file_path: str, line: int, character: int, ctx: Context) -> Dict[str, Any]:
    """Get hover information at specified position"""
    # Implementation using rust_analyzer client
    pass

# ... additional tools ...

if __name__ == "__main__":
    mcp.run()
```

## Usage Example

```bash
# Install and run with uv
uv run rust-analyzer-mcp.py

# Or make executable and run directly
chmod +x rust-analyzer-mcp.py
./rust-analyzer-mcp.py
```

## MCP Client Configuration

### Claude Code (CLI)
```bash
# Add as project-scoped MCP server
claude mcp add --scope project rust-analyzer uv run /path/to/rust_analyzer_mcp.py

# Or with wrapper script if ENOENT errors occur
claude mcp add --scope project rust-analyzer /path/to/run_rust_analyzer_mcp.sh
```

### Claude Desktop
```json
{
  "mcpServers": {
    "rust-analyzer": {
      "command": "uv",
      "args": ["run", "/path/to/rust-analyzer-mcp.py"],
      "env": {
        "RUST_ANALYZER_PATH": "/custom/path/to/rust-analyzer"
      }
    }
  }
}
```

## Deliverables
1. Single Python script file with all functionality
2. Comprehensive error handling and logging
3. Support for all rust-analyzer LSP features
4. Documentation in script comments
5. Example usage patterns
6. Complete test suite with pytest
   - Unit tests for LSP client components
   - Integration tests with real rust-analyzer
   - Mock-based tests for MCP tool functions
   - 59 total tests with 100% pass rate

## Research Summary

### FastMCP Framework
- Standard Python framework for MCP servers
- Built-in support for stdio transport (ideal for LSP integration)
- Decorator-based tool definition
- Native asyncio support for concurrent operations
- Automatic schema generation from type hints

### rust-analyzer LSP Features
- Supports all standard LSP features
- Extensive custom extensions for Rust-specific functionality
- Communicates via stdio with JSON-RPC 2.0 protocol
- Requires proper initialization sequence
- Supports workspace and single-file modes

### Python LSP Client Implementation
- Custom asyncio implementation recommended for full control
- Must handle LSP message framing (Content-Length headers)
- Asynchronous request/response correlation required
- Notification handling for diagnostics and other server-initiated messages
- Proper subprocess lifecycle management critical

## Implementation Lessons Learned

### Version Requirements
- **Python >= 3.10**: Required by FastMCP dependency chain
- **FastMCP >= 0.3.0**: Minimum version for stable API
- **rust-analyzer**: Any recent version (protocol is stable)
- **uv script metadata**: Must include `requires-python = ">=3.10"`

### API Compatibility Issues Resolved
1. **FastMCP Initialization**: 
   - ❌ `FastMCP(version="0.1.0")` - version parameter not supported
   - ✅ `FastMCP(name="rust-analyzer-mcp")` - correct initialization
   
2. **Lifecycle Management**:
   - ❌ `@mcp.server.on_initialize` - deprecated pattern
   - ✅ `lifespan` parameter with asynccontextmanager - proper pattern

3. **Tool Function Access**:
   - ❌ Direct function calls in tests fail
   - ✅ Access via `.fn` attribute on decorated functions

4. **Semantic Tokens Capability**:
   - ❌ Missing `formats` field causes rust-analyzer errors
   - ✅ Must include `"formats": ["relative"]` in capability

### rust-analyzer Integration Insights
1. **Asynchronous Indexing**: rust-analyzer may return `None` while indexing
2. **File Synchronization**: Not required for read-only operations
3. **Diagnostics**: Published via notifications, not request/response
4. **Error Handling**: "content modified" errors are normal during rapid operations
5. **Subprocess Management**: Clean shutdown prevents zombie processes

### Claude Code Integration
1. **Command Parsing**: Claude Code may treat full command strings as single executables
2. **Wrapper Scripts**: Shell scripts can work around command parsing issues
3. **MCP Tool Naming**: Tools are prefixed as `mcp__<serverName>__<toolName>`
4. **Security**: Use `--allowedTools` flag to explicitly permit MCP tools

This requirements document outlines a comprehensive MCP server that will make rust-analyzer's full feature set available through the Model Context Protocol. The implementation will prioritize reliability, completeness, and ease of use.