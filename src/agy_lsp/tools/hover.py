"""MCP hover tool: inspect type signatures and documentation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agy_lsp.config import PluginConfig
from agy_lsp.lsp.manager import LspManager
from agy_lsp.utils.paths import (
    is_safe_workspace_path,
    normalize_path,
)


def _extract_hover_text(contents: Any) -> str:
    """Extract clean string content from LSP Hover contents union."""
    if not contents:
        return ""

    if isinstance(contents, str):
        return contents.strip()

    if isinstance(contents, dict):
        # MarkupContent: {"kind": "markdown", "value": "..."}
        if "value" in contents:
            return str(contents["value"]).strip()
        # MarkedString: {"language": "python", "value": "..."}
        val = contents.get("value", "")
        lang = contents.get("language", "")
        if lang:
            return f"```{lang}\n{val}\n```"
        return str(val).strip()

    if isinstance(contents, list):
        parts = []
        for item in contents:
            t = _extract_hover_text(item)
            if t:
                parts.append(t)
        return "\n\n".join(parts)

    return str(contents).strip()


async def hover_tool(
    manager: LspManager,
    config: PluginConfig,
    file_path: str,
    line: int,
    character: int,
) -> dict[str, Any]:
    """Retrieve type information, function signatures, and docstrings at a specific position.

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
    res = await client.get_hover(norm_path, line, character)

    if not res or not isinstance(res, dict):
        return {
            "hover": "",
            "message": f"No hover information available at {file_path}:{line}:{character}",
        }

    contents = res.get("contents")
    text = _extract_hover_text(contents)

    return {
        "file": norm_path,
        "line": line,
        "column": character,
        "hover": text,
    }
