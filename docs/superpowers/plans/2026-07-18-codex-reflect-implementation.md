# codex-reflect Codex-Only Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the `claude-reflect` feedback loop, history analysis, and Skill discovery as a Codex-only open-source Plugin built for Codex Hooks, Plugins, Skills, and `AGENTS.md`.

**Architecture:** Preserve upstream detection, confidence, decay, and semantic-validation logic in a platform-independent core. Isolate Codex-specific Hooks, history, targets, state, and subprocess behavior behind adapters. Hooks own automatic capture, the four upstream-named Skills own interaction and final confirmation, and `$CODEX_HOME/codex-reflect` owns shared state.

**Tech Stack:** Python 3.8+ standard library, Codex Plugin manifest, Hooks, Agent Skills, JSON, JSONL, `unittest`, `pytest`, and GitHub Actions (macOS, Linux, Windows)

---

## Implementation prerequisites

- Approved design: `docs/superpowers/specs/2026-07-18-codex-reflect-design.md`
- Baseline: 222 tests pass with `python3 -m unittest discover -s tests -v`.
- Follow TDD and make each task an independent commit.
- If the Phase 0 capability spike finds a Codex blocker, stop and revisit the design instead of adding a complex workaround.
- Obtain user approval before Plugin installation or removal, Hook trust changes, or writes under `$CODEX_HOME`, because these operations change local user state.

## Final file map

```text
.agents/
  plugins/
    marketplace.json                  # repository marketplace
plugins/
  codex-reflect/
    .codex-plugin/
      plugin.json                     # Codex Plugin manifest
    assets/
      reflect-demo.jpg
    hooks/
      hooks.json                      # Codex lifecycle hooks
    schemas/
      learning-analysis.schema.json
      tool-error-analysis.schema.json
      contradictions.schema.json
    skills/
      reflect/SKILL.md
      reflect-skills/SKILL.md
      view-queue/SKILL.md
      skip-reflect/SKILL.md
    scripts/
      capture_learning.py
      check_learnings.py
      post_commit_reminder.py
      session_start_reminder.py
      read_queue.py
      clear_queue.py
      extract_session_learnings.py
      extract_tool_errors.py
      extract_tool_rejections.py
      compare_detection.py
      commands/
        reflect.py
        reflect_skills.py
      lib/
        __init__.py
        codex_hooks.py
        codex_history.py
        codex_paths.py
        capabilities.py
        redaction.py
        reflect_utils.py
        semantic_detector.py
        state_store.py
        target_resolver.py
tests/
  fixtures/codex/
  test_capabilities.py
  test_codex_history.py
  test_codex_hooks.py
  test_codex_paths.py
  test_codex_plugin_contract.py
  test_reflect_command.py
  test_reflect_skills_command.py
  test_state_store.py
  test_target_resolver.py
  test_integration.py
  test_memory_hierarchy.py
  test_reflect_utils.py
  test_semantic_detector.py
  test_tool_errors.py
AGENTS.md                                # contributor guidance for Codex
README.md
CHANGELOG.md
DISTRIBUTION.md
RELEASING.md
LICENSE                                  # upstream MIT notice preserved
```

## Task 1: Move the runtime into the Codex Plugin bundle

**Files:**
- Move: `scripts/` -> `plugins/codex-reflect/scripts/`
- Move: `assets/` -> `plugins/codex-reflect/assets/`
- Modify: `tests/test_integration.py`
- Modify: `tests/test_memory_hierarchy.py`
- Modify: `tests/test_reflect_utils.py`
- Modify: `tests/test_semantic_detector.py`
- Modify: `tests/test_tool_errors.py`

- [ ] **Step 1: Run the pre-move baseline**

Run:

```bash
python3 -m unittest discover -s tests -v
```

Expected: `Ran 222 tests` and `OK`.

- [ ] **Step 2: Move runtime files and assets into the Plugin bundle**

Run:

```bash
mkdir -p plugins/codex-reflect
git mv scripts plugins/codex-reflect/scripts
git mv assets plugins/codex-reflect/assets
```

- [ ] **Step 3: Confirm tests fail because they still reference old paths**

Run:

```bash
python3 -m unittest discover -s tests -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'lib'` or a file-not-found error for the old `scripts/` path.

- [ ] **Step 4: Update the runtime root in five test modules**

In each file, replace the `scripts` reference under the repository root with:

```python
REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = REPO_ROOT / "plugins" / "codex-reflect"
SCRIPTS_DIR = PLUGIN_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
```

Use the same definition for `SCRIPTS_DIR` in `tests/test_integration.py` and `sys.path.insert` in the other four files. Also change test fixtures that construct the repository-root `scripts` path to `PLUGIN_ROOT / "scripts"`.

- [ ] **Step 5: Verify the behavior-preserving move**

Run:

```bash
python3 -m unittest discover -s tests -v
```

Expected: 222 tests passing.

- [ ] **Step 6: commit**

```bash
git add plugins/codex-reflect tests
git commit -m "refactor: move runtime into Codex plugin bundle"
```

## Task 2: Add the Codex Plugin package contract and Phase 0 scaffold

**Files:**
- Create: `.agents/plugins/marketplace.json`
- Create: `plugins/codex-reflect/.codex-plugin/plugin.json`
- Create: `plugins/codex-reflect/hooks/hooks.json`
- Create: `plugins/codex-reflect/scripts/capability_probe_hook.py`
- Create: `plugins/codex-reflect/skills/reflect/SKILL.md`
- Create: `plugins/codex-reflect/skills/reflect-skills/SKILL.md`
- Create: `plugins/codex-reflect/skills/view-queue/SKILL.md`
- Create: `plugins/codex-reflect/skills/skip-reflect/SKILL.md`
- Create: `tests/test_codex_plugin_contract.py`

- [ ] **Step 1: Write failing package contract tests**

```python
import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = REPO_ROOT / "plugins" / "codex-reflect"


class TestCodexPluginContract(unittest.TestCase):
    def test_manifest_declares_four_fork_named_skills_and_hooks(self):
        manifest = json.loads(
            (PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["name"], "codex-reflect")
        self.assertEqual(manifest["skills"], "./skills/")
        self.assertEqual(manifest["hooks"], "./hooks/hooks.json")
        for name in ("reflect", "reflect-skills", "view-queue", "skip-reflect"):
            self.assertTrue((PLUGIN_ROOT / "skills" / name / "SKILL.md").is_file())

    def test_marketplace_points_to_nested_plugin(self):
        catalog = json.loads(
            (REPO_ROOT / ".agents" / "plugins" / "marketplace.json").read_text(encoding="utf-8")
        )
        entry = catalog["plugins"][0]
        self.assertEqual(entry["name"], "codex-reflect")
        self.assertEqual(entry["source"]["path"], "./plugins/codex-reflect")

    def test_hooks_use_native_plugin_root(self):
        hooks = json.loads((PLUGIN_ROOT / "hooks" / "hooks.json").read_text())
        commands = [
            handler["command"]
            for groups in hooks["hooks"].values()
            for group in groups
            for handler in group["hooks"]
        ]
        self.assertTrue(all("${PLUGIN_ROOT}" in command for command in commands))
        self.assertTrue(all("CLAUDE_PLUGIN_ROOT" not in command for command in commands))
```

- [ ] **Step 2: Confirm the contract test fails**

Run:

```bash
python3 -m unittest tests.test_codex_plugin_contract -v
```

Expected: FAIL because the manifest or marketplace does not exist.

- [ ] **Step 3: Create the marketplace and manifest**

`.agents/plugins/marketplace.json`:

```json
{
  "name": "codex-reflect-marketplace",
  "interface": { "displayName": "codex-reflect" },
  "plugins": [
    {
      "name": "codex-reflect",
      "source": { "source": "local", "path": "./plugins/codex-reflect" },
      "policy": { "installation": "AVAILABLE", "authentication": "ON_INSTALL" },
      "category": "Developer Tools"
    }
  ]
}
```

`plugins/codex-reflect/.codex-plugin/plugin.json`:

```json
{
  "name": "codex-reflect",
  "version": "4.0.0-rc.1",
  "description": "Capture Codex corrections and turn them into reviewed AGENTS.md guidance and reusable skills.",
  "author": { "name": "daichikuwa0618", "url": "https://github.com/daichikuwa0618" },
  "repository": "https://github.com/daichikuwa0618/codex-reflect",
  "license": "MIT",
  "keywords": ["codex", "self-learning", "corrections", "AGENTS.md", "skills"],
  "skills": "./skills/",
  "hooks": "./hooks/hooks.json"
}
```

