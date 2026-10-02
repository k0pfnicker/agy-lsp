"""Unit tests for all MCP tool handlers with security, formatting, and behavior verification."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from agy_lsp.lsp.manager import LspManager
from agy_lsp.tools import (
    call_hierarchy_tool,
    document_symbols_tool,
    find_references_tool,
    get_diagnostics_tool,
    get_type_hierarchy_tool,
    go_to_definition_tool,
    hover_tool,
    lsp_status_tool,
    rename_symbol_tool,
    workspace_symbols_tool,
)
from agy_lsp.utils.paths import path_to_uri


@pytest.fixture
def mock_client(sample_python_file: Path):
    client = MagicMock()
    client.is_alive = True
    client.pid = 12345
    client.command = "mock-lsp"
    client.workspace_root = str(sample_python_file.parent)
    client.last_error = None
    client.diagnostics_cache = {
        path_to_uri(sample_python_file): [
            {
                "range": {
                    "start": {"line": 4, "character": 0},
                    "end": {"line": 4, "character": 10},
                },
                "severity": 1,
                "message": "Sample error message",
                "code": "E101",
                "source": "mock",
            }
        ]
    }
    client.get_diagnostics = AsyncMock(return_value=client.diagnostics_cache[path_to_uri(sample_python_file)])
    client.get_definition = AsyncMock(
        return_value={
            "uri": path_to_uri(sample_python_file),
            "range": {
                "start": {"line": 3, "character": 6},
                "end": {"line": 3, "character": 16},
            },
        }
    )
    client.get_references = AsyncMock(
        return_value=[
            {
                "uri": path_to_uri(sample_python_file),
                "range": {
                    "start": {"line": 21, "character": 11},
                    "end": {"line": 21, "character": 21},
                },
            }
        ]
    )
    client.get_hover = AsyncMock(
        return_value={
            "contents": {
                "kind": "markdown",
                "value": "```python\nclass Calculator\n```\nA simple arithmetic calculator.",
            }
        }
    )
    client.get_document_symbols = AsyncMock(
        return_value=[
            {
                "name": "Calculator",
                "kind": 5,
                "range": {
                    "start": {"line": 3, "character": 0},
                    "end": {"line": 17, "character": 0},
                },
                "children": [
                    {
                        "name": "add",
                        "kind": 6,
                        "range": {
                            "start": {"line": 9, "character": 4},
                            "end": {"line": 12, "character": 0},
                        },
                    }
                ],
            }
        ]
    )
    client.get_workspace_symbols = AsyncMock(
        return_value=[
            {
                "name": "Calculator",
                "kind": 5,
                "location": {
                    "uri": path_to_uri(sample_python_file),
                    "range": {
                        "start": {"line": 3, "character": 0},
                        "end": {"line": 17, "character": 0},
                    },
                },
            }
        ]
    )
    client.prepare_call_hierarchy = AsyncMock(
        return_value=[
            {
                "name": "compute_total",
                "kind": 12,
                "uri": path_to_uri(sample_python_file),
                "range": {
                    "start": {"line": 19, "character": 4},
                    "end": {"line": 23, "character": 0},
                },
            }
        ]
    )
    client.call_hierarchy_incoming = AsyncMock(
        return_value=[
            {
                "from": {
                    "name": "main_entry",
                    "kind": 12,
                    "uri": path_to_uri(sample_python_file),
                    "range": {
                        "start": {"line": 25, "character": 4},
                        "end": {"line": 28, "character": 0},
                    },
                }
            }
        ]
    )
    client.prepare_type_hierarchy = AsyncMock(
        return_value=[
            {
                "name": "Calculator",
                "kind": 5,
                "uri": path_to_uri(sample_python_file),
                "range": {
                    "start": {"line": 3, "character": 0},
                    "end": {"line": 17, "character": 0},
                },
            }
        ]
    )
    client.type_hierarchy_supertypes = AsyncMock(
        return_value=[
            {
                "name": "object",
                "kind": 5,
                "uri": path_to_uri(sample_python_file),
                "range": {
                    "start": {"line": 0, "character": 0},
                    "end": {"line": 0, "character": 0},
                },
            }
        ]
    )
    client.rename_symbol = AsyncMock(
        return_value={
            "changes": {
                path_to_uri(sample_python_file): [
                    {
                        "range": {
                            "start": {"line": 3, "character": 6},
                            "end": {"line": 3, "character": 16},
                        },
                        "newText": "MathEngine",
                    }
                ]
            }
        }
    )
    client.doc_manager = MagicMock()
    client.ensure_file_synced = AsyncMock(return_value=path_to_uri(sample_python_file))
    return client


@pytest.fixture
def mock_manager(mock_client):
    manager = MagicMock(spec=LspManager)
    manager.get_client_for_file = AsyncMock(return_value=mock_client)
    manager.get_client_for_language = AsyncMock(return_value=mock_client)
    manager.get_all_active_clients = AsyncMock(return_value=[mock_client])
    manager.get_status_summary = MagicMock(
        return_value=[
            {
                "language": "python",
                "command": "mock-lsp",
                "status": "RUNNING",
                "pid": 12345,
                "workspace_root": mock_client.workspace_root,
                "restart_count": 0,
                "error": None,
            }
        ]
    )
    return manager


@pytest.mark.asyncio
async def test_get_diagnostics(mock_manager, test_config, sample_python_file):
    res = await get_diagnostics_tool(mock_manager, test_config, file_path=str(sample_python_file))
    assert "diagnostics" in res
    assert res["count"] == 1
    diag = res["diagnostics"][0]
    assert diag["severity"] == "Error"
    assert diag["line"] == 5  # 1-indexed


@pytest.mark.asyncio
async def test_security_outside_workspace_rejected(mock_manager, test_config, tmp_path):
    outside_file = tmp_path / "outside.py"
    outside_file.write_text("x = 1\n", encoding="utf-8")

    res = await get_diagnostics_tool(mock_manager, test_config, file_path=str(outside_file))
    assert "error" in res
    assert "Security restriction" in res["error"]


@pytest.mark.asyncio
async def test_go_to_definition(mock_manager, test_config, sample_python_file):
    res = await go_to_definition_tool(
        mock_manager,
        test_config,
        file_path=str(sample_python_file),
        line=22,
        character=15,
        include_snippet=True,
    )
    assert "definitions" in res
    assert res["count"] == 1
    defn = res["definitions"][0]
    assert defn["line"] == 4
    assert "snippet" in defn
    assert "class Calculator:" in defn["snippet"]


@pytest.mark.asyncio
async def test_find_references(mock_manager, test_config, sample_python_file):
    res = await find_references_tool(
        mock_manager,
        test_config,
        file_path=str(sample_python_file),
        line=4,
        character=7,
        limit=10,
    )
    assert "references" in res
    assert res["count"] == 1
    assert res["references"][0]["line"] == 22


@pytest.mark.asyncio
async def test_hover(mock_manager, test_config, sample_python_file):
    res = await hover_tool(
        mock_manager,
        test_config,
        file_path=str(sample_python_file),
        line=4,
        character=7,
    )
    assert "hover" in res
    assert "class Calculator" in res["hover"]


@pytest.mark.asyncio
async def test_document_symbols(mock_manager, test_config, sample_python_file):
    res = await document_symbols_tool(
        mock_manager,
        test_config,
        file_path=str(sample_python_file),
    )
    assert res["count"] == 1
    sym = res["symbols"][0]
    assert sym["name"] == "Calculator"
    assert sym["kind"] == "Class"
    assert len(sym["children"]) == 1
    assert sym["children"][0]["name"] == "add"


@pytest.mark.asyncio
async def test_workspace_symbols(mock_manager, test_config):
    res = await workspace_symbols_tool(
        mock_manager,
        test_config,
        query="Calc",
    )
    assert res["count"] == 1
    assert res["symbols"][0]["name"] == "Calculator"


@pytest.mark.asyncio
async def test_rename_symbol_preview_only_by_default(mock_manager, test_config, sample_python_file):
    # Verify file content before rename
    original_text = sample_python_file.read_text(encoding="utf-8")
    assert "class Calculator:" in original_text

    # Default apply=False
    res = await rename_symbol_tool(
        mock_manager,
        test_config,
        file_path=str(sample_python_file),
        line=4,
        character=7,
        new_name="MathEngine",
        apply=False,
    )

    assert res["applied"] is False
    assert "PREVIEW ONLY" in res["message"]
    assert str(sample_python_file) in res["diffs"]
    assert "+class MathEngine:" in res["diffs"][str(sample_python_file)]

    # Confirm file on disk was NOT modified!
    after_text = sample_python_file.read_text(encoding="utf-8")
    assert after_text == original_text


@pytest.mark.asyncio
async def test_rename_symbol_apply_with_permission(mock_manager, test_config, sample_python_file):
    # Create temporary copy to test actual disk write
    test_config.writeChanges = True
    try:
        res = await rename_symbol_tool(
            mock_manager,
            test_config,
            file_path=str(sample_python_file),
            line=4,
            character=7,
            new_name="MathEngine",
            apply=True,
        )
        assert res["applied"] is True
        assert "applied to disk" in res["message"]
    finally:
        sample_python_file.write_text(
            sample_python_file.read_text(encoding="utf-8").replace("MathEngine", "Calculator"),
            encoding="utf-8",
        )


@pytest.mark.asyncio
async def test_call_hierarchy(mock_manager, test_config, sample_python_file):
    res = await call_hierarchy_tool(
        mock_manager,
        test_config,
        file_path=str(sample_python_file),
        line=20,
        character=5,
        direction="incoming",
    )
    assert res["count"] == 1
    assert res["calls"][0]["name"] == "main_entry"


@pytest.mark.asyncio
async def test_type_hierarchy(mock_manager, test_config, sample_python_file):
    res = await get_type_hierarchy_tool(
        mock_manager,
        test_config,
        file_path=str(sample_python_file),
        line=4,
        character=7,
        direction="supertypes",
    )
    assert res["count"] == 1
    assert res["types"][0]["name"] == "object"


@pytest.mark.asyncio
async def test_lsp_status(mock_manager, test_config):
    res = await lsp_status_tool(mock_manager, test_config)
    assert "workspace_root" in res
    assert "servers" in res
    assert len(res["servers"]) == 1
    assert res["servers"][0]["status"] == "RUNNING"
