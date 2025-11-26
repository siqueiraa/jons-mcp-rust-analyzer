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
mcp = FastMCP(name="rust-analyzer-mcp", lifespan=lifespan)


# Register all tools with the MCP server
mcp.tool(hover)
mcp.tool(completion)
mcp.tool(definition)
mcp.tool(type_definition)
mcp.tool(implementation)
mcp.tool(references)
mcp.tool(document_symbols)
mcp.tool(workspace_symbols)
mcp.tool(diagnostics)
mcp.tool(code_actions)
mcp.tool(rename)
mcp.tool(format_document)
mcp.tool(format_range)
mcp.tool(expand_macro)
mcp.tool(analyzer_status)
mcp.tool(related_tests)
mcp.tool(runnables)


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
    mcp.run()


if __name__ == "__main__":
    main()
