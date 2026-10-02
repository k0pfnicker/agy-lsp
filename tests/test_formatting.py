"""Tests for token-efficient formatting, snippet extraction, and unified diffs."""

from pathlib import Path

from agy_lsp.utils.formatting import (
    compute_unified_diff,
    deduplicate_diagnostics,
    extract_code_snippet,
    format_diagnostic_item,
    limit_and_sort_results,
    truncate_message,
)


def test_truncate_message():
    short_msg = "A short message."
    assert truncate_message(short_msg, max_chars=50) == short_msg

    long_msg = "X" * 100
    res = truncate_message(long_msg, max_chars=40)
    assert len(res) <= 40
    assert res.endswith("... [truncated]")


def test_extract_code_snippet(tmp_path: Path):
    f = tmp_path / "test.py"
    f.write_text("line 1\nline 2\nline 3\nline 4\nline 5\nline 6\nline 7\n", encoding="utf-8")

    snippet = extract_code_snippet(f, start_line_1idx=4, end_line_1idx=4, context_lines=1)
    assert snippet is not None
    assert "line 3" in snippet
    assert ">    4 | line 4" in snippet
    assert "line 5" in snippet
    assert "line 1" not in snippet  # Beyond context window


def test_compute_unified_diff():
    orig = "def foo():\n    return 1\n"
    new = "def bar():\n    return 1\n"
    diff = compute_unified_diff(orig, new, "test.py")
    assert "-def foo():" in diff
    assert "+def bar():" in diff


def test_format_diagnostic_item():
    raw_diag = {
        "range": {
            "start": {"line": 9, "character": 4},
            "end": {"line": 9, "character": 12},
        },
        "severity": 1,
        "message": "Undefined variable 'x'",
        "code": "E001",
        "source": "pyright",
    }
    formatted = format_diagnostic_item(raw_diag, "main.py")
    assert formatted["file"] == "main.py"
    assert formatted["line"] == 10  # 1-indexed
    assert formatted["column"] == 5
    assert formatted["severity"] == "Error"
    assert formatted["code"] == "E001"
    assert formatted["source"] == "pyright"


def test_deduplicate_diagnostics():
    item1 = {"file": "a.py", "line": 5, "column": 1, "severity": "Error", "message": "msg"}
    item2 = {"file": "a.py", "line": 5, "column": 1, "severity": "Error", "message": "msg"}
    item3 = {"file": "a.py", "line": 6, "column": 1, "severity": "Error", "message": "msg"}

    deduped = deduplicate_diagnostics([item1, item2, item3])
    assert len(deduped) == 2


def test_limit_and_sort_results():
    items = [{"file": f"file_{i}.py", "line": i} for i in range(100, 0, -1)]
    limited, truncated, total = limit_and_sort_results(items, limit=20, sort_key="line")

    assert len(limited) == 20
    assert truncated is True
    assert total == 100
    assert limited[0]["line"] == 1
