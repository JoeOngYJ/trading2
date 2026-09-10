#!/usr/bin/env python3
"""Label-blind D0 v3 audit of direct daily BTC spot/perpetual bars."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import zipfile
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "research/btc/contracts/btc-spot-perp-continuation-data-audit-v3.json"
DEFAULT_OUTPUT = ROOT / "artifacts/agent-level-experiment/btc-focused/spot-perp-continuation-d0-v3"
UTC = timezone.utc
DAY_MS = 86_400_000


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


def timestamp_ms(raw: object, *, spot: bool, close_time: bool = False) -> int:
    value = int(raw)
    if value >= 100_000_000_000_000:
        if not spot:
            raise ValueError("unexpected microsecond perpetual timestamp")
        remainder = value % 1000
        if (not close_time and remainder != 0) or (close_time and remainder != 999):
            raise ValueError("unexpected spot microsecond timestamp remainder")
        value //= 1000
    if value < 1_000_000_000_000:
        raise ValueError("timestamp is too small")
    return value


def parse_daily_kline(row: list[object], *, spot: bool) -> tuple:
    if len(row) != 12:
        raise ValueError("daily kline does not have 12 fields")
    opened = timestamp_ms(row[0], spot=spot)
    closed = timestamp_ms(row[6], spot=spot, close_time=True)
    if opened % DAY_MS or closed != opened + DAY_MS - 1:
        raise ValueError("kline is not an exact completed UTC day")
    try:
        opening, high, low, close = (Decimal(str(row[index])) for index in (1, 2, 3, 4))
        base_volume = Decimal(str(row[5]))
        quote_volume = Decimal(str(row[7]))
        trade_count = int(row[8])
        taker_buy_base = Decimal(str(row[9]))
        taker_buy_quote = Decimal(str(row[10]))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("invalid numeric daily-kline field") from exc
    if min(opening, high, low, close) <= 0:
        raise ValueError("non-positive daily price")
    if high < max(opening, close) or low > min(opening, close) or high < low:
        raise ValueError("invalid daily OHLC ordering")
    if min(base_volume, quote_volume, taker_buy_base, taker_buy_quote) < 0 or trade_count < 0:
        raise ValueError("negative daily volume or trade count")
    if taker_buy_base > base_volume or taker_buy_quote > quote_volume:
        raise ValueError("daily taker-buy volume exceeds total volume")
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


def add_unique(target: dict[int, tuple], row: tuple, source: str) -> None:
    opened = row[0]
    if opened in target:
        if target[opened] != row:
            raise ValueError(f"conflicting daily row at {iso_utc(opened)} from {source}")
        raise ValueError(f"duplicate daily row at {iso_utc(opened)} from {source}")
    target[opened] = row


def load_monthly(source_manifest: dict, market: str) -> tuple[dict[int, tuple], dict]:
    records = [item for item in source_manifest["archive_records"] if item["market"] == market]
    rows: dict[int, tuple] = {}
    units: Counter[str] = Counter()
    for record in records:
        if record["status"] == "failed":
            continue
        path = ROOT / record["archive_path"]
        if sha256_path(path) != record["archive_sha256"] or record["archive_sha256"] != record["official_checksum"]:
            raise ValueError(f"{market} archive checksum mismatch: {record['archive_path']}")
        for raw in csv_rows(path):
            parsed = parse_daily_kline(raw, spot=market == "spot")
            add_unique(rows, parsed, record["archive_path"])
            units["microseconds" if int(raw[0]) >= 100_000_000_000_000 else "milliseconds"] += 1
    ordered = sorted(rows)
    gaps = sum(right - left != DAY_MS for left, right in zip(ordered, ordered[1:]))
    return rows, {
        "archive_count": len(records),
        "archive_failures": sum(item["status"] == "failed" for item in records),
        "first_open_at": None if not ordered else iso_utc(ordered[0]),
        "gap_count": gaps,
        "last_open_at": None if not ordered else iso_utc(ordered[-1]),
        "row_count": len(rows),
        "timestamp_units": dict(sorted(units.items())),
    }


def load_rest(source_manifest: dict) -> dict[int, tuple]:
    item = source_manifest["rest_daily"]
    path = ROOT / item["path"]
    if sha256_path(path) != item["sha256"]:
        raise ValueError("daily REST response checksum mismatch")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if len(payload) != item["row_count"]:
        raise ValueError("daily REST row count changed")
    rows: dict[int, tuple] = {}
    for raw in payload:
        add_unique(rows, parse_daily_kline(raw, spot=False), item["path"])
    return rows


def load_daily_overlap(source_manifest: dict) -> dict[int, tuple]:
    item = source_manifest["futures_daily_overlap"]
    path = ROOT / item["archive_path"]
    if sha256_path(path) != item["archive_sha256"] or item["archive_sha256"] != item["official_checksum"]:
        raise ValueError("futures daily-overlap checksum mismatch")
    rows: dict[int, tuple] = {}
    for raw in csv_rows(path):
        add_unique(rows, parse_daily_kline(raw, spot=False), item["archive_path"])
    return rows


def exact_overlap(left: dict[int, tuple], right: dict[int, tuple], start_ms: int, end_ms: int) -> dict:
    expected = list(range(start_ms, end_ms, DAY_MS))
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
        if value - previous != DAY_MS:
            segments.append({"end_open_at": iso_utc(previous), "days": (previous - start) // DAY_MS + 1, "start_open_at": iso_utc(start)})
            start = value
        previous = value
    segments.append({"end_open_at": iso_utc(previous), "days": (previous - start) // DAY_MS + 1, "start_open_at": iso_utc(start)})
    return segments


def feature_ready_counts(segments: list[dict], warmup_days: int) -> tuple[dict[str, int], dict[str, int]]:
    years: Counter[str] = Counter()
    months: Counter[str] = Counter()
    for segment in segments:
        start = datetime.fromisoformat(segment["start_open_at"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(segment["end_open_at"].replace("Z", "+00:00"))
        decision = start + timedelta(days=warmup_days)
        last_decision = end + timedelta(days=1)
        while decision <= last_decision and decision < datetime(2026, 1, 1, tzinfo=UTC):
            years[str(decision.year)] += 1
            months[decision.strftime("%Y-%m")] += 1
            decision += timedelta(days=1)
    return dict(sorted(years.items())), dict(sorted(months.items()))


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
    if source_manifest.get("audit_id") != contract.get("audit_id") or source_manifest.get("credentials_used") is not False:
        raise ValueError("D0 v3 source identity or credential boundary failed")
    if source_manifest.get("acquisition_has_no_future_return_label_forecast_strategy_or_pnl") is not True:
        raise ValueError("D0 v3 source acquisition crossed the label/model boundary")
    for item in contract["bound_inputs"]:
        if sha256_path(ROOT / item["path"]) != item["sha256"]:
            raise ValueError(f"bound input checksum mismatch: {item['path']}")

    spot, spot_summary = load_monthly(source_manifest, "spot")
    perpetual_monthly, perpetual_summary = load_monthly(source_manifest, "perpetual")
    rest = load_rest(source_manifest)
    daily_overlap_rows = load_daily_overlap(source_manifest)
    year_2020 = iso_to_ms("2020-01-01T00:00:00Z")
    jan_4_2020 = iso_to_ms("2020-01-04T00:00:00Z")
    year_2026 = iso_to_ms("2026-01-01T00:00:00Z")
    daily_overlap = exact_overlap(rest, daily_overlap_rows, iso_to_ms("2019-12-31T00:00:00Z"), year_2020)
    monthly_overlap = exact_overlap(rest, perpetual_monthly, year_2020, jan_4_2020)
    perpetual = {timestamp: row for timestamp, row in rest.items() if timestamp < year_2020}
    perpetual.update(perpetual_monthly)
    first_perpetual = iso_to_ms(contract["data_boundary"]["first_perpetual_day"])
    common = sorted(timestamp for timestamp in set(spot).intersection(perpetual) if first_perpetual <= timestamp < year_2026)
    segments = build_segments(common)
    feature_by_year, feature_by_month = feature_ready_counts(segments, contract["gates"]["normalization_warmup_days"])

    coverage_by_year = {}
    for year in range(2020, 2026):
        start = iso_to_ms(f"{year:04d}-01-01T00:00:00Z")
        end = iso_to_ms(f"{year + 1:04d}-01-01T00:00:00Z")
        expected = (end - start) // DAY_MS
        observed = sum(start <= value < end for value in common)
        coverage_by_year[str(year)] = {"coverage": observed / expected, "expected_days": expected, "observed_common_days": observed}
    total_expected = sum(item["expected_days"] for item in coverage_by_year.values())
    total_observed = sum(item["observed_common_days"] for item in coverage_by_year.values())
    evaluation_months = [f"{year:04d}-{month:02d}" for year in range(2021, 2026) for month in range(1, 13)]
    gate_results = {
        "all_148_monthly_archives_and_sidecars_pass": len(source_manifest["archive_records"]) == 148 and source_manifest["archive_failures"] == 0,
        "daily_archive_overlap_exact": daily_overlap["exact_match"],
        "direct_perpetual_daily_continuous": perpetual_summary["archive_count"] == 72 and perpetual_summary["gap_count"] == 0,
        "direct_spot_daily_continuous": spot_summary["archive_count"] == 76 and spot_summary["gap_count"] == 0,
        "evaluation_common_coverage_at_least_99pct": total_observed / total_expected >= contract["gates"]["overall_common_daily_coverage_minimum"],
        "every_2020_2025_year_common_coverage_at_least_98pct": all(
            item["coverage"] >= contract["gates"]["yearly_common_daily_coverage_minimum"] for item in coverage_by_year.values()
        ),
        "every_2021_2025_month_feature_ready": all(feature_by_month.get(month, 0) > 0 for month in evaluation_months),
        "every_2021_2025_year_at_least_330_feature_ready_days": all(
            feature_by_year.get(str(year), 0) >= contract["gates"]["feature_ready_days_each_evaluation_year_minimum"] for year in range(2021, 2026)
        ),
        "pre_2021_feature_ready_days_at_least_300": sum(count for year, count in feature_by_year.items() if int(year) < 2021) >= contract["gates"]["feature_ready_days_before_2021_minimum"],
        "rest_to_monthly_overlap_exact": monthly_overlap["exact_match"],
        "source_and_output_remain_label_model_strategy_pnl_free": True,
    }
    passed = all(gate_results.values())
    segment_report = {
        "audit_id": contract["audit_id"],
        "common_day_count": len(common),
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
        "common_daily": {
            "coverage_2020_2025": total_observed / total_expected,
            "coverage_by_year": coverage_by_year,
            "first_common_open_at": iso_utc(common[0]),
            "last_common_open_at": iso_utc(common[-1]),
            "segment_count": len(segments),
        },
        "contract": {"path": str(CONTRACT_PATH.relative_to(ROOT)), "sha256": sha256_path(CONTRACT_PATH)},
        "d0_passed": passed,
        "daily_archive_overlap": daily_overlap,
        "decision": "d0_v3_passed_label_blind_data_qualification" if passed else "d0_v3_rejected_label_blind_data_qualification",
        "feature_availability": {
            "by_year": feature_by_year,
            "evaluation_months_missing": [month for month in evaluation_months if feature_by_month.get(month, 0) == 0],
            "pre_2021_count": sum(count for year, count in feature_by_year.items() if int(year) < 2021),
            "warmup_days": contract["gates"]["normalization_warmup_days"],
        },
        "gate_results": gate_results,
        "monthly_archive_overlap": monthly_overlap,
        "next_stage": "freeze_D1_with_daily_input_formulas_before_any_future_return_label_or_model" if passed else "stop_without_D1",
        "no_future_return_label_forecast_strategy_pnl_position_or_order_computed": True,
        "perpetual_daily": {
            "canonical_first_open_at": iso_utc(min(perpetual)),
            "canonical_last_open_at": iso_utc(max(perpetual)),
            "canonical_row_count": len(perpetual),
            "monthly": perpetual_summary,
            "rest_pre_2020_rows": sum(timestamp < year_2020 for timestamp in rest),
        },
        "segment_report": {"path": str(segment_path.relative_to(ROOT)), "sha256": sha256_path(segment_path)},
        "source_manifest": {"path": str(source_manifest_path.relative_to(ROOT)), "sha256": sha256_path(source_manifest_path)},
        "spot_daily": spot_summary,
    }
    report_path = output / "audit-report.json"
    report_path.write_bytes(canonical_bytes(report))
    evidence_paths = [source_manifest_path, segment_path, report_path, ROOT / source_manifest["rest_daily"]["path"], ROOT / source_manifest["futures_daily_overlap"]["archive_path"], ROOT / source_manifest["futures_daily_overlap"]["official_checksum_path"]]
    for item in source_manifest["archive_records"]:
        if item["status"] != "failed":
            evidence_paths.extend((ROOT / item["archive_path"], ROOT / item["official_checksum_path"]))
    evidence_manifest = {
        "audit_id": contract["audit_id"],
        "files": [{"path": str(path.relative_to(ROOT)), "sha256": sha256_path(path)} for path in evidence_paths],
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
