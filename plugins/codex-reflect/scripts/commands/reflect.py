#!/usr/bin/env python3
"""Prepare a reviewed Codex reflection without editing guidance targets."""
import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

from lib.codex_history import (
    list_session_files,
    parse_transcript,
    read_transcript_metadata,
)
from lib.capabilities import Capabilities, probe_capabilities
from lib.codex_paths import get_codex_home, get_project_id
from lib.reflect_utils import (
    detect_patterns,
    extract_tool_errors,
    should_include_message,
)
from lib.semantic_detector import detect_contradictions, semantic_analyze
from lib.state_store import StateStore
from lib.target_resolver import TargetResolver, TargetSuggestion


@dataclass(frozen=True)
class ReflectionContext:
    project: Path
    codex_home: Optional[Path] = None
    user_home: Optional[Path] = None
    session_files: Optional[List[Path]] = None
    capabilities: Optional[Capabilities] = None


def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--scan-history", action="store_true")
    parser.add_argument("--days", type=int)
    parser.add_argument("--targets", action="store_true")
    parser.add_argument("--review", action="store_true")
    parser.add_argument("--dedupe", action="store_true")
    parser.add_argument("--organize", action="store_true")
    parser.add_argument("--include-tool-errors", action="store_true")
    parser.add_argument("--model")
    return parser.parse_args(argv)


def _state_store(context, project):
    codex_home = Path(context.codex_home or get_codex_home()).resolve()
    state_dir = codex_home / "codex-reflect" / "projects" / get_project_id(project)
    return StateStore(state_dir)


def _base_result(project, capabilities):
    return {
        "project": str(project),
        "capabilities": asdict(capabilities),
        "candidates": [],
        "targets": [],
        "duplicates": [],
        "contradictions": [],
        "history": {
            "scanned": 0,
            "unsupported_sessions": 0,
            "issues": [],
        },
    }


def _target_dict(suggestion, candidate_id=None):
    value = {
        "kind": suggestion.kind,
        "path": str(suggestion.path) if suggestion.path is not None else None,
        "read_only": bool(suggestion.read_only),
    }
    if candidate_id is not None:
        value["candidate_id"] = candidate_id
    return value


def _available_targets(resolver, project):
    values = [
        {"kind": "agents", "path": str(path), "read_only": False}
        for path in resolver.instruction_targets(project)
    ]
    values.extend([
        {
            "kind": "skill-root",
            "path": str(resolver.repo_skill_root(project)),
            "read_only": False,
        },
        {
            "kind": "skill-root",
            "path": str(resolver.user_skill_root()),
            "read_only": False,
        },
    ])
    return values


