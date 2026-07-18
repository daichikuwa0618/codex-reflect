# codex-reflect contributor guide

## Project

codex-reflect は、Codex の訂正・肯定・明示的な記憶指示を Hook で捕捉し、人間のレビュー後に `AGENTS.md` または Codex Skill へ反映する Codex Plugin です。

本リポジトリは [BayramAnnakov/claude-reflect](https://github.com/BayramAnnakov/claude-reflect) の MIT License fork です。既存の `LICENSE` と upstream の著作権表示を保持してください。

## Layout

- `.agents/plugins/marketplace.json`: repository marketplace
- `plugins/codex-reflect/.codex-plugin/plugin.json`: Plugin manifest
- `plugins/codex-reflect/hooks/hooks.json`: Codex Hook definitions
- `plugins/codex-reflect/skills/*/SKILL.md`: fork 元準拠の 4 Skills
- `plugins/codex-reflect/scripts/`: Hook、queue、history、semantic、command 実装
- `plugins/codex-reflect/schemas/`: `codex exec` structured output schemas
- `tests/`: unit、integration、package contract tests

Runtime は Codex 専用です。旧 runtime manifest、旧 command bundle、旧 state path、旧 CLI 呼び出しを再導入しないでください。Codex Memories は生成管理されるため、この Plugin から読み書きしません。

## Development

Python 3.8 互換の標準ライブラリ実装を維持し、機能修正は failing test から始めます。自動テストでは model を呼ばず、semantic response と subprocess を mock してください。

```bash
python -m unittest discover -s tests -v
python -m pytest tests/ -v
python -m json.tool .agents/plugins/marketplace.json
python -m json.tool plugins/codex-reflect/.codex-plugin/plugin.json
python -m json.tool plugins/codex-reflect/hooks/hooks.json
git diff --check
```

Hook smoke:

```bash
echo '{"hook_event_name":"SessionStart","cwd":"."}' | python plugins/codex-reflect/scripts/session_start_reminder.py
echo '{"hook_event_name":"PostToolUse","cwd":".","tool_input":{"command":"true"}}' | python plugins/codex-reflect/scripts/post_commit_reminder.py
echo '{"hook_event_name":"UserPromptSubmit","cwd":".","prompt":"test"}' | python plugins/codex-reflect/scripts/capture_learning.py
```

## Safety and verification

- transcript は既知の Codex JSONL schema だけを解析し、未知 schema は skip 理由を報告します。
- history scan は scope と provider 送信範囲を説明し、利用者の承認後だけ開始します。
- `reflect` と `reflect-skills` は exact diff と final confirmation の後だけ永続 target を変更します。
- Plugin install/remove、Hook trust、live semantic smoke は local user state または quota を使うため、実行前に利用者の承認を得ます。
- desktop app 自身の UI 自動操作、存在しない IDE surface、非公開 DB 解析、Hook trust bypass のための workaround は追加しません。

Release 前は package contract、3 OS CI、手動 Codex E2E、uninstall 後の承認済み target 保持を確認します。
