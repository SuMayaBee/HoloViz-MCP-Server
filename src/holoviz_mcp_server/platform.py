"""Platform utilities — Windows DLL path handling."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

_DLL_DIR_HANDLES: dict[str, Any] = {}


def prepend_env_dll_paths(env: dict[str, str]) -> dict[str, str]:
    """Prepend conda/pixi environment DLL directories to PATH (Windows only)."""
    if sys.platform != "win32":
        return env

    env_root = Path(sys.executable).resolve().parent
    candidate_dirs = [
        env_root,
        env_root / "Scripts",
        env_root / "Library" / "bin",
        env_root / "DLLs",
    ]

    existing_path = env.get("PATH", "")
    existing_entries: set[str] = set(existing_path.split(os.pathsep)) if existing_path else set()

    new_prefixes = [str(d) for d in candidate_dirs if d.exists() and str(d) not in existing_entries]
    if new_prefixes:
        env["PATH"] = os.pathsep.join(new_prefixes + ([existing_path] if existing_path else []))

    add_dll = getattr(os, "add_dll_directory", None)
    if add_dll is not None:
        for d in candidate_dirs:
            resolved = str(d.resolve())
            if d.exists() and resolved not in _DLL_DIR_HANDLES:
                try:
                    _DLL_DIR_HANDLES[resolved] = add_dll(str(d))
                except OSError:
                    pass

    return env
