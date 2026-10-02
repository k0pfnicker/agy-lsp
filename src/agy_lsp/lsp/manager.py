"""LSP Manager orchestrating language server processes, lifecycle, lazy-start, and auto-recovery."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Optional

from agy_lsp.config import PluginConfig
from agy_lsp.lsp.adapters import resolve_language_server
from agy_lsp.lsp.client import LspClient
from agy_lsp.utils.logging import get_logger
from agy_lsp.utils.paths import detect_language_from_path, normalize_path

logger = get_logger("agy-lsp.manager")


class LanguageServerNotAvailableError(Exception):
    """Raised when a language server executable is missing or cannot be started."""

    def __init__(
        self,
        language: str,
        command: str,
        reason: str,
        install_hint: Optional[str] = None,
    ) -> None:
        self.language = language
        self.command = command
        self.reason = reason
        self.install_hint = install_hint
        msg = f"Language server for '{language}' is not available: {reason}"
        if install_hint:
            msg += f"\n\nHow to fix:\n{install_hint}"
        super().__init__(msg)


@dataclass
class ServerStatusInfo:
    language: str
    command: str
    pid: Optional[int]
    status: str
    workspace_root: str
    restart_count: int
    last_error: Optional[str]


class LspManager:
    """Manages LSP client instances, restart attempts, and routing."""

    def __init__(self, config: PluginConfig) -> None:
        self.config = config
        self._clients: dict[str, LspClient] = {}
        self._restart_counts: dict[str, int] = {}
        self._lock = asyncio.Lock()

    async def get_client_for_file(self, file_path: str) -> LspClient:
        """Determine the language for the file and return an active, healthy LspClient."""
        lang = detect_language_from_path(file_path)
        if not lang:
            if self.config.defaultLanguage != "auto":
                lang = self.config.defaultLanguage
            else:
                raise ValueError(
                    f"Could not determine programming language for file: '{file_path}' (unrecognized extension)."
                )
        return await self.get_client_for_language(lang)

    async def get_client_for_language(self, language: str) -> LspClient:
        """Get or lazily start an LspClient for the given language."""
        async with self._lock:
            existing = self._clients.get(language)
            if existing and existing.is_alive:
                return existing

            # If existing crashed or died
            if existing and not existing.is_alive:
                restarts = self._restart_counts.get(language, 0)
                if restarts >= self.config.maxRestartAttempts:
                    raise RuntimeError(
                        f"Language server for '{language}' crashed and reached maximum restart limit "
                        f"({self.config.maxRestartAttempts} attempts). Last error: {existing.last_error}"
                    )
                logger.warning(
                    f"LSP server for '{language}' appears dead. Attempting restart ({restarts + 1}/{self.config.maxRestartAttempts})..."
                )
                self._restart_counts[language] = restarts + 1
                await existing.stop()
                self._clients.pop(language, None)

            # Resolve server executable
            resolution = resolve_language_server(language, self.config)
            if not resolution.is_available:
                raise LanguageServerNotAvailableError(
                    language=language,
                    command=resolution.command,
                    reason=resolution.missing_reason or "Executable not found",
                    install_hint=resolution.install_hint,
                )

            workspace = self.config.workspaceRoot or normalize_path(".")

            client = LspClient(
                language=language,
                command=resolution.command,
                args=resolution.args,
                workspace_root=workspace,
                config=self.config,
                env=resolution.env,
            )

            try:
                await client.start()
                self._clients[language] = client
                return client
            except Exception as e:
                self._clients.pop(language, None)
                raise RuntimeError(
                    f"Failed to start language server for '{language}' ('{resolution.command}'): {e}"
                ) from e

    async def get_all_active_clients(self) -> list[LspClient]:
        """Return all currently active and alive clients."""
        async with self._lock:
            return [c for c in self._clients.values() if c.is_alive]

    def get_status_summary(self) -> list[dict[str, Any]]:
        """Return status information for all managed language servers."""
        statuses = []
        # Check all known supported languages
        all_langs = set(self.config.servers.keys()) | set(self._clients.keys())

        for lang in sorted(all_langs):
            client = self._clients.get(lang)
            if client and client.is_alive:
                status_str = "RUNNING"
                pid = client.pid
                cmd = client.command
                root = client.workspace_root
                err = client.last_error
            elif client and not client.is_alive:
                status_str = "CRASHED"
                pid = None
                cmd = client.command
                root = client.workspace_root
                err = client.last_error or "Process exited unexpectedly"
            else:
                resolution = resolve_language_server(lang, self.config)
                status_str = "AVAILABLE" if resolution.is_available else "NOT_INSTALLED"
                pid = None
                cmd = resolution.command
                root = self.config.workspaceRoot or ""
                err = resolution.missing_reason if not resolution.is_available else None

            statuses.append(
                {
                    "language": lang,
                    "command": cmd,
                    "status": status_str,
                    "pid": pid,
                    "workspace_root": root,
                    "restart_count": self._restart_counts.get(lang, 0),
                    "error": err,
                }
            )

        return statuses

    async def shutdown_all(self) -> None:
        """Gracefully stop all running language server clients."""
        async with self._lock:
            for lang, client in list(self._clients.items()):
                try:
                    await client.stop()
                except Exception as e:
                    logger.warning(f"Error stopping client for {lang}: {e}")
            self._clients.clear()
