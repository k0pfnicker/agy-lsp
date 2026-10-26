"""Language server adapters, executable discovery, and missing-server diagnostics."""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from agy_lsp.config import PluginConfig
from agy_lsp.utils.paths import find_compile_commands_dir


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
        "  - Python/.venv (fastest, ~18 MB): pip install clangd\n"
        "  - Windows: pip install clangd (or scoop install llvm / winget install LLVM.LLVM)\n"
        "  - macOS: brew install llvm (or pip install clangd)\n"
        "  - Linux: sudo apt install clangd (or pip install clangd)"
    ),
    "typescript": (
        "TypeScript/JavaScript Language Server is not installed or not in PATH.\n"
        "To install typescript-language-server:\n"
        "  npm install -g typescript-language-server typescript"
    ),
    "python": (
        "Python Language Server is not installed or not in PATH.\n"
        "To install:\n"
        "  - python-lsp-server: pip install python-lsp-server\n"
        "  - basedpyright: pip install basedpyright\n"
        "  - pyright: pip install pyright (or npm install -g pyright)"
    ),
    "rust": (
        "Rust Language Server (rust-analyzer) is not installed or not in PATH.\n"
        "To install rust-analyzer:\n"
        "  rustup component add rust-analyzer"
    ),
    "go": (
        "Go Language Server (gopls) is not installed or not in PATH.\n"
        "To install gopls:\n"
        "  go install golang.org/x/tools/gopls@latest"
    ),
}


def find_executable(name: str) -> Optional[str]:
    """Find an executable in PATH, active Python environment, local .venv, or direct filesystem path."""
    # 1. Direct path or file
    if os.path.isfile(name):
        return os.path.abspath(name)

    # 2. Check active Python environment (sys.executable / sys.prefix) and .venv folders
    venv_dir = os.environ.get("VIRTUAL_ENV")
    script_dirs: list[Path] = []

    # Active interpreter's Scripts/bin folder (works even when launched without activating venv)
    if sys.executable:
        script_dirs.append(Path(sys.executable).resolve().parent)
    if sys.prefix:
        script_dirs.append(Path(sys.prefix).resolve() / ("Scripts" if os.name == "nt" else "bin"))

    venv_candidates = []
    if venv_dir:
        venv_candidates.append(Path(venv_dir))
    venv_candidates.append(Path.cwd() / ".venv")
    venv_candidates.append(Path(__file__).resolve().parent.parent.parent.parent / ".venv")

    for venv in venv_candidates:
        if venv.is_dir():
            script_dirs.append(venv / ("Scripts" if os.name == "nt" else "bin"))

    for script_dir in script_dirs:
        if script_dir.is_dir():
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


def _augment_cpp_args(args: list[str], config: PluginConfig, target_file: Optional[str] = None) -> list[str]:
    """Automatically append --compile-commands-dir for clangd if compile_commands.json is in a subdirectory."""
    final_args = list(args)
    if any(a.startswith("--compile-commands-dir") for a in final_args):
        return final_args

    cc_dir = find_compile_commands_dir(target_file, config.workspaceRoot)
    if cc_dir:
        final_args.append(f"--compile-commands-dir={cc_dir}")
    return final_args


def resolve_language_server(
    language: str,
    config: PluginConfig,
    target_file: Optional[str] = None,
) -> AdapterResolution:
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
        args = _augment_cpp_args(srv_cfg.args, config, target_file) if language == "cpp" else list(srv_cfg.args)
        return AdapterResolution(
            language=language,
            command=primary_exe,
            args=args,
            env=dict(srv_cfg.env),
            is_available=True,
        )

    # Try fallbacks
    for fb in srv_cfg.fallbacks:
        fb_cmd = fb.get("command")
        if fb_cmd:
            fb_exe = find_executable(fb_cmd)
            if fb_exe:
                fb_args = list(fb.get("args", []))
                if language == "cpp" and "clangd" in Path(fb_exe).name.lower():
                    fb_args = _augment_cpp_args(fb_args, config, target_file)
                return AdapterResolution(
                    language=language,
                    command=fb_exe,
                    args=fb_args,
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
