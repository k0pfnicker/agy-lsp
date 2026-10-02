"""Tests for path normalization, URI handling, workspace security, and language detection."""

import os
from pathlib import Path

from agy_lsp.utils.paths import (
    detect_language_from_path,
    find_workspace_root,
    is_safe_workspace_path,
    normalize_path,
    path_to_uri,
    uri_to_path,
)


def test_normalize_path(tmp_path: Path):
    sub = tmp_path / "subdir" / "file.txt"
    norm = normalize_path(sub)
    assert Path(norm).is_absolute()
    if os.name == "nt":
        assert norm[1] == ":"
        assert norm[0].isupper()


def test_uri_roundtrip(tmp_path: Path):
    test_file = tmp_path / "hello world.py"
    test_file.touch()

    uri = path_to_uri(test_file)
    assert uri.startswith("file://")
    assert "%20" in uri or "hello" in uri

    recovered = uri_to_path(uri)
    assert normalize_path(recovered) == normalize_path(test_file)


def test_is_safe_workspace_path(tmp_path: Path):
    ws_root = tmp_path / "workspace"
    ws_root.mkdir()
    inside = ws_root / "src" / "main.py"
    outside = tmp_path / "secret.txt"

    assert is_safe_workspace_path(inside, ws_root, allow_outside=False) is True
    assert is_safe_workspace_path(outside, ws_root, allow_outside=False) is False
    assert is_safe_workspace_path(outside, ws_root, allow_outside=True) is True

    # Traversal test
    traversal = ws_root / ".." / "secret.txt"
    assert is_safe_workspace_path(traversal, ws_root, allow_outside=False) is False


def test_find_workspace_root(sample_python_dir: Path):
    nested = sample_python_dir / "deep" / "nested"
    nested.mkdir(parents=True, exist_ok=True)

    root = find_workspace_root(nested)
    assert normalize_path(root) == normalize_path(sample_python_dir)


def test_detect_language_from_path():
    assert detect_language_from_path("foo/bar.py") == "python"
    assert detect_language_from_path("foo/bar.pyi") == "python"
    assert detect_language_from_path("C:/src/App.cs") == "csharp"
    assert detect_language_from_path("src/main.cpp") == "cpp"
    assert detect_language_from_path("include/header.hpp") == "cpp"
    assert detect_language_from_path("frontend/app.ts") == "typescript"
    assert detect_language_from_path("frontend/component.tsx") == "typescript"
    assert detect_language_from_path("frontend/bundle.js") == "typescript"
    assert detect_language_from_path("data.json") is None
    assert detect_language_from_path("README.md") is None
