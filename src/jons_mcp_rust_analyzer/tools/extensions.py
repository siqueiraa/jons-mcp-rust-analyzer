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
    """Expand macro at position. Returns expanded code."""
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


async def analyzer_status(ctx: Context | None = None) -> dict[str, Any]:
    """Get rust-analyzer server status including progress info."""
    from ..server import ensure_rust_analyzer

    client = ensure_rust_analyzer()

    if ctx:
        await ctx.info("Getting rust-analyzer status")

    # Get internal status from rust-analyzer
    response = await client.request(LSPMethods.ANALYZER_STATUS, {})
    internal_status = response if isinstance(response, str) else "Status unavailable"

    # Get progress status from our tracking
    progress_status = client.get_progress_status()

    return {
        "progress": progress_status,
        "internalStatus": internal_status,
    }


async def related_tests(
    file_path: str,
    line: int,
    character: int,
    ctx: Context | None = None,
) -> list[dict[str, Any]]:
    """Find tests related to code at position."""
    from ..server import ensure_rust_analyzer_indexed

    client = await ensure_rust_analyzer_indexed()
    file_uri = ensure_file_uri(file_path)

    if ctx:
        await ctx.info(f"Finding related tests at {file_path}:{line}:{character}")

    response = await client.request(
        LSPMethods.RELATED_TESTS,
        {
            "textDocument": {"uri": file_uri},
            "position": {"line": line, "character": character},
        },
    )

    return response or []


async def runnables(
    file_path: str,
    line: int | None = None,
    character: int | None = None,
    ctx: Context | None = None,
) -> list[dict[str, Any]]:
    """Get runnable targets (tests, bins, examples) in file."""
    from ..server import ensure_rust_analyzer_indexed

    client = await ensure_rust_analyzer_indexed()
    file_uri = ensure_file_uri(file_path)

    if ctx:
        await ctx.info(f"Getting runnables for {file_path}")

    params: dict[str, Any] = {"textDocument": {"uri": file_uri}}

    if line is not None and character is not None:
        params["position"] = {"line": line, "character": character}

    response = await client.request(LSPMethods.RUNNABLES, params)

    return response or []
