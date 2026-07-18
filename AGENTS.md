# codex-reflect contributor guide

## Project

codex-reflect is a Codex Plugin that captures corrections, positive feedback, and explicit memory instructions through Hooks, then applies them to `AGENTS.md` or a Codex Skill after human review.

This repository is an MIT-licensed fork of [BayramAnnakov/claude-reflect](https://github.com/BayramAnnakov/claude-reflect). Preserve the existing `LICENSE` and upstream copyright notice.

All repository documentation, contributor guidance, and user-facing text must be written in English so the project is ready for public distribution. Non-English literals may remain only when required as multilingual pattern data or test fixtures.

## Layout

- `.agents/plugins/marketplace.json`: repository marketplace
- `plugins/codex-reflect/.codex-plugin/plugin.json`: Plugin manifest
- `plugins/codex-reflect/hooks/hooks.json`: Codex Hook definitions
- `plugins/codex-reflect/skills/*/SKILL.md`: four Skills named after their upstream equivalents
- `plugins/codex-reflect/scripts/`: Hook, queue, history, semantic, and command implementations
- `plugins/codex-reflect/schemas/`: structured output schemas for `codex exec`
- `tests/`: unit, integration, and package contract tests

The runtime is Codex-only. Do not reintroduce legacy runtime manifests, command bundles, state paths, or CLI calls. Codex Memories are generated and managed by Codex, so this Plugin must not read or write them.

## Development

Maintain Python 3.8 compatibility and use only the standard library at runtime. Start functional fixes with a failing test. Automated tests must not call a model; mock semantic responses and subprocesses instead.

```bash
python -m unittest discover -s tests -v
python -m pytest tests/ -v
python -m json.tool .agents/plugins/marketplace.json
python -m json.tool plugins/codex-reflect/.codex-plugin/plugin.json
python -m json.tool plugins/codex-reflect/hooks/hooks.json
git diff --check
```

Hook smoke tests:

```bash
echo '{"hook_event_name":"SessionStart","cwd":"."}' | python plugins/codex-reflect/scripts/session_start_reminder.py
echo '{"hook_event_name":"PostToolUse","cwd":".","tool_input":{"command":"true"}}' | python plugins/codex-reflect/scripts/post_commit_reminder.py
echo '{"hook_event_name":"UserPromptSubmit","cwd":".","prompt":"test"}' | python plugins/codex-reflect/scripts/capture_learning.py
```

## Safety and verification

- Parse only known Codex JSONL transcript schemas and report why unknown schemas were skipped.
- Explain the history scan scope and provider data transfer, then start scanning only after user approval.
- `reflect` and `reflect-skills` may change persistent targets only after showing the exact diff and receiving final confirmation.
- Obtain user approval before Plugin installation or removal, Hook trust changes, or live semantic smoke tests because they use local user state or quota.
- Do not add workarounds that automate the desktop app itself, emulate unavailable IDE surfaces, parse private databases, or bypass Hook trust.

Before release, verify the package contract, the three-OS CI matrix, manual Codex E2E, and preservation of approved targets after uninstall.