- [ ] **Step 4: Create four Skills as discovery probes**

Give every `SKILL.md` the correct upstream name in frontmatter. In Phase 0, have each Skill only confirm its own loading as shown below; Tasks 9 through 11 replace these probes with final workflows.

```markdown
---
name: reflect
description: Review captured Codex corrections and propose durable AGENTS.md or Skill updates.
---

Resolve `../../scripts/capability_probe_hook.py` relative to this SKILL.md and run it with stdin `{"hook_event_name":"SkillProbe"}`. Report its `systemMessage` and do not edit files.
```

For the remaining files, set `name` to `reflect-skills`, `view-queue`, or `skip-reflect` and use the same write-free probe.

- [ ] **Step 5: Create write-free Phase 0 Hook probes and configuration**

Do not register pre-port runtime Hooks at this point. `capability_probe_hook.py` returns only known Hook payload field names and does not save prompt contents or files.

```python
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
```

```json
{
  "description": "codex-reflect lifecycle hooks",
  "hooks": {
    "UserPromptSubmit": [{
      "hooks": [{
        "type": "command",
        "command": "python3 \"${PLUGIN_ROOT}/scripts/capability_probe_hook.py\""
      }]
    }],
    "PreCompact": [{
      "hooks": [{
        "type": "command",
        "command": "python3 \"${PLUGIN_ROOT}/scripts/capability_probe_hook.py\""
      }]
    }],
    "PostToolUse": [{
      "matcher": "^Bash$",
      "hooks": [{
        "type": "command",
        "command": "python3 \"${PLUGIN_ROOT}/scripts/capability_probe_hook.py\""
      }]
    }],
    "SessionStart": [{
      "matcher": "startup|resume|clear|compact",
      "hooks": [{
        "type": "command",
        "command": "python3 \"${PLUGIN_ROOT}/scripts/capability_probe_hook.py\""
      }]
    }]
  }
}
```

- [ ] **Step 6: Pass the package contract**

Run:

```bash
python3 -m unittest tests.test_codex_plugin_contract -v
```

Expected: 3 tests passing.

- [ ] **Step 7: Manually verify Phase 0 Plugin discovery**

Obtain user approval before this step because it changes user configuration and consumes one Codex invocation.

Run:

```bash
codex plugin marketplace add .
codex plugin add codex-reflect@codex-reflect-marketplace
codex plugin list
printf 'Reply with exactly: codex-reflect semantic probe ok' | codex exec --ephemeral --disable hooks --sandbox read-only --skip-git-repo-check -
```

Expected: `codex-reflect@codex-reflect-marketplace` is `installed, enabled`. `codex exec` exits after one invocation and does not recurse into Hook probes. Start a new session in the CLI, desktop, and IDE extension; confirm four Skills, the `$codex-reflect:reflect` probe, and four Hook groups under `/hooks`. After trust, each event probe returns only the event name and known field names. Every surface and each Skill/Hook reports the same `state_root`, and no real `$CODEX_HOME/codex-reflect` directory or project file is created.

