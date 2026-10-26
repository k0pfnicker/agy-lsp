#!/usr/bin/env python3
"""Reproducible benchmark measuring agy-lsp latency and payload compactness.

Compares compact, structured responses returned by `agy-lsp` (`document_symbols`,
`go_to_definition`, `hover`) against the raw untruncated LSP server responses
and full-file text reads on the sample project.

Note on Token Estimates:
Token counts reported by this script use a deterministic character heuristic
(ceil(utf8_chars / 4)) and are explicitly labeled as estimates (`estimated_tokens_char_div_4`).
"""

from __future__ import annotations

import asyncio
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from agy_lsp.config import PluginConfig  # noqa: E402
from agy_lsp.lsp.adapters import find_executable, resolve_language_server  # noqa: E402
from agy_lsp.lsp.manager import LspManager  # noqa: E402
from agy_lsp.tools.hover import hover_tool  # noqa: E402
from agy_lsp.tools.navigation import go_to_definition_tool  # noqa: E402
from agy_lsp.tools.symbols import document_symbols_tool  # noqa: E402
from agy_lsp.utils.paths import normalize_path  # noqa: E402


def estimate_tokens(text: str) -> int:
    """Heuristic token estimate (~4 characters per token)."""
    return math.ceil(len(text) / 4.0)


def measure_payload(obj: Any) -> dict[str, int]:
    """Compute UTF-8 byte length, character count, and estimated token count."""
    serialized = json.dumps(obj, ensure_ascii=False) if not isinstance(obj, str) else obj
    return {
        "utf8_bytes": len(serialized.encode("utf-8")),
        "char_length": len(serialized),
        "estimated_tokens_char_div_4": estimate_tokens(serialized),
    }


async def run_benchmark() -> dict[str, Any]:
    sample_dir = ROOT_DIR / "tests" / "fixtures" / "sample_python_project"
    sample_file = sample_dir / "sample.py"

    cfg = PluginConfig(
        workspaceRoot=normalize_path(sample_dir),
        includeCodeSnippets=True,
        snippetContextLines=2,
    )

    # Prefer pylsp if available in the test environment for deterministic local execution
    pylsp_exe = find_executable("pylsp")
    if pylsp_exe:
        cfg.servers["python"].command = pylsp_exe
        cfg.servers["python"].args = []
    else:
        resolved = resolve_language_server("python", cfg)
        if not resolved.is_available:
            raise RuntimeError(f"No Python language server available for benchmark: {resolved.missing_reason}")

    manager = LspManager(cfg)

    try:
        # 1. Cold start + document_symbols
        t0 = time.perf_counter()
        compact_symbols = await document_symbols_tool(manager, cfg, str(sample_file))
        t1 = time.perf_counter()
        cold_start_symbols_ms = round((t1 - t0) * 1000.0, 2)

        # Raw LSP documentSymbol payload for comparison
        client = await manager.get_client_for_file(normalize_path(sample_file))
        raw_symbols = await client.get_document_symbols(normalize_path(sample_file))

        # 2. Warm go_to_definition (line 23, character 12 -> Calculator(a))
        t2 = time.perf_counter()
        compact_def = await go_to_definition_tool(
            manager,
            cfg,
            str(sample_file),
            line=23,
            character=12,
            include_snippet=True,
        )
        t3 = time.perf_counter()
        warm_definition_ms = round((t3 - t2) * 1000.0, 2)

        # 3. Warm hover (line 4, character 7 -> class Calculator)
        t4 = time.perf_counter()
        compact_hover = await hover_tool(
            manager,
            cfg,
            str(sample_file),
            line=4,
            character=7,
        )
        t5 = time.perf_counter()
        warm_hover_ms = round((t5 - t4) * 1000.0, 2)

        raw_file_text = sample_file.read_text(encoding="utf-8")
    finally:
        await manager.shutdown_all()

    compact_symbols_metrics = measure_payload(compact_symbols)
    raw_symbols_metrics = measure_payload(raw_symbols)
    compact_def_metrics = measure_payload(compact_def)
    compact_hover_metrics = measure_payload(compact_hover)
    full_file_metrics = measure_payload(raw_file_text)

    return {
        "target_file": "tests/fixtures/sample_python_project/sample.py",
        "metrics": {
            "cold_start_document_symbols_ms": cold_start_symbols_ms,
            "warm_go_to_definition_ms": warm_definition_ms,
            "warm_hover_ms": warm_hover_ms,
            "document_symbols_compact": compact_symbols_metrics,
            "document_symbols_raw_lsp": raw_symbols_metrics,
            "go_to_definition_compact": compact_def_metrics,
            "hover_compact": compact_hover_metrics,
            "full_file_read_baseline": full_file_metrics,
            "symbols_compact_vs_raw_lsp_ratio": round(
                compact_symbols_metrics["utf8_bytes"] / max(1, raw_symbols_metrics["utf8_bytes"]),
                4,
            ),
            "definition_vs_full_file_ratio": round(
                compact_def_metrics["utf8_bytes"] / max(1, full_file_metrics["utf8_bytes"]),
                4,
            ),
        },
        "notes": [
            "estimated_tokens_char_div_4 is a heuristic estimate (ceil(chars / 4)), not a model-specific tokenizer count.",
            "Ratios compare single-call compact MCP payloads against raw LSP JSON and full-file reads on the fixture module.",
        ],
    }


def main() -> None:
    report = asyncio.run(run_benchmark())
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
