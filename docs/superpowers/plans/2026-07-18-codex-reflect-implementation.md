# codex-reflect Codex 専用化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `claude-reflect` の feedback loop、履歴分析、Skill 発見を、Codex Hooks・Plugins・Skills・`AGENTS.md` に適合した Codex 専用 OSS Plugin として提供する。

**Architecture:** fork 元の検出・confidence・decay・semantic validation ロジックを platform-independent core として維持し、Codex 固有の Hook、履歴、target、state、subprocess を adapter に隔離する。自動捕捉は Hook、対話と最終確認は fork 元準拠の 4 Skills、共有状態は `$CODEX_HOME/codex-reflect` が担当する。

**Tech Stack:** Python 3.8+ standard library、Codex Plugin manifest／Hooks／Agent Skills、JSON／JSONL、`unittest`／`pytest`、GitHub Actions（macOS・Linux・Windows）

---

## 実装前提

- 承認済み設計: `docs/superpowers/specs/2026-07-18-codex-reflect-design.md`
- baseline: `python3 -m unittest discover -s tests -v` で 222 tests passing
- 実装は TDD で進め、各 task を独立 commit にする。
- Phase 0 の capability spike で Codex 自体の blocker が判明した場合、複雑な workaround を追加せず停止して設計へ戻る。
- Plugin の install／remove、Hook trust、`$CODEX_HOME` への書き込みは local user state を変更するため、実行前にユーザー承認を得る。

## 最終 file map

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

## Task 1: Runtime を Codex Plugin bundle 配下へ移す

**Files:**
- Move: `scripts/` -> `plugins/codex-reflect/scripts/`
- Move: `assets/` -> `plugins/codex-reflect/assets/`
- Modify: `tests/test_integration.py`
- Modify: `tests/test_memory_hierarchy.py`
- Modify: `tests/test_reflect_utils.py`
- Modify: `tests/test_semantic_detector.py`
- Modify: `tests/test_tool_errors.py`

- [ ] **Step 1: 移動前 baseline を実行する**

Run:

```bash
python3 -m unittest discover -s tests -v
```

Expected: `Ran 222 tests`、`OK`。

- [ ] **Step 2: runtime と asset を Plugin bundle へ移す**

Run:

```bash
mkdir -p plugins/codex-reflect
git mv scripts plugins/codex-reflect/scripts
git mv assets plugins/codex-reflect/assets
```

- [ ] **Step 3: tests が旧 path を参照して失敗することを確認する**

Run:

```bash
python3 -m unittest discover -s tests -v
```

Expected: `ModuleNotFoundError: No module named 'lib'` または旧 `scripts/` path の file-not-found で FAIL。

- [ ] **Step 4: 5 test modules の runtime root を更新する**

各 file で repository root 直下の `scripts` 参照を次へ置換する。

```python
REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = REPO_ROOT / "plugins" / "codex-reflect"
SCRIPTS_DIR = PLUGIN_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
```

`tests/test_integration.py` の `SCRIPTS_DIR`、その他 4 files の `sys.path.insert` を同じ定義へ揃える。test fixture 内で repository root の `scripts` を組み立てている箇所も `PLUGIN_ROOT / "scripts"` に変更する。

- [ ] **Step 5: behavior-preserving move を検証する**

Run:

```bash
python3 -m unittest discover -s tests -v
```

Expected: 222 tests passing。

- [ ] **Step 6: commit**

```bash
git add plugins/codex-reflect tests
git commit -m "refactor: move runtime into Codex plugin bundle"
```

## Task 2: Codex Plugin package contract と Phase 0 scaffold

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

- [ ] **Step 1: package contract の failing tests を書く**

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

- [ ] **Step 2: contract test が fail することを確認する**

Run:

```bash
python3 -m unittest tests.test_codex_plugin_contract -v
```

Expected: manifest または marketplace が存在せず FAIL。

- [ ] **Step 3: marketplace と manifest を作る**

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

- [ ] **Step 4: 4 Skills を discovery probe として作る**

各 `SKILL.md` は正しい fork 元名を frontmatter に持たせる。Phase 0 では次のように file 自身の読み込みを明示するだけとし、Task 9〜11 で最終 workflow へ置換する。

```markdown
---
name: reflect
description: Review captured Codex corrections and propose durable AGENTS.md or Skill updates.
---

Resolve `../../scripts/capability_probe_hook.py` relative to this SKILL.md and run it with stdin `{"hook_event_name":"SkillProbe"}`. Report its `systemMessage` and do not edit files.
```

