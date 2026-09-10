#!/usr/bin/env python3
"""Offline quality audit for btc-carry-data-qualification-v1."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "research/btc/contracts/btc-carry-data-qualification-v1.json"
OUTPUT = ROOT / "artifacts/agent-level-experiment/btc-focused/carry-data-qualification-v1"
SOURCE_MANIFEST = OUTPUT / "source-manifest.json"
SERIES = ("klines", "markPriceKlines", "indexPriceKlines", "premiumIndexKlines")
UTC = timezone.utc
HOUR_MS = 3_600_000
FUNDING_INTERVAL_MS = 8 * HOUR_MS


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def timestamp_ms(raw: str) -> tuple[int, str]:
    value = int(raw)
    if value >= 100_000_000_000_000:
        if value % 1000:
            raise ValueError(f"microsecond timestamp is not millisecond aligned: {value}")
        return value // 1000, "microseconds"
    if value < 1_000_000_000_000:
        raise ValueError(f"timestamp is too small: {value}")
    return value, "milliseconds"


def iso_utc(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp / 1000, tz=UTC).isoformat().replace("+00:00", "Z")


def scheduled_funding_timestamp(observed: int) -> tuple[int, int]:
    """Map a funding publication timestamp to its nearest scheduled eight-hour event.

    Binance's official archive contains sub-second publication jitter. The economic event
    is identified by its scheduled timestamp; the observed offset is retained as a quality
    diagnostic and offsets of one second or more fail closed.
    """
    scheduled = round(observed / FUNDING_INTERVAL_MS) * FUNDING_INTERVAL_MS
    offset = abs(observed - scheduled)
    if offset >= 1_000:
        raise ValueError("funding event is over one second from schedule")
    return scheduled, offset


def csv_rows(path: Path):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != 1 or not names[0].endswith(".csv"):
            raise ValueError(f"archive must contain exactly one CSV: {path}")
        with archive.open(names[0]) as raw:
            wrapper = io.TextIOWrapper(raw, encoding="utf-8", newline="")
            reader = csv.reader(wrapper)
            first = next(reader, None)
            if first is None:
                raise ValueError(f"empty CSV: {path}")
            if first[0] not in {"open_time", "calc_time"}:
                yield first
            yield from reader


def audit_price_series(records: list[dict], series: str) -> tuple[dict, set[int]]:
    open_times: set[int] = set()
    duplicate_count = 0
    invalid_count = 0
    unit_counts: Counter[str] = Counter()
    archive_rows: dict[str, int] = {}
    for record in records:
        path = ROOT / record["archive_path"]
        rows = 0
        for row in csv_rows(path):
            rows += 1
            try:
                if len(row) != 12:
                    raise ValueError("unexpected kline width")
                opened, unit = timestamp_ms(row[0])
                closed, close_unit = timestamp_ms(row[6])
                if unit != close_unit or closed != opened + 3_599_999 or opened % 3_600_000:
                    raise ValueError("invalid hourly timestamp boundary")
                values = [float(row[index]) for index in (1, 2, 3, 4)]
                if not all(math.isfinite(value) for value in values):
                    raise ValueError("non-finite OHLC")
                opening, high, low, close = values
                if high < max(opening, close) or low > min(opening, close) or high < low:
                    raise ValueError("invalid OHLC ordering")
                if series != "premiumIndexKlines" and min(values) <= 0:
                    raise ValueError("non-positive price")
                if opened in open_times:
                    duplicate_count += 1
                else:
                    open_times.add(opened)
                unit_counts[unit] += 1
            except (ValueError, OverflowError):
                invalid_count += 1
        archive_rows[record["month"]] = rows
    ordered = sorted(open_times)
    gap_intervals = [
        {
            "first_missing_open_at": iso_utc(left + HOUR_MS),
            "last_missing_open_at": iso_utc(right - HOUR_MS),
            "missing_hours": (right - left) // HOUR_MS - 1,
            "next_available_open_at": iso_utc(right),
            "previous_available_open_at": iso_utc(left),
        }
        for left, right in zip(ordered, ordered[1:])
        if right - left != HOUR_MS
    ]
    return {
        "archive_count": len(records),
        "archive_rows": archive_rows,
        "duplicate_open_times": duplicate_count,
        "first_open_at": None if not ordered else iso_utc(ordered[0]),
        "gap_intervals": gap_intervals,
        "hourly_calendar_gaps": len(gap_intervals),
        "invalid_rows": invalid_count,
        "last_open_at": None if not ordered else iso_utc(ordered[-1]),
        "missing_hours": sum(item["missing_hours"] for item in gap_intervals),
        "row_count": len(open_times),
        "timestamp_units": dict(sorted(unit_counts.items())),
    }, open_times


def audit_funding(records: list[dict]) -> dict:
    scheduled_times: set[int] = set()
    duplicate_count = 0
    invalid_count = 0
    interval_counts: Counter[int] = Counter()
    unit_counts: Counter[str] = Counter()
    archive_rows: dict[str, int] = {}
    maximum_schedule_offset_ms = 0
    for record in records:
        path = ROOT / record["archive_path"]
        rows = 0
        for row in csv_rows(path):
            rows += 1
            try:
                if len(row) != 3:
                    raise ValueError("unexpected funding width")
                observed, unit = timestamp_ms(row[0])
                interval = int(row[1])
                rate = float(row[2])
                if interval != 8 or not math.isfinite(rate):
                    raise ValueError("invalid funding interval or rate")
                scheduled, offset = scheduled_funding_timestamp(observed)
                maximum_schedule_offset_ms = max(maximum_schedule_offset_ms, offset)
                if scheduled in scheduled_times:
                    duplicate_count += 1
                else:
                    scheduled_times.add(scheduled)
                interval_counts[interval] += 1
                unit_counts[unit] += 1
            except (ValueError, OverflowError):
                invalid_count += 1
        archive_rows[record["month"]] = rows
    ordered = sorted(scheduled_times)
    missing_intervals = sum(max(0, (right - left) // FUNDING_INTERVAL_MS - 1) for left, right in zip(ordered, ordered[1:]))
    irregular_intervals = sum(right - left != FUNDING_INTERVAL_MS for left, right in zip(ordered, ordered[1:]))
    return {
        "archive_count": len(records),
        "archive_rows": archive_rows,
        "duplicate_times": duplicate_count,
        "first_event_at": None if not ordered else iso_utc(ordered[0]),
        "interval_hour_counts": {str(key): value for key, value in sorted(interval_counts.items())},
        "invalid_rows": invalid_count,
        "irregular_intervals": irregular_intervals,
        "last_event_at": None if not ordered else iso_utc(ordered[-1]),
        "maximum_schedule_offset_ms": maximum_schedule_offset_ms,
        "missing_scheduled_events": missing_intervals,
        "row_count": len(scheduled_times),
        "timestamp_units": dict(sorted(unit_counts.items())),
    }


def inspect_public_evidence(source_manifest: dict) -> dict:
    by_name = {item["name"]: item for item in source_manifest["public_evidence_records"]}
    snapshots = {}
    for name in ("spot-exchange-info-BTCUSDT", "usd-m-exchange-info", "usd-m-funding-info", "usd-m-mark-index-BTCUSDT"):
        item = by_name[name]
        valid = False
        detail = None
        if item["status"] == "downloaded":
            payload = json.loads((ROOT / item["path"]).read_text(encoding="utf-8"))
            if name == "spot-exchange-info-BTCUSDT":
                symbols = payload.get("symbols", [])
                valid = len(symbols) == 1 and symbols[0].get("symbol") == "BTCUSDT"
                detail = {"symbol": symbols[0].get("symbol") if symbols else None, "status": symbols[0].get("status") if symbols else None}
            elif name == "usd-m-exchange-info":
                matches = [row for row in payload.get("symbols", []) if row.get("symbol") == "BTCUSDT"]
                valid = len(matches) == 1 and matches[0].get("contractType") == "PERPETUAL"
                detail = None if not matches else {key: matches[0].get(key) for key in ("symbol", "status", "contractType", "onboardDate", "marginAsset")}
            elif name == "usd-m-funding-info":
                matches = [row for row in payload if row.get("symbol") == "BTCUSDT"]
                valid = isinstance(payload, list)
                detail = {
                    "BTCUSDT_override_rows": len(matches),
                    "current_override": None if not matches else {
                        key: matches[0].get(key)
                        for key in ("fundingIntervalHours", "adjustedFundingRateCap", "adjustedFundingRateFloor")
                    },
                    "interpretation": "current_override_only_not_historical_rules" if matches else "absence_is_no_current_override",
                }
            else:
                valid = payload.get("symbol") == "BTCUSDT" and all(key in payload for key in ("markPrice", "indexPrice", "time"))
                detail = {"symbol": payload.get("symbol"), "time": payload.get("time")}
        snapshots[name] = {"source_status": item["status"], "valid": valid, "detail": detail}
    documentation = {
        name: {"status": by_name[name]["status"], "error": by_name[name].get("error")}
        for name in ("binance-public-data-README", "binance-fee-schedule", "usd-m-account-margin-documentation", "usd-m-market-data-documentation")
    }
    return {"current_snapshots": snapshots, "documentation": documentation}


def main() -> None:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    source_manifest = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))
    if source_manifest["audit_id"] != contract["audit_id"] or source_manifest["credentials_used"] is not False:
        raise ValueError("source manifest violates frozen audit identity or credential boundary")
    for item in contract["bound_existing_inputs"]:
        if sha256_path(ROOT / item["path"]) != item["sha256"]:
            raise ValueError(f"bound input checksum mismatch: {item['path']}")
    if source_manifest["return_pnl_or_strategy_calculated"] is not False:
        raise ValueError("acquisition crossed strategy boundary")

    archive_records = source_manifest["archive_records"]
    checksum_failures = 0
    for item in archive_records:
        if item["status"] == "failed" or not item.get("archive_path"):
            checksum_failures += 1
            continue
        path = ROOT / item["archive_path"]
        if sha256_path(path) != item["archive_sha256"] or item["archive_sha256"] != item["official_checksum"]:
            checksum_failures += 1

    price_results = {}
    open_time_sets = {}
    for series in SERIES:
        records = [item for item in archive_records if item["series"] == series and item["status"] != "failed"]
        price_results[series], open_time_sets[series] = audit_price_series(records, series)
    funding_records = [item for item in archive_records if item["series"] == "fundingRate" and item["status"] != "failed"]
    funding_result = audit_funding(funding_records)
    synchronized = all(open_time_sets[series] == open_time_sets[SERIES[0]] for series in SERIES[1:])
    expected_first = "2020-01-01T00:00:00Z"
    expected_last = "2025-12-31T23:00:00Z"
    expected_rows = 52_608
    public_evidence = inspect_public_evidence(source_manifest)

    data_gate_results = {
        "all_360_archives_and_sidecars_present": len(archive_records) == 360 and source_manifest["archive_failures"] == 0,
        "all_official_archive_checksums_match": checksum_failures == 0,
        "all_price_series_72_months": all(price_results[series]["archive_count"] == 72 for series in SERIES),
        "all_price_series_exact_2020_2025_boundary": all(price_results[series]["first_open_at"] == expected_first and price_results[series]["last_open_at"] == expected_last for series in SERIES),
        "all_price_series_exact_row_count": all(price_results[series]["row_count"] == expected_rows for series in SERIES),
        "all_price_series_no_duplicates_gaps_or_invalid_rows": all(price_results[series]["duplicate_open_times"] == 0 and price_results[series]["hourly_calendar_gaps"] == 0 and price_results[series]["invalid_rows"] == 0 for series in SERIES),
        "all_price_series_synchronized": synchronized,
        "funding_72_months": funding_result["archive_count"] == 72,
        "funding_complete_8h_no_duplicates_or_invalid_rows": funding_result["duplicate_times"] == 0 and funding_result["missing_scheduled_events"] == 0 and funding_result["irregular_intervals"] == 0 and funding_result["invalid_rows"] == 0,
        "spot_and_futures_current_identity_snapshots_valid": all(item["valid"] for item in public_evidence["current_snapshots"].values()),
        "spot_development_manifest_bound": any(item["path"].endswith("s1-ledger-v1/manifest.json") for item in contract["bound_existing_inputs"]),
    }
    data_gate_passed = all(data_gate_results.values())

    strategy_readiness_results = {
        "effective_dated_historical_fee_evidence": False,
        "effective_dated_historical_margin_brackets": False,
        "exact_account_fee": False,
        "official_fee_page_archived": public_evidence["documentation"]["binance-fee-schedule"]["status"] == "downloaded",
        "official_margin_documentation_archived": public_evidence["documentation"]["usd-m-account-margin-documentation"]["status"] == "downloaded",
        "official_market_data_documentation_archived": public_evidence["documentation"]["usd-m-market-data-documentation"]["status"] == "downloaded",
        "current_rules_not_projected_backward": True,
    }
    strategy_ready = all(strategy_readiness_results.values())
    report = {
        "actionable_arm_id": "no_trade",
        "audit_id": contract["audit_id"],
        "contract": {"path": str(CONTRACT_PATH.relative_to(ROOT)), "sha256": sha256_path(CONTRACT_PATH)},
        "data_gate_passed": data_gate_passed,
        "data_gate_results": data_gate_results,
        "decision": "market_series_passed_strategy_readiness_blocked" if data_gate_passed and not strategy_ready else ("fully_qualified_for_separate_strategy_contract" if strategy_ready else "data_qualification_rejected"),
        "funding": funding_result,
        "no_strategy_return_pnl_position_or_order_computed": True,
        "price_series": price_results,
        "public_evidence": public_evidence,
        "source_manifest": {"path": str(SOURCE_MANIFEST.relative_to(ROOT)), "sha256": sha256_path(SOURCE_MANIFEST)},
        "strategy_readiness_gate_passed": strategy_ready,
        "strategy_readiness_results": strategy_readiness_results,
    }
    report_path = OUTPUT / "audit-report.json"
    report_path.write_bytes(canonical_bytes(report))
    manifest = {
        "audit_id": contract["audit_id"],
        "files": [
            {"path": str(path.relative_to(ROOT)), "sha256": sha256_path(path)}
            for path in (SOURCE_MANIFEST, report_path)
        ],
    }
    (OUTPUT / "evidence-manifest.json").write_bytes(canonical_bytes(manifest))
    print(json.dumps({
        "data_gate_passed": data_gate_passed,
        "decision": report["decision"],
        "report": str(report_path.relative_to(ROOT)),
        "strategy_readiness_gate_passed": strategy_ready,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
