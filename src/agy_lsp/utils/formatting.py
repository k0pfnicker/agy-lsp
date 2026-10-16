"""Formatting and token optimization utilities for agy-lsp.

Ensures responses are concise, structured, and avoid wasting context tokens.
Provides snippet extraction, unified diff generation, diagnostic deduplication,
and smart identifier column snapping for LLM line/character queries.
"""

from __future__ import annotations

import difflib
import re
from pathlib import Path
from typing import Any, Optional

_COMMON_NON_SYMBOL_KEYWORDS = {
    "static",
    "const",
    "volatile",
    "inline",
    "extern",
    "unsigned",
    "signed",
    "void",
    "int",
    "char",
    "short",
    "long",
    "float",
    "double",
    "bool",
    "uint8_t",
    "uint16_t",
    "uint32_t",
    "uint64_t",
    "int8_t",
    "int16_t",
    "int32_t",
    "int64_t",
    "size_t",
    "struct",
    "enum",
    "union",
    "typedef",
    "return",
    "if",
    "else",
    "for",
    "while",
    "switch",
    "case",
    "def",
    "async",
    "class",
    "public",
    "private",
    "protected",
    "internal",
    "export",
    "function",
    "let",
    "var",
}

_IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def resolve_symbol_position(
    file_path: str | Path,
    line_1idx: int,
    character_1idx: int,
    symbol_name: Optional[str] = None,
) -> tuple[int, int]:
    """Resolve or snap (line_1idx, character_1idx) to a valid identifier on or near the line.

    1. If symbol_name is provided, searches line_1idx (and +/- 2 lines if needed) for symbol_name.
    2. If character_1idx lands on whitespace or punctuation, snaps to the nearest non-keyword identifier on line_1idx.
    """
    try:
        p = Path(file_path)
        if not p.is_file():
            return line_1idx, character_1idx
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return line_1idx, character_1idx

    if not lines or line_1idx < 1 or line_1idx > len(lines):
        return line_1idx, character_1idx

    if symbol_name:
        # Check target line first, then +/- 2 surrounding lines
        search_Offsets = [0, -1, 1, -2, 2]
        pat = re.compile(r"\b" + re.escape(symbol_name) + r"\b")
        for offset in search_Offsets:
            cand_line = line_1idx + offset
            if 1 <= cand_line <= len(lines):
                m = pat.search(lines[cand_line - 1])
                if m:
                    return cand_line, m.start() + 1

    line_text = lines[line_1idx - 1]
    if not line_text:
        return line_1idx, character_1idx

    col0 = max(0, character_1idx - 1)
    # Check if col0 is already inside a non-keyword identifier
    for m in _IDENTIFIER_RE.finditer(line_text):
        if m.start() <= col0 <= m.end():
            word = m.group(0)
            if word not in _COMMON_NON_SYMBOL_KEYWORDS:
                return line_1idx, character_1idx

    # Otherwise, collect candidate identifiers on this line (preferring non-keywords)
    matches = list(_IDENTIFIER_RE.finditer(line_text))
    non_kw = [m for m in matches if m.group(0) not in _COMMON_NON_SYMBOL_KEYWORDS]
    candidates = non_kw if non_kw else matches
    if not candidates:
        return line_1idx, character_1idx

    # Pick candidate closest to requested col0 (or first non-keyword if col0 was at start of line)
    best = min(candidates, key=lambda m: min(abs(m.start() - col0), abs(m.end() - col0)))
    return line_1idx, best.start() + 1


def find_alternative_columns_on_line(
    file_path: str | Path,
    line_1idx: int,
    tried_character_1idx: int,
) -> list[int]:
    """Return 1-indexed start columns of other identifiers on line_1idx for fallback retry."""
    try:
        p = Path(file_path)
        if not p.is_file():
            return []
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return []

    if not lines or line_1idx < 1 or line_1idx > len(lines):
        return []

    line_text = lines[line_1idx - 1]
    cols: list[int] = []
    for m in _IDENTIFIER_RE.finditer(line_text):
        word = m.group(0)
        col1 = m.start() + 1
        if word not in _COMMON_NON_SYMBOL_KEYWORDS and col1 != tried_character_1idx:
            cols.append(col1)
    return cols


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
