"""Tests for language server adapters and missing-executable handling."""

from agy_lsp.config import PluginConfig
from agy_lsp.lsp.adapters import resolve_language_server


def test_resolve_missing_server():
    cfg = PluginConfig()
    # Query language with intentionally nonexistent command
    cfg.servers["csharp"].command = "nonexistent-csharp-compiler-binary"
    cfg.servers["csharp"].fallbacks = []

    res = resolve_language_server("csharp", cfg)
    assert res.is_available is False
    assert "csharp" in res.missing_reason.lower()
    assert res.install_hint is not None
    assert "dotnet tool install -g csharp-ls" in res.install_hint


def test_resolve_fallback_command():
    cfg = PluginConfig()
    cfg.servers["python"].command = "nonexistent-pyright-command"
    # Fallback to python itself or pylsp which is installed in .venv
    res = resolve_language_server("python", cfg)
    # pylsp was installed in .venv, so it should resolve via fallback!
    assert res.is_available is True
    assert "pylsp" in res.command.lower()
