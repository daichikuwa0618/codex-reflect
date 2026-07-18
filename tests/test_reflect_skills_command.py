#!/usr/bin/env python3
"""Tests for deterministic reusable-Skill discovery input."""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "plugins" / "codex-reflect" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from commands.reflect_skills import (
    DiscoveryContext,
    collect_discovery_input,
    collect_existing_skills,
    parse_args,
)


class TestReflectSkillsCommand(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.codex_home = root / "codex-home"
        self.user_home = root / "home"
        self.project = root / "repo"
        self.other_project = root / "other-repo"
        self.project.mkdir()
        self.other_project.mkdir()
        self.context = DiscoveryContext(
            codex_home=self.codex_home,
            project=self.project,
            user_home=self.user_home,
            now=datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc),
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write_session(self, name, cwd, timestamp, messages):
        path = self.codex_home / "sessions" / "2026" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        records = [
            {
                "type": "session_meta",
                "payload": {
                    "id": name[:-6] if name.endswith(".jsonl") else name,
                    "cwd": str(cwd),
                    "timestamp": timestamp,
                },
            }
        ]
        records.extend(
            {
                "type": "event_msg",
                "payload": {"type": "user_message", "message": message},
            }
            for message in messages
        )
        path.write_text(
            "\n".join(json.dumps(record) for record in records) + "\n",
            encoding="utf-8",
        )
        return path

    def test_defaults_to_current_project_and_fourteen_days(self):
        args = parse_args([])

        self.assertEqual(args.days, 14)
        self.assertIsNone(args.project)
        self.assertFalse(args.all_projects)
        self.assertFalse(args.dry_run)

    def test_collects_only_supported_sessions_in_date_range(self):
        self._write_session(
            "current-a.jsonl",
            self.project,
            "2026-07-10T12:00:00Z",
            ["build, test, then publish"],
        )
        self._write_session(
            "current-b.jsonl",
            self.project,
            "2026-07-18T11:00:00Z",
            ["build, test, then publish again"],
        )
        self._write_session(
            "old.jsonl",
            self.project,
            "2026-06-01T00:00:00Z",
            ["too old"],
        )
        self._write_session(
            "other.jsonl",
            self.other_project,
            "2026-07-18T10:00:00Z",
            ["other project"],
        )
        unknown = self.codex_home / "archived_sessions" / "unknown.jsonl"
        unknown.parent.mkdir(parents=True)
        unknown.write_text('{"type":"future_record"}\n', encoding="utf-8")

        result = collect_discovery_input(self.context, days=14)

        self.assertEqual(result["supported_sessions"], 2)
        self.assertEqual(result["unsupported_sessions"], 1)
        self.assertEqual(result["projects"], [str(self.project.resolve())])
        self.assertEqual(
            [session["session_id"] for session in result["sessions"]],
            ["current-a", "current-b"],
        )

    def test_all_projects_includes_each_project_in_scope(self):
        self._write_session(
            "current.jsonl",
            self.project,
            "2026-07-18T10:00:00Z",
            ["current project"],
        )
        self._write_session(
            "other.jsonl",
            self.other_project,
            "2026-07-18T11:00:00Z",
            ["other project"],
        )

        result = collect_discovery_input(
            self.context,
            days=14,
            all_projects=True,
        )

        self.assertEqual(result["supported_sessions"], 2)
        self.assertEqual(
            result["projects"],
            sorted([str(self.project.resolve()), str(self.other_project.resolve())]),
        )

    def test_existing_skills_include_repo_and_user_authoring_sources(self):
        repo_skill = self.project / ".agents" / "skills" / "deploy" / "SKILL.md"
        user_skill = self.user_home / ".agents" / "skills" / "review" / "SKILL.md"
        repo_skill.parent.mkdir(parents=True)
        user_skill.parent.mkdir(parents=True)
        repo_skill.write_text(
            "---\nname: deploy\ndescription: Use when deploying.\n---\n",
            encoding="utf-8",
        )
        user_skill.write_text(
            "---\nname: daily-review\ndescription: Use when reviewing.\n---\n",
            encoding="utf-8",
        )

        result = collect_existing_skills(self.project, self.user_home)

        self.assertEqual({item["name"] for item in result}, {"deploy", "daily-review"})
        self.assertEqual({item["scope"] for item in result}, {"repository", "user"})
        self.assertTrue(all(item["writable"] for item in result))

    def test_missing_timestamp_is_unsupported_when_days_are_bounded(self):
        self._write_session(
            "missing-time.jsonl",
            self.project,
            "",
            ["do not leak into a bounded scan"],
        )

        result = collect_discovery_input(self.context, days=14)

        self.assertEqual(result["supported_sessions"], 0)
        self.assertEqual(result["unsupported_sessions"], 1)
        self.assertTrue(any(
            "missing or invalid timestamp" in issue
            for issue in result["issues"]
        ))

    def test_negative_days_are_rejected(self):
        with self.assertRaises(ValueError):
            collect_discovery_input(self.context, days=-1)


if __name__ == "__main__":
    unittest.main()