def _parse_timestamp(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _is_stale(item, now=None):
    if item.get("type") == "explicit":
        return False
    captured = _parse_timestamp(item.get("captured_at", item.get("timestamp")))
    decay_days = item.get("decay_days")
    if captured is None or not isinstance(decay_days, (int, float)):
        return False
    current = now or datetime.now(timezone.utc)
    return current - captured > timedelta(days=max(0, decay_days))


def _same_project(resolver, transcript_cwd, project):
    if not transcript_cwd:
        return True
    try:
        transcript_root = resolver.repository_root(transcript_cwd)
    except (OSError, RuntimeError, ValueError):
        return False
    return os.path.normcase(str(transcript_root)) == os.path.normcase(str(project))


def _history_item(message, transcript, index, project):
    item_type, patterns, confidence, sentiment, decay_days = detect_patterns(message)
    if item_type is None:
        return None
    return {
        "schema_version": 1,
        "id": "history:{}:{}".format(
            transcript.session_id or transcript.path.name, index
        ),
        "type": item_type,
        "message": message,
        "captured_at": transcript.timestamp,
        "project": str(project),
        "session_id": transcript.session_id,
        "source": "history",
        "patterns": patterns,
        "confidence": confidence,
        "sentiment": sentiment,
        "decay_days": decay_days,
    }


def _scan_history(
    context,
    resolver,
    project,
    history_summary,
    days=None,
    include_tool_errors=False,
):
    files = (
        list(context.session_files)
        if context.session_files is not None
        else list_session_files(context.codex_home)
    )
    candidates = []
    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=days)
        if days is not None
        else None
    )
    for session_file in files:
        try:
            metadata = read_transcript_metadata(session_file)
        except (OSError, ValueError, RuntimeError) as error:
            history_summary["unsupported_sessions"] += 1
            history_summary["issues"].append(
                "{}: {}".format(session_file, type(error).__name__)
            )
            continue
        if metadata is None and cutoff is not None:
            history_summary["unsupported_sessions"] += 1
            history_summary["issues"].append(
                "{}: unsupported transcript schema".format(session_file)
            )
            continue
        if metadata is not None:
            timestamp = _parse_timestamp(metadata.timestamp)
            if cutoff is not None:
                if timestamp is None:
                    history_summary["issues"].append(
                        "{}: missing timestamp for --days filter".format(
                            session_file
                        )
                    )
                    continue
                if timestamp < cutoff:
                    continue
            if not _same_project(resolver, metadata.cwd, project):
                continue

        history_summary["scanned"] += 1
        try:
            transcript = parse_transcript(session_file)
        except (OSError, ValueError, RuntimeError) as error:
            history_summary["issues"].append(
                "{}: {}".format(session_file, type(error).__name__)
            )
            continue
        if not transcript.supported:
            history_summary["unsupported_sessions"] += 1
            history_summary["issues"].extend(
                "{}: {}".format(session_file, issue)
                for issue in transcript.issues
            )
            continue
        history_summary["issues"].extend(
            "{}: {}".format(session_file, issue)
            for issue in transcript.issues
        )
        timestamp = _parse_timestamp(transcript.timestamp)
        if cutoff is not None:
            if timestamp is None:
                history_summary["issues"].append(
                    "{}: missing timestamp for --days filter".format(
                        session_file
                    )
                )
                continue
            if timestamp < cutoff:
                continue
        if not _same_project(resolver, transcript.cwd, project):
            continue
        for index, message in enumerate(transcript.user_messages, start=1):
            if not should_include_message(message):
                continue
            item = _history_item(message, transcript, index, project)
            if item is not None:
                candidates.append(item)
        if include_tool_errors:
            try:
                errors = extract_tool_errors(session_file)
            except (OSError, ValueError, RuntimeError) as error:
                history_summary["issues"].append(
                    "{}: {}".format(session_file, type(error).__name__)
                )
                continue
            for index, error in enumerate(errors, start=1):
                guideline = error.get("suggested_guideline") or error.get(
                    "content", ""
                )
                candidates.append({
                    "schema_version": 1,
                    "id": "tool-error:{}:{}".format(
                        transcript.session_id or session_file.name, index
                    ),
                    "type": "tool-error",
                    "message": guideline,
                    "captured_at": transcript.timestamp,
                    "project": str(project),
                    "session_id": transcript.session_id,
                    "source": "tool-error-history",
                    "confidence": error.get("confidence", 0.7),
                    "decay_days": 180,
                })
    return candidates


def _semantic_candidates(items, model=None, semantic_available=True):
    candidates = []
    for original in items:
        item = dict(original) if isinstance(original, dict) else {}
        message = item.get("message", item.get("original_message", ""))
        if not isinstance(message, str) or not message:
            continue
        if not semantic_available:
            item["semantic_status"] = "unavailable"
            candidates.append(item)
            continue
        result = semantic_analyze(message, model=model)
        if result is None:
            item["semantic_status"] = "unavailable"
            candidates.append(item)
            continue
        if not result.get("is_learning"):
            if item.get("type") == "explicit":
                item["semantic_status"] = "explicit-retained"
                item["semantic_reasoning"] = result.get("reasoning", "")
                candidates.append(item)
            continue
        item["semantic_status"] = "validated"
        item["semantic_confidence"] = result.get("confidence", 0.0)
        item["semantic_type"] = result.get("type")
        item["semantic_reasoning"] = result.get("reasoning", "")
        if result.get("extracted_learning"):
            item["extracted_learning"] = result["extracted_learning"]
        candidates.append(item)
    return candidates


