"""Formatting and token optimization utilities for agy-lsp.

Ensures responses are concise, structured, and avoid wasting context tokens.
Provides snippet extraction, unified diff generation, and diagnostic deduplication.
"""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any, Optional


def truncate_message(msg: str, max_chars: int = 300) -> str:
    """Truncate long messages with a clear indicator to conserve tokens."""
    if not msg or len(msg) <= max_chars:
        return msg
    return msg[: max_chars - 20] + "... [truncated]"


def extract_code_snippet(
    file_path: str | Path,
    start_line_1idx: int,
    end_line_1idx: int,
    context_lines: int = 3,
) -> Optional[str]:
    """Read a small, targeted slice of code around start_line/end_line.

    start_line_1idx and end_line_1idx are 1-indexed.
    """
    try:
        p = Path(file_path)
        if not p.is_file():
            return None
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return None

    total_lines = len(lines)
    if total_lines == 0:
        return ""

    from_line = max(1, start_line_1idx - context_lines)
    to_line = min(total_lines, end_line_1idx + context_lines)

    snippet_lines = []
    for line_num in range(from_line, to_line + 1):
        idx = line_num - 1
        prefix = "> " if start_line_1idx <= line_num <= end_line_1idx else "  "
        snippet_lines.append(f"{prefix}{line_num:4d} | {lines[idx]}")

    return "\n".join(snippet_lines)


def compute_unified_diff(
    original_text: str,
    new_text: str,
    file_path: str,
) -> str:
    """Produce a standard unified diff between original and new file content."""
    original_lines = original_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)

    diff = difflib.unified_diff(
        original_lines,
        new_lines,
        fromfile=f"a/{file_path}",
        tofile=f"b/{file_path}",
    )
    return "".join(diff)


def format_diagnostic_item(diag: dict[str, Any], file_path: str) -> dict[str, Any]:
    """Format a single LSP diagnostic into a compact, standardized dictionary."""
    range_obj = diag.get("range", {})
    start = range_obj.get("start", {})
    end = range_obj.get("end", {})

    # LSP positions are 0-indexed, convert to 1-indexed for user/agent ergonomics
    line_start = start.get("line", 0) + 1
    col_start = start.get("character", 0) + 1
    line_end = end.get("line", start.get("line", 0)) + 1
    col_end = end.get("character", start.get("character", 0)) + 1

    severity_map = {1: "Error", 2: "Warning", 3: "Information", 4: "Hint"}
    sev_raw = diag.get("severity", 1)
    severity_str = severity_map.get(sev_raw, "Error")

    msg = diag.get("message", "").strip()
    truncated_msg = truncate_message(msg, max_chars=400)

    result: dict[str, Any] = {
        "file": file_path,
        "line": line_start,
        "column": col_start,
        "severity": severity_str,
        "message": truncated_msg,
    }

    if line_end != line_start or col_end != col_start:
        result["end_line"] = line_end
        result["end_column"] = col_end

    code = diag.get("code")
    if code is not None:
        result["code"] = str(code)

    source = diag.get("source")
    if source:
        result["source"] = str(source)

    return result


def deduplicate_diagnostics(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate diagnostics that have the exact same file, line, column, and message."""
    seen = set()
    deduped = []
    for d in items:
        key = (
            d.get("file"),
            d.get("line"),
            d.get("column"),
            d.get("severity"),
            d.get("message"),
        )
        if key not in seen:
            seen.add(key)
            deduped.append(d)
    return deduped


def limit_and_sort_results(
    items: list[dict[str, Any]],
    limit: int = 50,
    sort_key: str = "line",
) -> tuple[list[dict[str, Any]], bool, int]:
    """Sort items by file/sort_key and apply a maximum limit.

    Returns (items, was_truncated, total_count).
    """
    total = len(items)

    def _key(x: dict[str, Any]):
        return (str(x.get("file", "")), x.get(sort_key, 0))

    try:
        sorted_items = sorted(items, key=_key)
    except Exception:
        sorted_items = items

    if total > limit:
        return sorted_items[:limit], True, total
    return sorted_items, False, total
