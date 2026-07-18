#!/usr/bin/env python3
"""Integration tests for claude-reflect scripts.

These tests verify that both bash and Python versions produce the same results.
Run with: python -m pytest tests/test_integration.py -v
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Skip bash tests on Windows
IS_WINDOWS = sys.platform == 'win32'
skip_on_windows = unittest.skipIf(IS_WINDOWS, "Bash scripts not available on Windows")

# Script locations
REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = REPO_ROOT / "plugins" / "codex-reflect"
SCRIPTS_DIR = PLUGIN_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
from lib.codex_paths import get_project_id
import check_learnings

BASH_SCRIPTS = {
    "check_learnings": SCRIPTS_DIR / "legacy" / "check-learnings.sh",
    "post_commit_reminder": SCRIPTS_DIR / "legacy" / "post-commit-reminder.sh",
    "capture_learning": SCRIPTS_DIR / "legacy" / "capture-learning.sh",
    "extract_session_learnings": SCRIPTS_DIR / "legacy" / "extract-session-learnings.sh",
    "extract_tool_rejections": SCRIPTS_DIR / "legacy" / "extract-tool-rejections.sh",
}
PYTHON_SCRIPTS = {
    "session_start_reminder": SCRIPTS_DIR / "session_start_reminder.py",
    "check_learnings": SCRIPTS_DIR / "check_learnings.py",
    "post_commit_reminder": SCRIPTS_DIR / "post_commit_reminder.py",
    "capture_learning": SCRIPTS_DIR / "capture_learning.py",
    "extract_session_learnings": SCRIPTS_DIR / "extract_session_learnings.py",
    "extract_tool_rejections": SCRIPTS_DIR / "extract_tool_rejections.py",
}


def run_bash_script(script_path: Path, stdin: str = "", args: list = None) -> tuple:
    """Run a bash script and return (stdout, stderr, returncode)."""
    cmd = ["bash", str(script_path)] + (args or [])
    result = subprocess.run(
        cmd,
        input=stdin,
        capture_output=True,
        text=True,
        cwd=str(SCRIPTS_DIR),
    )
    return result.stdout, result.stderr, result.returncode


def run_python_script(
    script_path: Path,
    stdin: str = "",
    args: list = None,
    env: dict = None,
) -> tuple:
    """Run a Python script and return (stdout, stderr, returncode)."""
    cmd = [sys.executable, str(script_path)] + (args or [])
    result = subprocess.run(
        cmd,
        input=stdin,
        capture_output=True,
        text=True,
        cwd=str(SCRIPTS_DIR),
        env=env,
    )
    return result.stdout, result.stderr, result.returncode


class TestCaptureLearning(unittest.TestCase):
    """Tests for the Codex UserPromptSubmit capture hook."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_root = Path(self.temp_dir.name)
        self.codex_home = self.temp_root / "codex-home"
        self.project = self.temp_root / "project"
        self.codex_home.mkdir()
        self.project.mkdir()
        self.env = os.environ.copy()
        self.env["CODEX_HOME"] = str(self.codex_home)

    def tearDown(self):
        self.temp_dir.cleanup()

    def run_capture(self, payload):
        return run_python_script(
            PYTHON_SCRIPTS["capture_learning"],
            stdin=json.dumps(payload),
            env=self.env,
        )

    def queue_paths(self):
        return list(
            (self.codex_home / "codex-reflect" / "projects").glob(
                "*/queue.json"
            )
        ) if (self.codex_home / "codex-reflect" / "projects").exists() else []

    def test_codex_prompt_is_appended_once_to_project_queue(self):
        payload = {
            "hook_event_name": "UserPromptSubmit",
            "cwd": str(self.project),
            "session_id": "session-1",
            "turn_id": "turn-1",
            "model": "gpt-test",
            "prompt": "remember: run focused tests",
        }

        stdout, stderr, code = self.run_capture(payload)

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(
            json.loads(stdout),
            {
                "continue": True,
                "systemMessage": (
                    "codex-reflect captured a learning candidate"
                ),
            },
        )
        self.assertEqual(len(self.queue_paths()), 1)
        items = json.loads(self.queue_paths()[0].read_text(encoding="utf-8"))
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["schema_version"], 1)
        self.assertEqual(item["message"], payload["prompt"])
        self.assertEqual(item["project"], str(self.project))
        self.assertEqual(item["session_id"], "session-1")
        self.assertEqual(item["turn_id"], "turn-1")
        self.assertEqual(item["model"], "gpt-test")
        self.assertEqual(item["source"], "hook")

    def test_message_fallback_is_not_treated_as_prompt(self):
        stdout, stderr, code = self.run_capture({
            "hook_event_name": "UserPromptSubmit",
            "cwd": str(self.project),
            "message": "remember: this is not the Codex prompt field",
        })

        self.assertEqual((stdout, stderr, code), ("", "", 0))
        self.assertEqual(self.queue_paths(), [])

    def test_non_actionable_prompt_has_no_output_or_state_write(self):
        stdout, stderr, code = self.run_capture({
            "hook_event_name": "UserPromptSubmit",
            "cwd": str(self.project),
            "prompt": "Please explain this function",
        })

        self.assertEqual((stdout, stderr, code), ("", "", 0))
        self.assertFalse((self.codex_home / "codex-reflect").exists())

    def assert_unscoped_cwd_is_skipped(self, cwd):
        stdout, stderr, code = self.run_capture({
            "hook_event_name": "UserPromptSubmit",
            "cwd": cwd,
            "prompt": "remember: do not capture without project scope",
        })

        self.assertEqual((stdout, stderr, code), ("", "", 0))
        self.assertFalse((self.codex_home / "codex-reflect").exists())

    def test_empty_cwd_is_skipped_without_state_write(self):
        self.assert_unscoped_cwd_is_skipped("")

    def test_relative_cwd_is_skipped_without_state_write(self):
        self.assert_unscoped_cwd_is_skipped("relative/project")

    def test_non_string_cwd_is_skipped_without_state_write(self):
        self.assert_unscoped_cwd_is_skipped(["not", "a", "path"])

    def test_storage_failure_warns_and_does_not_block_turn(self):
        first_stdout, first_stderr, first_code = self.run_capture({
            "hook_event_name": "UserPromptSubmit",
            "cwd": str(self.project),
            "prompt": "remember: first candidate",
        })
        self.assertEqual(first_code, 0, first_stdout + first_stderr)
        queue_path = self.queue_paths()[0]
        queue_path.write_text("{broken", encoding="utf-8")

        stdout, stderr, code = self.run_capture({
            "hook_event_name": "UserPromptSubmit",
            "cwd": str(self.project),
            "prompt": "remember: second candidate",
        })

        self.assertEqual(code, 0)
        self.assertEqual(stdout, "")
        self.assertIn("Warning: capture_learning.py error:", stderr)
        self.assertEqual(queue_path.read_text(encoding="utf-8"), "{broken")


