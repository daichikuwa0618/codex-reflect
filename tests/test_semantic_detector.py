#!/usr/bin/env python3
"""Tests for semantic_detector module.

These tests mock subprocess.run to avoid actual Codex CLI calls.
Run with: python -m pytest tests/test_semantic_detector.py -v
"""
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add scripts directory to path
REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = REPO_ROOT / "plugins" / "codex-reflect"
SCRIPTS_DIR = PLUGIN_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from lib.semantic_detector import (
    semantic_analyze,
    validate_tool_error,
    validate_queue_items,
    detect_contradictions,
    _extract_json_from_text,
    _validate_response,
    ANALYSIS_PROMPT,
    DEFAULT_TIMEOUT,
)


def _codex_run_with_response(response_dict):
    """Return a subprocess side effect that writes Codex structured output."""
    def fake_run(command, **kwargs):
        output_index = command.index("--output-last-message") + 1
        Path(command[output_index]).write_text(
            json.dumps(response_dict), encoding="utf-8"
        )
        return subprocess.CompletedProcess(command, 0, "", "")

    return fake_run


def _codex_run_with_raw_output(value):
    def fake_run(command, **kwargs):
        output_index = command.index("--output-last-message") + 1
        Path(command[output_index]).write_text(value, encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    return fake_run


class TestSemanticAnalyze(unittest.TestCase):
    """Tests for semantic_analyze function."""

    def _mock_codex_response(self, response_dict):
        return _codex_run_with_response(response_dict)

    @patch("lib.semantic_detector.subprocess.run")
    def test_codex_exec_contract_is_ephemeral_read_only_and_hook_free(
        self, mock_run
    ):
        mock_run.side_effect = _codex_run_with_response({
            "is_learning": True,
            "type": "correction",
            "confidence": 0.9,
            "reasoning": "Reusable correction",
            "extracted_learning": "Use rg instead of grep",
        })

        semantic_analyze("no, use rg", model="gpt-test")

        command = mock_run.call_args.args[0]
        self.assertEqual(command[:2], ["codex", "exec"])
        self.assertIn("--ephemeral", command)
        self.assertEqual(command[command.index("--disable") + 1], "hooks")
        self.assertEqual(
            command[command.index("--sandbox") + 1], "read-only"
        )
        self.assertEqual(command[command.index("--model") + 1], "gpt-test")
        self.assertEqual(command[-1], "-")

    @patch("lib.semantic_detector.subprocess.run")
    def test_codex_exec_uses_current_default_model_when_unspecified(
        self, mock_run
    ):
        mock_run.side_effect = _codex_run_with_response({
            "is_learning": False,
            "type": None,
            "confidence": 0,
            "reasoning": "Not reusable",
            "extracted_learning": None,
        })

        semantic_analyze("hello")

        self.assertNotIn("--model", mock_run.call_args.args[0])

    @patch("lib.semantic_detector.subprocess.run")
    def test_codex_exec_redacts_prompt_before_subprocess(self, mock_run):
        prompts = []

        def fake_run(command, **kwargs):
            prompts.append(kwargs["input"])
            return _codex_run_with_response({
                "is_learning": False,
                "type": None,
                "confidence": 0,
                "reasoning": "Not reusable",
                "extracted_learning": None,
            })(command, **kwargs)

        mock_run.side_effect = fake_run

        semantic_analyze("API_KEY=secret-value")

        self.assertEqual(len(prompts), 1)
        self.assertNotIn("secret-value", prompts[0])
        self.assertIn("[REDACTED]", prompts[0])

    @patch("lib.semantic_detector.subprocess.run")
    def test_successful_correction_detection(self, mock_run):
        """Test successful detection of a correction."""
        mock_run.side_effect = self._mock_codex_response({
            "is_learning": True,
            "type": "correction",
            "confidence": 0.85,
            "reasoning": "User is correcting the AI to use a different approach",
            "extracted_learning": "Use Python instead of JavaScript for this task",
        })

        result = semantic_analyze("no, use Python instead of JavaScript")

        self.assertIsNotNone(result)
        self.assertTrue(result["is_learning"])
        self.assertEqual(result["type"], "correction")
        self.assertEqual(result["confidence"], 0.85)
        self.assertIn("Python", result["extracted_learning"])

    @patch("lib.semantic_detector.subprocess.run")
    def test_successful_positive_detection(self, mock_run):
        """Test successful detection of positive feedback."""
        mock_run.side_effect = self._mock_codex_response({
            "is_learning": True,
            "type": "positive",
            "confidence": 0.75,
            "reasoning": "User affirming the approach",
            "extracted_learning": "Continue using async/await pattern",
        })

        result = semantic_analyze("perfect! that's exactly what I wanted")

        self.assertIsNotNone(result)
        self.assertTrue(result["is_learning"])
        self.assertEqual(result["type"], "positive")

    @patch("lib.semantic_detector.subprocess.run")
    def test_successful_explicit_detection(self, mock_run):
        """Test successful detection of explicit remember marker."""
        mock_run.side_effect = self._mock_codex_response({
            "is_learning": True,
            "type": "explicit",
            "confidence": 0.95,
            "reasoning": "User explicitly asking to remember",
            "extracted_learning": "Always use gpt-5.1 for reasoning tasks",
        })

        result = semantic_analyze("remember: always use gpt-5.1 for reasoning tasks")

        self.assertIsNotNone(result)
        self.assertTrue(result["is_learning"])
        self.assertEqual(result["type"], "explicit")
        self.assertGreaterEqual(result["confidence"], 0.90)

    @patch("lib.semantic_detector.subprocess.run")
    def test_not_a_learning(self, mock_run):
        """Test detection of non-learning message."""
        mock_run.side_effect = self._mock_codex_response({
            "is_learning": False,
            "type": None,
            "confidence": 0.1,
            "reasoning": "This is just a greeting, not a reusable learning",
            "extracted_learning": None,
        })

        result = semantic_analyze("Hello, how are you?")

        self.assertIsNotNone(result)
        self.assertFalse(result["is_learning"])
        self.assertIsNone(result["type"])

    @patch("lib.semantic_detector.subprocess.run")
    def test_multi_language_spanish(self, mock_run):
        """Test detection works for Spanish messages."""
        mock_run.side_effect = self._mock_codex_response({
            "is_learning": True,
            "type": "correction",
            "confidence": 0.80,
            "reasoning": "User is correcting in Spanish - asking to use Python",
            "extracted_learning": "Use Python instead of JavaScript",
        })

        result = semantic_analyze("no, usa Python en vez de JavaScript")

        self.assertIsNotNone(result)
        self.assertTrue(result["is_learning"])
        self.assertEqual(result["type"], "correction")

    @patch("lib.semantic_detector.subprocess.run")
    def test_multi_language_french(self, mock_run):
        """Test detection works for French messages."""
        mock_run.side_effect = self._mock_codex_response({
            "is_learning": True,
            "type": "correction",
            "confidence": 0.78,
            "reasoning": "User correcting in French",
            "extracted_learning": "Use async functions",
        })

        result = semantic_analyze("non, utilise les fonctions async")

        self.assertIsNotNone(result)
        self.assertTrue(result["is_learning"])

    @patch("lib.semantic_detector.subprocess.run")
    def test_multi_language_russian(self, mock_run):
        """Test detection works for Russian messages."""
        mock_run.side_effect = self._mock_codex_response({
            "is_learning": True,
            "type": "correction",
            "confidence": 0.82,
            "reasoning": "User correcting in Russian - don't use global variables",
            "extracted_learning": "Avoid global variables",
        })

        result = semantic_analyze("нет, не используй глобальные переменные")

        self.assertIsNotNone(result)
        self.assertTrue(result["is_learning"])

    @patch("lib.semantic_detector.subprocess.run")
    def test_timeout_returns_none(self, mock_run):
        """Test that timeout returns None for graceful fallback."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="codex", timeout=30)

        result = semantic_analyze("some text")

        self.assertIsNone(result)

    @patch("lib.semantic_detector.subprocess.run")
    def test_codex_not_installed(self, mock_run):
        """Test graceful handling when Codex CLI is not installed."""
        mock_run.side_effect = FileNotFoundError("codex not found")

        result = semantic_analyze("some text")

        self.assertIsNone(result)

    @patch("lib.semantic_detector.subprocess.run")
    def test_codex_cli_error(self, mock_run):
        """Test handling of Codex CLI returning non-zero exit code."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Error: API key not found"
        mock_run.return_value = mock_result

        result = semantic_analyze("some text")

        self.assertIsNone(result)

    @patch("lib.semantic_detector.subprocess.run")
    def test_empty_output(self, mock_run):
        """Test handling of a missing Codex structured output file."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        result = semantic_analyze("some text")

        self.assertIsNone(result)

    @patch("lib.semantic_detector.subprocess.run")
    def test_invalid_json_output(self, mock_run):
        """Test handling of invalid JSON in output."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "This is not JSON at all"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        result = semantic_analyze("some text")

        self.assertIsNone(result)

    @patch("lib.semantic_detector.subprocess.run")
    def test_wrapped_json_response_is_rejected(self, mock_run):
        """Structured output must match the requested schema directly."""
        mock_run.side_effect = _codex_run_with_response({
            "result": {
                "is_learning": True,
                "type": "correction",
                "confidence": 0.80,
                "reasoning": "User correction",
                "extracted_learning": "Use pytest",
            }
        })

        result = semantic_analyze("no, use pytest not unittest")

        self.assertIsNone(result)

    @patch("lib.semantic_detector.subprocess.run")
    def test_json_with_markdown_wrapper_is_rejected(self, mock_run):
        """Schema-constrained output must not accept markdown wrappers."""
        mock_run.side_effect = _codex_run_with_raw_output('''Here is the analysis:
```json
{
  "is_learning": true,
  "type": "correction",
  "confidence": 0.75,
  "reasoning": "User wants different approach",
  "extracted_learning": "Use type hints"
}
```
''')

        result = semantic_analyze("you should use type hints")

        self.assertIsNone(result)

    def test_empty_text_input(self):
        """Test that empty text returns None without calling Codex."""
        result = semantic_analyze("")
        self.assertIsNone(result)

        result = semantic_analyze("   ")
        self.assertIsNone(result)

    @patch("lib.semantic_detector.subprocess.run")
    def test_custom_timeout(self, mock_run):
        """Test that custom timeout is passed to subprocess."""
        mock_run.side_effect = self._mock_codex_response({
            "is_learning": False,
            "type": None,
            "confidence": 0.1,
            "reasoning": "Not a learning",
            "extracted_learning": None,
        })

        semantic_analyze("test", timeout=60)

        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args[1]
        self.assertEqual(call_kwargs["timeout"], 60)

    @patch("lib.semantic_detector.subprocess.run")
    def test_custom_model(self, mock_run):
        """Test that a custom model is passed to Codex CLI."""
        mock_run.side_effect = self._mock_codex_response({
            "is_learning": False,
            "type": None,
            "confidence": 0.1,
            "reasoning": "Not a learning",
            "extracted_learning": None,
        })

        semantic_analyze("test", model="gpt-test")

        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        self.assertIn("--model", call_args)
        self.assertIn("gpt-test", call_args)


class TestCodexSchemas(unittest.TestCase):
    def test_required_schema_files_are_valid_objects(self):
        schemas = PLUGIN_ROOT / "schemas"
        for name in (
            "learning-analysis.schema.json",
            "tool-error-analysis.schema.json",
            "contradictions.schema.json",
        ):
            with self.subTest(name=name):
                value = json.loads((schemas / name).read_text(encoding="utf-8"))
                self.assertEqual(value["type"], "object")
                self.assertFalse(value["additionalProperties"])


class TestExtractJsonFromText(unittest.TestCase):
    """Tests for _extract_json_from_text helper."""

    def test_extract_simple_json(self):
        """Test extraction of simple JSON object."""
        text = '{"is_learning": true, "confidence": 0.8}'
        result = _extract_json_from_text(text)
        self.assertIsNotNone(result)
        self.assertTrue(result["is_learning"])

    def test_extract_json_with_prefix(self):
        """Test extraction when JSON has prefix text."""
        text = 'Here is the result: {"is_learning": true}'
        result = _extract_json_from_text(text)
        self.assertIsNotNone(result)
        self.assertTrue(result["is_learning"])

    def test_extract_json_with_suffix(self):
        """Test extraction when JSON has suffix text."""
        text = '{"is_learning": false} and some more text'
        result = _extract_json_from_text(text)
        self.assertIsNotNone(result)
        self.assertFalse(result["is_learning"])

    def test_extract_nested_json(self):
        """Test extraction of nested JSON object."""
        text = 'Result: {"data": {"is_learning": true}, "meta": {}}'
        result = _extract_json_from_text(text)
        self.assertIsNotNone(result)
        self.assertIn("data", result)

    def test_no_json_found(self):
        """Test when no JSON is in text."""
        text = "This is just plain text without any JSON"
        result = _extract_json_from_text(text)
        self.assertIsNone(result)

    def test_invalid_json(self):
        """Test when JSON is malformed."""
        text = '{"is_learning": true, missing_quote: value}'
        result = _extract_json_from_text(text)
        self.assertIsNone(result)


class TestValidateResponse(unittest.TestCase):
    """Tests for _validate_response helper."""

    def test_valid_learning_response(self):
        """Test validation of complete valid response."""
        content = {
            "is_learning": True,
            "type": "correction",
            "confidence": 0.85,
            "reasoning": "User correction",
            "extracted_learning": "Use Python",
        }
        result = _validate_response(content)
        self.assertIsNotNone(result)
        self.assertTrue(result["is_learning"])
        self.assertEqual(result["type"], "correction")
        self.assertEqual(result["confidence"], 0.85)

    def test_missing_is_learning_field(self):
        """Test that missing is_learning field returns None."""
        content = {
            "type": "correction",
            "confidence": 0.85,
        }
        result = _validate_response(content)
        self.assertIsNone(result)

    def test_string_boolean_true(self):
        """Test normalization of string 'true' to boolean."""
        content = {
            "is_learning": "true",
            "type": "correction",
            "confidence": 0.8,
        }
        result = _validate_response(content)
        self.assertIsNotNone(result)
        self.assertTrue(result["is_learning"])

    def test_string_boolean_false(self):
        """Test normalization of string 'false' to boolean."""
        content = {
            "is_learning": "false",
            "type": None,
            "confidence": 0.1,
        }
        result = _validate_response(content)
        self.assertIsNotNone(result)
        self.assertFalse(result["is_learning"])

    def test_confidence_clamping_high(self):
        """Test that confidence > 1.0 is clamped to 1.0."""
        content = {
            "is_learning": True,
            "type": "correction",
            "confidence": 1.5,
        }
        result = _validate_response(content)
        self.assertEqual(result["confidence"], 1.0)

    def test_confidence_clamping_low(self):
        """Test that confidence < 0.0 is clamped to 0.0."""
        content = {
            "is_learning": True,
            "type": "correction",
            "confidence": -0.5,
        }
        result = _validate_response(content)
        self.assertEqual(result["confidence"], 0.0)

    def test_invalid_type_normalized(self):
        """Test that invalid type is normalized to None."""
        content = {
            "is_learning": True,
            "type": "invalid_type",
            "confidence": 0.8,
        }
        result = _validate_response(content)
        self.assertIsNone(result["type"])

    def test_non_dict_input(self):
        """Test that non-dict input returns None."""
        result = _validate_response("not a dict")
        self.assertIsNone(result)

        result = _validate_response(["list", "items"])
        self.assertIsNone(result)

    def test_extracted_learning_only_when_is_learning(self):
        """Test that extracted_learning is None when is_learning is False."""
        content = {
            "is_learning": False,
            "type": "correction",  # Should be nullified
            "confidence": 0.1,
            "extracted_learning": "This should be ignored",
        }
        result = _validate_response(content)
        self.assertIsNone(result["type"])
        self.assertIsNone(result["extracted_learning"])


class TestValidateQueueItems(unittest.TestCase):
    """Tests for validate_queue_items function."""

    def _mock_semantic_result(self, is_learning, confidence=0.8):
        """Create a mock semantic analysis result."""
        return {
            "is_learning": is_learning,
            "type": "correction" if is_learning else None,
            "confidence": confidence,
            "reasoning": "Mock reasoning",
            "extracted_learning": "Mock learning" if is_learning else None,
        }

    @patch("lib.semantic_detector.semantic_analyze")
    def test_filters_non_learnings(self, mock_analyze):
        """Test that non-learnings are filtered out."""
        mock_analyze.side_effect = [
            self._mock_semantic_result(True, 0.8),
            self._mock_semantic_result(False, 0.2),
            self._mock_semantic_result(True, 0.9),
        ]

        items = [
            {"message": "no, use Python", "confidence": 0.6},
            {"message": "Hello world", "confidence": 0.6},
            {"message": "remember: use async", "confidence": 0.9},
        ]

        result = validate_queue_items(items)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["message"], "no, use Python")
        self.assertEqual(result[1]["message"], "remember: use async")

    @patch("lib.semantic_detector.semantic_analyze")
    def test_updates_confidence(self, mock_analyze):
        """Test that confidence is updated from semantic analysis."""
        mock_analyze.return_value = self._mock_semantic_result(True, 0.95)

        items = [{"message": "test", "confidence": 0.6}]

        result = validate_queue_items(items)

        self.assertEqual(len(result), 1)
        # Should use higher of regex (0.6) and semantic (0.95)
        self.assertEqual(result[0]["confidence"], 0.95)

    @patch("lib.semantic_detector.semantic_analyze")
    def test_keeps_original_if_semantic_higher_confidence(self, mock_analyze):
        """Test that original confidence is kept if higher than semantic."""
        mock_analyze.return_value = self._mock_semantic_result(True, 0.5)

        items = [{"message": "test", "confidence": 0.8}]

        result = validate_queue_items(items)

        self.assertEqual(len(result), 1)
        # Should use higher of regex (0.8) and semantic (0.5)
        self.assertEqual(result[0]["confidence"], 0.8)

    @patch("lib.semantic_detector.semantic_analyze")
    def test_adds_semantic_fields(self, mock_analyze):
        """Test that semantic analysis fields are added to items."""
        mock_analyze.return_value = {
            "is_learning": True,
            "type": "explicit",
            "confidence": 0.9,
            "reasoning": "Explicit remember marker",
            "extracted_learning": "Always use pytest",
        }

        items = [{"message": "remember: use pytest", "confidence": 0.9}]

        result = validate_queue_items(items)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["semantic_type"], "explicit")
        self.assertEqual(result[0]["semantic_confidence"], 0.9)
        self.assertIn("semantic_reasoning", result[0])
        self.assertEqual(result[0]["extracted_learning"], "Always use pytest")

    @patch("lib.semantic_detector.semantic_analyze")
    def test_fallback_on_semantic_failure(self, mock_analyze):
        """Test that items are kept if semantic analysis fails."""
        mock_analyze.return_value = None  # Simulate failure

        items = [{"message": "test", "confidence": 0.7}]

        result = validate_queue_items(items)

        # Should keep original item as fallback
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["confidence"], 0.7)

    @patch("lib.semantic_detector.semantic_analyze")
    def test_skips_empty_messages(self, mock_analyze):
        """Test that items with empty messages are skipped."""
        items = [
            {"message": "", "confidence": 0.6},
            {"message": "valid message", "confidence": 0.7},
        ]

        mock_analyze.return_value = self._mock_semantic_result(True, 0.8)

        result = validate_queue_items(items)

        # Empty message should be skipped, only semantic_analyze called once
        self.assertEqual(mock_analyze.call_count, 1)

    def test_empty_items_list(self):
        """Test with empty items list."""
        result = validate_queue_items([])
        self.assertEqual(result, [])


