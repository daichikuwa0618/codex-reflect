#!/usr/bin/env python3
"""Tests for locked, atomic project queue storage."""
import json
import os
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = REPO_ROOT / "plugins" / "codex-reflect"
SCRIPTS_DIR = PLUGIN_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from lib.state_store import CorruptQueueError, FileLock, StateStore


class TestStateStore(unittest.TestCase):
    def test_thread_locks_are_shared_per_path_not_globally(self):
        with tempfile.TemporaryDirectory() as root:
            first = FileLock(Path(root) / "first.lock")
            same = FileLock(Path(root) / "." / "first.lock")
            different = FileLock(Path(root) / "different.lock")

            self.assertIs(first.thread_lock, same.thread_lock)
            self.assertIsNot(first.thread_lock, different.thread_lock)

    def test_thread_lock_is_released_when_lock_setup_fails(self):
        with tempfile.TemporaryDirectory() as root:
            lock = FileLock(Path(root) / "queue.json.lock")

            with patch.object(Path, "mkdir", side_effect=OSError("no access")):
                with self.assertRaisesRegex(OSError, "no access"):
                    lock.__enter__()

            self.assertFalse(lock.thread_lock.locked())

    def test_append_round_trips_atomically(self):
        with tempfile.TemporaryDirectory() as root:
            store = StateStore(Path(root))
            store.append({"id": "one", "schema_version": 1})
            self.assertEqual(
                store.load(), [{"id": "one", "schema_version": 1}]
            )

    def test_save_uses_same_directory_tempfile_fsync_and_replace(self):
        with tempfile.TemporaryDirectory() as root, patch(
            "lib.state_store.tempfile.mkstemp", wraps=tempfile.mkstemp
        ) as make_temp, patch(
            "lib.state_store.os.fsync", wraps=os.fsync
        ) as fsync, patch(
            "lib.state_store.os.replace", wraps=os.replace
        ) as replace:
            store = StateStore(Path(root))
            store.save([{"id": "one"}])

            self.assertEqual(Path(make_temp.call_args.kwargs["dir"]), Path(root))
            fsync.assert_called_once()
            source, destination = replace.call_args.args
            self.assertEqual(Path(source).parent, Path(root))
            self.assertEqual(Path(destination), Path(root) / "queue.json")

    def test_lock_file_contains_first_byte(self):
        with tempfile.TemporaryDirectory() as root:
            store = StateStore(Path(root))
            store.append({"id": "one"})
            self.assertEqual((Path(root) / "queue.json.lock").read_bytes(), b"\0")

    def test_loading_missing_queue_does_not_create_state(self):
        with tempfile.TemporaryDirectory() as root:
            state_root = Path(root) / "missing" / "project"

            self.assertEqual(StateStore(state_root).load(), [])
            self.assertFalse(state_root.exists())

    def test_clear_returns_removed_items(self):
        with tempfile.TemporaryDirectory() as root:
            store = StateStore(Path(root))
            store.save([{"id": "one"}])
            self.assertEqual(store.clear(), [{"id": "one"}])
            self.assertEqual(store.load(), [])

    def test_malformed_queue_is_not_overwritten_by_load(self):
        with tempfile.TemporaryDirectory() as root:
            queue = Path(root) / "queue.json"
            queue.parent.mkdir(parents=True, exist_ok=True)
            queue.write_text("{broken", encoding="utf-8")
            with self.assertRaises(CorruptQueueError):
                StateStore(Path(root)).load()
            self.assertEqual(queue.read_text(encoding="utf-8"), "{broken")

    def test_malformed_queue_is_not_overwritten_by_mutations(self):
        with tempfile.TemporaryDirectory() as root:
            queue = Path(root) / "queue.json"
            queue.write_text("{broken", encoding="utf-8")
            store = StateStore(Path(root))

            for operation in (
                lambda: store.save([{"id": "replacement"}]),
                lambda: store.append({"id": "appended"}),
                store.clear,
            ):
                with self.subTest(operation=operation), self.assertRaises(
                    CorruptQueueError
                ):
                    operation()
                self.assertEqual(queue.read_text(encoding="utf-8"), "{broken")

    def test_non_array_queue_is_corrupt_and_not_overwritten(self):
        with tempfile.TemporaryDirectory() as root:
            queue = Path(root) / "queue.json"
            queue.write_text(json.dumps({"id": "one"}), encoding="utf-8")
            store = StateStore(Path(root))

            with self.assertRaisesRegex(CorruptQueueError, "JSON array"):
                store.save([])
            self.assertEqual(json.loads(queue.read_text(encoding="utf-8")), {"id": "one"})

    def test_concurrent_appends_do_not_lose_items(self):
        with tempfile.TemporaryDirectory() as root:
            def append(index):
                StateStore(Path(root)).append({"id": str(index)})

            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(append, range(32)))
            items = StateStore(Path(root)).load()
            self.assertEqual(
                {item["id"] for item in items},
                {str(index) for index in range(32)},
            )


if __name__ == "__main__":
    unittest.main()
