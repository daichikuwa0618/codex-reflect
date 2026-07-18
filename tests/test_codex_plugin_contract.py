#!/usr/bin/env python3
"""Contract tests for the nested Codex plugin package."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = REPO_ROOT / "plugins" / "codex-reflect"
MANIFEST_PATH = PLUGIN_ROOT / ".codex-plugin" / "plugin.json"
HOOKS_PATH = PLUGIN_ROOT / "hooks" / "hooks.json"
MARKETPLACE_PATH = REPO_ROOT / ".agents" / "plugins" / "marketplace.json"
PROBE_PATH = PLUGIN_ROOT / "scripts" / "capability_probe_hook.py"
SKILL_NAMES = ("reflect", "reflect-skills", "view-queue", "skip-reflect")
SKILL_BODY = (
    "Resolve `../../scripts/capability_probe_hook.py` relative to this SKILL.md "
    'and run it with stdin `{"hook_event_name":"SkillProbe"}`. Report its '
    "`systemMessage` and do not edit files."
)
PROBE_COMMAND = 'python3 "${PLUGIN_ROOT}/scripts/capability_probe_hook.py"'
CAPTURE_COMMAND = 'python3 "${PLUGIN_ROOT}/scripts/capture_learning.py"'


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

        for event_name in ("PreCompact", "PostToolUse", "SessionStart"):
            for group in hook_groups[event_name]:
                for handler in group["hooks"]:
                    self.assertEqual(handler["type"], "command")
                    self.assertEqual(handler["command"], PROBE_COMMAND)
                    self.assertIn("${PLUGIN_ROOT}", handler["command"])
                    self.assertNotIn("CLAUDE_PLUGIN_ROOT", handler["command"])

    def test_capability_probe_is_write_free_and_reports_only_field_names(self):
        self.assertTrue(PROBE_PATH.is_file(), f"missing {PROBE_PATH}")
        payload = {
            "hook_event_name": "PostToolUse",
            "session_id": "secret-session-value",
            "prompt": "secret prompt value",
            "tool_input": {
                "command": "secret command value",
                "path": "secret path value",
            },
            "ignored_field": "secret ignored value",
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            codex_home = temp_root / "codex-home"
            codex_home.mkdir()
            project_dir = temp_root / "project"
            project_dir.mkdir()
            state_root = codex_home / "codex-reflect"
            env = os.environ.copy()
            env["CODEX_HOME"] = str(codex_home)

            result = subprocess.run(
                [sys.executable, str(PROBE_PATH)],
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                cwd=project_dir,
                env=env,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            output = json.loads(result.stdout)
            self.assertIs(output["continue"], True)
            message = output["systemMessage"]
            self.assertIn("PostToolUse", message)
            self.assertIn(
                "fields=hook_event_name,prompt,session_id,tool_input",
                message,
            )
            self.assertIn("tool_input_fields=command,path", message)
            self.assertIn(f"state_root={state_root}", message)
            for secret_value in (
                "secret-session-value",
                "secret prompt value",
                "secret command value",
                "secret path value",
                "secret ignored value",
            ):
                self.assertNotIn(secret_value, message)
            self.assertFalse(state_root.exists())
            self.assertEqual(list(project_dir.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
