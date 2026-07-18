"""Local secret redaction for transcript-derived text."""
import re


_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)(\b(?:api[_-]?key|secret|token|password|passwd|credential|cookie|"
    r"authorization)\b\s*=\s*)([\"']?)([^\s\"']+)(\2)"
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
        lambda match: (
            match.group(1)
            + match.group(2)
            + "[REDACTED]"
            + match.group(4)
        ),
        value,
    )
    redacted = _BEARER_PATTERN.sub(r"\1[REDACTED]", redacted)
    redacted = _JWT_PATTERN.sub("[REDACTED]", redacted)
    redacted = _OPENAI_TOKEN_PATTERN.sub("[REDACTED]", redacted)
    return _GITHUB_TOKEN_PATTERN.sub("[REDACTED]", redacted)
