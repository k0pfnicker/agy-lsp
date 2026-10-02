"""MCP refactor tool: rename_symbol with preview diff and safe write controls."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agy_lsp.config import PluginConfig
from agy_lsp.lsp.manager import LspManager
from agy_lsp.utils.formatting import compute_unified_diff
from agy_lsp.utils.paths import (
    is_safe_workspace_path,
    normalize_path,
    uri_to_path,
)


def _apply_text_edits(content: str, edits: list[dict[str, Any]]) -> str:
    """Apply a list of LSP TextEdits to a string content.

    Edits are sorted descending by line & character so earlier offsets remain valid.
    """

    def _edit_sort_key(e: dict[str, Any]):
        r = e.get("range", {})
        s = r.get("start", {})
        return (s.get("line", 0), s.get("character", 0))

    sorted_edits = sorted(edits, key=_edit_sort_key, reverse=True)
    lines = content.splitlines(keepends=True)

    # In case the file doesn't end with a newline and splitlines stripped it
    for edit in sorted_edits:
        r = edit.get("range", {})
        start = r.get("start", {})
        end = r.get("end", {})
        new_text = edit.get("newText", "")

        s_line = start.get("line", 0)
        s_char = start.get("character", 0)
        e_line = end.get("line", 0)
        e_char = end.get("character", 0)

        # Reconstruct into single buffer or line edits
        # Easiest and most accurate: char offset mapping
        # Convert (line, char) to absolute index
        char_offsets = []
        cur = 0
        for line_text in lines:
            char_offsets.append(cur)
            cur += len(line_text)
        char_offsets.append(cur)  # End of file

        start_idx = char_offsets[min(s_line, len(lines))] + s_char
        end_idx = char_offsets[min(e_line, len(lines))] + e_char

        full_text = "".join(lines)
        full_text = full_text[:start_idx] + new_text + full_text[end_idx:]
        lines = full_text.splitlines(keepends=True)

    return "".join(lines)


async def rename_symbol_tool(
    manager: LspManager,
    config: PluginConfig,
    file_path: str,
    line: int,
    character: int,
    new_name: str,
    apply: bool = False,
) -> dict[str, Any]:
    """Perform an LSP rename on a symbol, generating a preview diff before writing changes.

    Args:
        file_path: Path to the target source file.
        line: 1-indexed line number.
        character: 1-indexed column number.
        new_name: The new identifier name.
        apply: Whether to actually write the modifications to disk. Default is False (preview only).
    """
    workspace_root = config.workspaceRoot or normalize_path(".")
    norm_path = normalize_path(file_path)

    if not is_safe_workspace_path(norm_path, workspace_root, config.allowOutsideWorkspace):
        return {"error": f"Security restriction: Access to file '{file_path}' outside workspace is denied."}

    if not Path(norm_path).exists():
        return {"error": f"File not found: '{file_path}'"}

    client = await manager.get_client_for_file(norm_path)
    workspace_edit = await client.rename_symbol(norm_path, line, character, new_name)

    if not workspace_edit or not isinstance(workspace_edit, dict):
        return {"error": f"No rename edits proposed by language server for symbol at {file_path}:{line}:{character}"}

    # Extract all edits grouped by file path
    edits_by_file: dict[str, list[dict[str, Any]]] = {}

    # Handle standard 'changes': { uri: [TextEdit, ...] }
    if "changes" in workspace_edit and isinstance(workspace_edit["changes"], dict):
        for uri, edits in workspace_edit["changes"].items():
            fpath = uri_to_path(uri)
            edits_by_file[fpath] = list(edits)

    # Handle 'documentChanges': [ TextDocumentEdit, ... ]
    if "documentChanges" in workspace_edit and isinstance(workspace_edit["documentChanges"], list):
        for doc_edit in workspace_edit["documentChanges"]:
            if isinstance(doc_edit, dict) and "textDocument" in doc_edit:
                uri = doc_edit["textDocument"].get("uri", "")
                fpath = uri_to_path(uri)
                edits = doc_edit.get("edits", [])
                edits_by_file.setdefault(fpath, []).extend(edits)

    if not edits_by_file:
        return {"message": "No files require changes for this rename operation."}

    diffs: dict[str, str] = {}
    updated_contents: dict[str, str] = {}

    for fpath, edits in edits_by_file.items():
        if not is_safe_workspace_path(fpath, workspace_root, config.allowOutsideWorkspace):
            return {
                "error": f"Security violation: Rename would affect file outside workspace '{fpath}'. Operation aborted."
            }

        target_file = Path(fpath)
        if not target_file.is_file():
            continue

        original_text = target_file.read_text(encoding="utf-8", errors="replace")
        new_text = _apply_text_edits(original_text, edits)
        diff = compute_unified_diff(original_text, new_text, fpath)
        diffs[fpath] = diff
        updated_contents[fpath] = new_text

    can_write = apply and config.writeChanges
    applied = False

    if can_write:
        for fpath, new_text in updated_contents.items():
            Path(fpath).write_text(new_text, encoding="utf-8")
            client.doc_manager.invalidate(fpath)
            await client.ensure_file_synced(fpath)
        applied = True

    status_msg = (
        "Changes applied to disk successfully."
        if applied
        else "PREVIEW ONLY: Changes have NOT been written to disk. "
        "To write changes, set 'apply': true and ensure 'writeChanges': true is enabled in configuration."
    )

    return {
        "applied": applied,
        "new_name": new_name,
        "affected_files_count": len(diffs),
        "message": status_msg,
        "diffs": diffs,
    }
