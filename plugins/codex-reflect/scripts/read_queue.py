#!/usr/bin/env python3
"""Read the current project's codex-reflect queue without modifying it."""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib.reflect_utils import load_queue


def _relative_time(value):
    if not isinstance(value, str) or not value:
        return "unknown time"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return "unknown time"
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    seconds = max(
        0,
        int((datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds()),
    )
    if seconds < 5:
        return "just now"
    if seconds < 60:
        return "{}s ago".format(seconds)
    minutes = seconds // 60
    if minutes < 60:
        return "{}m ago".format(minutes)
    hours = minutes // 60
    if hours < 24:
        return "{}h ago".format(hours)
    return "{}d ago".format(hours // 24)


def _format_item(item):
    item = item if isinstance(item, dict) else {}
    confidence = item.get("confidence")
    if isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
        confidence_text = "{:.2f}".format(max(0.0, min(1.0, confidence)))
    else:
        confidence_text = "0.00"
    message = item.get("message", item.get("original_message", ""))
    if not isinstance(message, str):
        message = str(message)
    pattern = item.get("patterns", item.get("pattern", ""))
    if isinstance(pattern, list):
        pattern = " ".join(str(value) for value in pattern)
    elif not isinstance(pattern, str):
        pattern = str(pattern) if pattern else ""
    pattern_text = " ({})".format(pattern) if pattern else ""
    captured_at = item.get("captured_at", item.get("timestamp"))
    return '[{}] {}{} - {}'.format(
        confidence_text,
        json.dumps(message, ensure_ascii=False),
        pattern_text,
        _relative_time(captured_at),
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    items = load_queue()
    if args.json:
        print(json.dumps(items, ensure_ascii=False, indent=2))
    else:
        for item in items:
            print(_format_item(item))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
