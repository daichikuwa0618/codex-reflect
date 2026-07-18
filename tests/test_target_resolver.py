#!/usr/bin/env python3
"""Unit tests for Codex AGENTS.md and Skill target resolution."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "plugins" / "codex-reflect" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from lib.target_resolver import TargetResolver, TargetSuggestion


class TestTargetResolver(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        temp_root = Path(self.temp_dir.name).resolve()
        self.home = temp_root / "home"
        self.codex_home = self.home / ".codex"
        self.repo = temp_root / "repo"
        self.cwd = self.repo / "src" / "payments"
        self.codex_home.mkdir(parents=True)
        self.cwd.mkdir(parents=True)
        subprocess.run(
            ["git", "init", "-q", str(self.repo)],
            check=True,
            capture_output=True,
        )
        self.resolver = TargetResolver(self.codex_home, user_home=self.home)

    def tearDown(self):
        self.temp_dir.cleanup()

    @staticmethod
    def write(path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def test_global_override_masks_global_agents(self):
        self.write(self.codex_home / "AGENTS.md", "base")
        self.write(self.codex_home / "AGENTS.override.md", "override")

        targets = self.resolver.instruction_targets(self.cwd)

        self.assertIn(self.codex_home / "AGENTS.override.md", targets)
        self.assertNotIn(self.codex_home / "AGENTS.md", targets)

    def test_empty_global_override_falls_back_to_regular_agents(self):
        self.write(self.codex_home / "AGENTS.md", "base")
        self.write(self.codex_home / "AGENTS.override.md", "\n")

        targets = self.resolver.instruction_targets(self.cwd)

        self.assertIn(self.codex_home / "AGENTS.md", targets)
        self.assertNotIn(self.codex_home / "AGENTS.override.md", targets)

    def test_nested_override_wins_once_in_each_directory(self):
        self.write(self.repo / "AGENTS.md", "root")
        self.write(self.repo / "src" / "AGENTS.md", "src")
        self.write(self.repo / "src" / "AGENTS.override.md", "src override")
        self.write(self.cwd / "AGENTS.md", "payments")

        targets = self.resolver.instruction_targets(self.cwd)

        self.assertEqual(
            targets,
            [
                self.repo / "AGENTS.md",
                self.repo / "src" / "AGENTS.override.md",
                self.cwd / "AGENTS.md",
            ],
        )

    def test_repository_root_uses_git_toplevel(self):
        self.assertEqual(self.resolver.repository_root(self.cwd), self.repo.resolve())

    def test_repository_root_falls_back_to_cwd_outside_git(self):
        directory = Path(self.temp_dir.name).resolve() / "not-a-repo"
        directory.mkdir()

        self.assertEqual(self.resolver.repository_root(directory), directory.resolve())

    def test_skill_roots_are_repo_and_user_agents_directories(self):
        self.assertEqual(
            self.resolver.user_skill_root(), self.home / ".agents" / "skills"
        )
        self.assertEqual(
            self.resolver.repo_skill_root(self.repo),
            self.repo / ".agents" / "skills",
        )

    def test_path_specific_learning_prefers_active_file_in_evidence_directory(self):
        self.write(self.cwd / "AGENTS.override.md", "payments override")

        target = self.resolver.suggest_instruction_target(
            "In src/payments, always run make test-payments", self.cwd
        )

        self.assertEqual(target, self.cwd / "AGENTS.override.md")

    def test_path_specific_learning_prefers_nearest_parent_agents(self):
        self.write(self.repo / "src" / "AGENTS.md", "src")

        target = self.resolver.suggest_instruction_target(
            "In src/payments, always run make test-payments", self.cwd
        )

        self.assertEqual(target, self.repo / "src" / "AGENTS.md")

    def test_path_specific_learning_prefers_nearest_parent_override(self):
        self.write(self.repo / "src" / "AGENTS.md", "src")
        self.write(self.repo / "src" / "AGENTS.override.md", "src override")

        target = self.resolver.suggest_instruction_target(
            "In src/payments, always run make test-payments", self.cwd
        )

        self.assertEqual(target, self.repo / "src" / "AGENTS.override.md")

    def test_path_specific_learning_falls_back_to_active_repo_root(self):
        self.write(self.repo / "AGENTS.md", "root")

        target = self.resolver.suggest_instruction_target(
            "In src/payments, always run make test-payments", self.cwd
        )

        self.assertEqual(target, self.repo / "AGENTS.md")

    def test_path_specific_learning_proposes_regular_file_without_active_ancestor(self):
        target = self.resolver.suggest_instruction_target(
            "In src/payments, always run make test-payments", self.cwd
        )

        self.assertEqual(target, self.cwd / "AGENTS.md")
        self.assertFalse((self.cwd / "AGENTS.md").exists())
        self.assertFalse((self.cwd / "AGENTS.override.md").exists())

    def test_non_repository_suggestion_does_not_walk_parent_directories(self):
        parent = Path(self.temp_dir.name).resolve() / "not-a-repo"
        cwd = parent / "nested"
        cwd.mkdir(parents=True)
        self.write(parent / "AGENTS.md", "parent")

        target = self.resolver.suggest_instruction_target("local", cwd)

        self.assertEqual(target, cwd / "AGENTS.md")

    def test_cross_project_skill_prefers_user_scope(self):
        target = self.resolver.suggest_skill_root({"repo-a", "repo-b"}, self.repo)

        self.assertEqual(target, self.home / ".agents" / "skills")

    def test_single_project_skill_prefers_repo_scope(self):
        target = self.resolver.suggest_skill_root({"repo-a"}, self.repo)

        self.assertEqual(target, self.repo / ".agents" / "skills")

    def test_global_routing_proposes_regular_file_without_creating_override(self):
        suggestion = self.resolver.suggest_target("global")

        self.assertEqual(
            suggestion,
            TargetSuggestion("agents", self.codex_home / "AGENTS.md"),
        )
        self.assertFalse((self.codex_home / "AGENTS.md").exists())
        self.assertFalse((self.codex_home / "AGENTS.override.md").exists())

    def test_global_routing_uses_active_override(self):
        self.write(self.codex_home / "AGENTS.md", "base")
        self.write(self.codex_home / "AGENTS.override.md", "override")

        suggestion = self.resolver.suggest_target("global")

        self.assertEqual(
            suggestion,
            TargetSuggestion("agents", self.codex_home / "AGENTS.override.md"),
        )

    def test_project_routing_uses_repository_root(self):
        suggestion = self.resolver.suggest_target("project", cwd=self.cwd)

        self.assertEqual(
            suggestion, TargetSuggestion("agents", self.repo / "AGENTS.md")
        )

    def test_path_specific_routing_uses_evidence_directory(self):
        suggestion = self.resolver.suggest_target("path-specific", cwd=self.cwd)

        self.assertEqual(
            suggestion, TargetSuggestion("agents", self.cwd / "AGENTS.md")
        )

    def test_multi_project_routing_uses_user_skill_root(self):
        suggestion = self.resolver.suggest_target(
            "multi-project",
            cwd=self.cwd,
            source_projects={"repo-a", "repo-b"},
        )

        self.assertEqual(
            suggestion,
            TargetSuggestion("skill-root", self.home / ".agents" / "skills"),
        )

    def test_low_confidence_routing_keeps_learning_in_queue(self):
        suggestion = self.resolver.suggest_target("low-confidence")

        self.assertEqual(suggestion, TargetSuggestion("queue", None, read_only=True))


if __name__ == "__main__":
    unittest.main()
