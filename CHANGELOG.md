# Changelog

All notable changes to **agy-lsp** are documented in this file.

## [1.1.0] - 2026-10-16

### Added
- **One-Step Setup Helper (`setup_agy.py`)**: Automatically detects `.venv` executable paths, updates `~/.gemini/config/mcp_config.json`, installs `.agents/skills/agy-lsp/SKILL.md`, and removes duplicate plugin `mcp_config.json` entries.
- **Zero-Config `.venv` Auto-Bootstrapping (`run_server.py`)**: Automatically creates `.venv` and installs dependencies on first launch when installed via `agy plugin install .`, and injects `.venv/Scripts` (or `.venv/bin`) into `PATH`.
- **Smart Column Auto-Snapping (`resolve_symbol_position`)**: Position-based tools (`go_to_definition`, `find_references`, `hover`, `rename_symbol`, `prepare_call_hierarchy`, `call_hierarchy`, `get_type_hierarchy`) now automatically snap inaccurate LLM column estimates (`character`) or an optional `symbol_name` parameter to the actual identifier on the target line, with automatic fallback retry across candidate identifiers on the line.
- **Token-Compact `document_symbols` (`include_fields`, `max_depth`)**: Collapses C/C++ struct fields (`Field`) and enum constants (`EnumMember`) into `"fields_count": N` by default, reducing JSON payload size by >80% on large header/source files while preserving `include_fields=True` for full expansion.
- **Automatic `clangd` `--compile-commands-dir` Discovery**: Searches the workspace and build subdirectories (`build`, `out`, `07_build`, etc.) for `compile_commands.json` and passes `--compile-commands-dir=<dir>` to `clangd` automatically.
- **Zero-Admin C/C++ LSP Hint**: Added `pip install clangd` wheel installation instructions alongside system package managers.

### Fixed
- **Event-Driven `get_diagnostics` Synchronization**: Replaced the static `200ms` sleep after `textDocument/didOpen` and `textDocument/didChange` with per-URI `asyncio.Event` signaling on `textDocument/publishDiagnostics`, eliminating empty diagnostic results on initial file open.
- **Workspace Root Discovery (`AGY_LSP_WORKSPACE`)**: `load_config()` now honors the `AGY_LSP_WORKSPACE` environment variable and recognizes `.slnx`, `.vcxproj`, and `agy-lsp.json` markers.

## [1.0.0] - 2026-03-31

### Added
- Initial release of **agy-lsp** MCP Bridge for Google Antigravity CLI (`agy`).
- 11 MCP tools: `get_diagnostics`, `go_to_definition`, `find_references`, `rename_symbol`, `document_symbols`, `workspace_symbols`, `hover`, `prepare_call_hierarchy`, `call_hierarchy`, `get_type_hierarchy`, and `lsp_status`.
- Multi-language support for Python (`pyright-langserver`, `pylsp`), C/C++ (`clangd`, `ccls`), C# (`csharp-ls`, `roslyn-language-server`), and TypeScript/JavaScript (`typescript-language-server`, `vtsls`).
