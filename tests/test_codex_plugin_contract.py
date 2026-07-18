#!/usr/bin/env python3
"""Contract tests for the nested Codex plugin package."""

import json
import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = REPO_ROOT / "plugins" / "codex-reflect"
MANIFEST_PATH = PLUGIN_ROOT / ".codex-plugin" / "plugin.json"
HOOKS_PATH = PLUGIN_ROOT / "hooks" / "hooks.json"
MARKETPLACE_PATH = REPO_ROOT / ".agents" / "plugins" / "marketplace.json"
SKILL_NAMES = ("reflect", "reflect-skills", "view-queue", "skip-reflect")
SKILL_BODY = (
    "Report that this workflow is not available in this build. "
    "Do not run scripts or edit files."
)
FINAL_SKILL_SCRIPTS = {
    "reflect": ("../../scripts/commands/reflect.py",),
    "reflect-skills": ("../../scripts/commands/reflect_skills.py",),
    "view-queue": ("../../scripts/read_queue.py",),
    "skip-reflect": (
        "../../scripts/read_queue.py",
        "../../scripts/clear_queue.py",
    ),
}
CAPTURE_COMMAND = 'python3 "${PLUGIN_ROOT}/scripts/capture_learning.py"'
PRECOMPACT_COMMAND = 'python3 "${PLUGIN_ROOT}/scripts/check_learnings.py"'
POST_TOOL_COMMAND = 'python3 "${PLUGIN_ROOT}/scripts/post_commit_reminder.py"'
SESSION_START_COMMAND = (
    'python3 "${PLUGIN_ROOT}/scripts/session_start_reminder.py"'
)
PUBLIC_DOCUMENTATION = (
    REPO_ROOT / "AGENTS.md",
    REPO_ROOT / "CHANGELOG.md",
    REPO_ROOT / "README.md",
    REPO_ROOT / "DISTRIBUTION.md",
    REPO_ROOT / "RELEASING.md",
    REPO_ROOT
    / "docs"
    / "superpowers"
    / "specs"
    / "2026-07-18-codex-reflect-design.md",
    REPO_ROOT
    / "docs"
    / "superpowers"
    / "plans"
    / "2026-07-18-codex-reflect-implementation.md",
)
JAPANESE_PROSE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")


