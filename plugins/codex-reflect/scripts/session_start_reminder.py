#!/usr/bin/env python3
"""Report project-scoped codex-reflect state at SessionStart."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib.codex_hooks import HookEvent, system_message
from lib.codex_paths import get_project_state_dir
from lib.state_store import StateStore


def _valid_cwd(data):
    cwd = data.get("cwd") if isinstance(data, dict) else None
    return isinstance(cwd, str) and bool(cwd) and os.path.isabs(cwd)


def _format_item(item, index):
    if not isinstance(item, dict):
        return f"{index}. learning candidate"
    message = item.get("message", "")
    if not isinstance(message, str):
        message = ""
    if len(message) > 60:
        message = message[:57] + "..."
    confidence = item.get("confidence")
    confidence_text = (
        f"[{confidence:.0%}] "
        if isinstance(confidence, (int, float))
        else ""
    )
    return f"{index}. {confidence_text}{message or 'learning candidate'}"


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
    store = StateStore(get_project_state_dir(event.cwd))
    initialized = store.queue_path.exists()
    items = store.load()

    if not initialized:
        print(json.dumps(system_message(
            "codex-reflect is not initialized for this project. "
            "Run $codex-reflect:reflect --scan-history to review available "
            "Codex session history."
        )))
        return 0
    if not items:
        return 0

    lines = [f"codex-reflect has {len(items)} pending learning(s):"]
    lines.extend(
        _format_item(item, index)
        for index, item in enumerate(items[:5], 1)
    )
    if len(items) > 5:
        lines.append(f"... and {len(items) - 5} more")
    lines.append("Run $codex-reflect:reflect to review them.")
    print(json.dumps(system_message("\n".join(lines))))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(
            f"Warning: session_start_reminder.py error: {error}",
            file=sys.stderr,
        )
        raise SystemExit(0)
