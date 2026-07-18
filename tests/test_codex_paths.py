#!/usr/bin/env python3
"""Tests for Codex-specific state paths."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = REPO_ROOT / "plugins" / "codex-reflect"
SCRIPTS_DIR = PLUGIN_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from lib.codex_paths import (
    get_codex_home,
    get_project_id,
    get_project_state_dir,
    normalize_project_path,
)


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

    def test_git_repository_root_and_nested_directory_share_identity(self):
        with tempfile.TemporaryDirectory() as root:
            result = subprocess.run(
                ["git", "init", "--quiet", root],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            nested = Path(root) / "src" / "feature"
            nested.mkdir(parents=True)

            self.assertEqual(get_project_id(root), get_project_id(str(nested)))

    def test_non_repository_falls_back_to_normalized_directory(self):
        with tempfile.TemporaryDirectory() as root:
            nested = Path(root) / "nested"
            nested.mkdir()

            self.assertEqual(
                normalize_project_path(str(nested)),
                os.path.normcase(os.path.normpath(str(nested.resolve()))).replace(
                    "\\", "/"
                ),
            )
            self.assertNotEqual(get_project_id(root), get_project_id(str(nested)))

    def test_git_lookup_failure_falls_back_to_normalized_directory(self):
        with tempfile.TemporaryDirectory() as root, patch(
            "lib.codex_paths.subprocess.run", side_effect=OSError("git unavailable")
        ) as run:
            self.assertEqual(
                normalize_project_path(root),
                os.path.normcase(os.path.normpath(str(Path(root).resolve()))).replace(
                    "\\", "/"
                ),
            )
            run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