残りは `name` を `reflect-skills`、`view-queue`、`skip-reflect` に置換し、同じ write-free probe を実行する。

- [ ] **Step 5: write-free な Phase 0 Hook probe と config を作る**

この時点では移植前の runtime Hook を登録しない。`capability_probe_hook.py` は Hook payload の既知 field 名だけを返し、prompt 本文や file を保存しない。

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

- [ ] **Step 6: package contract を通す**

Run:

```bash
python3 -m unittest tests.test_codex_plugin_contract -v
```

Expected: 3 tests passing。

- [ ] **Step 7: Phase 0 の Plugin discovery を手動検証する**

この step は user config を変更し Codex quota を 1 invocation 分消費するため、実行前にユーザー承認を得る。

Run:

```bash
codex plugin marketplace add .
codex plugin add codex-reflect@codex-reflect-marketplace
codex plugin list
printf 'Reply with exactly: codex-reflect semantic probe ok' | codex exec --ephemeral --disable hooks --sandbox read-only --skip-git-repo-check -
```

Expected: `codex-reflect@codex-reflect-marketplace` が `installed, enabled`。`codex exec` は 1 回で終了し、Hook probe を再帰させない。CLI、desktop、IDE extension の各 surface で新しい session を開始し、4 Skills の表示、`$codex-reflect:reflect` の probe、`/hooks` の 4 Hook groups を確認する。trust 後、各 event の probe は event 名と既知 field 名だけを返す。各 surface と Skill／Hook の `state_root` が同じであり、実際の `$CODEX_HOME/codex-reflect` directory と project file は作られない。

