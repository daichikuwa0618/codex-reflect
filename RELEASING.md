# Release process

## 1. Version

Update these locations to the same version:

- `plugins/codex-reflect/.codex-plugin/plugin.json`
- the version badge in `README.md`
- the first release section in `CHANGELOG.md`

The repository marketplace references the nested manifest and does not carry a separate Plugin version.

## 2. Automated verification

```bash
python -m unittest discover -s tests -v
python -m pytest tests/ -v
python -m json.tool .agents/plugins/marketplace.json
python -m json.tool plugins/codex-reflect/.codex-plugin/plugin.json
python -m json.tool plugins/codex-reflect/hooks/hooks.json
git diff --check
```

If the README displays a test count, update it only from this fresh run. Confirm that the macOS, Linux, and Windows CI matrix passes on Python 3.8 and 3.11.

## 3. Codex E2E

Obtain approval first because these checks use local user state and model quota.

1. Add or update the marketplace snapshot.
2. Remove and add the Plugin, then confirm `installed, enabled` with `codex plugin list`.
3. Review and trust the exact definitions of all four Hook groups in `/hooks`.
4. Confirm real-time capture of `remember:` in a temporary Git repository.
5. Verify `view-queue`, `reflect --dry-run`, cancellation before confirmation, and approved application.
6. Verify active and archived history scanning and `reflect-skills --dry-run`.
7. Remove the Plugin and confirm that approved `AGENTS.md` files and Skills remain.

Do not present desktop app self-automation or emulation of unavailable IDE surfaces as release gates. Record unavailable surfaces as capability gaps.

## 4. Runtime dependency scan

```bash
rg -n "CLAUDE_PLUGIN_ROOT|CLAUDE_PLUGIN_DATA|~/\.claude|claude -p|\.claude-plugin|/reflect-skills|/view-queue|/skip-reflect" plugins AGENTS.md
```

Expected: no matches and exit code 1. Documentation and CHANGELOG entries that contain attribution or migration history are outside this scan.

## 5. Commit, tag, and publish

```bash
git status --short --branch
git log --oneline --decorate --max-count=15
git tag vX.Y.Z
git push origin main
git push origin vX.Y.Z
```

Creating a tag and pushing change external repository state, so perform them only when the user explicitly requests it. Release notes must state the verified Codex version, test matrix, manual E2E results, and unresolved capability gaps.
