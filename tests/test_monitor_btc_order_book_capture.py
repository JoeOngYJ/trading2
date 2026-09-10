import hashlib
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

SCRIPT = Path(__file__).parents[1] / "scripts" / "monitor_btc_order_book_capture.py"
SPEC = importlib.util.spec_from_file_location("monitor_btc_order_book_capture", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def write_manifest(capture_dir, *, status="running", checkpoint="2026-08-25T00:01:00+00:00"):
    capture_dir.mkdir(parents=True)
    raw = capture_dir / "raw"
    raw.mkdir()
    partition = raw / "raw-20260825T00.ndjson.gz"
    partition.write_bytes(b"partition")
    partial = raw / "raw-20260825T01.ndjson.part"
    if status == "running":
        partial.write_bytes(b"active")
    item = {
        "file": partition.name,
        "sha256": hashlib.sha256(partition.read_bytes()).hexdigest(),
        "bytes": partition.stat().st_size,
        "records": 10,
        "kind_counts": {"stream": 10},
    }
    manifest = {
        "capture_id": capture_dir.name,
        "status": status,
        "started_at": "2026-08-25T00:00:00+00:00",
        "checkpointed_at": checkpoint,
        "ended_at": "2026-08-25T02:00:00+00:00" if status == "complete" else None,
        "requested_duration_seconds": 7200,
        "connections": 1,
        "reconnects": 0,
        "record_count": 10,
        "active_record_count": 12,
        "partitions": [item],
    }
    (capture_dir / "capture-manifest.json").write_text(
        MODULE.canonical_json(manifest) + "\n", encoding="utf-8"
    )
    return manifest, partition


def test_running_capture_health_and_staleness(tmp_path):
    capture_dir = tmp_path / "capture-1"
    write_manifest(capture_dir)
    healthy = MODULE.capture_status(
        capture_dir, now=datetime(2026, 8, 25, 0, 2, tzinfo=timezone.utc), min_free_gb=0
    )
    assert healthy["healthy"]
    assert healthy["finalized_partitions"] == 1
    stale = MODULE.capture_status(
        capture_dir, now=datetime(2026, 8, 25, 0, 5, tzinfo=timezone.utc),
        stale_seconds=180, min_free_gb=0,
    )
    assert not stale["healthy"]
    assert "stale_checkpoint" in stale["reasons"]


def test_partition_checksum_damage_fails_health(tmp_path):
    capture_dir = tmp_path / "capture-2"
    _, partition = write_manifest(capture_dir)
    partition.write_bytes(b"damaged")
    result = MODULE.capture_status(
        capture_dir, now=datetime(2026, 8, 25, 0, 2, tzinfo=timezone.utc), min_free_gb=0
    )
    assert not result["healthy"]
    assert result["partition_errors"][0]["error"] == "checksum_mismatch"


def test_recent_rotated_partition_is_tolerated_until_running_manifest_catches_up(tmp_path):
    capture_dir = tmp_path / "capture-race"
    write_manifest(capture_dir)
    pending = capture_dir / "raw" / "raw-20260825T01.ndjson.gz"
    pending.write_bytes(b"newly-finalized")
    result = MODULE.capture_status(
        capture_dir, now=datetime(2026, 8, 25, 0, 2, tzinfo=timezone.utc), stale_seconds=180,
        min_free_gb=0,
    )
    assert result["healthy"]
    assert result["pending_manifest_partitions"] == [pending.name]


def test_complete_capture_requires_no_partial_and_matching_count(tmp_path):
    capture_dir = tmp_path / "capture-3"
    write_manifest(capture_dir, status="complete")
    result = MODULE.capture_status(capture_dir, min_free_gb=0)
    assert result["healthy"]


def test_full_utc_hours_excludes_partial_edges():
    start = datetime(2026, 8, 25, 0, 30, tzinfo=timezone.utc)
    end = datetime(2026, 8, 25, 3, 30, tzinfo=timezone.utc)
    assert MODULE.full_utc_hours(start, end) == [
        "2026-08-25T01:00:00Z", "2026-08-25T02:00:00Z"
    ]


def test_acceptance_is_frozen_and_requires_hourly_coverage():
    capture = {
        "capture_id": "capture-4", "status": "complete",
        "started_at": "2026-08-25T00:30:00+00:00",
        "ended_at": "2026-08-25T03:30:00+00:00",
        "requested_duration_seconds": 10800, "reconnects": 0,
    }
    replay = {
        "accepted_depth_events": 999, "inactive_depth_events": 1,
        "accepted_segments": [{"segment_id": 1}], "rejected_intervals": [],
        "clock_sync_samples": [{"connection_id": 1}],
        "hourly_quality": [
            {"hour": "2026-08-25T01:00:00Z", "stream_records": 10,
             "accepted_depth_events": 5},
            {"hour": "2026-08-25T02:00:00Z", "stream_records": 10,
             "accepted_depth_events": 5},
        ],
    }
    accepted = MODULE.evaluate_acceptance(capture, replay)
    assert accepted["decision"] == "accepted"
    assert accepted["accepted_depth_fraction"] == 0.999
    replay["hourly_quality"].pop()
    rejected = MODULE.evaluate_acceptance(capture, replay)
    assert rejected["decision"] == "rejected"
    assert rejected["missing_full_utc_hours"] == ["2026-08-25T02:00:00Z"]
