"""Code intelligence tools (diagnostics, code_actions, rename)."""

from typing import Any

from fastmcp import Context

from ..constants import DEFAULT_PAGINATION_LIMIT, DEFAULT_PAGINATION_OFFSET, LSPMethods
from ..exceptions import LSPRequestError
from ..utils import apply_pagination, diagnostic_sort_key, ensure_file_uri


async def diagnostics(
    file_path: str | None = None,
    limit: int = DEFAULT_PAGINATION_LIMIT,
    offset: int = DEFAULT_PAGINATION_OFFSET,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Get compiler errors and warnings.

    Returns {items, totalItems, hasMore, nextOffset} where each item has:
    - uri: File containing the diagnostic
    - range: Location in file
    - severity: 1=Error, 2=Warning, 3=Info, 4=Hint
    - message: Description of the issue

    If file_path is omitted, returns diagnostics for all open files.
    Paginated: use limit/offset, check hasMore for more results.
    """
    from ..server import current_diagnostics

    if ctx:
        await ctx.info(
            f"Getting diagnostics for {file_path or 'all files'} "
            f"(limit: {limit}, offset: {offset})"
        )

    if file_path:
        file_uri = ensure_file_uri(file_path)
        file_diagnostics = {file_uri: current_diagnostics.get(file_uri, [])}
    else:
        file_diagnostics = current_diagnostics

    items: list[dict[str, Any]] = []
    for uri, diags in file_diagnostics.items():
        for diag in diags:
            item = diag.copy()
            item["uri"] = uri
            items.append(item)

    items.sort(key=diagnostic_sort_key)
    paginated_items, metadata = apply_pagination(items, offset, limit)

    return {"items": paginated_items, **metadata}


async def rename(
    file_path: str,
    line: int,
    character: int,
    new_name: str,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Rename symbol at position (0-indexed) across the entire project.

    Returns WorkspaceEdit with {changes: {uri: [TextEdit]}} or {documentChanges: [...]}.
    All references to the symbol across all files will be updated.
    Returns {error} if rename is not possible at this position.
    """
    from ..server import ensure_rust_analyzer_indexed

    client = await ensure_rust_analyzer_indexed()
    file_uri = ensure_file_uri(file_path)

    if ctx:
        await ctx.info(
            f"Renaming symbol at {file_path}:{line}:{character} to '{new_name}'"
        )

    try:
        prepare_result = await client.request(
            LSPMethods.PREPARE_RENAME,
            {
                "textDocument": {"uri": file_uri},
                "position": {"line": line, "character": character},
            },
        )

        if not prepare_result:
            return {"error": "Cannot rename at this position"}

    except LSPRequestError:
        return {"error": "Cannot rename at this position"}

    response = await client.request(
        LSPMethods.RENAME,
        {
            "textDocument": {"uri": file_uri},
            "position": {"line": line, "character": character},
            "newName": new_name,
        },
    )

    return response or {"changes": {}}