def _duplicate_groups(candidates):
    groups = {}
    for index, candidate in enumerate(candidates):
        message = candidate.get("extracted_learning") or candidate.get("message", "")
        key = " ".join(str(message).lower().split())
        if key:
            groups.setdefault(key, []).append(candidate.get("id", index))
    return [
        {"normalized": key, "candidate_ids": values}
        for key, values in groups.items()
        if len(values) > 1
    ]


def _candidate_target(resolver, candidate, project):
    confidence = candidate.get("confidence", 0.0)
    if isinstance(confidence, (int, float)) and confidence < 0.6:
        return TargetSuggestion("queue", None, read_only=True)
    skill_path = candidate.get("skill_path")
    if skill_path:
        return resolver.suggest_target("skill", cwd=project, skill_path=skill_path)
    source_projects = candidate.get("source_projects")
    if isinstance(source_projects, list) and len(set(source_projects)) > 1:
        return resolver.suggest_target(
            "multi-project", cwd=project, source_projects=source_projects
        )
    scope = candidate.get("scope")
    if scope == "global":
        return resolver.suggest_target("global")
    if scope == "path-specific" and candidate.get("evidence_path"):
        return resolver.suggest_target(
            "path-specific", cwd=candidate["evidence_path"]
        )
    return resolver.suggest_target("project", cwd=project)


def prepare_reflection(
    context,
    dry_run=False,
    scan_history=False,
    days=None,
    targets=False,
    review=False,
    dedupe=False,
    organize=False,
    include_tool_errors=False,
    model=None,
):
    del dry_run
    if days is not None and days < 0:
        raise ValueError("days must be non-negative")
    codex_home = Path(context.codex_home or get_codex_home()).resolve()
    resolver = TargetResolver(codex_home, user_home=context.user_home)
    project = resolver.repository_root(context.project)
    capabilities = context.capabilities or probe_capabilities(codex_home)
    result = _base_result(project, capabilities)

    if targets:
        result["targets"] = _available_targets(resolver, project)
        return result

    queue_items = _state_store(context, project).load()
    items = [
        dict(item)
        for item in queue_items
        if isinstance(item, dict) and (review or not _is_stale(item))
    ]
    if scan_history:
        if capabilities.history_available or context.session_files is not None:
            items.extend(_scan_history(
                context,
                resolver,
                project,
                result["history"],
                days=days,
                include_tool_errors=include_tool_errors,
            ))
        else:
            result["history"]["issues"].extend(
                warning
                for warning in capabilities.warnings
                if "history" in warning.lower()
                or "sessions" in warning.lower()
            )

    candidates = _semantic_candidates(
        items,
        model=model,
        semantic_available=capabilities.semantic_available,
    )
    result["candidates"] = candidates
    if dedupe:
        result["duplicates"] = _duplicate_groups(candidates)
    if organize and capabilities.semantic_available:
        entries = [
            candidate.get("extracted_learning") or candidate.get("message", "")
            for candidate in candidates
        ]
        result["contradictions"] = detect_contradictions(
            [entry for entry in entries if entry], model=model
        )
    result["targets"] = [
        _target_dict(
            _candidate_target(resolver, candidate, project),
            candidate_id=candidate.get("id", index),
        )
        for index, candidate in enumerate(candidates)
    ]
    return result


def main(argv=None):
    args = parse_args(argv)
    result = prepare_reflection(
        ReflectionContext(project=Path.cwd()), **vars(args)
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
