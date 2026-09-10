#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PRODUCTION_DIRS = ("src", "migrations", "config", "user_data/strategies")
HARNESS_DIRS = ("tests", "ops")
PRODUCTION_FILES = (
    "pyproject.toml", "uv.lock", "Dockerfile", "compose.yaml", "compose.chaos.yaml",
    "user_data/config.json",
)


def files(directories: tuple[str, ...], individual: tuple[str, ...] = ()) -> list[Path]:
    selected: set[Path] = set()
    for relative in directories:
        selected.update(
            path for path in (ROOT / relative).rglob("*")
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
            and not path.name.endswith(".example")
        )
    selected.update(ROOT / relative for relative in individual)
    return sorted(selected)


def digest(file_hashes: dict[str, str]) -> str:
    canonical = json.dumps(file_hashes, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


def container_image(container: str) -> str:
    return subprocess.run(
        ["docker", "inspect", "--format", "{{.Image}}", container],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def snapshot() -> dict:
    production_hashes = {
        path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in files(PRODUCTION_DIRS, PRODUCTION_FILES)
    }
    harness_hashes = {
        path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in files(HARNESS_DIRS)
    }
    file_hashes = {**production_hashes, **harness_hashes}
    return {
        "candidate_sha256": digest(production_hashes),
        "harness_sha256": digest(harness_hashes),
        "aggregate_sha256": digest(file_hashes),
        "files": file_hashes,
        "container_images": {
            "postgres": container_image(os.environ["TEST_POSTGRES_CONTAINER"]),
            "nats": container_image(os.environ["TEST_NATS_CONTAINER"]),
        },
        "python": sys.version,
    }


def main(mode: str, target: Path) -> int:
    current = snapshot()
    if mode == "create":
        target.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(current["aggregate_sha256"])
        return 0
    expected = json.loads(target.read_text(encoding="utf-8"))
    if current != expected:
        print("release candidate changed during acceptance run", file=sys.stderr)
        print(f"expected aggregate: {expected['aggregate_sha256']}", file=sys.stderr)
        print(f"current aggregate:  {current['aggregate_sha256']}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in {"create", "verify"}:
        raise SystemExit(f"usage: {sys.argv[0]} create|verify MANIFEST_PATH")
    raise SystemExit(main(sys.argv[1], Path(sys.argv[2])))
