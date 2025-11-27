"""MCP tools for rust-analyzer functionality."""

from .extensions import expand_macro
from .formatting import format_document, format_range
from .intelligence import diagnostics, rename
from .language import (
    definition,
    document_symbols,
    implementation,
    references,
    symbol_info,
    type_info,
    workspace_symbols,
)

__all__ = [
    # Language features
    "symbol_info",
    "type_info",
    "definition",
    "implementation",
    "references",
    "document_symbols",
    "workspace_symbols",
    # Code intelligence
    "diagnostics",
    "rename",
    # Formatting
    "format_document",
    "format_range",
    # rust-analyzer extensions
    "expand_macro",
]
