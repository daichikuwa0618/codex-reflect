#!/usr/bin/env python3
"""Contract tests for the nested Codex plugin package."""

import json
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
QUEUE_SKILL_SCRIPTS = {
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


class TestCodexPluginContract(unittest.TestCase):
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
            if skill_name in QUEUE_SKILL_SCRIPTS:
                self.assertNotEqual(body.strip(), SKILL_BODY)
                for script in QUEUE_SKILL_SCRIPTS[skill_name]:
                    self.assertIn(script, body)
            else:
                self.assertEqual(body.strip(), SKILL_BODY)

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
