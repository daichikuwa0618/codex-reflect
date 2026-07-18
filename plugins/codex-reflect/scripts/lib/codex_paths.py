"""Stable paths for codex-reflect state shared by Hooks and Skills."""
import hashlib
import os
from pathlib import Path
from typing import Optional


def get_codex_home() -> Path:
    """Return the configured Codex home, or the default under the user home."""
    configured = os.environ.get("CODEX_HOME")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path.home() / ".codex"


def normalize_project_path(project_dir: Optional[str] = None) -> str:
    """Return a platform-normalized absolute project path."""
    path = Path(project_dir or os.getcwd()).expanduser().resolve()
    normalized = os.path.normcase(os.path.normpath(str(path)))
    return normalized.replace("\\", "/")


def get_project_id(project_dir: Optional[str] = None) -> str:
    """Return a stable, path-safe identifier for a project directory."""
    value = normalize_project_path(project_dir).encode("utf-8")
    return hashlib.sha256(value).hexdigest()[:16]


def get_project_state_dir(project_dir: Optional[str] = None) -> Path:
    """Return this project's state directory below CODEX_HOME/codex-reflect."""
    return (
        get_codex_home()
        / "codex-reflect"
        / "projects"
        / get_project_id(project_dir)
    )
