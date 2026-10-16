"""End-to-End tests against real Language Server processes (pylsp for Python and clangd for C/C++)."""

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
    hover_tool,
    lsp_status_tool,
    rename_symbol_tool,
)
from agy_lsp.utils.paths import normalize_path


@pytest.mark.asyncio
async def test_real_python_lsp_server_end_to_end(sample_python_dir: Path, sample_python_file: Path):
    """Start real python-lsp-server, perform document outline, definition, references, hover, rename preview, and shutdown."""
    pylsp_exe = find_executable("pylsp")
    if not pylsp_exe:
        pytest.skip("pylsp is not installed or available for real E2E testing.")

    cfg = PluginConfig()
    cfg.workspaceRoot = normalize_path(sample_python_dir)
    cfg.servers["python"].command = pylsp_exe
    cfg.servers["python"].args = []
    cfg.includeCodeSnippets = True

    manager = LspManager(cfg)

    try:
        # 1. Start client & retrieve document symbols
        sym_res = await document_symbols_tool(manager, cfg, str(sample_python_file))
        assert "symbols" in sym_res
        assert sym_res["count"] > 0
        names = [s["name"] for s in sym_res["symbols"]]
        assert "Calculator" in names or "compute_total" in names

        # 2. Hover inspection over Calculator class definition (with column snapping from col 1)
        hover_res = await hover_tool(manager, cfg, str(sample_python_file), line=4, character=1)
        assert "hover" in hover_res
        assert len(hover_res["hover"]) > 0

        # 3. Go to definition (with column snapping from col 1 using symbol_name)
        def_res = await go_to_definition_tool(
            manager,
            cfg,
            str(sample_python_file),
            line=23,
            character=1,
            include_snippet=True,
            symbol_name="Calculator",
        )
        assert "definitions" in def_res
        if def_res["count"] > 0:
            target = def_res["definitions"][0]
            assert "sample.py" in target["file"].lower()
            assert target["line"] in (4, 7)
            if "snippet" in target:
                assert "Calculator" in target["snippet"]

        # 4. Find references across sample.py
        ref_res = await find_references_tool(
            manager,
            cfg,
            str(sample_python_file),
            line=21,
            character=1,
            include_declaration=True,
            symbol_name="compute_total",
        )
        assert ref_res.get("count", 0) >= 2

        # 5. Safe rename preview (apply=False)
        rename_res = await rename_symbol_tool(
            manager,
            cfg,
            str(sample_python_file),
            line=21,
            character=5,
            new_name="calculate_sum",
            apply=False,
            symbol_name="compute_total",
        )
        assert rename_res.get("applied") is False
        assert "diffs" in rename_res

        # 6. Check diagnostics & status
        diag_res = await get_diagnostics_tool(manager, cfg, str(sample_python_file))
        assert "diagnostics" in diag_res

        status_res = await lsp_status_tool(manager, cfg)
        py_srv = next(s for s in status_res["servers"] if s["language"] == "python")
        assert py_srv["status"] == "RUNNING"

    finally:
        # 7. Clean shutdown
        await manager.shutdown_all()
        clients = await manager.get_all_active_clients()
        assert len(clients) == 0


@pytest.mark.asyncio
async def test_real_clangd_lsp_server_end_to_end(
    sample_cpp_dir: Path, sample_cpp_header: Path, sample_cpp_source: Path
):
    """Start real clangd server, perform C/C++ symbols, definition, references, hover, call hierarchy, and shutdown."""
    clangd_exe = find_executable("clangd")
    if not clangd_exe:
        pytest.skip("clangd is not installed or available for real E2E testing.")

    cfg = PluginConfig()
    cfg.workspaceRoot = normalize_path(sample_cpp_dir)
    cfg.includeCodeSnippets = True

    manager = LspManager(cfg)

    try:
        # 1. Document symbols with default field collapsing
        sym_res = await document_symbols_tool(manager, cfg, str(sample_cpp_header))
        assert sym_res["count"] >= 7

        # 2. Sync source file and test hover with column auto-snapping
        hover_res = await hover_tool(
            manager, cfg, str(sample_cpp_source), line=32, character=1, symbol_name="execute_step"
        )
        assert "execute_step" in hover_res.get("hover", "")

        # 3. Cross-file go_to_definition (from engine.h prototype to engine.c implementation or vice versa)
        def_res = await go_to_definition_tool(
            manager,
            cfg,
            str(sample_cpp_source),
            line=73,
            character=1,
            include_snippet=True,
            symbol_name="execute_step",
        )
        assert def_res["count"] == 1
        assert def_res["definitions"][0]["line"] == 32
        assert "execute_step" in def_res["definitions"][0].get("snippet", "")

        # 4. Call hierarchy
        ch_res = await call_hierarchy_tool(
            manager,
            cfg,
            str(sample_cpp_source),
            line=32,
            character=1,
            direction="incoming",
            symbol_name="execute_step",
        )
        assert ch_res["count"] >= 1
        assert ch_res["calls"][0]["name"] == "run_program"

    finally:
        await manager.shutdown_all()
        clients = await manager.get_all_active_clients()
        assert len(clients) == 0
