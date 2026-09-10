#!/usr/bin/env python3
"""Label-blind D0 v2 audit using official direct spot-hourly archives."""

from __future__ import annotations

import argparse
import csv
import importlib.util
import io
import json
import zipfile
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "research/btc/contracts/btc-spot-perp-continuation-data-audit-v2.json"
DEFAULT_OUTPUT = ROOT / "artifacts/agent-level-experiment/btc-focused/spot-perp-continuation-d0-v2"
UTC = timezone.utc
HOUR_MS = 3_600_000


def load_v1_module():
    path = ROOT / "scripts/audit_btc_spot_perp_continuation_data.py"
    spec = importlib.util.spec_from_file_location("spot_perp_d0_v1_audit", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


V1 = load_v1_module()
canonical_bytes = V1.canonical_bytes
sha256_path = V1.sha256_path
iso_to_ms = V1.iso_to_ms
iso_utc = V1.iso_utc
load_bound_perpetual = V1.load_bound_perpetual
load_rest_rows = V1.load_rest_rows
load_daily_overlap = V1.load_daily_overlap
load_spot_hourly = V1.load_spot_hourly
exact_overlap = V1.exact_overlap
build_segments = V1.build_segments
feature_ready_counts = V1.feature_ready_counts


def spot_timestamp_ms(raw: object, *, close_time: bool = False) -> int:
    value = int(raw)
    if value >= 100_000_000_000_000:
        remainder = value % 1000
        if (not close_time and remainder != 0) or (close_time and remainder != 999):
            raise ValueError("unexpected spot microsecond timestamp remainder")
        value //= 1000
    if value < 1_000_000_000_000:
        raise ValueError("timestamp is too small")
    return value


def parse_spot_kline(row: list[object]) -> tuple:
    if len(row) != 12:
        raise ValueError("spot kline does not have 12 fields")
    opened = spot_timestamp_ms(row[0])
    closed = spot_timestamp_ms(row[6], close_time=True)
    if opened % HOUR_MS or closed != opened + HOUR_MS - 1:
        raise ValueError("spot kline is not an exact completed hour")
    try:
        opening, high, low, close = (Decimal(str(row[index])) for index in (1, 2, 3, 4))
        base_volume = Decimal(str(row[5]))
        quote_volume = Decimal(str(row[7]))
        trade_count = int(row[8])
        taker_buy_base = Decimal(str(row[9]))
        taker_buy_quote = Decimal(str(row[10]))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("invalid numeric spot-kline field") from exc
    if min(opening, high, low, close) <= 0:
        raise ValueError("non-positive spot price")
    if high < max(opening, close) or low > min(opening, close) or high < low:
        raise ValueError("invalid spot OHLC ordering")
    if min(base_volume, quote_volume, taker_buy_base, taker_buy_quote) < 0 or trade_count < 0:
        raise ValueError("negative spot volume or trade count")
    if taker_buy_base > base_volume or taker_buy_quote > quote_volume:
        raise ValueError("spot taker-buy volume exceeds total volume")
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


def load_direct_spot(source_manifest: dict) -> tuple[dict[int, tuple], dict]:
    records = source_manifest["spot_archive_records"]
    rows: dict[int, tuple] = {}
    units: Counter[str] = Counter()
    for record in records:
        if record["status"] == "failed":
            continue
        path = ROOT / record["archive_path"]
        if sha256_path(path) != record["archive_sha256"] or record["archive_sha256"] != record["official_checksum"]:
            raise ValueError(f"spot archive checksum mismatch: {record['archive_path']}")
        for raw in csv_rows(path):
            parsed = parse_spot_kline(raw)
            opened = parsed[0]
            if opened in rows:
                if rows[opened] != parsed:
                    raise ValueError(f"conflicting duplicate spot hour: {iso_utc(opened)}")
                raise ValueError(f"duplicate spot hour: {iso_utc(opened)}")
            rows[opened] = parsed
            units["microseconds" if int(raw[0]) >= 100_000_000_000_000 else "milliseconds"] += 1
    ordered = sorted(rows)
    gaps = [
        {"left": iso_utc(left), "right": iso_utc(right), "missing_hours": (right - left) // HOUR_MS - 1}
        for left, right in zip(ordered, ordered[1:])
        if right - left != HOUR_MS
    ]
    return rows, {
        "archive_count": len(records),
        "archive_failures": sum(item["status"] == "failed" for item in records),
        "first_open_at": None if not ordered else iso_utc(ordered[0]),
        "gap_count": len(gaps),
        "gaps": gaps,
        "last_open_at": None if not ordered else iso_utc(ordered[-1]),
        "row_count": len(rows),
        "timestamp_units": dict(sorted(units.items())),
    }


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
        raise ValueError("D0 v2 source identity or credential boundary failed")
    if source_manifest.get("acquisition_has_no_future_return_label_forecast_strategy_or_pnl") is not True:
        raise ValueError("D0 v2 source acquisition crossed the label/model boundary")
    for item in contract["bound_inputs"]:
        if sha256_path(ROOT / item["path"]) != item["sha256"]:
            raise ValueError(f"bound input checksum mismatch: {item['path']}")

    parent_source_path = ROOT / contract["bound_inputs_by_role"]["parent_d0_v1_source_manifest"]["path"]
    parent_source = json.loads(parent_source_path.read_text(encoding="utf-8"))
    if parent_source.get("revision_count") != 0:
        raise ValueError("parent D0 detected a perpetual archive revision")
    rest = load_rest_rows(parent_source)
    daily = load_daily_overlap(parent_source)
    monthly_perpetual, monthly_perpetual_summary = load_bound_perpetual(contract)
    spot, spot_summary = load_direct_spot(source_manifest)

    first_perpetual = iso_to_ms(contract["data_boundary"]["first_perpetual_hour"])
    year_2020 = iso_to_ms("2020-01-01T00:00:00Z")
    jan_3_2020 = iso_to_ms("2020-01-03T00:00:00Z")
    year_2026 = iso_to_ms("2026-01-01T00:00:00Z")
    daily_overlap = exact_overlap(rest, daily, iso_to_ms("2019-12-31T00:00:00Z"), year_2020)
    perpetual_overlap = exact_overlap(rest, monthly_perpetual, year_2020, jan_3_2020)
    perpetual = {timestamp: row for timestamp, row in rest.items() if timestamp < year_2020}
    perpetual.update(monthly_perpetual)

    common = sorted(
        timestamp for timestamp in set(spot).intersection(perpetual)
        if first_perpetual <= timestamp < year_2026
    )
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

    legacy_aggregate, legacy_summary = load_spot_hourly(contract, first_perpetual, year_2026)
    diagnostic_hours = sorted(set(legacy_aggregate).intersection(spot).intersection(common))
    close_mismatches = sum(legacy_aggregate[timestamp]["close"] != spot[timestamp][4] for timestamp in diagnostic_hours)
    quote_volume_mismatches = sum(legacy_aggregate[timestamp]["quote_volume"] != spot[timestamp][7] for timestamp in diagnostic_hours)

    gate_results = {
        "all_76_direct_spot_archives_and_sidecars_pass": spot_summary["archive_count"] == 76 and spot_summary["archive_failures"] == 0,
        "daily_perpetual_archive_overlap_exact": daily_overlap["exact_match"],
        "direct_spot_hourly_continuous_over_boundary": spot_summary["gap_count"] == 0,
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
        "parent_all_72_perpetual_sidecars_unchanged": len(parent_source["monthly_sidecar_rechecks"]) == 72 and parent_source["revision_count"] == 0,
        "pre_2021_feature_ready_days_at_least_300": sum(
            count for year, count in feature_by_year.items() if int(year) < 2021
        ) >= contract["gates"]["feature_ready_days_before_2021_minimum"],
        "rest_to_2020_perpetual_monthly_overlap_exact": perpetual_overlap["exact_match"],
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
            "first_common_open_at": iso_utc(common[0]),
            "last_common_open_at": iso_utc(common[-1]),
            "segment_count": len(segments),
        },
        "contract": {"path": str(CONTRACT_PATH.relative_to(ROOT)), "sha256": sha256_path(CONTRACT_PATH)},
        "d0_passed": passed,
        "decision": "d0_v2_passed_label_blind_data_qualification" if passed else "d0_v2_rejected_label_blind_data_qualification",
        "direct_spot": spot_summary,
        "feature_availability": {
            "by_year": feature_by_year,
            "evaluation_months_missing": [month for month in evaluation_months if feature_by_month.get(month, 0) == 0],
            "pre_2021_count": sum(count for year, count in feature_by_year.items() if int(year) < 2021),
            "warmup_days": contract["gates"]["normalization_warmup_days"],
        },
        "gate_results": gate_results,
        "legacy_5m_aggregate_diagnostic": {
            "close_mismatch_hours": close_mismatches,
            "compared_complete_hours": len(diagnostic_hours),
            "legacy_summary": legacy_summary,
            "not_a_gate": True,
            "quote_volume_mismatch_hours": quote_volume_mismatches,
            "source_precedence": "official_direct_1h",
        },
        "next_stage": "freeze_D1_before_any_future_return_label_or_model" if passed else "stop_without_D1",
        "no_future_return_label_forecast_strategy_pnl_position_or_order_computed": True,
        "perpetual": {
            "canonical_first_open_at": iso_utc(min(perpetual)),
            "canonical_last_open_at": iso_utc(max(perpetual)),
            "canonical_row_count": len(perpetual),
            "monthly_2020_2025": monthly_perpetual_summary,
            "rest_pre_2020_rows": sum(timestamp < year_2020 for timestamp in rest),
        },
        "segment_report": {"path": str(segment_path.relative_to(ROOT)), "sha256": sha256_path(segment_path)},
        "source_manifest": {"path": str(source_manifest_path.relative_to(ROOT)), "sha256": sha256_path(source_manifest_path)},
    }
    report_path = output / "audit-report.json"
    report_path.write_bytes(canonical_bytes(report))
    evidence_paths = [source_manifest_path, segment_path, report_path]
    for item in source_manifest["spot_archive_records"]:
        if item["status"] != "failed":
            evidence_paths.extend((ROOT / item["archive_path"], ROOT / item["official_checksum_path"]))
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
