# codex-reflect Codex 専用化 要件・設計

- Status: ユーザー承認済み
- Date: 2026-07-18
- Base: `BayramAnnakov/claude-reflect` `main` (`8dc9db43c9bfaa53b567d63f3f48385bcf3d3084`)
- License: MIT

## 1. 背景

`claude-reflect` は、ユーザーからの訂正・肯定・明示的な記憶指示を自動捕捉し、人間のレビューを経て永続的なガイダンスへ反映する。また、過去セッションから反復ワークフローを発見して再利用可能な Skill を生成する。

本プロジェクトは、この成果を維持しながら Claude Code 固有の Plugin、Hooks、履歴、command、memory hierarchy を Codex の公式 surface に置き換える。Claude Code との runtime 互換や既存データ移行は行わず、Codex 専用 OSS Plugin とする。

## 2. 設計原則

1. fork 元と同じユーザー成果を、Codex-native な操作で提供する。
2. fork 元の実績ある detection、confidence、decay、dedup、human review、テスト資産を再利用する。
3. Claude／Codex 固有部分を adapter に隔離する。
4. 自動捕捉と永続ガイダンスへの昇格を分離する。
5. `AGENTS.md` または Skills を変更する前に、変更案と最終確認を提示する。
6. Codex に自然な対応機能がない場合は、制約と利用可能な代替を明記する。大規模で壊れやすい workaround は作らない。
7. Codex の内部 DB、非公開 schema、生成管理される Memories を書き換えない。
8. transcript、Hook、semantic analysis の失敗で queue の候補を失わない。

## 3. 目的

`codex-reflect` を導入した利用者が、次の feedback loop を Codex CLI、ChatGPT desktop app のローカル Codex、Codex IDE extension で利用できることを目的とする。

```text
ユーザーの feedback
  -> 自動捕捉
  -> project queue
  -> 意味解析と scope 判定
  -> 人間によるレビュー・編集
  -> 最終確認
  -> AGENTS.md または Skill
```

## 4. 対象と非対象

### 4.1 対象

- Codex CLI
- ChatGPT desktop app 上のローカル Codex
- Codex IDE extension
- 同一 Codex host の `CODEX_HOME`、Plugins、Hooks、Skills、session transcripts
- macOS、Linux、Windows
- 個人および repository 単位のガイダンス
- 一般公開する MIT License の OSS Plugin

### 4.2 非対象

- Codex cloud task
- ChatGPT web Work mode
- Claude Code runtime との併用モード
- `~/.claude` からの既存 queue、memory、command の移行
- `~/.codex/memories` の直接編集
- Codex 内部 SQLite DB の直接参照・変更
- transcript format を安定 API に見せかける互換 daemon
- Hook trust や sandbox を自動回避する仕組み

## 5. 操作体系

Skill 名は fork 元に準拠する。

| fork 元 | Codex Plugin |
|---|---|
| `/reflect` | `$codex-reflect:reflect` |
| `/reflect-skills` | `$codex-reflect:reflect-skills` |
| `/view-queue` | `$codex-reflect:view-queue` |
| `/skip-reflect` | `$codex-reflect:skip-reflect` |

### 5.1 `reflect`

次の引数と成果を維持する。

- `--dry-run`: queue、`AGENTS.md`、Skills を変更せず、ユーザーへの確認も行わずに変更案を表示する。
- `--scan-history`: 保存済み session から候補を抽出する。
- `--days N`: 履歴対象を直近 N 日へ制限する。
- `--targets`: 現在適用可能な `AGENTS.md` と Skills の候補を表示する。
- `--review`: stale／decayed を含めて queue を表示する。
- `--dedupe`: 類似するガイダンスを提示し、統合案を作る。
- `--organize`: `AGENTS.md` hierarchy、Skills、queue 間の整理案を提示する。
- `--include-tool-errors`: project 固有の tool error を候補へ含める。`--scan-history` では有効とする。
- `--model MODEL`: semantic analysis 用 Codex model を上書きする。

初回の `reflect` は全履歴スキャンを提案する。自動開始せず、対象となる active／archived session の件数と、semantic analysis へ送られる情報を説明して承認を得る。利用者は `--days N` で範囲を制限できる。

### 5.2 `reflect-skills`

- `--days N`: 直近 N 日を解析する。既定は fork 元と同じ 14 日。
- `--project <path>`: 指定 project の session を解析する。
- `--all-projects`: 複数 project を横断する。
- `--dry-run`: Skill を生成せず候補だけを表示する。

