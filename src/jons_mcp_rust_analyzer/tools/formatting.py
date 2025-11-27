"""Formatting tools."""

from typing import Any

from fastmcp import Context

from ..constants import LSPMethods
from ..utils import ensure_file_uri


async def format_document(
    file_path: str,
    tab_size: int = 4,
    insert_spaces: bool = True,
    ctx: Context | None = None,
) -> list[dict[str, Any]]:
    """Format entire file using rustfmt.

    Returns array of TextEdit objects: {range, newText}.
    Apply these edits to the file to format it.
    Uses rustfmt with the project's rustfmt.toml configuration if present.
    """
    from ..server import ensure_rust_analyzer_indexed

    client = await ensure_rust_analyzer_indexed()
    file_uri = ensure_file_uri(file_path)

    if ctx:
        await ctx.info(f"Formatting {file_path}")

    response = await client.request(
        LSPMethods.FORMATTING,
        {
            "textDocument": {"uri": file_uri},
            "options": {"tabSize": tab_size, "insertSpaces": insert_spaces},
        },
    )

    return response or []


async def format_range(
    file_path: str,
    start_line: int,
    start_char: int,
    end_line: int,
    end_char: int,
    tab_size: int = 4,
    insert_spaces: bool = True,
    ctx: Context | None = None,
) -> list[dict[str, Any]]:
    """Format a specific range in a file (0-indexed).

    Returns array of TextEdit objects: {range, newText}.
    Apply these edits to format the selected range.
    Note: rustfmt may expand the range to include complete items.
    """
    from ..server import ensure_rust_analyzer_indexed

    client = await ensure_rust_analyzer_indexed()
    file_uri = ensure_file_uri(file_path)

    if ctx:
        await ctx.info(f"Formatting range in {file_path}")

    response = await client.request(
        LSPMethods.RANGE_FORMATTING,
        {
            "textDocument": {"uri": file_uri},
            "range": {
                "start": {"line": start_line, "character": start_char},
                "end": {"line": end_line, "character": end_char},
            },
            "options": {"tabSize": tab_size, "insertSpaces": insert_spaces},
        },
    )

    return response or []
