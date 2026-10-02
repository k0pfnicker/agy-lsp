"""End-to-End tests against real Language Server process (python-lsp-server / pylsp)."""

from pathlib import Path

import pytest

from agy_lsp.config import PluginConfig
from agy_lsp.lsp.adapters import find_executable
from agy_lsp.lsp.manager import LspManager
from agy_lsp.tools.diagnostics import get_diagnostics_tool
from agy_lsp.tools.hover import hover_tool
from agy_lsp.tools.navigation import go_to_definition_tool
from agy_lsp.tools.symbols import document_symbols_tool
from agy_lsp.utils.paths import normalize_path


@pytest.mark.asyncio
async def test_real_lsp_server_end_to_end(sample_python_dir: Path, sample_python_file: Path):
    """Start real python-lsp-server, perform document outline, definition, hover, and shutdown."""
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

        # 2. Hover inspection over Calculator class definition
        # In sample.py: line 4, col 7: "class Calculator:"
        hover_res = await hover_tool(manager, cfg, str(sample_python_file), line=4, character=7)
        assert "hover" in hover_res
        # pylsp docstring or signature
        assert len(hover_res["hover"]) > 0

        # 3. Go to definition
        # In sample.py: line 22, col 15: "calc = Calculator(a)"
        def_res = await go_to_definition_tool(
            manager, cfg, str(sample_python_file), line=22, character=15, include_snippet=True
        )
        assert "definitions" in def_res
        if def_res["count"] > 0:
            target = def_res["definitions"][0]
            assert "sample.py" in target["file"].lower()
            assert target["line"] in (4, 7)  # Class or __init__
            if "snippet" in target:
                assert "Calculator" in target["snippet"]

        # 4. Check diagnostics
        diag_res = await get_diagnostics_tool(manager, cfg, str(sample_python_file))
        assert "diagnostics" in diag_res

    finally:
        # 5. Clean shutdown
        await manager.shutdown_all()
        # Verify no orphaned processes
        clients = await manager.get_all_active_clients()
        assert len(clients) == 0