If Skills do not appear, record whether the issue matches [openai/codex#22078](https://github.com/openai/codex/issues/22078) and stop executing this plan. Do not install duplicate legacy Skills.

- [ ] **Step 8: commit**

```bash
git add .agents/plugins plugins/codex-reflect/.codex-plugin plugins/codex-reflect/hooks plugins/codex-reflect/scripts/capability_probe_hook.py plugins/codex-reflect/skills tests/test_codex_plugin_contract.py
git commit -m "feat: add Codex plugin package scaffold"
```

## Task 3: Implement Codex paths and the shared StateStore

**Files:**
- Create: `plugins/codex-reflect/scripts/lib/codex_paths.py`
- Create: `plugins/codex-reflect/scripts/lib/state_store.py`
- Create: `tests/test_codex_paths.py`
- Create: `tests/test_state_store.py`
- Modify: `plugins/codex-reflect/scripts/lib/reflect_utils.py`
- Modify: `tests/test_reflect_utils.py`
- Modify: `tests/test_memory_hierarchy.py`

- [ ] **Step 1: Write failing Codex path tests**

```python
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lib.codex_paths import get_codex_home, get_project_id, get_project_state_dir


class TestCodexPaths(unittest.TestCase):
    def test_codex_home_honors_environment(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {"CODEX_HOME": root}):
            self.assertEqual(get_codex_home(), Path(root).resolve())

    def test_state_dir_is_below_codex_reflect(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {"CODEX_HOME": root}):
            state = get_project_state_dir("/tmp/example")
            self.assertEqual(state.parent.parent, Path(root).resolve() / "codex-reflect")

    def test_project_id_is_stable_and_path_safe(self):
        first = get_project_id("/tmp/example")
        second = get_project_id("/tmp/example/.")
        self.assertEqual(first, second)
        self.assertRegex(first, r"^[a-f0-9]{16}$")
```

- [ ] **Step 2: Write failing StateStore tests**

```python
class TestStateStore(unittest.TestCase):
    def test_append_round_trips_atomically(self):
        with tempfile.TemporaryDirectory() as root:
            store = StateStore(Path(root))
            store.append({"id": "one", "schema_version": 1})
            self.assertEqual(store.load(), [{"id": "one", "schema_version": 1}])

    def test_clear_returns_removed_items(self):
        with tempfile.TemporaryDirectory() as root:
            store = StateStore(Path(root))
            store.save([{"id": "one"}])
            self.assertEqual(store.clear(), [{"id": "one"}])
            self.assertEqual(store.load(), [])

    def test_malformed_queue_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as root:
            queue = Path(root) / "queue.json"
            queue.parent.mkdir(parents=True, exist_ok=True)
            queue.write_text("{broken", encoding="utf-8")
            with self.assertRaises(CorruptQueueError):
                StateStore(Path(root)).load()
            self.assertEqual(queue.read_text(encoding="utf-8"), "{broken")

    def test_concurrent_appends_do_not_lose_items(self):
        with tempfile.TemporaryDirectory() as root:
            def append(index):
                StateStore(Path(root)).append({"id": str(index)})

            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(append, range(32)))
            items = StateStore(Path(root)).load()
            self.assertEqual({item["id"] for item in items}, {str(index) for index in range(32)})
```

Add `from concurrent.futures import ThreadPoolExecutor` to the test module.

- [ ] **Step 3: Confirm tests fail with import errors**

Run:

```bash
python3 -m unittest tests.test_codex_paths tests.test_state_store -v
```

Expected: FAIL because `lib.codex_paths` and `lib.state_store` do not exist.

- [ ] **Step 4: Implement Codex path helpers**

```python
import hashlib
import os
from pathlib import Path
from typing import Optional


def get_codex_home() -> Path:
    configured = os.environ.get("CODEX_HOME")
    return Path(configured).expanduser().resolve() if configured else Path.home() / ".codex"


def normalize_project_path(project_dir: Optional[str] = None) -> str:
    path = Path(project_dir or os.getcwd()).expanduser().resolve()
    normalized = os.path.normcase(os.path.normpath(str(path)))
    return normalized.replace("\\", "/")


def get_project_id(project_dir: Optional[str] = None) -> str:
    value = normalize_project_path(project_dir).encode("utf-8")
    return hashlib.sha256(value).hexdigest()[:16]


def get_project_state_dir(project_dir: Optional[str] = None) -> Path:
    return get_codex_home() / "codex-reflect" / "projects" / get_project_id(project_dir)
```

- [ ] **Step 5: Implement cross-platform locking and an atomic StateStore**

`state_store.py` locks the first byte of `queue.json.lock` and saves by applying `os.replace` to a temporary file in the same directory. `append` holds the same lock from load through save so concurrent Hook executions do not lose updates.

```python
import json
import os
import tempfile
from pathlib import Path


class CorruptQueueError(RuntimeError):
    pass


class FileLock:
    def __init__(self, path):
        self.path = Path(path)
        self.handle = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+b")
        self.handle.seek(0, os.SEEK_END)
        if self.handle.tell() == 0:
            self.handle.write(b"\0")
            self.handle.flush()
        self.handle.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(self.handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.handle.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        self.handle.close()


class StateStore:
    def __init__(self, project_state_dir: Path):
        self.root = Path(project_state_dir)
        self.queue_path = self.root / "queue.json"
        self.lock_path = self.root / "queue.json.lock"

    def _load_unlocked(self):
        if not self.queue_path.exists():
            return []
        try:
            value = json.loads(self.queue_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise CorruptQueueError(str(error)) from error
        if not isinstance(value, list):
            raise CorruptQueueError("queue root must be a JSON array")
        return value

    def _save_unlocked(self, items):
        self.root.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(dir=str(self.root), prefix="queue-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(items, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self.queue_path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def load(self):
        with FileLock(self.lock_path):
            return self._load_unlocked()

    def save(self, items):
        with FileLock(self.lock_path):
            self._save_unlocked(items)

    def append(self, item):
        with FileLock(self.lock_path):
            items = self._load_unlocked()
            items.append(item)
            self._save_unlocked(items)

    def clear(self):
        with FileLock(self.lock_path):
            items = self._load_unlocked()
            self._save_unlocked([])
            return items
```

- [ ] **Step 6: Switch the reflect_utils queue wrapper to Codex state**

Remove `get_claude_dir`, legacy global migration, Claude cleanup settings, and auto-memory helpers from the new API. Keep the smallest wrapper that preserves existing `load_queue`, `save_queue`, and `append_to_queue` callers.

```python
def get_queue_path(project_dir=None):
    return get_project_state_dir(project_dir) / "queue.json"


def get_backup_dir(project_dir=None):
    return get_project_state_dir(project_dir) / "backups"


def load_queue(project_dir=None):
    return StateStore(get_project_state_dir(project_dir)).load()


def save_queue(items, project_dir=None):
    StateStore(get_project_state_dir(project_dir)).save(items)


def append_to_queue(item, project_dir=None):
    StateStore(get_project_state_dir(project_dir)).append(item)
```

Task 6 replaces Claude memory-hierarchy tests with Codex target tests. In this task, remove Claude path assertions while preserving pattern and queue tests.

- [ ] **Step 7: Pass focused tests and the full suite**

Run:

```bash
python3 -m unittest tests.test_codex_paths tests.test_state_store tests.test_reflect_utils -v
python3 -m unittest discover -s tests -v
```

Expected: all passing.

- [ ] **Step 8: commit**

```bash
git add plugins/codex-reflect/scripts/lib tests
git commit -m "feat: store queues under Codex home"
```

## Task 4: Implement the Codex Hook adapter and real-time capture

**Files:**
- Create: `plugins/codex-reflect/scripts/lib/codex_hooks.py`
- Create: `tests/test_codex_hooks.py`
- Modify: `plugins/codex-reflect/scripts/capture_learning.py`
- Modify: `plugins/codex-reflect/hooks/hooks.json`
- Modify: `tests/test_integration.py`

- [ ] **Step 1: Write failing Hook input/output tests**

```python
class TestCodexHookInput(unittest.TestCase):
    def test_user_prompt_submit_fields_are_normalized(self):
        event = HookEvent.from_dict({
            "session_id": "session-1",
            "turn_id": "turn-1",
            "cwd": "/repo",
            "hook_event_name": "UserPromptSubmit",
            "model": "gpt-test",
            "prompt": "remember: run focused tests",
        })
        self.assertEqual(event.prompt, "remember: run focused tests")
        self.assertEqual(event.cwd, "/repo")

    def test_system_message_uses_codex_common_output(self):
        self.assertEqual(
            system_message("captured"),
            {"continue": True, "systemMessage": "captured"},
        )
```

The integration test passes a temporary `CODEX_HOME` and Hook JSON through subprocess stdin and asserts that the generated `$CODEX_HOME/codex-reflect/projects/*/queue.json` contains one item.

- [ ] **Step 2: Confirm the tests fail**

Run:

```bash
python3 -m unittest tests.test_codex_hooks tests.test_integration.TestCaptureLearning -v
```

Expected: FAIL because `HookEvent` is undefined or the queue path does not match.

- [ ] **Step 3: Implement the Codex Hook adapter**

```python
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class HookEvent:
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
        return cls(
            event_name=str(value.get("hook_event_name", "")),
            cwd=str(value.get("cwd", "") or ""),
            session_id=str(value.get("session_id", "") or ""),
            turn_id=value.get("turn_id"),
            model=value.get("model"),
            prompt=value.get("prompt"),
            tool_name=value.get("tool_name"),
            tool_input=value.get("tool_input") if isinstance(value.get("tool_input"), dict) else {},
            tool_response=value.get("tool_response"),
        )


def system_message(message):
    return {"continue": True, "systemMessage": message}
```

- [ ] **Step 4: Connect capture_learning.py to Codex payloads and state**

Read `prompt` only from `HookEvent.prompt`. Add `schema_version=1`, `session_id`, `turn_id`, `model`, and `source="hook"` to the queue item. Use `event.cwd` as the project when saving. On success, write JSON only to stdout.

```python
event = HookEvent.from_dict(json.loads(sys.stdin.read()))
prompt = event.prompt
if not prompt or not should_include_message(prompt):
    return 0
item_type, patterns, confidence, sentiment, decay_days = detect_patterns(prompt)
if item_type:
    item = create_queue_item(
        message=prompt,
        item_type=item_type,
        patterns=patterns,
        confidence=confidence,
        sentiment=sentiment,
        decay_days=decay_days,
        project=event.cwd,
        session_id=event.session_id,
        turn_id=event.turn_id,
        source="hook",
    )
    append_to_queue(item, event.cwd)
    print(json.dumps(system_message("codex-reflect captured a learning candidate")))
```

On exception, write a warning to stderr and exit 0 so the Codex turn is not blocked.

Switch only the `UserPromptSubmit` command in `hooks/hooks.json` from the probe to `capture_learning.py`. Keep the other three events on write-free probes until Task 5 is complete.

- [ ] **Step 5: Pass focused tests and the full suite**

Run:

```bash
python3 -m unittest tests.test_codex_hooks tests.test_integration.TestCaptureLearning -v
python3 -m unittest discover -s tests -v
```

Expected: all passing.

- [ ] **Step 6: commit**

```bash
git add plugins/codex-reflect/scripts tests
git commit -m "feat: capture Codex prompt feedback from hooks"
```

## Task 5: Implement the SessionStart, PreCompact, and PostToolUse lifecycle

**Files:**
- Delete: `plugins/codex-reflect/scripts/capability_probe_hook.py`
- Modify: `plugins/codex-reflect/scripts/session_start_reminder.py`
- Modify: `plugins/codex-reflect/scripts/check_learnings.py`
- Modify: `plugins/codex-reflect/scripts/post_commit_reminder.py`
- Modify: `plugins/codex-reflect/hooks/hooks.json`
- Modify: `tests/test_integration.py`

- [ ] **Step 1: Write failing integration tests for Codex lifecycle output**

```python
def test_session_start_returns_codex_system_message(self):
    payload = {"hook_event_name": "SessionStart", "cwd": self.project, "session_id": "s1"}
    stdout, _, code = run_python_script(PYTHON_SCRIPTS["session_start_reminder"], json.dumps(payload), self.env)
    self.assertEqual(code, 0)
    self.assertIn("systemMessage", json.loads(stdout))

def test_precompact_creates_project_backup(self):
    stdout, _, code = run_python_script(PYTHON_SCRIPTS["check_learnings"], json.dumps({
        "hook_event_name": "PreCompact", "cwd": self.project, "session_id": "s1"
    }), self.env)
    self.assertEqual(code, 0)
    self.assertEqual(len(list(self.project_state.glob("backups/*.json"))), 1)

def test_post_tool_use_detects_non_amend_commit(self):
    payload = {
        "hook_event_name": "PostToolUse",
        "cwd": self.project,
        "tool_name": "Bash",
        "tool_input": {"cmd": "git commit -m test"},
    }
    stdout, _, _ = run_python_script(PYTHON_SCRIPTS["post_commit_reminder"], json.dumps(payload), self.env)
    self.assertIn("Git commit detected", json.loads(stdout)["systemMessage"])
```

Add an `env=None` parameter to the `run_python_script` test helper and pass the `env=env` keyword argument to the existing `subprocess.run` call. In `setUp`, copy the host environment and override only `CODEX_HOME` with a temporary directory.

- [ ] **Step 2: Confirm tests fail because existing output is Claude-specific**

Run:

```bash
python3 -m unittest tests.test_integration.TestSessionStartReminder tests.test_integration.TestCheckLearnings tests.test_integration.TestPostCommitReminder -v
```

Expected: FAIL because the output is plain text or uses a Claude-specific response shape.

- [ ] **Step 3: Move three Hooks to the shared adapter and StateStore**

- `session_start_reminder.py`: show up to five queue items for `event.cwd`; when uninitialized, return a `systemMessage` that suggests `reflect --scan-history`.
- `check_learnings.py`: produce no output for an empty queue; otherwise atomically write `backups/pre-compact-<timestamp>.json` and return a JSON `systemMessage`.
- `post_commit_reminder.py`: read `cmd` from `HookEvent.tool_input`, falling back to `command` only for Codex builds where `cmd` is absent. Normalize a string or list of strings, and return a JSON `systemMessage` only when the command contains `git commit` but not `--amend`. Do not read other nested fields or tool output.

Every script exits 0 for empty stdin, invalid JSON, or I/O errors.

Switch the `SessionStart`, `PreCompact`, and `PostToolUse` commands in `hooks/hooks.json` to their completed scripts. This removes Phase 0 probes from runtime Hooks, so delete `capability_probe_hook.py` from the package and use a contract test to confirm no references remain.

- [ ] **Step 4: Pass the tests**

Run:

```bash
python3 -m unittest tests.test_integration -v
python3 -m unittest discover -s tests -v
```

Expected: all passing.

- [ ] **Step 5: commit**

```bash
git add plugins/codex-reflect/scripts tests/test_integration.py
git commit -m "feat: adapt reflect lifecycle hooks for Codex"
```

## Task 6: Implement the `AGENTS.md` and Skill TargetResolver

**Files:**
- Create: `plugins/codex-reflect/scripts/lib/target_resolver.py`
- Create: `tests/test_target_resolver.py`
- Replace: `tests/test_memory_hierarchy.py`
- Modify: `plugins/codex-reflect/scripts/lib/reflect_utils.py`

- [ ] **Step 1: Write failing tests for the active instruction chain**

```python
class TestTargetResolver(unittest.TestCase):
    def test_global_override_masks_global_agents(self):
        self.write(self.codex_home / "AGENTS.md", "base")
        self.write(self.codex_home / "AGENTS.override.md", "override")
        targets = TargetResolver(self.codex_home).instruction_targets(self.repo / "src")
        self.assertIn(self.codex_home / "AGENTS.override.md", targets)
        self.assertNotIn(self.codex_home / "AGENTS.md", targets)

    def test_nested_override_wins_in_each_directory(self):
        self.write(self.repo / "AGENTS.md", "root")
        self.write(self.repo / "src" / "AGENTS.md", "src")
        self.write(self.repo / "src" / "AGENTS.override.md", "src override")
        targets = TargetResolver(self.codex_home).instruction_targets(self.repo / "src")
        self.assertEqual(targets[-1], self.repo / "src" / "AGENTS.override.md")

    def test_skill_roots_are_repo_and_user_agents_directories(self):
        resolver = TargetResolver(self.codex_home, user_home=self.home)
        self.assertEqual(resolver.user_skill_root(), self.home / ".agents" / "skills")
        self.assertEqual(resolver.repo_skill_root(self.repo), self.repo / ".agents" / "skills")
```

- [ ] **Step 2: Write failing target-suggestion tests**

```python
def test_path_specific_learning_prefers_nearest_agents_file(self):
    learning = "In src/payments, always run make test-payments"
    target = self.resolver.suggest_instruction_target(learning, self.repo / "src" / "payments")
    self.assertEqual(target, self.repo / "src" / "payments" / "AGENTS.md")

def test_cross_project_skill_prefers_user_scope(self):
    target = self.resolver.suggest_skill_root({"repo-a", "repo-b"}, self.repo)
    self.assertEqual(target, self.home / ".agents" / "skills")
```

- [ ] **Step 3: Confirm the tests fail**

Run:

```bash
python3 -m unittest tests.test_target_resolver -v
```

Expected: FAIL because `TargetResolver` is undefined.

- [ ] **Step 4: Resolve active files and Skill roots**

```python
import subprocess
from pathlib import Path


class TargetResolver:
    def __init__(self, codex_home, user_home=None):
        self.codex_home = Path(codex_home)
        self.user_home = Path(user_home) if user_home else Path.home()

    @staticmethod
    def active_instruction_file(directory):
        override = Path(directory) / "AGENTS.override.md"
        regular = Path(directory) / "AGENTS.md"
        if override.is_file() and override.read_text(encoding="utf-8").strip():
            return override
        if regular.is_file() and regular.read_text(encoding="utf-8").strip():
            return regular
        return None

    def user_skill_root(self):
        return self.user_home / ".agents" / "skills"

    @staticmethod
    def repo_skill_root(repo_root):
        return Path(repo_root) / ".agents" / "skills"

    @staticmethod
    def repository_root(cwd):
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return Path(result.stdout.strip()).resolve()
        return Path(cwd).resolve()

    def instruction_targets(self, cwd):
        cwd = Path(cwd).resolve()
        root = self.repository_root(cwd)
        targets = []
        global_target = self.active_instruction_file(self.codex_home)
        if global_target:
            targets.append(global_target)
        try:
            relative_parts = cwd.relative_to(root).parts
        except ValueError:
            relative_parts = ()
        directory = root
        for part in (None,) + relative_parts:
            if part is not None:
                directory = directory / part
            target = self.active_instruction_file(directory)
            if target:
                targets.append(target)
        return targets

    def suggest_instruction_target(self, learning, cwd):
        cwd = Path(cwd).resolve()
        active = self.active_instruction_file(cwd)
        return active or cwd / "AGENTS.md"

    def suggest_skill_root(self, source_projects, repo_root):
        if len(set(source_projects)) > 1:
            return self.user_skill_root()
        return self.repo_skill_root(repo_root)
```

Select exactly one active file in every directory from the root to the working directory. The production implementation of `suggest_instruction_target` accepts the learning evidence path and passes its directory as `cwd` only for path-specific evidence. General project learning passes the repository root.

- [ ] **Step 5: Map upstream routing to Codex targets**

- global behavior -> active global `AGENTS` file
- project behavior -> repository root `AGENTS.md`
- path-specific -> nearest nested active `AGENTS` file, or a proposal for `AGENTS.md` in that directory if none exists
- skill correction -> existing Skill with a writable authoring source
- multi-project workflow -> user Skill root
- low confidence -> remain in the queue

Return Plugin cache, system, and admin-managed Skills only as `read_only=True` suggestions, never as write targets.

- [ ] **Step 6: Replace Claude memory-hierarchy tests with Codex routing tests**

Replace `tests/test_memory_hierarchy.py` with `TestAgentsHierarchy`, `TestSkillRouting`, and `TestReadOnlyPluginSkill`. Remove assertions for `.claude/rules`, `CLAUDE.local.md`, and auto memory.

- [ ] **Step 7: Pass the tests**

Run:

```bash
python3 -m unittest tests.test_target_resolver tests.test_memory_hierarchy -v
python3 -m unittest discover -s tests -v
```

Expected: all passing.

- [ ] **Step 8: commit**

```bash
git add plugins/codex-reflect/scripts/lib tests
git commit -m "feat: route learnings to Codex guidance targets"
```

## Task 7: Implement the Codex history adapter and redaction

**Files:**
- Create: `plugins/codex-reflect/scripts/lib/codex_history.py`
- Create: `plugins/codex-reflect/scripts/lib/redaction.py`
- Create: `tests/fixtures/codex/rollout-v1.jsonl`
- Create: `tests/fixtures/codex/unknown-rollout.jsonl`
- Create: `tests/test_codex_history.py`
- Modify: `plugins/codex-reflect/scripts/extract_session_learnings.py`
- Modify: `plugins/codex-reflect/scripts/extract_tool_errors.py`
- Modify: `plugins/codex-reflect/scripts/extract_tool_rejections.py`
- Modify: `plugins/codex-reflect/scripts/lib/reflect_utils.py`
- Modify: `tests/test_reflect_utils.py`
- Modify: `tests/test_tool_errors.py`

- [ ] **Step 1: Add sanitized Codex transcript fixtures**

`rollout-v1.jsonl` contains no real user data and reproduces only the currently verified record shape.

```jsonl
{"type":"session_meta","payload":{"id":"session-1","cwd":"/repo","timestamp":"2026-07-18T00:00:00Z"}}
{"type":"event_msg","payload":{"type":"user_message","message":"no, use rg instead of grep","images":[],"local_images":[],"text_elements":[]}}
{"type":"response_item","payload":{"type":"custom_tool_call_output","name":"exec_command","output":"Process exited with code 1: TOKEN=secret-value"}}
```

`unknown-rollout.jsonl`:

```jsonl
{"type":"future_record","payload":{"body":"no, use another parser"}}
```

- [ ] **Step 2: Write failing history-normalization tests**

```python
class TestCodexHistory(unittest.TestCase):
    def test_extracts_user_message_and_session_metadata(self):
        result = parse_transcript(FIXTURES / "rollout-v1.jsonl")
        self.assertEqual(result.session_id, "session-1")
        self.assertEqual(result.cwd, "/repo")
        self.assertEqual(result.user_messages, ["no, use rg instead of grep"])

    def test_unknown_schema_is_reported_not_guessed(self):
        result = parse_transcript(FIXTURES / "unknown-rollout.jsonl")
        self.assertFalse(result.supported)
        self.assertEqual(result.user_messages, [])
        self.assertIn("unsupported transcript schema", result.issues[0])

    def test_session_enumeration_includes_active_and_archived(self):
        files = list_session_files(self.codex_home)
        self.assertEqual(files, sorted([self.active, self.archived]))
```

- [ ] **Step 3: Write failing secret-redaction tests**

```python
def test_redacts_assignment_and_bearer_token(self):
    value = redact_secrets("API_KEY=abc123 Authorization: Bearer token-value")
    self.assertNotIn("abc123", value)
    self.assertNotIn("token-value", value)
    self.assertEqual(value.count("[REDACTED]"), 2)
```

- [ ] **Step 4: Confirm the tests fail**

Run:

```bash
python3 -m unittest tests.test_codex_history -v
```

Expected: FAIL because the modules do not exist.

- [ ] **Step 5: Implement the normalized history model and schema detection**

```python
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


def read_jsonl(path):
    records = []
    with Path(path).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid JSONL at line {line_number}: {error}") from error
            if not isinstance(value, dict):
                raise ValueError(f"record at line {line_number} must be an object")
            records.append(value)
    return records


def parse_transcript(path):
    records = read_jsonl(path)
    known_types = {"session_meta", "event_msg", "response_item", "turn_context"}
    metadata = next(
        (record.get("payload") for record in records if record.get("type") == "session_meta"),
        None,
    )
    has_known_event = any(record.get("type") in known_types - {"session_meta"} for record in records)
    if not isinstance(metadata, dict) or not has_known_event:
        return TranscriptResult(Path(path), False, issues=["unsupported transcript schema"])

    messages = []
    outputs = []
    issues = []
    for record in records:
        record_type = record.get("type")
        payload = record.get("payload")
        if record_type not in known_types:
            issues.append(f"ignored unknown record type: {record_type}")
            continue
        if not isinstance(payload, dict):
            continue
        if record_type == "event_msg" and payload.get("type") == "user_message":
            message = payload.get("message")
            if isinstance(message, str) and message not in messages:
                messages.append(message)
        if record_type == "response_item" and payload.get("type") == "custom_tool_call_output":
            output = payload.get("output")
            if isinstance(output, str):
                outputs.append(output)
            elif output is not None:
                outputs.append(json.dumps(output, ensure_ascii=False, sort_keys=True))

    return TranscriptResult(
        path=Path(path),
        supported=True,
        session_id=str(metadata.get("id", "")),
        cwd=str(metadata.get("cwd", "")),
        timestamp=str(metadata.get("timestamp", "")),
        user_messages=messages,
        tool_outputs=outputs,
        issues=issues,
    )
```

When the same message appears in both `event_msg` and `response_item`, preserve occurrence order and collapse exact text duplicates to one item. Enumerate `sessions/**/*.jsonl` and `archived_sessions/**/*.jsonl`; do not read SQLite databases or UI caches.

- [ ] **Step 6: Implement local redaction**

`redaction.py` targets assignments, Bearer values, JWTs, and OpenAI/GitHub-style tokens, replacing only the value with `[REDACTED]`. Never log the input.

- [ ] **Step 7: Route three extraction scripts through the adapter**

- `extract_session_learnings.py`: `TranscriptResult.user_messages`
- `extract_tool_errors.py`: apply existing error patterns to `TranscriptResult.tool_outputs`
- `extract_tool_rejections.py`: use only records containing known user-rejection text

Turn `reflect_utils.extract_user_messages`, `extract_tool_errors`, and `extract_tool_rejections` into adapter wrappers while preserving the existing detection and aggregation APIs.

- [ ] **Step 8: Pass focused tests and the full suite**

Run:

```bash
python3 -m unittest tests.test_codex_history tests.test_reflect_utils tests.test_tool_errors -v
python3 -m unittest discover -s tests -v
```

Expected: all passing.

- [ ] **Step 9: commit**

```bash
git add plugins/codex-reflect/scripts tests
git commit -m "feat: parse supported Codex session history"
```

## Task 8: `codex exec` semantic adapter

**Files:**
- Create: `plugins/codex-reflect/schemas/learning-analysis.schema.json`
- Create: `plugins/codex-reflect/schemas/tool-error-analysis.schema.json`
- Create: `plugins/codex-reflect/schemas/contradictions.schema.json`
- Modify: `plugins/codex-reflect/scripts/lib/semantic_detector.py`
- Modify: `tests/test_semantic_detector.py`

- [ ] **Step 1: Write failing Codex command-contract tests**

```python
@patch("lib.semantic_detector.subprocess.run")
def test_semantic_analyze_invokes_ephemeral_codex_without_hooks(self, run):
    response = {
        "is_learning": True,
        "type": "correction",
        "confidence": 0.9,
        "reasoning": "Reusable correction",
        "extracted_learning": "Use rg instead of grep",
    }

    def fake_run(command, **kwargs):
        output_index = command.index("--output-last-message") + 1
        Path(command[output_index]).write_text(json.dumps(response), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    run.side_effect = fake_run
    semantic_analyze("no, use rg", model="gpt-test")
    command = run.call_args.args[0]
    self.assertEqual(command[0:2], ["codex", "exec"])
    self.assertIn("--ephemeral", command)
    self.assertEqual(command[command.index("--disable") + 1], "hooks")
    self.assertEqual(command[command.index("--sandbox") + 1], "read-only")
    self.assertEqual(command[command.index("--model") + 1], "gpt-test")


@patch("lib.semantic_detector.subprocess.run")
def test_semantic_analyze_redacts_before_subprocess(self, run):
    def fake_run(command, **kwargs):
        output_index = command.index("--output-last-message") + 1
        Path(command[output_index]).write_text(
            json.dumps({
                "is_learning": False,
                "type": None,
                "confidence": 0,
                "reasoning": "No reusable learning",
                "extracted_learning": None,
            }),
            encoding="utf-8",
        )
        self.assertNotIn("secret-value", kwargs["input"])
        self.assertIn("[REDACTED]", kwargs["input"])
        return subprocess.CompletedProcess(command, 0, "", "")

    run.side_effect = fake_run
    semantic_analyze("API_KEY=secret-value")
```

Rename existing `test_claude_*` tests to `test_codex_*` and replace `claude -p` command assertions with Codex flags.

- [ ] **Step 2: Confirm tests fail because they expect the old Claude command**

Run:

```bash
python3 -m unittest tests.test_semantic_detector -v
```

Expected: FAIL because `command[0]` is `claude`.

- [ ] **Step 3: Add three JSON Schemas**

Required fields in the learning schema:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "additionalProperties": false,
  "required": ["is_learning", "type", "confidence", "reasoning", "extracted_learning"],
  "properties": {
    "is_learning": {"type": "boolean"},
    "type": {"type": ["string", "null"], "enum": ["correction", "positive", "explicit", null]},
    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    "reasoning": {"type": "string"},
    "extracted_learning": {"type": ["string", "null"]}
  }
}
```

The tool-error schema requires `is_learnable`, `refined_guideline`, `confidence`, and `reasoning`. The contradiction schema likewise requires `entry1`, `entry2`, and `conflict` inside `contradictions[]`.

- [ ] **Step 4: Implement the Codex subprocess runner**

```python
def _run_codex(prompt, schema_path, timeout, model=None):
    prompt = redact_secrets(prompt)
    with tempfile.TemporaryDirectory(prefix="codex-reflect-") as temp_dir:
        output_path = Path(temp_dir) / "result.json"
        command = [
            "codex", "exec",
            "--ephemeral",
            "--disable", "hooks",
            "--sandbox", "read-only",
            "--skip-git-repo-check",
            "--cd", temp_dir,
            "--output-schema", str(schema_path),
            "--output-last-message", str(output_path),
            "-",
        ]
        if model:
            command[2:2] = ["--model", model]
        result = subprocess.run(
            command,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if result.returncode != 0 or not output_path.exists():
            return None
        return json.loads(output_path.read_text(encoding="utf-8"))
```

When no model is specified, use the current Codex default and do not hard-code a model slug. Preserve existing `_validate_response`, queue fallback, tool-error validation, and contradiction validation. Replace `CLAUDE.md` wording in prompts with `AGENTS.md` or Skill guidance.

- [ ] **Step 5: Pass tests and schema parsing**

Run:

```bash
python3 -m unittest tests.test_semantic_detector -v
python3 -m json.tool plugins/codex-reflect/schemas/learning-analysis.schema.json
python3 -m json.tool plugins/codex-reflect/schemas/tool-error-analysis.schema.json
python3 -m json.tool plugins/codex-reflect/schemas/contradictions.schema.json
python3 -m unittest discover -s tests -v
```

Expected: all passing.

- [ ] **Step 6: Run an approved live semantic smoke test**

Run this only after user approval because it consumes Codex quota.

Run:

```bash
python3 -c "import sys; sys.path.insert(0, 'plugins/codex-reflect/scripts'); from lib.semantic_detector import semantic_analyze; print(semantic_analyze('remember: run focused tests'))"
```

Expected: a dictionary containing `is_learning=True` and `type='explicit'`. No new Codex session file is created.

- [ ] **Step 7: commit**

```bash
git add plugins/codex-reflect/schemas plugins/codex-reflect/scripts/lib/semantic_detector.py tests/test_semantic_detector.py
git commit -m "feat: validate learnings with Codex exec"
```

## Task 9: Implement the `view-queue` and `skip-reflect` Skills

**Files:**
- Modify: `plugins/codex-reflect/scripts/read_queue.py`
- Create: `plugins/codex-reflect/scripts/clear_queue.py`
- Modify: `plugins/codex-reflect/skills/view-queue/SKILL.md`
- Modify: `plugins/codex-reflect/skills/skip-reflect/SKILL.md`
- Create: `tests/test_queue_commands.py`

- [ ] **Step 1: Write failing queue-command tests**

```python
class TestQueueCommands(unittest.TestCase):
    def test_read_queue_formats_confidence_pattern_and_relative_time(self):
        result = self.run("read_queue.py", cwd=self.project)
        self.assertIn('[0.90] "remember: run tests"', result.stdout)
        self.assertIn("(remember:)", result.stdout)

    def test_clear_queue_requires_confirm_flag(self):
        result = self.run("clear_queue.py", cwd=self.project)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.load_queue(), self.items)

    def test_clear_queue_outputs_removed_items_with_confirm(self):
        result = self.run("clear_queue.py", "--confirm", cwd=self.project)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout), self.items)
        self.assertEqual(self.load_queue(), [])
