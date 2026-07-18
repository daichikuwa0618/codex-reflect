"""Local secret redaction for transcript-derived text."""
import re
from typing import Any


_SECRET_KEY = (
    r"(?:api[_-]?key|secret|token|password|passwd|credential|cookie|"
    r"authorization)"
)
_SECRET_KEY_PATTERN = re.compile(r"(?i)^{}$".format(_SECRET_KEY))
_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)(\b{}\b\s*=\s*)"
    r"(\"[^\r\n\"]*\"|'[^\r\n']*'|Bearer\s+[^\s,;}}\]]+|"
    r"[^\s,;}}\]]+)".format(_SECRET_KEY)
)
_JSON_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)([\"']{}[\"']\s*:\s*)([\"'])([^\r\n]*?)(\2)".format(
        _SECRET_KEY
    )
)
_BEARER_PATTERN = re.compile(
    r"(?i)(\bBearer\s+)([A-Za-z0-9._~+/=-]+)"
)
_JWT_PATTERN = re.compile(
    r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"
)
_OPENAI_TOKEN_PATTERN = re.compile(
    r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"
)
_GITHUB_TOKEN_PATTERN = re.compile(
    r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"
)


def redact_secrets(value: str) -> str:
    """Replace supported credential values without logging the input."""
    if not isinstance(value, str):
        return value

    redacted = _ASSIGNMENT_PATTERN.sub(
        _redact_assignment,
        value,
    )
    redacted = _JSON_ASSIGNMENT_PATTERN.sub(
        r"\1\2[REDACTED]\4", redacted
    )
    redacted = _BEARER_PATTERN.sub(r"\1[REDACTED]", redacted)
    redacted = _JWT_PATTERN.sub("[REDACTED]", redacted)
    redacted = _OPENAI_TOKEN_PATTERN.sub("[REDACTED]", redacted)
    return _GITHUB_TOKEN_PATTERN.sub("[REDACTED]", redacted)


def _redact_assignment(match: re.Match) -> str:
    raw_value = match.group(2)
    if (
        len(raw_value) >= 2
        and raw_value[0] in ("\"", "'")
        and raw_value[-1] == raw_value[0]
    ):
        replacement = raw_value[0] + "[REDACTED]" + raw_value[-1]
    else:
        replacement = "[REDACTED]"
    return match.group(1) + replacement


def redact_structure(value: Any) -> Any:
    """Recursively redact secret-keyed values in JSON-compatible data."""
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            if isinstance(key, str) and _SECRET_KEY_PATTERN.fullmatch(key):
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = redact_structure(item)
        return redacted
    if isinstance(value, list):
        return [redact_structure(item) for item in value]
    if isinstance(value, str):
        return redact_secrets(value)
    return value
