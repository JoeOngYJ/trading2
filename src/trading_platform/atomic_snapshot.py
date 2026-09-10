from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

from .contracts import SignedEnvelope


_SAFE_COMPONENT = re.compile(r"[^A-Za-z0-9_.-]")


def snapshot_name(pair: str, timeframe: str) -> str:
    return f"{_SAFE_COMPONENT.sub('_', pair)}__{_SAFE_COMPONENT.sub('_', timeframe)}.json"


def atomic_write_snapshot(directory: Path, envelope: SignedEnvelope) -> Path:
    directory.mkdir(parents=True, exist_ok=True, mode=0o750)
    target = directory / snapshot_name(envelope.payload.pair, envelope.payload.timeframe)
    data = envelope.model_dump_json(indent=2).encode("utf-8")
    fd, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=directory)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_name, 0o640)
        os.replace(temporary_name, target)
        directory_fd = os.open(directory, os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise
    return target


def read_snapshot(directory: Path, pair: str, timeframe: str) -> SignedEnvelope:
    target = directory / snapshot_name(pair, timeframe)
    return SignedEnvelope.model_validate_json(target.read_text(encoding="utf-8"))


def write_health(directory: Path, state: dict[str, object]) -> Path:
    directory.mkdir(parents=True, exist_ok=True, mode=0o750)
    target = directory / "bridge-health.json"
    fd, temporary_name = tempfile.mkstemp(prefix=".bridge-health.", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(state, handle, separators=(",", ":"), default=str)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, target)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise
    return target
