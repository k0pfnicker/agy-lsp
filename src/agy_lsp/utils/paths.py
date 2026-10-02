"""Path utilities for agy-lsp.

Handles path normalization, URI conversions (Windows, macOS, Linux),
workspace root detection, workspace confinement checks, and language detection.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname


def normalize_path(path: str | Path) -> str:
    """Normalize a filesystem path to an absolute, canonical string."""
    p = Path(path).expanduser().resolve()
    path_str = str(p)
    # On Windows, preserve drive letter casing consistently (e.g. C:\...)
    if os.name == "nt" and len(path_str) >= 2 and path_str[1] == ":":
        path_str = path_str[0].upper() + path_str[1:]
    return path_str


def path_to_uri(path: str | Path) -> str:
    """Convert a filesystem path to an RFC-compliant file:// URI."""
    norm = normalize_path(path)
    return Path(norm).as_uri()


def uri_to_path(uri: str) -> str:
    """Convert an RFC-compliant file:// URI back to a native filesystem path."""
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        raise ValueError(f"Unsupported URI scheme: '{parsed.scheme}' (expected 'file')")

    raw_path = unquote(parsed.path)
    os_path = url2pathname(raw_path)
    return normalize_path(os_path)


def is_safe_workspace_path(
    target_path: str | Path,
    workspace_root: str | Path,
    allow_outside: bool = False,
) -> bool:
    """Check if target_path is confined within workspace_root.

    Prevents path traversal or unauthorized outside-workspace access unless allow_outside is True.
    """
    if allow_outside:
        return True

    try:
        target_resolved = Path(normalize_path(target_path))
        workspace_resolved = Path(normalize_path(workspace_root))
        target_resolved.relative_to(workspace_resolved)
        return True
    except (ValueError, Exception):
        return False


def find_workspace_root(start_path: Optional[str | Path] = None) -> str:
    """Find the workspace root by traversing upwards from start_path (or current directory)
    looking for project indicators (.git, .sln, pyproject.toml, package.json, etc.).
    """
    current = Path(normalize_path(start_path or Path.cwd()))

    markers = [
        ".git",
        "pyproject.toml",
        "setup.py",
        "package.json",
        "tsconfig.json",
        "CMakeLists.txt",
        "compile_commands.json",
        "Cargo.toml",
        "go.mod",
    ]

    check_dir = current
    while True:
        for marker in markers:
            if (check_dir / marker).exists():
                return normalize_path(check_dir)

        try:
            if list(check_dir.glob("*.sln")) or list(check_dir.glob("*.csproj")):
                return normalize_path(check_dir)
        except (OSError, PermissionError):
            pass

        parent = check_dir.parent
        if parent == check_dir:
            break
        check_dir = parent

    return normalize_path(current)


EXTENSION_LANGUAGE_MAP: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".cs": "csharp",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".c": "cpp",
    ".h": "cpp",
    ".hpp": "cpp",
    ".hxx": "cpp",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "typescript",
    ".jsx": "typescript",
    ".mjs": "typescript",
    ".cjs": "typescript",
}


def detect_language_from_path(file_path: str | Path) -> Optional[str]:
    """Detect language identifier ('python', 'csharp', 'cpp', 'typescript') from file extension."""
    suffix = Path(file_path).suffix.lower()
    return EXTENSION_LANGUAGE_MAP.get(suffix)
