# Copyright (c) 2026 OceanBase.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> None:
    if len(sys.argv) > 2 or (len(sys.argv) == 2 and sys.argv[1] != "--check"):
        raise SystemExit(f"usage: {Path(sys.argv[0]).name} [--check]")

    repository = Path(__file__).resolve().parents[2]
    check_only = len(sys.argv) == 2
    project = repository / "evaluation/skill-up"
    source_root = repository / "integrations/claude-code/plugins/powercontext"
    vendor_root = project / "vendor/powercontext-plugin"
    lock_path = project / "skill.lock.json"
    source_to_destination = (
        (Path("skills/powercontext-project-context/SKILL.md"), Path("SKILL.md")),
        (
            Path("skills/powercontext-project-context/references/review-publication.md"),
            Path("references/review-publication.md"),
        ),
        (
            Path("skills/powercontext-project-context/references/scope-memory.md"),
            Path("references/scope-memory.md"),
        ),
        (
            Path("skills/powercontext-project-context/references/work-handoff.md"),
            Path("references/work-handoff.md"),
        ),
        (Path("scripts/workspace_scope.py"), Path("scripts/workspace_scope.py")),
        (Path("claude_code_settings.py"), Path("claude_code_settings.py")),
        (Path("powercontext_client_config.py"), Path("powercontext_client_config.py")),
        (Path("scope_binding_errors.py"), Path("scope_binding_errors.py")),
    )

    source_files = [source_root / source for source, _ in source_to_destination]
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

    expected_files = {
        destination.as_posix(): (source_root / source).read_bytes() for source, destination in source_to_destination
    }
    source_by_destination = {destination.as_posix(): source.as_posix() for source, destination in source_to_destination}
    lock = {
        "schema": "powercontext.skill-up-skill-lock.v1",
        "source_revision": revision,
        "source_root": "integrations/claude-code/plugins/powercontext",
        "files": {
            name: {
                "sha256": hashlib.sha256(content).hexdigest(),
                "source": f"integrations/claude-code/plugins/powercontext/{source_by_destination[name]}",
            }
            for name, content in sorted(expected_files.items())
        },
    }
    lock_bytes = (json.dumps(lock, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()

    if check_only:
        actual_names = (
            {
                path.relative_to(vendor_root).as_posix()
                for path in vendor_root.rglob("*")
                if path.is_file() and "__pycache__" not in path.relative_to(vendor_root).parts and path.suffix != ".pyc"
            }
            if vendor_root.is_dir()
            else set()
        )
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
        return

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


if __name__ == "__main__":
    main()
