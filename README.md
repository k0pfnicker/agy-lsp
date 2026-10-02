# agy-lsp — Language Server Protocol MCP Bridge for Antigravity CLI

[![Tests](https://img.shields.io/badge/tests-37%20passed-brightgreen.svg)]()
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-blue.svg)]()
[![MCP](https://img.shields.io/badge/MCP-2.0%20%2F%201.0-orange.svg)]()
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

*Read this in other languages: [English](README.md) | [Deutsch](README.de.md)*

**agy-lsp** is a production-ready, professional plugin for the **Google Antigravity CLI (`agy`)**. It connects AI coding agents to native **Language Servers (LSP)** for C#, C/C++, TypeScript/JavaScript, and Python via the standardized **Model Context Protocol (MCP)**.

---

## Table of Contents

1. [Purpose & Benefits](#purpose--benefits)
2. [Architecture](#architecture)
3. [MCP Tools Overview](#mcp-tools-overview)
4. [Supported Languages & Language Servers](#supported-languages--language-servers)
5. [Prerequisites](#prerequisites)
6. [Installation & Quickstart](#installation--quickstart)
   - [Windows](#windows)
   - [Linux / macOS](#linux--macos)
7. [Integration into Antigravity CLI](#integration-into-antigravity-cli)
8. [Language Server Installation](#language-server-installation)
9. [Configuration (`agy-lsp.json`)](#configuration-agy-lspjson)
10. [Token Efficiency & Context Optimization](#token-efficiency--context-optimization)
11. [Security Model](#security-model)
12. [Troubleshooting & Diagnostics](#troubleshooting--diagnostics)
13. [Development, Testing & QA](#development-testing--qa)
14. [Adding New Languages](#adding-new-languages)
15. [Known Limitations](#known-limitations)
16. [License](#license)

---

## 1. Purpose & Benefits

Large Language Models (LLMs) often face two major challenges when working in real-world software codebases:
1. **Inaccurate Search & Context Waste:** Plaintext keyword search and reading entire files consumes thousands of context tokens while frequently missing semantic relationships (such as method overloads, polymorphism, interface implementations, and namespaces).
2. **Missing Feedback Loops:** After modifying code, agents often fail to notice syntax, type-checking, or import errors until much later or not at all.

**agy-lsp** bridges this gap by giving the Antigravity agent direct compiler and type intelligence via standardized MCP tools:
- **Precise Symbol Navigation:** Jump to definitions and query all workspace references without guessing.
- **Automated Quality Control:** Fetch compiler diagnostics (errors, warnings, hints) immediately after edits.
- **Safe Refactoring:** Symbol renaming generates a unified preview diff before any changes are written to disk.
- **Minimized Token Usage:** Compact snippets, structural document outlines, and strict result limits prevent context bloat.

---

## 2. Architecture

```text
┌─────────────────────────────────────────────────────────────┐
│                    Antigravity CLI (agy)                    │
│                                                             │
│   Agent Turn / Reasoning ◄──► Skills / AGENTS.md Rules      │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              │ Stdio Transport (JSON-RPC)
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                  agy-lsp (MCP-Server)                       │
│                                                             │
│  ├── Tool Schemas (get_diagnostics, go_to_definition, ...)  │
│  ├── Document Sync (didOpen, didChange, didClose, Cache)    │
│  ├── Token Reducer (Snippet extraction, Dedup, Limits)      │
│  └── Workspace Confinement Security Check                   │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              │ Async Process I/O (Content-Length Framing)
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   Language Server (LSP)                     │
│                                                             │
│   [Python]       [C#]             [C / C++]      [TS / JS]  │
│   pyright /      csharp-ls /      clangd         typescript-│
│   pylsp          Roslyn Server                   language-  │
│                                                  server     │
└─────────────────────────────────────────────────────────────┘
```

The bridge launches Language Server processes **on demand (lazy loading)** only when a tool targets a file belonging to that language. Running processes are reused throughout the session and automatically recovered with bounded retries if a crash occurs.

---

## 3. MCP Tools Overview

The plugin registers 11 high-performance MCP tools:

| Tool | Purpose | Key Parameters | Return Value |
| :--- | :--- | :--- | :--- |
| `get_diagnostics` | Retrieve compiler errors, warnings, and hints for a file or workspace | `file_path`, `line_start`, `line_end`, `severity`, `limit` | List of deduplicated diagnostics with file, line, column, code, and message. |
| `go_to_definition` | Jump from a symbol position to its definition/declaration | `file_path`, `line`, `character`, `include_snippet` | Target file, line range, and optional compact code excerpt. |
| `find_references` | Locate all usages of a symbol across the workspace | `file_path`, `line`, `character`, `include_declaration`, `limit` | List of reference locations across files. |
| `rename_symbol` | Perform workspace-wide LSP rename refactoring | `file_path`, `line`, `character`, `new_name`, `apply` | **Unified preview diff** across all affected files. Disk writes require `apply=True` and `writeChanges=True`. |
| `document_symbols` | Structural outline of classes, methods, and properties | `file_path`, `query` | Symbol tree with kind, line ranges, and identifiers. |
| `workspace_symbols` | Search symbols across the entire project | `query`, `limit` | Matches with symbol name, kind, file, and position. |
| `hover` | Inspect signatures, types, and docstrings | `file_path`, `line`, `character` | Markdown-formatted hover information. |
| `prepare_call_hierarchy` | Verify support and return call hierarchy root item | `file_path`, `line`, `character` | Prepared symbol item for call graphs. |
| `call_hierarchy` | Find callers (`incoming`) or called functions (`outgoing`) | `file_path`, `line`, `character`, `direction` | List of callers or callee functions. |
| `get_type_hierarchy` | Inspect base types (`supertypes`) or derived classes (`subtypes`) | `file_path`, `line`, `character`, `direction` | Type inheritance hierarchy. |
| `lsp_status` | Health status of all servers, workspace root, and errors | *none* | JSON overview of server states (`RUNNING`, `AVAILABLE`, `NOT_INSTALLED`, `CRASHED`), PID, and root. |

*Note:* All line and column arguments and outputs are **1-indexed** for agent ergonomics.

---

## 4. Supported Languages & Language Servers

| Language | Primary Server | File Extensions | Project Discovery Markers |
| :--- | :--- | :--- | :--- |
| **Python** | `pyright-langserver` *(Fallbacks: `pylsp`, `pyright`)* | `.py`, `.pyi` | `pyproject.toml`, `setup.py`, `requirements.txt` |
| **C#** | `csharp-ls` *(Fallback: `roslyn-language-server`)* | `.cs` | `*.sln`, `*.csproj` |
| **C / C++** | `clangd` *(Fallback: `ccls`)* | `.c`, `.cpp`, `.cc`, `.cxx`, `.h`, `.hpp`, `.hxx` | `CMakeLists.txt`, `compile_commands.json` |
| **TypeScript / JS**| `typescript-language-server` *(Fallback: `vtsls`)* | `.ts`, `.tsx`, `.js`, `.jsx`, `.mjs`, `.cjs` | `package.json`, `tsconfig.json` |

---

## 5. Prerequisites

- **Operating System:** Windows 10/11, macOS, or Linux.
- **Python:** Python 3.9 or higher (Python 3.14+ fully supported).
- **Antigravity CLI:** `agy` installed.
- The corresponding language server for the language you wish to inspect (e.g. `pylsp` or `pyright` for Python, `clangd` for C++, etc.).

---

## 6. Installation & Quickstart

### Windows

```powershell
# 1. Clone and enter the repository
git clone git@github-personal:k0pfnicker/agy-lsp.git
cd agy-lsp

# 2. Create virtual environment and install dependencies
python -m venv .venv
.\.venv\Scripts\pip.exe install -e .

# 3. Optional: Install Python language server for immediate out-of-the-box support
.\.venv\Scripts\pip.exe install python-lsp-server
```

### Linux / macOS

```bash
# 1. Clone and enter the repository
git clone git@github.com:k0pfnicker/agy-lsp.git
cd agy-lsp

# 2. Create virtual environment and install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# 3. Optional: Install Python language server
pip install python-lsp-server
```

---

## 7. Integration into Antigravity CLI

### Option A: As a Discovered Plugin (Recommended)

The plugin adheres strictly to the official Antigravity plugin manifest specifications (`plugin.json` and `mcp_config.json`).

Link or copy the directory into an Antigravity plugin discovery folder:
- **Global:** `~/.gemini/config/plugins/agy-lsp`
- **Project-Specific:** `.agents/plugins/agy-lsp`

Validate the plugin with the official CLI command:
```bash
agy plugin validate .
```
Expected output:
```text
  [ok]    .
          ✔ skills      : 1 processed
          ✔ mcpServers  : 1 processed
```

### Option B: Via `agy mcp` Command Line

Register the server directly using the CLI:
```bash
agy mcp add agy-lsp -- command="python" args=["/path/to/agy-lsp/run_server.py"]
```

---

## 8. Language Server Installation

If a language server is not installed, the plugin provides a clear, user-friendly error message with actionable installation commands:

### Python
```bash
# Option 1: python-lsp-server (pure Python, no Node.js required)
pip install python-lsp-server

# Option 2: Pyright
npm install -g pyright
```

### C# (.NET)
```bash
dotnet tool install -g csharp-ls
```

### C / C++
- **Windows:** `scoop install llvm` or `winget install LLVM.LLVM`
- **macOS:** `brew install llvm`
- **Linux (Debian/Ubuntu):** `sudo apt-get install clangd`

### TypeScript / JavaScript
```bash
npm install -g typescript-language-server typescript
```

---

## 9. Configuration (`agy-lsp.json`)

`agy-lsp` works out of the box with safe defaults. To customize behavior, place an `agy-lsp.json` file at your workspace root or under `~/.gemini/config/agy-lsp.json`:

```json
{
  "defaultLanguage": "auto",
  "workspaceRoot": null,
  "maxResults": 50,
  "includeCodeSnippets": false,
  "snippetContextLines": 3,
  "allowOutsideWorkspace": false,
  "writeChanges": false,
  "serverStartupTimeoutMs": 15000,
  "requestTimeoutMs": 10000,
  "maxRestartAttempts": 2,
  "servers": {
    "csharp": {
      "command": "csharp-ls",
      "args": []
    },
    "cpp": {
      "command": "clangd",
      "args": ["--background-index"]
    },
    "typescript": {
      "command": "typescript-language-server",
      "args": ["--stdio"]
    },
    "python": {
      "command": "pyright-langserver",
      "args": ["--stdio"],
      "fallbacks": [
        { "command": "pylsp", "args": [] }
      ]
    }
  }
}
```

### Configuration Options Reference

| Key | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `defaultLanguage` | `string` | `"auto"` | Fallback language for files with unrecognized extensions. |
| `workspaceRoot` | `string \| null` | `null` | Explicit workspace root. If `null`, discovered automatically via `.git`, `.sln`, etc. |
| `maxResults` | `integer` | `50` | Maximum number of diagnostics, references, or symbols returned. |
| `includeCodeSnippets` | `boolean` | `false` | Whether to include code snippets with definition and reference locations. |
| `snippetContextLines` | `integer` | `3` | Number of context lines before and after target line in snippets. |
| `allowOutsideWorkspace` | `boolean` | `false` | **Security boundary:** Forbids accessing paths outside the workspace root. |
| `writeChanges` | `boolean` | `false` | **Write protection:** Enables writing rename refactorings directly to disk. |
| `serverStartupTimeoutMs`| `integer` | `15000` | Timeout in milliseconds for LSP process initialization handshake. |
| `requestTimeoutMs` | `integer` | `10000` | Timeout in milliseconds for individual LSP JSON-RPC requests. |
| `maxRestartAttempts` | `integer` | `2` | Maximum retry attempts when a server process crashes unexpectedly. |

---

## 10. Token Efficiency & Context Optimization

To prevent context bloat and optimize LLM token consumption, `agy-lsp` incorporates several efficiency mechanisms:

1. **No Full File Dumps:** Returns precise coordinates or compact snippets (default: 3 lines context) instead of entire files.
2. **Diagnostic Deduplication:** Merges redundant diagnostic reports at identical file locations.
3. **Message Truncation:** Overly verbose compiler error messages are truncated at 400 characters (`... [truncated]`).
4. **Result Limiting & Pagination:** Result lists are capped at `maxResults` and annotated with a `truncated: true` flag and total count.
5. **Compact Structure:** Omits empty optional keys and null values.

---

## 11. Security Model

- **Workspace Confinement:** All file paths are canonicalized (`resolve()`). Accessing files outside the workspace root is rejected unless `allowOutsideWorkspace: true` is set. Path traversal attacks (`../../`) are blocked.
- **No Shell Execution:** Subprocesses are launched directly using `asyncio.create_subprocess_exec` without a shell (`shell=False`).
- **Static Command Allowlist:** Server commands are loaded strictly from static configuration or defaults, never from dynamic agent tool arguments.
- **Secret Redaction:** Stderr logs automatically redact bearer tokens, API keys, and passwords.
- **Stderr Isolation:** All diagnostic logs are routed strictly to `sys.stderr`, preserving clean JSON-RPC communication on `sys.stdout`.

---

## 12. Troubleshooting & Diagnostics

### Checking Server Health
Invoke the `lsp_status` tool through the agent or MCP:
```json
{
  "name": "lsp_status",
  "arguments": {}
}
```
Output details:
- Status per language (`RUNNING`, `AVAILABLE`, `NOT_INSTALLED`, `CRASHED`),
- Process ID (PID) and workspace root,
- Detailed error messages and installation advice if a binary is missing.

### Error: "Language server command '...' was not found"
Ensure the language server is installed and available in `PATH`, or specify its absolute executable path in `agy-lsp.json`:
```json
{
  "servers": {
    "csharp": {
      "command": "C:/Users/<User>/.dotnet/tools/csharp-ls.exe"
    }
  }
}
```

---

## 13. Development, Testing & QA

### Running the Test Suite

The test suite contains 37 automated tests across unit, integration, and end-to-end categories:

```powershell
# Run all tests
.\.venv\Scripts\pytest.exe -v

# Run the real LSP process E2E test
.\.venv\Scripts\pytest.exe tests/test_e2e_real_lsp.py -v
```

### Linting & Formatting Check
```powershell
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\ruff.exe format --check .
```

### Plugin Manifest Validation
```powershell
agy plugin validate .
```

---

## 14. Adding New Languages

To add a new language server (e.g. Rust via `rust-analyzer` or Go via `gopls`):

1. **Map file extensions:** In [`paths.py`](src/agy_lsp/utils/paths.py) in `EXTENSION_LANGUAGE_MAP`:
   ```python
   ".rs": "rust",
   ".go": "go",
   ```
2. **Register default server:** In [`config.py`](src/agy_lsp/config.py) in `DEFAULT_SERVERS`:
   ```python
   "rust": ServerConfig(command="rust-analyzer", args=[]),
   "go": ServerConfig(command="gopls", args=["serve"]),
   ```
3. **Add installation hint:** In [`adapters.py`](src/agy_lsp/lsp/adapters.py) in `INSTALL_HINTS`.

Alternatively, configure new languages purely declaratively in `agy-lsp.json` without modifying source code!

---

## 15. Known Limitations

- **C# on Modern .NET Previews:** On .NET 10 Preview environments, `dotnet tool install -g csharp-ls` may encounter packaging manifest issues. Configure an alternative Roslyn server path in `agy-lsp.json` if needed.
- **Multiple Workspace Roots:** The bridge currently targets one primary workspace root per session. Submodules and subfolders within the root are fully supported.
- **C/C++ Semantic Macro Expansion:** `clangd` yields optimal results when a `compile_commands.json` database is present in the workspace root.

---

## 16. License

This project is licensed under the [MIT License](LICENSE).
