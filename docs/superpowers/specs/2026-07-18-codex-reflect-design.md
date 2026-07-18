# codex-reflect Codex-Only Requirements and Design

- Status: Approved by the user
- Date: 2026-07-18
- Base: `BayramAnnakov/claude-reflect` `main` (`8dc9db43c9bfaa53b567d63f3f48385bcf3d3084`)
- License: MIT

## 1. Background

`claude-reflect` automatically captures corrections, positive feedback, and explicit memory instructions, then promotes them to persistent guidance after human review. It also discovers repeated workflows in past sessions and generates reusable Skills.

This project preserves those outcomes while replacing Claude Code-specific Plugins, Hooks, history, commands, and memory hierarchy with official Codex surfaces. It is a Codex-only open-source Plugin; runtime compatibility with Claude Code and migration of legacy data are out of scope.

## 2. Design principles

1. Produce the same user outcomes as the upstream project through Codex-native operations.
2. Reuse proven upstream detection, confidence, decay, deduplication, human review, and test assets.
3. Isolate Claude-specific and Codex-specific behavior behind adapters.
4. Keep automatic capture separate from promotion to persistent guidance.
5. Present the proposal and obtain final confirmation before changing `AGENTS.md` or Skills.
6. When Codex has no natural equivalent, document the limitation and available alternative instead of building a large, fragile workaround.
7. Do not modify Codex internal databases, private schemas, or generated Codex Memories.
8. Never lose queued candidates because transcript parsing, Hooks, or semantic analysis failed.

## 3. Goal

Users who install `codex-reflect` should be able to use this feedback loop from the Codex CLI, local Codex in the ChatGPT desktop app, and the Codex IDE extension:

```text
user feedback
  -> automatic capture
  -> project queue
  -> semantic analysis and scope classification
  -> human review and editing
  -> final confirmation
  -> AGENTS.md or Skill
```

## 4. Scope

### 4.1 In scope

- Codex CLI
- Local Codex in the ChatGPT desktop app
- Codex IDE extension
- `CODEX_HOME`, Plugins, Hooks, Skills, and session transcripts on the same Codex host
- macOS, Linux, and Windows
- User-level and repository-level guidance
- A publicly distributed MIT-licensed open-source Plugin

### 4.2 Out of scope

- Codex cloud tasks
- ChatGPT web Work mode
- A dual-runtime mode with Claude Code
- Migration of existing queues, memories, or commands from `~/.claude`
- Direct edits to `~/.codex/memories`
- Direct access to or modification of Codex internal SQLite databases
- A compatibility daemon that presents transcript formats as stable APIs
- Automatic bypasses for Hook trust or sandbox controls

## 5. User operations

Skill names follow the upstream project.

| Upstream | Codex Plugin |
|---|---|
| `/reflect` | `$codex-reflect:reflect` |
| `/reflect-skills` | `$codex-reflect:reflect-skills` |
| `/view-queue` | `$codex-reflect:view-queue` |
| `/skip-reflect` | `$codex-reflect:skip-reflect` |

### 5.1 `reflect`

Preserve these arguments and outcomes:

- `--dry-run`: show the proposal without changing the queue, `AGENTS.md`, or Skills and without asking selection questions.
- `--scan-history`: extract candidates from saved sessions.
- `--days N`: restrict history to the latest N days.
- `--targets`: show eligible `AGENTS.md` and Skill targets.
- `--review`: include stale or decayed queue items.
- `--dedupe`: present similar guidance and propose consolidation.
- `--organize`: propose organization across the `AGENTS.md` hierarchy, Skills, and queue.
- `--include-tool-errors`: include project-specific tool errors. This applies to history scans.
- `--model MODEL`: override the Codex model used for semantic analysis.

The first `reflect` run proposes a history scan but never starts it automatically. It reports the number of active and archived sessions in scope and explains what semantic analysis sends to the provider before asking for approval. Users can restrict the range with `--days N`.

### 5.2 `reflect-skills`

