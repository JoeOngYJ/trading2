#!/usr/bin/env python3
"""Qualify three frozen public Crypto Lake files without computing market features."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from trading_platform.research_program import canonical_json, sha256_file


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = (
    REPO_ROOT / "config/experiments/btc-order-book-cryptolake-sample-audit-v1.json"
)
CONTRACT_SCHEMA = "btc-order-book-provider-sample-audit-contract-v1"


def load_canonical(path: Path, label: str) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    payload = json.loads(raw)
    if not isinstance(payload, dict) or raw != canonical_json(payload):
        raise ValueError(f"{label} is not canonical JSON")
    return payload


def require_contract(path: Path) -> dict[str, Any]:
    if path.resolve(strict=True) != DEFAULT_CONTRACT.resolve(strict=True):
        raise ValueError("exact frozen Crypto Lake sample-audit contract is required")
    contract = load_canonical(path, "sample-audit contract")
    if contract.get("schema_version") != CONTRACT_SCHEMA or contract.get("status") != "frozen":
        raise ValueError("unsupported or unfrozen sample-audit contract")
    if contract["boundaries"].get("sealed_2026_access_allowed") is not False:
        raise ValueError("sample audit must prohibit sealed-2026 access")
    allowed_dates = set(contract["boundaries"]["allowed_partition_dates"])
    if not allowed_dates or any(value.startswith("2026-") for value in allowed_dates):
        raise ValueError("sample audit contains a prohibited 2026 partition")
    filenames: set[str] = set()
    for item in contract["inputs"]["objects"]:
        if item["partition_date"] not in allowed_dates:
            raise ValueError("object falls outside the frozen partition dates")
        if item["filename"] in filenames or Path(item["filename"]).name != item["filename"]:
            raise ValueError("invalid or duplicate sample filename")
        filenames.add(item["filename"])
        validate_url(contract, item["url"])
    return contract


def validate_url(contract: dict[str, Any], raw_url: str) -> None:
    parsed = urlparse(raw_url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != contract["inputs"]["allowed_host"]
        or not parsed.path.startswith(contract["inputs"]["allowed_path_prefix"])
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(f"sample URL violates the frozen allowlist: {raw_url}")
    if "/dt=2026-" in parsed.path:
        raise ValueError("sealed-2026 sample URL is prohibited")


def artifact_root(contract: dict[str, Any], *, must_exist: bool) -> Path:
    root = (REPO_ROOT / contract["output"]["artifact_root"]).resolve(
        strict=must_exist
    )
    root.relative_to(REPO_ROOT.resolve(strict=True))
    if root.is_symlink():
        raise ValueError("symlinked audit root is prohibited")
    return root


def write_once(path: Path, payload: str) -> None:
    if path.exists():
        raise ValueError(f"refusing to overwrite audit artifact: {path}")
    path.write_text(payload, encoding="utf-8")


def _etag(headers: httpx.Headers) -> str:
    return headers.get("etag", "").strip('"')


def download_samples(contract: dict[str, Any]) -> dict[str, Any]:
    root = artifact_root(contract, must_exist=False)
    root.mkdir(parents=True, exist_ok=False)
    raw_dir = root / "raw"
    raw_dir.mkdir()
    records: list[dict[str, Any]] = []
    timeout = httpx.Timeout(connect=20, read=120, write=30, pool=20)
    try:
        with httpx.Client(follow_redirects=False, timeout=timeout) as client:
            for item in contract["inputs"]["objects"]:
                validate_url(contract, item["url"])
                head = client.head(item["url"])
                head.raise_for_status()
                observed_bytes = int(head.headers.get("content-length", "-1"))
                observed_etag = _etag(head.headers)
                if observed_bytes != item["expected_bytes"]:
                    raise ValueError(f"remote size changed: {item['filename']}")
                if observed_etag != item["expected_etag"]:
                    raise ValueError(f"remote ETag changed: {item['filename']}")
                target = raw_dir / item["filename"]
                partial = target.with_suffix(target.suffix + ".part")
                digest = hashlib.sha256()
                total = 0
                with client.stream("GET", item["url"]) as response:
                    response.raise_for_status()
                    with partial.open("xb") as handle:
                        for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                            handle.write(chunk)
                            digest.update(chunk)
                            total += len(chunk)
                        handle.flush()
                        os.fsync(handle.fileno())
                if total != item["expected_bytes"]:
                    raise ValueError(f"download size mismatch: {item['filename']}")
                os.replace(partial, target)
                records.append(
                    {
                        "bytes": total,
                        "dataset": item["dataset"],
                        "etag": observed_etag,
                        "file": str(target.relative_to(root)),
                        "partition_date": item["partition_date"],
                        "sha256": digest.hexdigest(),
                        "url": item["url"],
                    }
                )
    except Exception:
        for partial in raw_dir.glob("*.part"):
            partial.unlink()
        raise
    manifest = {
        "audit_id": contract["audit_id"],
        "contract_sha256": sha256_file(DEFAULT_CONTRACT),
        "objects": records,
        "provider_terms": contract["inputs"]["provider_terms"],
        "retrieved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "schema_version": "btc-order-book-provider-source-manifest-v1",
    }
    source_path = root / "source-manifest.json"
    write_once(source_path, canonical_json(manifest))
    return manifest


def _timestamp_ns(array: pa.Array) -> np.ndarray:
    values = np.asarray(array.cast(pa.int64()).to_numpy(zero_copy_only=False), dtype=np.int64)
    if pa.types.is_timestamp(array.type):
        factor = {"s": 1_000_000_000, "ms": 1_000_000, "us": 1_000, "ns": 1}[
            array.type.unit
        ]
        values = values * factor
    return values


def _numeric(array: pa.Array) -> np.ndarray:
    return np.asarray(array.to_numpy(zero_copy_only=False), dtype=np.float64)


def _unique_text(array: pa.Array) -> set[str]:
    return {str(value) for value in pc.unique(array).to_pylist() if value is not None}


def parquet_schema_summary(path: Path, spec: dict[str, Any]) -> dict[str, Any]:
    parquet = pq.ParquetFile(path)
    metadata = {
        key.decode("utf-8", errors="replace"): value.decode("utf-8", errors="replace")
        for key, value in (parquet.schema_arrow.metadata or {}).items()
    }
    return {
        "columns": sorted(parquet.schema_arrow.names),
        "dataset": spec["dataset"],
        "file": spec["filename"],
        "partition_date": spec["partition_date"],
        "row_count": parquet.metadata.num_rows,
        "row_groups": parquet.num_row_groups,
        "schema": str(parquet.schema_arrow),
        "schema_metadata": metadata,
    }


def inspect_parquet(path: Path, spec: dict[str, Any], venue: str, symbol: str) -> dict[str, Any]:
    parquet = pq.ParquetFile(path)
    columns = set(parquet.schema_arrow.names)
    missing = sorted(set(spec["required_columns"]) - columns)
    if missing:
        raise ValueError(f"missing required columns: {missing}")
    selected = list(spec["required_columns"])
    row_count = 0
    observed_venues: set[str] = set()
    observed_symbols: set[str] = set()
    observed_sides: set[str] = set()
    minimum_received: int | None = None
    maximum_received: int | None = None
    previous_received: int | None = None
    previous_sequence: int | None = None
    previous_trade_id: int | None = None
    partition_start = int(
        datetime.fromisoformat(spec["partition_date"])
        .replace(tzinfo=timezone.utc)
        .timestamp()
    ) * 1_000_000_000
    partition_end = partition_start + 86_400 * 1_000_000_000

    for batch in parquet.iter_batches(batch_size=262_144, columns=selected):
        row_count += batch.num_rows
        by_name = {name: batch.column(index) for index, name in enumerate(selected)}
        null_columns = [name for name, array in by_name.items() if array.null_count]
        if null_columns:
            raise ValueError(f"required columns contain nulls: {sorted(null_columns)}")
        received = _timestamp_ns(by_name["received_time"])
        if len(received):
            if received.min() < partition_start or received.max() >= partition_end:
                raise ValueError("received_time crosses the declared UTC partition")
            if np.any(np.diff(received) < 0) or (
                previous_received is not None and int(received[0]) < previous_received
            ):
                raise ValueError("received_time is not non-decreasing")
            previous_received = int(received[-1])
            minimum_received = int(received.min()) if minimum_received is None else min(
                minimum_received, int(received.min())
            )
            maximum_received = int(received.max()) if maximum_received is None else max(
                maximum_received, int(received.max())
            )
        sequence = np.asarray(
            by_name["sequence_number"].cast(pa.int64()).to_numpy(zero_copy_only=False),
            dtype=np.int64,
        ) if "sequence_number" in by_name else None
        if sequence is not None and len(sequence):
            if np.any(np.diff(sequence) < 0) or (
                previous_sequence is not None and int(sequence[0]) < previous_sequence
            ):
                raise ValueError("sequence_number is not non-decreasing")
            previous_sequence = int(sequence[-1])
        if "trade_id" in by_name:
            trade_ids = np.asarray(
                by_name["trade_id"].cast(pa.int64()).to_numpy(zero_copy_only=False),
                dtype=np.int64,
            )
            if len(trade_ids) and (
                np.any(np.diff(trade_ids) <= 0)
                or (previous_trade_id is not None and int(trade_ids[0]) <= previous_trade_id)
            ):
                raise ValueError("trade_id is not strictly increasing")
            if len(trade_ids):
                previous_trade_id = int(trade_ids[-1])
        observed_venues.update(_unique_text(by_name["exchange"]))
        observed_symbols.update(_unique_text(by_name["symbol"]))
        if "side" in by_name:
            observed_sides.update(_unique_text(by_name["side"]))
        if "origin_time" in by_name:
            origin = _timestamp_ns(by_name["origin_time"])
            if len(origin) and (origin.min() < partition_start or origin.max() >= partition_end):
                raise ValueError("origin_time crosses the declared UTC partition")
        if spec["dataset"] == "book":
            bid = _numeric(by_name["bid_0_price"])
            ask = _numeric(by_name["ask_0_price"])
            bid_size = _numeric(by_name["bid_0_size"])
            ask_size = _numeric(by_name["ask_0_size"])
            if (
                not np.all(np.isfinite(bid))
                or not np.all(np.isfinite(ask))
                or not np.all(np.isfinite(bid_size))
                or not np.all(np.isfinite(ask_size))
                or np.any(bid <= 0)
                or np.any(ask <= 0)
                or np.any(bid_size < 0)
                or np.any(ask_size < 0)
                or np.any(bid >= ask)
            ):
                raise ValueError("invalid or crossed snapshot top of book")
        elif spec["dataset"] == "trades":
            price = _numeric(by_name["price"])
            quantity = _numeric(by_name["quantity"])
            if (
                not np.all(np.isfinite(price))
                or not np.all(np.isfinite(quantity))
                or np.any(price <= 0)
                or np.any(quantity <= 0)
            ):
                raise ValueError("invalid trade price or quantity")
        elif spec["dataset"] == "book_delta_v2":
            price = _numeric(by_name["price"])
            size = _numeric(by_name["size"])
            if (
                not np.all(np.isfinite(price))
                or not np.all(np.isfinite(size))
                or np.any(price <= 0)
                or np.any(size < 0)
            ):
                raise ValueError("invalid delta price or size")

    if row_count <= 0:
        raise ValueError("empty parquet sample")
    if observed_venues != {venue} or observed_symbols != {symbol}:
        raise ValueError("venue or symbol identity mismatch")
    if spec["dataset"] == "trades" and observed_sides != {"buy", "sell"}:
        raise ValueError("trade side domain mismatch")
    result = parquet_schema_summary(path, spec)
    result.update({
        "max_received_time_ns": maximum_received,
        "min_received_time_ns": minimum_received,
        "sequence_non_decreasing": True if "sequence_number" in selected else None,
        "symbol_values": sorted(observed_symbols),
        "venue_values": sorted(observed_venues),
    })
    return result


def raw_replay_missing(inspections: list[dict[str, Any]]) -> list[str]:
    by_dataset = {item["dataset"]: set(item["columns"]) for item in inspections}
    delta = by_dataset.get("book_delta_v2", set())
    missing: list[str] = []
    for field, label in (
        ("first_update_id", "first_update_id_U"),
        ("final_update_id", "final_update_id_u"),
        ("origin_time", "exchange_event_timestamp_on_deltas"),
        ("event_type", "exchange_native_message_or_snapshot_type"),
    ):
        if field not in delta:
            missing.append(label)
    partitions: dict[str, set[str]] = {}
    for item in inspections:
        partitions.setdefault(item["partition_date"], set()).add(item["dataset"])
    if not any({"book", "book_delta_v2", "trades"} <= datasets for datasets in partitions.values()):
        missing.append("same_partition_snapshot_delta_and_trade_bundle")
    missing.extend(
        [
            "gap_reconnect_resubscribe_parse_clock_and_drop_incident_log",
            "raw_aggregate_trade_message_boundaries",
        ]
    )
    if any(
        item.get("schema_metadata", {}).get("contains_gaps", "").lower() == "yes"
        for item in inspections
    ):
        missing.append("provider_declares_unlocated_gaps")
    return sorted(set(missing))


def audit_samples(contract: dict[str, Any]) -> dict[str, Any]:
    root = artifact_root(contract, must_exist=True)
    source_path = root / "source-manifest.json"
    source = load_canonical(source_path, "provider source manifest")
    if (
        source.get("audit_id") != contract["audit_id"]
        or source.get("contract_sha256") != sha256_file(DEFAULT_CONTRACT)
        or source.get("schema_version") != "btc-order-book-provider-source-manifest-v1"
    ):
        raise ValueError("provider source manifest does not match the frozen audit")
    source_by_dataset = {item["dataset"]: item for item in source["objects"]}
    inspections: list[dict[str, Any]] = []
    object_errors: list[dict[str, str]] = []
    for spec in contract["inputs"]["objects"]:
        record = source_by_dataset.get(spec["dataset"])
        if record is None or record["partition_date"] != spec["partition_date"]:
            raise ValueError("source manifest object mismatch")
        path = (root / record["file"]).resolve(strict=True)
        path.relative_to(root)
        if path.is_symlink() or not path.is_file():
            raise ValueError("invalid provider sample path")
        if path.stat().st_size != spec["expected_bytes"] or record["bytes"] != spec["expected_bytes"]:
            raise ValueError("provider sample byte count mismatch")
        if record["etag"] != spec["expected_etag"] or sha256_file(path) != record["sha256"]:
            raise ValueError("provider sample checksum or ETag mismatch")
        try:
            inspections.append(
                inspect_parquet(
                    path,
                    spec,
                    contract["inputs"]["venue"],
                    contract["inputs"]["symbol"],
                )
            )
        except ValueError as exc:
            summary = parquet_schema_summary(path, spec)
            summary["validation_error"] = str(exc)
            inspections.append(summary)
            object_errors.append({"file": spec["filename"], "error": str(exc)})
    missing = raw_replay_missing(inspections)
    adapter_accepted = not object_errors
    report = {
        "active_or_partial_ob0_accessed": False,
        "adapter_fixture_accepted": adapter_accepted,
        "audit_id": contract["audit_id"],
        "contract_sha256": sha256_file(DEFAULT_CONTRACT),
        "decision": (
            "reject"
            if not adapter_accepted
            else "adapter_fixture_only" if missing else "raw_replay_contract_accepted"
        ),
        "economic_metrics_computed": False,
        "features_labels_forecasts_or_pnl_computed": False,
        "inspections": inspections,
        "object_errors": object_errors,
        "raw_replay_contract_accepted": not missing,
        "raw_replay_missing_requirements": missing,
        "schema_version": "btc-order-book-provider-sample-audit-report-v1",
        "sealed_2026_accessed": False,
    }
    report_path = root / "audit-report.json"
    write_once(report_path, canonical_json(report))
    artifacts: dict[str, dict[str, Any]] = {}
    for path in [DEFAULT_CONTRACT, Path(__file__), source_path, report_path]:
        artifacts[str(path.relative_to(REPO_ROOT))] = {
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
    for record in source["objects"]:
        path = root / record["file"]
        artifacts[str(path.relative_to(REPO_ROOT))] = {
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
    manifest = {
        "adapter_fixture_accepted": report["adapter_fixture_accepted"],
        "artifacts": artifacts,
        "audit_id": contract["audit_id"],
        "contract_sha256": sha256_file(DEFAULT_CONTRACT),
        "decision": report["decision"],
        "economic_metrics_computed": False,
        "raw_replay_contract_accepted": report["raw_replay_contract_accepted"],
        "schema_version": "btc-order-book-provider-sample-audit-manifest-v1",
        "sealed_2026_accessed": False,
    }
    manifest_path = root / "manifest.json"
    write_once(manifest_path, canonical_json(manifest))
    return report


def verify_audit(contract: dict[str, Any]) -> dict[str, Any]:
    root = artifact_root(contract, must_exist=True)
    manifest_path = root / "manifest.json"
    manifest = load_canonical(manifest_path, "sample-audit manifest")
    if manifest.get("contract_sha256") != sha256_file(DEFAULT_CONTRACT):
        raise ValueError("audit manifest contract mismatch")
    for name, expected in manifest["artifacts"].items():
        path = (REPO_ROOT / name).resolve(strict=True)
        path.relative_to(REPO_ROOT)
        if path.stat().st_size != expected["bytes"] or sha256_file(path) != expected["sha256"]:
            raise ValueError(f"audit artifact mismatch: {name}")
    return {
        "decision": manifest["decision"],
        "manifest_sha256": sha256_file(manifest_path),
        "verified_artifacts": len(manifest["artifacts"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("download", "audit", "verify"))
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    args = parser.parse_args()
    contract = require_contract(args.contract)
    if args.command == "download":
        result = download_samples(contract)
        summary = {"downloaded_objects": len(result["objects"])}
    elif args.command == "audit":
        result = audit_samples(contract)
        summary = {
            "adapter_fixture_accepted": result["adapter_fixture_accepted"],
            "decision": result["decision"],
            "raw_replay_contract_accepted": result["raw_replay_contract_accepted"],
        }
    else:
        summary = verify_audit(contract)
    print(canonical_json(summary), end="")


if __name__ == "__main__":
    main()