Skills が表示されない場合は [openai/codex#22078](https://github.com/openai/codex/issues/22078) と同系統かを記録し、この plan の実行を停止する。legacy Skill の二重 install は行わない。

- [ ] **Step 8: commit**

```bash
git add .agents/plugins plugins/codex-reflect/.codex-plugin plugins/codex-reflect/hooks plugins/codex-reflect/scripts/capability_probe_hook.py plugins/codex-reflect/skills tests/test_codex_plugin_contract.py
git commit -m "feat: add Codex plugin package scaffold"
```

## Task 3: Codex paths と共有 StateStore

**Files:**
- Create: `plugins/codex-reflect/scripts/lib/codex_paths.py`
- Create: `plugins/codex-reflect/scripts/lib/state_store.py`
- Create: `tests/test_codex_paths.py`
- Create: `tests/test_state_store.py`
- Modify: `plugins/codex-reflect/scripts/lib/reflect_utils.py`
- Modify: `tests/test_reflect_utils.py`
- Modify: `tests/test_memory_hierarchy.py`

- [ ] **Step 1: Codex path の failing tests を書く**

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

- [ ] **Step 2: StateStore の failing tests を書く**

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

test module に `from concurrent.futures import ThreadPoolExecutor` を追加する。

- [ ] **Step 3: tests が import error で fail することを確認する**

Run:

```bash
python3 -m unittest tests.test_codex_paths tests.test_state_store -v
```

Expected: `lib.codex_paths`／`lib.state_store` が存在せず FAIL。

- [ ] **Step 4: Codex path helpers を実装する**

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

- [ ] **Step 5: cross-platform lock と atomic StateStore を実装する**

`state_store.py` は `queue.json.lock` の先頭 1 byte を lock し、保存は同一 directory の temporary file を `os.replace` する。`append` は load から save まで同じ lock を保持し、同時 Hook 実行で update を失わない。

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

- [ ] **Step 6: reflect_utils の queue wrapper を Codex state へ切り替える**

`get_claude_dir`、legacy global migration、Claude cleanup setting、auto-memory helpers を新 API から外す。既存の `load_queue`、`save_queue`、`append_to_queue` 呼び出し元を壊さない最小 wrapper にする。

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

Claude memory hierarchy tests は Task 6 の Codex target tests へ置き換えるため、この task では Claude path assertions を削除し、pattern／queue tests を維持する。

- [ ] **Step 7: focused tests と full suite を通す**

Run:

```bash
python3 -m unittest tests.test_codex_paths tests.test_state_store tests.test_reflect_utils -v
python3 -m unittest discover -s tests -v
```

Expected: all passing。

- [ ] **Step 8: commit**

```bash
git add plugins/codex-reflect/scripts/lib tests
git commit -m "feat: store queues under Codex home"
```

## Task 4: Codex Hook adapter と realtime capture

**Files:**
- Create: `plugins/codex-reflect/scripts/lib/codex_hooks.py`
- Create: `tests/test_codex_hooks.py`
- Modify: `plugins/codex-reflect/scripts/capture_learning.py`
- Modify: `plugins/codex-reflect/hooks/hooks.json`
- Modify: `tests/test_integration.py`

- [ ] **Step 1: Hook input／output の failing tests を書く**

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

Integration test は temporary `CODEX_HOME` と Hook JSON を subprocess stdin に渡し、生成された `$CODEX_HOME/codex-reflect/projects/*/queue.json` に 1 item が入ることを assert する。

- [ ] **Step 2: failing tests を確認する**

Run:

```bash
python3 -m unittest tests.test_codex_hooks tests.test_integration.TestCaptureLearning -v
```

Expected: `HookEvent` が未定義、または queue path 不一致で FAIL。

- [ ] **Step 3: Codex Hook adapter を実装する**

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

- [ ] **Step 4: capture_learning.py を Codex payload と state に接続する**

`prompt` を `HookEvent.prompt` からのみ取得し、queue item に `schema_version=1`、`session_id`、`turn_id`、`model`、`source="hook"` を追加する。保存時の project は `event.cwd` とする。成功時 stdout は JSON だけにする。

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

exception は stderr に warning を出して exit 0 とし、Codex turn を block しない。

`hooks/hooks.json` の `UserPromptSubmit` command だけを probe から `capture_learning.py` に切り替える。ほかの 3 events は Task 5 が完了するまで write-free probe のままにする。

- [ ] **Step 5: focused tests と full suite を通す**

Run:

```bash
python3 -m unittest tests.test_codex_hooks tests.test_integration.TestCaptureLearning -v
python3 -m unittest discover -s tests -v
```

Expected: all passing。

- [ ] **Step 6: commit**

```bash
git add plugins/codex-reflect/scripts tests
git commit -m "feat: capture Codex prompt feedback from hooks"
```

## Task 5: SessionStart・PreCompact・PostToolUse lifecycle

**Files:**
- Delete: `plugins/codex-reflect/scripts/capability_probe_hook.py`
- Modify: `plugins/codex-reflect/scripts/session_start_reminder.py`
- Modify: `plugins/codex-reflect/scripts/check_learnings.py`
- Modify: `plugins/codex-reflect/scripts/post_commit_reminder.py`
- Modify: `plugins/codex-reflect/hooks/hooks.json`
- Modify: `tests/test_integration.py`

- [ ] **Step 1: Codex lifecycle output の failing integration tests を書く**

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

test helper `run_python_script` は `env=None` parameter を追加し、既存の `subprocess.run` 呼び出しへ keyword argument `env=env` を追加する。`setUp` では host の environment を copy して temporary `CODEX_HOME` だけを上書きする。

- [ ] **Step 2: existing Claude output との差で fail することを確認する**

Run:

```bash
python3 -m unittest tests.test_integration.TestSessionStartReminder tests.test_integration.TestCheckLearnings tests.test_integration.TestPostCommitReminder -v
```

Expected: plain text または Claude-specific response shape のため FAIL。

- [ ] **Step 3: 3 hooks を共通 adapter と StateStore に切り替える**

- `session_start_reminder.py`: `event.cwd` の queue を最大 5 件表示し、未初期化なら「`reflect --scan-history` を提案する」文を含む `systemMessage` を返す。
- `check_learnings.py`: queue が空なら no output、存在すれば `backups/pre-compact-<timestamp>.json` を atomic write し JSON `systemMessage` を返す。
- `post_commit_reminder.py`: `HookEvent.tool_input` の `cmd` を読み、値がない Codex build だけ `command` を読む。string または string list を正規化し、`git commit` を含み `--amend` を含まない場合だけ JSON `systemMessage` を返す。その他の nested fields や tool output は読まない。

各 script は空 stdin、invalid JSON、I/O error で exit 0 とする。

`hooks/hooks.json` の `SessionStart`、`PreCompact`、`PostToolUse` commands をそれぞれ完成した script に切り替える。これで Phase 0 probe は runtime Hook から外れるため、`capability_probe_hook.py` は package から削除し、contract test で参照が残っていないことを確認する。

- [ ] **Step 4: tests を通す**

Run:

```bash
python3 -m unittest tests.test_integration -v
python3 -m unittest discover -s tests -v
```

Expected: all passing。

- [ ] **Step 5: commit**

```bash
git add plugins/codex-reflect/scripts tests/test_integration.py
git commit -m "feat: adapt reflect lifecycle hooks for Codex"
```

## Task 6: `AGENTS.md`／Skill TargetResolver

**Files:**
- Create: `plugins/codex-reflect/scripts/lib/target_resolver.py`
- Create: `tests/test_target_resolver.py`
- Replace: `tests/test_memory_hierarchy.py`
- Modify: `plugins/codex-reflect/scripts/lib/reflect_utils.py`

- [ ] **Step 1: active instruction chain の failing tests を書く**

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

- [ ] **Step 2: target suggestion の failing tests を書く**

```python
def test_path_specific_learning_prefers_nearest_agents_file(self):
    learning = "In src/payments, always run make test-payments"
    target = self.resolver.suggest_instruction_target(learning, self.repo / "src" / "payments")
    self.assertEqual(target, self.repo / "src" / "payments" / "AGENTS.md")

def test_cross_project_skill_prefers_user_scope(self):
    target = self.resolver.suggest_skill_root({"repo-a", "repo-b"}, self.repo)
    self.assertEqual(target, self.home / ".agents" / "skills")
```

- [ ] **Step 3: failing tests を確認する**

Run:

```bash
python3 -m unittest tests.test_target_resolver -v
```

Expected: `TargetResolver` が未定義で FAIL。

- [ ] **Step 4: active file と Skill root を解決する**

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

root から cwd までの各 directory で active file を 1 件だけ選ぶ。`suggest_instruction_target` の production implementation は learning の evidence path を受け取り、path-specific evidence がある場合だけその directory を `cwd` として渡す。一般的な project learning は repository root を渡す。

- [ ] **Step 5: fork 元の routing を Codex targets に変換する**

- global behavior -> active global `AGENTS` file
- project behavior -> repository root `AGENTS.md`
- path-specific -> nearest nested active `AGENTS` file、未作成ならその directory の `AGENTS.md` proposal
- skill correction -> writable authoring source の既存 Skill
- multi-project workflow -> user Skill root
- low confidence -> queue のまま

Plugin cache、system、admin-managed Skill は write target に返さず `read_only=True` の suggestion とする。

- [ ] **Step 6: Claude memory hierarchy tests を Codex routing tests に置換する**

`tests/test_memory_hierarchy.py` は `TestAgentsHierarchy`、`TestSkillRouting`、`TestReadOnlyPluginSkill` へ置き換え、`.claude/rules`、`CLAUDE.local.md`、auto memory assertions を削除する。

- [ ] **Step 7: tests を通す**

Run:

```bash
python3 -m unittest tests.test_target_resolver tests.test_memory_hierarchy -v
python3 -m unittest discover -s tests -v
```

Expected: all passing。

- [ ] **Step 8: commit**

```bash
git add plugins/codex-reflect/scripts/lib tests
git commit -m "feat: route learnings to Codex guidance targets"
```

## Task 7: Codex history adapter と redaction

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

- [ ] **Step 1: sanitized Codex transcript fixtures を追加する**

`rollout-v1.jsonl` は実データを含めず、現在確認済みの record shape を再現する。

```jsonl
{"type":"session_meta","payload":{"id":"session-1","cwd":"/repo","timestamp":"2026-07-18T00:00:00Z"}}
{"type":"event_msg","payload":{"type":"user_message","message":"no, use rg instead of grep","images":[],"local_images":[],"text_elements":[]}}
{"type":"response_item","payload":{"type":"custom_tool_call_output","name":"exec_command","output":"Process exited with code 1: TOKEN=secret-value"}}
```

`unknown-rollout.jsonl`:

```jsonl
{"type":"future_record","payload":{"body":"no, use another parser"}}
```

- [ ] **Step 2: history normalization の failing tests を書く**

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

- [ ] **Step 3: secret redaction の failing tests を書く**

```python
def test_redacts_assignment_and_bearer_token(self):
    value = redact_secrets("API_KEY=abc123 Authorization: Bearer token-value")
    self.assertNotIn("abc123", value)
    self.assertNotIn("token-value", value)
    self.assertEqual(value.count("[REDACTED]"), 2)
```

- [ ] **Step 4: failing tests を確認する**

Run:

```bash
python3 -m unittest tests.test_codex_history -v
```

Expected: modules が存在せず FAIL。

- [ ] **Step 5: normalized history model と schema detection を実装する**

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

同じ message が `event_msg` と `response_item` の両方に現れる場合は、出現順を維持して exact text duplicate を 1 件にする。`sessions/**/*.jsonl` と `archived_sessions/**/*.jsonl` を列挙し、SQLite や UI cache は読まない。

- [ ] **Step 6: local redaction を実装する**

`redaction.py` は assignment、Bearer、JWT、OpenAI／GitHub style token を対象に、値だけを `[REDACTED]` へ置換する。入力を log に出さない。

- [ ] **Step 7: 3 extraction scripts を adapter 経由へ変更する**

- `extract_session_learnings.py`: `TranscriptResult.user_messages`
- `extract_tool_errors.py`: `TranscriptResult.tool_outputs` から existing error pattern を適用
- `extract_tool_rejections.py`: known user rejection text がある record だけを利用

`reflect_utils.extract_user_messages`、`extract_tool_errors`、`extract_tool_rejections` は adapter wrapper にして、既存 detection／aggregation API を維持する。

- [ ] **Step 8: focused tests と full suite を通す**

Run:

```bash
python3 -m unittest tests.test_codex_history tests.test_reflect_utils tests.test_tool_errors -v
python3 -m unittest discover -s tests -v
```

Expected: all passing。

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

- [ ] **Step 1: Codex command contract の failing tests を書く**

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

既存 `test_claude_*` 名を `test_codex_*` に変更し、`claude -p` command assertions を Codex flags へ置換する。

- [ ] **Step 2: tests が旧 Claude command のため fail することを確認する**

Run:

```bash
python3 -m unittest tests.test_semantic_detector -v
```

Expected: command[0] が `claude` のため FAIL。

- [ ] **Step 3: 3 JSON Schemas を追加する**

learning schema の required fields:

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

tool error schema は `is_learnable`、`refined_guideline`、`confidence`、`reasoning`、contradiction schema は `contradictions[]` の `entry1`、`entry2`、`conflict` を同様に required とする。

- [ ] **Step 4: Codex subprocess runner を実装する**

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

model 未指定時は Codex の current default を使い、特定の model slug を hardcode しない。既存 `_validate_response`、queue fallback、tool error、contradiction validation は維持し、prompt 内の `CLAUDE.md` 表記を `AGENTS.md`／Skill guidance に変更する。

- [ ] **Step 5: tests と schema parse を通す**

Run:

```bash
python3 -m unittest tests.test_semantic_detector -v
python3 -m json.tool plugins/codex-reflect/schemas/learning-analysis.schema.json
python3 -m json.tool plugins/codex-reflect/schemas/tool-error-analysis.schema.json
python3 -m json.tool plugins/codex-reflect/schemas/contradictions.schema.json
python3 -m unittest discover -s tests -v
```

Expected: all passing。

- [ ] **Step 6: live semantic smoke test を承認付きで実行する**

Codex quota を消費するためユーザー承認後に実行する。

Run:

```bash
python3 -c "import sys; sys.path.insert(0, 'plugins/codex-reflect/scripts'); from lib.semantic_detector import semantic_analyze; print(semantic_analyze('remember: run focused tests'))"
```

Expected: `is_learning=True`、`type='explicit'` を含む dict。新しい Codex session file は増えない。

- [ ] **Step 7: commit**

```bash
git add plugins/codex-reflect/schemas plugins/codex-reflect/scripts/lib/semantic_detector.py tests/test_semantic_detector.py
git commit -m "feat: validate learnings with Codex exec"
```

## Task 9: `view-queue` と `skip-reflect` Skills

**Files:**
- Modify: `plugins/codex-reflect/scripts/read_queue.py`
- Create: `plugins/codex-reflect/scripts/clear_queue.py`
- Modify: `plugins/codex-reflect/skills/view-queue/SKILL.md`
- Modify: `plugins/codex-reflect/skills/skip-reflect/SKILL.md`
- Create: `tests/test_queue_commands.py`

- [ ] **Step 1: queue command の failing tests を書く**

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

- [ ] **Step 2: failing tests を確認する**

Run:

```bash
python3 -m unittest tests.test_queue_commands -v
```

Expected: formatted output／clear command が未実装で FAIL。

- [ ] **Step 3: deterministic queue commands を実装する**

`read_queue.py` は `--json` なら raw JSON、それ以外は fork 元の `[0.85] "message" (pattern) - relative time` を表示する。`clear_queue.py` は `--confirm` がなければ exit 2、あれば removed items を stdout JSON に出して clear する。

- [ ] **Step 4: 2 Skills を最終 workflow へ置換する**

`view-queue/SKILL.md`:

```markdown
---
name: view-queue
description: View codex-reflect learning candidates for the current project without changing them.
---

Resolve `../../scripts/read_queue.py` relative to this SKILL.md and run it with the current working directory unchanged. Return its formatted output verbatim. Do not modify queue or target files.
```

`skip-reflect/SKILL.md` は `read_queue.py --json` で一覧を取得し、件数と message preview を提示して確認する。承認後だけ `clear_queue.py --confirm` を実行し、取消時は何も実行しない。

- [ ] **Step 5: tests を通す**

Run:

```bash
python3 -m unittest tests.test_queue_commands tests.test_codex_plugin_contract -v
python3 -m unittest discover -s tests -v
```

Expected: all passing。

- [ ] **Step 6: commit**

```bash
git add plugins/codex-reflect/scripts plugins/codex-reflect/skills tests
git commit -m "feat: add Codex queue management skills"
```

## Task 10: `reflect` preparation command と Skill workflow

**Files:**
- Create: `plugins/codex-reflect/scripts/commands/__init__.py`
- Create: `plugins/codex-reflect/scripts/commands/reflect.py`
- Modify: `plugins/codex-reflect/skills/reflect/SKILL.md`
- Create: `tests/test_reflect_command.py`

- [ ] **Step 1: argument contract と no-write の failing tests を書く**

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

- [ ] **Step 2: failing tests を確認する**

Run:

```bash
python3 -m unittest tests.test_reflect_command -v
```

Expected: `commands.reflect` が未定義で FAIL。

- [ ] **Step 3: parse_args と preparation pipeline を実装する**

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

`prepare_reflection` は queue、history adapter、semantic adapter、TargetResolver を順に呼び、次の shape の JSON-serializable dict を返す。値は example であり、key と value type を contract とする。

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

候補の semantic failure は item に `semantic_status="unavailable"` を付け、削除しない。explicit item は必ず candidates に残す。`--targets` は target list だけ、`--review` は stale を含む queue、`--dedupe`／`--organize` は該当 analysis を追加する。command 自身は `AGENTS.md`／Skills を編集しない。capability summary は Task 12 でこの response に追加する。

- [ ] **Step 4: `reflect` Skill に human review gate を記述する**

Skill は preparation command の JSON を読み、次を順番に行う。

1. 初回 history scan の scope／provider 送信内容を説明し承認を得る。
2. candidate summary を表示する。
3. apply all／select／details／skip を選ばせる。
4. target routing を候補ごとに確認する。
5. exact file diff を作る。
6. final confirmation を得る。
7. confirmation 後だけ edit tool で `AGENTS.md`／writable Skill を変更する。
8. target が review 中に変わっていたら中止して diff を再生成する。
9. applied items だけ queue から削除する。

`--dry-run` は step 3 以降の質問と書き込みを行わず proposal を表示して終了する。read-only Plugin／system Skill は改善案だけを表示する。Codex Memories は読まない・書かない。

- [ ] **Step 5: Skill contract test と focused tests を通す**

`tests/test_codex_plugin_contract.py` に、`reflect/SKILL.md` が 9 workflow keywords（`dry-run`、`scan-history`、`apply all`、`select`、`details`、`skip`、`final confirmation`、`AGENTS.md`、`queue`）を含む test を追加する。

Run:

```bash
python3 -m unittest tests.test_reflect_command tests.test_codex_plugin_contract -v
python3 -m unittest discover -s tests -v
```

Expected: all passing。

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

- [ ] **Step 1: discovery input の failing tests を書く**

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

- [ ] **Step 2: failing tests を確認する**

Run:

```bash
python3 -m unittest tests.test_reflect_skills_command -v
```

Expected: module が存在せず FAIL。

- [ ] **Step 3: deterministic discovery input collector を実装する**

`parse_args` は `--days` default 14、`--project`、`--all-projects`、`--dry-run` を持つ。collector は supported transcripts の user messages、cwd、timestamp、既存 Skill metadata を JSON で返す。

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

test fixture の `context.now` と transcript timestamp は timezone-aware UTC に統一する。pattern clustering と Skill 内容生成は Skill を実行している Codex が行い、hardcoded keyword cluster は作らない。

- [ ] **Step 4: `reflect-skills` Skill を最終 workflow へ置換する**

Skill は collector JSON から次を行う。

1. multi-step intent／workflow を semantic に比較する。
2. 同じ intent が複数回ある候補だけを提示する。
3. existing Skill と同義なら improvement として分類する。
4. name、description、evidence count、source projects を表示する。
5. 生成候補と配置先を確認する。
6. repository scope は `$REPO_ROOT/.agents/skills/<name>/SKILL.md`、cross-project は `$HOME/.agents/skills/<name>/SKILL.md` を提案する。
7. final confirmation 後だけ valid frontmatter を持つ Skill を生成する。
8. `--dry-run` は file を生成しない。

Plugin cache、system、admin-managed Skill は直接編集しない。

- [ ] **Step 5: tests を通す**

Run:

```bash
python3 -m unittest tests.test_reflect_skills_command tests.test_codex_plugin_contract -v
python3 -m unittest discover -s tests -v
```

Expected: all passing。

- [ ] **Step 6: commit**

```bash
git add plugins/codex-reflect/scripts/commands/reflect_skills.py plugins/codex-reflect/skills/reflect-skills tests
git commit -m "feat: discover reusable skills from Codex history"
```

## Task 12: CapabilityProbe と graceful degradation

**Files:**
- Create: `plugins/codex-reflect/scripts/lib/capabilities.py`
- Create: `tests/test_capabilities.py`
- Modify: `plugins/codex-reflect/scripts/session_start_reminder.py`
- Modify: `plugins/codex-reflect/scripts/commands/reflect.py`

- [ ] **Step 1: capability tests を書く**

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

- [ ] **Step 2: failing tests を確認する**

Run:

```bash
python3 -m unittest tests.test_capabilities -v
```

Expected: module が存在せず FAIL。

- [ ] **Step 3: dependency-free CapabilityProbe を実装する**

Python 3.8 でも動くよう `tomllib` に依存せず、`config.toml` の `[history] persistence = "none"` だけを狭い line parser で読む。その他は `codex --version`、session directories、state directory writeability を検査する。

```python
@dataclass
class Capabilities:
    codex_version: Optional[str]
    history_available: bool
    semantic_available: bool
    realtime_queue_available: bool
    warnings: List[str]
```

Hook trust は internal config を推測せず、queue が未作成の場合に `/hooks` を確認する diagnostic message として扱う。

- [ ] **Step 4: SessionStart と reflect summary に capability を表示する**

history unavailable、unknown transcript、semantic unavailable を別々に表示する。core queue が使える場合は全体 failure と表現しない。unsupported feature から別ログ、SQLite、legacy Skill install へ fallback しない。

- [ ] **Step 5: tests を通す**

Run:

```bash
python3 -m unittest tests.test_capabilities tests.test_integration tests.test_reflect_command -v
python3 -m unittest discover -s tests -v
```

Expected: all passing。

- [ ] **Step 6: commit**

```bash
git add plugins/codex-reflect/scripts tests
git commit -m "feat: report Codex capability gaps safely"
```

## Task 13: Claude runtime artifacts を除去し、Codex docs／CI を完成する

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

- [ ] **Step 1: Codex-only documentation contract の failing tests を追加する**

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

- [ ] **Step 2: contract が旧 artifacts で fail することを確認する**

Run:

```bash
python3 -m unittest tests.test_codex_plugin_contract -v
```

Expected: `.claude-plugin`／`commands`／root `SKILL.md` が存在して FAIL。

- [ ] **Step 3: Claude-only runtime artifacts を削除する**

Run:

```bash
git rm -r .claude-plugin commands plugins/codex-reflect/scripts/legacy
git rm SKILL.md
git mv CLAUDE.md AGENTS.md
```

`AGENTS.md` は Codex Plugin layout、test command、Phase 0／E2E command、MIT attribution を説明する contributor guide に書き換える。Claude Hook schema、`.claude` paths、Claude commands は残さない。

- [ ] **Step 4: README と distribution docs を Codex 専用へ書き換える**

README は次を必須 section とする。

1. `codex-reflect` の目的
2. `claude-reflect` fork と MIT attribution
3. marketplace install
4. Hook trust 手順
5. 4 fork-named Skills と引数
6. realtime capture と human review
7. `$CODEX_HOME/codex-reflect` state
8. semantic subprocess の provider 送信範囲
9. transcript schema、hosted tool、Memories の capability gaps
10. macOS／Linux／Windows support

`DISTRIBUTION.md` は Codex marketplace 配布、`RELEASING.md` は manifest version、package tests、Codex E2E、tag 手順へ置換する。`CHANGELOG.md` の過去履歴は保持し、先頭へ `4.0.0-rc.1` の Codex-only breaking change を追加する。

- [ ] **Step 5: CI path と contract checks を更新する**

`.github/workflows/test.yml` の Hook smoke path を次へ変更する。

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

CI matrix は既存の `ubuntu-latest`、`macos-latest`、`windows-latest` と Python 3.8／3.11 を維持する。

- [ ] **Step 6: Claude runtime dependency scan と full tests を実行する**

Run:

```bash
rg -n "CLAUDE_PLUGIN_ROOT|CLAUDE_PLUGIN_DATA|~/.claude|claude -p|\.claude-plugin|/reflect-skills|/view-queue|/skip-reflect" plugins AGENTS.md
python3 -m unittest discover -s tests -v
git diff --check
```

Expected: `rg` は no matches で exit 1。attribution／migration explanation を含む docs と、旧 artifact が消えたことを assert する tests はこの runtime scan の対象外とする。tests は all passing、`git diff --check` exit 0。

- [ ] **Step 7: commit**

```bash
git add -A
git commit -m "docs: complete Codex-only plugin migration"
```

## Task 14: Release gate と local E2E

**Files:**
- Modify only if verification reveals a defect: files owned by Tasks 2〜13
- Update test count only after final run: `README.md`

- [ ] **Step 1: fresh automated verification を実行する**

Run:

```bash
python3 -m unittest discover -s tests -v
python3 -m pytest tests/ -v
python3 -m json.tool .agents/plugins/marketplace.json
python3 -m json.tool plugins/codex-reflect/.codex-plugin/plugin.json
python3 -m json.tool plugins/codex-reflect/hooks/hooks.json
git diff --check
```

Expected: すべて exit 0。test count をこの実行結果から README badge に反映する。

- [ ] **Step 2: Plugin install／Hook trust の承認を得る**

local user state を変更するため、次の command 実行前にユーザーへ承認を求める。Phase 0 で install した probe bundle を最新実装へ確実に置換するため、一度 remove してから同じ marketplace から再 install する。

```bash
codex plugin remove codex-reflect@codex-reflect-marketplace
codex plugin add codex-reflect@codex-reflect-marketplace
codex plugin list
```

Expected: Plugin が installed, enabled。新しい session で `/hooks` に 4 Hook groups が表示される。未 trust なら UI から exact Hook definitions を review／trust する。

- [ ] **Step 3: realtime capture E2E を実行する**

新しい temporary Git repository で Codex を開始し、次を送る。

```text
remember: always run focused tests before the full suite
```

Expected: capture notification が表示され、`$codex-reflect:view-queue` に explicit candidate が 1 件表示される。

- [ ] **Step 4: dry-run と apply gate E2E を実行する**

Run in Codex:

```text
$codex-reflect:reflect --dry-run
```

Expected: proposal は表示されるが queue と `AGENTS.md` は変化しない。

続けて `$codex-reflect:reflect` を実行し、final confirmation 前に cancel して no-write を確認する。その後再実行して approve し、`AGENTS.md` に選択した learning だけが追加されることを確認する。

- [ ] **Step 5: history と Skill discovery E2E を実行する**

`$codex-reflect:reflect --scan-history --days 14` が supported／unsupported session count を表示することを確認する。次に `$codex-reflect:reflect-skills --dry-run --days 14` を実行し、file を生成せず候補または「反復なし」を根拠付きで返すことを確認する。

- [ ] **Step 6: uninstall preservation を確認する**

ユーザー承認後に Plugin を remove し、生成済み `AGENTS.md` と user／repo Skills が残ることを確認する。

```bash
codex plugin remove codex-reflect@codex-reflect-marketplace
```

- [ ] **Step 7: final status と commit range を確認する**

Run:

```bash
git status --short --branch
git log --oneline --decorate --max-count=15
```

Expected: intended commits だけがあり、worktree clean。E2E で defect を修正した場合は focused regression test を追加してから、その component の commit message で追加 commit する。

## Spec coverage checklist

| Spec requirement | Plan task |
|---|---|
| Codex Plugin／4 fork-named Skills | Tasks 2, 9, 10, 11 |
| realtime capture／lifecycle | Tasks 4, 5 |
| `$CODEX_HOME/codex-reflect` state | Task 3 |
| `AGENTS.md`／Skills routing | Task 6 |
| active／archived history | Task 7 |
| `codex exec` semantic validation | Task 8 |
| human review／final confirmation | Tasks 9, 10, 11 |
| tool errors／rejections | Task 7, Task 10 |
| capability gaps／no large workaround | Tasks 2, 12, 14 |
| privacy／redaction | Tasks 7, 8, 13 |
| macOS／Linux／Windows | Tasks 3, 13, 14 |
| MIT attribution／Codex-only docs | Task 13 |
| release gates／E2E | Task 14 |
