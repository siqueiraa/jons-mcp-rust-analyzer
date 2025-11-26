"""Utility functions for the MCP rust-analyzer server."""

from pathlib import Path
from typing import Any, Callable, TypeVar

from .constants import DEFAULT_PAGINATION_LIMIT, DEFAULT_PAGINATION_OFFSET

T = TypeVar("T")


def ensure_file_uri(file_path: str) -> str:
    """Convert file path to proper file URI.

    Args:
        file_path: Path to the file (absolute, relative, or already a URI)

    Returns:
        Properly formatted file:// URI
    """
    if file_path.startswith("file://"):
        return file_path

    path = Path(file_path)
    if not path.is_absolute():
        path = Path.cwd() / path

    return f"file://{path.absolute()}"


def apply_pagination(
    items: list[T],
    offset: int = DEFAULT_PAGINATION_OFFSET,
    limit: int = DEFAULT_PAGINATION_LIMIT,
    add_offset_field: bool = True,
) -> tuple[list[T | dict[str, Any]], dict[str, Any]]:
    """Apply pagination to a list of items.

    Args:
        items: The full list of items to paginate
        offset: Number of items to skip
        limit: Maximum number of items to return
        add_offset_field: Whether to add an 'offset' field to each item

    Returns:
        Tuple of (paginated_items, metadata_dict)
    """
    total_items = len(items)
    start_idx = min(offset, total_items)
    end_idx = min(start_idx + limit, total_items)
    paginated = items[start_idx:end_idx]

    # Add offset field to each item if requested
    result_items: list[T | dict[str, Any]]
    if add_offset_field:
        processed_items: list[dict[str, Any]] = []
        for i, item in enumerate(paginated):
            if isinstance(item, dict):
                processed_item = item.copy()
            else:
                processed_item = {"item": item}
            processed_item["offset"] = start_idx + i
            processed_items.append(processed_item)
        result_items = processed_items  # type: ignore[assignment]
    else:
        result_items = list(paginated)

    has_more = end_idx < total_items

    metadata = {
        "totalItems": total_items,
        "offset": offset,
        "limit": limit,
        "hasMore": has_more,
        "nextOffset": end_idx if has_more else None,
    }

    return result_items, metadata


# Sort key functions for consistent pagination ordering


def completion_sort_key(item: dict[str, Any]) -> tuple[str, str]:
    """Sort key for completion items.

    Sorts by sortText (if available), then by label.
    """
    sort_text = item.get("sortText", item.get("label", ""))
    label = item.get("label", "")
    return (sort_text, label)


def members_sort_key(item: dict[str, Any]) -> tuple[int, str, str]:
    """Sort key for members (fields first, then methods, then others).

    LSP CompletionItemKind values:
    - 5 = Field
    - 2 = Method
    - 3 = Function
    """
    kind = item.get("kind", 999)
    # Priority: Fields (5) first, then Methods (2), then Functions (3), then others
    kind_priority = {5: 0, 2: 1, 3: 2}.get(kind, 3)
    sort_text = item.get("sortText", item.get("label", ""))
    label = item.get("label", "")
    return (kind_priority, sort_text, label)


def location_sort_key(item: dict[str, Any]) -> tuple[str, int, int]:
    """Sort key for items with location info (references, etc.).

    Sorts by URI, then by line, then by character.
    """
    uri = item.get("uri", "")
    start = item.get("range", {}).get("start", {})
    line = start.get("line", 0)
    char = start.get("character", 0)
    return (uri, line, char)


def symbol_sort_key(item: dict[str, Any]) -> tuple[int, str]:
    """Sort key for document symbols.

    Sorts by line number, then by name.
    """
    start = item.get("range", {}).get("start", {})
    line = start.get("line", 0)
    name = item.get("fullName", item.get("name", ""))
    return (line, name)


def workspace_symbol_sort_key(item: dict[str, Any]) -> tuple[str, str, int]:
    """Sort key for workspace symbols.

    Sorts by name, then by URI, then by line.
    """
    name = item.get("name", "")
    location = item.get("location", {})
    uri = location.get("uri", "")
    line = location.get("range", {}).get("start", {}).get("line", 0)
    return (name, uri, line)


def diagnostic_sort_key(item: dict[str, Any]) -> tuple[int, str, int, int]:
    """Sort key for diagnostics.

    Sorts by severity (errors first), then by URI, then by position.
    """
    severity = item.get("severity", 999)  # Lower is more severe
    uri = item.get("uri", "")
    start = item.get("range", {}).get("start", {})
    line = start.get("line", 0)
    char = start.get("character", 0)
    return (severity, uri, line, char)


def flatten_document_symbols(
    symbols: list[dict[str, Any]],
    parent_name: str = "",
) -> list[dict[str, Any]]:
    """Flatten hierarchical document symbols for pagination.

    Args:
        symbols: List of potentially nested symbols
        parent_name: Name of parent symbol for context

    Returns:
        Flattened list of symbols with fullName field added
    """
    flat: list[dict[str, Any]] = []
    for symbol in symbols:
        # Add parent context to name for clarity
        if parent_name:
            symbol["fullName"] = f"{parent_name}::{symbol['name']}"
        else:
            symbol["fullName"] = symbol["name"]

        flat.append(symbol)

        # Recursively flatten children
        if "children" in symbol:
            flat.extend(flatten_document_symbols(symbol["children"], symbol["fullName"]))

    return flat