class TestCodexPluginContract(unittest.TestCase):
    def test_public_documentation_is_english(self):
        for path in PUBLIC_DOCUMENTATION:
            with self.subTest(path=path):
                text = path.read_text(encoding="utf-8")
                match = JAPANESE_PROSE.search(text)
                self.assertIsNone(
                    match,
                    f"Japanese prose remains in {path} at offset "
                    f"{match.start() if match else 'unknown'}",
                )

    def test_claude_runtime_manifests_are_removed(self):
        for path in (
            REPO_ROOT / ".claude-plugin",
            REPO_ROOT / "commands",
            REPO_ROOT / "hooks",
            REPO_ROOT / "SKILL.md",
            PLUGIN_ROOT / "scripts" / "legacy",
        ):
            with self.subTest(path=path):
                self.assertFalse(path.exists(), f"obsolete runtime artifact: {path}")

    def test_license_preserves_upstream_notice(self):
        license_text = (REPO_ROOT / "LICENSE").read_text(encoding="utf-8")
        self.assertIn("Copyright (c) 2025 Bayram Annakov", license_text)

    def test_readme_documents_attribution_and_codex_gaps(self):
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        for text in (
            "BayramAnnakov/claude-reflect",
            "Hook trust",
            "transcript",
            "Codex Memories",
            "$CODEX_HOME/codex-reflect",
            "$codex-reflect:reflect",
            "macOS",
            "Linux",
            "Windows",
        ):
            with self.subTest(text=text):
                self.assertIn(text, readme)

    def test_repository_guidance_and_ci_are_codex_native(self):
        self.assertTrue((REPO_ROOT / "AGENTS.md").is_file())
        self.assertFalse((REPO_ROOT / "CLAUDE.md").exists())
        workflow = (
            REPO_ROOT / ".github" / "workflows" / "test.yml"
        ).read_text(encoding="utf-8")
        for text in (
            "ubuntu-latest",
            "macos-latest",
            "windows-latest",
            "'3.8'",
            "'3.11'",
            "plugins/codex-reflect/scripts/session_start_reminder.py",
            ".agents/plugins/marketplace.json",
        ):
            with self.subTest(text=text):
                self.assertIn(text, workflow)

    def test_plugin_runtime_has_no_claude_dependencies(self):
        forbidden = (
            "CLAUDE_PLUGIN_ROOT",
            "CLAUDE_PLUGIN_DATA",
            "~/.claude",
            "claude -p",
            ".claude-plugin",
        )
        for path in PLUGIN_ROOT.rglob("*"):
            if not path.is_file() or path.suffix not in {
                ".json", ".md", ".py", ".sh"
            }:
                continue
            text = path.read_text(encoding="utf-8")
            for token in forbidden:
                with self.subTest(path=path, token=token):
                    self.assertNotIn(token, text)

    def test_manifest_and_skill_discovery_contract(self):
        self.assertTrue(MANIFEST_PATH.is_file(), f"missing {MANIFEST_PATH}")
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

        self.assertEqual(manifest["name"], "codex-reflect")
        self.assertEqual(manifest["skills"], "./skills/")
        self.assertEqual(manifest["hooks"], "./hooks/hooks.json")

        for skill_name in SKILL_NAMES:
            skill_path = PLUGIN_ROOT / "skills" / skill_name / "SKILL.md"
            self.assertTrue(skill_path.is_file(), f"missing {skill_path}")
            skill_text = skill_path.read_text(encoding="utf-8")
            self.assertTrue(skill_text.startswith("---\n"))
            _, frontmatter, body = skill_text.split("---", maxsplit=2)
            self.assertIn(f"name: {skill_name}\n", frontmatter)
            self.assertRegex(frontmatter, r"(?m)^description: Use when .+$")
            if skill_name in FINAL_SKILL_SCRIPTS:
                self.assertNotEqual(body.strip(), SKILL_BODY)
                for script in FINAL_SKILL_SCRIPTS[skill_name]:
                    self.assertIn(script, body)
            else:
                self.assertEqual(body.strip(), SKILL_BODY)

    def test_reflect_skill_contains_review_and_write_gates(self):
        body = (
            PLUGIN_ROOT / "skills" / "reflect" / "SKILL.md"
        ).read_text(encoding="utf-8")
        for keyword in (
            "dry-run",
            "scan-history",
            "apply all",
            "select",
            "details",
            "skip",
            "final confirmation",
            "AGENTS.md",
            "queue",
            "--dedupe",
            "--organize",
        ):
            with self.subTest(keyword=keyword):
                self.assertIn(keyword, body)

    def test_reflect_skills_skill_contains_discovery_and_write_gates(self):
        body = (
            PLUGIN_ROOT / "skills" / "reflect-skills" / "SKILL.md"
        ).read_text(encoding="utf-8")
        for keyword in (
            "multi-step intent",
            "multiple sessions",
            "improvement",
            "evidence count",
            "source projects",
            "final confirmation",
            ".agents/skills",
            "dry-run",
            "read-only",
        ):
            with self.subTest(keyword=keyword):
                self.assertIn(keyword, body)

    def test_repository_marketplace_contract(self):
        self.assertTrue(MARKETPLACE_PATH.is_file(), f"missing {MARKETPLACE_PATH}")
        marketplace = json.loads(MARKETPLACE_PATH.read_text(encoding="utf-8"))

        self.assertEqual(marketplace["plugins"][0]["name"], "codex-reflect")
        self.assertEqual(
            marketplace["plugins"][0]["source"]["path"],
            "./plugins/codex-reflect",
        )

    def test_hook_groups_use_plugin_root(self):
        self.assertTrue(HOOKS_PATH.is_file(), f"missing {HOOKS_PATH}")
        hook_groups = json.loads(HOOKS_PATH.read_text(encoding="utf-8"))["hooks"]

        self.assertEqual(set(hook_groups), {
            "UserPromptSubmit",
            "PreCompact",
            "PostToolUse",
            "SessionStart",
        })
        self.assertNotIn("matcher", hook_groups["UserPromptSubmit"][0])
        self.assertNotIn("matcher", hook_groups["PreCompact"][0])
        self.assertEqual(hook_groups["PostToolUse"][0]["matcher"], "^Bash$")
        self.assertEqual(
            hook_groups["SessionStart"][0]["matcher"],
            "startup|resume|clear|compact",
        )

        user_prompt_handler = hook_groups["UserPromptSubmit"][0]["hooks"][0]
        self.assertEqual(user_prompt_handler["command"], CAPTURE_COMMAND)

        expected_commands = {
            "PreCompact": PRECOMPACT_COMMAND,
            "PostToolUse": POST_TOOL_COMMAND,
            "SessionStart": SESSION_START_COMMAND,
        }
        for event_name, expected_command in expected_commands.items():
            for group in hook_groups[event_name]:
                for handler in group["hooks"]:
                    self.assertEqual(handler["type"], "command")
                    self.assertEqual(handler["command"], expected_command)
                    self.assertIn("${PLUGIN_ROOT}", handler["command"])
                    self.assertNotIn("CLAUDE_PLUGIN_ROOT", handler["command"])

    def test_runtime_package_has_no_phase_zero_probe_reference(self):
        probe_path = PLUGIN_ROOT / "scripts" / "capability_probe_hook.py"
        self.assertFalse(probe_path.exists(), f"obsolete {probe_path}")

        for path in PLUGIN_ROOT.rglob("*"):
            if not path.is_file() or path.suffix not in {
                ".json", ".md", ".py", ".sh"
            }:
                continue
            self.assertNotIn(
                "capability_probe_hook.py",
                path.read_text(encoding="utf-8"),
                f"obsolete probe reference in {path}",
            )


if __name__ == "__main__":
    unittest.main()
