"""Locked, atomic storage for a project's codex-reflect queue."""
import json
import os
import tempfile
import threading
from pathlib import Path


_THREAD_LOCKS = {}
_THREAD_LOCKS_GUARD = threading.Lock()


def _thread_lock_for(path):
    key = str(Path(path).resolve())
    with _THREAD_LOCKS_GUARD:
        return _THREAD_LOCKS.setdefault(key, threading.Lock())


class CorruptQueueError(RuntimeError):
    """Raised when an existing queue cannot be safely interpreted."""


class FileLock:
    """Cross-platform exclusive lock over the first byte of a lock file."""

    def __init__(self, path):
        self.path = Path(path)
        self.handle = None
        self.thread_lock = _thread_lock_for(self.path)

    def __enter__(self):
        self.thread_lock.acquire()
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.handle = self.path.open("a+b")
            self.handle.seek(0, os.SEEK_END)
            if self.handle.tell() == 0:
                self.handle.write(b"\0")
                self.handle.flush()
            self.handle.seek(0)

            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.handle.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl

                fcntl.lockf(
                    self.handle.fileno(), fcntl.LOCK_EX, 1, 0, os.SEEK_SET
                )
        except Exception:
            if self.handle is not None:
                self.handle.close()
            self.thread_lock.release()
            raise
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            self.handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.lockf(
                    self.handle.fileno(), fcntl.LOCK_UN, 1, 0, os.SEEK_SET
                )
        finally:
            self.handle.close()
            self.thread_lock.release()


class StateStore:
    """Persist one project's queue without lost concurrent updates."""

    def __init__(self, project_state_dir: Path):
        self.root = Path(project_state_dir)
        self.queue_path = self.root / "queue.json"
        self.lock_path = self.root / "queue.json.lock"

    def _load_unlocked(self):
        if not self.queue_path.exists():
            return []
        try:
            value = json.loads(self.queue_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as error:
            raise CorruptQueueError(str(error)) from error
        if not isinstance(value, list):
            raise CorruptQueueError("queue root must be a JSON array")
        return value

    def _save_unlocked(self, items):
        self.root.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            dir=str(self.root), prefix="queue-", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(items, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self.queue_path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def load(self):
        if not self.queue_path.exists():
            return []
        with FileLock(self.lock_path):
            return self._load_unlocked()

    def save(self, items):
        with FileLock(self.lock_path):
            if self.queue_path.exists():
                self._load_unlocked()
            self._save_unlocked(items)

    def append(self, item):
        with FileLock(self.lock_path):
            items = self._load_unlocked()
            items.append(item)
            self._save_unlocked(items)

    def clear(self):
        with FileLock(self.lock_path):
            items = self._load_unlocked()
            self._save_unlocked([])
            return items
