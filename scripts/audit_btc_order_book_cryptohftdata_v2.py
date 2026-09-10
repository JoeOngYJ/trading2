#!/usr/bin/env python3
"""Successor CryptoHFTData audit using received-time partition semantics."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import httpx
import numpy as np
import pyarrow as pa

import scripts.audit_btc_order_book_cryptohftdata as v1
from trading_platform.research_program import canonical_json, sha256_file


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = (
    REPO_ROOT
    / "config/experiments/btc-order-book-cryptohftdata-hour-day-audit-v2.json"
)
CONTRACT_SCHEMA = "btc-order-book-cryptohftdata-hour-day-audit-contract-v2"
SOURCE_SCHEMA = "btc-order-book-cryptohftdata-source-manifest-v2"
REPORT_SCHEMA = "btc-order-book-cryptohftdata-audit-report-v2"
MANIFEST_SCHEMA = "btc-order-book-cryptohftdata-audit-manifest-v2"


def load_canonical(path: Path, label: str) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    payload = json.loads(raw)
    if not isinstance(payload, dict) or raw != canonical_json(payload):
        raise ValueError(f"{label} is not canonical JSON")
    return payload


def require_contract(path: Path) -> dict[str, Any]:
    if path.resolve(strict=True) != DEFAULT_CONTRACT.resolve(strict=True):
        raise ValueError("exact frozen CryptoHFTData v2 contract is required")
    contract = load_canonical(path, "CryptoHFTData v2 contract")
    if contract.get("schema_version") != CONTRACT_SCHEMA or contract.get("status") != "frozen":
        raise ValueError("unsupported or unfrozen CryptoHFTData v2 contract")
    if (
        contract.get("replacement_of") != "btc-order-book-cryptohftdata-hour-day-audit-v1"
        or contract["decision_rule"].get("partition_clock") != "received_time"
        or contract["decision_rule"].get("maximum_received_minus_exchange_time_ms") != 5000
        or contract["boundaries"].get("sealed_2026_access_allowed") is not False
        or contract["boundaries"]["exact_partition_date"].startswith("2026-")
        or contract["boundaries"]["full_day_hours_utc"] != list(range(24))
    ):
        raise ValueError("v2 successor boundary is not frozen as declared")
    return contract


def artifact_root(contract: dict[str, Any], *, must_exist: bool) -> Path:
    root = (REPO_ROOT / contract["output"]["artifact_root"]).resolve(strict=must_exist)
    root.relative_to(REPO_ROOT.resolve(strict=True))
    if root.is_symlink():
        raise ValueError("symlinked v2 audit root is prohibited")
    return root


def write_once(path: Path, payload: str) -> None:
    if path.exists():
        raise ValueError(f"refusing to overwrite v2 audit artifact: {path}")
    path.write_text(payload, encoding="utf-8")


def verify_predecessor(contract: dict[str, Any]) -> list[dict[str, Any]]:
    inherited = contract["inputs"]["inherited_pilot"]
    v1_contract = REPO_ROOT / "config/experiments/btc-order-book-cryptohftdata-hour-day-audit-v1.json"
    v1_source = (
        REPO_ROOT
        / "artifacts/agent-level-experiment/btc-order-book/provider-audits/cryptohftdata-hour-day-v1/pilot/source-manifest.json"
    )
    v1_manifest = v1_source.with_name("hour-manifest.json")
    if (
        sha256_file(v1_contract) != inherited["predecessor_contract_sha256"]
        or sha256_file(v1_source) != inherited["predecessor_source_manifest_sha256"]
        or sha256_file(v1_manifest) != inherited["predecessor_hour_manifest_sha256"]
    ):
        raise ValueError("immutable predecessor contract or manifest changed")
    observed: list[dict[str, Any]] = []
    for spec in inherited["objects"]:
        parquet = (REPO_ROOT / spec["parquet_file"]).resolve(strict=True)
        compressed = (REPO_ROOT / spec["compressed_file"]).resolve(strict=True)
        parquet.relative_to(REPO_ROOT.resolve(strict=True))
        compressed.relative_to(REPO_ROOT.resolve(strict=True))
        if parquet.is_symlink() or compressed.is_symlink():
            raise ValueError("symlinked predecessor artifact is prohibited")
        if (
            parquet.stat().st_size != spec["parquet_bytes"]
            or compressed.stat().st_size != spec["compressed_bytes"]
            or sha256_file(parquet) != spec["parquet_sha256"]
            or sha256_file(compressed) != spec["compressed_sha256"]
        ):
            raise ValueError("predecessor provider bytes changed")
        observed.append(dict(spec))
    return observed


def initialize_hour(contract: dict[str, Any]) -> dict[str, Any]:
    objects = verify_predecessor(contract)
    root = artifact_root(contract, must_exist=False)
    root.mkdir(parents=True, exist_ok=True)
    pilot = root / "pilot"
    pilot.mkdir(exist_ok=False)
    source = {
        "audit_id": contract["audit_id"],
        "contract_sha256": sha256_file(DEFAULT_CONTRACT),
        "objects": objects,
        "phase": "pilot",
        "predecessor_hour_manifest_sha256": contract["inputs"]["inherited_pilot"]["predecessor_hour_manifest_sha256"],
        "reused_checksum_identical_predecessor_bytes": True,
        "schema_version": SOURCE_SCHEMA,
    }
    write_once(pilot / "source-manifest.json", canonical_json(source))
    return source


def _common_time_checks_v2(
    table: pa.Table, date: str, hour: int
) -> tuple[np.ndarray, np.ndarray, dict[str, int]]:
    received = v1.timestamp_ns(table["received_time"])
    event = v1.timestamp_ns(table["event_time"])
    start_ns, end_ns = v1._partition_bounds(date, hour)
    if not len(received) or len(received) != len(event):
        raise ValueError("timestamp columns are empty or misaligned")
    if received.min() < start_ns or received.max() >= end_ns:
        raise ValueError("received_time crosses the frozen UTC hour")
    if np.any(np.diff(received) < 0):
        raise ValueError("received_time is not non-decreasing")
    latency = received - event
    if np.any(latency < 0):
        raise ValueError("received_time precedes exchange event_time")
    maximum_latency_ns = 5_000_000_000
    if latency.max() > maximum_latency_ns:
        raise ValueError("received-minus-event latency exceeds the frozen five-second ceiling")
    if event.max() >= end_ns:
        raise ValueError("exchange event_time reaches beyond the receipt partition")
    return received, event, {
        "max_event_time_ns": int(event.max()),
        "max_received_minus_event_ns": int(latency.max()),
        "max_received_time_ns": int(received.max()),
        "min_event_time_ns": int(event.min()),
        "min_received_minus_event_ns": int(latency.min()),
        "min_received_time_ns": int(received.min()),
    }


def inspect_file(path: Path, contract: dict[str, Any], hour: int, data_type: str) -> dict[str, Any]:
    original = v1._common_time_checks
    v1._common_time_checks = _common_time_checks_v2
    try:
        return (
            v1.inspect_orderbook(path, contract, hour)
            if data_type == "orderbook"
            else v1.inspect_trades(path, contract, hour)
        )
    finally:
        v1._common_time_checks = original


def _pilot_passed(contract: dict[str, Any]) -> bool:
    try:
        report_path = artifact_root(contract, must_exist=True) / "pilot/hour-audit-report.json"
    except FileNotFoundError:
        return False
    if not report_path.exists():
        return False
    report = load_canonical(report_path, "v2 pilot report")
    return (
        report.get("audit_id") == contract["audit_id"]
        and report.get("contract_sha256") == sha256_file(DEFAULT_CONTRACT)
        and report.get("decision") == "hour_pass"
    )


def download_day(contract: dict[str, Any]) -> dict[str, Any]:
    if not _pilot_passed(contract):
        raise ValueError("full-day download is prohibited until the v2 pilot hour passes")
    root = artifact_root(contract, must_exist=True)
    destination = root / "day"
    destination.mkdir(exist_ok=False)
    hours = [hour for hour in range(24) if hour != contract["boundaries"]["pilot_hour_utc"]]
    records: list[dict[str, Any]] = []
    timeout = httpx.Timeout(connect=20, read=180, write=30, pool=20)
    with httpx.Client(timeout=timeout) as client:
        for hour in hours:
            for data_type in contract["inputs"]["data_types"]:
                records.append(v1._download_one(client, contract, destination, hour, data_type))
    source = {
        "audit_id": contract["audit_id"],
        "contract_sha256": sha256_file(DEFAULT_CONTRACT),
        "objects": records,
        "phase": "day",
        "retrieved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "schema_version": SOURCE_SCHEMA,
    }
    write_once(destination / "source-manifest.json", canonical_json(source))
    return source


def _load_source(contract: dict[str, Any], phase: str) -> list[dict[str, Any]]:
    root = artifact_root(contract, must_exist=True)
    source = load_canonical(root / phase / "source-manifest.json", f"v2 {phase} source manifest")
    if (
        source.get("schema_version") != SOURCE_SCHEMA
        or source.get("audit_id") != contract["audit_id"]
        or source.get("contract_sha256") != sha256_file(DEFAULT_CONTRACT)
        or source.get("phase") != phase
    ):
        raise ValueError("v2 source manifest does not match the frozen audit")
    return source["objects"]


def _records(contract: dict[str, Any], phase: str) -> Iterable[tuple[str, dict[str, Any]]]:
    yield from (("pilot", item) for item in _load_source(contract, "pilot"))
    if phase == "day":
        if not _pilot_passed(contract):
            raise ValueError("day audit is prohibited until the v2 pilot hour passes")
        yield from (("day", item) for item in _load_source(contract, "day"))


def _verify_record(contract: dict[str, Any], phase: str, record: dict[str, Any]) -> Path:
    if phase == "pilot":
        parquet = (REPO_ROOT / record["parquet_file"]).resolve(strict=True)
        compressed = (REPO_ROOT / record["compressed_file"]).resolve(strict=True)
    else:
        root = artifact_root(contract, must_exist=True) / "day"
        parquet = (root / record["parquet_file"]).resolve(strict=True)
        compressed = (root / record["compressed_file"]).resolve(strict=True)
    parquet.relative_to(REPO_ROOT.resolve(strict=True))
    compressed.relative_to(REPO_ROOT.resolve(strict=True))
    if (
        parquet.stat().st_size != record["parquet_bytes"]
        or compressed.stat().st_size != record["compressed_bytes"]
        or sha256_file(parquet) != record["parquet_sha256"]
        or sha256_file(compressed) != record["compressed_sha256"]
    ):
        raise ValueError("v2 provider artifact checksum mismatch")
    return parquet


def _artifact_entry(path: Path) -> dict[str, Any]:
    return {"bytes": path.stat().st_size, "sha256": sha256_file(path)}


def audit_phase(contract: dict[str, Any], phase: str) -> dict[str, Any]:
    root = artifact_root(contract, must_exist=True)
    records = list(_records(contract, phase))
    if len(records) != (2 if phase == "pilot" else 48):
        raise ValueError("v2 source manifest does not contain the frozen object count")
    inspections: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for source_phase, record in records:
        hour = int(record["hour_utc"])
        data_type = record["data_type"]
        try:
            path = _verify_record(contract, source_phase, record)
            inspection = inspect_file(path, contract, hour, data_type)
            inspection["source_phase"] = source_phase
            inspections.append(inspection)
        except (ValueError, OSError, pa.ArrowException) as exc:
            errors.append({"data_type": data_type, "error": str(exc), "hour_utc": hour})
    by_hour: dict[int, dict[str, dict[str, Any]]] = {}
    for item in inspections:
        by_hour.setdefault(item["hour_utc"], {})[item["data_type"]] = item
    if phase == "day" and not errors:
        for hour in range(24):
            pair = by_hour.get(hour, {})
            if set(pair) != {"orderbook", "trades"}:
                errors.append({"data_type": "pair", "error": "missing hourly pair", "hour_utc": hour})
                continue
            book, trades = pair["orderbook"], pair["trades"]
            if max(book["min_received_time_ns"], trades["min_received_time_ns"]) > min(
                book["max_received_time_ns"], trades["max_received_time_ns"]
            ):
                errors.append(
                    {"data_type": "pair", "error": "trade/orderbook receipt ranges do not overlap", "hour_utc": hour}
                )
            if book["max_group_gap_ns"] > 1_000_000_000:
                errors.append(
                    {"data_type": "orderbook", "error": "unexplained received-time gap exceeds one second", "hour_utc": hour}
                )
        for hour in range(23):
            if by_hour[hour + 1]["trades"]["first_trade_id"] != by_hour[hour]["trades"]["last_trade_id"] + 1:
                errors.append(
                    {"data_type": "trades", "error": "cross-hour trade-ID discontinuity", "hour_utc": hour + 1}
                )
    accepted = not errors
    decision = (
        "hour_pass" if phase == "pilot" and accepted else
        "hour_reject" if phase == "pilot" else
        "day_pass" if accepted else
        "day_reject"
    )
    report = {
        "active_or_partial_ob0_accessed": False,
        "audit_id": contract["audit_id"],
        "contract_sha256": sha256_file(DEFAULT_CONTRACT),
        "decision": decision,
        "economic_metrics_computed": False,
        "errors": sorted(errors, key=lambda item: (item["hour_utc"], item["data_type"], item["error"])),
        "features_labels_forecasts_or_pnl_computed": False,
        "inspections": sorted(inspections, key=lambda item: (item["hour_utc"], item["data_type"])),
        "normalized_source_is_exchange_native_raw": False,
        "partition_clock": "received_time",
        "phase": phase,
        "provider_fixture_accepted": accepted,
        "schema_version": REPORT_SCHEMA,
        "sealed_2026_accessed": False,
    }
    report_name = "hour-audit-report.json" if phase == "pilot" else "day-audit-report.json"
    report_path = root / phase / report_name
    write_once(report_path, canonical_json(report))
    artifacts: dict[str, dict[str, Any]] = {}
    for path in [DEFAULT_CONTRACT, Path(__file__), root / "pilot/source-manifest.json", report_path]:
        artifacts[str(path.relative_to(REPO_ROOT))] = _artifact_entry(path)
    for record in _load_source(contract, "pilot"):
        for key in ("compressed_file", "parquet_file"):
            path = REPO_ROOT / record[key]
            artifacts[str(path.relative_to(REPO_ROOT))] = _artifact_entry(path)
    if phase == "day":
        day_source = root / "day/source-manifest.json"
        artifacts[str(day_source.relative_to(REPO_ROOT))] = _artifact_entry(day_source)
        for record in _load_source(contract, "day"):
            for key in ("compressed_file", "parquet_file"):
                path = root / "day" / record[key]
                artifacts[str(path.relative_to(REPO_ROOT))] = _artifact_entry(path)
    manifest = {
        "artifacts": artifacts,
        "audit_id": contract["audit_id"],
        "contract_sha256": sha256_file(DEFAULT_CONTRACT),
        "decision": decision,
        "economic_metrics_computed": False,
        "phase": phase,
        "provider_fixture_accepted": accepted,
        "schema_version": MANIFEST_SCHEMA,
        "sealed_2026_accessed": False,
    }
    manifest_name = "hour-manifest.json" if phase == "pilot" else "day-manifest.json"
    write_once(root / phase / manifest_name, canonical_json(manifest))
    return report


def verify_phase(contract: dict[str, Any], phase: str) -> dict[str, Any]:
    root = artifact_root(contract, must_exist=True)
    name = "hour-manifest.json" if phase == "pilot" else "day-manifest.json"
    path = root / phase / name
    manifest = load_canonical(path, f"v2 {phase} manifest")
    if (
        manifest.get("schema_version") != MANIFEST_SCHEMA
        or manifest.get("contract_sha256") != sha256_file(DEFAULT_CONTRACT)
        or manifest.get("phase") != phase
    ):
        raise ValueError("v2 audit manifest does not match the frozen phase")
    for name, expected in manifest["artifacts"].items():
        artifact = (REPO_ROOT / name).resolve(strict=True)
        artifact.relative_to(REPO_ROOT.resolve(strict=True))
        if artifact.stat().st_size != expected["bytes"] or sha256_file(artifact) != expected["sha256"]:
            raise ValueError(f"v2 audit artifact mismatch: {name}")
    return {
        "decision": manifest["decision"],
        "manifest_sha256": sha256_file(path),
        "phase": phase,
        "verified_artifacts": len(manifest["artifacts"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=("initialize-hour", "audit-hour", "download-day", "audit-day", "verify-hour", "verify-day"),
    )
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    args = parser.parse_args()
    contract = require_contract(args.contract)
    if args.command == "initialize-hour":
        source = initialize_hour(contract)
        summary = {"inherited_objects": len(source["objects"]), "phase": "pilot"}
    elif args.command == "audit-hour":
        report = audit_phase(contract, "pilot")
        summary = {"decision": report["decision"], "errors": len(report["errors"]), "phase": "pilot"}
    elif args.command == "download-day":
        source = download_day(contract)
        summary = {"downloaded_objects": len(source["objects"]), "phase": "day"}
    elif args.command == "audit-day":
        report = audit_phase(contract, "day")
        summary = {"decision": report["decision"], "errors": len(report["errors"]), "phase": "day"}
    elif args.command == "verify-hour":
        summary = verify_phase(contract, "pilot")
    else:
        summary = verify_phase(contract, "day")
    print(canonical_json(summary), end="")


if __name__ == "__main__":
    main()
