#!/usr/bin/env python3
"""Tests for the supported Codex JSONL history adapter."""
import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "plugins" / "codex-reflect" / "scripts"
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "codex"
sys.path.insert(0, str(SCRIPTS_DIR))

from lib.codex_history import list_session_files, parse_transcript, read_jsonl
from lib.redaction import redact_secrets


class TestCodexHistory(unittest.TestCase):
    def test_extracts_known_messages_metadata_and_redacted_tool_output(self):
        result = parse_transcript(FIXTURES / "rollout-v1.jsonl")

        self.assertTrue(result.supported)
        self.assertEqual(result.session_id, "session-1")
        self.assertEqual(result.cwd, "/repo")
        self.assertEqual(result.timestamp, "2026-07-18T00:00:00Z")
        self.assertEqual(
            result.user_messages,
            ["no, use rg instead of grep", "remember: run focused tests"],
        )
        self.assertEqual(
            result.tool_outputs,
            ["Process exited with code 1: API_KEY=[REDACTED]"],
        )

    def test_deduplicates_exact_event_and_response_user_text_in_order(self):
        result = parse_transcript(FIXTURES / "rollout-v1.jsonl")

        self.assertEqual(
            result.user_messages,
            ["no, use rg instead of grep", "remember: run focused tests"],
        )

    def test_unknown_schema_is_reported_not_guessed(self):
        result = parse_transcript(FIXTURES / "unknown-rollout.jsonl")

        self.assertFalse(result.supported)
        self.assertEqual(result.user_messages, [])
        self.assertEqual(result.tool_outputs, [])
        self.assertIn("unsupported transcript schema", result.issues[0])

    def test_unknown_record_in_supported_transcript_is_reported_not_parsed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "mixed.jsonl"
            records = [
                {"type": "session_meta", "payload": {"id": "s1"}},
                {
                    "type": "event_msg",
                    "payload": {"type": "user_message", "message": "first"},
                },
                {"type": "future_record", "payload": {"message": "guessed"}},
            ]
            path.write_text(
                "".join(json.dumps(record) + "\n" for record in records),
                encoding="utf-8",
            )

            result = parse_transcript(path)

        self.assertTrue(result.supported)
        self.assertEqual(result.user_messages, ["first"])
        self.assertIn("ignored unknown record type: future_record", result.issues)

    def test_response_item_requires_user_role_and_input_text_shape(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "roles.jsonl"
            records = [
                {"type": "session_meta", "payload": {"id": "s1"}},
                {"type": "turn_context", "payload": {}},
                {
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "input_text", "text": "ignore"}],
                    },
                },
                {
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {"type": "output_text", "text": "ignore"},
                            {"type": "input_text", "text": "include"},
                        ],
                    },
                },
            ]
            path.write_text(
                "".join(json.dumps(record) + "\n" for record in records),
                encoding="utf-8",
            )

            result = parse_transcript(path)

        self.assertEqual(result.user_messages, ["include"])

    def test_only_custom_tool_call_output_is_normalized(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "outputs.jsonl"
            records = [
                {"type": "session_meta", "payload": {"id": "s1"}},
                {"type": "turn_context", "payload": {}},
                {
                    "type": "response_item",
                    "payload": {
                        "type": "function_call_output",
                        "output": "do not infer this output",
                    },
                },
                {
                    "type": "response_item",
                    "payload": {
                        "type": "custom_tool_call_output",
                        "output": {"error": "TOKEN=secret"},
                    },
                },
            ]
            path.write_text(
                "".join(json.dumps(record) + "\n" for record in records),
                encoding="utf-8",
            )

            result = parse_transcript(path)

        self.assertEqual(result.tool_outputs, ['{"error": "TOKEN=[REDACTED]"}'])

    def test_invalid_jsonl_reports_line_number(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "broken.jsonl"
            path.write_text(
                '{"type":"session_meta","payload":{}}\nnot-json\n',
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, r"invalid JSONL at line 2"):
                read_jsonl(path)

    def test_non_object_jsonl_reports_line_number(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "array.jsonl"
            path.write_text("[]\n", encoding="utf-8")

            with self.assertRaisesRegex(
                ValueError, r"record at line 1 must be an object"
            ):
                read_jsonl(path)

    def test_session_enumeration_includes_only_active_and_archived_jsonl(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home = Path(temp_dir)
            active = codex_home / "sessions" / "2026" / "07" / "active.jsonl"
            archived = codex_home / "archived_sessions" / "archived.jsonl"
            ignored = codex_home / "ui-cache" / "cached.jsonl"
            sqlite = codex_home / "state.sqlite"
            for path in (active, archived, ignored):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("", encoding="utf-8")
            sqlite.write_text("not a transcript", encoding="utf-8")

            files = list_session_files(codex_home)

        self.assertEqual(files, sorted([active, archived]))


class TestSecretRedaction(unittest.TestCase):
    def test_redacts_assignment_and_bearer_token_values_only(self):
        value = "API_KEY=abc123 Authorization: Bearer token-value"

        redacted = redact_secrets(value)

        self.assertEqual(
            redacted,
            "API_KEY=[REDACTED] Authorization: Bearer [REDACTED]",
        )

    def test_redacts_jwt_openai_and_github_style_tokens(self):
        value = (
            "jwt eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.signaturevalue "
            "openai sk-proj-abcdefghijklmnopqrstuvwxyz123456 "
            "github github_pat_abcdefghijklmnopqrstuvwxyz123456"
        )

        redacted = redact_secrets(value)

        self.assertNotIn("eyJhbGci", redacted)
        self.assertNotIn("sk-proj-", redacted)
        self.assertNotIn("github_pat_", redacted)
        self.assertEqual(redacted.count("[REDACTED]"), 3)

    def test_does_not_redact_non_secret_assignments(self):
        self.assertEqual(redact_secrets("COUNT=3 MODE=test"), "COUNT=3 MODE=test")


if __name__ == "__main__":
    unittest.main()
