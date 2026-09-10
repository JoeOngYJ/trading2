#!/usr/bin/env python3
"""T0 data/causality preflight for the frozen BTC multi-horizon trend experiment.

This script intentionally computes no signal value, direction, position, return, cost or PnL.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for _entry in (str(ROOT), str(SRC)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from scripts.backtest_btc_positive_funding_carry import (
    B2_SOURCE,
    HOUR_MS,
    load_archive_bars,
    load_funding,
)
from trading_platform.btc_carry import utc_ms


CONTRACT = ROOT / "research/btc/contracts/btc-multihorizon-perp-trend-v1.json"
DEFAULT_OUTPUT = ROOT / "artifacts/agent-level-experiment/btc-focused/multihorizon-perp-trend-v1/t0-v2"
MAX_HORIZON_HOURS = 2016


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def contiguous_missing(timestamps: set[int], start: int, end: int, step: int) -> list[int]:
    if start > end or start % step or end % step:
        raise ValueError("invalid aligned continuity boundary")
    return [value for value in range(start, end + step, step) if value not in timestamps]


def eligible_daily_decisions(
    timestamps: set[int], start: int, end: int, horizon_hours: int = MAX_HORIZON_HOURS
) -> tuple[list[int], list[int]]:
    """Return eligible 00:05 decision anchors and ineligible anchors using timestamps only."""
    eligible: list[int] = []
    ineligible: list[int] = []
    day_ms = 24 * HOUR_MS
    day = start - start % day_ms
    if day < start:
        day += day_ms
    while day <= end:
        completed_hour = day - HOUR_MS  # 23:00 bar completes at 00:00; decision is 00:05.
        execution_hour = day + HOUR_MS  # next declared executable hourly open is 01:00.
        history_start = completed_hour - horizon_hours * HOUR_MS
        required = range(history_start, completed_hour + HOUR_MS, HOUR_MS)
        target = eligible if execution_hour <= end and all(value in timestamps for value in required) and execution_hour in timestamps else ineligible
        target.append(day + 5 * 60_000)
        day += day_ms
    return eligible, ineligible


def verify_contract(contract: dict[str, Any]) -> None:
    if (
        contract.get("experiment_id") != "btc-multihorizon-perp-trend-v1"
        or contract.get("status") != "frozen_before_strategy_return_access"
        or contract.get("action_boundary", {}).get("actionable_arm_id") != "no_trade"
    ):
        raise ValueError("trend contract is not frozen and fail closed")
    for item in contract["bound_inputs"]:
        path = ROOT / item["path"]
        if not path.is_file() or sha256_path(path) != item["sha256"]:
            raise ValueError(f"missing or changed bound input: {item['path']}")


def run(output: Path) -> dict[str, Any]:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    verify_contract(contract)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite immutable T0 output: {output}")

    source = json.loads(B2_SOURCE.read_text(encoding="utf-8"))
    selected = [row for row in source["archive_records"] if row["series"] in {"klines", "fundingRate"}]
    archive_errors: list[str] = []
    for row in selected:
        path = ROOT / row["archive_path"]
        if row.get("status") != "downloaded_and_official_checksum_matched":
            archive_errors.append(f"status:{row['archive_path']}")
        elif not path.is_file() or sha256_path(path) != row["archive_sha256"]:
            archive_errors.append(f"checksum:{row['archive_path']}")

    bars = load_archive_bars([row for row in selected if row["series"] == "klines"], "klines")
    funding = load_funding([row for row in selected if row["series"] == "fundingRate"])
    start = utc_ms("2020-02-03T00:00:00Z")
    end = utc_ms("2025-12-31T23:00:00Z")
    source_start = utc_ms("2020-01-01T00:00:00Z")
    timestamps = set(bars)
    missing_hours = contiguous_missing(timestamps, source_start, end, HOUR_MS)
    funding_start = utc_ms("2020-02-03T00:00:00Z")
    funding_end = utc_ms("2025-12-31T16:00:00Z")
    funding_times = {event.scheduled_ms for event in funding}
    missing_funding = contiguous_missing(funding_times, funding_start, funding_end, 8 * HOUR_MS)
    late_funding = [event.scheduled_ms for event in funding if event.observed_ms > event.scheduled_ms + HOUR_MS]
    eligible, ineligible = eligible_daily_decisions(timestamps, start, end)
    first_eligible = eligible[0] if eligible else None
    # At the 25 March decision, the inclusive 2,016-hour endpoint pair reaches
    # 2019-12-31 23:00, one hour before the archive. The first valid decision is 26 March.
    expected_first = utc_ms("2020-03-26T00:05:00Z")

    gates = {
        "all_selected_archives_match_official_checksums": not archive_errors,
        "hourly_2020_2025_continuity_complete": not missing_hours,
        "funding_8h_schedule_complete": not missing_funding,
        "funding_available_by_next_hour": not late_funding,
        "first_84d_feature_decision_exact": first_eligible == expected_first,
        "at_least_2000_eligible_daily_decisions": len(eligible) >= 2000,
        "warmup_or_terminal_ineligible_decision_count_exact": len(ineligible) == 52,
        "no_2026_loaded": max(timestamps) == end and max(funding_times) < utc_ms("2026-01-01T00:00:00Z"),
    }
    passed = all(gates.values())
    report = {
        "actionable_arm_id": "no_trade",
        "archive_errors": archive_errors,
        "counts": {
            "eligible_daily_decisions": len(eligible),
            "funding_events_all_archives": len(funding),
            "hourly_bars_all_archives": len(bars),
            "ineligible_warmup_or_terminal_daily_decisions": len(ineligible),
            "missing_funding_events_in_boundary": len(missing_funding),
            "missing_hours_in_boundary": len(missing_hours),
        },
        "decision": "t0_passed_implementation_permitted" if passed else "t0_rejected_fail_closed",
        "experiment_id": contract["experiment_id"],
        "first_eligible_decision_ms": first_eligible,
        "gates": gates,
        "no_signal_direction_position_cost_return_or_pnl_calculated": True,
        "strategy_return_accessed": False,
        "t1_permitted": passed,
        "year_2026_accessed": False,
    }
    output.mkdir(parents=True)
    report_path = output / "report.json"
    report_path.write_bytes(canonical_bytes(report))
    manifest = {
        "actionable_arm_id": "no_trade",
        "artifacts": [{"path": str(report_path.relative_to(ROOT)), "sha256": sha256_path(report_path)}],
        "bound_contract": {"path": str(CONTRACT.relative_to(ROOT)), "sha256": sha256_path(CONTRACT)},
        "experiment_id": contract["experiment_id"],
        "no_strategy_return_or_action_created": True,
        "schema_version": "btc-multihorizon-perp-trend-t0-manifest-v1",
    }
    manifest_path = output / "evidence-manifest.json"
    manifest_path.write_bytes(canonical_bytes(manifest))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    print(json.dumps(run(output), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
