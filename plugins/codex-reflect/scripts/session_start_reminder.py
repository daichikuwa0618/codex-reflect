#!/usr/bin/env python3
"""Report project-scoped codex-reflect state at SessionStart."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib.codex_hooks import HookEvent, system_message
from lib.capabilities import probe_capabilities
from lib.codex_paths import get_codex_home, get_project_state_dir
from lib.state_store import StateStore


def _valid_cwd(data):
    cwd = data.get("cwd") if isinstance(data, dict) else None
    return isinstance(cwd, str) and bool(cwd) and os.path.isabs(cwd)


def _format_item(item, index):
    confidence = item.get("confidence") if isinstance(item, dict) else None
    confidence_text = (
        f"[{confidence:.0%}] "
        if isinstance(confidence, (int, float))
        else ""
    )
    return f"{index}. {confidence_text}learning candidate"


def _capability_lines(capabilities):
    version = (
        f" ({capabilities.codex_version})"
        if capabilities.codex_version is not None
        else ""
    )
    lines = [
        "Codex capabilities: history={}, semantic={}{}; realtime queue={}.".format(
            "available" if capabilities.history_available else "unavailable",
            "available" if capabilities.semantic_available else "unavailable",
            version,
            (
                "available"
                if capabilities.realtime_queue_available
                else "unavailable"
            ),
        )
    ]
    lines.extend("Capability: {}.".format(warning) for warning in capabilities.warnings)
    return lines


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
    capabilities = probe_capabilities(get_codex_home())
    store = StateStore(get_project_state_dir(event.cwd))
    initialized = store.queue_path.exists()
    if not capabilities.realtime_queue_available:
        lines = ["codex-reflect realtime queue is unavailable."]
        lines.extend(_capability_lines(capabilities))
        print(json.dumps(system_message("\n".join(lines))))
        return 0
    items = store.load()

    if not initialized:
        lines = ["codex-reflect has no project queue yet."]
        lines.extend(_capability_lines(capabilities))
        if capabilities.realtime_queue_available:
            lines.append(
                "Realtime capture may not have run; review and trust the "
                "codex-reflect definitions with /hooks."
            )
        if capabilities.history_available:
            lines.append(
                "Run $codex-reflect:reflect --scan-history to review available "
                "Codex session history."
            )
        elif capabilities.realtime_queue_available:
            lines.append(
                "Saved history is unavailable, but the realtime queue remains "
                "available after Hook trust."
            )
        print(json.dumps(system_message("\n".join(lines))))
        return 0
    if not items:
        if capabilities.warnings:
            lines = ["codex-reflect queue is empty."]
            lines.extend(_capability_lines(capabilities))
            print(json.dumps(system_message("\n".join(lines))))
        return 0

    lines = [f"codex-reflect has {len(items)} pending learning(s):"]
    lines.extend(
        _format_item(item, index)
        for index, item in enumerate(items[:5], 1)
    )
    if len(items) > 5:
        lines.append(f"... and {len(items) - 5} more")
    lines.append("Run $codex-reflect:reflect to review them.")
    lines.extend(_capability_lines(capabilities))
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