- `--days N`: analyze the latest N days; the upstream-compatible default is 14.
- `--project <path>`: analyze sessions for one project.
- `--all-projects`: analyze sessions across projects.
- `--dry-run`: show candidates without generating Skills.

The default scope is the current project. Show the candidate name, description, repetition evidence, and proposed destination, then generate only Skills approved by the user.

### 5.3 `view-queue`

Display the current-project queue with confidence, pattern, relative time, and source. Do not write anything.

### 5.4 `skip-reflect`

List the items that will be discarded, ask for confirmation, and then clear only the current-project queue. Do not modify backups or already-applied `AGENTS.md` files and Skills.

## 6. Functional requirements

### FR-01: Real-time capture

The `UserPromptSubmit` Hook detects:

- corrections
- positive feedback
- explicit memory instructions
- existing multilingual patterns, including CJK

The Hook performs only fast heuristic detection and never starts a model. Continue excluding system content, tool results, session continuations, extremely long prompts, and the other inputs filtered by the upstream project.

### FR-02: Project-scoped queue

Isolate candidates by project using the current repository root. Outside a repository, use the normalized current working directory as the project identity.

### FR-03: Lifecycle notifications

- `SessionStart`: report pending items and suggest the first history scan.
- `PreCompact`: create a queue backup.
- `PostToolUse`: when a `git commit` is observable, remind the user about pending candidates.

If Hook trust, project trust, or incomplete event coverage prevents a Hook from firing, provide diagnostics.

### FR-04: Semantic validation

Use `codex exec` as the Codex equivalent of the upstream semantic subprocess:

- use an ephemeral session;
- disable reflect Hooks to prevent recursion;
- use a read-only sandbox;
- constrain the final response with JSON Schema;
- permit a model override;
- fall back to heuristic results on timeout, authentication failure, or schema errors; and
- never discard an explicit memory instruction solely because of semantic classification.

### FR-05: Human review

For every learning candidate, show:

- the original message
- the normalized actionable learning
- the source
- the confidence score
- the suggested target
- duplicate or contradiction findings
- stale or decay status

Allow the user to apply all, select items, review details, or skip. For Skill-related candidates, let the user route to an existing Skill, `AGENTS.md`, both, or skip.

### FR-06: Final confirmation

Immediately before changing `AGENTS.md` or a Skill, show the target file and the exact addition, update, or replacement. Apply only changes covered by final confirmation.

This final confirmation is not required for internal Plugin state such as queue updates, backups, schema migrations, or initialization metadata.

### FR-07: Target routing

Target the instruction chain Codex actually reads:

- Global: use `$CODEX_HOME/AGENTS.override.md` when it exists; otherwise use `$CODEX_HOME/AGENTS.md`.
- Repository: resolve the applicable `AGENTS.override.md` or `AGENTS.md` files from the repository root to the current working directory.
- Nested: route path-specific learning to the nearest applicable directory.
- Existing Skill: use it when the correction concerns execution of that Skill.
- New Skill: use it for a repeated workflow observed across multiple sessions.

Do not create an `AGENTS.override.md` automatically and mask an existing `AGENTS.md`. When proposing a new instruction file, include the target and filename in final confirmation.

### FR-08: Duplicates and contradictions

Search the applicable `AGENTS.md` chain and target Skills for semantically equivalent, duplicate, or contradictory guidance. Present findings without automatic deletion or overwrite.

### FR-09: Tool errors and rejections

Create candidates from tool errors and user rejections only when they can be read from stable Hook payloads or supported transcript schemas. Show the raw candidate; do not hide it merely because a model classified it as non-reusable.

### FR-10: Skill discovery and improvement

Use semantic analysis to compare intent and workflow across sessions and propose repeated patterns. When a pattern is semantically equivalent to an existing Skill, propose an improvement rather than a new Skill.

Generate repository-scoped Skills under `$REPO_ROOT/.agents/skills/<name>/SKILL.md` and user-scoped Skills under `$HOME/.agents/skills/<name>/SKILL.md`. Recommend repository scope when all evidence belongs to one project and user scope when evidence spans projects; the user confirms the destination.

