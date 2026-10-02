"""MCP tools for symbol navigation: go_to_definition and find_references."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from agy_lsp.config import PluginConfig
from agy_lsp.lsp.manager import LspManager
from agy_lsp.utils.formatting import extract_code_snippet, limit_and_sort_results
from agy_lsp.utils.paths import (
    is_safe_workspace_path,
    normalize_path,
    uri_to_path,
)


def _parse_location(loc: dict[str, Any]) -> tuple[str, int, int, int, int]:
    """Extract (file_path, start_line, start_col, end_line, end_col) from Location or LocationLink."""
    # LocationLink uses targetUri and targetRange / targetSelectionRange
    if "targetUri" in loc:
        uri = loc["targetUri"]
        range_obj = loc.get("targetSelectionRange") or loc.get("targetRange", {})
    else:
        uri = loc.get("uri", "")
        range_obj = loc.get("range", {})

    target_path = uri_to_path(uri)
    start = range_obj.get("start", {})
    end = range_obj.get("end", {})

    start_line = start.get("line", 0) + 1
    start_col = start.get("character", 0) + 1
    end_line = end.get("line", start.get("line", 0)) + 1
    end_col = end.get("character", start.get("character", 0)) + 1

    return target_path, start_line, start_col, end_line, end_col


async def go_to_definition_tool(
    manager: LspManager,
    config: PluginConfig,
    file_path: str,
    line: int,
    character: int,
    include_snippet: Optional[bool] = None,
) -> dict[str, Any]:
    """Jump from a symbol position to its definition.

    Args:
        file_path: Path to the source file.
        line: 1-indexed line number where the symbol is located.
        character: 1-indexed column number of the symbol.
        include_snippet: If True, include a compact code excerpt around the definition target.
    """
    workspace_root = config.workspaceRoot or normalize_path(".")
    norm_path = normalize_path(file_path)

    if not is_safe_workspace_path(norm_path, workspace_root, config.allowOutsideWorkspace):
        return {"error": f"Security restriction: Access to file '{file_path}' outside workspace is denied."}

    if not Path(norm_path).exists():
        return {"error": f"File not found: '{file_path}'"}

    client = await manager.get_client_for_file(norm_path)
    raw_res = await client.get_definition(norm_path, line, character)

    if not raw_res:
        return {
            "count": 0,
            "definitions": [],
            "message": f"No definition found for symbol at {file_path}:{line}:{character}",
        }

    # Normalize to list
    raw_locations = raw_res if isinstance(raw_res, list) else [raw_res]
    definitions = []
    want_snippet = include_snippet if include_snippet is not None else config.includeCodeSnippets

    for loc in raw_locations:
        if not isinstance(loc, dict):
            continue
        try:
            target_path, s_line, s_col, e_line, e_col = _parse_location(loc)
            is_in_ws = is_safe_workspace_path(target_path, workspace_root, allow_outside=True)

            item: dict[str, Any] = {
                "file": target_path,
                "line": s_line,
                "column": s_col,
                "end_line": e_line,
                "end_column": e_col,
                "in_workspace": is_in_ws,
            }

            if want_snippet and is_in_ws:
                snippet = extract_code_snippet(
                    target_path,
                    start_line_1idx=s_line,
                    end_line_1idx=e_line,
                    context_lines=config.snippetContextLines,
                )
                if snippet:
                    item["snippet"] = snippet

            definitions.append(item)
        except Exception:
            continue

    return {"count": len(definitions), "definitions": definitions}


async def find_references_tool(
    manager: LspManager,
    config: PluginConfig,
    file_path: str,
    line: int,
    character: int,
    include_declaration: bool = False,
    limit: Optional[int] = None,
    include_snippet: Optional[bool] = None,
) -> dict[str, Any]:
    """Find all references to a symbol across the workspace.

    Args:
        file_path: Path to the source file.
        line: 1-indexed line number of the symbol.
        character: 1-indexed column number of the symbol.
        include_declaration: Whether to include the symbol's declaration itself in the results.
        limit: Maximum number of reference items to return.
        include_snippet: Whether to include code snippets around each reference.
    """
    workspace_root = config.workspaceRoot or normalize_path(".")
    norm_path = normalize_path(file_path)

    if not is_safe_workspace_path(norm_path, workspace_root, config.allowOutsideWorkspace):
        return {"error": f"Security restriction: Access to file '{file_path}' outside workspace is denied."}

    if not Path(norm_path).exists():
        return {"error": f"File not found: '{file_path}'"}

    client = await manager.get_client_for_file(norm_path)
    raw_res = await client.get_references(norm_path, line, character, include_declaration=include_declaration)

    if not raw_res:
        return {"references": [], "count": 0, "message": "No references found."}

    references = []
    want_snippet = include_snippet if include_snippet is not None else config.includeCodeSnippets

    for loc in raw_res:
        if not isinstance(loc, dict):
            continue
        try:
            target_path, s_line, s_col, e_line, e_col = _parse_location(loc)
            is_in_ws = is_safe_workspace_path(target_path, workspace_root, allow_outside=True)

            ref_item: dict[str, Any] = {
                "file": target_path,
                "line": s_line,
                "column": s_col,
            }
            if e_line != s_line or e_col != s_col:
                ref_item["end_line"] = e_line
                ref_item["end_column"] = e_col

            if want_snippet and is_in_ws:
                snippet = extract_code_snippet(
                    target_path,
                    start_line_1idx=s_line,
                    end_line_1idx=e_line,
                    context_lines=1,
                )
                if snippet:
                    ref_item["snippet"] = snippet

            references.append(ref_item)
        except Exception:
            continue

    max_limit = limit if limit is not None else config.maxResults
    limited, truncated, total_count = limit_and_sort_results(references, limit=max_limit, sort_key="line")

    res: dict[str, Any] = {
        "count": len(limited),
        "total": total_count,
        "references": limited,
    }
    if truncated:
        res["truncated"] = True
        res["note"] = f"Results limited to {max_limit}. Total references found: {total_count}."

    return res
