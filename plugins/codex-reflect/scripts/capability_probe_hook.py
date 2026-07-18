import json
import os
import sys
from pathlib import Path


SAFE_FIELDS = {
    "hook_event_name", "session_id", "turn_id", "cwd", "model",
    "prompt", "tool_name", "tool_input", "tool_response",
}


def main():
    payload = json.loads(sys.stdin.read() or "{}")
    event_name = str(payload.get("hook_event_name", "unknown"))
    fields = ",".join(sorted(SAFE_FIELDS.intersection(payload)))
    tool_input = payload.get("tool_input")
    tool_fields = ",".join(sorted(tool_input)) if isinstance(tool_input, dict) else ""
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()
    state_root = codex_home / "codex-reflect"
    output = {
        "continue": True,
        "systemMessage": (
            f"codex-reflect capability probe: {event_name} "
            f"fields={fields} tool_input_fields={tool_fields} state_root={state_root}"
        ),
    }
    print(json.dumps(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
