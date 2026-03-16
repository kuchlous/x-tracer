#!/usr/bin/env python3
"""
Atomic registry update helper for testcase agents.

Acquires an exclusive file lock, reads the latest committed registry.json,
appends the new entry, writes, and commits — so concurrent agents never
overwrite each other's entries.

Usage:
    python3 tests/registry_update.py <manifest_path>

Example:
    python3 tests/registry_update.py tests/cases/synthetic/gates/and_x_prop/manifest.json
"""

import fcntl
import json
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT     = Path(__file__).parent.parent
REGISTRY_PATH = REPO_ROOT / "tests" / "registry.json"
LOCK_PATH     = REPO_ROOT / "tests" / "registry.lock"


def git(args: list[str], cwd: Path = REPO_ROOT) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git"] + args, capture_output=True, text=True, cwd=str(cwd)
    )


def update_registry(manifest_path: Path) -> None:
    manifest = json.loads(manifest_path.read_text())
    rel_path = str(manifest_path.parent.relative_to(REPO_ROOT))

    entry = {
        "id":         manifest["id"],
        "category":   manifest["category"],
        "generation": manifest["generation"],
        "path":       rel_path,
        "status":     manifest["status"],
        "author":     manifest["author"],
    }

    LOCK_PATH.touch(exist_ok=True)
    with open(LOCK_PATH, "r") as lock_file:
        # Block until we hold the exclusive lock
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            # Read the latest committed registry (not any in-memory state)
            result = git(["show", f"HEAD:tests/registry.json"])
            if result.returncode == 0:
                registry = json.loads(result.stdout)
            elif REGISTRY_PATH.exists():
                registry = json.loads(REGISTRY_PATH.read_text())
            else:
                registry = []

            # Idempotent: skip if already registered
            if any(e["id"] == entry["id"] for e in registry):
                print(f"[registry] {entry['id']} already registered, skipping")
                return

            registry.append(entry)
            REGISTRY_PATH.write_text(json.dumps(registry, indent=2) + "\n")

            # Stage and commit
            git(["add", str(REGISTRY_PATH.relative_to(REPO_ROOT))])
            result = git(["commit", "-m",
                          f"registry: add {entry['id']} [{entry['author']}]"])
            if result.returncode != 0:
                print(f"[registry] commit failed: {result.stderr.strip()}", file=sys.stderr)
                sys.exit(1)

            print(f"[registry] committed {entry['id']}")

        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <manifest_path>")
        sys.exit(1)

    update_registry(Path(sys.argv[1]))
