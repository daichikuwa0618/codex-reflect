#!/usr/bin/env python3
"""Tests for Codex-specific state paths."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = REPO_ROOT / "plugins" / "codex-reflect"
SCRIPTS_DIR = PLUGIN_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from lib.codex_paths import get_codex_home, get_project_id, get_project_state_dir


class TestCodexPaths(unittest.TestCase):
    def test_codex_home_honors_environment(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(
            os.environ, {"CODEX_HOME": root}
        ):
            self.assertEqual(get_codex_home(), Path(root).resolve())

    def test_codex_home_defaults_below_user_home(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(
            os.environ, {}, clear=True
        ), patch("lib.codex_paths.Path.home", return_value=Path(root)):
            self.assertEqual(get_codex_home(), Path(root) / ".codex")

    def test_state_dir_is_below_codex_reflect(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(
            os.environ, {"CODEX_HOME": root}
        ):
            state = get_project_state_dir("/tmp/example")
            self.assertEqual(
                state.parent.parent, Path(root).resolve() / "codex-reflect"
            )

    def test_project_id_is_stable_and_path_safe(self):
        first = get_project_id("/tmp/example")
        second = get_project_id("/tmp/example/.")
        self.assertEqual(first, second)
        self.assertRegex(first, r"^[a-f0-9]{16}$")


if __name__ == "__main__":
    unittest.main()
