#!/usr/bin/env python3
"""Monitor a BTC L2 capture and run deterministic OB0 acceptance after completion."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

PIPELINE_PATH = Path(__file__).with_name("btc_order_book_pipeline.py")
DEFAULT_CAPTURE_ROOT = Path("artifacts/agent-level-experiment/btc-order-book/captures")
DEFAULT_ACCEPTANCE_ROOT = Path("artifacts/agent-level-experiment/btc-order-book/acceptance")


class MonitorError(RuntimeError):
    pass


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise MonitorError(f"timestamp lacks timezone: {value}")
    return parsed.astimezone(timezone.utc)


def load_manifest(capture_dir: Path) -> dict[str, Any]:
    path = capture_dir / "capture-manifest.json"
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MonitorError(f"cannot read capture manifest: {exc}") from exc
    if manifest.get("capture_id") != capture_dir.name:
        raise MonitorError("capture ID disagrees with directory name")
    return manifest


def verify_partitions(capture_dir: Path, manifest: dict[str, Any]) -> list[dict[str, str | None]]:
    errors: list[dict[str, str | None]] = []
    expected_names: set[str] = set()
    for item in manifest.get("partitions", []):
        name = item.get("file")
        if not isinstance(name, str) or name in expected_names:
            errors.append({"file": str(name), "error": "invalid_or_duplicate_manifest_entry"})
            continue
        expected_names.add(name)
        path = capture_dir / "raw" / name
        if not path.is_file():
            errors.append({"file": name, "error": "missing"})
            continue
        actual = sha256_path(path)
        if actual != item.get("sha256"):
            errors.append({"file": name, "error": "checksum_mismatch"})
    actual_names = {path.name for path in (capture_dir / "raw").glob("raw-*.ndjson.gz")}
    for unexpected in sorted(actual_names - expected_names):
        errors.append({"file": unexpected, "error": "unmanifested_partition"})
    return errors


def capture_status(
    capture_dir: Path, *, stale_seconds: float = 180.0, min_free_gb: float = 10.0,
    now: datetime | None = None,
) -> dict[str, Any]:
    manifest = load_manifest(capture_dir)
    now = now or datetime.now(timezone.utc)
    status = manifest.get("status")
    checkpoint = parse_time(manifest["checkpointed_at"])
    checkpoint_age = (now - checkpoint).total_seconds()
    raw_partition_errors = verify_partitions(capture_dir, manifest)
    partition_errors: list[dict[str, str | None]] = []
    pending_manifest_partitions: list[str] = []
    for item in raw_partition_errors:
        if status == "running" and item.get("error") == "unmanifested_partition":
            pending_path = capture_dir / "raw" / str(item["file"])
            age = now.timestamp() - pending_path.stat().st_mtime
            if age <= stale_seconds:
                pending_manifest_partitions.append(str(item["file"]))
                continue
        partition_errors.append(item)
    part_files = sorted((capture_dir / "raw").glob("*.part"))
    part_bytes = sum(path.stat().st_size for path in part_files)
    part_age = None
    if part_files:
        newest_ns = max(path.stat().st_mtime_ns for path in part_files)
        part_age = max(0.0, now.timestamp() - newest_ns / 1_000_000_000)
    disk = shutil.disk_usage(capture_dir)
    free_gb = disk.free / 1_000_000_000
    finalized_bytes = sum(int(item.get("bytes", 0)) for item in manifest.get("partitions", []))
    finalized_records = sum(int(item.get("records", 0)) for item in manifest.get("partitions", []))
    reasons: list[str] = []
    if status == "running":
        if checkpoint_age > stale_seconds:
            reasons.append("stale_checkpoint")
        if not part_files:
            reasons.append("missing_active_partition")
        elif part_age is not None and part_age > stale_seconds:
            reasons.append("stale_active_partition")
    elif status == "complete":
        if part_files:
            reasons.append("partial_file_after_completion")
        if finalized_records != int(manifest.get("record_count", -1)):
            reasons.append("finalized_record_count_mismatch")
    else:
        reasons.append(f"terminal_or_unknown_status:{status}")
    if partition_errors:
        reasons.append("partition_verification_failed")
    if free_gb < min_free_gb:
        reasons.append("low_disk_space")
    return {
        "capture_id": manifest["capture_id"],
        "status": status,
        "healthy": not reasons,
        "reasons": reasons,
        "started_at": manifest.get("started_at"),
        "checkpointed_at": manifest.get("checkpointed_at"),
        "checkpoint_age_seconds": round(checkpoint_age, 3),
        "connections": manifest.get("connections"),
        "reconnects": manifest.get("reconnects"),
        "active_record_count": manifest.get("active_record_count"),
        "finalized_record_count": finalized_records,
        "finalized_partitions": len(manifest.get("partitions", [])),
        "finalized_compressed_bytes": finalized_bytes,
        "active_partial_files": [path.name for path in part_files],
        "active_partial_bytes": part_bytes,
        "active_partial_age_seconds": None if part_age is None else round(part_age, 3),
        "free_disk_gb": round(free_gb, 3),
        "partition_errors": partition_errors,
        "pending_manifest_partitions": pending_manifest_partitions,
    }


def full_utc_hours(start: datetime, end: datetime) -> list[str]:
    cursor = start.replace(minute=0, second=0, microsecond=0)
    if cursor < start:
        cursor += timedelta(hours=1)
    finish = end.replace(minute=0, second=0, microsecond=0)
    result: list[str] = []
    while cursor < finish:
        result.append(cursor.strftime("%Y-%m-%dT%H:00:00Z"))
        cursor += timedelta(hours=1)
    return result


def evaluate_acceptance(
    capture_manifest: dict[str, Any], replay_manifest: dict[str, Any],
    *, minimum_accepted_fraction: float = 0.995,
) -> dict[str, Any]:
    checks: dict[str, bool] = {}
    checks["capture_complete"] = capture_manifest.get("status") == "complete"
    try:
        start = parse_time(capture_manifest["started_at"])
        end = parse_time(capture_manifest["ended_at"])
        requested = int(capture_manifest["requested_duration_seconds"])
        elapsed = (end - start).total_seconds()
    except (KeyError, TypeError, ValueError, MonitorError):
        start = end = datetime.now(timezone.utc)
        requested = 0
        elapsed = -1
    checks["requested_duration_met"] = elapsed >= requested > 0
    accepted = int(replay_manifest.get("accepted_depth_events", 0))
    inactive = int(replay_manifest.get("inactive_depth_events", 0))
    denominator = accepted + inactive
    accepted_fraction = 0.0 if denominator == 0 else accepted / denominator
    checks["accepted_depth_present"] = accepted > 0
    checks["accepted_fraction_met"] = accepted_fraction >= minimum_accepted_fraction
    checks["accepted_segment_present"] = bool(replay_manifest.get("accepted_segments"))
    checks["clock_sync_present"] = bool(replay_manifest.get("clock_sync_samples"))
    observed_hours = {
        item.get("hour") for item in replay_manifest.get("hourly_quality", [])
        if int(item.get("stream_records", 0)) > 0 and int(item.get("accepted_depth_events", 0)) > 0
    }
    expected_hours = full_utc_hours(start, end) if elapsed >= 0 else []
    missing_hours = sorted(set(expected_hours) - observed_hours)
    checks["all_full_hours_have_accepted_depth"] = bool(expected_hours) and not missing_hours
    return {
        "schema_version": "btc-spot-l2-ob0-acceptance-v1",
        "capture_id": capture_manifest.get("capture_id"),
        "decision": "accepted" if all(checks.values()) else "rejected",
        "checks": checks,
        "requested_duration_seconds": requested,
        "observed_duration_seconds": elapsed,
        "minimum_accepted_depth_fraction": minimum_accepted_fraction,
        "accepted_depth_fraction": accepted_fraction,
        "expected_full_utc_hours": len(expected_hours),
        "missing_full_utc_hours": missing_hours,
        "reconnects": capture_manifest.get("reconnects"),
        "accepted_segments": len(replay_manifest.get("accepted_segments", [])),
        "rejected_intervals": len(replay_manifest.get("rejected_intervals", [])),
    }


def load_pipeline() -> Any:
    spec = importlib.util.spec_from_file_location("btc_order_book_pipeline_for_monitor", PIPELINE_PATH)
    if spec is None or spec.loader is None:
        raise MonitorError("cannot load order-book pipeline")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run_acceptance(capture_dir: Path, output_dir: Path, minimum_fraction: float) -> dict[str, Any]:
    capture_manifest = load_manifest(capture_dir)
    status = capture_status(capture_dir)
    if capture_manifest.get("status") != "complete" or not status["healthy"]:
        raise MonitorError(f"capture is not complete and healthy: {status['reasons']}")
    output_dir.mkdir(parents=True, exist_ok=True)
    primary = output_dir / "replay-primary"
    pipeline = load_pipeline()
    primary_manifest = pipeline.replay_records(
        pipeline.iter_capture_records(capture_dir), primary
    )
    primary_manifest["capture_manifest_sha256"] = sha256_path(
        capture_dir / "capture-manifest.json"
    )
    pipeline.atomic_write_json(primary / "replay-manifest.json", primary_manifest)
    with tempfile.TemporaryDirectory(prefix="btc-l2-replay-verify-", dir=output_dir) as temp:
        verification = Path(temp)
        verification_manifest = pipeline.replay_records(
            pipeline.iter_capture_records(capture_dir), verification
        )
        deterministic = all(
            primary_manifest[key] == verification_manifest[key]
            for key in ("feature_sha256", "trade_sha256")
        )
    report = evaluate_acceptance(
        capture_manifest, primary_manifest,
        minimum_accepted_fraction=minimum_fraction,
    )
    report["checks"]["deterministic_replay"] = deterministic
    if not deterministic:
        report["decision"] = "rejected"
    report["capture_manifest_sha256"] = sha256_path(capture_dir / "capture-manifest.json")
    report["replay_manifest_sha256"] = sha256_path(primary / "replay-manifest.json")
    pipeline.atomic_write_json(output_dir / "ob0-acceptance-report.json", report)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--capture-dir", type=Path, required=True)
    status_parser.add_argument("--stale-seconds", type=float, default=180.0)
    status_parser.add_argument("--min-free-gb", type=float, default=10.0)

    accept_parser = subparsers.add_parser("accept")
    accept_parser.add_argument("--capture-dir", type=Path, required=True)
    accept_parser.add_argument("--output-dir", type=Path, required=True)
    accept_parser.add_argument("--minimum-accepted-fraction", type=float, default=0.995)

    watch_parser = subparsers.add_parser("watch")
    watch_parser.add_argument("--capture-dir", type=Path, required=True)
    watch_parser.add_argument("--output-dir", type=Path, required=True)
    watch_parser.add_argument("--poll-seconds", type=float, default=60.0)
    watch_parser.add_argument("--stale-seconds", type=float, default=180.0)
    watch_parser.add_argument("--min-free-gb", type=float, default=10.0)
    watch_parser.add_argument("--minimum-accepted-fraction", type=float, default=0.995)
    args = parser.parse_args()
    if getattr(args, "minimum_accepted_fraction", 0.995) <= 0 or getattr(
        args, "minimum_accepted_fraction", 0.995
    ) > 1:
        parser.error("minimum accepted fraction must be in (0, 1]")
    if getattr(args, "poll_seconds", 60) <= 0:
        parser.error("poll seconds must be positive")
    return args


def main() -> None:
    args = parse_args()
    if args.command == "status":
        result = capture_status(
            args.capture_dir, stale_seconds=args.stale_seconds, min_free_gb=args.min_free_gb
        )
        print(canonical_json(result))
        raise SystemExit(0 if result["healthy"] else 1)
    if args.command == "accept":
        print(canonical_json(run_acceptance(
            args.capture_dir, args.output_dir, args.minimum_accepted_fraction
        )))
        return
    while True:
        result = capture_status(
            args.capture_dir, stale_seconds=args.stale_seconds, min_free_gb=args.min_free_gb
        )
        print(canonical_json(result), flush=True)
        if not result["healthy"]:
            raise SystemExit(1)
        if result["status"] == "complete":
            report = run_acceptance(
                args.capture_dir, args.output_dir, args.minimum_accepted_fraction
            )
            print(canonical_json(report), flush=True)
            raise SystemExit(0 if report["decision"] == "accepted" else 1)
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    main()
