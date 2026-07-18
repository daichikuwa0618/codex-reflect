#!/usr/bin/env python3
"""Tests for narrow, dependency-free Codex capability probing."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "plugins" / "codex-reflect" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from lib.capabilities import probe_capabilities


class TestCapabilities(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.codex_home = Path(self.temp_dir.name) / "codex-home"
        self.codex_home.mkdir()
        self.config = self.codex_home / "config.toml"

    def tearDown(self):
        self.temp_dir.cleanup()

    def _saved_session(self):
        session = self.codex_home / "sessions" / "saved.jsonl"
        session.parent.mkdir(parents=True, exist_ok=True)
        session.write_text("{}\n", encoding="utf-8")

    @patch("lib.capabilities.subprocess.run")
    def test_reports_codex_version(self, run):
        run.return_value = subprocess.CompletedProcess(
            [], 0, "codex-cli 0.144.1\n", ""
        )

        result = probe_capabilities(self.codex_home)

        self.assertEqual(result.codex_version, "0.144.1")
        self.assertTrue(result.semantic_available)

    @patch("lib.capabilities.subprocess.run")
    def test_history_none_disables_only_history_features(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, "codex 1.0.0\n", "")
        self._saved_session()
        self.config.write_text(
            '[history]\npersistence = "none"\n', encoding="utf-8"
        )

        result = probe_capabilities(self.codex_home)

        self.assertFalse(result.history_available)
        self.assertTrue(result.realtime_queue_available)
        self.assertIn("Codex history persistence is disabled", result.warnings)

    @patch("lib.capabilities.subprocess.run")
    def test_missing_session_dirs_is_not_core_failure(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, "codex 1.0.0\n", "")

        result = probe_capabilities(self.codex_home)

        self.assertFalse(result.history_available)
        self.assertIn("No saved Codex sessions found", result.warnings)
        self.assertTrue(result.realtime_queue_available)

    @patch("lib.capabilities.subprocess.run", side_effect=FileNotFoundError)
    def test_missing_codex_cli_disables_only_semantic_features(self, _run):
        result = probe_capabilities(self.codex_home)

        self.assertIsNone(result.codex_version)
        self.assertFalse(result.semantic_available)
        self.assertTrue(result.realtime_queue_available)
        self.assertTrue(any(
            "semantic validation is unavailable" in warning
            for warning in result.warnings
        ))

    @patch("lib.capabilities.subprocess.run")
    def test_non_directory_state_path_disables_realtime_queue(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, "codex 1.0.0\n", "")
        (self.codex_home / "codex-reflect").write_text("blocked", encoding="utf-8")

        result = probe_capabilities(self.codex_home)

        self.assertFalse(result.realtime_queue_available)
        self.assertTrue(any(
            "realtime capture is unavailable" in warning
            for warning in result.warnings
        ))

    @patch("lib.capabilities.subprocess.run")
    def test_dangling_state_symlink_disables_realtime_queue(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, "codex 1.0.0\n", "")
        state = self.codex_home / "codex-reflect"
        try:
            state.symlink_to(self.codex_home / "missing", target_is_directory=True)
        except (NotImplementedError, OSError):
            self.skipTest("directory symlinks are unavailable")

        result = probe_capabilities(self.codex_home)

        self.assertFalse(result.realtime_queue_available)

    @patch("lib.capabilities.subprocess.run")
    def test_commented_history_setting_does_not_disable_history(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, "codex 1.0.0\n", "")
        self._saved_session()
        self.config.write_text(
            '[history]\n# persistence = "none"\n', encoding="utf-8"
        )

        result = probe_capabilities(self.codex_home)

        self.assertTrue(result.history_available)


if __name__ == "__main__":
    unittest.main()
