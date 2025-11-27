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


def members_method_sort_key(method: dict[str, Any]) -> tuple[int, str, str]:
    """Sort key for members methods: inherent first, then by trait, then by name."""
    trait = method.get("trait")
    is_inherent = 0 if trait is None else 1
    return (is_inherent, trait or "", method.get("name", ""))


def parse_impl_name(name: str) -> tuple[str | None, str]:
    """Parse 'impl Trait for Type' or 'impl Type' patterns.

    Args:
        name: The impl block name from document_symbols (e.g., "impl Clone for MyStruct")

    Returns:
        Tuple of (trait_name or None, type_name)
    """
    import re

    # Match "impl TraitName for TypeName"
    trait_match = re.match(r"impl(?:<[^>]+>)?\s+(\w+(?:::\w+)*)\s+for\s+(.+)", name)
    if trait_match:
        return (trait_match.group(1), trait_match.group(2).strip())

    # Match "impl TypeName" (inherent impl)
    inherent_match = re.match(r"impl(?:<[^>]+>)?\s+(.+)", name)
    if inherent_match:
        return (None, inherent_match.group(1).strip())

    return (None, name)


def parse_method_label(label: str) -> tuple[str, str | None, bool]:
    """Parse completion label to extract method name, trait, and import status.

    rust-analyzer completion labels use these formats:
    - "method_name"                    -> inherent method, no trait
    - "method_name (as TraitName)"     -> trait method, already imported
    - "method_name (use path::Trait)"  -> trait method, needs import

    Args:
        label: The completion item label from rust-analyzer

    Returns:
        Tuple of (method_name, trait_name or None, needs_import)
    """
    import re

    # Match "method (as Trait)" - trait already in scope
    as_match = re.match(r"^(\w+)\s*\(as\s+(.+)\)$", label)
    if as_match:
        return (as_match.group(1), as_match.group(2), False)

    # Match "method (use path::Trait)" - trait needs import
    use_match = re.match(r"^(\w+)\s*\(use\s+(.+)\)$", label)
    if use_match:
        # Extract just the trait name from the path
        path = use_match.group(2)
        trait_name = path.split("::")[-1] if "::" in path else path
        return (use_match.group(1), trait_name, True)

    # Plain method name - inherent impl
    return (label, None, False)


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
            flat.extend(
                flatten_document_symbols(symbol["children"], symbol["fullName"])
            )

    return flat
