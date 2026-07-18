#!/usr/bin/env python3
"""Remind about queued learnings after a non-amend git commit."""
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


def _normalize_command(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list) and all(
        isinstance(part, str) for part in value
    ):
        return " ".join(value)
    return ""


def _command_from(tool_input):
    if "cmd" not in tool_input:
        return _normalize_command(tool_input.get("command"))

    value = tool_input["cmd"]
    if value is None or value == "" or value == []:
        return _normalize_command(tool_input.get("command"))
    return _normalize_command(value)


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
    command = _command_from(event.tool_input)
    if "git commit" not in command or "--amend" in command:
        return 0

    items = StateStore(get_project_state_dir(event.cwd)).load()
    message = "Git commit detected!"
    if items:
        message += f" You have {len(items)} queued learning(s)."
    message += (
        " Feature complete? Run $codex-reflect:reflect to process learnings."
    )
    print(json.dumps(system_message(message)))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(
            f"Warning: post_commit_reminder.py error: {error}",
            file=sys.stderr,
        )
        raise SystemExit(0)
