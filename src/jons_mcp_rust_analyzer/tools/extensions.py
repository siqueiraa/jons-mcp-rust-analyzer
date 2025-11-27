"""rust-analyzer extension tools."""

from typing import Any

from fastmcp import Context

from ..constants import LSPMethods
from ..utils import ensure_file_uri


async def expand_macro(
    file_path: str,
    line: int,
    character: int,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Expand a Rust macro at position (0-indexed).

    Returns {name, expansion} where expansion is the generated code.
    Use this to see what code a macro like derive, vec!, println!, etc. produces.
    Returns {expansion: "No macro found..."} if no macro at position.
    """
    from ..server import ensure_rust_analyzer_indexed

    client = await ensure_rust_analyzer_indexed()
    file_uri = ensure_file_uri(file_path)

    if ctx:
        await ctx.info(f"Expanding macro at {file_path}:{line}:{character}")

    response = await client.request(
        LSPMethods.EXPAND_MACRO,
        {
            "textDocument": {"uri": file_uri},
            "position": {"line": line, "character": character},
        },
    )

    return response or {"expansion": "No macro found at this position"}
