# Release process

## 1. Version

次を同じ version に更新します。

- `plugins/codex-reflect/.codex-plugin/plugin.json`
- `README.md` の version badge
- `CHANGELOG.md` の先頭 release section

repository marketplace は nested manifest を参照するため、別の plugin version を持ちません。

## 2. Automated verification

```bash
python -m unittest discover -s tests -v
python -m pytest tests/ -v
python -m json.tool .agents/plugins/marketplace.json
python -m json.tool plugins/codex-reflect/.codex-plugin/plugin.json
python -m json.tool plugins/codex-reflect/hooks/hooks.json
git diff --check
```

README に test count を表示する場合は、この fresh run の値だけを反映します。CI の macOS / Linux / Windows、Python 3.8 / 3.11 matrix が成功していることを確認します。

## 3. Codex E2E

local user state と model quota を使用するため、事前承認を得ます。

1. marketplace snapshot を追加または更新する。
2. Plugin を remove / add し、`codex plugin list` で installed / enabled を確認する。
3. `/hooks` で 4 Hook groups の exact definitions を trust する。
4. temporary Git repository で `remember:` の realtime capture を確認する。
5. `view-queue`、`reflect --dry-run`、cancel-before-confirmation、approved apply を確認する。
6. active / archived history scan と `reflect-skills --dry-run` を確認する。
7. Plugin を remove し、承認済み `AGENTS.md` と Skills が保持されることを確認する。

Desktop app 自身の UI 自動操作や、存在しない IDE surface の代替検証は release gate に見せかけません。実行できない surface は capability gap として記録します。

## 4. Runtime dependency scan

```bash
rg -n "CLAUDE_PLUGIN_ROOT|CLAUDE_PLUGIN_DATA|~/\.claude|claude -p|\.claude-plugin|/reflect-skills|/view-queue|/skip-reflect" plugins AGENTS.md
```

Expected: no matches、exit 1。fork attribution と migration history を含む docs / CHANGELOG は対象外です。

## 5. Commit, tag, publish

```bash
git status --short --branch
git log --oneline --decorate --max-count=15
git tag vX.Y.Z
git push origin main
git push origin vX.Y.Z
```

tag 作成と push は repository を外部変更するため、利用者の明示依頼がある場合だけ実行します。release note には verified Codex version、test matrix、manual E2E 結果、未解決 capability gap を記載します。