class TestValidateToolError(unittest.TestCase):
    @patch("lib.semantic_detector.subprocess.run")
    def test_uses_tool_error_schema_and_redacts_prompt(self, mock_run):
        prompts = []

        def fake_run(command, **kwargs):
            prompts.append(kwargs["input"])
            return _codex_run_with_response({
                "is_learnable": True,
                "refined_guideline": "Load the project environment first",
                "confidence": 0.8,
                "reasoning": "Project-specific environment failure",
            })(command, **kwargs)

        mock_run.side_effect = fake_run

        result = validate_tool_error(
            "env_undefined",
            "API_KEY=secret-value is not set",
            2,
            "Load the environment",
        )

        command = mock_run.call_args.args[0]
        schema = command[command.index("--output-schema") + 1]
        self.assertTrue(schema.endswith("tool-error-analysis.schema.json"))
        self.assertNotIn("secret-value", prompts[0])
        self.assertEqual(result["confidence"], 0.8)


class TestAnalysisPrompt(unittest.TestCase):
    """Tests for the analysis prompt template."""

    def test_prompt_contains_key_instructions(self):
        """Test that prompt contains essential instructions."""
        self.assertIn("is_learning", ANALYSIS_PROMPT)
        self.assertIn("correction", ANALYSIS_PROMPT)
        self.assertIn("positive", ANALYSIS_PROMPT)
        self.assertIn("explicit", ANALYSIS_PROMPT)
        self.assertIn("confidence", ANALYSIS_PROMPT)
        self.assertIn("ANY language", ANALYSIS_PROMPT)

    def test_prompt_format_string(self):
        """Test that prompt can be formatted with text."""
        formatted = ANALYSIS_PROMPT.format(text="test message")
        self.assertIn("test message", formatted)


