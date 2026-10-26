"""Empirical benchmarks and value-verification tests for agy-lsp.

This module quantifies why agy-lsp is valuable for AI coding agents across 6 dimensions:
1. Token & Context Compression (document_symbols field collapsing vs. raw LSP & full file reads)
2. LLM Column Estimation Resilience (Smart Column Auto-Snapping vs. raw LSP coordinates)
3. Semantic Precision vs. Text Grep (go_to_definition & find_references ignoring comments/strings)
4. Real-Time Compiler Feedback Loop (event-driven get_diagnostics with clangd & pylsp + deduplication)
5. Safe Semantic Refactoring (rename_symbol unified diff preview leaving strings/comments intact)
6. Zero-Read Call Graph Analysis (call_hierarchy incoming & outgoing calls via clangd AST)
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import pytest

from agy_lsp.config import PluginConfig
from agy_lsp.lsp.adapters import find_executable
from agy_lsp.lsp.manager import LspManager
from agy_lsp.tools import (
    call_hierarchy_tool,
    document_symbols_tool,
    find_references_tool,
    get_diagnostics_tool,
    go_to_definition_tool,
    rename_symbol_tool,
)
from agy_lsp.utils.formatting import (
    deduplicate_diagnostics,
    format_diagnostic_item,
    limit_and_sort_results,
)
from agy_lsp.utils.paths import normalize_path


def _estimate_tokens(text: str) -> int:
    """Standard ~4 chars per token heuristic used for LLM context estimation."""
    return max(1, round(len(text) / 4))


@pytest.mark.asyncio
async def test_benchmark_1_token_compression_document_symbols(sample_cpp_dir: Path, sample_cpp_header: Path):
    """Benchmark 1: Measure payload & token savings of document_symbols vs. raw LSP and full file."""
    clangd_exe = find_executable("clangd")
    if not clangd_exe:
        pytest.skip("clangd not installed")

    cfg = PluginConfig()
    cfg.workspaceRoot = normalize_path(sample_cpp_dir)
    manager = LspManager(cfg)

    try:
        client = await manager.get_client_for_file(str(sample_cpp_header))

        # 1. Raw LSP documentSymbol payload
        raw_lsp_symbols = await client.get_document_symbols(str(sample_cpp_header))
        raw_lsp_json = json.dumps(raw_lsp_symbols)

        # 2. Full expanded document_symbols (include_fields=True)
        expanded_res = await document_symbols_tool(manager, cfg, str(sample_cpp_header), include_fields=True)
        expanded_json = json.dumps(expanded_res)

        # 3. Default agy-lsp token-compact document_symbols (include_fields=False)
        compact_res = await document_symbols_tool(manager, cfg, str(sample_cpp_header), include_fields=False)
        compact_json = json.dumps(compact_res)

        reduction_vs_raw = (1.0 - (len(compact_json) / len(raw_lsp_json))) * 100.0
        reduction_vs_expanded = (1.0 - (len(compact_json) / len(expanded_json))) * 100.0

        print(
            f"\n[Benchmark 1 - Document Symbols Token Reduction]\n"
            f"  Raw LSP JSON:        {len(raw_lsp_json):5d} bytes (~{_estimate_tokens(raw_lsp_json):4d} tokens)\n"
            f"  Expanded (fields):   {len(expanded_json):5d} bytes (~{_estimate_tokens(expanded_json):4d} tokens)\n"
            f"  agy-lsp Compact:     {len(compact_json):5d} bytes (~{_estimate_tokens(compact_json):4d} tokens)\n"
            f"  Reduction vs Raw:    {reduction_vs_raw:.1f}%\n"
            f"  Reduction vs Full:   {reduction_vs_expanded:.1f}%"
        )

        # Verify all top-level types and functions are preserved
        names = {s["name"] for s in compact_res["symbols"]}
        assert {
            "Opcode",
            "VmContext",
            "PacketFrame",
            "vm_init",
            "execute_step",
            "run_program",
            "compute_checksum",
        }.issubset(names)

        # Find the Struct/Enum symbols (distinct from their C typedefs)
        with_fields = {s["name"]: s["fields_count"] for s in compact_res["symbols"] if "fields_count" in s}
        assert with_fields["Opcode"] == 21
        assert with_fields["VmContext"] == 34
        assert with_fields["PacketFrame"] == 10

        assert reduction_vs_raw >= 85.0
        assert reduction_vs_expanded >= 75.0
    finally:
        await manager.shutdown_all()


@pytest.mark.asyncio
async def test_benchmark_2_smart_column_auto_snapping_vs_raw_lsp(
    sample_cpp_dir: Path, sample_cpp_header: Path, sample_cpp_source: Path
):
    """Benchmark 2: Compare raw LSP definition lookup vs. agy-lsp smart column auto-snapping on inaccurate LLM columns."""
    clangd_exe = find_executable("clangd")
    if not clangd_exe:
        pytest.skip("clangd not installed")

    cfg = PluginConfig()
    cfg.workspaceRoot = normalize_path(sample_cpp_dir)
    manager = LspManager(cfg)

    try:
        await document_symbols_tool(manager, cfg, str(sample_cpp_header))
        client = await manager.get_client_for_file(str(sample_cpp_source))
        uri = await client.ensure_file_synced(str(sample_cpp_source))

        # Realistic imprecise LLM call-site / type-reference queries on engine.c:
        # Line 47: "            ctx->r0 = clamp_register(operand, 0xFFFFFFFFULL);" -> clamp_register at engine.c:9
        # Line 50: "            ctx->r0 = clamp_register(ctx->r0 + operand, 0xFFFFFFFFULL);" -> clamp_register at engine.c:9
        # Line 71: "    vm_init(ctx, 4096);" -> vm_init at engine.c:16
        # Line 73: "        int rc = execute_step(ctx, code[i], (uint64_t)i * 10);" -> execute_step at engine.c:32
        # Line 81: "uint32_t compute_checksum(const PacketFrame *frame) {" -> PacketFrame at engine.h:86
        imprecise_queries = [
            # (description, line_1idx, char_1idx, symbol_name, expected_def_line)
            ("Indented whitespace (col 1) on vm_init call (line 71)", 71, 1, None, 16),
            ("Indented whitespace (col 3) before vm_init call (line 71)", 71, 3, None, 16),
            ("Past end of line (col 60) on vm_init call (line 71)", 71, 60, "vm_init", 16),
            ("Indented whitespace (col 1) on execute_step call (line 73)", 73, 1, "execute_step", 32),
            ("On 'int' keyword (col 9) on execute_step call (line 73)", 73, 9, "execute_step", 32),
            ("Off-by-1 line above (line 72) with symbol_name='execute_step'", 72, 1, "execute_step", 32),
            ("Off-by-1 line below (line 74) with symbol_name='execute_step'", 74, 1, "execute_step", 32),
            ("Indented whitespace (col 1) on clamp_register call (line 47)", 47, 1, "clamp_register", 9),
            ("Past end of line (col 95) on clamp_register call (line 50)", 50, 95, "clamp_register", 9),
            ("On 'const' keyword (col 27) for PacketFrame type (line 81)", 81, 27, "PacketFrame", 86),
        ]

        raw_lsp_hits = 0
        agy_lsp_hits = 0

        for _desc, line, col, sym_name, expected_def_line in imprecise_queries:
            # 1. Raw LSP textDocument/definition at exact (line-1, col-1) without snapping
            raw_def = await client.send_request(
                "textDocument/definition",
                {
                    "textDocument": {"uri": uri},
                    "position": {"line": line - 1, "character": max(0, col - 1)},
                },
            )
            if isinstance(raw_def, list) and len(raw_def) > 0:
                r_line = raw_def[0].get("range", {}).get("start", {}).get("line", -1) + 1
                if r_line == expected_def_line:
                    raw_lsp_hits += 1

            # 2. agy-lsp go_to_definition_tool with smart snapping & fallback
            agy_def = await go_to_definition_tool(
                manager, cfg, str(sample_cpp_source), line=line, character=col, symbol_name=sym_name
            )
            if agy_def.get("count", 0) > 0:
                if agy_def["definitions"][0]["line"] == expected_def_line:
                    agy_lsp_hits += 1

        total = len(imprecise_queries)
        print(
            f"\n[Benchmark 2 - Inaccurate LLM Column Resilience (go_to_definition)]\n"
            f"  Raw LSP Hit Rate:  {raw_lsp_hits}/{total} ({raw_lsp_hits / total * 100:.0f}%)\n"
            f"  agy-lsp Hit Rate:  {agy_lsp_hits}/{total} ({agy_lsp_hits / total * 100:.0f}%)"
        )

        assert raw_lsp_hits == 0  # Raw LSP fails on all 10 imprecise positions
        assert agy_lsp_hits == total  # agy-lsp resolves 10/10 (100%)
    finally:
        await manager.shutdown_all()


@pytest.mark.asyncio
async def test_benchmark_3_semantic_navigation_vs_grep(
    sample_cpp_dir: Path, sample_cpp_header: Path, sample_cpp_source: Path
):
    """Benchmark 3: Compare plaintext grep vs. semantic go_to_definition & find_references."""
    clangd_exe = find_executable("clangd")
    if not clangd_exe:
        pytest.skip("clangd not installed")

    cfg = PluginConfig()
    cfg.workspaceRoot = normalize_path(sample_cpp_dir)
    cfg.includeCodeSnippets = True
    manager = LspManager(cfg)

    try:
        # Ensure both header and source are opened in clangd
        await document_symbols_tool(manager, cfg, str(sample_cpp_header))
        await document_symbols_tool(manager, cfg, str(sample_cpp_source))

        # 1. Simulate plaintext grep for "execute_step" across workspace files
        grep_matches = []
        full_files_bytes = 0
        for f in (sample_cpp_header, sample_cpp_source):
            text = f.read_text(encoding="utf-8")
            full_files_bytes += len(text)
            for idx, line_text in enumerate(text.splitlines(), start=1):
                if re.search(r"\bexecute_step\b", line_text):
                    grep_matches.append((f.name, idx, line_text.strip()))

        # Out of 8 grep matches, 5 are comments/strings (62.5% false positives!)
        false_positives = [m for m in grep_matches if m[2].startswith("*") or '"execute_step' in m[2]]

        # 2. agy-lsp go_to_definition from call site in engine.c:72
        def_res = await go_to_definition_tool(
            manager,
            cfg,
            str(sample_cpp_source),
            line=72,
            character=18,
            include_snippet=True,
            symbol_name="execute_step",
        )
        def_json = json.dumps(def_res)

        # 3. agy-lsp find_references on execute_step (including declaration)
        ref_res = await find_references_tool(
            manager,
            cfg,
            str(sample_cpp_source),
            line=32,
            character=5,
            include_declaration=True,
            symbol_name="execute_step",
        )

        ref_lines = {(Path(r["file"]).name, r["line"]) for r in ref_res["references"]}
        fp_rate = len(false_positives) / len(grep_matches) * 100.0
        context_savings_pct = (1.0 - len(def_json) / full_files_bytes) * 100.0

        print(
            f"\n[Benchmark 3 - Semantic Navigation vs. Grep]\n"
            f"  Grep matches for 'execute_step': {len(grep_matches)} total ({len(false_positives)} false positives = {fp_rate:.1f}% noise)\n"
            f"  LSP References (AST-verified):   {ref_res['count']} total (0 false positives): {sorted(ref_lines)}\n"
            f"  Full files context size:         {full_files_bytes} bytes (~{_estimate_tokens('x' * full_files_bytes)} tokens)\n"
            f"  go_to_definition snippet size:   {len(def_json)} bytes (~{_estimate_tokens(def_json)} tokens, -{context_savings_pct:.1f}%)"
        )

        assert len(grep_matches) == 8
        assert len(false_positives) == 5
        assert ref_res["count"] == 3  # Only prototype (engine.h:89), def (engine.c:32), call (engine.c:72)
        assert ("engine.c", 33) not in ref_lines  # String literal ignored!
        assert ("engine.c", 5) not in ref_lines  # Comment ignored!
        assert ("engine.c", 6) not in ref_lines  # Comment ignored!
        assert ("engine.h", 5) not in ref_lines  # Comment ignored!
        assert ("engine.h", 6) not in ref_lines  # Comment ignored!
        assert def_res["count"] == 1
        assert def_res["definitions"][0]["line"] == 32
    finally:
        await manager.shutdown_all()


@pytest.mark.asyncio
async def test_benchmark_4_realtime_diagnostics_and_noise_reduction(tmp_path: Path):
    """Benchmark 4: Measure real-time C/C++ compiler diagnostics and deduplication/truncation."""
    clangd_exe = find_executable("clangd")
    if not clangd_exe:
        pytest.skip("clangd not installed")

    buggy_c = tmp_path / "buggy.c"
    buggy_c.write_text(
        "int add_numbers(int a, int b) {\n"
        "    return a + b;\n"
        "}\n\n"
        "int broken_caller(void) {\n"
        "    int x = undeclared_var + 1;\n"
        '    int y = add_numbers("wrong_type", 2, 3);\n'
        "    return x + y;\n"
        "}\n",
        encoding="utf-8",
    )

    cfg = PluginConfig()
    cfg.workspaceRoot = normalize_path(tmp_path)
    manager = LspManager(cfg)

    try:
        t0 = time.perf_counter()
        diag_res = await get_diagnostics_tool(manager, cfg, str(buggy_c))
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        print(
            f"\n[Benchmark 4 - Real-Time clangd Diagnostics]\n"
            f"  Diagnostics detected: {diag_res['count']} errors in {elapsed_ms:.0f} ms\n"
            f"  Messages: {[d['message'] for d in diag_res['diagnostics']]}"
        )

        assert diag_res["count"] >= 2
        lines_with_errors = {d["line"] for d in diag_res["diagnostics"]}
        assert 6 in lines_with_errors  # undeclared_var
        assert 7 in lines_with_errors  # too many arguments / wrong type

        # Also benchmark diagnostic noise reduction (deduplication + 400-char truncation + limit)
        noisy_raw_diags = []
        long_template_err = (
            "error: no matching function for call to 'std::vector<std::basic_string<char>>::push_back' "
            + ("with template candidate details " * 30)
        )
        for i in range(120):
            # 60 duplicates at line 10, plus 60 distinct lines
            line_no = 10 if i < 60 else (i - 40)
            noisy_raw_diags.append(
                {
                    "range": {"start": {"line": line_no, "character": 4}, "end": {"line": line_no, "character": 12}},
                    "severity": 1,
                    "message": long_template_err,
                    "code": "template_err",
                    "source": "clangd",
                }
            )

        raw_noisy_json = json.dumps(noisy_raw_diags)
        formatted = [format_diagnostic_item(d, "noisy.cpp") for d in noisy_raw_diags]
        deduped = deduplicate_diagnostics(formatted)
        limited, truncated, total = limit_and_sort_results(deduped, limit=50, sort_key="line")
        compact_noisy_json = json.dumps(
            {"count": len(limited), "total": total, "truncated": truncated, "diagnostics": limited}
        )

        noise_reduction_pct = (1.0 - len(compact_noisy_json) / len(raw_noisy_json)) * 100.0
        print(
            f"  Noisy Cascade Raw JSON:     {len(raw_noisy_json):6d} bytes (~{_estimate_tokens(raw_noisy_json):5d} tokens)\n"
            f"  agy-lsp Deduplicated/Capped:{len(compact_noisy_json):6d} bytes (~{_estimate_tokens(compact_noisy_json):5d} tokens)\n"
            f"  Cascade Token Reduction:    {noise_reduction_pct:.1f}%"
        )
        assert noise_reduction_pct >= 75.0
    finally:
        await manager.shutdown_all()


@pytest.mark.asyncio
async def test_benchmark_5_safe_semantic_rename_and_call_hierarchy(
    sample_cpp_dir: Path, sample_cpp_header: Path, sample_cpp_source: Path
):
    """Benchmark 5 & 6: Verify AST-safe rename preview diff and call hierarchy in C via clangd."""
    clangd_exe = find_executable("clangd")
    if not clangd_exe:
        pytest.skip("clangd not installed")

    cfg = PluginConfig()
    cfg.workspaceRoot = normalize_path(sample_cpp_dir)
    manager = LspManager(cfg)

    try:
        # Sync both files so clangd indexes the translation unit
        await document_symbols_tool(manager, cfg, str(sample_cpp_header))
        await document_symbols_tool(manager, cfg, str(sample_cpp_source))

        # 1. Rename execute_step -> dispatch_op (preview mode apply=False)
        rename_res = await rename_symbol_tool(
            manager,
            cfg,
            str(sample_cpp_source),
            line=32,
            character=5,
            new_name="dispatch_op",
            apply=False,
            symbol_name="execute_step",
        )

        assert rename_res["applied"] is False
        assert rename_res["affected_files_count"] == 2  # Both engine.h and engine.c!
        c_diff = rename_res["diffs"][normalize_path(sample_cpp_source)]
        h_diff = rename_res["diffs"][normalize_path(sample_cpp_header)]
        assert "-int execute_step(" in h_diff
        assert "+int dispatch_op(" in h_diff
        assert "-int execute_step(" in c_diff
        assert "+int dispatch_op(" in c_diff
        assert "-        int rc = execute_step(" in c_diff
        assert "+        int rc = dispatch_op(" in c_diff
        # Verify string literal "execute_step" on line 33 was NOT renamed!
        assert '"dispatch_op"' not in c_diff

        # 2. Call Hierarchy: outgoing calls from execute_step (calls clamp_register)
        outgoing_res = await call_hierarchy_tool(
            manager,
            cfg,
            str(sample_cpp_source),
            line=32,
            character=5,
            direction="outgoing",
            symbol_name="execute_step",
        )
        outgoing_names = [c["name"] for c in outgoing_res.get("calls", [])]

        # 3. Call Hierarchy: incoming calls to execute_step (called by run_program)
        incoming_res = await call_hierarchy_tool(
            manager,
            cfg,
            str(sample_cpp_source),
            line=32,
            character=5,
            direction="incoming",
            symbol_name="execute_step",
        )
        incoming_names = [c["name"] for c in incoming_res.get("calls", [])]

        print(
            f"\n[Benchmark 5 & 6 - Rename Safety & Call Hierarchy]\n"
            f"  Rename affected files: {rename_res['affected_files_count']} (engine.h + engine.c; string literals & comments preserved!)\n"
            f"  Incoming callers of execute_step: {incoming_names}\n"
            f"  Outgoing callees of execute_step: {outgoing_names}"
        )

        assert "clamp_register" in outgoing_names
        assert "run_program" in incoming_names
    finally:
        await manager.shutdown_all()
