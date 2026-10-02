"""MCP tool for checking language server status and environment health."""

from __future__ import annotations

from typing import Any

from agy_lsp.config import PluginConfig
from agy_lsp.lsp.manager import LspManager


async def lsp_status_tool(
    manager: LspManager,
    config: PluginConfig,
) -> dict[str, Any]:
    """Retrieve operational status of all configured Language Servers and workspace configuration."""
    servers_status = manager.get_status_summary()

    return {
        "workspace_root": config.workspaceRoot,
        "config": {
            "default_language": config.defaultLanguage,
            "max_results": config.maxResults,
            "include_snippets": config.includeCodeSnippets,
            "allow_outside_workspace": config.allowOutsideWorkspace,
            "write_changes": config.writeChanges,
            "request_timeout_ms": config.requestTimeoutMs,
            "max_restart_attempts": config.maxRestartAttempts,
        },
        "servers": servers_status,
    }
