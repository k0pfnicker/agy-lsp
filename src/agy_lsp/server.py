"""Main MCP Server for agy-lsp.

Exposes Language Server Protocol capabilities as Model Context Protocol (MCP) tools
for Antigravity CLI and agents.
"""

from __future__ import annotations

import asyncio
import atexit
import sys
from typing import Any, Optional

try:
    from mcp.server.mcpserver import MCPServer
except ImportError:
    from mcp.server.fastmcp import FastMCP as MCPServer

from agy_lsp.config import PluginConfig, load_config
from agy_lsp.lsp.manager import LanguageServerNotAvailableError, LspManager
from agy_lsp.tools import (
    call_hierarchy_tool,
    document_symbols_tool,
    find_references_tool,
    get_diagnostics_tool,
    get_type_hierarchy_tool,
    go_to_definition_tool,
    hover_tool,
    lsp_status_tool,
    prepare_call_hierarchy_tool,
    rename_symbol_tool,
    workspace_symbols_tool,
)
from agy_lsp.utils.logging import get_logger

logger = get_logger("agy-lsp.server")


def create_server(config: Optional[PluginConfig] = None) -> tuple[MCPServer, LspManager, PluginConfig]:
    """Create and configure the MCPServer instance and underlying LspManager."""
    cfg = config or load_config()
    manager = LspManager(cfg)

    app = MCPServer(
        name="agy-lsp",
        version="1.0.0",
        description="Language Server Protocol (LSP) Bridge for Antigravity CLI. Provides diagnostics, definitions, references, hover, symbols, call hierarchy, and safe renaming.",
    )

    # 1. get_diagnostics
    @app.tool(
        name="get_diagnostics",
        description=(
            "Retrieve errors, warnings, and code hints for a file or the whole workspace. "
            "Use to check syntax/type errors after edits, before and after refactoring."
        ),
    )
    async def get_diagnostics(
        file_path: Optional[str] = None,
        line_start: Optional[int] = None,
        line_end: Optional[int] = None,
        severity: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> dict[str, Any]:
        """Get diagnostics for a file or entire workspace."""
        try:
            return await get_diagnostics_tool(
                manager=manager,
                config=cfg,
                file_path=file_path,
                line_start=line_start,
                line_end=line_end,
                severity=severity,
                limit=limit,
            )
        except LanguageServerNotAvailableError as e:
            return {"error": e.reason, "language": e.language, "install_hint": e.install_hint}
        except Exception as e:
            logger.error(f"Error in get_diagnostics: {e}")
            return {"error": str(e)}

    # 2. go_to_definition
    @app.tool(
        name="go_to_definition",
        description=(
            "Jump from a symbol position to its declaration/definition. "
            "Returns target file path, line, column, and optional surrounding code snippet."
        ),
    )
    async def go_to_definition(
        file_path: str,
        line: int,
        character: int,
        include_snippet: Optional[bool] = None,
    ) -> dict[str, Any]:
        """Go to definition of a symbol at line:character (1-indexed)."""
        try:
            return await go_to_definition_tool(
                manager=manager,
                config=cfg,
                file_path=file_path,
                line=line,
                character=character,
                include_snippet=include_snippet,
            )
        except LanguageServerNotAvailableError as e:
            return {"error": e.reason, "language": e.language, "install_hint": e.install_hint}
        except Exception as e:
            logger.error(f"Error in go_to_definition: {e}")
            return {"error": str(e)}

    # 3. find_references
    @app.tool(
        name="find_references",
        description=(
            "Find all references and usages of a symbol across the workspace. "
            "Returns file locations and compact line numbers. Use to assess impact of changes."
        ),
    )
    async def find_references(
        file_path: str,
        line: int,
        character: int,
        include_declaration: bool = False,
        limit: Optional[int] = None,
        include_snippet: Optional[bool] = None,
    ) -> dict[str, Any]:
        """Find references to a symbol at line:character (1-indexed)."""
        try:
            return await find_references_tool(
                manager=manager,
                config=cfg,
                file_path=file_path,
                line=line,
                character=character,
                include_declaration=include_declaration,
                limit=limit,
                include_snippet=include_snippet,
            )
        except LanguageServerNotAvailableError as e:
            return {"error": e.reason, "language": e.language, "install_hint": e.install_hint}
        except Exception as e:
            logger.error(f"Error in find_references: {e}")
            return {"error": str(e)}

    # 4. rename_symbol
    @app.tool(
        name="rename_symbol",
        description=(
            "Rename a symbol across all workspace files via LSP. "
            "By default (apply=False), generates and returns a unified preview diff without modifying files. "
            "Requires apply=True AND writeChanges enabled in config to actually write changes to disk."
        ),
    )
    async def rename_symbol(
        file_path: str,
        line: int,
        character: int,
        new_name: str,
        apply: bool = False,
    ) -> dict[str, Any]:
        """Rename a symbol and preview/apply workspace changes."""
        try:
            return await rename_symbol_tool(
                manager=manager,
                config=cfg,
                file_path=file_path,
                line=line,
                character=character,
                new_name=new_name,
                apply=apply,
            )
        except LanguageServerNotAvailableError as e:
            return {"error": e.reason, "language": e.language, "install_hint": e.install_hint}
        except Exception as e:
            logger.error(f"Error in rename_symbol: {e}")
            return {"error": str(e)}

    # 5. document_symbols
    @app.tool(
        name="document_symbols",
        description=(
            "Retrieve outline of classes, methods, functions, and properties in a file. "
            "Use to quickly understand file architecture without reading all lines."
        ),
    )
    async def document_symbols(
        file_path: str,
        query: Optional[str] = None,
    ) -> dict[str, Any]:
        """List symbols in a document, optionally filtering by name."""
        try:
            return await document_symbols_tool(
                manager=manager,
                config=cfg,
                file_path=file_path,
                query=query,
            )
        except LanguageServerNotAvailableError as e:
            return {"error": e.reason, "language": e.language, "install_hint": e.install_hint}
        except Exception as e:
            logger.error(f"Error in document_symbols: {e}")
            return {"error": str(e)}

    # 6. workspace_symbols
    @app.tool(
        name="workspace_symbols",
        description=(
            "Search for classes, methods, interfaces, and variables across the entire workspace. "
            "Much faster and more accurate than text search."
        ),
    )
    async def workspace_symbols(
        query: str,
        limit: Optional[int] = None,
    ) -> dict[str, Any]:
        """Search workspace symbols matching query."""
        try:
            return await workspace_symbols_tool(
                manager=manager,
                config=cfg,
                query=query,
                limit=limit,
            )
        except LanguageServerNotAvailableError as e:
            return {"error": e.reason, "language": e.language, "install_hint": e.install_hint}
        except Exception as e:
            logger.error(f"Error in workspace_symbols: {e}")
            return {"error": str(e)}

    # 7. hover
    @app.tool(
        name="hover",
        description=(
            "Inspect type definitions, documentation strings, and signatures at a cursor position. "
            "Use to check parameter types, return values, and docstrings."
        ),
    )
    async def hover(
        file_path: str,
        line: int,
        character: int,
    ) -> dict[str, Any]:
        """Hover over symbol to get documentation and type info."""
        try:
            return await hover_tool(
                manager=manager,
                config=cfg,
                file_path=file_path,
                line=line,
                character=character,
            )
        except LanguageServerNotAvailableError as e:
            return {"error": e.reason, "language": e.language, "install_hint": e.install_hint}
        except Exception as e:
            logger.error(f"Error in hover: {e}")
            return {"error": str(e)}

    # 8. prepare_call_hierarchy
    @app.tool(
        name="prepare_call_hierarchy",
        description=(
            "Prepare a function or method for call hierarchy inspection. Verifies if the symbol supports call graphs."
        ),
    )
    async def prepare_call_hierarchy(
        file_path: str,
        line: int,
        character: int,
    ) -> dict[str, Any]:
        """Prepare call hierarchy item for a symbol."""
        try:
            return await prepare_call_hierarchy_tool(
                manager=manager,
                config=cfg,
                file_path=file_path,
                line=line,
                character=character,
            )
        except LanguageServerNotAvailableError as e:
            return {"error": e.reason, "language": e.language, "install_hint": e.install_hint}
        except Exception as e:
            logger.error(f"Error in prepare_call_hierarchy: {e}")
            return {"error": str(e)}

    # 8b. call_hierarchy
    @app.tool(
        name="call_hierarchy",
        description=(
            "Trace caller/callee relationships for a function or method. "
            "direction='incoming' returns callers; direction='outgoing' returns called functions."
        ),
    )
    async def call_hierarchy(
        file_path: str,
        line: int,
        character: int,
        direction: str = "incoming",
    ) -> dict[str, Any]:
        """Find callers (incoming) or called functions (outgoing)."""
        try:
            return await call_hierarchy_tool(
                manager=manager,
                config=cfg,
                file_path=file_path,
                line=line,
                character=character,
                direction=direction,
            )
        except LanguageServerNotAvailableError as e:
            return {"error": e.reason, "language": e.language, "install_hint": e.install_hint}
        except Exception as e:
            logger.error(f"Error in call_hierarchy: {e}")
            return {"error": str(e)}

    # 9. get_type_hierarchy
    @app.tool(
        name="get_type_hierarchy",
        description=(
            "Inspect class and interface inheritance hierarchy. "
            "direction='supertypes' returns base classes/interfaces; direction='subtypes' returns derived types."
        ),
    )
    async def get_type_hierarchy(
        file_path: str,
        line: int,
        character: int,
        direction: str = "supertypes",
    ) -> dict[str, Any]:
        """Inspect inheritance hierarchy (supertypes or subtypes)."""
        try:
            return await get_type_hierarchy_tool(
                manager=manager,
                config=cfg,
                file_path=file_path,
                line=line,
                character=character,
                direction=direction,
            )
        except LanguageServerNotAvailableError as e:
            return {"error": e.reason, "language": e.language, "install_hint": e.install_hint}
        except Exception as e:
            logger.error(f"Error in get_type_hierarchy: {e}")
            return {"error": str(e)}

    # 10. lsp_status
    @app.tool(
        name="lsp_status",
        description=(
            "Show status of all Language Server processes, active workspace root, "
            "process IDs, restart counts, and error summaries."
        ),
    )
    async def lsp_status() -> dict[str, Any]:
        """Show language server and bridge health status."""
        try:
            return await lsp_status_tool(manager=manager, config=cfg)
        except Exception as e:
            logger.error(f"Error in lsp_status: {e}")
            return {"error": str(e)}

    return app, manager, cfg


async def run_server_async(config: Optional[PluginConfig] = None) -> None:
    """Run the MCP server over stdio asynchronously."""
    app, manager, _ = create_server(config)

    def _cleanup():
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(manager.shutdown_all())

    atexit.register(_cleanup)

    logger.info("Starting agy-lsp MCP server over stdio...")
    try:
        await app.run_stdio_async()
    finally:
        await manager.shutdown_all()


def main() -> None:
    """CLI entry point for the agy-lsp MCP server."""
    try:
        asyncio.run(run_server_async())
    except (KeyboardInterrupt, SystemExit):
        pass
    except Exception as e:
        logger.critical(f"Fatal server failure: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
