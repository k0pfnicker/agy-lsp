"""MCP tool implementation for get_diagnostics."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from agy_lsp.config import PluginConfig
from agy_lsp.lsp.manager import LspManager
from agy_lsp.utils.formatting import (
    deduplicate_diagnostics,
    format_diagnostic_item,
    limit_and_sort_results,
)
from agy_lsp.utils.paths import (
    is_safe_workspace_path,
    normalize_path,
    uri_to_path,
)


async def get_diagnostics_tool(
    manager: LspManager,
    config: PluginConfig,
    file_path: Optional[str] = None,
    line_start: Optional[int] = None,
    line_end: Optional[int] = None,
    severity: Optional[str] = None,
    limit: Optional[int] = None,
) -> dict[str, Any]:
    """Retrieve diagnostics (errors, warnings, hints) for a file or the entire workspace.

    Args:
        file_path: Optional path to a specific file. If omitted, returns diagnostics across the workspace.
        line_start: Optional starting line number (1-indexed) to filter.
        line_end: Optional ending line number (1-indexed) to filter.
        severity: Optional severity filter ("Error", "Warning", "Information", "Hint").
        limit: Maximum number of diagnostics to return (defaults to configured maxResults).
    """
    workspace_root = config.workspaceRoot or normalize_path(".")

    if file_path:
        norm_path = normalize_path(file_path)
        if not is_safe_workspace_path(norm_path, workspace_root, config.allowOutsideWorkspace):
            return {
                "error": f"Security restriction: Access to file '{file_path}' outside workspace is denied.",
                "diagnostics": [],
            }

        if not Path(norm_path).exists():
            return {
                "error": f"File not found: '{file_path}'",
                "diagnostics": [],
            }

        client = await manager.get_client_for_file(norm_path)
        raw_items = await client.get_diagnostics(norm_path)
        formatted = [format_diagnostic_item(item, norm_path) for item in raw_items]
    else:
        # Collect from all active clients
        active_clients = await manager.get_all_active_clients()
        formatted = []
        for client in active_clients:
            for uri, diags in client.diagnostics_cache.items():
                try:
                    fpath = uri_to_path(uri)
                    for item in diags:
                        formatted.append(format_diagnostic_item(item, fpath))
                except Exception:
                    pass

    # Deduplicate
    deduped = deduplicate_diagnostics(formatted)

    # Filter by severity
    if severity:
        sev_clean = severity.strip().capitalize()
        deduped = [d for d in deduped if d.get("severity") == sev_clean]

    # Filter by line range
    if line_start is not None:
        deduped = [d for d in deduped if d.get("line", 0) >= line_start]
    if line_end is not None:
        deduped = [d for d in deduped if d.get("line", 0) <= line_end]

    max_limit = limit if limit is not None else config.maxResults
    limited, truncated, total_count = limit_and_sort_results(deduped, limit=max_limit, sort_key="line")

    res: dict[str, Any] = {
        "count": len(limited),
        "total": total_count,
        "diagnostics": limited,
    }
    if truncated:
        res["truncated"] = True
        res["note"] = f"Results truncated to {max_limit}. Total matching diagnostics: {total_count}."

    return res
