"""MCP tools for rust-analyzer functionality."""

from .extensions import (
    analyzer_status,
    expand_macro,
    related_tests,
    runnables,
)
from .formatting import format_document, format_range
from .intelligence import code_actions, diagnostics, rename
from .language import (
    completion,
    definition,
    document_symbols,
    hover,
    implementation,
    members,
    references,
    type_definition,
    workspace_symbols,
)

__all__ = [
    # Language features
    "hover",
    "completion",
    "members",
    "definition",
    "type_definition",
    "implementation",
    "references",
    "document_symbols",
    "workspace_symbols",
    # Code intelligence
    "diagnostics",
    "code_actions",
    "rename",
    # Formatting
    "format_document",
    "format_range",
    # rust-analyzer extensions
    "expand_macro",
    "analyzer_status",
    "related_tests",
    "runnables",
]
