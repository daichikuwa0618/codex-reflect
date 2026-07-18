"""Adapter for the confirmed Codex JSONL transcript schema."""
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .codex_paths import get_codex_home
from .redaction import redact_secrets, redact_structure


KNOWN_RECORD_TYPES = {
    "session_meta",
    "event_msg",
    "response_item",
    "turn_context",
}


@dataclass
class TranscriptResult:
    path: Path
    supported: bool
    session_id: str = ""
    cwd: str = ""
    timestamp: str = ""
    user_messages: List[str] = field(default_factory=list)
    tool_outputs: List[str] = field(default_factory=list)
    issues: List[str] = field(default_factory=list)


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    """Read object records from JSONL and report malformed line numbers."""
    records = []
    with Path(path).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    "invalid JSONL at line {}: {}".format(line_number, error)
                ) from error
            if not isinstance(value, dict):
                raise ValueError(
                    "record at line {} must be an object".format(line_number)
                )
            records.append(value)
    return records


def _metadata_value(metadata: Dict[str, Any], key: str) -> str:
    value = metadata.get(key)
    return value if isinstance(value, str) else ""


def _append_message(
    messages: List[str],
    own_unmatched: Dict[str, int],
    other_unmatched: Dict[str, int],
    value: Any,
) -> None:
    if not isinstance(value, str):
        return
    other_count = other_unmatched.get(value, 0)
    if other_count:
        if other_count == 1:
            del other_unmatched[value]
        else:
            other_unmatched[value] = other_count - 1
        return
    messages.append(redact_secrets(value))
    own_unmatched[value] = own_unmatched.get(value, 0) + 1


def _append_response_user_messages(
    messages: List[str],
    response_unmatched: Dict[str, int],
    event_unmatched: Dict[str, int],
    payload: Dict[str, Any],
) -> None:
    if payload.get("type") != "message" or payload.get("role") != "user":
        return
    content = payload.get("content")
    if not isinstance(content, list):
        return
    for item in content:
        if not isinstance(item, dict) or item.get("type") != "input_text":
            continue
        _append_message(
            messages,
            response_unmatched,
            event_unmatched,
            item.get("text"),
        )


def _append_custom_tool_output(outputs: List[str], payload: Dict[str, Any]) -> None:
    if payload.get("type") != "custom_tool_call_output":
        return
    output = payload.get("output")
    if isinstance(output, str):
        outputs.append(redact_secrets(output))
    elif output is not None:
        outputs.append(
            json.dumps(
                redact_structure(output),
                ensure_ascii=False,
                sort_keys=True,
            )
        )


def parse_transcript(path: Path) -> TranscriptResult:
    """Normalize only confirmed Codex records; unsupported schemas stay empty."""
    transcript_path = Path(path)
    records = read_jsonl(transcript_path)
    metadata: Optional[Dict[str, Any]] = next(
        (
            record.get("payload")
            for record in records
            if record.get("type") == "session_meta"
            and isinstance(record.get("payload"), dict)
        ),
        None,
    )
    has_known_event = any(
        record.get("type") in KNOWN_RECORD_TYPES - {"session_meta"}
        for record in records
    )
    if metadata is None or not has_known_event:
        return TranscriptResult(
            transcript_path,
            False,
            issues=["unsupported transcript schema"],
        )

    messages: List[str] = []
    event_unmatched: Dict[str, int] = {}
    response_unmatched: Dict[str, int] = {}
    outputs: List[str] = []
    issues: List[str] = []
    for record in records:
        record_type = record.get("type")
        if record_type not in KNOWN_RECORD_TYPES:
            issues.append("ignored unknown record type: {}".format(record_type))
            continue
        if record_type == "turn_context":
            event_unmatched.clear()
            response_unmatched.clear()
            continue
        payload = record.get("payload")
        if not isinstance(payload, dict):
            continue
        if record_type == "event_msg" and payload.get("type") == "user_message":
            _append_message(
                messages,
                event_unmatched,
                response_unmatched,
                payload.get("message"),
            )
        elif record_type == "response_item":
            _append_response_user_messages(
                messages,
                response_unmatched,
                event_unmatched,
                payload,
            )
            _append_custom_tool_output(outputs, payload)

    return TranscriptResult(
        path=transcript_path,
        supported=True,
        session_id=_metadata_value(metadata, "id"),
        cwd=_metadata_value(metadata, "cwd"),
        timestamp=_metadata_value(metadata, "timestamp"),
        user_messages=messages,
        tool_outputs=outputs,
        issues=issues,
    )


def list_session_files(codex_home: Optional[Path] = None) -> List[Path]:
    """Enumerate active and archived JSONL transcripts in stable path order."""
    root = Path(codex_home) if codex_home is not None else get_codex_home()
    files: Dict[str, Path] = {}
    for directory_name in ("sessions", "archived_sessions"):
        directory = root / directory_name
        if directory.is_symlink() or not directory.is_dir():
            continue
        try:
            authorized_root = directory.resolve(strict=True)
        except OSError:
            continue
        for candidate in directory.rglob("*.jsonl"):
            if candidate.is_symlink():
                continue
            try:
                if not candidate.is_file():
                    continue
                canonical = candidate.resolve(strict=True)
                canonical.relative_to(authorized_root)
            except (OSError, ValueError):
                continue
            key = os.path.normcase(str(canonical))
            if key not in files:
                files[key] = canonical
    return [files[key] for key in sorted(files)]
