"""Core language feature tools."""

from typing import Any

from fastmcp import Context

from ..constants import DEFAULT_PAGINATION_LIMIT, DEFAULT_PAGINATION_OFFSET, LSPMethods
from ..utils import (
    apply_pagination,
    completion_sort_key,
    ensure_file_uri,
    flatten_document_symbols,
    location_sort_key,
    symbol_sort_key,
    workspace_symbol_sort_key,
)


async def hover(
    file_path: str,
    line: int,
    character: int,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Get type info and docs at position. Lines/chars are 0-indexed."""
    from ..server import ensure_rust_analyzer_indexed

    client = await ensure_rust_analyzer_indexed()
    file_uri = ensure_file_uri(file_path)

    if ctx:
        await ctx.info(f"Getting hover info at {file_path}:{line}:{character}")

    response = await client.request(
        LSPMethods.HOVER,
        {
            "textDocument": {"uri": file_uri},
            "position": {"line": line, "character": character},
        },
    )

    if not response:
        return {"contents": "No hover information available"}

    return dict(response) if isinstance(response, dict) else {"contents": response}


async def completion(
    file_path: str,
    line: int,
    character: int,
    limit: int = DEFAULT_PAGINATION_LIMIT,
    offset: int = DEFAULT_PAGINATION_OFFSET,
    include_detail: bool = True,
    include_documentation: bool = False,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Get completions at position. Returns paginated items with offset field."""
    from ..server import ensure_rust_analyzer_indexed

    client = await ensure_rust_analyzer_indexed()
    file_uri = ensure_file_uri(file_path)

    if ctx:
        await ctx.info(
            f"Getting completions at {file_path}:{line}:{character} "
            f"(limit: {limit}, offset: {offset})"
        )

    response = await client.request(
        LSPMethods.COMPLETION,
        {
            "textDocument": {"uri": file_uri},
            "position": {"line": line, "character": character},
        },
    )

    items: list[dict[str, Any]] = []
    is_incomplete = False

    if isinstance(response, list):
        items = response
    elif isinstance(response, dict):
        items = response.get("items", [])
        is_incomplete = response.get("isIncomplete", False)

    items.sort(key=completion_sort_key)

    total_items = len(items)
    start_idx = min(offset, total_items)
    end_idx = min(start_idx + limit, total_items)
    paginated_items = items[start_idx:end_idx]

    has_more = end_idx < total_items

    processed_items = []
    for i, item in enumerate(paginated_items):
        processed_item: dict[str, Any] = {
            "label": item.get("label", ""),
            "kind": item.get("kind"),
            "offset": start_idx + i,
        }

        if include_detail and "detail" in item:
            processed_item["detail"] = item["detail"]

        if include_documentation and "documentation" in item:
            processed_item["documentation"] = item["documentation"]

        processed_items.append(processed_item)

    return {
        "items": processed_items,
        "isIncomplete": is_incomplete,
        "totalItems": total_items,
        "offset": offset,
        "limit": limit,
        "hasMore": has_more,
        "nextOffset": end_idx if has_more else None,
        "includeDetail": include_detail,
        "includeDocumentation": include_documentation,
    }


async def definition(
    file_path: str,
    line: int,
    character: int,
    ctx: Context | None = None,
) -> dict[str, Any] | list[dict[str, Any]]:
    """Go to definition of symbol at position."""
    from ..server import ensure_rust_analyzer_indexed

    client = await ensure_rust_analyzer_indexed()
    file_uri = ensure_file_uri(file_path)

    if ctx:
        await ctx.info(f"Finding definition at {file_path}:{line}:{character}")

    response = await client.request(
        LSPMethods.DEFINITION,
        {
            "textDocument": {"uri": file_uri},
            "position": {"line": line, "character": character},
        },
    )

    return response or {"message": "No definition found"}


async def type_definition(
    file_path: str,
    line: int,
    character: int,
    ctx: Context | None = None,
) -> dict[str, Any] | list[dict[str, Any]]:
    """Go to type definition of symbol at position."""
    from ..server import ensure_rust_analyzer_indexed

    client = await ensure_rust_analyzer_indexed()
    file_uri = ensure_file_uri(file_path)

    if ctx:
        await ctx.info(f"Finding type definition at {file_path}:{line}:{character}")

    response = await client.request(
        LSPMethods.TYPE_DEFINITION,
        {
            "textDocument": {"uri": file_uri},
            "position": {"line": line, "character": character},
        },
    )

    return response or {"message": "No type definition found"}


async def implementation(
    file_path: str,
    line: int,
    character: int,
    ctx: Context | None = None,
) -> dict[str, Any] | list[dict[str, Any]]:
    """Find implementations of trait/type at position."""
    from ..server import ensure_rust_analyzer_indexed

    client = await ensure_rust_analyzer_indexed()
    file_uri = ensure_file_uri(file_path)

    if ctx:
        await ctx.info(f"Finding implementations at {file_path}:{line}:{character}")

    response = await client.request(
        LSPMethods.IMPLEMENTATION,
        {
            "textDocument": {"uri": file_uri},
            "position": {"line": line, "character": character},
        },
    )

    return response or {"message": "No implementations found"}


async def references(
    file_path: str,
    line: int,
    character: int,
    include_declaration: bool = True,
    limit: int = DEFAULT_PAGINATION_LIMIT,
    offset: int = DEFAULT_PAGINATION_OFFSET,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Find all references to symbol. Returns paginated items."""
    from ..server import ensure_rust_analyzer_indexed

    client = await ensure_rust_analyzer_indexed()
    file_uri = ensure_file_uri(file_path)

    if ctx:
        await ctx.info(
            f"Finding references at {file_path}:{line}:{character} "
            f"(limit: {limit}, offset: {offset})"
        )

    response = await client.request(
        LSPMethods.REFERENCES,
        {
            "textDocument": {"uri": file_uri},
            "position": {"line": line, "character": character},
            "context": {"includeDeclaration": include_declaration},
        },
    )

    items = response or []
    items.sort(key=location_sort_key)
    paginated_items, metadata = apply_pagination(items, offset, limit)

    return {"items": paginated_items, **metadata}


async def document_symbols(
    file_path: str,
    limit: int = DEFAULT_PAGINATION_LIMIT,
    offset: int = DEFAULT_PAGINATION_OFFSET,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Get all symbols in file (functions, structs, etc.). Paginated."""
    from ..server import ensure_rust_analyzer_indexed

    client = await ensure_rust_analyzer_indexed()
    file_uri = ensure_file_uri(file_path)

    if ctx:
        await ctx.info(
            f"Getting document symbols for {file_path} (limit: {limit}, offset: {offset})"
        )

    response = await client.request(
        LSPMethods.DOCUMENT_SYMBOL,
        {"textDocument": {"uri": file_uri}},
    )

    symbols = response or []
    items = flatten_document_symbols(symbols)
    items.sort(key=symbol_sort_key)

    total_items = len(items)
    start_idx = min(offset, total_items)
    end_idx = min(start_idx + limit, total_items)
    paginated_items = items[start_idx:end_idx]

    processed_items = []
    for i, item in enumerate(paginated_items):
        processed_item = item.copy()
        processed_item["offset"] = start_idx + i
        processed_item.pop("children", None)
        processed_items.append(processed_item)

    has_more = end_idx < total_items

    return {
        "items": processed_items,
        "totalItems": total_items,
        "offset": offset,
        "limit": limit,
        "hasMore": has_more,
        "nextOffset": end_idx if has_more else None,
    }


async def workspace_symbols(
    query: str,
    limit: int = DEFAULT_PAGINATION_LIMIT,
    offset: int = DEFAULT_PAGINATION_OFFSET,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Search symbols across workspace. Query can be partial name."""
    from ..server import ensure_rust_analyzer_indexed

    client = await ensure_rust_analyzer_indexed()

    if ctx:
        await ctx.info(
            f"Searching workspace symbols: {query} (limit: {limit}, offset: {offset})"
        )

    response = await client.request(
        LSPMethods.WORKSPACE_SYMBOL,
        {"query": query},
    )

    items = response or []
    items.sort(key=workspace_symbol_sort_key)
    paginated_items, metadata = apply_pagination(items, offset, limit)

    return {"items": paginated_items, **metadata}
