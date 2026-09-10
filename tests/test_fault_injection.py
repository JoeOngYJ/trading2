import json
import os
import signal
import subprocess
import sys
import time

import pytest

from trading_platform.fault_injection import checkpoint


def test_checkpoint_is_disabled_without_both_test_guards(monkeypatch, tmp_path):
    monkeypatch.setenv("PLATFORM_ENVIRONMENT", "production")
    monkeypatch.setenv("PLATFORM_FAULT_INJECTION", "1")
    monkeypatch.setenv("PLATFORM_FAULT_CHECKPOINT", "worker.after_claim")
    monkeypatch.setenv("PLATFORM_FAULT_MARKER_DIR", str(tmp_path))
    monkeypatch.setattr("trading_platform.fault_injection.os.kill",
                        lambda *_: pytest.fail("checkpoint activated in production"))
    checkpoint("worker.after_claim")
    assert list(tmp_path.iterdir()) == []


def test_checkpoint_flushes_marker_then_stops_process(monkeypatch, tmp_path):
    monkeypatch.setenv("PLATFORM_ENVIRONMENT", "test")
    monkeypatch.setenv("PLATFORM_FAULT_INJECTION", "1")
    monkeypatch.setenv("PLATFORM_FAULT_CHECKPOINT", "bridge.after_snapshot_replace")
    monkeypatch.setenv("PLATFORM_FAULT_MARKER_DIR", str(tmp_path))
    stopped = []
    monkeypatch.setattr("trading_platform.fault_injection.os.kill",
                        lambda pid, sig: stopped.append((pid, sig)))
    checkpoint("bridge.after_snapshot_replace")
    marker = tmp_path / "bridge_after_snapshot_replace.json"
    assert json.loads(marker.read_text())["checkpoint"] == "bridge.after_snapshot_replace"
    assert stopped and stopped[0][1] == signal.SIGSTOP


def test_external_harness_can_sigkill_a_paused_checkpoint(tmp_path):
    env = {
        **os.environ,
        "PLATFORM_ENVIRONMENT": "test",
        "PLATFORM_FAULT_INJECTION": "1",
        "PLATFORM_FAULT_CHECKPOINT": "worker.after_claim",
        "PLATFORM_FAULT_MARKER_DIR": str(tmp_path),
    }
    process = subprocess.Popen([
        sys.executable, "-c",
        "from trading_platform.fault_injection import checkpoint; "
        "checkpoint('worker.after_claim')",
    ], env=env)
    marker = tmp_path / "worker_after_claim.json"
    deadline = time.monotonic() + 5
    try:
        while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert marker.exists(), "checkpoint marker was not created before the deadline"
        process.kill()
        assert process.wait(timeout=5) == -signal.SIGKILL
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
