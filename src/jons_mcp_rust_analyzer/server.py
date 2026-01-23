"""FastMCP server for rust-analyzer.

This module provides the main server setup, lifespan management,
and tool registration for the MCP rust-analyzer server.
"""

import argparse
import logging
import os
import signal
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from fastmcp import FastMCP

from .constants import LSPMethods
from .exceptions import RustAnalyzerNotInitializedError
from .lsp_client import RustAnalyzerClient

# Global project root (can be set via CLI argument or environment variable)
_project_root: Path | None = None

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

# Configure logging
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Global rust-analyzer client instance
rust_analyzer: RustAnalyzerClient | None = None

# Store diagnostics from rust-analyzer
current_diagnostics: dict[str, list[dict[str, Any]]] = {}


async def handle_diagnostics(params: dict[str, Any]) -> None:
    """Handle diagnostics notification from rust-analyzer.

    Args:
        params: The publishDiagnostics notification parameters
    """
    uri = params.get("uri", "")
    diagnostics_list = params.get("diagnostics", [])
    current_diagnostics[uri] = diagnostics_list
    logger.debug(f"Received {len(diagnostics_list)} diagnostics for {uri}")


@asynccontextmanager
async def lifespan(mcp: FastMCP) -> AsyncIterator[None]:
    """Manage the lifecycle of the rust-analyzer client."""
    global rust_analyzer

    # Determine project root: CLI arg > env var > cwd
    if _project_root is not None:
        project_root = _project_root
    elif "RUST_PROJECT_PATH" in os.environ:
        project_root = Path(os.environ["RUST_PROJECT_PATH"]).resolve()
    else:
        project_root = Path.cwd()

    logger.info(f"Starting MCP server in project: {project_root}")

    # Check if this is a Rust project
    if not (project_root / "Cargo.toml").exists():
        logger.warning(
            "No Cargo.toml found in current directory. "
            "rust-analyzer may not work correctly."
        )

    rust_analyzer = RustAnalyzerClient(project_root)
    rust_analyzer.on_notification(LSPMethods.PUBLISH_DIAGNOSTICS, handle_diagnostics)

    try:
        await rust_analyzer.start()
    except Exception as e:
        logger.error(f"Failed to start rust-analyzer: {e}", exc_info=True)
        raise

    yield

    # Shutdown
    if rust_analyzer:
        await rust_analyzer.shutdown()
        rust_analyzer = None


def ensure_rust_analyzer() -> RustAnalyzerClient:
    """Ensure rust-analyzer is initialized.

    Returns:
        The initialized rust-analyzer client

    Raises:
        RustAnalyzerNotInitializedError: If client is not initialized
    """
    if rust_analyzer is None:
        raise RustAnalyzerNotInitializedError("rust-analyzer client not initialized")
    if not rust_analyzer.is_initialized():
        raise RustAnalyzerNotInitializedError("rust-analyzer is not ready")
    return rust_analyzer


async def ensure_rust_analyzer_indexed() -> RustAnalyzerClient:
    """Ensure rust-analyzer is initialized and ready (progress complete).

    Returns:
        The initialized rust-analyzer client

    Raises:
        RustAnalyzerNotInitializedError: If client is not initialized or wait times out
    """
    client = ensure_rust_analyzer()

    if not client.is_ready():
        logger.info("Waiting for rust-analyzer to be ready...")
        if not await client.wait_until_ready():
            raise RustAnalyzerNotInitializedError(
                "rust-analyzer not ready (timed out). Try again later."
            )

    return client


# Create FastMCP server instance with lifespan
mcp = FastMCP(
    name="rust-analyzer-mcp",
    lifespan=lifespan,
    instructions="""
MCP server providing rust-analyzer LSP features for Rust code intelligence.

## Navigation & Discovery
| Tool | Purpose |
|------|---------|
| workspace_symbols | Search for types/functions across the project by name |
| document_symbols | List all symbols defined in a file |
| definition | Jump to where a symbol is defined |
| implementation | Find trait implementations or impl blocks |
| references | Find all usages of a symbol |

## Understanding Code
| Tool | Purpose |
|------|---------|
| type_info | Get type name, fields, and methods for a value (primary tool) |
| symbol_info | Get type signature and docs for any symbol (via hover) |

## Code Intelligence
| Tool | Purpose |
|------|---------|
| diagnostics | Get compiler errors and warnings |

## Refactoring
| Tool | Purpose |
|------|---------|
| rename | Safely rename a symbol across the project |

## Formatting
| Tool | Purpose |
|------|---------|
| format_document | Format an entire file |
| format_range | Format a specific range |

## Macros
| Tool | Purpose |
|------|---------|
| expand_macro | Show macro expansion at a position |

## Typical Workflow
1. Use workspace_symbols or document_symbols to find code
2. Call type_info on a variable to discover its type, fields, and methods
3. Use definition to navigate to source, references to find usages
4. Check diagnostics after making changes
5. Use format_range to format lines around your changes

## Pagination
Tools returning lists (references, document_symbols, workspace_symbols, diagnostics,
type_info methods) return max 20 items. Use limit/offset parameters and check
hasMore for additional results.
""",
)


# Register all tools with the MCP server
mcp.tool(symbol_info)
mcp.tool(type_info)
mcp.tool(definition)
mcp.tool(implementation)
mcp.tool(references)
mcp.tool(document_symbols)
mcp.tool(workspace_symbols)
mcp.tool(diagnostics)
mcp.tool(rename)
mcp.tool(format_document)
mcp.tool(format_range)
mcp.tool(expand_macro)


# Signal handling for graceful shutdown
def signal_handler(signum: int, frame: Any) -> None:
    """Handle shutdown signals.

    Args:
        signum: Signal number
        frame: Current stack frame
    """
    # Don't log in signal handlers to avoid reentrant logging issues
    sys.exit(0)


def main() -> None:
    """Main entry point for the MCP server."""
    global _project_root

    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="MCP server for rust-analyzer LSP features"
    )
    parser.add_argument(
        "project_path",
        nargs="?",
        help="Path to the Rust project (defaults to current directory)",
    )
    parser.add_argument(
        "--http",
        action="store_true",
        help="Run as persistent HTTP server instead of stdio",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=9000,
        help="HTTP port (default: 9000)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="HTTP host (default: 127.0.0.1)",
    )
    args = parser.parse_args()

    # Set project root from CLI argument
    if args.project_path:
        _project_root = Path(args.project_path).resolve()
        if not _project_root.exists():
            print(f"Error: Project path does not exist: {_project_root}", file=sys.stderr)
            sys.exit(1)

    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Run the MCP server
    if args.http:
        logger.info(f"Starting HTTP server on {args.host}:{args.port}")
        mcp.run(transport="http", host=args.host, port=args.port)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