```

- [ ] **Step 2: Confirm the tests fail**

Run:

```bash
python3 -m unittest tests.test_queue_commands -v
```

Expected: FAIL because formatted output and the clear command are not implemented.

- [ ] **Step 3: Implement deterministic queue commands**

`read_queue.py` outputs raw JSON with `--json`; otherwise it uses the upstream `[0.85] "message" (pattern) - relative time` format. `clear_queue.py` exits 2 without `--confirm`; with confirmation, it clears the queue and writes removed items as JSON to stdout.

- [ ] **Step 4: Replace two Skill probes with final workflows**

`view-queue/SKILL.md`:

```markdown
---
name: view-queue
description: View codex-reflect learning candidates for the current project without changing them.
---

Resolve `../../scripts/read_queue.py` relative to this SKILL.md and run it with the current working directory unchanged. Return its formatted output verbatim. Do not modify queue or target files.
```

`skip-reflect/SKILL.md` uses `read_queue.py --json` to retrieve items, then presents the count and message previews for confirmation. It runs `clear_queue.py --confirm` only after approval and does nothing when cancelled.

- [ ] **Step 5: Pass the tests**

Run:

```bash
python3 -m unittest tests.test_queue_commands tests.test_codex_plugin_contract -v
python3 -m unittest discover -s tests -v
```

Expected: all passing.

- [ ] **Step 6: commit**

```bash
git add plugins/codex-reflect/scripts plugins/codex-reflect/skills tests
git commit -m "feat: add Codex queue management skills"
```

## Task 10: Implement the `reflect` preparation command and Skill workflow

**Files:**
- Create: `plugins/codex-reflect/scripts/commands/__init__.py`
- Create: `plugins/codex-reflect/scripts/commands/reflect.py`
- Modify: `plugins/codex-reflect/skills/reflect/SKILL.md`
- Create: `tests/test_reflect_command.py`

- [ ] **Step 1: Write failing argument-contract and no-write tests**

```python
class TestReflectCommand(unittest.TestCase):
    def test_parser_supports_fork_flags(self):
        args = parse_args([
            "--dry-run", "--scan-history", "--days", "30", "--targets",
            "--review", "--dedupe", "--organize", "--include-tool-errors",
            "--model", "gpt-test",
        ])
        self.assertTrue(args.dry_run)
        self.assertEqual(args.days, 30)
        self.assertEqual(args.model, "gpt-test")

    def test_dry_run_does_not_change_queue_or_targets(self):
        before_queue = self.queue.read_bytes()
        before_agents = self.agents.read_bytes()
        result = prepare_reflection(self.context, dry_run=True)
        self.assertGreaterEqual(len(result["candidates"]), 1)
        self.assertEqual(self.queue.read_bytes(), before_queue)
        self.assertEqual(self.agents.read_bytes(), before_agents)

    def test_unknown_transcripts_are_reported(self):
        result = prepare_reflection(self.context, scan_history=True)
        self.assertEqual(result["history"]["unsupported_sessions"], 1)
