"""Read-only resolution of Codex instruction and Skill authoring targets."""
import os
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional


@dataclass(frozen=True)
class TargetSuggestion:
    """A proposed guidance target; ``path`` is absent for queue-only routing."""

    kind: str
    path: Optional[Path]
    read_only: bool = False


class TargetResolver:
    """Resolve the active AGENTS.md chain and safe Skill authoring roots."""

    def __init__(self, codex_home, user_home=None):
        self.codex_home = Path(codex_home).expanduser().resolve()
        self.user_home = (
            Path(user_home).expanduser().resolve()
            if user_home is not None
            else Path.home().resolve()
        )

    @staticmethod
    def active_instruction_file(directory) -> Optional[Path]:
        directory = Path(directory).expanduser().resolve()
        for name in ("AGENTS.override.md", "AGENTS.md"):
            candidate = directory / name
            try:
                if candidate.is_file() and candidate.read_text(encoding="utf-8").strip():
                    return candidate
            except OSError:
                continue
        return None

    def user_skill_root(self) -> Path:
        return self.user_home / ".agents" / "skills"

    @staticmethod
    def repo_skill_root(repo_root) -> Path:
        return Path(repo_root).expanduser().resolve() / ".agents" / "skills"

    @staticmethod
    def repository_root(cwd) -> Path:
        cwd = Path(cwd).expanduser().resolve()
        try:
            result = subprocess.run(
                ["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError:
            return cwd
        if result.returncode == 0 and result.stdout.strip():
            return Path(result.stdout.strip()).expanduser().resolve()
        return cwd

    def instruction_targets(self, cwd) -> List[Path]:
        cwd = Path(cwd).expanduser().resolve()
        root = self.repository_root(cwd)
        targets = []

        global_target = self.active_instruction_file(self.codex_home)
        if global_target is not None:
            targets.append(global_target)

        directories = [root]
        try:
            relative_parts = cwd.relative_to(root).parts
        except ValueError:
            relative_parts = ()
        directory = root
        for part in relative_parts:
            directory = directory / part
            directories.append(directory)

        for directory in directories:
            target = self.active_instruction_file(directory)
            if target is not None and target not in targets:
                targets.append(target)
        return targets

    def suggest_global_instruction_target(self) -> Path:
        active = self.active_instruction_file(self.codex_home)
        return active if active is not None else self.codex_home / "AGENTS.md"

    def suggest_instruction_target(self, learning, cwd) -> Path:
        del learning
        cwd = Path(cwd).expanduser().resolve()
        active = self.active_instruction_file(cwd)
        if active is not None:
            return active

        root = self.repository_root(cwd)
        try:
            cwd.relative_to(root)
        except ValueError:
            return cwd / "AGENTS.md"

        directory = cwd
        while directory != root:
            directory = directory.parent
            active = self.active_instruction_file(directory)
            if active is not None:
                return active
        return cwd / "AGENTS.md"

    def suggest_skill_root(self, source_projects: Iterable[str], repo_root) -> Path:
        if len(set(source_projects)) > 1:
            return self.user_skill_root()
        return self.repo_skill_root(repo_root)

    @staticmethod
    def _is_within(path: Path, root: Path) -> bool:
        return path == root or root in path.parents

    @staticmethod
    def _is_writable_regular_file(path: Path) -> bool:
        try:
            mode = path.stat().st_mode
        except OSError:
            return False
        write_bits = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
        return (
            stat.S_ISREG(mode)
            and bool(mode & write_bits)
            and os.access(path, os.W_OK)
        )

    def suggest_skill_target(self, skill_path, repo_root) -> TargetSuggestion:
        skill_path = Path(skill_path).expanduser().resolve()
        writable_roots = (
            self.user_skill_root().resolve(),
            self.repo_skill_root(repo_root).resolve(),
        )
        read_only = not (
            any(self._is_within(skill_path, root) for root in writable_roots)
            and self._is_writable_regular_file(skill_path)
        )
        return TargetSuggestion("skill", skill_path, read_only=read_only)

    def suggest_target(
        self,
        scope: str,
        cwd=None,
        *,
        source_projects: Iterable[str] = (),
        skill_path=None,
    ) -> TargetSuggestion:
        """Route one reviewed learning without writing the proposed target."""
        if scope == "global":
            return TargetSuggestion("agents", self.suggest_global_instruction_target())
        if scope == "low-confidence":
            return TargetSuggestion("queue", None, read_only=True)
        if cwd is None:
            raise ValueError("cwd is required for this target scope")

        repo_root = self.repository_root(cwd)
        if scope == "project":
            return TargetSuggestion(
                "agents", self.suggest_instruction_target("", repo_root)
            )
        if scope == "path-specific":
            return TargetSuggestion("agents", self.suggest_instruction_target("", cwd))
        if scope == "skill":
            if skill_path is None:
                raise ValueError("skill_path is required for skill routing")
            return self.suggest_skill_target(skill_path, repo_root)
        if scope == "multi-project":
            return TargetSuggestion(
                "skill-root",
                self.suggest_skill_root(source_projects, repo_root),
            )
        raise ValueError("unknown target scope: {}".format(scope))
