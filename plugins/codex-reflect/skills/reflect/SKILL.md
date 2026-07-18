---
name: reflect
description: Use when captured Codex feedback should be reviewed as persistent AGENTS.md or Skill guidance.
---

Resolve `../../scripts/commands/reflect.py` relative to this SKILL.md and keep the current working directory unchanged.

1. Before `--scan-history`, explain the active and archived session scope, local redaction, and the candidate text sent to the configured Codex provider. Obtain approval before running the history scan.
2. Run the preparation command and present the candidate summary.
3. Ask the user to choose `apply all`, `select`, `details`, or `skip`.
4. Confirm target routing for every selected candidate. A read-only Plugin or system Skill receives an improvement proposal only.
5. Re-read each target and create an exact file diff for `AGENTS.md` or a writable Skill.
6. Show the exact target paths and diff, then obtain `final confirmation`.
7. Only after final confirmation, use edit tools to apply the approved diff.
8. If a target changed during review, stop, re-read it, and regenerate the diff before asking again.
9. Remove only successfully applied items from the current-project `queue`; leave skipped or failed items queued.

For `--dry-run`, display the proposal and stop before choice prompts, confirmation, queue changes, or target writes. `--targets` only reports applicable targets. `--review`, `--dedupe`, `--organize`, `--include-tool-errors`, `--days`, and `--model` are passed through when requested. Never read or write Codex Memories.
