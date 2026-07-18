"""Normalize Codex Hook payloads and common output."""
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class HookEvent:
    """Fields shared by the Codex Hook events used by codex-reflect."""

    event_name: str
    cwd: str
    session_id: str
    turn_id: Optional[str]
    model: Optional[str]
    prompt: Optional[str]
    tool_name: Optional[str]
    tool_input: Dict[str, Any]
    tool_response: Any

    @classmethod
    def from_dict(cls, value):
        tool_input = value.get("tool_input")
        return cls(
            event_name=str(value.get("hook_event_name", "") or ""),
            cwd=str(value.get("cwd", "") or ""),
            session_id=str(value.get("session_id", "") or ""),
            turn_id=value.get("turn_id"),
            model=value.get("model"),
            prompt=value.get("prompt"),
            tool_name=value.get("tool_name"),
            tool_input=tool_input if isinstance(tool_input, dict) else {},
            tool_response=value.get("tool_response"),
        )


def system_message(message):
    """Return Codex common Hook output with a system message."""
    return {"continue": True, "systemMessage": message}
