"""Tests for LSP server process lifecycle, document synchronization, and restart recovery."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from agy_lsp.config import PluginConfig
from agy_lsp.lsp.client import LspClient
from agy_lsp.lsp.manager import LanguageServerNotAvailableError, LspManager
from agy_lsp.lsp.sync import DocumentManager


def test_document_sync_lifecycle(tmp_path: Path):
    doc_file = tmp_path / "mod.py"
    doc_file.write_text("x = 1\n", encoding="utf-8")

    mgr = DocumentManager()

    # 1. First sync -> didOpen
    action, doc, payload = mgr.prepare_sync(str(doc_file))
    assert action == "open"
    assert doc.version == 1
    assert payload["textDocument"]["text"] == "x = 1\n"

    # 2. No changes -> noop
    action, doc, payload = mgr.prepare_sync(str(doc_file))
    assert action == "noop"
    assert payload is None

    # 3. Content changed -> didChange
    doc_file.write_text("x = 2\n", encoding="utf-8")
    action, doc, payload = mgr.prepare_sync(str(doc_file))
    assert action == "change"
    assert doc.version == 2
    assert payload["contentChanges"][0]["text"] == "x = 2\n"

    # 4. Close document
    close_payload = mgr.close_document(str(doc_file))
    assert close_payload is not None
    assert "textDocument" in close_payload


@pytest.mark.asyncio
async def test_manager_missing_server_raises_clear_error(tmp_path: Path):
    cfg = PluginConfig()
    cfg.workspaceRoot = str(tmp_path)
    cfg.servers["csharp"].command = "completely-nonexistent-command-xyz"
    cfg.servers["csharp"].fallbacks = []

    mgr = LspManager(cfg)
    dummy_cs = tmp_path / "App.cs"
    dummy_cs.write_text("class App {}", encoding="utf-8")

    with pytest.raises(LanguageServerNotAvailableError) as exc_info:
        await mgr.get_client_for_file(str(dummy_cs))

    err = exc_info.value
    assert err.language == "csharp"
    assert "csharp-ls" in err.install_hint or "Roslyn" in err.install_hint


@pytest.mark.asyncio
async def test_manager_restart_limit(tmp_path: Path):
    cfg = PluginConfig()
    cfg.workspaceRoot = str(tmp_path)
    cfg.maxRestartAttempts = 1

    mgr = LspManager(cfg)

    # Mock a dead client
    dead_client = AsyncMock(spec=LspClient)
    dead_client.is_alive = False
    dead_client.last_error = "Server crashed with SIGSEGV"
    dead_client.stop = AsyncMock()

    mgr._clients["python"] = dead_client
    mgr._restart_counts["python"] = 1  # Reached limit

    with pytest.raises(RuntimeError) as exc_info:
        await mgr.get_client_for_language("python")

    assert "reached maximum restart limit" in str(exc_info.value)