既定では current project のみを対象とする。候補名、説明、根拠となる反復回数、想定配置先を提示し、利用者が承認した Skill だけを生成する。

### 5.3 `view-queue`

current project の queue を confidence、pattern、相対時刻、source とともに表示する。書き込みは行わない。

### 5.4 `skip-reflect`

破棄対象を一覧表示し、確認後に current project の queue を空にする。backup と既に適用済みの `AGENTS.md`／Skills は変更しない。

## 6. 機能要件

### FR-01: リアルタイム捕捉

`UserPromptSubmit` Hook で次を検出する。

- correction
- positive feedback
- 明示的な記憶指示
- CJK を含む複数言語の既存 pattern

Hook は高速な heuristic 判定だけを行い、model を起動しない。system content、tool result、session continuation、極端に長い prompt など、fork 元で除外している入力を引き続き除外する。

### FR-02: project-scoped queue

候補は current repository root を基準に project ごとに分離する。repository 外では正規化した current working directory を project identity とする。

### FR-03: lifecycle 通知

- `SessionStart`: 未処理件数と初回履歴スキャンを案内する。
- `PreCompact`: queue の backup を作成する。
- `PostToolUse`: `git commit` を観測できた場合、未処理候補を案内する。

Hook trust、project trust、event coverage の不足で発火しない場合は、診断手順を提示する。

### FR-04: semantic validation

fork 元の `claude -p` subprocess に相当する処理として `codex exec` を使用する。

- ephemeral session とする。
- reflect 自身の Hooks を無効にし、再帰を防ぐ。
- read-only sandbox とする。
- final response を JSON Schema で制約する。
- model override を許可する。
- timeout、認証失敗、schema error では heuristic 結果へ fallback する。
- 明示的な記憶指示を semantic 判定だけで破棄しない。

### FR-05: human review

学習候補ごとに次を表示する。

- original message
- 整形後の actionable learning
- source
- confidence
- suggested target
- duplicate／contradiction
- stale／decay 状態

利用者は apply all、選択適用、詳細レビュー、skip を選べる。Skill 関連候補は既存 Skill、`AGENTS.md`、両方、skip から routing を選べる。

### FR-06: 最終確認

`AGENTS.md` または Skills を変更する直前に、対象ファイルと追加・更新・置換内容を表示する。利用者が最終確認した変更だけを適用する。

queue、backup、schema migration、初期化情報など Plugin 内部状態の自動保存には、この最終確認を要求しない。

### FR-07: target routing

Codex が実際に読む instruction chain を対象とする。

- Global: `$CODEX_HOME/AGENTS.override.md` が存在すればそれを active file とし、なければ `$CODEX_HOME/AGENTS.md`
- Repository: repository root から current working directory までの applicable な `AGENTS.override.md` または `AGENTS.md`
- Nested: path-specific な学習に最も近い applicable directory の active file
- Existing Skill: correction が特定 Skill の実行に関連する場合
- New Skill: 複数 session にまたがる反復 workflow の場合

`AGENTS.override.md` を自動新規作成して既存 `AGENTS.md` を mask しない。存在しない instruction file を新規作成する場合は、target と filename を最終確認に含める。

### FR-08: duplicate／contradiction

applicable な `AGENTS.md` chain と対象 Skills を検索し、同義・重複・矛盾の候補を提示する。自動削除や自動上書きは行わない。

### FR-09: tool error／rejection

安定した Hook payload または対応済み transcript schema から取得できる範囲で、tool error と利用者による rejection を候補化する。利用者へ raw candidate を示し、model が再利用不可と判断しただけで不可視にしない。

### FR-10: Skill 発見・改善

複数 session の intent と workflow を semantic analysis で比較し、反復 pattern を提案する。既存 Skill と同義の場合は新規作成せず、改善候補として提示する。

生成先は repository scope の `$REPO_ROOT/.agents/skills/<name>/SKILL.md` または user scope の `$HOME/.agents/skills/<name>/SKILL.md` とする。根拠が単一 project に閉じていれば repository scope、複数 project に共通すれば user scope を提案し、利用者が配置先を確定する。

既存 Skill の authoring source が書き込み可能な user／repository Skill なら改善 diff を提示できる。Plugin cache、system Skill、admin-managed Skill など、書き換えるべきでない配布物の場合は直接編集せず、改善案だけを表示する。

