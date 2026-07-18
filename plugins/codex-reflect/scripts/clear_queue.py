#!/usr/bin/env python3
"""Clear the current project's queue only after explicit confirmation."""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib.codex_paths import get_project_state_dir
from lib.state_store import StateStore


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()
    if not args.confirm:
        print("Refusing to clear queue without --confirm.", file=sys.stderr)
        return 2
    removed = StateStore(get_project_state_dir()).clear()
    print(json.dumps(removed, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
