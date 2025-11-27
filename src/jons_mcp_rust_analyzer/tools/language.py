"""Core language feature tools."""

from pathlib import Path
from typing import Any

from fastmcp import Context

from ..constants import DEFAULT_PAGINATION_LIMIT, DEFAULT_PAGINATION_OFFSET, LSPMethods
from ..utils import (
    apply_pagination,
    completion_sort_key,
    ensure_file_uri,
    flatten_document_symbols,
    location_sort_key,
    members_method_sort_key,
    parse_method_label,
    symbol_sort_key,
    workspace_symbol_sort_key,
)


async def symbol_info(
    file_path: str,
    line: int,
    character: int,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Get type signature and documentation for symbol at position (0-indexed).

    Returns {contents} with markdown-formatted type info and docs.
    Use this to get full details for any symbol, field, or method.
    """
    from ..server import ensure_rust_analyzer_indexed

    client = await ensure_rust_analyzer_indexed()
    file_uri = ensure_file_uri(file_path)

    if ctx:
        await ctx.info(f"Getting symbol info at {file_path}:{line}:{character}")

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
    """Get code completions at position (0-indexed).

    Returns {items, totalItems, hasMore, nextOffset} where each item has:
    - label: Completion text
    - kind: Completion type (1=Text, 2=Method, 3=Function, 5=Field, 6=Variable, etc.)
    - detail: Type signature (if include_detail=true)
    - documentation: Doc comments (if include_documentation=true)

    Paginated: use limit/offset, check hasMore for more results.
    """
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
    """Go to definition of symbol at position (0-indexed).

    Returns location(s) where the symbol is defined: {uri, range}.
    Use this to jump from a variable/function usage to its declaration.
    """
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
    """Go to type definition of symbol at position (0-indexed).

    Returns location(s) where the type is defined: {uri, range}.
    Use this to find the struct/enum/trait definition for a variable's type.
    """
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
    """Find implementations of trait or type at position (0-indexed).

    Returns location(s) of impl blocks: {uri, range}.
    Call on a trait to find all types implementing it, or on a type to find its impl blocks.
    """
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
    """Find all references to symbol at position (0-indexed).

    Returns {items, totalItems, hasMore, nextOffset} where each item has {uri, range}.
    Set include_declaration=false to exclude the definition itself.
    Paginated: use limit/offset, check hasMore for more results.
    """
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
    """Get all symbols defined in a file (functions, structs, enums, etc.).

    Returns {items, totalItems, hasMore, nextOffset} where each item has:
    - name, fullName: Symbol name (fullName includes parent context like "MyStruct::method")
    - kind: Symbol type (5=Class, 6=Method, 8=Field, 12=Function, 23=Struct, etc.)
    - range: Location in file

    Paginated: use limit/offset, check hasMore for more results.
    """
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
    """Search for symbols across the entire workspace by name.

    Returns {items, totalItems, hasMore, nextOffset} where each item has:
    - name: Symbol name
    - kind: Symbol type (5=Class, 12=Function, 23=Struct, etc.)
    - location: {uri, range} where the symbol is defined

    Query can be a partial name (e.g., "MyStr" matches "MyStruct").
    Paginated: use limit/offset, check hasMore for more results.
    """
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


def _build_symbol_info_args(uri: str, symbol: dict[str, Any]) -> dict[str, Any]:
    """Build args dict for calling symbol_info on this symbol."""
    # Convert file:// URI to path
    file_path = uri.replace("file://", "")
    start = symbol.get("selectionRange", symbol.get("range", {})).get("start", {})
    return {
        "file_path": file_path,
        "line": start.get("line", 0),
        "character": start.get("character", 0),
    }


async def _get_methods_via_completion(
    client: Any,
    file_uri: str,
    file_path: str,
    line: int,
    character: int,
    include_documentation: bool = False,
) -> list[dict[str, Any]]:
    """Get available methods using completion after a dot.

    The cursor can be anywhere in a variable name. This function:
    1. Finds the end of the current token (variable name)
    2. Checks if there's already a dot after it
    3. If no dot, inserts one temporarily using didChange
    4. Calls completion at the position after the dot
    5. Uses completionItem/resolve to get method signatures (detail field)
    6. Restores the original content if modified

    Args:
        include_documentation: If True, include doc comments for each method
    """
    import logging

    logger = logging.getLogger(__name__)

    # Read file content to find token boundaries
    content = Path(file_path).read_text()
    lines_list = content.splitlines()
    current_line = lines_list[line] if line < len(lines_list) else ""

    # Find end of current token (variable name)
    # Token ends at first non-identifier character
    token_end = character
    while token_end < len(current_line) and (
        current_line[token_end].isalnum() or current_line[token_end] == "_"
    ):
        token_end += 1

    # Check if there's already a dot after the token
    has_dot = token_end < len(current_line) and current_line[token_end] == "."

    # Track document version - start at 2 (1 was didOpen)
    doc_version = 2

    if has_dot:
        # Dot already exists, complete at position after dot
        dot_position = token_end + 1
        logger.info(f"members: dot already exists, completing at {line}:{dot_position}")
        response = await client.request(
            LSPMethods.COMPLETION,
            {
                "textDocument": {"uri": file_uri},
                "position": {"line": line, "character": dot_position},
            },
        )
    else:
        # Need to insert a dot - use didChange to modify document temporarily
        # Insert "." after the token
        modified_line = current_line[:token_end] + "." + current_line[token_end:]
        modified_lines = lines_list.copy()
        modified_lines[line] = modified_line

        logger.info(
            f"members: inserting dot at {line}:{token_end}, completing at {line}:{token_end + 1}"
        )

        # Send didChange with the modified content
        await client.notify(
            "textDocument/didChange",
            {
                "textDocument": {"uri": file_uri, "version": doc_version},
                "contentChanges": [{"text": "\n".join(modified_lines)}],
            },
        )
        doc_version += 1

        # Complete at position after the inserted dot
        response = await client.request(
            LSPMethods.COMPLETION,
            {
                "textDocument": {"uri": file_uri},
                "position": {"line": line, "character": token_end + 1},
            },
        )

    # Filter to method-like items
    # CompletionItemKind: 2=Method, 3=Function
    items = (
        response
        if isinstance(response, list)
        else (response.get("items", []) if response else [])
    )
    method_items = [item for item in items if item.get("kind") in (2, 3)]

    methods: list[dict[str, Any]] = []

    # Build method list from completion items
    # We use completionItem/resolve to get the full detail (method signature)
    # Note: We don't provide symbol_info_args for methods because definition lookup
    # is unreliable (trait methods go to trait definitions in external crates)
    for item in method_items:
        label = item.get("label", "")
        name, trait_info, needs_import = parse_method_label(label)

        # Get full detail via completionItem/resolve
        detail = item.get("detail")
        documentation = None
        try:
            resolved = await client.request("completionItem/resolve", item)
            if resolved:
                if detail is None:
                    detail = resolved.get("detail")
                # Only extract documentation if requested (can be large)
                if include_documentation:
                    doc = resolved.get("documentation")
                    if doc:
                        if isinstance(doc, str):
                            documentation = doc
                        elif isinstance(doc, dict):
                            documentation = doc.get("value")
        except Exception as e:
            logger.warning(f"Failed to resolve completion item {name}: {e}")

        method_entry: dict[str, Any] = {
            "name": name,
            "kind": item.get("kind"),
            "detail": detail,
            "trait": trait_info,
            "needsImport": needs_import,
        }
        if include_documentation:
            method_entry["documentation"] = documentation
        methods.append(method_entry)

    # Restore original content if we modified it
    if not has_dot:
        await client.notify(
            "textDocument/didChange",
            {
                "textDocument": {"uri": file_uri, "version": doc_version},
                "contentChanges": [{"text": content}],
            },
        )

    return methods


async def members(
    file_path: str,
    line: int,
    character: int,
    limit: int = DEFAULT_PAGINATION_LIMIT,
    offset: int = DEFAULT_PAGINATION_OFFSET,
    include_documentation: bool = False,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Get fields and methods available on the type at position.

    Call this on a variable to discover all fields and methods you can access on it.

    Response includes:
    - typeName, typeKind: The type's name and kind (struct, enum, etc.)
    - fields: Array of {name, kind, detail}
      - detail: Field type (e.g., "i32", "Vec<String>")
    - methods: Array of {name, kind, detail, trait, needsImport}
      - detail: Method signature with parameter names (e.g., "fn(&self, count: i32) -> bool")
      - trait: Which trait this method comes from, or null for inherent methods
      - needsImport: Whether the trait needs to be imported to use this method
      - documentation: (only if include_documentation=True) Doc comments

    Args:
        include_documentation: If True, include doc comments for methods (default False)

    Paginated: use limit/offset for methods, check hasMore for more results.
    """
    import logging

    from ..server import ensure_rust_analyzer_indexed

    logger = logging.getLogger(__name__)

    client = await ensure_rust_analyzer_indexed()
    file_uri = ensure_file_uri(file_path)

    # Resolve the file path for reading
    resolved_path = file_path
    if not Path(file_path).is_absolute():
        resolved_path = str(Path.cwd() / file_path)

    if ctx:
        await ctx.info(
            f"Getting members at {file_path}:{line}:{character} "
            f"(limit: {limit}, offset: {offset})"
        )

    # Step 1: Get type definition location
    type_def_response = await client.request(
        LSPMethods.TYPE_DEFINITION,
        {
            "textDocument": {"uri": file_uri},
            "position": {"line": line, "character": character},
        },
    )

    if not type_def_response:
        return {"error": "No type definition found at position"}

    # Handle single location or array of locations
    if isinstance(type_def_response, list):
        type_location = type_def_response[0] if type_def_response else None
    else:
        type_location = type_def_response

    if not type_location:
        return {"error": "No type definition found at position"}

    # Handle both Location (uri, range) and LocationLink (targetUri, targetRange) formats
    type_uri = type_location.get("uri") or type_location.get("targetUri") or ""
    type_range = type_location.get("range") or type_location.get("targetRange") or {}
    type_start = type_range.get("start", {})
    type_line = type_start.get("line", 0)

    if not type_uri:
        return {"error": "No type definition found at position (empty URI)"}

    logger.info(f"members: type definition at {type_uri}:{type_line}")

    # Step 2: Open the type definition file if it's a local file
    # This is needed for hover to work on fields
    type_file_path = type_uri.replace("file://", "")
    type_file_content = None
    if Path(type_file_path).exists():
        try:
            type_file_content = Path(type_file_path).read_text()
            await client.notify(
                LSPMethods.DID_OPEN,
                {
                    "textDocument": {
                        "uri": type_uri,
                        "languageId": "rust",
                        "version": 1,
                        "text": type_file_content,
                    }
                },
            )
        except Exception as e:
            logger.warning(f"Failed to open type file {type_uri}: {e}")

    # Step 3: Get document symbols for the type definition file to find fields
    type_symbols_response = await client.request(
        LSPMethods.DOCUMENT_SYMBOL,
        {"textDocument": {"uri": type_uri}},
    )

    type_symbols = type_symbols_response or []

    # Find the type symbol at the definition location
    type_name = "unknown"
    type_kind = "unknown"
    field_symbols: list[dict[str, Any]] = []

    for symbol in type_symbols:
        symbol_range = symbol.get("range", {})
        symbol_start = symbol_range.get("start", {})
        if symbol_start.get("line") == type_line:
            type_name = symbol.get("name", "unknown")
            # LSP SymbolKind: 5=Class, 23=Struct, 10=Enum, 11=Interface
            kind_num = symbol.get("kind", 0)
            kind_map = {5: "class", 23: "struct", 10: "enum", 11: "interface"}
            type_kind = kind_map.get(kind_num, "unknown")

            # Extract fields from children
            for child in symbol.get("children", []):
                child_kind = child.get("kind", 0)
                # LSP SymbolKind: 8=Field
                if child_kind == 8:
                    field_symbols.append(child)
            break

    # Step 3: Get field types via hover
    fields: list[dict[str, Any]] = []
    for field_symbol in field_symbols:
        field_name = field_symbol.get("name", "")
        field_kind = field_symbol.get("kind", 0)

        # Get field type via hover at the field's selection range
        field_detail = None
        selection_range = field_symbol.get("selectionRange", {})
        field_start = selection_range.get("start", {})
        field_line = field_start.get("line", 0)
        field_char = field_start.get("character", 0)

        try:
            hover_response = await client.request(
                LSPMethods.HOVER,
                {
                    "textDocument": {"uri": type_uri},
                    "position": {"line": field_line, "character": field_char},
                },
            )
            if hover_response:
                contents = hover_response.get("contents", {})
                logger.debug(f"Hover for field {field_name}: {contents}")
                # Contents may be string, {kind, value}, or array
                if isinstance(contents, list):
                    # Take first element if array
                    contents = contents[0] if contents else {}
                # Extract type from hover - may be string or {kind, value}
                if isinstance(contents, str):
                    # Parse type from "field_name: type" format
                    if ": " in contents:
                        field_detail = contents.split(": ", 1)[1].strip()
                    else:
                        field_detail = contents
                elif isinstance(contents, dict):
                    value = contents.get("value", "")
                    # Hover returns markdown like "```rust\nfield: Type\n```"
                    # Try multiple parsing strategies
                    lines = value.split("\n")
                    for hover_line in lines:
                        hover_line = hover_line.strip()
                        # Skip code fence markers
                        if hover_line.startswith("```"):
                            continue
                        # Look for "field_name: Type" pattern
                        if hover_line.startswith(f"{field_name}:"):
                            field_detail = hover_line.split(":", 1)[1].strip()
                            field_detail = field_detail.rstrip(",")
                            break
                        # Also try just ": " anywhere in case field name differs
                        elif ": " in hover_line and not hover_line.startswith("//"):
                            # Could be "pub field_name: Type" or similar
                            parts = hover_line.split(": ", 1)
                            if len(parts) == 2:
                                field_detail = parts[1].strip().rstrip(",")
                                break
        except Exception as e:
            logger.warning(f"Failed to get hover for field {field_name}: {e}")

        fields.append(
            {
                "name": field_name,
                "kind": field_kind,
                "detail": field_detail,
            }
        )

    logger.info(
        f"members: found type {type_name} ({type_kind}) with {len(fields)} fields"
    )

    # Close the type file if we opened it
    if type_file_content is not None:
        try:
            await client.notify(
                LSPMethods.DID_CLOSE,
                {"textDocument": {"uri": type_uri}},
            )
        except Exception as e:
            logger.warning(f"Failed to close type file {type_uri}: {e}")

    # Step 5: Get methods via completion (finds ALL methods including trait impls)
    methods = await _get_methods_via_completion(
        client, file_uri, resolved_path, line, character, include_documentation
    )

    # Sort methods: inherent first, then by trait, then by name
    methods.sort(key=members_method_sort_key)

    logger.info(f"members: found {len(methods)} methods via completion")

    # Calculate totals
    total_fields = len(fields)
    total_methods = len(methods)

    # Paginate methods only (fields are typically few and always returned in full)
    start_idx = min(offset, total_methods)
    end_idx = min(start_idx + limit, total_methods)
    paginated_methods = methods[start_idx:end_idx]

    has_more = end_idx < total_methods

    return {
        "typeName": type_name,
        "typeKind": type_kind,
        "fields": fields,
        "methods": paginated_methods,
        "totalFields": total_fields,
        "totalMethods": total_methods,
        "offset": offset,
        "limit": limit,
        "hasMore": has_more,
        "nextOffset": end_idx if has_more else None,
    }