## 7. Codex 固有の対応関係

| Claude Code 側 | Codex 側 | 方針 |
|---|---|---|
| `.claude-plugin/plugin.json` | `.codex-plugin/plugin.json` | Codex manifest へ置換 |
| Claude command | Plugin-bundled Skill | fork 元の名前を維持 |
| `CLAUDE.md` | `AGENTS.md`／`AGENTS.override.md` | active instruction chain に routing |
| `.claude/rules/*.md` | nested `AGENTS.md` または既存 Skill | Codex の自然な scope へ変換 |
| `CLAUDE.local.md` | 既存の applicable `AGENTS.override.md` | override を勝手に新規作成しない |
| Claude auto memory | 対応なし | Codex Memories を直接編集しない |
| `claude -p` | `codex exec` | ephemeral、Hooks off、read-only |
| `~/.claude/projects` | `$CODEX_HOME/codex-reflect` | Hook と Skill が共有できる安定 path |
| Claude session JSONL | Codex history adapter | 既知 schema のみ best-effort 対応 |

low-confidence learning は Codex Memories へ書かず、review 済みになるまで queue に残す。`--organize` は `AGENTS.md`、Skills、queue の間だけで整理案を作る。

## 8. アーキテクチャ

```text
Codex Hooks / Plugin Skills
        |
        v
Workflow orchestration
        |
        v
Platform-independent core
        |
        v
Codex adapters / state / targets
```

### 8.1 想定 Plugin 構成

```text
.codex-plugin/
  plugin.json
hooks/
  hooks.json
skills/
  reflect/SKILL.md
  reflect-skills/SKILL.md
  view-queue/SKILL.md
  skip-reflect/SKILL.md
scripts/
  hooks/
  commands/
  core/
  adapters/
schemas/
tests/
```

構成名は実装計画で file 単位に確定するが、Hook、workflow、core、adapter の責務境界は維持する。

### 8.2 Integration 層

Codex manifest、Hooks、Skills を所有する。Hooks は捕捉、backup、通知だけを担当する。Skills はユーザー対話と workflow の進行を担当する。

### 8.3 Workflow 層

`reflect`、`reflect-skills`、`view-queue`、`skip-reflect` の処理順序を所有する。JSONL 解析、path 解決、queue 更新などの決定的処理は scripts へ委譲し、`SKILL.md` を巨大な shell snippet 集にしない。

### 8.4 Core 層

次の platform-independent logic を所有する。

- pattern detection
- confidence／decay
- candidate／learning model
- semantic response validation
- duplicate／contradiction model
- tool error aggregation
- target suggestion
- secret redaction

Core 層は `.claude`、`.codex`、Claude session、Codex transcript の path や schema を知らない。

### 8.5 Adapter 層

- `HookInputAdapter`: Codex Hook JSON を normalized event へ変換する。
- `HistoryAdapter`: active／archived transcript の既知 schema を normalized event へ変換する。
- `SemanticAdapter`: 安全な設定で `codex exec` を実行する。
- `StateStore`: `$CODEX_HOME/codex-reflect` の queue、backup、state を扱う。
- `TargetResolver`: applicable な `AGENTS.md` と Skills を解決する。
- `CapabilityProbe`: Codex version、Hooks、履歴、権限、Skill discovery を診断する。

## 9. 状態管理

### 9.1 保存場所

共有状態は `$CODEX_HOME/codex-reflect` に置く。`CODEX_HOME` が未設定の場合は `~/.codex/codex-reflect` とする。

```text
$CODEX_HOME/codex-reflect/
  state.json
  projects/
    <project-id>/
      queue.json
      backups/
```

`$PLUGIN_DATA` は Plugin Hook 固有の一時データに限り、Hook と Skill の共有 SSOT にはしない。公式に `$PLUGIN_DATA` が Plugin Skill の通常 shell command へ渡される保証がないためである。

### 9.2 Queue item

queue item は最低限、次の情報を持つ。

```text
schema_version
id
type
original_message
captured_at
project_root
session_id
turn_id
patterns
confidence
sentiment
decay_days
skill_context
source
```

### 9.3 Project identity

Git repository 内では正規化した repository root、repository 外では正規化した working directory を使用する。Windows の drive letter と case、separator、symlink を正規化し、安定した project ID を生成する。

### 9.4 書き込み整合性

