"""MCP tools for call hierarchy and type hierarchy analysis."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agy_lsp.config import PluginConfig
from agy_lsp.lsp.manager import LspManager
from agy_lsp.lsp.protocol import format_symbol_kind
from agy_lsp.utils.paths import (
    is_safe_workspace_path,
    normalize_path,
    uri_to_path,
)


def _format_hierarchy_item(item: dict[str, Any]) -> dict[str, Any]:
    uri = item.get("uri", "")
    try:
        fpath = uri_to_path(uri) if uri else ""
    except Exception:
        fpath = uri

    range_obj = item.get("range", {})
    start = range_obj.get("start", {})
    end = range_obj.get("end", {})

    return {
        "name": item.get("name", ""),
        "kind": format_symbol_kind(item.get("kind", 0)),
        "file": fpath,
        "line": start.get("line", 0) + 1,
        "column": start.get("character", 0) + 1,
        "end_line": end.get("line", start.get("line", 0)) + 1,
        "detail": item.get("detail"),
    }


async def prepare_call_hierarchy_tool(
    manager: LspManager,
    config: PluginConfig,
    file_path: str,
    line: int,
    character: int,
) -> dict[str, Any]:
    """Prepare a call hierarchy item at the given position.

    Args:
        file_path: Path to the target source file.
        line: 1-indexed line number.
        character: 1-indexed column number.
    """
    workspace_root = config.workspaceRoot or normalize_path(".")
    norm_path = normalize_path(file_path)

    if not is_safe_workspace_path(norm_path, workspace_root, config.allowOutsideWorkspace):
        return {"error": f"Security restriction: Access to file '{file_path}' outside workspace is denied."}

    if not Path(norm_path).exists():
        return {"error": f"File not found: '{file_path}'"}

    client = await manager.get_client_for_file(norm_path)
    res = await client.prepare_call_hierarchy(norm_path, line, character)

    if not res:
        return {"items": [], "message": f"No call hierarchy item at {file_path}:{line}:{character}"}

    items = res if isinstance(res, list) else [res]
    formatted = [_format_hierarchy_item(it) for it in items if isinstance(it, dict)]

    return {"count": len(formatted), "items": formatted}


async def call_hierarchy_tool(
    manager: LspManager,
    config: PluginConfig,
    file_path: str,
    line: int,
    character: int,
    direction: str = "incoming",
) -> dict[str, Any]:
    """Inspect callers (incoming) or called functions (outgoing) from a symbol position.

    Args:
        file_path: Path to the target source file.
        line: 1-indexed line number.
        character: 1-indexed column number.
        direction: Either 'incoming' (callers) or 'outgoing' (functions called by this symbol).
    """
    workspace_root = config.workspaceRoot or normalize_path(".")
    norm_path = normalize_path(file_path)

    if not is_safe_workspace_path(norm_path, workspace_root, config.allowOutsideWorkspace):
        return {"error": f"Security restriction: Access to file '{file_path}' outside workspace is denied."}

    if not Path(norm_path).exists():
        return {"error": f"File not found: '{file_path}'"}

    client = await manager.get_client_for_file(norm_path)
    prep_res = await client.prepare_call_hierarchy(norm_path, line, character)

    if not prep_res:
        return {"calls": [], "message": "Symbol does not support call hierarchy."}

    first_item = prep_res[0] if isinstance(prep_res, list) else prep_res
    if not isinstance(first_item, dict):
        return {"calls": [], "message": "Invalid call hierarchy response."}

    dir_clean = direction.lower().strip()
    calls_list = []

    if dir_clean == "incoming":
        raw_calls = await client.call_hierarchy_incoming(first_item)
        if isinstance(raw_calls, list):
            for call in raw_calls:
                from_item = call.get("from")
                if isinstance(from_item, dict):
                    formatted_item = _format_hierarchy_item(from_item)
                    calls_list.append(formatted_item)
    elif dir_clean == "outgoing":
        raw_calls = await client.call_hierarchy_outgoing(first_item)
        if isinstance(raw_calls, list):
            for call in raw_calls:
                to_item = call.get("to")
                if isinstance(to_item, dict):
                    formatted_item = _format_hierarchy_item(to_item)
                    calls_list.append(formatted_item)
    else:
        return {"error": f"Invalid direction '{direction}'. Expected 'incoming' or 'outgoing'."}

    return {
        "direction": dir_clean,
        "target": _format_hierarchy_item(first_item),
        "count": len(calls_list),
        "calls": calls_list,
    }


async def get_type_hierarchy_tool(
    manager: LspManager,
    config: PluginConfig,
    file_path: str,
    line: int,
    character: int,
    direction: str = "supertypes",
) -> dict[str, Any]:
    """Retrieve supertypes (base classes/interfaces) or subtypes (derived types) for a type.

    Args:
        file_path: Path to the target source file.
        line: 1-indexed line number.
        character: 1-indexed column number.
        direction: Either 'supertypes' (base classes) or 'subtypes' (inheriting classes).
    """
    workspace_root = config.workspaceRoot or normalize_path(".")
    norm_path = normalize_path(file_path)

    if not is_safe_workspace_path(norm_path, workspace_root, config.allowOutsideWorkspace):
        return {"error": f"Security restriction: Access to file '{file_path}' outside workspace is denied."}

    if not Path(norm_path).exists():
        return {"error": f"File not found: '{file_path}'"}

    client = await manager.get_client_for_file(norm_path)
    prep_res = await client.prepare_type_hierarchy(norm_path, line, character)

    if not prep_res:
        return {"types": [], "message": "Type hierarchy not supported or symbol is not a type."}

    first_item = prep_res[0] if isinstance(prep_res, list) else prep_res
    if not isinstance(first_item, dict):
        return {"types": [], "message": "Invalid type hierarchy response."}

    dir_clean = direction.lower().strip()
    types_list = []

    if dir_clean == "supertypes":
        raw_types = await client.type_hierarchy_supertypes(first_item)
    elif dir_clean == "subtypes":
        raw_types = await client.type_hierarchy_subtypes(first_item)
    else:
        return {"error": f"Invalid direction '{direction}'. Expected 'supertypes' or 'subtypes'."}

    if isinstance(raw_types, list):
        for t in raw_types:
            if isinstance(t, dict):
                types_list.append(_format_hierarchy_item(t))

    return {
        "direction": dir_clean,
        "target": _format_hierarchy_item(first_item),
        "count": len(types_list),
        "types": types_list,
    }