When the authoring source is a writable user or repository Skill, present an improvement diff. For Plugin cache, system, admin-managed, or other distributed Skills that should not be modified, show only a read-only proposal.

## 7. Codex mappings

| Claude Code surface | Codex surface | Policy |
|---|---|---|
| `.claude-plugin/plugin.json` | `.codex-plugin/plugin.json` | Replace with a Codex manifest |
| Claude command | Plugin-bundled Skill | Preserve upstream names |
| `CLAUDE.md` | `AGENTS.md` or `AGENTS.override.md` | Route into the active instruction chain |
| `.claude/rules/*.md` | nested `AGENTS.md` or an existing Skill | Map to natural Codex scope |
| `CLAUDE.local.md` | an existing applicable `AGENTS.override.md` | Never create an override silently |
| Claude auto memory | no equivalent target | Do not edit Codex Memories |
| `claude -p` | `codex exec` | Ephemeral, Hooks disabled, read-only |
| `~/.claude/projects` | `$CODEX_HOME/codex-reflect` | Stable shared path for Hooks and Skills |
| Claude session JSONL | Codex history adapter | Best-effort support for known schemas only |

Keep low-confidence learning in the queue until review instead of writing it to Codex Memories. `--organize` works only across `AGENTS.md`, Skills, and the queue.

## 8. Architecture

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

### 8.1 Plugin layout

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

The implementation plan determines exact file names, but it must preserve boundaries among Hooks, workflows, core logic, and adapters.

### 8.2 Integration layer

Own the Codex manifest, Hooks, and Skills. Hooks handle capture, backup, and notifications. Skills own user interaction and workflow progression.

### 8.3 Workflow layer

Own the execution order of `reflect`, `reflect-skills`, `view-queue`, and `skip-reflect`. Delegate deterministic JSONL parsing, path resolution, and queue updates to scripts instead of turning `SKILL.md` into a collection of large shell snippets.

### 8.4 Core layer

Own platform-independent logic:

- pattern detection
- confidence and decay
- candidate and learning models
- semantic response validation
- duplicate and contradiction models
- tool error aggregation
- target suggestions
- secret redaction

The core layer must not know `.claude` or `.codex` paths or Claude/Codex transcript schemas.

### 8.5 Adapter layer

- `HookInputAdapter`: normalize Codex Hook JSON.
- `HistoryAdapter`: normalize supported active and archived transcript schemas.
- `SemanticAdapter`: execute `codex exec` with safe settings.
- `StateStore`: manage queues, backups, and state under `$CODEX_HOME/codex-reflect`.
- `TargetResolver`: resolve applicable `AGENTS.md` files and Skills.
- `CapabilityProbe`: diagnose Codex version, Hooks, history, permissions, and Skill discovery.

## 9. State management

### 9.1 Storage location

Store shared state under `$CODEX_HOME/codex-reflect`, or under `~/.codex/codex-reflect` when `CODEX_HOME` is unset.

```text
$CODEX_HOME/codex-reflect/
  state.json
  projects/
    <project-id>/
      queue.json
      backups/
```

Limit `$PLUGIN_DATA` to Hook-specific temporary data. It is not the shared source of truth because Codex does not guarantee that ordinary shell commands run by Plugin Skills receive `$PLUGIN_DATA`.

### 9.2 Queue item

Each queue item contains at least:

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

Inside Git, use the normalized repository root. Outside Git, use the normalized working directory. Normalize Windows drive-letter case, separators, and symlinks to derive a stable project ID.

### 9.4 Write integrity

- Use a file lock and atomic replacement for queue updates.
- Preserve the current queue schema version in backups.
- Do not overwrite malformed JSON; report diagnostics and recovery options.
- Re-read a persistent target immediately before applying a change.
- If a target changed after review started, stop and regenerate the diff.
- If an apply is partial, keep unapplied candidates in the queue.

