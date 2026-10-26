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
    assert "pylsp" in res.command.lower() or "basedpyright" in res.command.lower()


def test_resolve_rust_and_go_install_hints():
    cfg = PluginConfig()
    cfg.servers["rust"].command = "nonexistent-rust-analyzer-bin"
    cfg.servers["go"].command = "nonexistent-gopls-bin"

    rust_res = resolve_language_server("rust", cfg)
    assert rust_res.is_available is False
    assert "rustup component add rust-analyzer" in (rust_res.install_hint or "")

    go_res = resolve_language_server("go", cfg)
    assert go_res.is_available is False
    assert "golang.org/x/tools/gopls" in (go_res.install_hint or "")
