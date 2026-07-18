"""Local secret redaction for transcript-derived text."""
import re
from typing import Any


_SECRET_COMPONENTS = {
    "authorization",
    "cookie",
    "credential",
    "passwd",
    "password",
    "secret",
    "token",
}
_SECRET_KEY_QUALIFIERS = {
    "access",
    "api",
    "auth",
    "authorization",
    "credential",
    "private",
    "secret",
}
_IDENTIFIER = r"[A-Za-z][A-Za-z0-9_-]*"
_ASSIGNMENT_START_PATTERN = re.compile(
    r"(?:"
    r"(?P<escaped_quote>\\+[\"'])(?P<escaped_key>{identifier})"
    r"(?P=escaped_quote)"
    r"|(?P<quote>[\"'])(?P<quoted_key>{identifier})(?P=quote)"
    r"|(?P<bare_key>(?<![A-Za-z0-9_-]){identifier})"
    r")\s*(?P<separator>=|:)\s*".format(identifier=_IDENTIFIER)
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

    redacted = _redact_assignments(value)
    redacted = _BEARER_PATTERN.sub(r"\1[REDACTED]", redacted)
    redacted = _JWT_PATTERN.sub("[REDACTED]", redacted)
    redacted = _OPENAI_TOKEN_PATTERN.sub("[REDACTED]", redacted)
    return _GITHUB_TOKEN_PATTERN.sub("[REDACTED]", redacted)


def _identifier_components(value: str):
    with_acronyms_split = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", value)
    with_camel_split = re.sub(
        r"([a-z0-9])([A-Z])", r"\1_\2", with_acronyms_split
    )
    return [
        component.lower()
        for component in re.split(r"[^A-Za-z0-9]+", with_camel_split)
        if component
    ]


def _is_secret_key(value: str) -> bool:
    components = _identifier_components(value)
    if any(
        component in _SECRET_COMPONENTS
        for component in components
    ):
        return True
    return "key" in components and any(
        component in _SECRET_KEY_QUALIFIERS
        for component in components
    )


def _redact_assignments(value: str) -> str:
    pieces = []
    copy_position = 0
    search_position = 0
    while True:
        match = _ASSIGNMENT_START_PATTERN.search(value, search_position)
        if match is None:
            break
        key = (
            match.group("escaped_key")
            or match.group("quoted_key")
            or match.group("bare_key")
        )
        if not _is_secret_key(key):
            search_position = match.end()
            continue

        end, replacement = _consume_assignment_value(
            value,
            match.end(),
            match.group("separator"),
            key,
        )
        if replacement is None:
            search_position = match.end()
            continue
        pieces.append(value[copy_position:match.end()])
        pieces.append(replacement)
        copy_position = end
        search_position = end

    if not pieces:
        return value
    pieces.append(value[copy_position:])
    return "".join(pieces)


def _consume_assignment_value(
    value: str,
    start: int,
    separator: str,
    key: str,
):
    if start >= len(value) or value[start] in "\r\n":
        return start, None

    delimiter = _backslash_quote_delimiter(value, start)
    if delimiter is not None:
        end = _backslash_quoted_end(value, start, delimiter)
        if end is None:
            return _line_end(value, start), delimiter + "[REDACTED]"
        return end, delimiter + "[REDACTED]" + delimiter

    if value[start] in ("\"", "'"):
        quote = value[start]
        position = start + 1
        while position < len(value):
            character = value[position]
            if character in "\r\n":
                break
            if character == "\\":
                position += 2
                continue
            if character == quote:
                return position + 1, quote + "[REDACTED]" + quote
            position += 1
        return _line_end(value, start), quote + "[REDACTED]"

    if "authorization" in _identifier_components(key):
        end = _line_end(value, start)
        scheme = re.match(
            r"([A-Za-z][A-Za-z0-9_-]*)[ \t]+(?=\S)",
            value[start:end],
        )
        replacement = "[REDACTED]"
        if separator == ":" and scheme is not None:
            replacement = scheme.group(1) + " [REDACTED]"
        return end, replacement

    bearer = re.match(
        r"(?i)Bearer\s+[^\s,;}}\]\"']+", value[start:]
    )
    if bearer is not None:
        replacement = "[REDACTED]"
        if separator == ":":
            prefix = re.match(r"(?i)Bearer\s+", bearer.group(0)).group(0)
            replacement = prefix + "[REDACTED]"
        return start + bearer.end(), replacement

    end = start
    while end < len(value) and value[end] not in " \t\r\n,;}][\"'":
        end += 1
    if end == start:
        return start, None
    return end, "[REDACTED]"


def _backslash_quote_delimiter(value: str, start: int):
    position = start
    while position < len(value) and value[position] == "\\":
        position += 1
    if position == start or position >= len(value):
        return None
    if value[position] not in ("\"", "'"):
        return None
    return value[start:position + 1]


def _backslash_quoted_end(value: str, start: int, delimiter: str):
    quote = delimiter[-1]
    delimiter_backslashes = len(delimiter) - 1
    position = start + len(delimiter)
    while position < len(value):
        if value[position] in "\r\n":
            return None
        if value[position] != quote:
            position += 1
            continue

        backslashes = 0
        before_quote = position - 1
        while before_quote >= start and value[before_quote] == "\\":
            backslashes += 1
            before_quote -= 1
        if backslashes == delimiter_backslashes:
            return position + 1
        position += 1
    return None


def _line_end(value: str, start: int) -> int:
    carriage_return = value.find("\r", start)
    line_feed = value.find("\n", start)
    candidates = [
        position
        for position in (carriage_return, line_feed)
        if position != -1
    ]
    return min(candidates) if candidates else len(value)


def redact_structure(value: Any) -> Any:
    """Recursively redact secret-keyed values in JSON-compatible data."""
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            if isinstance(key, str) and _is_secret_key(key):
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = redact_structure(item)
        return redacted
    if isinstance(value, list):
        return [redact_structure(item) for item in value]
    if isinstance(value, str):
        return redact_secrets(value)
    return value