class TestDetectContradictions(unittest.TestCase):
    """Tests for detect_contradictions function."""

    def _mock_codex_response(self, response_dict):
        return _codex_run_with_response(response_dict)

    def test_empty_entries_list(self):
        """Test that empty entries return empty list."""
        result = detect_contradictions([])
        self.assertEqual(result, [])

    def test_single_entry_returns_empty(self):
        """Test that single entry returns empty list (can't contradict itself)."""
        result = detect_contradictions(["Use tabs for indentation"])
        self.assertEqual(result, [])

    @patch("lib.semantic_detector.subprocess.run")
    def test_uses_contradiction_schema(self, mock_run):
        mock_run.side_effect = self._mock_codex_response({
            "contradictions": []
        })

        detect_contradictions(["Use tabs", "Use spaces"])

        command = mock_run.call_args.args[0]
        schema = command[command.index("--output-schema") + 1]
        self.assertTrue(schema.endswith("contradictions.schema.json"))

    @patch("lib.semantic_detector.subprocess.run")
    def test_detects_contradiction(self, mock_run):
        """Test successful detection of contradicting entries."""
        mock_run.side_effect = self._mock_codex_response({
            "contradictions": [
                {
                    "entry1": "Use tabs for indentation",
                    "entry2": "Use spaces for indentation",
                    "conflict": "opposite indentation preferences"
                }
            ]
        })

        entries = [
            "Use tabs for indentation",
            "Use spaces for indentation",
            "Use gpt-5.1 for reasoning"
        ]

        result = detect_contradictions(entries)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["entry1"], "Use tabs for indentation")
        self.assertEqual(result[0]["entry2"], "Use spaces for indentation")
        self.assertIn("indentation", result[0]["conflict"])

    @patch("lib.semantic_detector.subprocess.run")
    def test_no_contradictions_found(self, mock_run):
        """Test when no contradictions are found."""
        mock_run.side_effect = self._mock_codex_response({
            "contradictions": []
        })

        entries = [
            "Use gpt-5.1 for reasoning",
            "Use venv for Python projects",
            "Always run tests before committing"
        ]

        result = detect_contradictions(entries)
        self.assertEqual(result, [])

    @patch("lib.semantic_detector.subprocess.run")
    def test_rejects_wrapped_response(self, mock_run):
        """Contradiction output must match its schema directly."""
        mock_run.side_effect = _codex_run_with_response({
            "result": {
                "contradictions": [
                    {
                        "entry1": "Always use TypeScript",
                        "entry2": "Prefer JavaScript over TypeScript",
                        "conflict": "conflicting language preferences"
                    }
                ]
            }
        })

        entries = ["Always use TypeScript", "Prefer JavaScript over TypeScript"]
        result = detect_contradictions(entries)

        self.assertEqual(result, [])

    @patch("lib.semantic_detector.subprocess.run")
    def test_cli_error_returns_empty(self, mock_run):
        """Test that CLI errors return empty list."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Error"
        mock_run.return_value = mock_result

        entries = ["Use tabs", "Use spaces"]
        result = detect_contradictions(entries)

        self.assertEqual(result, [])

    @patch("lib.semantic_detector.subprocess.run")
    def test_timeout_returns_empty(self, mock_run):
        """Test that timeout returns empty list."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="codex", timeout=30)

        entries = ["Use tabs", "Use spaces"]
        result = detect_contradictions(entries)

        self.assertEqual(result, [])

    @patch("lib.semantic_detector.subprocess.run")
    def test_invalid_json_returns_empty(self, mock_run):
        """Test that invalid JSON returns empty list."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Not valid JSON"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        entries = ["Use tabs", "Use spaces"]
        result = detect_contradictions(entries)

        self.assertEqual(result, [])

    @patch("lib.semantic_detector.subprocess.run")
    def test_validates_contradiction_structure(self, mock_run):
        """Test that invalid contradiction structures are filtered out."""
        mock_run.side_effect = self._mock_codex_response({
            "contradictions": [
                {"entry1": "Valid", "entry2": "Also valid", "conflict": "reason"},
                {"entry1": "Missing entry2"},  # Invalid - missing entry2
                {"missing_both": "fields"},  # Invalid - missing both
            ]
        })

        entries = ["Valid", "Also valid", "Another entry"]
        result = detect_contradictions(entries)

        # Only the valid contradiction should be returned
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["entry1"], "Valid")


if __name__ == "__main__":
    unittest.main()
