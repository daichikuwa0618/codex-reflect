# Codex marketplace distribution

codex-reflect is distributed as a repository marketplace containing a Codex Plugin bundle.

## Package layout

```text
.agents/plugins/marketplace.json
plugins/codex-reflect/
  .codex-plugin/plugin.json
  hooks/hooks.json
  skills/*/SKILL.md
  scripts/
  schemas/
```

The marketplace Plugin source points to `./plugins/codex-reflect` inside the repository. The manifest version and release tag must match.

## Local marketplace verification

The following commands modify local Codex user state and require user approval before execution:

```bash
codex plugin marketplace add .
codex plugin add codex-reflect@codex-reflect-marketplace
codex plugin list
```

After installation, verify the following in a new task:

1. The four upstream-named Skills appear with their namespace.
2. `/hooks` shows `UserPromptSubmit`, `PreCompact`, `PostToolUse`, and `SessionStart`.
3. Real-time capture starts only after the exact Hook definitions are reviewed and trusted.
4. Hooks and Skills use the same `$CODEX_HOME/codex-reflect` state.

## Git marketplace

Example for adding the public repository:

```bash
codex plugin marketplace add daichikuwa0618/codex-reflect --ref main
codex plugin add codex-reflect@codex-reflect-marketplace
```

Use `--ref vX.Y.Z` to pin a release tag. Before publishing, verify that the tag and manifest version refer to the same commit.

## Package validation

```bash
python -m unittest discover -s tests -v
python -m pytest tests/ -v
python -m json.tool .agents/plugins/marketplace.json
python -m json.tool plugins/codex-reflect/.codex-plugin/plugin.json
python -m json.tool plugins/codex-reflect/hooks/hooks.json
git diff --check
```

CI runs a matrix of `ubuntu-latest`, `macos-latest`, and `windows-latest` with Python 3.8 and 3.11. The normal CI suite does not call a model. Run one semantic smoke test before release only after obtaining approval to use quota.

## Distribution requirements

- Preserve the upstream copyright notice and full MIT License in [LICENSE](LICENSE).
- Document upstream attribution, provider data transfer, Hook trust, transcript schema limitations, Codex Memories, and hosted-tool limitations in the README.
- Never modify Plugin caches, system Skills, or admin-managed Skills.
- Do not include legacy runtime bundles or legacy Skills.
- Verify through install/uninstall E2E that approved `AGENTS.md` files and Skills remain after uninstall.

Do not claim unverified reach, compatibility, or official endorsement for any distribution channel. Support statements must reflect capabilities measured on the stable Codex release used for the release.