- queue 更新は file lock と atomic replace を使用する。
- backup は queue の現行 schema version を保持する。
- JSON が破損している場合は上書きせず、診断と recovery candidate を表示する。
- 永続 target の適用直前に対象を再読込する。
- review 開始後に target が変化していた場合は書き込まず、diff を再生成する。
- partial apply が発生した場合、未適用候補は queue に残す。

## 10. データフロー

### 10.1 リアルタイム捕捉

```text
UserPromptSubmit
  -> Hook input normalization
  -> system/tool content filtering
  -> heuristic detection
  -> project queue
  -> short notification when captured
```

### 10.2 Reflect

```text
queue load
  -> optional history scan
  -> local extraction and redaction
  -> semantic validation
  -> duplicate/contradiction/scope analysis
  -> proposal
  -> user selection
  -> final diff
  -> final confirmation
  -> AGENTS.md / Skill apply
  -> queue update
```

### 10.3 Skill 発見

```text
normalized session events
  -> repeated intent/workflow analysis
  -> existing Skill comparison
  -> candidate list with evidence
  -> user selection and placement confirmation
  -> Skill generation
  -> structure validation
```

## 11. 履歴互換

### 11.1 読み取り対象

- `$CODEX_HOME/sessions`
- `$CODEX_HOME/archived_sessions`
- Hook payload の `transcript_path`

### 11.2 Schema policy

Codex 公式ドキュメントは transcript format を安定 interface として保証していない。`HistoryAdapter` は既知 schema を明示的に判定し、normalized user message、tool result、session metadata へ変換する。

- 対応 schema: 解析する。
- 未対応 schema: session を読み飛ばし、件数と理由を表示する。
- `history.persistence = "none"`: 履歴機能を unavailable と表示する。
- 履歴が削除済み: リアルタイム queue だけで動作する。

別のログ、SQLite DB、UI cache から強引に復元しない。

## 12. Privacy と Security

1. 初回履歴スキャンは opt-in とする。
2. 承認前に session 件数、対象範囲、model 送信内容を説明する。
3. transcript 全体を一括送信せず、ローカル抽出・redaction 後の候補と必要最小限の文脈だけを semantic subprocess へ渡す。
4. `codex exec` はローカル subprocess だが、通常は候補情報を利用者が設定した Codex provider へ送信する。この点を README と初回案内に明記する。
5. semantic subprocess に file write と tool use を許可しない。
6. transcript 内の命令文を system instruction ではなく解析対象データとして扱う。
7. token、API key、cookie、credential に見える値を送信前に redaction する。
8. Hook trust と project trust を自動回避しない。
9. global `AGENTS.md` など sandbox 外 target への書き込みは Codex の通常 approval を使用する。
10. uninstall で既に承認・生成された `AGENTS.md` と Skills を削除しない。

## 13. Codex capability gap policy

| Gap | 影響 | 方針 |
|---|---|---|
| transcript schema が非安定 | 履歴 scan、tool analysis、Skill 発見 | 既知 schema のみ解析し、未知 schema を報告 |
| 一部 hosted／specialized tool は Hook 非対応 | tool error／rejection の網羅性 | 観測可能な範囲だけを対応として明記 |
| Plugin Hooks は trust が必要 | 自動捕捉が開始しない場合がある | `/hooks` を含む onboarding を提示 |
| Codex Memories は生成管理 | low-confidence auto memory と同じ保存先がない | queue に保持し、Memories を編集しない |
| `$PLUGIN_DATA` は Skill 共有が非保証 | Hook と Skill の queue 共有 | `$CODEX_HOME/codex-reflect` を使用 |
| local marketplace Plugin Skill discovery の未解決報告 | local Plugin 開発・検証 | Phase 0 で現行 stable を検証し、再現時は release blocker |

不足 capability を補う独自 daemon、内部 DB parser、Hook trust bypass、Skill の二重 install は採用しない。

## 14. Error handling

- semantic timeout／CLI error: heuristic 結果を保持して続行する。
- Codex 認証なし: semantic validation unavailable と表示し、heuristic review を行う。
- transcript schema 未対応: 該当 session を skip し、集計を表示する。
- history 無効／欠落: history-dependent feature のみ unavailable とする。
- Hook 未 trust: queue が空であることを「学習なし」と誤認せず、Hook status の確認を案内する。
- global target の権限拒否: 書き込まず、queue と提案を保持する。
- target concurrent change: 適用を中止して再 review する。
- malformed queue: 自動初期化せず recovery information を表示する。
- `skip-reflect` の取消: queue を変更しない。

