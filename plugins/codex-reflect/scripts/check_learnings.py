#!/usr/bin/env python3
"""Atomically back up a project queue before Codex compacts context."""
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from uuid import uuid4

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib.codex_hooks import HookEvent, system_message
from lib.codex_paths import get_project_state_dir
from lib.state_store import StateStore


def _valid_cwd(data):
    cwd = data.get("cwd") if isinstance(data, dict) else None
    return isinstance(cwd, str) and bool(cwd) and os.path.isabs(cwd)


def _write_backup(items, backup_dir):
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    backup_path = backup_dir / f"pre-compact-{timestamp}-{uuid4().hex}.json"
    fd, temp_name = tempfile.mkstemp(
        dir=str(backup_dir), prefix="pre-compact-", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(items, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, backup_path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return backup_path


def main() -> int:
    input_data = sys.stdin.read()
    if not input_data:
        return 0
    try:
        data = json.loads(input_data)
    except json.JSONDecodeError:
        return 0
    if not _valid_cwd(data):
        return 0

    event = HookEvent.from_dict(data)
    state_dir = get_project_state_dir(event.cwd)
    items = StateStore(state_dir).load()
    if not items:
        return 0

    backup_path = _write_backup(items, state_dir / "backups")
    print(json.dumps(system_message(
        f"codex-reflect backed up {len(items)} learning(s) to {backup_path}."
    )))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Warning: check_learnings.py error: {error}", file=sys.stderr)
        raise SystemExit(0)