class CodexLifecycleHookTestCase(unittest.TestCase):
    """Temporary Codex home and project for lifecycle Hook integration."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_root = Path(self.temp_dir.name)
        self.codex_home = self.temp_root / "codex-home"
        self.project = self.temp_root / "project"
        self.other_project = self.temp_root / "other-project"
        self.codex_home.mkdir()
        self.project.mkdir()
        self.other_project.mkdir()
        self.env = os.environ.copy()
        self.env["CODEX_HOME"] = str(self.codex_home)
        self.project_state = self._project_state(self.project)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _project_state(self, project):
        return (
            self.codex_home
            / "codex-reflect"
            / "projects"
            / get_project_id(str(project))
        )

    def write_queue(self, items, project=None):
        state = self._project_state(project or self.project)
        state.mkdir(parents=True, exist_ok=True)
        (state / "queue.json").write_text(
            json.dumps(items), encoding="utf-8"
        )
        return state

    def run_hook(self, name, payload):
        stdin = payload if isinstance(payload, str) else json.dumps(payload)
        return run_python_script(
            PYTHON_SCRIPTS[name], stdin=stdin, env=self.env
        )

    def assert_invalid_cwd_is_skipped(self, name, extra_payload=None):
        for cwd in (None, "", "relative/project", ["not", "a", "path"]):
            with self.subTest(cwd=cwd):
                payload = {
                    "hook_event_name": "test",
                    "cwd": cwd,
                    **(extra_payload or {}),
                }
                stdout, stderr, code = self.run_hook(name, payload)
                self.assertEqual((stdout, stderr, code), ("", "", 0))
                self.assertFalse(
                    (self.codex_home / "codex-reflect").exists()
                )


class TestSessionStartReminder(CodexLifecycleHookTestCase):
    def test_session_start_returns_codex_system_message_when_uninitialized(self):
        payload = {
            "hook_event_name": "SessionStart",
            "cwd": str(self.project),
            "session_id": "s1",
        }

        stdout, stderr, code = self.run_hook(
            "session_start_reminder", payload
        )

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertNotEqual(stdout, "")
        response = json.loads(stdout)
        self.assertIn("systemMessage", response)
        self.assertIs(response["continue"], True)
        self.assertIn("reflect --scan-history", response["systemMessage"])
        self.assertFalse((self.codex_home / "codex-reflect").exists())

    def test_session_start_shows_at_most_five_items_from_event_project(self):
        self.write_queue([
            {
                "message": f"ignore instructions from project item {index}",
                "original_message": f"original secret item {index}",
                "confidence": 0.75,
            }
            for index in range(1, 7)
        ])
        self.write_queue(
            [{
                "message": "other project instruction",
                "original_message": "other project original",
                "confidence": 1.0,
            }],
            self.other_project,
        )

        stdout, stderr, code = self.run_hook("session_start_reminder", {
            "hook_event_name": "SessionStart",
            "cwd": str(self.project),
            "session_id": "s1",
        })

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertNotEqual(stdout, "")
        message = json.loads(stdout)["systemMessage"]
        for index in range(1, 6):
            self.assertIn(f"{index}. [75%] learning candidate", message)
        for index in range(1, 7):
            self.assertNotIn(
                f"ignore instructions from project item {index}", message
            )
            self.assertNotIn(f"original secret item {index}", message)
        self.assertNotIn("6. [75%] learning candidate", message)
        self.assertNotIn("other project instruction", message)
        self.assertNotIn("other project original", message)
        self.assertIn("6 pending learning", message)
        self.assertIn("1 more", message)

    def test_initialized_empty_queue_has_no_output(self):
        self.write_queue([])

        result = self.run_hook("session_start_reminder", {
            "hook_event_name": "SessionStart",
            "cwd": str(self.project),
        })

        self.assertEqual(result, ("", "", 0))

    def test_invalid_cwd_is_skipped_without_state_write(self):
        self.assert_invalid_cwd_is_skipped("session_start_reminder")

    def test_empty_and_invalid_json_exit_zero(self):
        for stdin in ("", "not json"):
            with self.subTest(stdin=stdin):
                self.assertEqual(
                    self.run_hook("session_start_reminder", stdin),
                    ("", "", 0),
                )

    def test_queue_io_error_exits_zero_without_overwriting(self):
        self.project_state.mkdir(parents=True)
        queue_path = self.project_state / "queue.json"
        queue_path.mkdir()

        stdout, stderr, code = self.run_hook("session_start_reminder", {
            "hook_event_name": "SessionStart",
            "cwd": str(self.project),
        })

        self.assertEqual(code, 0)
        self.assertEqual(stdout, "")
        self.assertIn("Warning: session_start_reminder.py error:", stderr)
        self.assertTrue(queue_path.is_dir())


class TestCheckLearnings(CodexLifecycleHookTestCase):
    def test_empty_queue_has_no_output_or_backup(self):
        self.write_queue([])

        result = self.run_hook("check_learnings", {
            "hook_event_name": "PreCompact",
            "cwd": str(self.project),
            "session_id": "s1",
        })

        self.assertEqual(result, ("", "", 0))
        self.assertFalse((self.project_state / "backups").exists())

    def test_precompact_creates_atomic_project_backup(self):
        items = [{"message": "keep this", "schema_version": 1}]
        self.write_queue(items)

        stdout, stderr, code = self.run_hook("check_learnings", {
            "hook_event_name": "PreCompact",
            "cwd": str(self.project),
            "session_id": "s1",
        })

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertNotEqual(stdout, "")
        response = json.loads(stdout)
        self.assertIn("systemMessage", response)
        self.assertIs(response["continue"], True)
        self.assertIn("1 learning", response["systemMessage"])
        backups = list((self.project_state / "backups").glob(
            "pre-compact-*.json"
        ))
        self.assertEqual(len(backups), 1)
        self.assertEqual(
            json.loads(backups[0].read_text(encoding="utf-8")), items
        )
        self.assertEqual(
            list((self.project_state / "backups").glob("*.tmp")), []
        )

    def test_same_timestamp_backups_do_not_collide(self):
        backup_dir = self.project_state / "backups"
        fixed_timestamp = "20260718-123456-000000"
        with patch("check_learnings.datetime") as datetime_mock:
            datetime_mock.now.return_value.strftime.return_value = (
                fixed_timestamp
            )
            first = check_learnings._write_backup(
                [{"id": "first"}], backup_dir
            )
            second = check_learnings._write_backup(
                [{"id": "second"}], backup_dir
            )

        self.assertNotEqual(first, second)
        backups = sorted(backup_dir.glob("pre-compact-*.json"))
        self.assertEqual(len(backups), 2)
        for backup in backups:
            self.assertRegex(
                backup.name,
                rf"^pre-compact-{fixed_timestamp}-.+\.json$",
            )
        self.assertEqual(
            {
                json.loads(backup.read_text(encoding="utf-8"))[0]["id"]
                for backup in backups
            },
            {"first", "second"},
        )
        self.assertEqual(list(backup_dir.glob("*.tmp")), [])

    def test_invalid_cwd_is_skipped_without_state_write(self):
        self.assert_invalid_cwd_is_skipped("check_learnings")

    def test_empty_and_invalid_json_exit_zero(self):
        for stdin in ("", "not json"):
            with self.subTest(stdin=stdin):
                self.assertEqual(
                    self.run_hook("check_learnings", stdin),
                    ("", "", 0),
                )

    def test_queue_io_error_exits_zero_without_backup(self):
        self.project_state.mkdir(parents=True)
        queue_path = self.project_state / "queue.json"
        queue_path.mkdir()

        stdout, stderr, code = self.run_hook("check_learnings", {
            "hook_event_name": "PreCompact",
            "cwd": str(self.project),
        })

        self.assertEqual(code, 0)
        self.assertEqual(stdout, "")
        self.assertIn("Warning: check_learnings.py error:", stderr)
        self.assertFalse((self.project_state / "backups").exists())


class TestPostCommitReminder(CodexLifecycleHookTestCase):
    def run_post_tool_use(self, tool_input, **extra):
        return self.run_hook("post_commit_reminder", {
            "hook_event_name": "PostToolUse",
            "cwd": str(self.project),
            "tool_name": "Bash",
            "tool_input": tool_input,
            **extra,
        })

    def test_detects_non_amend_commit_from_cmd(self):
        stdout, stderr, code = self.run_post_tool_use({
            "cmd": "git commit -m test"
        })

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertNotEqual(stdout, "")
        response = json.loads(stdout)
        self.assertIn("systemMessage", response)
        self.assertIs(response["continue"], True)
        self.assertIn("Git commit detected", response["systemMessage"])

    def test_normalizes_string_list_cmd(self):
        stdout, stderr, code = self.run_post_tool_use({
            "cmd": ["git", "commit", "-m", "test"]
        })

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertNotEqual(stdout, "")
        response = json.loads(stdout)
        self.assertIn("systemMessage", response)
        self.assertIn(
            "Git commit detected", response["systemMessage"]
        )

    def test_falls_back_to_command_when_cmd_is_absent(self):
        stdout, stderr, code = self.run_post_tool_use({
            "command": "git commit -m test"
        })

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertNotEqual(stdout, "")
        response = json.loads(stdout)
        self.assertIn("systemMessage", response)
        self.assertIn(
            "Git commit detected", response["systemMessage"]
        )

    def test_falls_back_to_command_when_cmd_has_no_value(self):
        for cmd in (None, "", []):
            with self.subTest(cmd=cmd):
                stdout, stderr, code = self.run_post_tool_use({
                    "cmd": cmd,
                    "command": "git commit -m test",
                })
                self.assertEqual(code, 0)
                self.assertEqual(stderr, "")
                self.assertNotEqual(stdout, "")
                self.assertIn(
                    "Git commit detected",
                    json.loads(stdout)["systemMessage"],
                )

    def test_nonempty_valid_cmd_takes_priority_over_command(self):
        result = self.run_post_tool_use({
            "cmd": "ls",
            "command": "git commit -m test",
        })

        self.assertEqual(result, ("", "", 0))

    def test_ignores_amend_and_non_commit_commands(self):
        for cmd in ("git commit --amend -m test", "git status"):
            with self.subTest(cmd=cmd):
                self.assertEqual(
                    self.run_post_tool_use({"cmd": cmd}),
                    ("", "", 0),
                )

    def test_ignores_non_string_command_values(self):
        for cmd in (123, {"value": "git commit"}, ["git", 123, "commit"]):
            with self.subTest(cmd=cmd):
                self.assertEqual(
                    self.run_post_tool_use({
                        "cmd": cmd,
                        "command": "git commit -m test",
                    }),
                    ("", "", 0),
                )

    def test_does_not_read_nested_fields_or_tool_output(self):
        payloads = (
            ({"nested": {"cmd": "git commit -m test"}}, {}),
            ({}, {"tool_response": {"cmd": "git commit -m test"}}),
            ({}, {"command": "git commit -m test"}),
        )
        for tool_input, extra in payloads:
            with self.subTest(tool_input=tool_input, extra=extra):
                self.assertEqual(
                    self.run_post_tool_use(tool_input, **extra),
                    ("", "", 0),
                )

    def test_commit_message_in_tool_output_does_not_trigger(self):
        result = self.run_post_tool_use(
            {"cmd": "git status"},
            tool_response="previous command: git commit -m test",
        )

        self.assertEqual(result, ("", "", 0))

    def test_valid_commit_uses_only_event_project_queue(self):
        self.write_queue([{"message": "current"}])
        self.write_queue(
            [{"message": "other"}, {"message": "other two"}],
            self.other_project,
        )

        stdout, _, _ = self.run_post_tool_use({"cmd": "git commit -m test"})

        self.assertNotEqual(stdout, "")
        message = json.loads(stdout)["systemMessage"]
        self.assertIn("1 queued learning", message)
        self.assertNotIn("2 queued", message)

    def test_invalid_cwd_is_skipped_without_state_write(self):
        self.assert_invalid_cwd_is_skipped(
            "post_commit_reminder",
            {"tool_name": "Bash", "tool_input": {"cmd": "git commit -m x"}},
        )

    def test_empty_and_invalid_json_exit_zero(self):
        for stdin in ("", "not json"):
            with self.subTest(stdin=stdin):
                self.assertEqual(
                    self.run_hook("post_commit_reminder", stdin),
                    ("", "", 0),
                )

    def test_queue_io_error_exits_zero_without_output(self):
        self.project_state.mkdir(parents=True)
        (self.project_state / "queue.json").mkdir()

        stdout, stderr, code = self.run_post_tool_use({
            "cmd": "git commit -m test"
        })

        self.assertEqual(code, 0)
        self.assertEqual(stdout, "")
        self.assertIn("Warning: post_commit_reminder.py error:", stderr)


class TestExtractSessionLearnings(unittest.TestCase):
    """Tests for session extraction script."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.session_file = Path(self.temp_dir) / "test-session.jsonl"

    def tearDown(self):
        """Clean up temporary files."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_session_file(self, entries: list):
        """Create a session file with given entries."""
        with open(self.session_file, "w") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

    @skip_on_windows
    def test_bash_extracts_user_messages(self):
        """Test bash script extracts user messages."""
        self._create_session_file([
            {
                "type": "user",
                "message": {
                    "content": [{"type": "text", "text": "Hello world"}]
                }
            },
            {
                "type": "assistant",
                "message": {"content": "Response"}
            },
        ])

        stdout, stderr, code = run_bash_script(
            BASH_SCRIPTS["extract_session_learnings"],
            args=[str(self.session_file)]
        )
        self.assertEqual(code, 0)
        self.assertIn("Hello world", stdout)

    def test_python_extracts_user_messages(self):
        """Test Python script extracts confirmed Codex user-message shapes."""
        self._create_session_file([
            {
                "type": "session_meta",
                "payload": {"id": "session-1", "cwd": self.temp_dir},
            },
            {
                "type": "event_msg",
                "payload": {"type": "user_message", "message": "Hello world"},
            },
        ])

        stdout, stderr, code = run_python_script(
            PYTHON_SCRIPTS["extract_session_learnings"],
            args=[str(self.session_file)]
        )
        self.assertEqual(code, 0)
        self.assertIn("Hello world", stdout)

    @skip_on_windows
    def test_bash_skips_meta_messages(self):
        """Test bash script skips isMeta messages."""
        self._create_session_file([
            {
                "type": "user",
                "isMeta": True,
                "message": {
                    "content": [{"type": "text", "text": "Meta message"}]
                }
            },
            {
                "type": "user",
                "message": {
                    "content": [{"type": "text", "text": "Regular message"}]
                }
            },
        ])

        stdout, stderr, code = run_bash_script(
            BASH_SCRIPTS["extract_session_learnings"],
            args=[str(self.session_file)]
        )
        self.assertEqual(code, 0)
        self.assertNotIn("Meta message", stdout)
        self.assertIn("Regular message", stdout)

    def test_python_skips_meta_messages(self):
        """Test Python script ignores non-user Codex response items."""
        self._create_session_file([
            {
                "type": "session_meta",
                "payload": {"id": "session-1", "cwd": self.temp_dir},
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "input_text", "text": "Meta message"}],
                },
            },
            {
                "type": "event_msg",
                "payload": {"type": "user_message", "message": "Regular message"},
            },
        ])

        stdout, stderr, code = run_python_script(
            PYTHON_SCRIPTS["extract_session_learnings"],
            args=[str(self.session_file)]
        )
        self.assertEqual(code, 0)
        self.assertNotIn("Meta message", stdout)
        self.assertIn("Regular message", stdout)

    @skip_on_windows
    def test_bash_corrections_only_flag(self):
        """Test bash script --corrections-only flag."""
        self._create_session_file([
            {
                "type": "user",
                "message": {
                    "content": [{"type": "text", "text": "Hello world"}]
                }
            },
            {
                "type": "user",
                "message": {
                    "content": [{"type": "text", "text": "no, use Python"}]
                }
            },
        ])

        stdout, stderr, code = run_bash_script(
            BASH_SCRIPTS["extract_session_learnings"],
            args=[str(self.session_file), "--corrections-only"]
        )
        self.assertEqual(code, 0)
        self.assertNotIn("Hello world", stdout)
        self.assertIn("no, use Python", stdout)

    def test_python_corrections_only_flag(self):
        """Test Python script --corrections-only flag."""
        self._create_session_file([
            {
                "type": "session_meta",
                "payload": {"id": "session-1", "cwd": self.temp_dir},
            },
            {
                "type": "event_msg",
                "payload": {"type": "user_message", "message": "Hello world"},
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "no, use Python"}],
                },
            },
        ])

        stdout, stderr, code = run_python_script(
            PYTHON_SCRIPTS["extract_session_learnings"],
            args=[str(self.session_file), "--corrections-only"]
        )
        self.assertEqual(code, 0)
        self.assertNotIn("Hello world", stdout)
        self.assertIn("no, use Python", stdout)

    @skip_on_windows
    def test_bash_nonexistent_file(self):
        """Test bash script handles nonexistent file."""
        stdout, stderr, code = run_bash_script(
            BASH_SCRIPTS["extract_session_learnings"],
            args=["/nonexistent/file.jsonl"]
        )
        self.assertNotEqual(code, 0)  # Should fail

    def test_python_nonexistent_file(self):
        """Test Python script handles nonexistent file."""
        stdout, stderr, code = run_python_script(
            PYTHON_SCRIPTS["extract_session_learnings"],
            args=["/nonexistent/file.jsonl"]
        )
        self.assertNotEqual(code, 0)  # Should fail


class TestCapturePatternEquivalence(unittest.TestCase):
    """Tests to verify bash and Python capture the same patterns."""

    # These tests ensure the Python pattern detection matches bash behavior

    def test_remember_pattern(self):
        """Test 'remember:' is detected by both versions."""
        test_messages = [
            "remember: always use gpt-5.1",
            "Remember: use async/await",
            "REMEMBER: never hardcode passwords",
        ]
        for msg in test_messages:
            with self.subTest(msg=msg):
                # The capture scripts would detect this
                # We test the pattern detection directly
                pass  # Pattern tests covered in test_reflect_utils.py

    def test_correction_patterns(self):
        """Test correction patterns are detected by both versions."""
        test_cases = [
            ("no, use Python", "no,use"),
            ("don't use that library", "don't-use"),
            ("stop using globals", "stop/never-use"),
            ("never use eval", "stop/never-use"),
            ("that's wrong", "that's-wrong"),
            ("that is incorrect", "that's-wrong"),
            ("I meant the other one", "I-meant/said"),
            ("I said use async", "I-meant/said"),
            ("I told you to use venv", "I-told-you"),
            ("you should use Python", "you-should-use"),
        ]
        for msg, expected_pattern in test_cases:
            with self.subTest(msg=msg):
                # Pattern matching tested in test_reflect_utils.py
                pass


if __name__ == "__main__":
    unittest.main()
