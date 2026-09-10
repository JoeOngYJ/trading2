#!/usr/bin/env python3
"""Label-blind D0 quality audit for BTC spot/perpetual continuation research."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import zipfile
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "research/btc/contracts/btc-spot-perp-continuation-data-audit-v1.json"
DEFAULT_OUTPUT = ROOT / "artifacts/agent-level-experiment/btc-focused/spot-perp-continuation-d0-v1"
UTC = timezone.utc
HOUR_MS = 3_600_000
FIVE_MINUTES_MS = 300_000


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iso_to_ms(value: str) -> int:
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)


def iso_utc(value_ms: int) -> str:
    return datetime.fromtimestamp(value_ms / 1000, tz=UTC).isoformat().replace("+00:00", "Z")


def timestamp_ms(raw: object) -> int:
    value = int(raw)
    if value >= 100_000_000_000_000:
        if value % 1000:
            raise ValueError("microsecond timestamp is not millisecond aligned")
        value //= 1000
    if value < 1_000_000_000_000:
        raise ValueError("timestamp is too small")
    return value


def csv_rows(path: Path):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != 1 or not names[0].endswith(".csv"):
            raise ValueError(f"archive must contain exactly one CSV: {path}")
        with archive.open(names[0]) as raw:
            reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-8", newline=""))
            first = next(reader, None)
            if first is None:
                raise ValueError(f"empty CSV: {path}")
            if first[0] != "open_time":
                yield first
            yield from reader


def parse_kline(row: list[object]) -> tuple:
    if len(row) < 11:
        raise ValueError("kline has fewer than 11 fields")
    opened = timestamp_ms(row[0])
    closed = timestamp_ms(row[6])
    if opened % HOUR_MS or closed != opened + HOUR_MS - 1:
        raise ValueError("kline is not aligned to an exact completed hour")
    try:
        opening, high, low, close = (Decimal(str(row[index])) for index in (1, 2, 3, 4))
        base_volume = Decimal(str(row[5]))
        quote_volume = Decimal(str(row[7]))
        trade_count = int(row[8])
        taker_buy_base = Decimal(str(row[9]))
        taker_buy_quote = Decimal(str(row[10]))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("invalid numeric kline field") from exc
    if min(opening, high, low, close) <= 0:
        raise ValueError("non-positive kline price")
    if high < max(opening, close) or low > min(opening, close) or high < low:
        raise ValueError("invalid kline OHLC ordering")
    if min(base_volume, quote_volume, taker_buy_base, taker_buy_quote) < 0 or trade_count < 0:
        raise ValueError("negative volume or trade count")
    if taker_buy_base > base_volume or taker_buy_quote > quote_volume:
        raise ValueError("taker-buy volume exceeds total volume")
    return (
        opened,
        opening,
        high,
        low,
        close,
        base_volume,
        closed,
        quote_volume,
        trade_count,
        taker_buy_base,
        taker_buy_quote,
    )


def add_unique(target: dict[int, tuple], row: tuple, source: str) -> None:
    opened = row[0]
    if opened in target:
        if target[opened] != row:
            raise ValueError(f"conflicting duplicate perpetual hour at {iso_utc(opened)} from {source}")
        raise ValueError(f"duplicate perpetual hour at {iso_utc(opened)} from {source}")
    target[opened] = row


def load_bound_perpetual(contract: dict) -> tuple[dict[int, tuple], dict]:
    role = contract["bound_inputs_by_role"]["existing_perpetual_source_manifest"]
    manifest_path = ROOT / role["path"]
    if sha256_path(manifest_path) != role["sha256"]:
        raise ValueError("bound perpetual source manifest checksum mismatch")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    records = sorted(
        (
            item for item in manifest["archive_records"]
            if item.get("series") == "klines" and item.get("status") != "failed"
        ),
        key=lambda item: item["month"],
    )
    rows: dict[int, tuple] = {}
    for record in records:
        path = ROOT / record["archive_path"]
        if sha256_path(path) != record["archive_sha256"] or record["archive_sha256"] != record["official_checksum"]:
            raise ValueError(f"bound perpetual archive checksum mismatch: {record['archive_path']}")
        for raw in csv_rows(path):
            add_unique(rows, parse_kline(raw), record["archive_path"])
    return rows, {
        "archive_count": len(records),
        "first_open_at": None if not rows else iso_utc(min(rows)),
        "last_open_at": None if not rows else iso_utc(max(rows)),
        "row_count": len(rows),
    }


def load_rest_rows(source_manifest: dict) -> dict[int, tuple]:
    rows: dict[int, tuple] = {}
    for page in source_manifest["rest_pages"]:
        path = ROOT / page["path"]
        if sha256_path(path) != page["sha256"]:
            raise ValueError(f"REST page checksum mismatch: {page['path']}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if len(payload) != page["row_count"]:
            raise ValueError("REST page row count changed")
        for raw in payload:
            add_unique(rows, parse_kline(raw), page["path"])
    return rows


def load_daily_overlap(source_manifest: dict) -> dict[int, tuple]:
    item = source_manifest["daily_overlap"]
    path = ROOT / item["archive_path"]
    if sha256_path(path) != item["archive_sha256"] or item["archive_sha256"] != item["official_checksum"]:
        raise ValueError("daily overlap archive checksum mismatch")
    rows: dict[int, tuple] = {}
    for raw in csv_rows(path):
        add_unique(rows, parse_kline(raw), item["archive_path"])
    return rows


def load_spot_hourly(contract: dict, first_ms: int, end_exclusive_ms: int) -> tuple[dict[int, dict], dict]:
    role = contract["bound_inputs_by_role"]["spot_candles_5m"]
    path = ROOT / role["path"]
    if sha256_path(path) != role["sha256"]:
        raise ValueError("bound spot 5-minute ledger checksum mismatch")
    hourly: dict[int, dict] = {}
    current_hour: int | None = None
    group: list[dict] = []
    invalid_or_incomplete = 0
    raw_rows_in_range = 0

    def finalize(hour: int | None, values: list[dict]) -> None:
        nonlocal invalid_or_incomplete
        if hour is None or not values:
            return
        expected = [hour + index * FIVE_MINUTES_MS for index in range(12)]
        opens = [item["open_ms"] for item in values]
        segments = {item["segment"] for item in values}
        if opens != expected or len(segments) != 1:
            invalid_or_incomplete += 1
            return
        hourly[hour] = {
            "close": values[-1]["close"],
            "quote_volume": sum((item["quote_volume"] for item in values), Decimal("0")),
            "segment": values[0]["segment"],
        }

    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            opened = iso_to_ms(row["open_at"])
            if opened < first_ms or opened >= end_exclusive_ms:
                continue
            raw_rows_in_range += 1
            available = iso_to_ms(row["available_at"])
            if opened % FIVE_MINUTES_MS or available != opened + FIVE_MINUTES_MS:
                raise ValueError("spot 5-minute timestamp availability is invalid")
            close = Decimal(str(row["close"]))
            quote_volume = Decimal(str(row["quote_volume"]))
            if close <= 0 or quote_volume < 0:
                raise ValueError("spot close or quote volume is invalid")
            hour = opened - opened % HOUR_MS
            if current_hour is None:
                current_hour = hour
            if hour != current_hour:
                finalize(current_hour, group)
                current_hour = hour
                group = []
            group.append({
                "close": close,
                "open_ms": opened,
                "quote_volume": quote_volume,
                "segment": str(row["segment"]),
            })
    finalize(current_hour, group)
    return hourly, {
        "complete_hour_count": len(hourly),
        "first_complete_hour_at": None if not hourly else iso_utc(min(hourly)),
        "incomplete_or_cross_segment_hours": invalid_or_incomplete,
        "last_complete_hour_at": None if not hourly else iso_utc(max(hourly)),
        "raw_5m_rows_in_range": raw_rows_in_range,
    }


def exact_overlap(left: dict[int, tuple], right: dict[int, tuple], start_ms: int, end_ms: int) -> dict:
    expected = list(range(start_ms, end_ms, HOUR_MS))
    missing_left = [value for value in expected if value not in left]
    missing_right = [value for value in expected if value not in right]
    mismatches = [value for value in expected if value in left and value in right and left[value] != right[value]]
    return {
        "exact_match": not missing_left and not missing_right and not mismatches,
        "expected_rows": len(expected),
        "mismatch_count": len(mismatches),
        "missing_left_count": len(missing_left),
        "missing_right_count": len(missing_right),
    }


def build_segments(common: list[int]) -> list[dict]:
    if not common:
        return []
    segments = []
    start = previous = common[0]
    for value in common[1:]:
        if value - previous != HOUR_MS:
            segments.append({
                "end_open_at": iso_utc(previous),
                "hours": (previous - start) // HOUR_MS + 1,
                "start_open_at": iso_utc(start),
            })
            start = value
        previous = value
    segments.append({
        "end_open_at": iso_utc(previous),
        "hours": (previous - start) // HOUR_MS + 1,
        "start_open_at": iso_utc(start),
    })
    return segments


def feature_ready_counts(segments: list[dict], warmup_days: int) -> tuple[dict[str, int], dict[str, int]]:
    ready_year: Counter[str] = Counter()
    ready_month: Counter[str] = Counter()
    warmup = timedelta(days=warmup_days)
    for segment in segments:
        start = datetime.fromisoformat(segment["start_open_at"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(segment["end_open_at"].replace("Z", "+00:00"))
        decision = (start + warmup).replace(hour=0, minute=0, second=0, microsecond=0)
        if decision - warmup < start:
            decision += timedelta(days=1)
        last_decision = end + timedelta(hours=1)
        while decision <= last_decision and decision < datetime(2026, 1, 1, tzinfo=UTC):
            ready_year[str(decision.year)] += 1
            ready_month[decision.strftime("%Y-%m")] += 1
            decision += timedelta(days=1)
    return dict(sorted(ready_year.items())), dict(sorted(ready_month.items()))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output = args.output.resolve()
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    source_manifest_path = output / "source-manifest.json"
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    if source_manifest.get("audit_id") != contract.get("audit_id"):
        raise ValueError("source manifest audit identity mismatch")
    if source_manifest.get("credentials_used") is not False:
        raise ValueError("D0 source manifest used credentials")
    if source_manifest.get("acquisition_has_no_future_return_label_forecast_strategy_or_pnl") is not True:
        raise ValueError("D0 source manifest crossed the label/model boundary")
    for item in contract["bound_inputs"]:
        if sha256_path(ROOT / item["path"]) != item["sha256"]:
            raise ValueError(f"bound input checksum mismatch: {item['path']}")

    rest = load_rest_rows(source_manifest)
    daily = load_daily_overlap(source_manifest)
    monthly, monthly_summary = load_bound_perpetual(contract)
    pre_2020_start = iso_to_ms(contract["pre_2020_rest_fallback"]["start_inclusive"])
    year_2020 = iso_to_ms("2020-01-01T00:00:00Z")
    jan_3_2020 = iso_to_ms("2020-01-03T00:00:00Z")
    year_2026 = iso_to_ms("2026-01-01T00:00:00Z")
    daily_overlap = exact_overlap(rest, daily, iso_to_ms("2019-12-31T00:00:00Z"), year_2020)
    monthly_overlap = exact_overlap(rest, monthly, year_2020, jan_3_2020)
    pre_2020 = {timestamp: row for timestamp, row in rest.items() if timestamp < year_2020}
    perpetual = dict(pre_2020)
    for timestamp, row in monthly.items():
        if timestamp in perpetual:
            raise ValueError("unexpected canonical perpetual overlap")
        perpetual[timestamp] = row

    spot, spot_summary = load_spot_hourly(contract, pre_2020_start, year_2026)
    common = sorted(set(spot).intersection(perpetual))
    segments = build_segments(common)
    feature_by_year, feature_by_month = feature_ready_counts(segments, contract["gates"]["normalization_warmup_days"])

    coverage_by_year = {}
    for year in range(2020, 2026):
        start = iso_to_ms(f"{year:04d}-01-01T00:00:00Z")
        end = iso_to_ms(f"{year + 1:04d}-01-01T00:00:00Z")
        expected = (end - start) // HOUR_MS
        observed = sum(start <= value < end for value in common)
        coverage_by_year[str(year)] = {
            "coverage": observed / expected,
            "expected_hours": expected,
            "observed_common_hours": observed,
        }
    total_expected = sum(item["expected_hours"] for item in coverage_by_year.values())
    total_observed = sum(item["observed_common_hours"] for item in coverage_by_year.values())
    evaluation_months = [f"{year:04d}-{month:02d}" for year in range(2021, 2026) for month in range(1, 13)]
    sidecar_revision_count = sum(item["revision_detected"] for item in source_manifest["monthly_sidecar_rechecks"])

    gate_results = {
        "all_72_bound_monthly_sidecars_still_match": len(source_manifest["monthly_sidecar_rechecks"]) == 72 and sidecar_revision_count == 0,
        "bound_2020_2025_perpetual_hourly_complete": monthly_summary == {
            "archive_count": 72,
            "first_open_at": "2020-01-01T00:00:00Z",
            "last_open_at": "2025-12-31T23:00:00Z",
            "row_count": 52608,
        },
        "daily_archive_overlap_exact": daily_overlap["exact_match"],
        "evaluation_common_coverage_at_least_99pct": total_observed / total_expected >= contract["gates"]["overall_common_hourly_coverage_minimum"],
        "every_2020_2025_year_common_coverage_at_least_98pct": all(
            item["coverage"] >= contract["gates"]["yearly_common_hourly_coverage_minimum"]
            for item in coverage_by_year.values()
        ),
        "every_2021_2025_month_feature_ready": all(feature_by_month.get(month, 0) > 0 for month in evaluation_months),
        "every_2021_2025_year_at_least_330_feature_ready_days": all(
            feature_by_year.get(str(year), 0) >= contract["gates"]["feature_ready_days_each_evaluation_year_minimum"]
            for year in range(2021, 2026)
        ),
        "pre_2020_rest_begins_at_frozen_first_hour": min(rest) == pre_2020_start,
        "pre_2021_feature_ready_days_at_least_300": sum(
            count for year, count in feature_by_year.items() if int(year) < 2021
        ) >= contract["gates"]["feature_ready_days_before_2021_minimum"],
        "rest_to_2020_monthly_overlap_exact": monthly_overlap["exact_match"],
        "source_and_output_remain_label_model_strategy_pnl_free": True,
    }
    passed = all(gate_results.values())
    segment_report = {
        "audit_id": contract["audit_id"],
        "common_hour_count": len(common),
        "feature_ready_by_month": feature_by_month,
        "feature_ready_by_year": feature_by_year,
        "segments": segments,
    }
    segment_path = output / "segment-report.json"
    segment_path.write_bytes(canonical_bytes(segment_report))
    report = {
        "actionable_arm_id": "no_trade",
        "audit_id": contract["audit_id"],
        "candidate_experiment_id": contract["candidate_experiment_id"],
        "common_hourly": {
            "coverage_2020_2025": total_observed / total_expected,
            "coverage_by_year": coverage_by_year,
            "first_common_open_at": None if not common else iso_utc(common[0]),
            "last_common_open_at": None if not common else iso_utc(common[-1]),
            "segment_count": len(segments),
        },
        "contract": {"path": str(CONTRACT_PATH.relative_to(ROOT)), "sha256": sha256_path(CONTRACT_PATH)},
        "d0_passed": passed,
        "daily_archive_overlap": daily_overlap,
        "decision": "d0_passed_label_blind_data_qualification" if passed else "d0_rejected_label_blind_data_qualification",
        "feature_availability": {
            "by_year": feature_by_year,
            "evaluation_months_missing": [month for month in evaluation_months if feature_by_month.get(month, 0) == 0],
            "pre_2021_count": sum(count for year, count in feature_by_year.items() if int(year) < 2021),
            "warmup_days": contract["gates"]["normalization_warmup_days"],
        },
        "gate_results": gate_results,
        "monthly_archive_overlap": monthly_overlap,
        "next_stage": "freeze_D1_before_any_future_return_label_or_model" if passed else "stop_without_D1",
        "no_future_return_label_forecast_strategy_pnl_position_or_order_computed": True,
        "perpetual": {
            "canonical_first_open_at": iso_utc(min(perpetual)),
            "canonical_last_open_at": iso_utc(max(perpetual)),
            "canonical_row_count": len(perpetual),
            "monthly_2020_2025": monthly_summary,
            "rest_fallback_rows": len(rest),
            "rest_pre_2020_rows": len(pre_2020),
            "sidecar_revision_count": sidecar_revision_count,
        },
        "segment_report": {"path": str(segment_path.relative_to(ROOT)), "sha256": sha256_path(segment_path)},
        "source_manifest": {"path": str(source_manifest_path.relative_to(ROOT)), "sha256": sha256_path(source_manifest_path)},
        "spot": spot_summary,
    }
    report_path = output / "audit-report.json"
    report_path.write_bytes(canonical_bytes(report))
    evidence_paths = [source_manifest_path, segment_path, report_path]
    evidence_paths.extend(ROOT / item["path"] for item in source_manifest["rest_pages"])
    evidence_paths.extend((
        ROOT / source_manifest["daily_overlap"]["archive_path"],
        ROOT / source_manifest["daily_overlap"]["official_checksum_path"],
    ))
    evidence_paths.extend(ROOT / item["current_sidecar_path"] for item in source_manifest["monthly_sidecar_rechecks"])
    evidence_manifest = {
        "audit_id": contract["audit_id"],
        "files": [
            {"path": str(path.relative_to(ROOT)), "sha256": sha256_path(path)}
            for path in evidence_paths
        ],
    }
    evidence_path = output / "evidence-manifest.json"
    evidence_path.write_bytes(canonical_bytes(evidence_manifest))
    print(json.dumps({
        "d0_passed": passed,
        "decision": report["decision"],
        "feature_ready_pre_2021": report["feature_availability"]["pre_2021_count"],
        "output": str(output.relative_to(ROOT)),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
