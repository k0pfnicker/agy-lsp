"""Pytest configuration and shared fixtures for agy-lsp tests."""

from pathlib import Path

import pytest

from agy_lsp.config import PluginConfig
from agy_lsp.utils.paths import normalize_path


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_python_dir(fixtures_dir: Path) -> Path:
    return fixtures_dir / "sample_python_project"


@pytest.fixture
def sample_python_file(sample_python_dir: Path) -> Path:
    return sample_python_dir / "sample.py"


@pytest.fixture
def sample_cs_file(fixtures_dir: Path) -> Path:
    return fixtures_dir / "sample_cs_project" / "Sample.cs"


@pytest.fixture
def test_config(sample_python_dir: Path) -> PluginConfig:
    cfg = PluginConfig()
    cfg.workspaceRoot = normalize_path(sample_python_dir)
    cfg.allowOutsideWorkspace = False
    cfg.writeChanges = False
    cfg.includeCodeSnippets = True
    cfg.maxResults = 50
    return cfg
