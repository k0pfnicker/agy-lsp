---
name: agy-lsp
description: >-
  Provides Language Server Protocol (LSP) workflows for semantic code navigation,
  diagnostics verification, symbol search, hover inspection, call hierarchy, and safe renaming.
  Activate this skill when investigating compiler/type errors, navigating definitions/references,
  or refactoring code across multiple files.
---

# agy-lsp: Language Server Workflows

This skill guides the agent on how to effectively leverage Language Server Protocol (LSP) tools
provided by the `agy-lsp` plugin.

---

## 1. Diagnostics & Verification Workflow

Whenever code is written or modified:

1. **Query Diagnostics**:
   Call `get_diagnostics(file_path="path/to/file")`.
2. **Analyze Output**:
   - Filter by `severity="Error"` to address compile-breaking problems first.
   - Note the exact line and column of the reported diagnostic.
3. **Verify Clean State**:
   After applying fixes, run `get_diagnostics(file_path="path/to/file")` again to ensure zero errors remain.

---

## 2. Refactoring & Symbol Rename Workflow

When renaming functions, classes, or variables:

1. **Find Usages First**:
   Call `find_references(file_path, line, character)` to inspect all call sites across the workspace.
2. **Dry-Run Rename**:
   Call `rename_symbol(file_path, line, character, new_name="NewName", apply=False)`.
3. **Inspect the Unified Diff**:
   Check the returned preview diff to ensure the rename is clean and no unintended symbols were matched.
4. **Apply Changes**:
   Once confirmed, execute `rename_symbol(..., apply=True)`.
5. **Post-Refactor Diagnostics**:
   Call `get_diagnostics()` across affected files to ensure the workspace compiles cleanly.

---

## 3. Semantic Code Exploration

To understand unfamiliar codebases without consuming large token budgets:

- **Quick File Outline**: Call `document_symbols(file_path)`.
- **Search Project Symbols**: Call `workspace_symbols(query="MyClass")`.
- **Type / Signature Inspection**: Call `hover(file_path, line, character)` to check docstrings and parameter types.
- **Trace Callers & Callees**: Call `call_hierarchy(file_path, line, character, direction="incoming")`.
- **Inheritance Hierarchy**: Call `get_type_hierarchy(file_path, line, character, direction="supertypes")`.

---

## 4. Troubleshooting Server Connections

If a tool reports that a language server is unavailable:
1. Run `lsp_status()` to inspect process states, paths, and error messages.
2. Check if the required server is installed:
   - Python: `pip install pyright` or `pip install python-lsp-server`
   - C#: `dotnet tool install -g csharp-ls`
   - C/C++: `scoop install llvm` (clangd)
   - TypeScript: `npm install -g typescript-language-server typescript`
3. Custom server commands can be configured in `agy-lsp.json` at the root of the workspace.
