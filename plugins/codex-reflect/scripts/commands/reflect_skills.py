#!/usr/bin/env python3
"""Collect deterministic Codex history input for reusable-Skill discovery."""
import argparse
import json
import os
import stat
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

from lib.codex_history import list_session_files, parse_transcript
from lib.codex_paths import get_codex_home
from lib.target_resolver import TargetResolver


@dataclass(frozen=True)
class DiscoveryContext:
    codex_home: Path
    project: Path
    user_home: Path
    now: datetime


def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=14)
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--project")
    scope.add_argument("--all-projects", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def _frontmatter_name(skill_file):
    fallback = skill_file.parent.name
    try:
        lines = skill_file.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return fallback
    if not lines or lines[0].strip() != "---":
        return fallback
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line.startswith("name:"):
            value = line.split(":", 1)[1].strip()
            return value or fallback
    return fallback


def _safe_authoring_root(root):
    lexical = Path(os.path.abspath(os.path.normpath(str(root))))
    try:
        canonical = root.resolve()
    except (OSError, RuntimeError):
        return None
    return canonical if canonical == lexical else None


def _is_writable_regular_file(path):
    try:
        mode = path.stat().st_mode
    except OSError:
        return False
    write_bits = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
    return stat.S_ISREG(mode) and bool(mode & write_bits) and os.access(path, os.W_OK)


def collect_existing_skills(project, user_home):
    roots = (
        ("repository", Path(project).expanduser().resolve() / ".agents" / "skills"),
        ("user", Path(user_home).expanduser().resolve() / ".agents" / "skills"),
    )
    result = []
    for scope, root in roots:
        safe_root = _safe_authoring_root(root)
        if safe_root is None or not safe_root.is_dir():
            continue
        for skill_file in sorted(safe_root.glob("*/SKILL.md")):
            if skill_file.is_symlink() or skill_file.parent.is_symlink():
                continue
            try:
                canonical = skill_file.resolve(strict=True)
                canonical.relative_to(safe_root)
            except (OSError, ValueError):
                continue
            if not canonical.is_file():
                continue
            result.append({
                "name": _frontmatter_name(canonical),
                "path": str(canonical),
                "scope": scope,
                "writable": _is_writable_regular_file(canonical),
            })
    return result


def _parse_timestamp(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)


def _utc(value):
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def collect_discovery_input(
    context,
    days=14,
    project=None,
    all_projects=False,
):
    if days < 0:
        raise ValueError("days must be non-negative")
    resolver = TargetResolver(context.codex_home, user_home=context.user_home)
    selected_project = resolver.repository_root(project or context.project)
    cutoff = _utc(context.now) - timedelta(days=days)
    sessions = []
    unsupported = 0
    projects = set()
    issues = []

    for path in list_session_files(context.codex_home):
        try:
            transcript = parse_transcript(path)
        except (OSError, ValueError, RuntimeError) as error:
            unsupported += 1
            issues.append("{}: {}".format(path, type(error).__name__))
            continue
        if not transcript.supported:
            unsupported += 1
            issues.extend(
                "{}: {}".format(path, issue)
                for issue in transcript.issues
            )
            continue
        timestamp = _parse_timestamp(transcript.timestamp)
        if timestamp is None:
            unsupported += 1
            issues.append("{}: missing or invalid timestamp".format(path))
            continue
        if timestamp < cutoff:
            continue
        if not transcript.cwd:
            unsupported += 1
            issues.append("{}: missing project cwd".format(path))
            continue
        transcript_project = resolver.repository_root(transcript.cwd)
        if not all_projects and transcript_project != selected_project:
            continue
        projects.add(str(transcript_project))
        sessions.append({
            "session_id": transcript.session_id,
            "project": str(transcript_project),
            "timestamp": transcript.timestamp,
            "messages": transcript.user_messages,
            "source": str(path),
        })
        issues.extend(
            "{}: {}".format(path, issue)
            for issue in transcript.issues
        )

    return {
        "supported_sessions": len(sessions),
        "unsupported_sessions": unsupported,
        "projects": sorted(projects),
        "sessions": sessions,
        "existing_skills": collect_existing_skills(
            selected_project,
            context.user_home,
        ),
        "issues": issues,
    }


def main(argv=None):
    args = parse_args(argv)
    result = collect_discovery_input(
        DiscoveryContext(
            codex_home=get_codex_home(),
            project=Path.cwd(),
            user_home=Path.home(),
            now=datetime.now(timezone.utc),
        ),
        days=args.days,
        project=args.project,
        all_projects=args.all_projects,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
