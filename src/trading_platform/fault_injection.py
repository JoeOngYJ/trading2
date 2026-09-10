from __future__ import annotations

import json
import os
import signal
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def checkpoint(name: str) -> None:
    """Pause at a named test checkpoint so an external harness can send SIGKILL."""
    if (
        os.getenv("PLATFORM_ENVIRONMENT") != "test"
        or os.getenv("PLATFORM_FAULT_INJECTION") != "1"
        or os.getenv("PLATFORM_FAULT_CHECKPOINT") != name
    ):
        return
    marker_dir_raw = os.getenv("PLATFORM_FAULT_MARKER_DIR")
    if not marker_dir_raw:
        raise RuntimeError("fault injection requires PLATFORM_FAULT_MARKER_DIR")
    marker_dir = Path(marker_dir_raw)
    marker_dir.mkdir(parents=True, exist_ok=True, mode=0o750)
    target = marker_dir / f"{name.replace('.', '_')}.json"
    fd, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=marker_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(
                {"checkpoint": name, "pid": os.getpid(),
                 "observed_at": datetime.now(timezone.utc).isoformat()},
                handle, separators=(",", ":"),
            )
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, target)
        directory_fd = os.open(marker_dir, os.O_DIRECTORY)
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
    os.kill(os.getpid(), signal.SIGSTOP)