## 10. Data flow

### 10.1 Real-time capture

```text
UserPromptSubmit
  -> Hook input normalization
  -> system/tool content filtering
  -> heuristic detection
  -> project queue
  -> short capture notification
```

### 10.2 Reflection

```text
queue load
  -> optional history scan
  -> local extraction and redaction
  -> semantic validation
  -> duplicate/contradiction/scope analysis
  -> proposal
  -> user selection
  -> exact diff
  -> final confirmation
  -> AGENTS.md / Skill apply
  -> queue update
```

### 10.3 Skill discovery

```text
normalized session events
  -> repeated intent/workflow analysis
  -> comparison with existing Skills
  -> candidate list with evidence
  -> user selection and destination confirmation
  -> Skill generation
  -> structure validation
```

## 11. History compatibility

### 11.1 Read locations

- `$CODEX_HOME/sessions`
- `$CODEX_HOME/archived_sessions`
- `transcript_path` from a Hook payload

### 11.2 Schema policy

Official Codex documentation does not promise a stable transcript interface. `HistoryAdapter` explicitly detects known schemas and converts them into normalized user messages, tool results, and session metadata.

- Supported schema: parse it.
- Unsupported schema: skip the session and report the count and reason.
- `history.persistence = "none"`: report history features as unavailable.
- Deleted history: operate from the real-time queue only.

Do not force recovery from other logs, SQLite databases, or UI caches.

## 12. Privacy and security

1. Make the first history scan opt-in.
2. Before approval, explain the session count, scope, and data sent to the model.
3. Never send a whole transcript. Locally extract and redact candidates, then send only the minimum required context.
4. `codex exec` is a local subprocess, but it normally sends candidate data to the user-configured Codex provider. State this in the README and first-run disclosure.
5. Do not allow file writes or tool use in the semantic subprocess.
6. Treat instructions inside transcripts as data, never as system instructions.
7. Redact values that resemble tokens, API keys, cookies, or credentials before sending.
8. Never bypass Hook trust or project trust.
9. Use ordinary Codex approval for writes to global `AGENTS.md` or other targets outside the sandbox.
10. Uninstalling must not delete already-approved or generated `AGENTS.md` files and Skills.

## 13. Codex capability-gap policy

| Gap | Impact | Policy |
|---|---|---|
| Transcript schemas are unstable | History scans, tool analysis, Skill discovery | Parse known schemas only and report unknown schemas |
| Some hosted or specialized tools do not emit Plugin Hooks | Completeness of tool error and rejection capture | Claim support only for observable records |
| Plugin Hooks require trust | Automatic capture may not start | Provide onboarding that includes `/hooks` |
| Codex Memories are generated and managed | No equivalent low-confidence auto-memory target | Keep candidates in the queue and do not edit Memories |
| `$PLUGIN_DATA` is not guaranteed to be shared with Skills | Shared queue access from Hooks and Skills | Use `$CODEX_HOME/codex-reflect` |
| Local marketplace Skill discovery has had unresolved reports | Local Plugin development and verification | Verify the current stable release in Phase 0; treat recurrence as a release blocker |

Do not add a custom daemon, internal database parser, Hook trust bypass, or duplicate Skill installation to fill these gaps.

## 14. Error handling

- Semantic timeout or CLI error: keep heuristic results and continue.
- Missing Codex authentication: report semantic validation as unavailable and continue heuristic review.
- Unsupported transcript schema: skip that session and show a summary.
- Disabled or missing history: disable only history-dependent features.
- Untrusted Hooks: do not misreport an empty queue as no learning; direct the user to Hook status.
- Permission denied for a global target: do not write; preserve the queue and proposal.
- Concurrent target change: stop and repeat review.
- Malformed queue: do not reinitialize automatically; show recovery information.
- Cancelled `skip-reflect`: do not modify the queue.

## 15. Verification strategy

### 15.1 Phase 0 capability spike

Before full implementation, use a minimal Plugin to verify:

