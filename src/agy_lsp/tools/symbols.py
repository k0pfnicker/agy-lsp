"""MCP tools for document and workspace symbols: document_symbols and workspace_symbols."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Optional

from agy_lsp.config import PluginConfig
from agy_lsp.lsp.manager import LspManager
from agy_lsp.lsp.protocol import format_symbol_kind
from agy_lsp.utils.formatting import limit_and_sort_results
from agy_lsp.utils.paths import (
    detect_language_from_path,
    is_safe_workspace_path,
    normalize_path,
    uri_to_path,
)

_LEAF_MEMBER_KINDS = {8, 22}  # Field (8), EnumMember (22)
_EXECUTABLE_SYMBOL_KINDS = {"Function", "Method", "Constructor"}


def _compute_first_executable_line(file_path: str | Path, decl_line: int, end_line: int) -> int:
    """Compute the first executable statement line inside a function/method body (1-indexed)."""
    try:
        p = Path(file_path)
        if not p.is_file():
            return decl_line
        source = p.read_text(encoding="utf-8", errors="replace")
        lang = detect_language_from_path(p)
        if lang == "python":
            tree = ast.parse(source)
            best_stmt_line: Optional[int] = None
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    node_end = getattr(node, "end_lineno", node.lineno)
                    if node.lineno <= decl_line <= node_end or abs(node.lineno - decl_line) <= 1:
                        body = list(node.body)
                        # Skip leading docstring expression if followed by executable statements
                        if (
                            len(body) > 1
                            and isinstance(body[0], ast.Expr)
                            and isinstance(getattr(body[0], "value", None), ast.Constant)
                            and isinstance(body[0].value.value, str)
                        ):
                            best_stmt_line = body[1].lineno
                        elif body:
                            best_stmt_line = body[0].lineno
                        break
            if best_stmt_line is not None:
                return best_stmt_line

        lines = source.splitlines()
        for line_num in range(decl_line + 1, min(len(lines), end_line) + 1):
            stripped = lines[line_num - 1].strip()
            if not stripped or stripped in ("{", "}") or stripped.startswith(("//", "#", "/*", "*", '"""', "'''")):
                continue
            return line_num
    except Exception:
        pass
    return decl_line


def _format_symbol_node(
    node: dict[str, Any],
    query: Optional[str] = None,
    include_fields: bool = False,
    max_depth: int = 2,
    _depth: int = 1,
) -> Optional[dict[str, Any]]:
    """Format an LSP DocumentSymbol or SymbolInformation into a compact dictionary."""
    name = node.get("name", "")
    raw_children = node.get("children", [])

    # Filter out leaf struct fields / enum members unless include_fields=True or query is provided
    if not include_fields and not query:
        filtered_children = [
            c for c in raw_children if isinstance(c, dict) and c.get("kind", 0) not in _LEAF_MEMBER_KINDS
        ]
        omitted_fields = len(raw_children) - len(filtered_children)
    else:
        filtered_children = [c for c in raw_children if isinstance(c, dict)]
        omitted_fields = 0

    can_recurse = _depth < max_depth or bool(query)

    if query and query.lower() not in name.lower():
        # Check if any children match before discarding
        formatted_children = []
        if can_recurse:
            for child in filtered_children:
                fc = _format_symbol_node(
                    child, query=query, include_fields=include_fields, max_depth=max_depth, _depth=_depth + 1
                )
                if fc:
                    formatted_children.append(fc)
        if not formatted_children:
            return None
    else:
        if can_recurse:
            formatted_children = [
                fc
                for c in filtered_children
                if (
                    fc := _format_symbol_node(
                        c, query=query, include_fields=include_fields, max_depth=max_depth, _depth=_depth + 1
                    )
                )
                is not None
            ]
        else:
            formatted_children = []

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
    elif raw_children and not can_recurse:
        res["children_count"] = len(raw_children)

    if omitted_fields > 0:
        res["fields_count"] = omitted_fields

    return res


