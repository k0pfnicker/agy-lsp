#!/usr/bin/env python3
"""Runner script for agy-lsp MCP Server.

Ensures the plugin's local .venv (if present) is used and src/ is added to sys.path.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# Add src to sys.path
root_dir = Path(__file__).resolve().parent
src_dir = root_dir / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

# Check if we should bootstrap or re-exec into local .venv python
venv_dir = root_dir / ".venv"
bin_dir = venv_dir / ("Scripts" if os.name == "nt" else "bin")
venv_py = bin_dir / ("python.exe" if os.name == "nt" else "python")

if not venv_py.is_file() and "AGY_LSP_VENV_ACTIVE" not in os.environ:
    try:
        import mcp  # noqa: F401
    except ImportError:
        sys.stderr.write("[agy-lsp] Bootstrapping local .venv and installing dependencies...\n")
        try:
            subprocess.check_call([sys.executable, "-m", "venv", str(venv_dir)], stdout=sys.stderr, stderr=sys.stderr)
            subprocess.check_call(
                [str(venv_py), "-m", "pip", "install", "--quiet", "-e", str(root_dir)],
                stdout=sys.stderr,
                stderr=sys.stderr,
            )
        except Exception as exc:
            sys.stderr.write(f"[agy-lsp] Auto-bootstrap failed: {exc}\n")

if venv_py.is_file() and "AGY_LSP_VENV_ACTIVE" not in os.environ:
    if Path(sys.executable).resolve() != venv_py.resolve():
        env = os.environ.copy()
        env["AGY_LSP_VENV_ACTIVE"] = "1"
        env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
        try:
            res = subprocess.call([str(venv_py), str(Path(__file__).resolve())] + sys.argv[1:], env=env)
            sys.exit(res)
        except Exception:
            pass  # Fall back to current python

# Also ensure bin_dir is in PATH when already running inside .venv
if bin_dir.is_dir() and str(bin_dir) not in os.environ.get("PATH", ""):
    os.environ["PATH"] = f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"

from agy_lsp.server import main  # noqa: E402

if __name__ == "__main__":
    main()
