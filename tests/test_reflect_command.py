#!/usr/bin/env python3
"""Tests for the read-only reflect preparation command."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "plugins" / "codex-reflect" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from commands.reflect import ReflectionContext, parse_args, prepare_reflection
from lib.capabilities import Capabilities
from lib.codex_paths import get_project_id


class TestReflectCommand(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.codex_home = root / "codex-home"
        self.project = root / "repo"
        self.project.mkdir()
        self.agents = self.project / "AGENTS.md"
        self.agents.write_text("- Existing guidance\n", encoding="utf-8")
        state = (
            self.codex_home
            / "codex-reflect"
            / "projects"
            / get_project_id(self.project)
        )
        state.mkdir(parents=True)
        self.queue = state / "queue.json"
        self.items = [
            {
                "id": "q1",
                "type": "explicit",
                "message": "remember: run focused tests",
                "confidence": 0.9,
                "timestamp": "2026-07-18T00:00:00Z",
                "decay_days": 120,
            }
        ]
        self.queue.write_text(json.dumps(self.items), encoding="utf-8")
        self.unknown = root / "unknown.jsonl"
        self.unknown.write_text(
            '{"type":"future_record","payload":{"body":"ignore"}}\n',
            encoding="utf-8",
        )
        self.context = ReflectionContext(
            project=self.project,
            codex_home=self.codex_home,
            session_files=[self.unknown],
            capabilities=Capabilities(
                codex_version="test",
                history_available=True,
                semantic_available=True,
                realtime_queue_available=True,
                warnings=[],
            ),
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_parser_supports_fork_flags(self):
        args = parse_args([
            "--dry-run",
            "--scan-history",
            "--days",
            "30",
            "--targets",
            "--review",
            "--dedupe",
            "--organize",
            "--include-tool-errors",
            "--model",
            "gpt-test",
        ])

        self.assertTrue(args.dry_run)
        self.assertTrue(args.scan_history)
        self.assertEqual(args.days, 30)
        self.assertEqual(args.model, "gpt-test")

    @patch("commands.reflect.semantic_analyze", return_value=None)
    def test_dry_run_does_not_change_queue_or_targets(self, _semantic):
        before_queue = self.queue.read_bytes()
        before_agents = self.agents.read_bytes()

        result = prepare_reflection(self.context, dry_run=True)

        self.assertGreaterEqual(len(result["candidates"]), 1)
        self.assertEqual(result["candidates"][0]["semantic_status"], "unavailable")
        self.assertEqual(self.queue.read_bytes(), before_queue)
        self.assertEqual(self.agents.read_bytes(), before_agents)

    @patch("commands.reflect.semantic_analyze", return_value=None)
    def test_unknown_transcripts_are_reported(self, _semantic):
        result = prepare_reflection(self.context, scan_history=True)

        self.assertEqual(result["history"]["scanned"], 1)
        self.assertEqual(result["history"]["unsupported_sessions"], 1)
        self.assertIn("unsupported transcript schema", result["history"]["issues"][0])

    @patch("commands.reflect.semantic_analyze")
    def test_explicit_candidate_survives_negative_semantic_result(self, semantic):
        semantic.return_value = {
            "is_learning": False,
            "type": None,
            "confidence": 0.1,
            "reasoning": "Not reusable",
            "extracted_learning": None,
        }

        result = prepare_reflection(self.context)

        self.assertEqual(len(result["candidates"]), 1)
        self.assertEqual(
            result["candidates"][0]["semantic_status"],
            "explicit-retained",
        )

    @patch("commands.reflect.semantic_analyze")
    def test_targets_only_does_not_run_semantic_analysis(self, semantic):
        result = prepare_reflection(self.context, targets=True)

        semantic.assert_not_called()
        self.assertEqual(result["candidates"], [])
        self.assertTrue(
            any(target["path"] == str(self.agents.resolve()) for target in result["targets"])
        )

    @patch("commands.reflect.semantic_analyze", return_value=None)
    def test_days_filter_excludes_session_without_timestamp(self, _semantic):
        transcript = Path(self.temp_dir.name) / "missing-timestamp.jsonl"
        transcript.write_text(
            "\n".join([
                json.dumps({
                    "type": "session_meta",
                    "payload": {"id": "s1", "cwd": str(self.project)},
                }),
                json.dumps({
                    "type": "event_msg",
                    "payload": {
                        "type": "user_message",
                        "message": "remember: secret scope",
                    },
                }),
            ]) + "\n",
            encoding="utf-8",
        )
        context = ReflectionContext(
            project=self.project,
            codex_home=self.codex_home,
            session_files=[transcript],
            capabilities=self.context.capabilities,
        )

        result = prepare_reflection(context, scan_history=True, days=1)

        self.assertFalse(any(
            candidate.get("source") == "history"
            for candidate in result["candidates"]
        ))
        self.assertTrue(any(
            "missing timestamp" in issue
            for issue in result["history"]["issues"]
        ))

    @patch("commands.reflect.semantic_analyze", return_value=None)
    def test_scope_filters_transcripts_before_full_parsing(self, _semantic):
        def write_session(name, cwd, timestamp, message, unknown=False):
            path = Path(self.temp_dir.name) / name
            records = [
                {
                    "type": "session_meta",
                    "payload": {
                        "id": name,
                        "cwd": str(cwd),
                        "timestamp": timestamp,
                    },
                },
                {
                    "type": "event_msg",
                    "payload": {"type": "user_message", "message": message},
                },
            ]
            if unknown:
                records.extend(
                    {"type": "future_record", "payload": {}}
                    for _ in range(3)
                )
            path.write_text(
                "".join(json.dumps(record) + "\n" for record in records),
                encoding="utf-8",
            )
            return path

        current = write_session(
            "current.jsonl",
            self.project,
            "2099-07-18T00:00:00Z",
            "remember: keep this project-scoped learning",
        )
        old = write_session(
            "old.jsonl",
            self.project,
            "2000-01-01T00:00:00Z",
            "remember: do not read this old learning",
            unknown=True,
        )
        other = write_session(
            "other.jsonl",
            Path(self.temp_dir.name) / "other-repo",
            "2099-07-18T00:00:00Z",
            "remember: do not read this other-project learning",
            unknown=True,
        )
        context = ReflectionContext(
            project=self.project,
            codex_home=self.codex_home,
            session_files=[current, old, other],
            capabilities=self.context.capabilities,
        )

        result = prepare_reflection(context, scan_history=True, days=30)

        history_candidates = [
            candidate
            for candidate in result["candidates"]
            if candidate.get("source") == "history"
        ]
        self.assertEqual(result["history"]["scanned"], 1)
        self.assertEqual(len(history_candidates), 1)
        self.assertEqual(
            history_candidates[0]["message"],
            "remember: keep this project-scoped learning",
        )
        self.assertFalse(any(
            "future_record" in issue for issue in result["history"]["issues"]
        ))

    @patch("commands.reflect.semantic_analyze", return_value=None)
    def test_history_scan_filters_app_injected_context(self, _semantic):
        transcript = Path(self.temp_dir.name) / "injected-context.jsonl"
        records = [
            {
                "type": "session_meta",
                "payload": {
                    "id": "injected-context",
                    "cwd": str(self.project),
                    "timestamp": "2099-07-18T00:00:00Z",
                },
            },
            {
                "type": "event_msg",
                "payload": {
                    "type": "user_message",
                    "message": (
                        "# AGENTS.md instructions for /repo\n\n"
                        "remember: do not treat this as user feedback"
                    ),
                },
            },
            {
                "type": "event_msg",
                "payload": {
                    "type": "user_message",
                    "message": "remember: keep this actual user feedback",
                },
            },
        ]
        transcript.write_text(
            "".join(json.dumps(record) + "\n" for record in records),
            encoding="utf-8",
        )
        context = ReflectionContext(
            project=self.project,
            codex_home=self.codex_home,
            session_files=[transcript],
            capabilities=self.context.capabilities,
        )

        result = prepare_reflection(context, scan_history=True, days=30)

        history_messages = [
            candidate["message"]
            for candidate in result["candidates"]
            if candidate.get("source") == "history"
        ]
        self.assertEqual(
            history_messages,
            ["remember: keep this actual user feedback"],
        )

    @patch("commands.reflect.semantic_analyze")
    @patch("commands.reflect.probe_capabilities")
    def test_missing_codex_cli_keeps_candidates_without_semantic_calls(
        self,
        probe,
        semantic,
    ):
        probe.return_value = Capabilities(
            codex_version=None,
            history_available=False,
            semantic_available=False,
            realtime_queue_available=True,
            warnings=[
                "Codex CLI is unavailable; semantic validation is unavailable"
            ],
        )

        context = ReflectionContext(
            project=self.project,
            codex_home=self.codex_home,
            session_files=[self.unknown],
        )

        with patch("commands.reflect.detect_contradictions") as contradictions:
            result = prepare_reflection(context, organize=True)

        semantic.assert_not_called()
        contradictions.assert_not_called()
        self.assertEqual(result["candidates"][0]["semantic_status"], "unavailable")
        self.assertFalse(result["capabilities"]["semantic_available"])
        self.assertTrue(result["capabilities"]["realtime_queue_available"])

    @patch("commands.reflect._scan_history")
    @patch("commands.reflect.probe_capabilities")
    def test_unavailable_history_is_reported_without_fallback_scan(
        self,
        probe,
        scan_history,
    ):
        probe.return_value = Capabilities(
            codex_version="1.0.0",
            history_available=False,
            semantic_available=True,
            realtime_queue_available=True,
            warnings=["Codex history persistence is disabled"],
        )
        context = ReflectionContext(
            project=self.project,
            codex_home=self.codex_home,
        )

        result = prepare_reflection(context, scan_history=True)

        scan_history.assert_not_called()
        self.assertIn(
            "Codex history persistence is disabled",
            result["history"]["issues"],
        )
        self.assertFalse(result["capabilities"]["history_available"])


if __name__ == "__main__":
    unittest.main()
