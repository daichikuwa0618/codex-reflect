#!/usr/bin/env python3
"""Detect and capture correction patterns from Codex user prompts.

Cross-platform compatible (Windows, macOS, Linux).
This script is called by Codex's UserPromptSubmit Hook to detect
correction patterns, positive feedback, and explicit "remember:" markers.
"""
import sys
import os
import json

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib.reflect_utils import (
    append_to_queue,
    detect_patterns,
    create_queue_item,
    should_include_message,
    MAX_CAPTURE_PROMPT_LENGTH,
)
from lib.codex_hooks import HookEvent, system_message


def main() -> int:
    """Main entry point."""
    input_data = sys.stdin.read()
    if not input_data:
        return 0

    data = json.loads(input_data)
    cwd = data.get("cwd") if isinstance(data, dict) else None
    if not isinstance(cwd, str) or not cwd or not os.path.isabs(cwd):
        return 0

    event = HookEvent.from_dict(data)
    prompt = event.prompt
    if not prompt:
        return 0

    # Filter out system content (XML tags, tool results, session continuations)
    if not should_include_message(prompt):
        return 0

    # Skip very long prompts — real user corrections are short.
    # Exception: explicit "remember:" markers are always processed.
    if len(prompt) > MAX_CAPTURE_PROMPT_LENGTH and "remember:" not in prompt.lower():
        return 0

    # Detect patterns
    item_type, patterns, confidence, sentiment, decay_days = detect_patterns(prompt)

    # If we found something, queue it
    if item_type:
        queue_item = create_queue_item(
            message=prompt,
            item_type=item_type,
            patterns=patterns,
            confidence=confidence,
            sentiment=sentiment,
            decay_days=decay_days,
            project=event.cwd,
            session_id=event.session_id,
            turn_id=event.turn_id,
            model=event.model,
            source="hook",
        )

        append_to_queue(queue_item, event.cwd)

        print(json.dumps(system_message(
            "codex-reflect captured a learning candidate"
        )))

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        # Never block on errors - just log and exit 0
        print(f"Warning: capture_learning.py error: {e}", file=sys.stderr)
        sys.exit(0)
