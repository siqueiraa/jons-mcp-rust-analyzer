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
    """Get completions at position. Paginated: use limit/offset, check hasMore for more results."""
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
    """Find all references to symbol. Paginated: use limit/offset, check hasMore for more results."""
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
    """Get all symbols in file (functions, structs, etc.). Paginated: use limit/offset, check hasMore for more results."""
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
    """Search symbols across workspace. Query can be partial name. Paginated: use limit/offset, check hasMore for more results."""
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


async def members(
    file_path: str,
    line: int,
    character: int,
    limit: int = DEFAULT_PAGINATION_LIMIT,
    offset: int = DEFAULT_PAGINATION_OFFSET,
    include_detail: bool = True,
    include_documentation: bool = False,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Get methods/fields available on the type at position.

    Returns the members (methods, fields) that can be accessed on the expression
    at the given position. The position can be anywhere on an identifier - the tool
    will find the end of it. Paginated: use limit/offset, check hasMore.
    """
    import asyncio
    import logging
    from pathlib import Path

    from ..server import ensure_rust_analyzer_indexed

    logger = logging.getLogger(__name__)

    client = await ensure_rust_analyzer_indexed()
    file_uri = ensure_file_uri(file_path)

    if ctx:
        await ctx.info(
            f"Getting members at {file_path}:{line}:{character} "
            f"(limit: {limit}, offset: {offset})"
        )

    # Read the actual file content
    resolved_path = Path(file_path)
    if not resolved_path.is_absolute():
        resolved_path = Path.cwd() / file_path

    original_content = resolved_path.read_text()
    file_lines = original_content.splitlines(keepends=True)

    # Handle case where file doesn't end with newline
    if original_content and not original_content.endswith('\n'):
        if file_lines:
            file_lines[-1] = file_lines[-1] + '\n'

    # Find the end of the identifier at the given position and insert '.' there
    completion_char = character + 1  # Default: right after given position
    original_line = ""
    modified_line = ""

    if line < len(file_lines):
        current_line = file_lines[line]
        original_line = current_line.rstrip('\n')
        line_content = original_line

        # Start at the given character position
        char_pos = min(character, len(line_content))

        # Scan right to find the end of the identifier
        end_pos = char_pos
        while end_pos < len(line_content) and (
            line_content[end_pos].isalnum() or line_content[end_pos] == '_'
        ):
            end_pos += 1

        # Check if there's already a '.' right after the identifier
        already_has_dot = end_pos < len(line_content) and line_content[end_pos] == '.'

        if already_has_dot:
            # Already has a dot - use original file, request completion after the dot
            completion_char = end_pos + 1
            modified_line = line_content
            modified_content = original_content  # Use original file as-is
            logger.info(f"members: found existing dot at position {end_pos}, using original file")
        else:
            # Insert dot at end of identifier, truncate rest of line to keep it clean
            modified_line = line_content[:end_pos] + '.'
            file_lines[line] = modified_line + '\n'
            completion_char = end_pos + 1
            modified_content = ''.join(file_lines)
            already_has_dot = False
    else:
        # Line doesn't exist, append lines as needed
        while len(file_lines) <= line:
            file_lines.append('\n')
        file_lines[line] = '.\n'
        modified_line = '.'
        modified_content = ''.join(file_lines)
        already_has_dot = False

    # Debug logging
    logger.info(f"members: file_uri={file_uri}")
    logger.info(f"members: line={line}, char={character}, completion_char={completion_char}")
    logger.info(f"members: original_line={original_line!r}")
    logger.info(f"members: modified_line={modified_line!r}")
    logger.info(f"members: already_has_dot={already_has_dot}")

    if already_has_dot:
        # File already has the dot - just request completion directly
        # rust-analyzer already has this file indexed
        logger.info("members: requesting completion directly (no didOpen needed)")
        response = await client.request(
            LSPMethods.COMPLETION,
            {
                "textDocument": {"uri": file_uri},
                "position": {"line": line, "character": completion_char},
            },
        )
        logger.info(f"members: got response type={type(response)}, "
                    f"items={len(response.get('items', [])) if isinstance(response, dict) else len(response) if isinstance(response, list) else 'N/A'}")
    else:
        # Need to open with modified content
        # Use the REAL file URI - didOpen makes rust-analyzer use our modified content
        # while keeping full project context (imports, dependencies, type resolution)
        try:
            logger.info("members: sending didOpen with modified content")
            await client.notify(
                LSPMethods.DID_OPEN,
                {
                    "textDocument": {
                        "uri": file_uri,
                        "languageId": "rust",
                        "version": 1,
                        "text": modified_content,
                    }
                },
            )

            # Give rust-analyzer time to process the document
            await asyncio.sleep(0.1)

            logger.info(f"members: requesting completion at line={line}, char={completion_char}")
            response = await client.request(
                LSPMethods.COMPLETION,
                {
                    "textDocument": {"uri": file_uri},
                    "position": {"line": line, "character": completion_char},
                },
            )
            logger.info(f"members: got response type={type(response)}, "
                        f"items={len(response.get('items', [])) if isinstance(response, dict) else len(response) if isinstance(response, list) else 'N/A'}")
        finally:
            # Close the document - rust-analyzer reverts to disk content
            logger.info("members: sending didClose")
            await client.notify(
                LSPMethods.DID_CLOSE,
                {"textDocument": {"uri": file_uri}},
            )

    # Process results (same as completion)
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
