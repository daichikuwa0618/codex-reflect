#!/usr/bin/env python3
"""Tests for deterministic project queue commands."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "plugins" / "codex-reflect" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from lib.codex_paths import get_project_id


class TestQueueCommands(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.codex_home = root / "codex-home"
        self.project = root / "project"
        self.project.mkdir()
        self.env = os.environ.copy()
        self.env["CODEX_HOME"] = str(self.codex_home)
        self.items = [
            {
                "message": "remember: run tests",
                "confidence": 0.9,
                "patterns": "remember:",
                "timestamp": "2026-07-18T00:00:00Z",
            }
        ]
        state = (
            self.codex_home
            / "codex-reflect"
            / "projects"
            / get_project_id(self.project)
        )
        state.mkdir(parents=True)
        self.queue_path = state / "queue.json"
        self.queue_path.write_text(
            json.dumps(self.items), encoding="utf-8"
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def run_script(self, name, *arguments):
        return subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / name), *arguments],
            cwd=str(self.project),
            env=self.env,
            capture_output=True,
            text=True,
            check=False,
        )

    def load_queue(self):
        return json.loads(self.queue_path.read_text(encoding="utf-8"))

    def test_read_queue_formats_confidence_pattern_and_relative_time(self):
        result = self.run_script("read_queue.py")

        self.assertEqual(result.returncode, 0)
        self.assertIn('[0.90] "remember: run tests"', result.stdout)
        self.assertIn("(remember:)", result.stdout)
        self.assertRegex(result.stdout, r" - (?:just now|\d+[smhd] ago)")
        self.assertEqual(self.load_queue(), self.items)

    def test_read_queue_json_returns_raw_items_without_writing(self):
        result = self.run_script("read_queue.py", "--json")

        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout), self.items)
        self.assertEqual(self.load_queue(), self.items)

    def test_clear_queue_requires_confirm_flag(self):
        result = self.run_script("clear_queue.py")

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertEqual(self.load_queue(), self.items)

    def test_clear_queue_outputs_removed_items_with_confirm(self):
        result = self.run_script("clear_queue.py", "--confirm")

        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout), self.items)
        self.assertEqual(self.load_queue(), [])


if __name__ == "__main__":
    unittest.main()