def _match_symbol_in_tree(
    nodes: list[dict[str, Any]],
    target_parts: list[str],
    parent_chain: Optional[list[str]] = None,
) -> Optional[dict[str, Any]]:
    """Search a formatted document_symbols tree for a simple ('add') or qualified ('Calculator.add') symbol."""
    chain = parent_chain or []
    for node in nodes:
        name = str(node.get("name", ""))
        base_name = name.split("(")[0].strip()
        cur_chain = [*chain, base_name]

        if len(target_parts) == 1:
            if base_name == target_parts[0] or name == target_parts[0]:
                return node
        else:
            if len(cur_chain) >= len(target_parts) and cur_chain[-len(target_parts) :] == target_parts:
                return node

        children = node.get("children", [])
        if isinstance(children, list) and children:
            found = _match_symbol_in_tree(children, target_parts, cur_chain)
            if found is not None:
                return found
    return None


async def resolve_symbol_target(
    manager: LspManager,
    config: PluginConfig,
    symbol: str,
    context_file: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Resolve a symbol name (e.g. 'calculate_total' or 'Calculator.add') to file, declaration line, and body_line.

    Designed for direct integration with agy-dap SymbolResolver so breakpoints can target functions/methods by name.
    """
    cleaned = symbol.strip()
    if not cleaned:
        return None
    parts = [p.strip() for p in cleaned.replace("::", ".").split(".") if p.strip()]
    if not parts:
        return None

    if context_file:
        doc_res = await document_symbols_tool(
            manager=manager,
            config=config,
            file_path=context_file,
            include_fields=True,
            max_depth=6,
        )
        symbols = doc_res.get("symbols", [])
        if isinstance(symbols, list) and symbols:
            matched = _match_symbol_in_tree(symbols, parts)
            if matched is not None:
                norm_file = normalize_path(context_file)
                decl_line = int(matched.get("line", 1))
                end_line = int(matched.get("end_line", decl_line))
                kind = str(matched.get("kind", "Function"))
                body_line = (
                    _compute_first_executable_line(norm_file, decl_line, end_line)
                    if kind in _EXECUTABLE_SYMBOL_KINDS
                    else decl_line
                )
                return {
                    "name": matched.get("name", parts[-1]),
                    "symbol": cleaned,
                    "kind": kind,
                    "file": norm_file,
                    "line": decl_line,
                    "body_line": body_line,
                    "column": int(matched.get("column", 1)),
                    "end_line": end_line,
                    "provider": "agy-lsp",
                }

    # Fallback to workspace_symbols search
    leaf_query = parts[-1]
    ws_res = await workspace_symbols_tool(manager=manager, config=config, query=leaf_query, limit=25)
    for item in ws_res.get("symbols", []):
        if not isinstance(item, dict):
            continue
        item_name = str(item.get("name", "")).split("(")[0].strip()
        if item_name == leaf_query:
            if len(parts) > 1:
                container = str(item.get("container") or "")
                if parts[-2] not in container:
                    continue
            fpath = str(item.get("file", ""))
            decl_line = int(item.get("line", 1))
            body_line = _compute_first_executable_line(fpath, decl_line, decl_line + 50) if fpath else decl_line
            return {
                "name": item.get("name", leaf_query),
                "symbol": cleaned,
                "kind": str(item.get("kind", "Function")),
                "file": fpath,
                "line": decl_line,
                "body_line": body_line,
                "column": int(item.get("column", 1)),
                "end_line": decl_line,
                "provider": "agy-lsp",
            }

    return None


async def document_symbols_tool(
    manager: LspManager,
    config: PluginConfig,
    file_path: str,
    query: Optional[str] = None,
    include_fields: bool = False,
    max_depth: int = 2,
) -> dict[str, Any]:
    """List classes, methods, properties, and symbols in a document.

    Args:
        file_path: Path to the target source file.
        query: Optional string to filter symbols by name.
        include_fields: If True, include struct fields and enum members (omitted by default to save tokens).
        max_depth: Maximum symbol nesting depth to expand (default: 2).
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
            node = _format_symbol_node(
                item,
                query=query,
                include_fields=include_fields,
                max_depth=max(1, max_depth),
            )
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
