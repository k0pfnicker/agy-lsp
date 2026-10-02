"""Language server adapters, executable discovery, and missing-server diagnostics."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from agy_lsp.config import PluginConfig


@dataclass
class AdapterResolution:
    """Result of resolving a language server executable."""

    language: str
    command: str
    args: list[str]
    env: dict[str, str]
    is_available: bool
    missing_reason: Optional[str] = None
    install_hint: Optional[str] = None


INSTALL_HINTS: dict[str, str] = {
    "csharp": (
        "C# Language Server is not installed or not in PATH.\n"
        "To install csharp-ls:\n"
        "  dotnet tool install -g csharp-ls\n"
        "Alternatively, configure a Roslyn Language Server or omnisharp in agy-lsp.json."
    ),
    "cpp": (
        "C/C++ Language Server (clangd) is not installed or not in PATH.\n"
        "To install clangd:\n"
        "  - Windows: scoop install llvm (or winget install LLVM.LLVM)\n"
        "  - macOS: brew install llvm\n"
        "  - Linux: sudo apt install clangd (or dnf install clang-tools-extra)"
    ),
    "typescript": (
        "TypeScript/JavaScript Language Server is not installed or not in PATH.\n"
        "To install typescript-language-server:\n"
        "  npm install -g typescript-language-server typescript"
    ),
    "python": (
        "Python Language Server is not installed or not in PATH.\n"
        "To install:\n"
        "  - pyright: npm install -g pyright (or pip install pyright)\n"
        "  - python-lsp-server: pip install python-lsp-server"
    ),
}


def find_executable(name: str) -> Optional[str]:
    """Find an executable in PATH, local .venv, or direct filesystem path."""
    # 1. Direct path or file
    if os.path.isfile(name):
        return os.path.abspath(name)

    # 2. Check virtual environment Scripts/bin relative to current directory or plugin
    venv_dir = os.environ.get("VIRTUAL_ENV")
    candidates = []
    if venv_dir:
        candidates.append(Path(venv_dir))
    candidates.append(Path.cwd() / ".venv")
    candidates.append(Path(__file__).resolve().parent.parent.parent.parent / ".venv")

    for venv in candidates:
        if venv.is_dir():
            script_dir = venv / ("Scripts" if os.name == "nt" else "bin")
            for ext in ("", ".exe", ".cmd", ".bat"):
                target = script_dir / f"{name}{ext}"
                if target.is_file():
                    return str(target.resolve())

    # 3. Check system PATH using shutil.which
    found = shutil.which(name)
    if found:
        return os.path.abspath(found)

    # 4. On Windows, check with .exe/.cmd/.bat if not explicitly in name
    if os.name == "nt" and not any(name.lower().endswith(ext) for ext in [".exe", ".cmd", ".bat"]):
        for ext in [".exe", ".cmd", ".bat"]:
            found = shutil.which(f"{name}{ext}")
            if found:
                return os.path.abspath(found)

    return None


def resolve_language_server(language: str, config: PluginConfig) -> AdapterResolution:
    """Resolve the executable and arguments for a language according to configuration and fallbacks."""
    srv_cfg = config.servers.get(language)
    if not srv_cfg:
        return AdapterResolution(
            language=language,
            command="",
            args=[],
            env={},
            is_available=False,
            missing_reason=f"No language server configured for language '{language}'.",
            install_hint=INSTALL_HINTS.get(language, f"Configure a server for '{language}' in agy-lsp.json."),
        )

    # Try primary command
    primary_exe = find_executable(srv_cfg.command)
    if primary_exe:
        return AdapterResolution(
            language=language,
            command=primary_exe,
            args=list(srv_cfg.args),
            env=dict(srv_cfg.env),
            is_available=True,
        )

    # Try fallbacks
    for fb in srv_cfg.fallbacks:
        fb_cmd = fb.get("command")
        if fb_cmd:
            fb_exe = find_executable(fb_cmd)
            if fb_exe:
                return AdapterResolution(
                    language=language,
                    command=fb_exe,
                    args=list(fb.get("args", [])),
                    env=dict(srv_cfg.env),
                    is_available=True,
                )

    hint = INSTALL_HINTS.get(language, f"Install the LSP server for {language}.")
    return AdapterResolution(
        language=language,
        command=srv_cfg.command,
        args=list(srv_cfg.args),
        env=dict(srv_cfg.env),
        is_available=False,
        missing_reason=(f"Language server command '{srv_cfg.command}' for '{language}' was not found on the system."),
        install_hint=hint,
    )
