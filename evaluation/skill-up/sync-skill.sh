#!/bin/sh
set -eu

case "${1:-}" in
  ""|--check) ;;
  *) echo "usage: $0 [--check]" >&2; exit 2 ;;
esac

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPOSITORY_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
exec python3 - "$REPOSITORY_ROOT" "${1:-}" <<'PY'
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

repository = Path(sys.argv[1]).resolve()
check_only = sys.argv[2] == "--check"
project = repository / "evaluation/skill-up"
source_root = repository / "integrations/claude-code/plugins/powercontext"
vendor_root = project / "vendor/powercontext-plugin"
lock_path = project / "skill.lock.json"
relative_paths = (
    Path("scripts/workspace_scope.py"),
    Path("skills/powercontext-project-context/SKILL.md"),
    Path("skills/powercontext-project-context/references/review-publication.md"),
    Path("skills/powercontext-project-context/references/scope-memory.md"),
    Path("skills/powercontext-project-context/references/work-handoff.md"),
)

source_files = [source_root / path for path in relative_paths]
for path in source_files:
    if not path.is_file():
        raise SystemExit(f"missing source file: {path.relative_to(repository)}")

revision = subprocess.run(
    [
        "git",
        "-C",
        str(repository),
        "log",
        "-1",
        "--format=%H",
        "--",
        *(str(path.relative_to(repository)) for path in source_files),
    ],
    check=True,
    capture_output=True,
    text=True,
).stdout.strip()
if len(revision) != 40:
    raise SystemExit("could not resolve the source Skill revision")

expected_files = {path.as_posix(): (source_root / path).read_bytes() for path in relative_paths}
lock = {
    "schema": "powercontext.skill-up-skill-lock.v1",
    "source_revision": revision,
    "source_root": "integrations/claude-code/plugins/powercontext",
    "files": {
        name: {
            "sha256": hashlib.sha256(content).hexdigest(),
            "source": f"integrations/claude-code/plugins/powercontext/{name}",
        }
        for name, content in sorted(expected_files.items())
    },
}
lock_bytes = (json.dumps(lock, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()

if check_only:
    actual_names = {
        path.relative_to(vendor_root).as_posix()
        for path in vendor_root.rglob("*")
        if path.is_file()
    } if vendor_root.is_dir() else set()
    expected_names = set(expected_files)
    if actual_names != expected_names:
        missing = sorted(expected_names - actual_names)
        unexpected = sorted(actual_names - expected_names)
        raise SystemExit(f"vendored file set differs: missing={missing}, unexpected={unexpected}")
    for name, expected in expected_files.items():
        if (vendor_root / name).read_bytes() != expected:
            raise SystemExit(f"vendored file differs: {name}")
    if not lock_path.is_file() or lock_path.read_bytes() != lock_bytes:
        raise SystemExit("skill.lock.json differs from the source Skill")
    raise SystemExit(0)

project.mkdir(parents=True, exist_ok=True)
temporary_root = Path(tempfile.mkdtemp(prefix=".skill-sync-", dir=project))
try:
    staged_vendor = temporary_root / "powercontext-plugin"
    for name, content in expected_files.items():
        destination = staged_vendor / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    staged_lock = temporary_root / "skill.lock.json"
    staged_lock.write_bytes(lock_bytes)
    if vendor_root.exists():
        shutil.rmtree(vendor_root)
    vendor_root.parent.mkdir(parents=True, exist_ok=True)
    staged_vendor.replace(vendor_root)
    staged_lock.replace(lock_path)
finally:
    shutil.rmtree(temporary_root, ignore_errors=True)
PY
