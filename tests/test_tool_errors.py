#!/usr/bin/env python3
"""Tests for tool error extraction functionality."""
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

# Add scripts directory to path
REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = REPO_ROOT / "plugins" / "codex-reflect"
SCRIPTS_DIR = PLUGIN_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from lib.reflect_utils import (
    extract_tool_errors,
    aggregate_tool_errors,
    TOOL_ERROR_EXCLUDE_PATTERNS,
    PROJECT_SPECIFIC_ERROR_PATTERNS,
)
import extract_tool_errors as extract_tool_errors_script


class TestToolErrorPatterns(unittest.TestCase):
    """Tests for error pattern definitions."""

    def test_exclude_patterns_defined(self):
        """Test that exclusion patterns are defined."""
        self.assertIsInstance(TOOL_ERROR_EXCLUDE_PATTERNS, list)
        self.assertGreater(len(TOOL_ERROR_EXCLUDE_PATTERNS), 0)

    def test_project_specific_patterns_defined(self):
        """Test that project-specific patterns are defined."""
        self.assertIsInstance(PROJECT_SPECIFIC_ERROR_PATTERNS, list)
        self.assertGreater(len(PROJECT_SPECIFIC_ERROR_PATTERNS), 0)

    def test_pattern_structure(self):
        """Test that patterns have correct structure."""
        for pattern in PROJECT_SPECIFIC_ERROR_PATTERNS:
            self.assertIsInstance(pattern, tuple)
            self.assertEqual(len(pattern), 3)
            error_type, regex, guideline = pattern
            self.assertIsInstance(error_type, str)
            self.assertIsInstance(regex, str)
            self.assertIsInstance(guideline, str)


