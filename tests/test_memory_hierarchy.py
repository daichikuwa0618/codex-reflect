#!/usr/bin/env python3
"""Routing integration tests for Codex AGENTS.md and Skill targets."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "plugins" / "codex-reflect" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from lib.target_resolver import TargetResolver, TargetSuggestion


class ResolverTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        temp_root = Path(self.temp_dir.name).resolve()
        self.home = temp_root / "home"
        self.codex_home = self.home / ".codex"
        self.repo = temp_root / "repo"
        self.nested = self.repo / "packages" / "api"
        self.codex_home.mkdir(parents=True)
        self.nested.mkdir(parents=True)
        subprocess.run(
            ["git", "init", "-q", str(self.repo)],
            check=True,
            capture_output=True,
        )
        self.resolver = TargetResolver(self.codex_home, user_home=self.home)

    def tearDown(self):
        self.temp_dir.cleanup()

    @staticmethod
    def write(path, text="guidance"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


class TestAgentsHierarchy(ResolverTestCase):
    def test_chain_selects_one_active_file_per_directory(self):
        self.write(self.codex_home / "AGENTS.md", "global")
        self.write(self.repo / "AGENTS.md", "repo")
        self.write(self.repo / "packages" / "AGENTS.md", "regular")
        self.write(self.repo / "packages" / "AGENTS.override.md", "override")
        self.write(self.nested / "AGENTS.md", "api")

        self.assertEqual(
            self.resolver.instruction_targets(self.nested),
            [
                self.codex_home / "AGENTS.md",
                self.repo / "AGENTS.md",
                self.repo / "packages" / "AGENTS.override.md",
                self.nested / "AGENTS.md",
            ],
        )

    def test_project_learning_is_routed_by_repository_root(self):
        suggestion = self.resolver.suggest_target("project", cwd=self.nested)

        self.assertEqual(suggestion.path, self.repo / "AGENTS.md")

    def test_path_learning_does_not_create_override(self):
        suggestion = self.resolver.suggest_target("path-specific", cwd=self.nested)

        self.assertEqual(suggestion.path, self.nested / "AGENTS.md")
        self.assertFalse((self.nested / "AGENTS.override.md").exists())


class TestSkillRouting(ResolverTestCase):
    def test_repo_authoring_skill_is_writable(self):
        skill = self.repo / ".agents" / "skills" / "test-runner" / "SKILL.md"
        self.write(skill, "# Test runner")

        suggestion = self.resolver.suggest_target(
            "skill", cwd=self.nested, skill_path=skill
        )

        self.assertEqual(suggestion, TargetSuggestion("skill", skill.resolve()))

    def test_user_authoring_skill_is_writable(self):
        skill = self.home / ".agents" / "skills" / "test-runner" / "SKILL.md"
        self.write(skill, "# Test runner")

        suggestion = self.resolver.suggest_target(
            "skill", cwd=self.nested, skill_path=skill
        )

        self.assertEqual(suggestion, TargetSuggestion("skill", skill.resolve()))

    def test_multi_project_workflow_uses_user_skill_root(self):
        suggestion = self.resolver.suggest_target(
            "multi-project",
            cwd=self.nested,
            source_projects={str(self.repo), "/another/repo"},
        )

        self.assertEqual(
            suggestion.path, self.home / ".agents" / "skills"
        )


class TestReadOnlyPluginSkill(ResolverTestCase):
    def test_missing_repo_authoring_skill_is_suggested_read_only(self):
        skill = self.repo / ".agents" / "skills" / "missing" / "SKILL.md"

        suggestion = self.resolver.suggest_target(
            "skill", cwd=self.nested, skill_path=skill
        )

        self.assertEqual(suggestion.path, skill.resolve())
        self.assertTrue(suggestion.read_only)

    def test_directory_at_repo_authoring_path_is_suggested_read_only(self):
        skill = self.repo / ".agents" / "skills" / "directory" / "SKILL.md"
        skill.mkdir(parents=True)

        suggestion = self.resolver.suggest_target(
            "skill", cwd=self.nested, skill_path=skill
        )

        self.assertEqual(suggestion.path, skill.resolve())
        self.assertTrue(suggestion.read_only)

    def test_nonwritable_repo_authoring_skill_is_suggested_read_only(self):
        skill = self.repo / ".agents" / "skills" / "locked" / "SKILL.md"
        self.write(skill, "# Locked")
        original_mode = skill.stat().st_mode
        skill.chmod(0o444)
        try:
            suggestion = self.resolver.suggest_target(
                "skill", cwd=self.nested, skill_path=skill
            )
        finally:
            skill.chmod(original_mode)

        self.assertEqual(suggestion.path, skill.resolve())
        self.assertTrue(suggestion.read_only)

    def test_plugin_cache_skill_is_suggested_read_only(self):
        skill = (
            self.codex_home
            / "plugins"
            / "cache"
            / "vendor"
            / "plugin"
            / "1.0.0"
            / "skills"
            / "review"
            / "SKILL.md"
        )
        self.write(skill, "# Cached review")

        suggestion = self.resolver.suggest_target(
            "skill", cwd=self.nested, skill_path=skill
        )

        self.assertEqual(suggestion.path, skill.resolve())
        self.assertTrue(suggestion.read_only)

    def test_system_skill_is_suggested_read_only(self):
        skill = (
            self.codex_home
            / "skills"
            / ".system"
            / "skill-creator"
            / "SKILL.md"
        )
        self.write(skill, "# System skill creator")

        suggestion = self.resolver.suggest_target(
            "skill", cwd=self.nested, skill_path=skill
        )

        self.assertEqual(suggestion.path, skill.resolve())
        self.assertTrue(suggestion.read_only)

    def test_admin_managed_skill_is_suggested_read_only(self):
        skill = (
            Path(self.temp_dir.name).resolve()
            / "managed"
            / "skills"
            / "review"
            / "SKILL.md"
        )
        self.write(skill, "# Managed review")

        suggestion = self.resolver.suggest_target(
            "skill", cwd=self.nested, skill_path=skill
        )

        self.assertEqual(suggestion.path, skill.resolve())
        self.assertTrue(suggestion.read_only)

    def test_repo_authoring_symlink_to_external_skill_is_suggested_read_only(self):
        external = (
            Path(self.temp_dir.name).resolve()
            / "external"
            / "review"
            / "SKILL.md"
        )
        self.write(external, "# External review")
        skill = self.repo / ".agents" / "skills" / "review" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        try:
            skill.symlink_to(external)
        except (NotImplementedError, OSError) as error:
            self.skipTest("symlink unavailable: {}".format(error))

        suggestion = self.resolver.suggest_target(
            "skill", cwd=self.nested, skill_path=skill
        )

        self.assertEqual(suggestion.path, external.resolve())
        self.assertTrue(suggestion.read_only)

    def test_repo_authoring_root_symlink_to_external_is_suggested_read_only(self):
        external_root = Path(self.temp_dir.name).resolve() / "external-repo-skills"
        external = external_root / "review" / "SKILL.md"
        self.write(external, "# External review")
        authoring_root = self.repo / ".agents" / "skills"
        authoring_root.parent.mkdir(parents=True)
        try:
            authoring_root.symlink_to(external_root, target_is_directory=True)
        except (NotImplementedError, OSError) as error:
            self.skipTest("symlink unavailable: {}".format(error))
        skill = authoring_root / "review" / "SKILL.md"

        suggestion = self.resolver.suggest_target(
            "skill", cwd=self.nested, skill_path=skill
        )

        self.assertEqual(suggestion.path, external.resolve())
        self.assertTrue(suggestion.read_only)

    def test_user_authoring_intermediate_symlink_is_suggested_read_only(self):
        external_agents = Path(self.temp_dir.name).resolve() / "external-user-agents"
        external = external_agents / "skills" / "review" / "SKILL.md"
        self.write(external, "# External review")
        agents = self.home / ".agents"
        agents.parent.mkdir(parents=True, exist_ok=True)
        try:
            agents.symlink_to(external_agents, target_is_directory=True)
        except (NotImplementedError, OSError) as error:
            self.skipTest("symlink unavailable: {}".format(error))
        skill = agents / "skills" / "review" / "SKILL.md"

        suggestion = self.resolver.suggest_target(
            "skill", cwd=self.nested, skill_path=skill
        )

        self.assertEqual(suggestion.path, external.resolve())
        self.assertTrue(suggestion.read_only)


if __name__ == "__main__":
    unittest.main()
