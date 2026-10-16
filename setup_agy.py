"""One-step setup helper for agy-lsp in Antigravity workspaces.

Resolves the installation friction points:
1. Detects the exact absolute path to the virtualenv `agy-lsp` binary and `.venv/Scripts` directory.
2. Updates `~/.gemini/config/mcp_config.json` (or prints the snippet) with absolute paths so `agy-lsp` works even when `.venv` is not on the global system PATH.
3. Copies the `SKILL.md` and `AGENTS.md` rule into `<workspace>/.agents/` without creating a duplicate `mcp_config.json` inside `.agents/plugins/agy-lsp/` (which otherwise registers a duplicate `agy-lsp_agy-lsp` MCP server).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path


def get_venv_scripts_dir() -> Path:
    return Path(sys.executable).resolve().parent


def get_agy_lsp_command() -> tuple[str, list[str]]:
    scripts_dir = get_venv_scripts_dir()
    exe_name = "agy-lsp.exe" if os.name == "nt" else "agy-lsp"
    candidate = scripts_dir / exe_name
    if candidate.is_file():
        return str(candidate), []
    return str(Path(sys.executable).resolve()), ["-m", "agy_lsp.server"]


def build_mcp_entry(workspace_root: Path) -> dict:
    cmd, args = get_agy_lsp_command()
    scripts_dir = str(get_venv_scripts_dir())
    env = {
        "AGY_LSP_WORKSPACE": str(workspace_root.resolve()),
        "PYTHONUNBUFFERED": "1",
        "PATH": f"{scripts_dir}{os.pathsep}{os.environ.get('PATH', '')}",
    }
    return {
        "command": cmd,
        "args": args,
        "env": env,
    }


def setup_workspace(workspace_root: Path, update_global_mcp: bool = True) -> dict:
    repo_root = Path(__file__).resolve().parent
    workspace_root = workspace_root.resolve()

    # 1. Copy skill to <workspace>/.agents/skills/agy-lsp/SKILL.md
    skill_src = repo_root / "skills" / "agy-lsp" / "SKILL.md"
    skill_dst = workspace_root / ".agents" / "skills" / "agy-lsp" / "SKILL.md"
    if skill_src.is_file():
        skill_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(skill_src, skill_dst)

    # 2. Remove duplicate .agents/plugins/agy-lsp/mcp_config.json if present
    dup_plugin_mcp = workspace_root / ".agents" / "plugins" / "agy-lsp" / "mcp_config.json"
    removed_dup = False
    if dup_plugin_mcp.is_file():
        dup_plugin_mcp.unlink()
        removed_dup = True

    # 3. Prepare MCP config entry
    mcp_entry = build_mcp_entry(workspace_root)
    global_mcp_path = Path.home() / ".gemini" / "config" / "mcp_config.json"

    if update_global_mcp:
        global_mcp_path.parent.mkdir(parents=True, exist_ok=True)
        if global_mcp_path.is_file():
            try:
                data = json.loads(global_mcp_path.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        else:
            data = {}
        mcp_servers = data.setdefault("mcpServers", {})
        mcp_servers["agy-lsp"] = mcp_entry
        global_mcp_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    return {
        "workspace_root": str(workspace_root),
        "skill_installed": str(skill_dst),
        "removed_duplicate_plugin_mcp": removed_dup,
        "global_mcp_config": str(global_mcp_path) if update_global_mcp else None,
        "mcp_entry": mcp_entry,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Configure agy-lsp for an Antigravity workspace.")
    parser.add_argument(
        "--workspace",
        default=".",
        help="Path to the target project workspace directory (default: current directory).",
    )
    parser.add_argument(
        "--no-global-mcp",
        action="store_true",
        help="Do not write to ~/.gemini/config/mcp_config.json; only print the snippet.",
    )
    args = parser.parse_args()

    result = setup_workspace(Path(args.workspace), update_global_mcp=not args.no_global_mcp)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