1. Codex loads the Plugin manifest.
2. All four upstream-named Skills are visible and executable.
3. Plugin Hooks run after trust.
4. `UserPromptSubmit` exposes prompt, working directory, and session ID.
5. Hooks and Skills can both access `$CODEX_HOME/codex-reflect`.
6. `codex exec --ephemeral --disable hooks` exits without recursion.
7. CLI, desktop, and IDE use the same host state.

Classify every failed item as a removed feature, an explicit limitation, or a release blocker. Do not move to a large workaround.

### 15.2 Automated tests

- existing detection, CJK, confidence, and decay tests
- Hook input/output contract tests
- active and archived history adapter fixture tests
- safe skip tests for unknown transcript schemas
- queue atomic-write, locking, and corruption tests
- `AGENTS.md` scope-routing tests
- `AGENTS.override.md` precedence tests
- new-Skill and existing-Skill improvement tests
- no-write tests for dry-run
- no-write tests before final confirmation
- semantic subprocess failure fallback tests
- secret redaction tests
- Windows path, CJK path, and UTF-8 tests
- Plugin manifest, Hook configuration, and Skill metadata contract tests

Normal CI must not call a model; use semantic fixtures. GitHub Actions runs on macOS, Linux, and Windows.

### 15.3 Manual E2E

1. Install the Plugin.
2. Trust the Hooks.
3. Capture a correction automatically.
4. Run `$codex-reflect:view-queue`.
5. Run `$codex-reflect:reflect --dry-run`.
6. Update `AGENTS.md` after final confirmation.
7. Scan active and archived history.
8. Run `$codex-reflect:reflect-skills`.
9. Confirm that Codex discovers the generated Skill.
10. Confirm approved targets remain after uninstall.

## 16. Supported versions and release

Do not guess a fixed historical version range. Prefer a capability probe. Officially support the stable Codex release verified at release time, and report missing features in environments without the required Hook, Plugin Skill, or history capability.

### Release gate

- No unresolved blocker remains from the Phase 0 capability spike.
- The upstream outcome-parity matrix is complete.
- CI passes on all three operating systems.
- Local E2E passes.
- No Claude runtime dependency remains.
- The README documents Hook trust, history data transfer, and known capability gaps.
- The original MIT License and Bayram Annakov copyright notice remain.
- The README attributes the upstream project and summarizes material changes.

## 17. License and attribution

Preserve this notice in the existing `LICENSE` under the terms of the MIT License:

```text
Copyright (c) 2025 Bayram Annakov
```

If derivative-work notices are added, do not remove the existing notice or MIT License text. The README must state that this is a Codex-only fork of `claude-reflect` and include the upstream URL.

## 18. Acceptance criteria

1. A Hook automatically captures a user correction into the project queue.
2. `reflect` performs semantic validation, routing, review, and final confirmation before updating `AGENTS.md` or a Skill.
3. `AGENTS.md` and Skills do not change before final confirmation.
4. `reflect-skills` proposes repeated workflows with evidence and generates only approved Skills.
5. `view-queue` and `skip-reflect` provide the same outcomes as upstream.
6. History-dependent features work with supported schemas and stop safely on unsupported schemas.
7. Semantic subprocess failure never loses candidates.
8. The platform-independent test suite passes on macOS, Linux, and Windows.
9. Capability gaps are shown explicitly to the user.
10. The project contains no large workaround for a feature Codex does not provide.

## 19. References

- [Codex Hooks](https://learn.chatgpt.com/docs/hooks)
- [Build Codex plugins](https://learn.chatgpt.com/docs/build-plugins)
- [Build Codex skills](https://learn.chatgpt.com/docs/build-skills)
- [Custom instructions with AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md)
- [Codex Memories](https://learn.chatgpt.com/docs/customization/memories)
- [Codex advanced configuration](https://learn.chatgpt.com/docs/config-file/config-advanced)
- [openai/codex issue #22078](https://github.com/openai/codex/issues/22078)
