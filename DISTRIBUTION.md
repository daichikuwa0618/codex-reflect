# Codex marketplace distribution

codex-reflect は repository marketplace と、その配下の Codex Plugin bundle として配布します。

## 配布構造

```text
.agents/plugins/marketplace.json
plugins/codex-reflect/
  .codex-plugin/plugin.json
  hooks/hooks.json
  skills/*/SKILL.md
  scripts/
  schemas/
```

marketplace の plugin source は repository 内の `./plugins/codex-reflect` を指します。manifest version と release tag は一致させます。

## Local marketplace 検証

次の操作は local Codex user state を変更するため、実行前に利用者の承認が必要です。

```bash
codex plugin marketplace add .
codex plugin add codex-reflect@codex-reflect-marketplace
codex plugin list
```

インストール後は新しい task で次を確認します。

1. fork 元準拠の 4 Skills が namespace 付きで表示される。
2. `/hooks` に `UserPromptSubmit`、`PreCompact`、`PostToolUse`、`SessionStart` が表示される。
3. exact Hook definitions を review / trust した後だけ realtime capture が始まる。
4. Hook と Skill が同じ `$CODEX_HOME/codex-reflect` state を参照する。

## Git marketplace

公開 repository から追加する例:

```bash
codex plugin marketplace add daichikuwa0618/codex-reflect --ref main
codex plugin add codex-reflect@codex-reflect-marketplace
```

release tag を固定する場合は `--ref vX.Y.Z` を使用します。公開前に tag が manifest version と同じ commit を指すことを確認してください。

## Package validation

```bash
python -m unittest discover -s tests -v
python -m pytest tests/ -v
python -m json.tool .agents/plugins/marketplace.json
python -m json.tool plugins/codex-reflect/.codex-plugin/plugin.json
python -m json.tool plugins/codex-reflect/hooks/hooks.json
git diff --check
```

CI は `ubuntu-latest`、`macos-latest`、`windows-latest` と Python 3.8 / 3.11 の matrix を通します。model を使う semantic smoke は通常 CI に含めず、release 前に quota 利用の承認を得て 1 回だけ行います。

## Distribution requirements

- [LICENSE](LICENSE) の upstream copyright notice と MIT License 本文を保持する。
- README に fork 元、provider 送信範囲、Hook trust、transcript schema、Codex Memories、hosted tool の制限を記載する。
- Plugin cache、system Skill、admin-managed Skill を書き換えない。
- 旧 runtime bundle や legacy Skill を同梱しない。
- install / uninstall E2E で、承認済み `AGENTS.md` と Skills が uninstall 後も残ることを確認する。

配布先ごとの未確認な reach、互換性、公式 endorsement は記載しません。release 時点の stable Codex で実測した capability だけを support statement に使用します。
