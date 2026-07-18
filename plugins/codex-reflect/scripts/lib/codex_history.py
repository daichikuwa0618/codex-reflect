"""Adapter for the confirmed Codex JSONL transcript schema."""
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .codex_paths import get_codex_home
from .redaction import redact_secrets


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


def _append_message(messages: List[str], seen: set, value: Any) -> None:
    if not isinstance(value, str) or value in seen:
        return
    seen.add(value)
    messages.append(redact_secrets(value))


def _append_response_user_messages(
    messages: List[str], seen: set, payload: Dict[str, Any]
) -> None:
    if payload.get("type") != "message" or payload.get("role") != "user":
        return
    content = payload.get("content")
    if not isinstance(content, list):
        return
    for item in content:
        if not isinstance(item, dict) or item.get("type") != "input_text":
            continue
        _append_message(messages, seen, item.get("text"))


def _append_custom_tool_output(outputs: List[str], payload: Dict[str, Any]) -> None:
    if payload.get("type") != "custom_tool_call_output":
        return
    output = payload.get("output")
    if isinstance(output, str):
        outputs.append(redact_secrets(output))
    elif output is not None:
        outputs.append(
            redact_secrets(
                json.dumps(output, ensure_ascii=False, sort_keys=True)
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
    seen_messages = set()
    outputs: List[str] = []
    issues: List[str] = []
    for record in records:
        record_type = record.get("type")
        if record_type not in KNOWN_RECORD_TYPES:
            issues.append("ignored unknown record type: {}".format(record_type))
            continue
        payload = record.get("payload")
        if not isinstance(payload, dict):
            continue
        if record_type == "event_msg" and payload.get("type") == "user_message":
            _append_message(messages, seen_messages, payload.get("message"))
        elif record_type == "response_item":
            _append_response_user_messages(messages, seen_messages, payload)
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
    files: List[Path] = []
    for directory_name in ("sessions", "archived_sessions"):
        directory = root / directory_name
        if directory.is_dir():
            files.extend(directory.rglob("*.jsonl"))
    return sorted(files)
