"""Tests for configuration parsing, merging, and environment overrides."""

import json
from pathlib import Path

from agy_lsp.config import load_config


def test_default_config():
    cfg = load_config()
    assert cfg.defaultLanguage == "auto"
    assert cfg.maxResults == 50
    assert cfg.writeChanges is False
    assert cfg.allowOutsideWorkspace is False
    assert "python" in cfg.servers
    assert "csharp" in cfg.servers
    assert "cpp" in cfg.servers
    assert "typescript" in cfg.servers


def test_custom_config_file(tmp_path: Path):
    custom_cfg = {
        "maxResults": 100,
        "writeChanges": True,
        "allowOutsideWorkspace": True,
        "servers": {
            "python": {
                "command": "custom-pyright",
                "args": ["--stdio"],
            }
        },
    }
    cfg_file = tmp_path / "agy-lsp.json"
    cfg_file.write_text(json.dumps(custom_cfg), encoding="utf-8")

    loaded = load_config(custom_path=cfg_file)
    assert loaded.maxResults == 100
    assert loaded.writeChanges is True
    assert loaded.allowOutsideWorkspace is True
    assert loaded.servers["python"].command == "custom-pyright"


def test_env_var_override(monkeypatch):
    monkeypatch.setenv("AGY_LSP_WRITE_CHANGES", "true")
    monkeypatch.setenv("AGY_LSP_ALLOW_OUTSIDE", "1")

    loaded = load_config()
    assert loaded.writeChanges is True
    assert loaded.allowOutsideWorkspace is True
