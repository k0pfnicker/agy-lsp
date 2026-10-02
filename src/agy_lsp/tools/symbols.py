"""MCP tools for document and workspace symbols: document_symbols and workspace_symbols."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from agy_lsp.config import PluginConfig
from agy_lsp.lsp.manager import LspManager
from agy_lsp.lsp.protocol import format_symbol_kind
from agy_lsp.utils.formatting import limit_and_sort_results
from agy_lsp.utils.paths import (
    is_safe_workspace_path,
    normalize_path,
    uri_to_path,
)


def _format_symbol_node(node: dict[str, Any], query: Optional[str] = None) -> Optional[dict[str, Any]]:
    """Format an LSP DocumentSymbol or SymbolInformation into a compact dictionary."""
    name = node.get("name", "")
    if query and query.lower() not in name.lower():
        # Check if any children match before discarding
        children = node.get("children", [])
        formatted_children = []
        for child in children:
            fc = _format_symbol_node(child, query)
            if fc:
                formatted_children.append(fc)
        if not formatted_children:
            return None
    else:
        children = node.get("children", [])
        formatted_children = [fc for c in children if (fc := _format_symbol_node(c, query)) is not None]

    kind_int = node.get("kind", 0)
    kind_name = format_symbol_kind(kind_int)

    # Range can be in 'range' or 'location.range'
    range_obj = node.get("range") or (node.get("location", {}).get("range", {}))
    start = range_obj.get("start", {})
    end = range_obj.get("end", {})

    res: dict[str, Any] = {
        "name": name,
        "kind": kind_name,
        "line": start.get("line", 0) + 1,
        "column": start.get("character", 0) + 1,
        "end_line": end.get("line", start.get("line", 0)) + 1,
    }

    detail = node.get("detail")
    if detail:
        res["detail"] = detail.strip()

    container = node.get("containerName")
    if container:
        res["container"] = container

    if formatted_children:
        res["children"] = formatted_children

    return res


async def document_symbols_tool(
    manager: LspManager,
    config: PluginConfig,
    file_path: str,
    query: Optional[str] = None,
) -> dict[str, Any]:
    """List classes, methods, properties, and symbols in a document.

    Args:
        file_path: Path to the target source file.
        query: Optional string to filter symbols by name.
    """
    workspace_root = config.workspaceRoot or normalize_path(".")
    norm_path = normalize_path(file_path)

    if not is_safe_workspace_path(norm_path, workspace_root, config.allowOutsideWorkspace):
        return {"error": f"Security restriction: Access to file '{file_path}' outside workspace is denied."}

    if not Path(norm_path).exists():
        return {"error": f"File not found: '{file_path}'"}

    client = await manager.get_client_for_file(norm_path)
    raw_symbols = await client.get_document_symbols(norm_path)

    if not raw_symbols:
        return {"symbols": [], "count": 0}

    formatted = []
    for item in raw_symbols:
        if isinstance(item, dict):
            node = _format_symbol_node(item, query)
            if node:
                formatted.append(node)

    return {"count": len(formatted), "symbols": formatted}


async def workspace_symbols_tool(
    manager: LspManager,
    config: PluginConfig,
    query: str,
    limit: Optional[int] = None,
) -> dict[str, Any]:
    """Search for symbols across the entire workspace.

    Args:
        query: Search string to match symbol names.
        limit: Maximum number of results to return.
    """
    active_clients = await manager.get_all_active_clients()
    if not active_clients:
        # If no client active yet, try resolving default or python
        try:
            client = await manager.get_client_for_language("python")
            active_clients = [client]
        except Exception:
            active_clients = []

    if not active_clients:
        return {
            "symbols": [],
            "count": 0,
            "message": "No active language servers to query workspace symbols.",
        }

    raw_results = []
    for client in active_clients:
        try:
            res = await client.get_workspace_symbols(query)
            if isinstance(res, list):
                raw_results.extend(res)
        except Exception:
            pass

    symbols = []
    for sym in raw_results:
        if not isinstance(sym, dict):
            continue
        loc = sym.get("location", {})
        uri = loc.get("uri", "")
        range_obj = loc.get("range", {})
        start = range_obj.get("start", {})

        try:
            fpath = uri_to_path(uri) if uri else ""
        except Exception:
            fpath = uri

        symbols.append(
            {
                "name": sym.get("name", ""),
                "kind": format_symbol_kind(sym.get("kind", 0)),
                "file": fpath,
                "line": start.get("line", 0) + 1,
                "column": start.get("character", 0) + 1,
                "container": sym.get("containerName"),
            }
        )

    max_limit = limit if limit is not None else config.maxResults
    limited, truncated, total_count = limit_and_sort_results(symbols, limit=max_limit, sort_key="name")

    res: dict[str, Any] = {
        "count": len(limited),
        "total": total_count,
        "symbols": limited,
    }
    if truncated:
        res["truncated"] = True
        res["note"] = f"Results limited to {max_limit}. Total symbols found: {total_count}."

    return res
