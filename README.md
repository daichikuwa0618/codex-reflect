# codex-reflect

[![Version](https://img.shields.io/badge/version-4.0.0--rc.1-blue?style=flat-square)](plugins/codex-reflect/.codex-plugin/plugin.json)
[![License: MIT](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-346%20passing-brightgreen?style=flat-square)](.github/workflows/test.yml)
[![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20Windows-lightgrey?style=flat-square)](.github/workflows/test.yml)

A Codex Plugin that captures corrections, positive feedback, and explicit memory instructions in a queue, then applies them to `AGENTS.md` or reusable Codex Skills after human review. It can also discover repeated workflows in session history.

## Fork and license

This repository is a Codex-only fork of [BayramAnnakov/claude-reflect](https://github.com/BayramAnnakov/claude-reflect). It preserves the upstream two-stage design, pattern detection, human review, and Skill discovery while adapting the project to Codex Plugins, Hooks, `AGENTS.md`, Codex Skills, and Codex session history under the terms of the MIT License.

The upstream copyright notice and full MIT License are preserved in [LICENSE](LICENSE).

## How it works

```text
Codex user prompt
  -> fast heuristic in the UserPromptSubmit Hook
  -> project queue under $CODEX_HOME/codex-reflect
  -> semantic validation and human review in $codex-reflect:reflect
  -> final confirmation
  -> AGENTS.md or a writable Skill
```

The Hook detects corrections, positive feedback, and `remember:` without starting a model. Persistent guidance is never applied automatically. `reflect` presents the candidate, destination, and exact diff, then writes only after the user gives final confirmation. Only successfully applied items are removed from the queue.

## Requirements

- A current stable Codex CLI or Codex app with Plugin support
- Python 3.8 or later
- Trust for Plugin Hooks in every project or repository where they are used

## Install from the marketplace

To add a local clone:

```bash
git clone https://github.com/daichikuwa0618/codex-reflect.git
cd codex-reflect
codex plugin marketplace add .
codex plugin add codex-reflect@codex-reflect-marketplace
codex plugin list
```

To add the Git marketplace directly:

```bash
codex plugin marketplace add daichikuwa0618/codex-reflect --ref main
codex plugin add codex-reflect@codex-reflect-marketplace
```

### Hook trust

After installation, open `/hooks` in a new Codex task. Review the exact definitions of these four Hook groups and trust them:

- `UserPromptSubmit`: captures corrections, positive feedback, and explicit feedback
- `PreCompact`: backs up the current-project queue
- `PostToolUse` (`Bash`): reminds you to review after a commit
- `SessionStart`: reports pending queue items and capability gaps

If no queue is created, check `/hooks` and project trust before concluding that there was nothing to learn. The Plugin does not bypass Hook trust.

## Skills

Skill names follow the upstream project. Invoke them with their Codex namespace:

| Skill | Purpose |
|---|---|
| `$codex-reflect:reflect` | Semantically validate the queue, route candidates, run human review, and apply approved guidance |
| `$codex-reflect:reflect-skills` | Discover repeated multi-step workflows in history and generate only approved Skills |
| `$codex-reflect:view-queue` | Show the current-project queue with confidence, pattern, and relative time |
| `$codex-reflect:skip-reflect` | Show the items to discard, then clear the current-project queue after confirmation |

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

- `--dry-run`: show the proposal without selection prompts, queue updates, or target writes.
- `--scan-history`: scan active and archived transcripts on an opt-in basis.
- `--days N`: restrict the history window to the latest N days.
- `--targets`: show eligible `AGENTS.md` and Skill authoring targets.
- `--review`: include decayed candidates.
- `--dedupe`: present duplicate candidates.
- `--organize`: propose organization across the `AGENTS.md` hierarchy, Skills, and queue.
- `--include-tool-errors`: include observable project-specific tool errors as candidates.
- `--model`: select the model for the semantic subprocess. When omitted, Codex uses its current default.

### `reflect-skills`

```text
$codex-reflect:reflect-skills
$codex-reflect:reflect-skills --days 30
$codex-reflect:reflect-skills --project <path>
$codex-reflect:reflect-skills --all-projects
$codex-reflect:reflect-skills --dry-run
```

By default, this command scans the latest 14 days in the current project. It presents only candidates whose intent appears in multiple sessions and treats a semantic match with an existing Skill as an improvement. Single-repository candidates are proposed under `<repo>/.agents/skills/<name>/SKILL.md`; cross-project candidates are proposed under `$HOME/.agents/skills/<name>/SKILL.md`. A Skill is created or improved only after final confirmation of its exact content.

## State and targets

Shared state lives under `CODEX_HOME` when set, otherwise under `~/.codex`:

```text
$CODEX_HOME/codex-reflect/
  projects/<stable-project-id>/
    queue.json
    queue.json.lock
    backups/
```

Queues are isolated by project. Updates use a lock and an atomic replacement in the same directory. A malformed queue is preserved rather than reinitialized, and the error is reported.

Approved guidance may target:

- the active global, repository, or nested `AGENTS.md`
- a repository-authored Skill under `<repo>/.agents/skills/`
- a user-authored Skill under `$HOME/.agents/skills/`

Plugin caches, system Skills, admin-managed Skills, and symlinks that escape an authoring root are read-only proposal targets. Codex Memories are generated and managed by Codex, so they are never used as storage for low-confidence candidates; those candidates remain in the queue.

## History and provider data transfer

History features read only known Codex JSONL transcript schemas under `$CODEX_HOME/sessions` and `$CODEX_HOME/archived_sessions`. Before the first scan, the Plugin explains the scope, session count, and data that semantic analysis will send to the provider, then waits for approval.

The full transcript is never passed to the semantic subprocess. The Plugin locally extracts user messages and tool output from known schemas, redacts values that look like tokens, API keys, cookies, or credentials, and sends only candidates with the minimum required context. Instructions found inside history are treated as untrusted data, not as instructions.

Semantic validation runs in an isolated subprocess similar to:

```text
codex exec --ephemeral --disable hooks --sandbox read-only ...
```

Candidate data is sent to the Codex provider configured by the user and may consume usage quota. If authentication is unavailable, a timeout occurs, or the CLI fails, the Plugin keeps the candidate with `semantic_status=unavailable` and continues with heuristic review.

## Known Codex capability gaps

- Transcript formats are not guaranteed to be stable APIs. Unknown schemas are not guessed; the Plugin reports the session count and skip reason.
- When `history.persistence = "none"`, history has been deleted, or no saved sessions exist, only history-dependent features are unavailable. The real-time queue remains available.
- Some hosted or specialized tools are not observable through Plugin Hooks. Tool error and rejection coverage is limited to observable records.
- Codex Memories are not persistent targets that this Plugin can manage directly.
- Hooks do not run until they are trusted.
- The Plugin does not automate the desktop app itself or emulate unavailable IDE surfaces.

The project intentionally does not provide a custom daemon, private database parser, forced recovery from unrelated logs, Hook trust bypass, or duplicate legacy Skill installation to work around these gaps.

## Platform support

Automated tests run on macOS, Linux, and Windows with Python 3.8 and 3.11. Hooks and deterministic helpers use only the Python standard library and do not require shell scripts or WSL. Actual Plugin and Hook availability follows the capabilities of the current Codex installation on each host.

## Update and uninstall

Upgrade the marketplace snapshot and reinstall the Plugin:

```bash
codex plugin marketplace upgrade codex-reflect-marketplace
codex plugin remove codex-reflect@codex-reflect-marketplace
codex plugin add codex-reflect@codex-reflect-marketplace
```

Uninstall:

```bash
codex plugin remove codex-reflect@codex-reflect-marketplace
```

Uninstalling does not delete previously approved or generated `AGENTS.md` files or user/repository Skills. Legacy runtime state is not imported automatically.

## Development

```bash
python -m unittest discover -s tests -v
python -m pytest tests/ -v
python -m json.tool .agents/plugins/marketplace.json
python -m json.tool plugins/codex-reflect/.codex-plugin/plugin.json
python -m json.tool plugins/codex-reflect/hooks/hooks.json
git diff --check
```

See [AGENTS.md](AGENTS.md) for contributor guidance, [DISTRIBUTION.md](DISTRIBUTION.md) for distribution, and [RELEASING.md](RELEASING.md) for the release process.

## License

[MIT License](LICENSE), including the Copyright (c) 2025 Bayram Annakov notice.