## 15. 検証戦略

### 15.1 Phase 0 capability spike

本実装前に最小 Plugin で次を確認する。

1. Plugin manifest が読み込まれる。
2. fork 元準拠の 4 Skills が表示・実行できる。
3. Plugin Hooks が trust 後に発火する。
4. `UserPromptSubmit` から prompt、cwd、session ID を取得できる。
5. Hook と Skill の両方から `$CODEX_HOME/codex-reflect` を参照できる。
6. `codex exec --ephemeral --disable hooks` が再帰せず終了する。
7. CLI、desktop、IDE が同一 host state を参照する。

成立しない項目は、機能削除、明示的な制限、release blocker のいずれかに分類する。大規模 workaround には移行しない。

### 15.2 自動テスト

- 既存 detection、CJK、confidence、decay test
- Hook input／output contract test
- active／archived history adapter fixture test
- unknown transcript schema の safe skip test
- queue atomic write、lock、corruption test
- `AGENTS.md` scope routing test
- `AGENTS.override.md` precedence test
- Skill 新規生成／既存 Skill 改善 test
- dry-run の no-write test
- final confirmation 前の target no-write test
- semantic subprocess failure の fallback test
- secret redaction test
- Windows path、CJK path、UTF-8 test
- Plugin manifest、Hook config、Skill metadata の contract test

通常 CI は model を呼ばず、semantic response を fixture 化する。GitHub Actions は macOS、Linux、Windows の matrix とする。

### 15.3 手動 E2E

1. Plugin install
2. Hook trust
3. correction の自動捕捉
4. `$codex-reflect:view-queue`
5. `$codex-reflect:reflect --dry-run`
6. 最終確認後の `AGENTS.md` 更新
7. active／archived 履歴 scan
8. `$codex-reflect:reflect-skills`
9. 生成 Skill の再認識
10. uninstall 後に承認済み target が保持されること

## 16. 対応 version と release

固定の古い version range を推測せず、capability probe を優先する。release 時点の stable Codex を正式対応とし、必要な Hook、Plugin Skill、履歴がない環境では不足機能を表示する。

### Release gate

- Phase 0 capability spike に未解決 blocker がない。
- fork 元との outcome parity matrix が完了している。
- 3 OS の CI が成功している。
- local E2E が成功している。
- Claude runtime 依存が残っていない。
- Hook trust、履歴送信範囲、既知の capability gap が README に記載されている。
- MIT License 原文と Bayram Annakov 氏の著作権表示が保持されている。
- fork 元への attribution と主な変更点が README に記載されている。

## 17. License と attribution

MIT License に従い、既存 `LICENSE` の次の表示を保持する。

```text
Copyright (c) 2025 Bayram Annakov
```

派生部分の著作権表示を追加する場合も、既存表示と MIT License 本文を削除しない。README には `claude-reflect` の fork であること、upstream URL、Codex 専用化したことを明記する。

## 18. Acceptance criteria

1. 利用者の訂正が Hook により project queue へ自動捕捉される。
2. `reflect` が semantic validation、routing、review、final confirmation を経て `AGENTS.md` または Skill を更新する。
3. 最終確認前に `AGENTS.md` と Skills は変更されない。
4. `reflect-skills` が反復 workflow を根拠付きで提案し、承認された Skill だけを生成する。
5. `view-queue` と `skip-reflect` が fork 元と同じ成果を提供する。
6. history-dependent feature は対応 schema で動作し、未対応 schema で安全に停止する。
7. semantic subprocess の失敗で候補が失われない。
8. macOS、Linux、Windows で platform-independent test suite が通る。
9. capability gap が隠されず、利用者へ具体的に表示される。
10. Codex にない機能を再現するための大規模 workaround が含まれない。

## 19. 参照

- [Codex Hooks](https://learn.chatgpt.com/docs/hooks)
- [Build Codex plugins](https://learn.chatgpt.com/docs/build-plugins)
- [Build Codex skills](https://learn.chatgpt.com/docs/build-skills)
- [Custom instructions with AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md)
- [Codex Memories](https://learn.chatgpt.com/docs/customization/memories)
- [Codex advanced configuration](https://learn.chatgpt.com/docs/config-file/config-advanced)
- [openai/codex issue #22078](https://github.com/openai/codex/issues/22078)
