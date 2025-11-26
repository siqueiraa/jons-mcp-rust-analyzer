"""FastMCP server exposing rust-analyzer LSP features.

This module provides backward compatibility by re-exporting
from the new package structure.
"""

from .jons_mcp_rust_analyzer import main

__all__ = ["main"]
