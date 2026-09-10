#!/usr/bin/env python3
"""Bounded, write-once CryptoHFTData source qualification without market research."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from trading_platform.research_program import canonical_json, sha256_file


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = (
    REPO_ROOT
    / "config/experiments/btc-order-book-cryptohftdata-hour-day-audit-v1.json"
)
CONTRACT_SCHEMA = "btc-order-book-cryptohftdata-hour-day-audit-contract-v1"
SOURCE_SCHEMA = "btc-order-book-cryptohftdata-source-manifest-v1"
REPORT_SCHEMA = "btc-order-book-cryptohftdata-audit-report-v1"
MANIFEST_SCHEMA = "btc-order-book-cryptohftdata-audit-manifest-v1"


def load_canonical(path: Path, label: str) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    payload = json.loads(raw)
    if not isinstance(payload, dict) or raw != canonical_json(payload):
        raise ValueError(f"{label} is not canonical JSON")
    return payload


def require_contract(path: Path) -> dict[str, Any]:
    if path.resolve(strict=True) != DEFAULT_CONTRACT.resolve(strict=True):
        raise ValueError("exact frozen CryptoHFTData audit contract is required")
    contract = load_canonical(path, "CryptoHFTData audit contract")
    if contract.get("schema_version") != CONTRACT_SCHEMA or contract.get("status") != "frozen":
        raise ValueError("unsupported or unfrozen CryptoHFTData audit contract")
    boundaries = contract["boundaries"]
    date = boundaries["exact_partition_date"]
    hours = boundaries["full_day_hours_utc"]
    if (
        boundaries.get("sealed_2026_access_allowed") is not False
        or str(date).startswith("2026-")
        or hours != list(range(24))
        or boundaries["pilot_hour_utc"] not in hours
    ):
        raise ValueError("audit boundary is not the exact frozen pre-2026 UTC day")
    if contract["inputs"]["data_types"] != ["orderbook", "trades"]:
        raise ValueError("the frozen orderbook/trades pair is required")
    if contract["isolation"].get("active_ob0_access_allowed") is not False:
        raise ValueError("active or partial OB0 access must remain prohibited")
    return contract


def object_key(contract: dict[str, Any], hour: int, data_type: str) -> str:
    if hour not in contract["boundaries"]["full_day_hours_utc"]:
        raise ValueError("hour falls outside the frozen day")
    if data_type not in contract["inputs"]["data_types"]:
        raise ValueError("data type falls outside the frozen pair")
    key = contract["inputs"]["file_template"].format(
        date=contract["boundaries"]["exact_partition_date"],
        hour=hour,
        data_type=data_type,
    )
    if "2026-" in key or ".." in key or key.startswith("/"):
        raise ValueError("unsafe or sealed object key")
    return key


def request_url(contract: dict[str, Any], key: str) -> str:
    return (
        f"https://{contract['inputs']['allowed_download_api_host']}"
        f"{contract['inputs']['allowed_download_api_path']}?{urlencode({'file': key})}"
    )


def validate_request_url(contract: dict[str, Any], raw_url: str) -> None:
    parsed = urlparse(raw_url)
    expected_keys = {
        object_key(contract, hour, data_type)
        for hour in contract["boundaries"]["full_day_hours_utc"]
        for data_type in contract["inputs"]["data_types"]
    }
    query = parse_qs(parsed.query, strict_parsing=True)
    if (
        parsed.scheme != "https"
        or parsed.hostname != contract["inputs"]["allowed_download_api_host"]
        or parsed.path != contract["inputs"]["allowed_download_api_path"]
        or parsed.fragment
        or set(query) != {"file"}
        or len(query["file"]) != 1
        or query["file"][0] not in expected_keys
    ):
        raise ValueError(f"provider URL violates the frozen allowlist: {raw_url}")
    if "2026-" in query["file"][0]:
        raise ValueError("sealed-2026 provider URL is prohibited")


def validate_redirect_url(contract: dict[str, Any], raw_url: str, key: str) -> None:
    parsed = urlparse(raw_url)
    expected_path = f"/cryptohftdata-processed/{key}.zst"
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or not parsed.hostname.endswith(contract["inputs"]["allowed_redirect_host_suffix"])
        or parsed.path != expected_path
        or not parsed.query
        or parsed.fragment
    ):
        raise ValueError("signed storage redirect violates the frozen allowlist")
    if "2026-" in parsed.path:
        raise ValueError("sealed-2026 storage redirect is prohibited")


def artifact_root(contract: dict[str, Any], *, must_exist: bool) -> Path:
    root = (REPO_ROOT / contract["output"]["artifact_root"]).resolve(strict=must_exist)
    root.relative_to(REPO_ROOT.resolve(strict=True))
    if root.is_symlink():
        raise ValueError("symlinked audit root is prohibited")
    return root


def write_once(path: Path, payload: str) -> None:
    if path.exists():
        raise ValueError(f"refusing to overwrite audit artifact: {path}")
    path.write_text(payload, encoding="utf-8")


def _download_one(
    client: httpx.Client,
    contract: dict[str, Any],
    destination: Path,
    hour: int,
    data_type: str,
) -> dict[str, Any]:
    key = object_key(contract, hour, data_type)
    api_url = request_url(contract, key)
    validate_request_url(contract, api_url)
    response = client.get(api_url, follow_redirects=False)
    if response.status_code not in {301, 302, 303, 307, 308}:
        response.raise_for_status()
        raise ValueError("provider download endpoint did not return a signed redirect")
    signed_url = response.headers.get("location", "")
    validate_redirect_url(contract, signed_url, key)
    raw_path = destination / "raw" / f"{hour:02d}" / f"BTCUSDT_{data_type}.parquet.zst"
    parquet_path = destination / "parquet" / f"{hour:02d}" / f"BTCUSDT_{data_type}.parquet"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    raw_partial = raw_path.with_suffix(raw_path.suffix + ".part")
    raw_digest = hashlib.sha256()
    total = 0
    headers: dict[str, str] = {}
    try:
        with client.stream("GET", signed_url, follow_redirects=False) as download:
            download.raise_for_status()
            headers = {
                "content_length": download.headers.get("content-length", ""),
                "etag": download.headers.get("etag", "").strip('"'),
                "last_modified": download.headers.get("last-modified", ""),
            }
            with raw_partial.open("xb") as handle:
                for chunk in download.iter_bytes(chunk_size=1024 * 1024):
                    handle.write(chunk)
                    raw_digest.update(chunk)
                    total += len(chunk)
                handle.flush()
                os.fsync(handle.fileno())
        if total <= 0:
            raise ValueError("provider returned an empty object")
        if headers["content_length"] and int(headers["content_length"]) != total:
            raise ValueError("provider object length changed during download")
        os.replace(raw_partial, raw_path)
        parquet_partial = parquet_path.with_suffix(parquet_path.suffix + ".part")
        with parquet_partial.open("xb") as output:
            completed = subprocess.run(
                ["zstd", "-d", "-q", "--stdout", str(raw_path)],
                check=False,
                stdout=output,
                stderr=subprocess.PIPE,
            )
            output.flush()
            os.fsync(output.fileno())
        if completed.returncode != 0:
            parquet_partial.unlink(missing_ok=True)
            raise ValueError(f"zstd decompression failed: {completed.stderr.decode(errors='replace')}")
        os.replace(parquet_partial, parquet_path)
        parquet = pq.ParquetFile(parquet_path)
        if parquet.metadata.num_rows <= 0:
            raise ValueError("decompressed parquet is empty")
    except Exception:
        raw_partial.unlink(missing_ok=True)
        parquet_path.with_suffix(parquet_path.suffix + ".part").unlink(missing_ok=True)
        raise
    return {
        "compressed_bytes": total,
        "compressed_file": str(raw_path.relative_to(destination)),
        "compressed_sha256": raw_digest.hexdigest(),
        "data_type": data_type,
        "etag": headers["etag"],
        "hour_utc": hour,
        "last_modified": headers["last_modified"],
        "object_key": key,
        "parquet_bytes": parquet_path.stat().st_size,
        "parquet_file": str(parquet_path.relative_to(destination)),
        "parquet_rows": parquet.metadata.num_rows,
        "parquet_sha256": sha256_file(parquet_path),
        "request_url": api_url,
    }


def _pilot_passed(contract: dict[str, Any]) -> bool:
    try:
        report_path = artifact_root(contract, must_exist=True) / "pilot/hour-audit-report.json"
    except FileNotFoundError:
        return False
    if not report_path.exists():
        return False
    report = load_canonical(report_path, "pilot hour report")
    return (
        report.get("audit_id") == contract["audit_id"]
        and report.get("contract_sha256") == sha256_file(DEFAULT_CONTRACT)
        and report.get("decision") == "hour_pass"
    )


def download_phase(contract: dict[str, Any], phase: str) -> dict[str, Any]:
    root = artifact_root(contract, must_exist=False)
    root.mkdir(parents=True, exist_ok=True)
    if phase == "pilot":
        destination = root / "pilot"
        hours = [contract["boundaries"]["pilot_hour_utc"]]
    elif phase == "day":
        if not _pilot_passed(contract):
            raise ValueError("full-day download is prohibited until the frozen pilot hour passes")
        destination = root / "day"
        hours = [
            hour
            for hour in contract["boundaries"]["full_day_hours_utc"]
            if hour != contract["boundaries"]["pilot_hour_utc"]
        ]
    else:
        raise ValueError("unsupported download phase")
    if destination.exists():
        if any(destination.iterdir()):
            raise ValueError(f"refusing to reuse non-empty audit phase directory: {destination}")
    else:
        destination.mkdir(parents=True)
    records: list[dict[str, Any]] = []
    timeout = httpx.Timeout(connect=20, read=180, write=30, pool=20)
    with httpx.Client(timeout=timeout) as client:
        for hour in hours:
            for data_type in contract["inputs"]["data_types"]:
                records.append(_download_one(client, contract, destination, hour, data_type))
    source = {
        "audit_id": contract["audit_id"],
        "contract_sha256": sha256_file(DEFAULT_CONTRACT),
        "objects": records,
        "phase": phase,
        "provider_terms": contract["inputs"]["provider_terms"],
        "retrieved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "schema_version": SOURCE_SCHEMA,
    }
    write_once(destination / "source-manifest.json", canonical_json(source))
    return source


def _to_array(value: pa.Array | pa.ChunkedArray) -> pa.Array:
    return value.combine_chunks() if isinstance(value, pa.ChunkedArray) else value


def timestamp_ns(value: pa.Array | pa.ChunkedArray) -> np.ndarray:
    array = _to_array(value)
    if array.null_count:
        raise ValueError("timestamp contains nulls")
    if pa.types.is_timestamp(array.type):
        raw = np.asarray(array.cast(pa.int64()).to_numpy(zero_copy_only=False), dtype=np.int64)
        factor = {"s": 1_000_000_000, "ms": 1_000_000, "us": 1_000, "ns": 1}[
            array.type.unit
        ]
        return raw * factor
    raw = np.asarray(array.cast(pa.int64()).to_numpy(zero_copy_only=False), dtype=np.int64)
    if not len(raw):
        return raw
    magnitude = int(np.median(np.abs(raw)))
    if magnitude >= 100_000_000_000_000_000:
        factor = 1
    elif magnitude >= 100_000_000_000_000:
        factor = 1_000
    elif magnitude >= 100_000_000_000:
        factor = 1_000_000
    elif magnitude >= 100_000_000:
        factor = 1_000_000_000
    else:
        raise ValueError("timestamp magnitude is not a supported Unix unit")
    return raw * factor


def _numeric(value: pa.Array | pa.ChunkedArray) -> np.ndarray:
    array = _to_array(value)
    try:
        cast = pc.cast(array, pa.float64(), safe=True)
    except (pa.ArrowInvalid, pa.ArrowNotImplementedError) as exc:
        raise ValueError("numeric field cannot be parsed exactly enough for validation") from exc
    return np.asarray(cast.to_numpy(zero_copy_only=False), dtype=np.float64)


def _int_values(value: pa.Array | pa.ChunkedArray, *, allow_null: bool) -> list[int | None]:
    array = _to_array(value)
    if array.null_count and not allow_null:
        raise ValueError("required integer field contains nulls")
    return [None if item is None else int(item) for item in array.to_pylist()]


def _text_values(value: pa.Array | pa.ChunkedArray, *, allow_null: bool = False) -> list[str | None]:
    array = _to_array(value)
    if array.null_count and not allow_null:
        raise ValueError("required text field contains nulls")
    return [None if item is None else str(item) for item in array.to_pylist()]


def _partition_bounds(date: str, hour: int) -> tuple[int, int]:
    start = datetime.fromisoformat(date).replace(tzinfo=timezone.utc) + timedelta(hours=hour)
    start_ns = int(start.timestamp()) * 1_000_000_000
    return start_ns, start_ns + 3_600_000_000_000


def _common_time_checks(
    table: pa.Table, date: str, hour: int
) -> tuple[np.ndarray, np.ndarray, dict[str, int]]:
    received = timestamp_ns(table["received_time"])
    event = timestamp_ns(table["event_time"])
    start_ns, end_ns = _partition_bounds(date, hour)
    if not len(received) or len(received) != len(event):
        raise ValueError("timestamp columns are empty or misaligned")
    if received.min() < start_ns or received.max() >= end_ns:
        raise ValueError("received_time crosses the frozen UTC hour")
    if event.min() < start_ns or event.max() >= end_ns:
        raise ValueError("event_time crosses the frozen UTC hour")
    if np.any(np.diff(received) < 0):
        raise ValueError("received_time is not non-decreasing")
    if np.any(received < event):
        raise ValueError("received_time precedes exchange event_time")
    return received, event, {
        "max_event_time_ns": int(event.max()),
        "max_received_time_ns": int(received.max()),
        "min_event_time_ns": int(event.min()),
        "min_received_time_ns": int(received.min()),
    }


def _required_table(path: Path, contract: dict[str, Any], data_type: str) -> pa.Table:
    parquet = pq.ParquetFile(path)
    required = contract["inputs"]["required_columns"][data_type]
    missing = sorted(set(required) - set(parquet.schema_arrow.names))
    if missing:
        raise ValueError(f"missing documented columns: {missing}")
    return pq.read_table(path, columns=required)


def inspect_orderbook(
    path: Path, contract: dict[str, Any], hour: int
) -> dict[str, Any]:
    table = _required_table(path, contract, "orderbook")
    common_non_null = ["received_time", "event_time", "symbol", "event_type", "side", "price", "quantity"]
    for name in common_non_null:
        if table[name].null_count:
            raise ValueError(f"required orderbook field contains nulls: {name}")
    received, event, times = _common_time_checks(
        table, contract["boundaries"]["exact_partition_date"], hour
    )
    symbols = set(_text_values(table["symbol"]))
    event_types = _text_values(table["event_type"])
    sides = _text_values(table["side"])
    if symbols != {contract["inputs"]["symbol"]}:
        raise ValueError("orderbook symbol identity mismatch")
    if not set(event_types) <= {"snapshot", "update"} or "snapshot" not in event_types:
        raise ValueError("orderbook lacks the required snapshot/update event domain")
    if set(sides) != {"bid", "ask"}:
        raise ValueError("orderbook side domain mismatch")
    prices = _numeric(table["price"])
    quantities = _numeric(table["quantity"])
    if (
        not np.all(np.isfinite(prices))
        or not np.all(np.isfinite(quantities))
        or np.any(prices <= 0)
        or np.any(quantities < 0)
    ):
        raise ValueError("invalid orderbook price or quantity")
    first_ids = _int_values(table["first_update_id"], allow_null=True)
    final_ids = _int_values(table["final_update_id"], allow_null=True)
    prev_ids = _int_values(table["prev_final_update_id"], allow_null=True)
    last_ids = _int_values(table["last_update_id"], allow_null=True)
    book: dict[str, dict[float, float]] = {"bid": {}, "ask": {}}
    previous_final: int | None = None
    initialized = False
    groups = 0
    snapshots = 0
    updates = 0
    max_group_gap_ns = 0
    previous_group_received: int | None = None
    current_key: tuple[Any, ...] | None = None
    current_rows: list[int] = []

    def flush(key: tuple[Any, ...] | None, rows: list[int]) -> None:
        nonlocal previous_final, initialized, groups, snapshots, updates
        nonlocal max_group_gap_ns, previous_group_received
        if key is None:
            return
        kind, group_received, _group_event, first_id, final_id, prev_id, last_id = key
        groups += 1
        if previous_group_received is not None:
            max_group_gap_ns = max(max_group_gap_ns, group_received - previous_group_received)
        previous_group_received = group_received
        if kind == "snapshot":
            if last_id is None:
                raise ValueError("snapshot lacks last_update_id")
            book["bid"].clear()
            book["ask"].clear()
            previous_final = last_id
            initialized = True
            snapshots += 1
        elif kind == "update":
            if not initialized:
                raise ValueError("update appears before a replay-initializing snapshot")
            if first_id is None or final_id is None or first_id > final_id:
                raise ValueError("update has invalid native first/final update IDs")
            if final_id <= int(previous_final):
                return
            expected = int(previous_final) + 1
            if not (first_id <= expected <= final_id):
                raise ValueError("unsegmented update-ID gap")
            if prev_id is not None and prev_id != previous_final:
                raise ValueError("prev_final_update_id does not match replay state")
            previous_final = final_id
            updates += 1
        else:
            raise ValueError("unsupported orderbook event type")
        for index in rows:
            side = str(sides[index])
            price = float(prices[index])
            quantity = float(quantities[index])
            if quantity == 0:
                book[side].pop(price, None)
            else:
                book[side][price] = quantity
        if not book["bid"] or not book["ask"]:
            raise ValueError("replay produced an empty book side")
        if max(book["bid"]) >= min(book["ask"]):
            raise ValueError("replay produced a crossed or locked book")

    for index in range(table.num_rows):
        kind = str(event_types[index])
        key = (
            kind,
            int(received[index]),
            int(event[index]),
            first_ids[index],
            final_ids[index],
            prev_ids[index],
            last_ids[index],
        )
        if current_key is not None and key != current_key:
            flush(current_key, current_rows)
            current_rows = []
        current_key = key
        current_rows.append(index)
    flush(current_key, current_rows)
    if not initialized or not snapshots or not updates:
        raise ValueError("orderbook lacks a usable snapshot-plus-update replay")
    result = {
        "columns": sorted(table.column_names),
        "data_type": "orderbook",
        "event_groups": groups,
        "final_update_id": previous_final,
        "hour_utc": hour,
        "max_group_gap_ns": max_group_gap_ns,
        "replay_uncrossed": True,
        "row_count": table.num_rows,
        "snapshot_groups": snapshots,
        "update_groups": updates,
    }
    result.update(times)
    return result


def inspect_trades(path: Path, contract: dict[str, Any], hour: int) -> dict[str, Any]:
    table = _required_table(path, contract, "trades")
    for name in [
        "received_time",
        "event_time",
        "symbol",
        "trade_id",
        "price",
        "quantity",
        "trade_time",
        "is_buyer_maker",
    ]:
        if table[name].null_count:
            raise ValueError(f"required trade field contains nulls: {name}")
    _received, _event, times = _common_time_checks(
        table, contract["boundaries"]["exact_partition_date"], hour
    )
    symbols = set(_text_values(table["symbol"]))
    if symbols != {contract["inputs"]["symbol"]}:
        raise ValueError("trade symbol identity mismatch")
    prices = _numeric(table["price"])
    quantities = _numeric(table["quantity"])
    if (
        not np.all(np.isfinite(prices))
        or not np.all(np.isfinite(quantities))
        or np.any(prices <= 0)
        or np.any(quantities <= 0)
    ):
        raise ValueError("invalid trade price or quantity")
    trade_ids = np.asarray(_int_values(table["trade_id"], allow_null=False), dtype=np.int64)
    if len(trade_ids) < 1 or np.any(np.diff(trade_ids) <= 0):
        raise ValueError("trade IDs are not strictly increasing")
    trade_time = timestamp_ns(table["trade_time"])
    start_ns, end_ns = _partition_bounds(contract["boundaries"]["exact_partition_date"], hour)
    if trade_time.min() < start_ns or trade_time.max() >= end_ns:
        raise ValueError("trade_time crosses the frozen UTC hour")
    result = {
        "columns": sorted(table.column_names),
        "data_type": "trades",
        "first_trade_id": int(trade_ids[0]),
        "hour_utc": hour,
        "last_trade_id": int(trade_ids[-1]),
        "row_count": table.num_rows,
        "trade_ids_strictly_increasing": True,
    }
    result.update(times)
    return result


def _source_objects(contract: dict[str, Any], phase: str) -> list[dict[str, Any]]:
    root = artifact_root(contract, must_exist=True)
    source = load_canonical(root / phase / "source-manifest.json", f"{phase} source manifest")
    if (
        source.get("schema_version") != SOURCE_SCHEMA
        or source.get("audit_id") != contract["audit_id"]
        or source.get("contract_sha256") != sha256_file(DEFAULT_CONTRACT)
        or source.get("phase") != phase
    ):
        raise ValueError("source manifest does not match the frozen audit")
    return source["objects"]


def _verify_source_object(
    contract: dict[str, Any], phase: str, record: dict[str, Any]
) -> Path:
    root = artifact_root(contract, must_exist=True)
    path = (root / phase / record["parquet_file"]).resolve(strict=True)
    path.relative_to((root / phase).resolve(strict=True))
    compressed = (root / phase / record["compressed_file"]).resolve(strict=True)
    compressed.relative_to((root / phase).resolve(strict=True))
    if path.is_symlink() or compressed.is_symlink():
        raise ValueError("symlinked provider artifact is prohibited")
    if (
        path.stat().st_size != record["parquet_bytes"]
        or compressed.stat().st_size != record["compressed_bytes"]
        or sha256_file(path) != record["parquet_sha256"]
        or sha256_file(compressed) != record["compressed_sha256"]
    ):
        raise ValueError("provider artifact checksum mismatch")
    return path


def _phase_records(contract: dict[str, Any], phase: str) -> Iterable[tuple[str, dict[str, Any]]]:
    if phase == "pilot":
        for record in _source_objects(contract, "pilot"):
            yield "pilot", record
        return
    if not _pilot_passed(contract):
        raise ValueError("full-day audit is prohibited until the frozen pilot hour passes")
    for record in _source_objects(contract, "pilot"):
        yield "pilot", record
    for record in _source_objects(contract, "day"):
        yield "day", record


def audit_phase(contract: dict[str, Any], phase: str) -> dict[str, Any]:
    root = artifact_root(contract, must_exist=True)
    records = list(_phase_records(contract, phase))
    expected_count = 2 if phase == "pilot" else 48
    if len(records) != expected_count:
        raise ValueError("source manifest does not contain the frozen object count")
    inspections: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for source_phase, record in records:
        hour = int(record["hour_utc"])
        data_type = record["data_type"]
        try:
            path = _verify_source_object(contract, source_phase, record)
            inspection = (
                inspect_orderbook(path, contract, hour)
                if data_type == "orderbook"
                else inspect_trades(path, contract, hour)
            )
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
            book = pair["orderbook"]
            trades = pair["trades"]
            if (
                max(book["min_received_time_ns"], trades["min_received_time_ns"])
                > min(book["max_received_time_ns"], trades["max_received_time_ns"])
            ):
                errors.append(
                    {"data_type": "pair", "error": "trade/orderbook receipt ranges do not overlap", "hour_utc": hour}
                )
            if book["max_group_gap_ns"] > 1_000_000_000:
                errors.append(
                    {"data_type": "orderbook", "error": "unexplained received-time gap exceeds one second", "hour_utc": hour}
                )
        for hour in range(23):
            left = by_hour[hour]["trades"]["last_trade_id"]
            right = by_hour[hour + 1]["trades"]["first_trade_id"]
            if right != left + 1:
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
        "phase": phase,
        "provider_fixture_accepted": accepted,
        "schema_version": REPORT_SCHEMA,
        "sealed_2026_accessed": False,
    }
    report_name = "hour-audit-report.json" if phase == "pilot" else "day-audit-report.json"
    report_path = root / phase / report_name
    write_once(report_path, canonical_json(report))
    artifacts: dict[str, dict[str, Any]] = {}
    phase_names = ["pilot"] if phase == "pilot" else ["pilot", "day"]
    for source_phase in phase_names:
        source_path = root / source_phase / "source-manifest.json"
        artifacts[str(source_path.relative_to(REPO_ROOT))] = {
            "bytes": source_path.stat().st_size,
            "sha256": sha256_file(source_path),
        }
        for record in _source_objects(contract, source_phase):
            for key in ("compressed_file", "parquet_file"):
                path = root / source_phase / record[key]
                artifacts[str(path.relative_to(REPO_ROOT))] = {
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
    for path in [DEFAULT_CONTRACT, Path(__file__), report_path]:
        artifacts[str(path.relative_to(REPO_ROOT))] = {
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
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
    manifest_name = "hour-manifest.json" if phase == "pilot" else "day-manifest.json"
    manifest_path = root / phase / manifest_name
    manifest = load_canonical(manifest_path, f"{phase} audit manifest")
    if (
        manifest.get("schema_version") != MANIFEST_SCHEMA
        or manifest.get("contract_sha256") != sha256_file(DEFAULT_CONTRACT)
        or manifest.get("phase") != phase
    ):
        raise ValueError("audit manifest does not match the frozen phase")
    for name, expected in manifest["artifacts"].items():
        path = (REPO_ROOT / name).resolve(strict=True)
        path.relative_to(REPO_ROOT.resolve(strict=True))
        if path.stat().st_size != expected["bytes"] or sha256_file(path) != expected["sha256"]:
            raise ValueError(f"audit artifact mismatch: {name}")
    return {
        "decision": manifest["decision"],
        "manifest_sha256": sha256_file(manifest_path),
        "phase": phase,
        "verified_artifacts": len(manifest["artifacts"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=("download-hour", "audit-hour", "download-day", "audit-day", "verify-hour", "verify-day"),
    )
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    args = parser.parse_args()
    contract = require_contract(args.contract)
    if args.command == "download-hour":
        source = download_phase(contract, "pilot")
        summary = {"downloaded_objects": len(source["objects"]), "phase": "pilot"}
    elif args.command == "audit-hour":
        report = audit_phase(contract, "pilot")
        summary = {"decision": report["decision"], "errors": len(report["errors"]), "phase": "pilot"}
    elif args.command == "download-day":
        source = download_phase(contract, "day")
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
