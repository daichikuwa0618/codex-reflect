---
name: skip-reflect
description: Use when all codex-reflect learning candidates for the current project should be discarded after explicit confirmation.
---

Resolve `../../scripts/read_queue.py` and `../../scripts/clear_queue.py` relative to this SKILL.md.

1. Run `read_queue.py --json` with the current working directory unchanged.
2. Present the candidate count and a short preview of each `message`.
3. Ask for explicit confirmation to discard the entire current-project queue.
4. Only after confirmation, run `clear_queue.py --confirm` with the current working directory unchanged and report the removed count.

If the user cancels or does not confirm, do not run `clear_queue.py` and do not modify any file. Backups and applied AGENTS.md or Skills are never changed.
