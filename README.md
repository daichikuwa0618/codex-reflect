# codex-reflect

[![Version](https://img.shields.io/badge/version-4.0.0--rc.1-blue?style=flat-square)](plugins/codex-reflect/.codex-plugin/plugin.json)
[![License: MIT](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-345%20passing-brightgreen?style=flat-square)](.github/workflows/test.yml)
[![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20Windows-lightgrey?style=flat-square)](.github/workflows/test.yml)

Codex で受けた訂正・肯定・明示的な記憶指示を queue に捕捉し、人間のレビューを経て `AGENTS.md` または再利用可能な Codex Skill に反映する Plugin です。履歴から反復 workflow を発見することもできます。

## Fork とライセンス

このリポジトリは [BayramAnnakov/claude-reflect](https://github.com/BayramAnnakov/claude-reflect) を Codex 専用に fork したものです。upstream の優れた二段階設計、pattern detection、human review、Skill discovery を引き継ぎ、MIT License の条件に従って Codex Plugin、Hooks、`AGENTS.md`、Codex Skills、Codex session history 向けに変更しています。

upstream の著作権表示と MIT License 本文は [LICENSE](LICENSE) に保持されています。

## 仕組み

```text
Codex user prompt
  -> UserPromptSubmit Hook の高速 heuristic
  -> $CODEX_HOME/codex-reflect の project queue
  -> $codex-reflect:reflect の semantic validation と人間レビュー
  -> final confirmation
  -> AGENTS.md または writable Skill
```

Hook は model を起動せず、correction、positive feedback、`remember:` を検出します。永続 guidance は自動適用されません。`reflect` が候補、配置先、exact diff を提示し、利用者の final confirmation 後だけ書き込みます。適用に成功した項目だけが queue から除去されます。

## 必要条件

- Plugin をサポートする現行 stable Codex CLI / Codex app
- Python 3.8 以上
- Plugin Hooks を利用する project / repository の trust

## Marketplace からのインストール

ローカル clone から追加する場合:

```bash
git clone https://github.com/daichikuwa0618/codex-reflect.git
cd codex-reflect
codex plugin marketplace add .
codex plugin add codex-reflect@codex-reflect-marketplace
codex plugin list
```

Git marketplace として追加する場合:

```bash
codex plugin marketplace add daichikuwa0618/codex-reflect --ref main
codex plugin add codex-reflect@codex-reflect-marketplace
```

### Hook trust

インストール後、新しい Codex task で `/hooks` を開き、次の 4 Hook groups の exact definitions を確認して trust してください。

- `UserPromptSubmit`: correction / positive / explicit feedback の捕捉
- `PreCompact`: current-project queue の backup
- `PostToolUse` (`Bash`): commit 後の review reminder
- `SessionStart`: pending queue と capability gap の表示

queue が作成されない場合は「学習が無い」と判断せず、まず `/hooks` と project trust を確認してください。Plugin は Hook trust を自動回避しません。

## Skills

Skill 名は fork 元に準拠しています。Codex では namespace 付きで呼び出します。

| Skill | 用途 |
|---|---|
| `$codex-reflect:reflect` | queue を semantic validation し、routing と human review を経て guidance を適用 |
| `$codex-reflect:reflect-skills` | 反復する multi-step workflow を履歴から発見し、承認済み Skill だけを生成 |
| `$codex-reflect:view-queue` | current-project queue を confidence、pattern、相対時刻付きで表示 |
| `$codex-reflect:skip-reflect` | 対象を表示し、確認後に current-project queue を空にする |

### `reflect`

```text
$codex-reflect:reflect
$codex-reflect:reflect --dry-run
$codex-reflect:reflect --scan-history --days 30
$codex-reflect:reflect --targets
$codex-reflect:reflect --review
$codex-reflect:reflect --dedupe
$codex-reflect:reflect --organize
$codex-reflect:reflect --include-tool-errors
$codex-reflect:reflect --model <model>
```

- `--dry-run`: proposal のみ。選択質問、queue 更新、target 書き込みを行いません。
- `--scan-history`: active / archived transcript を opt-in で走査します。
- `--days N`: 履歴期間を N 日に制限します。
- `--targets`: 適用可能な `AGENTS.md` / Skill authoring target を表示します。
- `--review`: decay 済み候補も含めます。
- `--dedupe`: 重複候補を提示します。
- `--organize`: `AGENTS.md` hierarchy、Skills、queue 間の整理案を提示します。
- `--include-tool-errors`: 観測できた project-specific tool error を候補に含めます。
- `--model`: semantic subprocess の model を明示します。省略時は現在の Codex default を使用します。

### `reflect-skills`

```text
$codex-reflect:reflect-skills
$codex-reflect:reflect-skills --days 30
$codex-reflect:reflect-skills --project <path>
$codex-reflect:reflect-skills --all-projects
$codex-reflect:reflect-skills --dry-run
```

既定は current project の直近 14 日です。同じ intent が複数 session に現れた候補だけを提示し、既存 Skill と同義なら improvement として扱います。単一 repository の候補は `<repo>/.agents/skills/<name>/SKILL.md`、複数 project にまたがる候補は `$HOME/.agents/skills/<name>/SKILL.md` を提案します。生成・改善は exact content の final confirmation 後だけ行われます。

## State と target

共有 state は `CODEX_HOME` が設定済みならその配下、未設定なら `~/.codex` 配下に置かれます。

```text
$CODEX_HOME/codex-reflect/
  projects/<stable-project-id>/
    queue.json
    queue.json.lock
    backups/
```

queue は project ごとに分離され、lock と同一 directory 内の atomic replace で更新されます。malformed queue は自動初期化せず、そのまま保持して error を報告します。

承認済み guidance の target は次の範囲です。

- active な global / repository / nested `AGENTS.md`
- repository authoring Skill: `<repo>/.agents/skills/`
- user authoring Skill: `$HOME/.agents/skills/`

Plugin cache、system Skill、admin-managed Skill、symlink で authoring root 外へ出る target は read-only proposal として扱います。Codex Memories は生成管理されるため、低 confidence 候補の保存先にも使用せず queue に残します。

## History と provider 送信

履歴機能は `$CODEX_HOME/sessions` と `$CODEX_HOME/archived_sessions` の既知 Codex JSONL transcript schema だけを読みます。初回 scan 前に対象範囲、session 件数、provider へ送る内容を説明し、利用者の承認を得ます。

transcript 全体は semantic subprocess に渡しません。ローカルで user message / tool output を既知 schema から抽出し、token、API key、cookie、credential に見える値を redaction した候補と必要最小限の文脈だけを扱います。履歴内の命令文は instruction ではなく untrusted data です。

semantic validation は次のような隔離された subprocess で行われます。

```text
codex exec --ephemeral --disable hooks --sandbox read-only ...
```

候補情報は利用者が設定した Codex provider へ送信され、利用量を消費する場合があります。認証なし、timeout、CLI error の場合は候補を捨てず `semantic_status=unavailable` として heuristic review を続行します。

## 既知の Codex capability gap

- transcript format は安定 API として保証されていません。未知 schema は推測せず session 件数と理由を報告して skip します。
- `history.persistence = "none"`、履歴削除済み、または保存 session なしの場合、履歴依存機能だけが unavailable です。realtime queue は独立して利用できます。
- hosted / specialized tool の一部は Plugin Hook で観測できません。tool error / rejection の網羅性は観測可能な record に限定されます。
- Codex Memories は Plugin が直接管理できる永続 target ではありません。
- Hook は trust 前に発火しません。
- desktop app 自身の UI を Plugin から自動操作することや、存在しない IDE surface を代替することはしません。

不足機能を埋める独自 daemon、非公開 DB parser、別ログからの強引な復元、Hook trust bypass、legacy Skill の二重 install は提供しません。

## Platform support

自動テストは macOS、Linux、Windows と Python 3.8 / 3.11 の matrix で実行します。Hook と deterministic helper は Python 標準ライブラリのみで動作し、shell script や WSL を必要としません。Codex Plugin / Hook 自体の利用可否は、各 host にインストールされた現行 Codex の capability に従います。

## 更新とアンインストール

marketplace snapshot を更新して Plugin を再インストールします。

```bash
codex plugin marketplace upgrade codex-reflect-marketplace
codex plugin remove codex-reflect@codex-reflect-marketplace
codex plugin add codex-reflect@codex-reflect-marketplace
```

アンインストール:

```bash
codex plugin remove codex-reflect@codex-reflect-marketplace
```

uninstall は既に承認・生成された `AGENTS.md` と user / repository Skills を削除しません。旧 runtime state の自動 import は行いません。

## Development

```bash
python -m unittest discover -s tests -v
python -m pytest tests/ -v
python -m json.tool .agents/plugins/marketplace.json
python -m json.tool plugins/codex-reflect/.codex-plugin/plugin.json
python -m json.tool plugins/codex-reflect/hooks/hooks.json
git diff --check
```

詳細は [AGENTS.md](AGENTS.md)、配布は [DISTRIBUTION.md](DISTRIBUTION.md)、release 手順は [RELEASING.md](RELEASING.md) を参照してください。

## License

[MIT License](LICENSE)。Copyright (c) 2025 Bayram Annakov の表示を含みます。