```

- [ ] **Step 2: Confirm the tests fail**

Run:

```bash
python3 -m unittest tests.test_reflect_command -v
```

Expected: FAIL because `commands.reflect` is undefined.

- [ ] **Step 3: Implement parse_args and the preparation pipeline**

```python
def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--scan-history", action="store_true")
    parser.add_argument("--days", type=int)
    parser.add_argument("--targets", action="store_true")
    parser.add_argument("--review", action="store_true")
    parser.add_argument("--dedupe", action="store_true")
    parser.add_argument("--organize", action="store_true")
    parser.add_argument("--include-tool-errors", action="store_true")
    parser.add_argument("--model")
    return parser.parse_args(argv)
```

`prepare_reflection` invokes the queue, history adapter, semantic adapter, and `TargetResolver` in order, then returns a JSON-serializable dictionary with the following shape. Values are examples; keys and value types define the contract.

```json
{
  "project": "/repo",
  "candidates": [],
  "targets": [],
  "duplicates": [],
  "contradictions": [],
  "history": {"scanned": 0, "unsupported_sessions": 0, "issues": []}
}
```

On semantic failure, mark the item with `semantic_status="unavailable"` and do not remove it. Always retain explicit items in `candidates`. `--targets` returns only the target list, `--review` includes stale queue items, and `--dedupe` or `--organize` adds the corresponding analysis. The command itself never edits `AGENTS.md` or Skills. Task 12 adds a capability summary to this response.

- [ ] **Step 4: Define the human-review gate in the `reflect` Skill**

The Skill reads JSON from the preparation command and performs these steps in order:

1. Explain the first history scan scope and provider data transfer, then obtain approval.
2. Show a candidate summary.
3. Ask the user to apply all, select, review details, or skip.
4. Confirm target routing for each candidate.
5. Create the exact file diff.
6. Obtain final confirmation.
7. Change `AGENTS.md` or a writable Skill with the edit tool only after confirmation.
8. If a target changed during review, stop and regenerate the diff.
9. Remove only applied items from the queue.

With `--dry-run`, stop after displaying the proposal without questions from step 3 onward or any writes. Show only improvement proposals for read-only Plugin or system Skills. Never read or write Codex Memories.

- [ ] **Step 5: Pass the Skill contract test and focused tests**

Add a test to `tests/test_codex_plugin_contract.py` requiring `reflect/SKILL.md` to contain nine workflow keywords: `dry-run`, `scan-history`, `apply all`, `select`, `details`, `skip`, `final confirmation`, `AGENTS.md`, and `queue`.

Run:

```bash
python3 -m unittest tests.test_reflect_command tests.test_codex_plugin_contract -v
python3 -m unittest discover -s tests -v
```

Expected: all passing.

- [ ] **Step 6: commit**

```bash
git add plugins/codex-reflect/scripts/commands plugins/codex-reflect/skills/reflect tests
git commit -m "feat: add reviewed Codex reflection workflow"
```

## Task 11: `reflect-skills` discovery workflow

**Files:**
- Create: `plugins/codex-reflect/scripts/commands/reflect_skills.py`
- Modify: `plugins/codex-reflect/skills/reflect-skills/SKILL.md`
- Create: `tests/test_reflect_skills_command.py`

- [ ] **Step 1: Write failing discovery-input tests**

```python
class TestReflectSkillsCommand(unittest.TestCase):
    def test_defaults_to_current_project_and_fourteen_days(self):
        args = parse_args([])
        self.assertEqual(args.days, 14)
        self.assertIsNone(args.project)
        self.assertFalse(args.all_projects)

    def test_collects_only_supported_sessions_in_date_range(self):
        result = collect_discovery_input(self.context, days=14)
        self.assertEqual(result["supported_sessions"], 2)
        self.assertEqual(result["unsupported_sessions"], 1)
        self.assertEqual(result["projects"], [str(self.project)])

    def test_existing_skills_include_repo_and_user_authoring_sources(self):
        result = collect_existing_skills(self.project, self.home)
        self.assertEqual({item["name"] for item in result}, {"deploy", "daily-review"})
