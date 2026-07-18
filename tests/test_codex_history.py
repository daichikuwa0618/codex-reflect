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

    def test_deduplicates_response_then_event_pair(self):
        result = self._parse_records([
            {"type": "session_meta", "payload": {"id": "s1"}},
            {"type": "turn_context", "payload": {}},
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "same prompt"}],
                },
            },
            {
                "type": "event_msg",
                "payload": {"type": "user_message", "message": "same prompt"},
            },
        ])

        self.assertEqual(result.user_messages, ["same prompt"])

    def test_same_prompt_in_two_turns_is_preserved_twice(self):
        result = self._parse_records([
            {"type": "session_meta", "payload": {"id": "s1"}},
            {"type": "turn_context", "payload": {"turn": 1}},
            {
                "type": "event_msg",
                "payload": {"type": "user_message", "message": "repeat prompt"},
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "repeat prompt"}],
                },
            },
            {"type": "turn_context", "payload": {"turn": 2}},
            {
                "type": "event_msg",
                "payload": {"type": "user_message", "message": "repeat prompt"},
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "repeat prompt"}],
                },
            },
        ])

        self.assertEqual(result.user_messages, ["repeat prompt", "repeat prompt"])

    def test_turn_context_resets_unmatched_pair_state_without_payload(self):
        result = self._parse_records([
            {"type": "session_meta", "payload": {"id": "s1"}},
            {
                "type": "event_msg",
                "payload": {"type": "user_message", "message": "repeat prompt"},
            },
            {"type": "turn_context"},
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "repeat prompt"}],
                },
            },
        ])

        self.assertEqual(result.user_messages, ["repeat prompt", "repeat prompt"])

    def test_repeated_same_source_occurrences_are_not_deduplicated(self):
        result = self._parse_records([
            {"type": "session_meta", "payload": {"id": "s1"}},
            {"type": "turn_context", "payload": {}},
            {
                "type": "event_msg",
                "payload": {"type": "user_message", "message": "repeat prompt"},
            },
            {
                "type": "event_msg",
                "payload": {"type": "user_message", "message": "repeat prompt"},
            },
        ])

        self.assertEqual(result.user_messages, ["repeat prompt", "repeat prompt"])

    def test_pairing_uses_raw_text_not_redacted_text(self):
        result = self._parse_records([
            {"type": "session_meta", "payload": {"id": "s1"}},
            {"type": "turn_context", "payload": {}},
            {
                "type": "event_msg",
                "payload": {"type": "user_message", "message": "TOKEN=first-secret"},
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "TOKEN=second-secret"}
                    ],
                },
            },
        ])

        self.assertEqual(
            result.user_messages,
            ["TOKEN=[REDACTED]", "TOKEN=[REDACTED]"],
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

    def test_structured_tool_output_redacts_nested_secret_keys(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "structured-output.jsonl"
            records = [
                {"type": "session_meta", "payload": {"id": "s1"}},
                {"type": "turn_context", "payload": {}},
                {
                    "type": "response_item",
                    "payload": {
                        "type": "custom_tool_call_output",
                        "output": {
                            "token": "top-secret",
                            "nested": {
                                "password": "secret phrase",
                                "safe": "keep this",
                            },
                            "items": [
                                {"api_key": "nested-secret"},
                                {"count": 3},
                            ],
                        },
                    },
                },
            ]
            path.write_text(
                "".join(json.dumps(record) + "\n" for record in records),
                encoding="utf-8",
            )

            result = parse_transcript(path)

        self.assertEqual(
            json.loads(result.tool_outputs[0]),
            {
                "token": "[REDACTED]",
                "nested": {
                    "password": "[REDACTED]",
                    "safe": "keep this",
                },
                "items": [
                    {"api_key": "[REDACTED]"},
                    {"count": 3},
                ],
            },
        )

    def test_end_to_end_tool_outputs_leave_no_raw_secret_values(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "redaction-e2e.jsonl"
            records = [
                {"type": "session_meta", "payload": {"id": "s1"}},
                {"type": "turn_context", "payload": {}},
                {
                    "type": "response_item",
                    "payload": {
                        "type": "custom_tool_call_output",
                        "output": (
                            r'{\"token\":\"escaped-string-secret\"} '
                            "Authorization=Bearer bearer-secret-value"
                        ),
                    },
                },
                {
                    "type": "response_item",
                    "payload": {
                        "type": "custom_tool_call_output",
                        "output": {
                            "AWS_SECRET_ACCESS_KEY": "aws-secret-value",
                            "nested": [
                                {"clientSecret": "client-secret-value"},
                                {"monkey": "banana"},
                            ],
                        },
                    },
                },
            ]
            path.write_text(
                "".join(json.dumps(record) + "\n" for record in records),
                encoding="utf-8",
            )

            result = parse_transcript(path)

        combined = "\n".join(result.tool_outputs)
        for secret in (
            "escaped-string-secret",
            "bearer-secret-value",
            "aws-secret-value",
            "client-secret-value",
        ):
            self.assertNotIn(secret, combined)
        self.assertIn('"monkey": "banana"', combined)

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

        self.assertEqual(files, sorted([active.resolve(), archived.resolve()]))

    def test_session_enumeration_skips_symlinked_history_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            codex_home = root / "codex-home"
            external_sessions = root / "external-sessions"
            external_sessions.mkdir()
            external_file = external_sessions / "outside.jsonl"
            external_file.write_text("", encoding="utf-8")
            codex_home.mkdir()
            self._symlink_or_skip(
                codex_home / "sessions",
                external_sessions,
                target_is_directory=True,
            )
            archived = codex_home / "archived_sessions" / "inside.jsonl"
            archived.parent.mkdir()
            archived.write_text("", encoding="utf-8")

            files = list_session_files(codex_home)

        self.assertEqual(files, [archived.resolve()])

    def test_session_enumeration_rejects_external_file_symlink(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            codex_home = root / "codex-home"
            sessions = codex_home / "sessions"
            sessions.mkdir(parents=True)
            external = root / "outside.jsonl"
            external.write_text("", encoding="utf-8")
            self._symlink_or_skip(sessions / "linked.jsonl", external)

            files = list_session_files(codex_home)

        self.assertEqual(files, [])

    def test_session_enumeration_deduplicates_canonical_file_and_link_aliases(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            codex_home = root / "codex-home"
            active = codex_home / "sessions" / "active.jsonl"
            active.parent.mkdir(parents=True)
            active.write_text("", encoding="utf-8")
            archive = codex_home / "archived_sessions"
            archive.mkdir()
            self._symlink_or_skip(archive / "alias-one.jsonl", active)
            self._symlink_or_skip(archive / "alias-two.jsonl", active)

            files = list_session_files(codex_home)

        self.assertEqual(files, [active.resolve()])

    def _symlink_or_skip(self, link, target, target_is_directory=False):
        try:
            link.symlink_to(target, target_is_directory=target_is_directory)
        except OSError as error:
            self.skipTest("symlinks unavailable: {}".format(type(error).__name__))

    def _parse_records(self, records):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "records.jsonl"
            path.write_text(
                "".join(json.dumps(record) + "\n" for record in records),
                encoding="utf-8",
            )
            return parse_transcript(path)


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

    def test_redacts_complete_quoted_assignment_value(self):
        self.assertEqual(
            redact_secrets('password="secret phrase"'),
            'password="[REDACTED]"',
        )

    def test_redacts_json_style_secret_assignment(self):
        self.assertEqual(
            redact_secrets('{"token": "structured-secret"}'),
            '{"token": "[REDACTED]"}',
        )

    def test_redacts_entire_bearer_assignment_without_suffix_leak(self):
        redacted = redact_secrets(
            "Authorization=Bearer fake-secret-value"
        )

        self.assertEqual(redacted, "Authorization=[REDACTED]")
        self.assertNotIn("fake-secret-value", redacted)

    def test_secret_identifier_components_cover_common_key_styles(self):
        values = (
            ("AWS_SECRET_ACCESS_KEY=aws-value", "aws-value"),
            ("GITHUB_TOKEN=github-value", "github-value"),
            ("access_token=access-value", "access-value"),
            ("clientSecret=client-value", "client-value"),
            ("API_KEY=api-value", "api-value"),
            ("x-client-secret: header-value", "header-value"),
        )

        for value, secret in values:
            with self.subTest(value=value):
                redacted = redact_secrets(value)
                self.assertIn("[REDACTED]", redacted)
                self.assertNotIn(secret, redacted)

    def test_secret_component_detection_avoids_substring_false_positive(self):
        self.assertEqual(
            redact_secrets("monkey=banana hockey=puck"),
            "monkey=banana hockey=puck",
        )

    def test_redacts_backslash_quoted_json_assignment(self):
        value = r'{\"token\":\"escaped-secret-value\"}'

        self.assertEqual(
            redact_secrets(value),
            r'{\"token\":\"[REDACTED]\"}',
        )

    def test_escaped_quote_inside_json_value_does_not_leak_suffix(self):
        value = '{"token": "prefix\\\"suffix-secret"}'

        redacted = redact_secrets(value)

        self.assertEqual(redacted, '{"token": "[REDACTED]"}')
        self.assertNotIn("suffix-secret", redacted)

    def test_escaped_quote_inside_backslash_quoted_json_value_does_not_leak(self):
        value = r'{\"token\":\"prefix\\\"suffix-secret\"}'

        redacted = redact_secrets(value)

        self.assertEqual(redacted, r'{\"token\":\"[REDACTED]\"}')
        self.assertNotIn("suffix-secret", redacted)

    def test_does_not_redact_non_secret_assignments(self):
        self.assertEqual(redact_secrets("COUNT=3 MODE=test"), "COUNT=3 MODE=test")


if __name__ == "__main__":
    unittest.main()
