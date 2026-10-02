# Agent Guidelines for Language Server Protocol (LSP) Tools

When working with code in supported languages (Python, C#, C/C++, TypeScript/JavaScript), adhere to the following best practices:

## 1. Precise Navigation Over Whole-File Reading
- **Do not read entire files** when searching for where a function, class, or method is declared or used.
- Call `go_to_definition(file_path, line, character)` to jump directly to declarations.
- Call `find_references(file_path, line, character)` to inspect usages across the workspace before changing APIs.
- Use `document_symbols(file_path)` to get an instant outline of classes, methods, and fields without wasting context tokens on full file contents.

## 2. Mandatory Diagnostics Verification Loop
- **After making code edits**, always call `get_diagnostics(file_path)` on modified files.
- Verify that no new syntax errors, type mismatches, or missing imports were introduced.
- If errors are reported, fix them immediately before concluding the turn.

## 3. Safe Refactoring and Symbol Renaming
- `rename_symbol` executes as a **preview diff** by default (`apply=False`).
- Always inspect the generated diff to verify that all affected call sites and declaration points are accurately updated.
- Only apply changes to disk when explicitly intended by setting `apply=True` (and ensuring write changes is allowed).

## 4. Context & Token Conservation
- Keep queries focused and use `limit` parameters for symbols or references when exploring large codebases.
- Use `hover(file_path, line, character)` to inspect type signatures and docstrings without reading implementation details.