```

- [ ] **Step 2: Confirm the tests fail**

Run:

```bash
python3 -m unittest tests.test_reflect_skills_command -v
```

Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement the deterministic discovery-input collector**

`parse_args` supports `--days` with a default of 14, `--project`, `--all-projects`, and `--dry-run`. The collector returns user messages, working directories, timestamps, and existing Skill metadata from supported transcripts as JSON.

```python
@dataclass(frozen=True)
class DiscoveryContext:
    codex_home: Path
    project: Path
    user_home: Path
    now: datetime


def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--project")
    parser.add_argument("--all-projects", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def collect_existing_skills(project, user_home):
    roots = [
        Path(project) / ".agents" / "skills",
        Path(user_home) / ".agents" / "skills",
    ]
    result = []
    for root in roots:
        if not root.is_dir():
            continue
        for skill_file in sorted(root.glob("*/SKILL.md")):
            name = skill_file.parent.name
            for line in skill_file.read_text(encoding="utf-8").splitlines():
                if line.startswith("name:"):
                    name = line.split(":", 1)[1].strip()
                    break
            result.append({"name": name, "path": str(skill_file), "writable": os.access(skill_file, os.W_OK)})
    return result


def collect_discovery_input(context, days=14, project=None, all_projects=False):
    cutoff = context.now - timedelta(days=days)
    selected_project = Path(project or context.project).resolve()
    sessions = []
    unsupported = 0
    projects = set()
    for path in list_session_files(context.codex_home):
        transcript = parse_transcript(path)
        if not transcript.supported:
            unsupported += 1
            continue
        try:
            timestamp = datetime.fromisoformat(transcript.timestamp.replace("Z", "+00:00"))
        except ValueError:
            unsupported += 1
            continue
        transcript_project = Path(transcript.cwd).resolve()
        if timestamp < cutoff or (not all_projects and transcript_project != selected_project):
            continue
        projects.add(str(transcript_project))
        sessions.append({
            "session_id": transcript.session_id,
            "project": str(transcript_project),
            "timestamp": transcript.timestamp,
            "messages": transcript.user_messages,
        })
    return {
        "supported_sessions": len(sessions),
        "unsupported_sessions": unsupported,
        "projects": sorted(projects),
        "sessions": sessions,
        "existing_skills": collect_existing_skills(selected_project, context.user_home),
    }
```

Normalize `context.now` and transcript timestamps in test fixtures to timezone-aware UTC. The Codex instance running the Skill performs pattern clustering and Skill-content generation; do not add hard-coded keyword clusters.

- [ ] **Step 4: Replace the `reflect-skills` probe with the final workflow**

The Skill performs these steps from collector JSON:

1. Compare multi-step intent and workflow semantically.
2. Present only candidates whose intent appears multiple times.
3. Classify semantic matches with existing Skills as improvements.
4. Show the name, description, evidence count, and source projects.
5. Confirm the candidate and destination.
6. Propose `$REPO_ROOT/.agents/skills/<name>/SKILL.md` for repository scope and `$HOME/.agents/skills/<name>/SKILL.md` for cross-project scope.
7. Generate a Skill with valid frontmatter only after final confirmation.
8. Never generate a file during `--dry-run`.

Do not edit Plugin cache, system, or admin-managed Skills directly.

- [ ] **Step 5: Pass the tests**

Run:

```bash
python3 -m unittest tests.test_reflect_skills_command tests.test_codex_plugin_contract -v
python3 -m unittest discover -s tests -v
```

Expected: all passing.

- [ ] **Step 6: commit**

```bash
git add plugins/codex-reflect/scripts/commands/reflect_skills.py plugins/codex-reflect/skills/reflect-skills tests
git commit -m "feat: discover reusable skills from Codex history"
```

## Task 12: Implement CapabilityProbe and graceful degradation

**Files:**
- Create: `plugins/codex-reflect/scripts/lib/capabilities.py`
- Create: `tests/test_capabilities.py`
- Modify: `plugins/codex-reflect/scripts/session_start_reminder.py`
- Modify: `plugins/codex-reflect/scripts/commands/reflect.py`

- [ ] **Step 1: Write capability tests**

```python
class TestCapabilities(unittest.TestCase):
    @patch("lib.capabilities.subprocess.run")
    def test_reports_codex_version(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, "codex-cli 0.144.1\n", "")
        result = probe_capabilities(self.codex_home)
        self.assertEqual(result.codex_version, "0.144.1")

    def test_history_none_disables_only_history_features(self):
        self.config.write_text('[history]\npersistence = "none"\n', encoding="utf-8")
        result = probe_capabilities(self.codex_home)
        self.assertFalse(result.history_available)
        self.assertTrue(result.realtime_queue_available)

    def test_missing_session_dirs_is_not_core_failure(self):
        result = probe_capabilities(self.codex_home)
        self.assertIn("No saved Codex sessions found", result.warnings)
        self.assertTrue(result.realtime_queue_available)
```

- [ ] **Step 2: Confirm the tests fail**

Run:

```bash
python3 -m unittest tests.test_capabilities -v
```

Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement a dependency-free CapabilityProbe**

To support Python 3.8, avoid `tomllib` and use a narrow line parser for only `[history] persistence = "none"` in `config.toml`. Other checks cover `codex --version`, session directories, and state-directory writability.

```python
@dataclass
class Capabilities:
    codex_version: Optional[str]
    history_available: bool
    semantic_available: bool
    realtime_queue_available: bool
    warnings: List[str]
```

Do not infer Hook trust from internal configuration. When no queue has been created, provide a diagnostic message that directs the user to `/hooks`.

- [ ] **Step 4: Show capabilities in SessionStart and the reflection summary**

Report unavailable history, unknown transcripts, and unavailable semantic validation separately. When the core queue works, do not describe the entire Plugin as failed. Do not fall back from unsupported features to unrelated logs, SQLite databases, or legacy Skill installation.

- [ ] **Step 5: Pass the tests**

Run:

```bash
python3 -m unittest tests.test_capabilities tests.test_integration tests.test_reflect_command -v
python3 -m unittest discover -s tests -v
```

Expected: all passing.

- [ ] **Step 6: commit**

```bash
git add plugins/codex-reflect/scripts tests
git commit -m "feat: report Codex capability gaps safely"
```

## Task 13: Remove Claude runtime artifacts and complete Codex documentation and CI

**Files:**
- Delete: `.claude-plugin/`
- Delete: `commands/`
- Delete: `SKILL.md`
- Delete: `plugins/codex-reflect/scripts/legacy/`
- Replace: `CLAUDE.md` -> `AGENTS.md`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `DISTRIBUTION.md`
- Modify: `RELEASING.md`
- Modify: `.github/workflows/test.yml`
- Preserve: `LICENSE`
- Modify: `tests/test_integration.py`
- Modify: `tests/test_codex_plugin_contract.py`

- [ ] **Step 1: Add failing Codex-only documentation contract tests**

```python
def test_claude_runtime_manifests_are_removed(self):
    self.assertFalse((REPO_ROOT / ".claude-plugin").exists())
    self.assertFalse((REPO_ROOT / "commands").exists())
    self.assertFalse((REPO_ROOT / "SKILL.md").exists())

def test_license_preserves_upstream_notice(self):
    license_text = (REPO_ROOT / "LICENSE").read_text(encoding="utf-8")
    self.assertIn("Copyright (c) 2025 Bayram Annakov", license_text)

def test_readme_documents_attribution_and_codex_gaps(self):
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    for text in ("BayramAnnakov/claude-reflect", "Hook trust", "transcript", "Codex Memories"):
        self.assertIn(text, readme)
```

- [ ] **Step 2: Confirm the contract fails on obsolete artifacts**

Run:

```bash
python3 -m unittest tests.test_codex_plugin_contract -v
```

Expected: FAIL because `.claude-plugin`, `commands`, or the root `SKILL.md` still exists.

- [ ] **Step 3: Remove Claude-only runtime artifacts**

Run:

```bash
git rm -r .claude-plugin commands plugins/codex-reflect/scripts/legacy
git rm SKILL.md
git mv CLAUDE.md AGENTS.md
```

Rewrite `AGENTS.md` as a contributor guide that explains the Codex Plugin layout, test commands, Phase 0/E2E commands, and MIT attribution. Remove Claude Hook schemas, `.claude` paths, and Claude commands.

- [ ] **Step 4: Rewrite the README and distribution documentation for Codex only**

The README must contain these sections:

1. Purpose of `codex-reflect`
2. `claude-reflect` fork and MIT attribution
3. marketplace install
4. Hook trust instructions
5. Four upstream-named Skills and their arguments
6. Real-time capture and human review
7. `$CODEX_HOME/codex-reflect` state
8. Provider data transfer from the semantic subprocess
9. Capability gaps involving transcript schemas, hosted tools, and Memories
10. macOS, Linux, and Windows support

Rewrite `DISTRIBUTION.md` for Codex marketplace distribution and `RELEASING.md` for manifest versions, package tests, Codex E2E, and tagging. Preserve historical entries in `CHANGELOG.md` and add a `4.0.0-rc.1` Codex-only breaking-change entry at the top.

- [ ] **Step 5: Update CI paths and contract checks**

Change Hook smoke paths in `.github/workflows/test.yml` to:

```yaml
- name: Run tests
  run: python -m pytest tests/ -v

- name: Validate JSON files
  shell: bash
  run: |
    python -m json.tool .agents/plugins/marketplace.json
    python -m json.tool plugins/codex-reflect/.codex-plugin/plugin.json
    python -m json.tool plugins/codex-reflect/hooks/hooks.json

- name: Test hook scripts are invokable
  shell: bash
  run: |
    echo '{"hook_event_name":"SessionStart","cwd":"."}' | python plugins/codex-reflect/scripts/session_start_reminder.py
    echo '{"hook_event_name":"PostToolUse","cwd":".","tool_input":{"command":"true"}}' | python plugins/codex-reflect/scripts/post_commit_reminder.py
    echo '{"hook_event_name":"UserPromptSubmit","cwd":".","prompt":"test"}' | python plugins/codex-reflect/scripts/capture_learning.py
```

Keep the existing CI matrix of `ubuntu-latest`, `macos-latest`, and `windows-latest` with Python 3.8 and 3.11.

- [ ] **Step 6: Run the Claude runtime dependency scan and full tests**

Run:

```bash
rg -n "CLAUDE_PLUGIN_ROOT|CLAUDE_PLUGIN_DATA|~/.claude|claude -p|\.claude-plugin|/reflect-skills|/view-queue|/skip-reflect" plugins AGENTS.md
python3 -m unittest discover -s tests -v
git diff --check
```

Expected: `rg` exits 1 with no matches. Documentation containing attribution or migration explanations and tests asserting the absence of old artifacts are outside this runtime scan. All tests pass and `git diff --check` exits 0.

- [ ] **Step 7: commit**

```bash
git add -A
git commit -m "docs: complete Codex-only plugin migration"
```

## Task 14: Complete the release gate and local E2E

**Files:**
- Modify only if verification reveals a defect: files owned by Tasks 2 through 13
- Update test count only after final run: `README.md`

- [ ] **Step 1: Run fresh automated verification**

Run:

```bash
python3 -m unittest discover -s tests -v
python3 -m pytest tests/ -v
python3 -m json.tool .agents/plugins/marketplace.json
python3 -m json.tool plugins/codex-reflect/.codex-plugin/plugin.json
python3 -m json.tool plugins/codex-reflect/hooks/hooks.json
git diff --check
```

Expected: every command exits 0. Update the README badge with the test count from this run.

- [ ] **Step 2: Obtain approval for Plugin installation and Hook trust**

Ask the user for approval before running these commands because they change local user state. Remove and reinstall from the same marketplace so the probe bundle installed during Phase 0 is definitely replaced by the latest implementation.

```bash
codex plugin remove codex-reflect@codex-reflect-marketplace
codex plugin add codex-reflect@codex-reflect-marketplace
codex plugin list
```

Expected: the Plugin is `installed, enabled`. A new session shows four Hook groups under `/hooks`. If they are not trusted, review and trust the exact Hook definitions in the UI.

- [ ] **Step 3: Run real-time capture E2E**

Start Codex in a new temporary Git repository and send:

```text
remember: always run focused tests before the full suite
```

Expected: a capture notification appears and `$codex-reflect:view-queue` shows one explicit candidate.

- [ ] **Step 4: Run dry-run and apply-gate E2E**

Run in Codex:

```text
$codex-reflect:reflect --dry-run
```

Expected: a proposal appears, but the queue and `AGENTS.md` do not change.

Next, run `$codex-reflect:reflect`, cancel before final confirmation, and verify no write occurred. Run it again, approve, and confirm that only the selected learning was added to `AGENTS.md`.

- [ ] **Step 5: Run history and Skill-discovery E2E**

Confirm that `$codex-reflect:reflect --scan-history --days 14` displays supported and unsupported session counts. Then run `$codex-reflect:reflect-skills --dry-run --days 14` and confirm it creates no file and returns either an evidence-backed candidate or a reason that no repetition was found.

- [ ] **Step 6: Verify uninstall preservation**

After user approval, remove the Plugin and confirm that generated `AGENTS.md` files and user/repository Skills remain.

```bash
codex plugin remove codex-reflect@codex-reflect-marketplace
```

- [ ] **Step 7: Check final status and commit range**

Run:

```bash
git status --short --branch
git log --oneline --decorate --max-count=15
```

Expected: only intended commits are present and the worktree is clean. If E2E required a defect fix, add a focused regression test and make an additional commit named for that component.

## Spec coverage checklist

| Spec requirement | Plan task |
|---|---|
| Codex Plugin and four upstream-named Skills | Tasks 2, 9, 10, 11 |
| real-time capture and lifecycle | Tasks 4, 5 |
| `$CODEX_HOME/codex-reflect` state | Task 3 |
| `AGENTS.md` and Skills routing | Task 6 |
| active and archived history | Task 7 |
| `codex exec` semantic validation | Task 8 |
| human review and final confirmation | Tasks 9, 10, 11 |
| tool errors and rejections | Task 7, Task 10 |
| capability gaps and no large workaround | Tasks 2, 12, 14 |
| privacy and redaction | Tasks 7, 8, 13 |
| macOS, Linux, and Windows | Tasks 3, 13, 14 |
| MIT attribution and Codex-only documentation | Task 13 |
| release gates and E2E | Task 14 |
