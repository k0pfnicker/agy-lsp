"""Configuration management for agy-lsp.

Supports environment overrides, project-local agy-lsp.json, global configs,
and safe defaults.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from agy_lsp.utils.logging import get_logger
from agy_lsp.utils.paths import find_workspace_root, normalize_path

logger = get_logger("agy-lsp.config")


@dataclass
class ServerConfig:
    """Configuration for a specific Language Server."""

    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    fallbacks: list[dict[str, Any]] = field(default_factory=list)


DEFAULT_SERVERS: dict[str, ServerConfig] = {
    "csharp": ServerConfig(
        command="csharp-ls",
        args=[],
        fallbacks=[
            {"command": "roslyn-language-server", "args": ["--stdio"]},
        ],
    ),
    "cpp": ServerConfig(
        command="clangd",
        args=["--background-index"],
        fallbacks=[
            {"command": "ccls", "args": []},
        ],
    ),
    "typescript": ServerConfig(
        command="typescript-language-server",
        args=["--stdio"],
        fallbacks=[
            {"command": "vtsls", "args": ["--stdio"]},
        ],
    ),
    "python": ServerConfig(
        command="pyright-langserver",
        args=["--stdio"],
        fallbacks=[
            {"command": "pylsp", "args": []},
            {"command": "pyright", "args": ["--langserver"]},
        ],
    ),
}


@dataclass
class PluginConfig:
    """Master configuration for the agy-lsp plugin."""

    defaultLanguage: str = "auto"
    workspaceRoot: Optional[str] = None
    maxResults: int = 50
    includeCodeSnippets: bool = False
    snippetContextLines: int = 3
    allowOutsideWorkspace: bool = False
    writeChanges: bool = False
    serverStartupTimeoutMs: int = 15000
    requestTimeoutMs: int = 10000
    maxRestartAttempts: int = 2
    servers: dict[str, ServerConfig] = field(default_factory=lambda: dict(DEFAULT_SERVERS))

    @property
    def server_startup_timeout_sec(self) -> float:
        return max(1.0, self.serverStartupTimeoutMs / 1000.0)

    @property
    def request_timeout_sec(self) -> float:
        return max(1.0, self.requestTimeoutMs / 1000.0)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


def load_config(
    custom_path: Optional[str | Path] = None,
    workspace_dir: Optional[str | Path] = None,
) -> PluginConfig:
    """Load and merge configuration from defaults, user files, and environment."""
    cfg = PluginConfig()

    # 1. Determine workspace root
    root = find_workspace_root(workspace_dir or os.getcwd())
    cfg.workspaceRoot = root

    # Potential config locations in order of precedence:
    candidates: list[Path] = []

    # A) Explicit path from argument or env
    env_cfg = os.environ.get("AGY_LSP_CONFIG")
    if custom_path:
        candidates.append(Path(custom_path))
    elif env_cfg:
        candidates.append(Path(env_cfg))

    # B) Project-level config
    candidates.append(Path(root) / "agy-lsp.json")
    candidates.append(Path(root) / ".gemini" / "agy-lsp.json")

    # C) Global config
    candidates.append(Path.home() / ".gemini" / "config" / "agy-lsp.json")

    for cand in candidates:
        if cand.is_file():
            try:
                data = json.loads(cand.read_text(encoding="utf-8"))
                _apply_dict_to_config(cfg, data)
                logger.info(f"Loaded configuration from {cand}")
                break
            except Exception as e:
                logger.warning(f"Failed to parse config file {cand}: {e}")

    # Environment variable overrides
    if os.environ.get("AGY_LSP_WRITE_CHANGES", "").lower() in ("1", "true", "yes"):
        cfg.writeChanges = True
    if os.environ.get("AGY_LSP_ALLOW_OUTSIDE", "").lower() in ("1", "true", "yes"):
        cfg.allowOutsideWorkspace = True

    # Normalize workspace root if specified in config
    if cfg.workspaceRoot:
        cfg.workspaceRoot = normalize_path(cfg.workspaceRoot)

    return cfg


def _apply_dict_to_config(cfg: PluginConfig, data: dict[str, Any]) -> None:
    """Safely apply dictionary values to PluginConfig instance."""
    if "defaultLanguage" in data:
        cfg.defaultLanguage = str(data["defaultLanguage"])
    if "workspaceRoot" in data and data["workspaceRoot"]:
        cfg.workspaceRoot = str(data["workspaceRoot"])
    if "maxResults" in data:
        cfg.maxResults = int(data["maxResults"])
    if "includeCodeSnippets" in data:
        cfg.includeCodeSnippets = bool(data["includeCodeSnippets"])
    if "snippetContextLines" in data:
        cfg.snippetContextLines = int(data["snippetContextLines"])
    if "allowOutsideWorkspace" in data:
        cfg.allowOutsideWorkspace = bool(data["allowOutsideWorkspace"])
    if "writeChanges" in data:
        cfg.writeChanges = bool(data["writeChanges"])
    if "serverStartupTimeoutMs" in data:
        cfg.serverStartupTimeoutMs = int(data["serverStartupTimeoutMs"])
    if "requestTimeoutMs" in data:
        cfg.requestTimeoutMs = int(data["requestTimeoutMs"])
    if "maxRestartAttempts" in data:
        cfg.maxRestartAttempts = int(data["maxRestartAttempts"])

    if "servers" in data and isinstance(data["servers"], dict):
        for lang, srv_data in data["servers"].items():
            if isinstance(srv_data, dict) and "command" in srv_data:
                cfg.servers[lang] = ServerConfig(
                    command=srv_data["command"],
                    args=srv_data.get("args", []),
                    env=srv_data.get("env", {}),
                    fallbacks=srv_data.get("fallbacks", []),
                )
