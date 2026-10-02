"""LSP Client implementation handling asynchronous JSON-RPC communication over stdio."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Optional

from agy_lsp.config import PluginConfig
from agy_lsp.lsp.protocol import encode_lsp_message
from agy_lsp.lsp.sync import DocumentManager
from agy_lsp.utils.logging import get_logger
from agy_lsp.utils.paths import normalize_path, path_to_uri

logger = get_logger("agy-lsp.client")


class LspClient:
    """Asynchronous client for interacting with a Language Server process over stdio JSON-RPC."""

    def __init__(
        self,
        language: str,
        command: str,
        args: list[str],
        workspace_root: str,
        config: PluginConfig,
        env: Optional[dict[str, str]] = None,
    ) -> None:
        self.language = language
        self.command = command
        self.args = args
        self.workspace_root = normalize_path(workspace_root)
        self.config = config
        self.env = env or {}

        self.proc: Optional[asyncio.subprocess.Process] = None
        self._reader_task: Optional[asyncio.Task] = None
        self._next_id = 1
        self._pending_requests: dict[int | str, asyncio.Future[Any]] = {}
        self.doc_manager = DocumentManager()

        # Cache published diagnostics: uri -> list of LSP diagnostic objects
        self.diagnostics_cache: dict[str, list[dict[str, Any]]] = {}
        self.server_capabilities: dict[str, Any] = {}
        self.last_error: Optional[str] = None
        self._is_initialized = False
        self._closed = False

    @property
    def is_alive(self) -> bool:
        return self.proc is not None and self.proc.returncode is None

    @property
    def pid(self) -> Optional[int]:
        return self.proc.pid if self.proc else None

    async def start(self) -> None:
        """Start the Language Server subprocess and execute the initialize handshake."""
        if self.is_alive:
            return

        spawn_env = os.environ.copy()
        spawn_env.update(self.env)
        # Ensure unbuffered IO where applicable
        spawn_env["PYTHONUNBUFFERED"] = "1"

        logger.info(
            f"Spawning LSP server for {self.language}: '{self.command}' with args {self.args} in {self.workspace_root}"
        )

        try:
            # Strictly do NOT use shell=True for security against command injection
            self.proc = await asyncio.create_subprocess_exec(
                self.command,
                *self.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.workspace_root,
                env=spawn_env,
            )
        except Exception as e:
            self.last_error = f"Failed to spawn language server '{self.command}': {e}"
            logger.error(self.last_error)
            raise RuntimeError(self.last_error) from e

        self._reader_task = asyncio.create_task(self._read_stdout_loop())
        asyncio.create_task(self._read_stderr_loop())

        # Perform initialize handshake
        await self._initialize_handshake()

    async def _initialize_handshake(self) -> None:
        """Send the initialize request and initialized notification with full capabilities."""
        root_uri = path_to_uri(self.workspace_root)
        init_params: dict[str, Any] = {
            "processId": os.getpid(),
            "rootUri": root_uri,
            "rootPath": self.workspace_root,
            "workspaceFolders": [
                {
                    "uri": root_uri,
                    "name": Path(self.workspace_root).name or "workspace",
                }
            ],
            "capabilities": {
                "workspace": {
                    "applyEdit": True,
                    "workspaceEdit": {"documentChanges": True},
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "symbol": {
                        "dynamicRegistration": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                },
                "textDocument": {
                    "synchronization": {
                        "dynamicRegistration": True,
                        "willSave": False,
                        "willSaveWaitUntil": False,
                        "didSave": True,
                    },
                    "publishDiagnostics": {
                        "relatedInformation": True,
                        "tagSupport": {"valueSet": [1, 2]},
                        "versionSupport": True,
                    },
                    "hover": {
                        "dynamicRegistration": True,
                        "contentFormat": ["markdown", "plaintext"],
                    },
                    "definition": {"dynamicRegistration": True, "linkSupport": True},
                    "references": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                    "rename": {
                        "dynamicRegistration": True,
                        "prepareSupport": True,
                    },
                    "callHierarchy": {"dynamicRegistration": True},
                    "typeHierarchy": {"dynamicRegistration": True},
                },
            },
            "initializationOptions": {},
        }

        try:
            response = await asyncio.wait_for(
                self.send_request("initialize", init_params),
                timeout=self.config.server_startup_timeout_sec,
            )
            if isinstance(response, dict):
                self.server_capabilities = response.get("capabilities", {})
            self._is_initialized = True
            await self.send_notification("initialized", {})
            logger.info(f"LSP server for {self.language} successfully initialized.")
        except asyncio.TimeoutError:
            self.last_error = f"LSP server for {self.language} timed out during initialization."
            logger.error(self.last_error)
            await self.stop()
            raise TimeoutError(self.last_error) from None
        except Exception as e:
            self.last_error = f"Initialization error for {self.language}: {e}"
            logger.error(self.last_error)
            await self.stop()
            raise

    async def _read_stdout_loop(self) -> None:
        """Continuously parse LSP messages from subprocess stdout."""
        assert self.proc and self.proc.stdout
        buffer = bytearray()

        try:
            while not self._closed and self.is_alive:
                chunk = await self.proc.stdout.read(65536)
                if not chunk:
                    break
                buffer.extend(chunk)

                while True:
                    # Look for header separator \r\n\r\n
                    header_end = buffer.find(b"\r\n\r\n")
                    if header_end == -1:
                        break

                    header_bytes = buffer[:header_end]
                    content_length = None
                    for line in header_bytes.decode("latin1", errors="replace").split("\r\n"):
                        if line.lower().startswith("content-length:"):
                            try:
                                content_length = int(line.split(":", 1)[1].strip())
                            except ValueError:
                                pass

                    if content_length is None:
                        # Malformed header, skip
                        buffer = buffer[header_end + 4 :]
                        continue

                    body_start = header_end + 4
                    body_end = body_start + content_length

                    if len(buffer) < body_end:
                        # Wait for more data
                        break

                    body_bytes = buffer[body_start:body_end]
                    buffer = buffer[body_end:]

                    try:
                        message = json.loads(body_bytes.decode("utf-8"))
                        self._handle_lsp_message(message)
                    except Exception as e:
                        logger.warning(f"Error parsing LSP JSON payload: {e}")

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"LSP stdout reader error: {e}")
        finally:
            self._fail_pending_requests("LSP process connection closed")

    async def _read_stderr_loop(self) -> None:
        """Stream stderr output to safe logger."""
        if not self.proc or not self.proc.stderr:
            return
        try:
            while not self._closed and self.is_alive:
                line = await self.proc.stderr.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").rstrip()
                if text:
                    logger.debug(f"[{self.language}-lsp stderr] {text}")
        except Exception:
            pass

    def _handle_lsp_message(self, msg: dict[str, Any]) -> None:
        """Handle incoming LSP message (response, notification, or request)."""
        msg_id = msg.get("id")

        # 1. Response to a pending client request
        if msg_id is not None and ("result" in msg or "error" in msg):
            future = self._pending_requests.pop(msg_id, None)
            if future and not future.done():
                if "error" in msg and msg["error"] is not None:
                    err = msg["error"]
                    err_msg = err.get("message", "Unknown LSP error") if isinstance(err, dict) else str(err)
                    future.set_exception(RuntimeError(f"LSP Error: {err_msg}"))
                else:
                    future.set_result(msg.get("result"))
            return

        # 2. Server-to-client request (must respond so server doesn't hang)
        method = msg.get("method", "")
        if msg_id is not None and method:
            asyncio.create_task(self._respond_to_server_request(msg_id, method, msg.get("params")))
            return

        # 3. Notification
        if method:
            self._handle_notification(method, msg.get("params", {}))

    async def _respond_to_server_request(self, req_id: Any, method: str, params: Any) -> None:
        """Respond with appropriate defaults to server requests."""
        result: Any = None
        if method == "workspace/configuration":
            # Return empty config for each item requested
            items = (params or {}).get("items", [])
            result = [{} for _ in items]
        elif method == "client/registerCapability":
            result = None
        elif method == "workspace/workspaceFolders":
            root_uri = path_to_uri(self.workspace_root)
            result = [{"uri": root_uri, "name": Path(self.workspace_root).name}]

        response = {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": result,
        }
        await self._send_raw(encode_lsp_message(response))

    def _handle_notification(self, method: str, params: dict[str, Any]) -> None:
        """Handle notifications sent from the language server."""
        if method == "textDocument/publishDiagnostics":
            uri = params.get("uri", "")
            diagnostics = params.get("diagnostics", [])
            if uri:
                self.diagnostics_cache[uri] = diagnostics
                logger.debug(f"Received {len(diagnostics)} diagnostics for {uri}")
        elif method in ("window/showMessage", "window/logMessage"):
            msg = params.get("message", "")
            logger.info(f"[{self.language}-lsp] {msg}")

    def _fail_pending_requests(self, reason: str) -> None:
        for fut in self._pending_requests.values():
            if not fut.done():
                fut.set_exception(ConnectionResetError(reason))
        self._pending_requests.clear()

    async def _send_raw(self, data: bytes) -> None:
        if not self.proc or not self.proc.stdin or self.proc.returncode is not None:
            raise ConnectionResetError(f"Language server {self.language} is not running.")
        self.proc.stdin.write(data)
        await self.proc.stdin.drain()

    async def send_request(self, method: str, params: Any) -> Any:
        """Send a JSON-RPC request and wait for the response."""
        req_id = self._next_id
        self._next_id += 1

        loop = asyncio.get_running_loop()
        future: asyncio.Future[Any] = loop.create_future()
        self._pending_requests[req_id] = future

        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        }

        try:
            await self._send_raw(encode_lsp_message(payload))
            return await asyncio.wait_for(future, timeout=self.config.request_timeout_sec)
        except asyncio.TimeoutError:
            self._pending_requests.pop(req_id, None)
            raise TimeoutError(f"LSP request '{method}' timed out after {self.config.request_timeout_sec}s") from None
        except Exception:
            self._pending_requests.pop(req_id, None)
            raise

    async def send_notification(self, method: str, params: Any) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        await self._send_raw(encode_lsp_message(payload))

    async def ensure_file_synced(self, file_path: str) -> str:
        """Ensure file is read and synchronized with the language server."""
        action, doc, payload = self.doc_manager.prepare_sync(file_path)
        if action == "open" and payload:
            await self.send_notification("textDocument/didOpen", payload)
            # Give server a brief moment to process open
            await asyncio.sleep(0.05)
        elif action == "change" and payload:
            await self.send_notification("textDocument/didChange", payload)
            await asyncio.sleep(0.05)
        return doc.uri

    async def get_diagnostics(self, file_path: Optional[str] = None) -> list[dict[str, Any]]:
        """Get diagnostics for a file or all cached diagnostics across the workspace."""
        if file_path:
            norm = normalize_path(file_path)
            uri = path_to_uri(norm)
            await self.ensure_file_synced(norm)
            # Wait briefly to let server publish diagnostics
            await asyncio.sleep(0.2)
            return list(self.diagnostics_cache.get(uri, []))

        # Whole workspace
        results = []
        for _uri, diags in self.diagnostics_cache.items():
            results.extend(diags)
        return results

    async def get_definition(self, file_path: str, line_1idx: int, character_1idx: int) -> Any:
        norm = normalize_path(file_path)
        uri = await self.ensure_file_synced(norm)
        params = {
            "textDocument": {"uri": uri},
            "position": {"line": line_1idx - 1, "character": character_1idx - 1},
        }
        return await self.send_request("textDocument/definition", params)

    async def get_references(
        self,
        file_path: str,
        line_1idx: int,
        character_1idx: int,
        include_declaration: bool = False,
    ) -> Any:
        norm = normalize_path(file_path)
        uri = await self.ensure_file_synced(norm)
        params = {
            "textDocument": {"uri": uri},
            "position": {"line": line_1idx - 1, "character": character_1idx - 1},
            "context": {"includeDeclaration": include_declaration},
        }
        return await self.send_request("textDocument/references", params)

    async def get_hover(self, file_path: str, line_1idx: int, character_1idx: int) -> Any:
        norm = normalize_path(file_path)
        uri = await self.ensure_file_synced(norm)
        params = {
            "textDocument": {"uri": uri},
            "position": {"line": line_1idx - 1, "character": character_1idx - 1},
        }
        return await self.send_request("textDocument/hover", params)

    async def get_document_symbols(self, file_path: str) -> Any:
        norm = normalize_path(file_path)
        uri = await self.ensure_file_synced(norm)
        params = {"textDocument": {"uri": uri}}
        return await self.send_request("textDocument/documentSymbol", params)

    async def get_workspace_symbols(self, query: str) -> Any:
        params = {"query": query}
        return await self.send_request("workspace/symbol", params)

    async def rename_symbol(self, file_path: str, line_1idx: int, character_1idx: int, new_name: str) -> Any:
        norm = normalize_path(file_path)
        uri = await self.ensure_file_synced(norm)
        params = {
            "textDocument": {"uri": uri},
            "position": {"line": line_1idx - 1, "character": character_1idx - 1},
            "newName": new_name,
        }
        return await self.send_request("textDocument/rename", params)

    async def prepare_call_hierarchy(self, file_path: str, line_1idx: int, character_1idx: int) -> Any:
        norm = normalize_path(file_path)
        uri = await self.ensure_file_synced(norm)
        params = {
            "textDocument": {"uri": uri},
            "position": {"line": line_1idx - 1, "character": character_1idx - 1},
        }
        return await self.send_request("textDocument/prepareCallHierarchy", params)

    async def call_hierarchy_incoming(self, item: dict[str, Any]) -> Any:
        return await self.send_request("callHierarchy/incomingCalls", {"item": item})

    async def call_hierarchy_outgoing(self, item: dict[str, Any]) -> Any:
        return await self.send_request("callHierarchy/outgoingCalls", {"item": item})

    async def prepare_type_hierarchy(self, file_path: str, line_1idx: int, character_1idx: int) -> Any:
        norm = normalize_path(file_path)
        uri = await self.ensure_file_synced(norm)
        params = {
            "textDocument": {"uri": uri},
            "position": {"line": line_1idx - 1, "character": character_1idx - 1},
        }
        return await self.send_request("textDocument/prepareTypeHierarchy", params)

    async def type_hierarchy_supertypes(self, item: dict[str, Any]) -> Any:
        return await self.send_request("typeHierarchy/supertypes", {"item": item})

    async def type_hierarchy_subtypes(self, item: dict[str, Any]) -> Any:
        return await self.send_request("typeHierarchy/subtypes", {"item": item})

    async def stop(self) -> None:
        """Gracefully shut down the Language Server process."""
        self._closed = True
        if not self.proc:
            return

        try:
            if self.is_alive and self._is_initialized:
                try:
                    await asyncio.wait_for(self.send_request("shutdown", None), timeout=2.0)
                    await self.send_notification("exit", None)
                except Exception:
                    pass

            if self.is_alive:
                self.proc.terminate()
                try:
                    await asyncio.wait_for(self.proc.wait(), timeout=3.0)
                except asyncio.TimeoutError:
                    self.proc.kill()
        except Exception as e:
            logger.warning(f"Error during LSP shutdown: {e}")
        finally:
            if self._reader_task and not self._reader_task.done():
                self._reader_task.cancel()
            self._fail_pending_requests("LSP server stopped")
            self.proc = None
