#!/usr/bin/env python3
"""Contract tests for normalized Codex Hook payloads and output."""
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "plugins" / "codex-reflect" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from lib.codex_hooks import HookEvent, system_message


class TestCodexHookInput(unittest.TestCase):
    def test_user_prompt_submit_fields_are_normalized(self):
        event = HookEvent.from_dict({
            "session_id": "session-1",
            "turn_id": "turn-1",
            "cwd": "/repo",
            "hook_event_name": "UserPromptSubmit",
            "model": "gpt-test",
            "prompt": "remember: run focused tests",
            "tool_name": "Bash",
            "tool_input": {"command": "python3 -m unittest"},
            "tool_response": {"exit_code": 0},
        })

        self.assertEqual(event.event_name, "UserPromptSubmit")
        self.assertEqual(event.prompt, "remember: run focused tests")
        self.assertEqual(event.cwd, "/repo")
        self.assertEqual(event.session_id, "session-1")
        self.assertEqual(event.turn_id, "turn-1")
        self.assertEqual(event.model, "gpt-test")
        self.assertEqual(event.tool_name, "Bash")
        self.assertEqual(event.tool_input, {"command": "python3 -m unittest"})
        self.assertEqual(event.tool_response, {"exit_code": 0})

    def test_missing_fields_and_non_mapping_tool_input_are_safe(self):
        event = HookEvent.from_dict({"tool_input": "not-a-mapping"})

        self.assertEqual(event.event_name, "")
        self.assertEqual(event.cwd, "")
        self.assertEqual(event.session_id, "")
        self.assertIsNone(event.prompt)
        self.assertEqual(event.tool_input, {})

    def test_system_message_uses_codex_common_output(self):
        self.assertEqual(
            system_message("captured"),
            {"continue": True, "systemMessage": "captured"},
        )


if __name__ == "__main__":
    unittest.main()
