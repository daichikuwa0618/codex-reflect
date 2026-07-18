"""Narrow, read-only probes for public Codex capabilities used by the plugin."""
import os
import re
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

VERSION_PATTERN = re.compile(
    r"\b(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?)\b"
)
HISTORY_SECTION = re.compile(r"^\[\s*history\s*\]\s*(?:#.*)?$", re.I)
SECTION = re.compile(r"^\[[^]]+\]\s*(?:#.*)?$")
PERSISTENCE_NONE = re.compile(
    r"^persistence\s*=\s*(['\"])none\1\s*(?:#.*)?$",
    re.I,
)


@dataclass(frozen=True)
class Capabilities:
    codex_version: Optional[str]
    history_available: bool
    semantic_available: bool
    realtime_queue_available: bool
    warnings: List[str]


def _codex_version() -> Optional[str]:
    try:
        result = subprocess.run(
            ["codex", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    match = VERSION_PATTERN.search("{}\n{}".format(result.stdout, result.stderr))
    return match.group(1) if match is not None else None


def _history_persistence_disabled(config_path: Path) -> Tuple[bool, Optional[str]]:
    try:
        lines = config_path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return False, None
    except (OSError, UnicodeError) as error:
        return False, "Could not read Codex history configuration: {}".format(
            type(error).__name__
        )

    in_history = False
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if HISTORY_SECTION.match(line):
            in_history = True
            continue
        if SECTION.match(line):
            in_history = False
            continue
        if in_history and PERSISTENCE_NONE.match(line):
            return True, None
    return False, None


def _directory_writable(path: Path) -> bool:
    try:
        mode = path.stat().st_mode
    except OSError:
        return False
    write_bits = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
    return (
        stat.S_ISDIR(mode)
        and bool(mode & write_bits)
        and os.access(path, os.W_OK)
    )


def _state_writable(codex_home: Path) -> bool:
    state_dir = codex_home / "codex-reflect"
    if state_dir.is_symlink():
        return False
    if state_dir.exists():
        return _directory_writable(state_dir)

    ancestor = state_dir.parent
    while not ancestor.exists() and ancestor != ancestor.parent:
        ancestor = ancestor.parent
    return _directory_writable(ancestor)


def _has_saved_sessions(codex_home: Path) -> bool:
    for directory_name in ("sessions", "archived_sessions"):
        directory = codex_home / directory_name
        if directory.is_symlink() or not directory.is_dir():
            continue
        try:
            authorized_root = directory.resolve(strict=True)
        except OSError:
            continue
        for candidate in directory.rglob("*.jsonl"):
            if candidate.is_symlink():
                continue
            try:
                canonical = candidate.resolve(strict=True)
                canonical.relative_to(authorized_root)
            except (OSError, ValueError):
                continue
            if canonical.is_file():
                return True
    return False


def probe_capabilities(codex_home) -> Capabilities:
    """Inspect only public executable, config, history, and filesystem state."""
    root = Path(codex_home).expanduser().resolve()
    warnings = []

    version = _codex_version()
    semantic_available = version is not None
    if not semantic_available:
        warnings.append(
            "Codex CLI is unavailable; semantic validation is unavailable"
        )

    history_disabled, config_warning = _history_persistence_disabled(
        root / "config.toml"
    )
    if config_warning is not None:
        warnings.append(config_warning)
    saved_sessions = _has_saved_sessions(root) if not history_disabled else False
    history_available = not history_disabled and saved_sessions
    if history_disabled:
        warnings.append("Codex history persistence is disabled")
    elif not saved_sessions:
        warnings.append("No saved Codex sessions found")

    realtime_queue_available = _state_writable(root)
    if not realtime_queue_available:
        warnings.append(
            "codex-reflect state directory is not writable; "
            "realtime capture is unavailable"
        )

    return Capabilities(
        codex_version=version,
        history_available=history_available,
        semantic_available=semantic_available,
        realtime_queue_available=realtime_queue_available,
        warnings=warnings,
    )