class TestExtractToolErrors(unittest.TestCase):
    """Tests for extract_tool_errors function."""

    def setUp(self):
        """Create temporary directory for test files."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temporary files."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_session_file(self, outputs, output_type="custom_tool_call_output"):
        """Create a supported, sanitized Codex session JSONL file."""
        session_file = Path(self.temp_dir) / "test_session.jsonl"
        self._write_session(session_file, outputs, output_type=output_type)
        return session_file

    def _write_session(
        self,
        session_file,
        outputs,
        output_type="custom_tool_call_output",
        cwd="/repo",
    ):
        entries = [
            {
                "type": "session_meta",
                "payload": {
                    "id": "session-1",
                    "cwd": cwd,
                    "timestamp": "2026-07-18T00:00:00Z",
                },
            },
            *[
                {
                    "type": "response_item",
                    "payload": {"type": output_type, "output": output},
                }
                for output in outputs
            ],
        ]
        session_file.write_text(
            "".join(json.dumps(entry) + "\n" for entry in entries),
            encoding="utf-8",
        )

    def test_extract_empty_file(self):
        """Test extraction from empty file."""
        session_file = Path(self.temp_dir) / "empty.jsonl"
        session_file.write_text("")

        result = extract_tool_errors(session_file)
        self.assertEqual(result, [])

    def test_extract_nonexistent_file(self):
        """Test extraction from nonexistent file."""
        session_file = Path(self.temp_dir) / "nonexistent.jsonl"

        result = extract_tool_errors(session_file)
        self.assertEqual(result, [])

    def test_extract_connection_refused_error(self):
        """Test extraction of connection refused errors."""
        session_file = self._create_session_file([
            "Connection refused to localhost:5432"
        ])

        result = extract_tool_errors(session_file, project_specific_only=True)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["error_type"], "connection_refused")
        self.assertIn("Connection refused", result[0]["content"])

    def test_exclude_guardrails(self):
        """Test that generic agent guardrails are excluded."""
        session_file = self._create_session_file([
            "File has not been read yet. Read it first before writing to it."
        ])

        result = extract_tool_errors(session_file, project_specific_only=True)
        self.assertEqual(result, [])

    def test_exclude_user_rejections(self):
        """Test that user rejections are excluded (handled separately)."""
        session_file = self._create_session_file([
            "The user doesn't want to proceed with this tool use."
        ])

        result = extract_tool_errors(session_file, project_specific_only=True)
        self.assertEqual(result, [])

    def test_exclude_bash_quoting_errors(self):
        """Test that bash quoting errors are excluded as non-project-specific."""
        session_file = self._create_session_file([
            "unexpected EOF while looking for matching `'"
        ])

        result = extract_tool_errors(session_file, project_specific_only=True)
        self.assertEqual(result, [])

    def test_extract_supabase_error(self):
        """Test extraction of Supabase-related errors."""
        session_file = self._create_session_file([
            "Error: supabase connection failed - invalid URL"
        ])

        result = extract_tool_errors(session_file, project_specific_only=True)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["error_type"], "supabase_error")
        self.assertIn("SUPABASE", result[0]["suggested_guideline"])

    def test_extract_module_not_found(self):
        """Test extraction of module not found errors."""
        session_file = self._create_session_file([
            "ModuleNotFoundError: No module named 'myapp.utils'"
        ])

        result = extract_tool_errors(session_file, project_specific_only=True)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["error_type"], "module_not_found")

    def test_include_all_errors(self):
        """Test that project_specific_only=False includes unknown errors."""
        session_file = self._create_session_file([
            "Some random unknown error happened"
        ])

        # With project_specific_only=True, should be empty
        result_filtered = extract_tool_errors(session_file, project_specific_only=True)
        self.assertEqual(result_filtered, [])

        # With project_specific_only=False, should be included
        result_all = extract_tool_errors(session_file, project_specific_only=False)
        self.assertEqual(len(result_all), 1)
        self.assertEqual(result_all[0]["error_type"], "unknown")

    def test_skip_function_call_output_shape(self):
        """Only the confirmed custom tool output shape is consumed."""
        session_file = self._create_session_file(
            ["Connection refused to localhost:5432"],
            output_type="function_call_output",
        )

        result = extract_tool_errors(session_file)
        self.assertEqual(result, [])

    def test_skip_successful_outputs_without_error_patterns(self):
        session_file = self._create_session_file([
            "Command completed successfully"
        ])

        result = extract_tool_errors(session_file)
        self.assertEqual(result, [])

    def test_redacts_secret_values_before_returning_error(self):
        session_file = self._create_session_file([
            "Connection refused; API_KEY=secret-value"
        ])

        result = extract_tool_errors(session_file)

        self.assertEqual(len(result), 1)
        self.assertNotIn("secret-value", result[0]["content"])
        self.assertIn("API_KEY=[REDACTED]", result[0]["content"])

    def test_project_scan_skips_malformed_session_and_keeps_valid_neighbors(self):
        codex_home = Path(self.temp_dir) / "codex-home"
        sessions = codex_home / "sessions"
        sessions.mkdir(parents=True)
        project = Path(self.temp_dir) / "project"
        project.mkdir()
        before = sessions / "a-valid.jsonl"
        malformed = sessions / "b-malformed.jsonl"
        after = sessions / "c-valid.jsonl"
        self._write_session(before, ["first"], cwd=str(project))
        malformed.write_text("TOP_SECRET=must-not-be-logged\n", encoding="utf-8")
        self._write_session(after, ["second"], cwd=str(project))
        stderr = StringIO()

        with patch.dict(os.environ, {"CODEX_HOME": str(codex_home)}), redirect_stderr(stderr):
            files = extract_tool_errors_script.find_session_files(
                str(project), all_projects=False
            )

        self.assertEqual(files, [before.resolve(), after.resolve()])
        warning = stderr.getvalue()
        self.assertIn(malformed.name, warning)
        self.assertIn("ValueError", warning)
        self.assertNotIn("TOP_SECRET", warning)
        self.assertNotIn("must-not-be-logged", warning)

    def test_main_skips_malformed_explicit_file_and_aggregates_valid_files(self):
        root = Path(self.temp_dir)
        before = root / "a-valid.jsonl"
        malformed = root / "b-malformed.jsonl"
        after = root / "c-valid.jsonl"
        self._write_session(before, ["Connection refused before"])
        malformed.write_text("TOKEN=must-not-be-logged\n", encoding="utf-8")
        self._write_session(after, ["Connection refused after"])
        stdout = StringIO()
        stderr = StringIO()
        argv = [
            "extract_tool_errors.py",
            str(before),
            str(malformed),
            str(after),
            "--min-count",
            "1",
            "--json",
        ]

        with patch.object(sys, "argv", argv), redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = extract_tool_errors_script.main()

        self.assertEqual(exit_code, 0)
        results = json.loads(stdout.getvalue())
        self.assertEqual(results[0]["error_type"], "connection_refused")
        self.assertEqual(results[0]["count"], 2)
        warning = stderr.getvalue()
        self.assertIn(str(malformed), warning)
        self.assertIn("ValueError", warning)
        self.assertNotIn("TOKEN", warning)
        self.assertNotIn("must-not-be-logged", warning)

    def test_project_scan_skips_unexpandable_cwd_and_keeps_valid_neighbors(self):
        codex_home = Path(self.temp_dir) / "codex-home"
        sessions = codex_home / "sessions"
        sessions.mkdir(parents=True)
        project = Path(self.temp_dir) / "project"
        project.mkdir()
        before = sessions / "a-valid.jsonl"
        invalid_cwd = sessions / "b-invalid-cwd.jsonl"
        after = sessions / "c-valid.jsonl"
        self._write_session(before, ["first"], cwd=str(project))
        self._write_session(
            invalid_cwd,
            ["must-not-be-logged"],
            cwd="~definitely_missing_user",
        )
        self._write_session(after, ["second"], cwd=str(project))
        stderr = StringIO()
        original_expanduser = Path.expanduser

        def expanduser(path):
            if str(path) == "~definitely_missing_user":
                raise RuntimeError("unexpandable user home")
            return original_expanduser(path)

        with patch.object(Path, "expanduser", expanduser), patch.dict(
            os.environ,
            {"CODEX_HOME": str(codex_home)},
        ), redirect_stderr(stderr):
            files = extract_tool_errors_script.find_session_files(
                str(project), all_projects=False
            )

        self.assertEqual(files, [before.resolve(), after.resolve()])
        warning = stderr.getvalue()
        self.assertIn(str(invalid_cwd.name), warning)
        self.assertIn("RuntimeError", warning)
        self.assertNotIn("definitely_missing_user", warning)
        self.assertNotIn("must-not-be-logged", warning)

    def test_main_skips_recursion_error_and_keeps_valid_neighbors(self):
        root = Path(self.temp_dir)
        before = root / "a-valid.jsonl"
        recursive = root / "b-recursive.jsonl"
        after = root / "c-valid.jsonl"
        self._write_session(before, ["Connection refused before"])
        recursive.write_text(
            '{"type":"session_meta","payload":{"id":"recursive"}}\n'
            '{"type":"response_item","payload":'
            '{"type":"custom_tool_call_output","output":'
            + "[" * 2000
            + '"deep-secret-value"'
            + "]" * 2000
            + "}}\n",
            encoding="utf-8",
        )
        self._write_session(after, ["Connection refused after"])
        stdout = StringIO()
        stderr = StringIO()
        argv = [
            "extract_tool_errors.py",
            str(before),
            str(recursive),
            str(after),
            "--min-count",
            "1",
            "--json",
        ]

        with patch.object(sys, "argv", argv), redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = extract_tool_errors_script.main()

        self.assertEqual(exit_code, 0)
        results = json.loads(stdout.getvalue())
        self.assertEqual(results[0]["error_type"], "connection_refused")
        self.assertEqual(results[0]["count"], 2)
        warning = stderr.getvalue()
        self.assertIn(str(recursive), warning)
        self.assertIn("RecursionError", warning)
        self.assertNotIn("deep-secret-value", warning)


class TestAggregateToolErrors(unittest.TestCase):
    """Tests for aggregate_tool_errors function."""

    def test_aggregate_empty_list(self):
        """Test aggregation of empty list."""
        result = aggregate_tool_errors([])
        self.assertEqual(result, [])

    def test_aggregate_below_threshold(self):
        """Test that errors below threshold are filtered out."""
        errors = [
            {"error_type": "connection_refused", "content": "error1", "suggested_guideline": "test"},
        ]

        result = aggregate_tool_errors(errors, min_occurrences=2)
        self.assertEqual(result, [])

    def test_aggregate_at_threshold(self):
        """Test that errors at threshold are included."""
        errors = [
            {"error_type": "connection_refused", "content": "error1", "suggested_guideline": "test"},
            {"error_type": "connection_refused", "content": "error2", "suggested_guideline": "test"},
        ]

        result = aggregate_tool_errors(errors, min_occurrences=2)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["error_type"], "connection_refused")
        self.assertEqual(result[0]["count"], 2)

    def test_aggregate_confidence_scaling(self):
        """Test that confidence scales with occurrence count."""
        errors_2 = [{"error_type": "test", "content": f"error{i}", "suggested_guideline": "test"}
                    for i in range(2)]
        errors_3 = [{"error_type": "test", "content": f"error{i}", "suggested_guideline": "test"}
                    for i in range(3)]
        errors_5 = [{"error_type": "test", "content": f"error{i}", "suggested_guideline": "test"}
                    for i in range(5)]

        result_2 = aggregate_tool_errors(errors_2, min_occurrences=2)
        result_3 = aggregate_tool_errors(errors_3, min_occurrences=2)
        result_5 = aggregate_tool_errors(errors_5, min_occurrences=2)

        self.assertEqual(result_2[0]["confidence"], 0.70)
        self.assertEqual(result_3[0]["confidence"], 0.85)
        self.assertEqual(result_5[0]["confidence"], 0.90)

    def test_aggregate_multiple_types(self):
        """Test aggregation of multiple error types."""
        errors = [
            {"error_type": "connection_refused", "content": "err1", "suggested_guideline": "fix1"},
            {"error_type": "connection_refused", "content": "err2", "suggested_guideline": "fix1"},
            {"error_type": "module_not_found", "content": "err3", "suggested_guideline": "fix2"},
            {"error_type": "module_not_found", "content": "err4", "suggested_guideline": "fix2"},
            {"error_type": "module_not_found", "content": "err5", "suggested_guideline": "fix2"},
            {"error_type": "single_error", "content": "err6", "suggested_guideline": "fix3"},
        ]

        result = aggregate_tool_errors(errors, min_occurrences=2)

        self.assertEqual(len(result), 2)
        # Should be sorted by count descending
        self.assertEqual(result[0]["error_type"], "module_not_found")
        self.assertEqual(result[0]["count"], 3)
        self.assertEqual(result[1]["error_type"], "connection_refused")
        self.assertEqual(result[1]["count"], 2)

    def test_aggregate_sample_errors_limit(self):
        """Test that sample_errors is limited to 3 items."""
        errors = [{"error_type": "test", "content": f"error{i}", "suggested_guideline": "test"}
                  for i in range(10)]

        result = aggregate_tool_errors(errors, min_occurrences=2)

        self.assertEqual(len(result), 1)
        self.assertLessEqual(len(result[0]["sample_errors"]), 3)


if __name__ == "__main__":
    unittest.main()
