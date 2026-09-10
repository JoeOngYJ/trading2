#!/usr/bin/env python3
"""Run the frozen btc-positive-funding-carry-v1 development backtest."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import sys
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from trading_platform.btc_carry import (
    CarryCostScenario,
    CarryParameters,
    FundingEvent,
    HOUR_MS,
    HourBar,
    funding_information_test,
    run_carry_backtest,
    utc_ms,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "research/btc/contracts/btc-positive-funding-carry-v1.json"
DEFAULT_OUTPUT = ROOT / "artifacts/agent-level-experiment/btc-focused/positive-funding-carry-v1"
B2_SOURCE = ROOT / "artifacts/agent-level-experiment/btc-focused/carry-data-qualification-v1/source-manifest.json"
RECOVERY_SOURCE = ROOT / "artifacts/agent-level-experiment/btc-focused/carry-gap-recovery-v1/source-manifest.json"
SPOT_LEDGER = ROOT / "artifacts/agent-level-experiment/btc-regime-routing/s1-ledger-v1/candles-5m.jsonl.gz"
UTC = timezone.utc


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
            if first[0] not in {"open_time", "calc_time"}:
                yield first
            yield from reader


def timestamp_ms(raw: str) -> int:
    value = int(raw)
    if value >= 100_000_000_000_000:
        if value % 1000:
            raise ValueError("microsecond timestamp is not millisecond aligned")
        value //= 1000
    if value < 1_000_000_000_000:
        raise ValueError("timestamp is not epoch milliseconds")
    return value


def load_archive_bars(records: list[dict[str, Any]], series: str) -> dict[int, HourBar]:
    bars: dict[int, HourBar] = {}
    for record in records:
        for row in csv_rows(ROOT / record["archive_path"]):
            if len(row) != 12:
                raise ValueError(f"unexpected {series} kline width")
            opened = timestamp_ms(row[0])
            closed = timestamp_ms(row[6])
            if opened % HOUR_MS or closed != opened + HOUR_MS - 1 or opened in bars:
                raise ValueError(f"invalid or duplicate {series} hourly timestamp")
            bars[opened] = HourBar(opened, Decimal(row[1]), Decimal(row[4]), "official_archive")
    return bars


def load_funding(records: list[dict[str, Any]]) -> list[FundingEvent]:
    events: list[FundingEvent] = []
    for record in records:
        for row in csv_rows(ROOT / record["archive_path"]):
            if len(row) != 3 or int(row[1]) != 8:
                raise ValueError("invalid funding row")
            observed = timestamp_ms(row[0])
            scheduled = round(observed / (8 * HOUR_MS)) * 8 * HOUR_MS
            events.append(FundingEvent(scheduled, observed, Decimal(row[2])))
    events.sort(key=lambda event: event.scheduled_ms)
    if len(events) != 6576 or len({event.scheduled_ms for event in events}) != len(events):
        raise ValueError("funding archive is not the frozen complete schedule")
    return events


def merge_recovery_mark(bars: dict[int, HourBar], source: dict[str, Any]) -> None:
    for record in source["requests"]:
        if record["series"] != "markPriceKlines" or record["status"] != "valid_exact_response":
            continue
        rows = json.loads((ROOT / record["raw_path"]).read_text(encoding="utf-8"))
        for row in rows:
            opened = int(row[0])
            if opened in bars:
                raise ValueError("recovered mark row overlaps archive")
            bars[opened] = HourBar(opened, Decimal(str(row[1])), Decimal(str(row[4])), "official_REST_recovery")


def parse_iso_ms(value: str) -> int:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return int(parsed.timestamp() * 1000)


def load_spot_hourly() -> tuple[dict[int, HourBar], dict[str, Any]]:
    aggregates: dict[int, dict[str, Any]] = defaultdict(lambda: {"count": 0, "opens": [], "segments": set()})
    numeric_rows_read = 0
    with gzip.open(SPOT_LEDGER, "rt", encoding="utf-8") as handle:
        for line in handle:
            item = json.loads(line)
            opened = parse_iso_ms(item["open_at"])
            year = datetime.fromtimestamp(opened / 1000, tz=UTC).year
            if year < 2020:
                continue
            if year > 2025:
                raise ValueError("spot loader crossed the frozen 2025 boundary")
            hour = opened - opened % HOUR_MS
            aggregate = aggregates[hour]
            aggregate["count"] += 1
            aggregate["opens"].append(opened)
            aggregate["segments"].add(str(item["segment"]))
            if opened == hour:
                aggregate["open"] = Decimal(str(item["open"]))
            if opened == hour + 55 * 60_000:
                aggregate["close"] = Decimal(str(item["close"]))
            numeric_rows_read += 1
    bars: dict[int, HourBar] = {}
    partial_hours = 0
    for hour, item in aggregates.items():
        expected = list(range(hour, hour + HOUR_MS, 5 * 60_000))
        if item["count"] == 12 and item["opens"] == expected and len(item["segments"]) == 1 and "open" in item and "close" in item:
            bars[hour] = HourBar(hour, item["open"], item["close"], next(iter(item["segments"])))
        else:
            partial_hours += 1
    return bars, {
        "complete_hours": len(bars),
        "numeric_rows_read": numeric_rows_read,
        "partial_or_missing_observed_hours": partial_hours,
        "source_sha256": sha256_path(SPOT_LEDGER),
    }


def load_scenarios() -> dict[str, CarryCostScenario]:
    source = json.loads((ROOT / "config/execution_scenarios.json").read_text(encoding="utf-8"))
    result = {}
    for item in source["scenarios"]:
        if item["scenario_id"] in {
            "candle-primary-30bps-rt-v1",
            "candle-stress-40bps-rt-v1",
            "candle-severe-80bps-rt-v1",
        }:
            result[item["scenario_id"]] = CarryCostScenario(
                item["scenario_id"], Decimal(item["taker_fee_bps"]), Decimal(item["implicit_cost_bps_per_side"])
            )
    if len(result) != 3:
        raise ValueError("frozen carry cost scenarios are incomplete")
    return result


def verify_contract(contract: dict[str, Any]) -> None:
    if contract.get("status") != "frozen_before_any_strategy_outcome" or contract.get("actionable_arm_id") != "no_trade":
        raise ValueError("strategy contract is not frozen and fail-closed")
    for item in contract["bound_inputs"]:
        path = ROOT / item["path"]
        if not path.is_file() or sha256_path(path) != item["sha256"]:
            raise ValueError(f"missing or changed bound input: {item['path']}")


def _spot_control(spot: dict[int, HourBar], start: int, end: int, scenario: CarryCostScenario) -> dict[str, Any]:
    first = min(timestamp for timestamp in spot if timestamp >= start)
    last = max(timestamp for timestamp in spot if timestamp <= end)
    quantity = (Decimal("1000") * Decimal("0.49") / spot[first].open).quantize(Decimal("0.00001"))
    buy = spot[first].open * (Decimal("1") + scenario.implicit_bps_per_fill / Decimal("10000"))
    sell = spot[last].open * (Decimal("1") - scenario.implicit_bps_per_fill / Decimal("10000"))
    fees = quantity * (buy + sell) * scenario.fee_bps_per_fill / Decimal("10000")
    pnl = quantity * (sell - buy) - fees
    return {"entry_ms": first, "exit_ms": last, "net_return": float(pnl / Decimal("1000")), "pnl_quote": str(pnl)}


def _gate_number(value: Any, minimum: float) -> bool:
    if value == "Infinity":
        return True
    return value is not None and float(value) >= minimum


def run(output: Path) -> dict[str, Any]:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    verify_contract(contract)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite immutable output: {output}")
    output.mkdir(parents=True)

    b2 = json.loads(B2_SOURCE.read_text(encoding="utf-8"))
    archive_records = b2["archive_records"]
    future = load_archive_bars([item for item in archive_records if item["series"] == "klines"], "klines")
    mark = load_archive_bars([item for item in archive_records if item["series"] == "markPriceKlines"], "markPriceKlines")
    funding = load_funding([item for item in archive_records if item["series"] == "fundingRate"])
    recovery = json.loads(RECOVERY_SOURCE.read_text(encoding="utf-8"))
    merge_recovery_mark(mark, recovery)
    spot, spot_audit = load_spot_hourly()
    if len(future) != 52608 or len(mark) != 52608:
        raise ValueError("complete futures and mark ledgers are required")

    scenarios = load_scenarios()
    params = CarryParameters()
    partitions = {
        "development": (utc_ms("2020-02-03T00:00:00Z"), utc_ms("2023-12-31T23:00:00Z")),
        "validation": (utc_ms("2024-01-01T00:00:00Z"), utc_ms("2025-12-31T23:00:00Z")),
    }
    results: dict[str, Any] = {}
    for partition, (start, end) in partitions.items():
        results[partition] = {}
        for scenario_id, scenario in scenarios.items():
            results[partition][scenario_id] = run_carry_backtest(
                spot=spot, future=future, mark=mark, funding=funding, start_ms=start, end_ms=end,
                scenario=scenario, params=params,
            )

    primary_id = "candle-primary-30bps-rt-v1"
    severe_id = "candle-severe-80bps-rt-v1"
    validation_start, validation_end = partitions["validation"]
    primary = results["validation"][primary_id]
    severe = results["validation"][severe_id]
    always_on = run_carry_backtest(
        spot=spot, future=future, mark=mark, funding=funding, start_ms=validation_start, end_ms=validation_end,
        scenario=scenarios[primary_id], params=params, mode="always_on",
    )
    no_funding = run_carry_backtest(
        spot=spot, future=future, mark=mark, funding=funding, start_ms=validation_start, end_ms=validation_end,
        scenario=scenarios[primary_id], params=params, include_funding=False,
    )
    robustness = {}
    for name, lookback in (("lookback_14d", 42), ("lookback_42d", 126)):
        robustness[name] = run_carry_backtest(
            spot=spot, future=future, mark=mark, funding=funding, start_ms=validation_start, end_ms=validation_end,
            scenario=scenarios[primary_id], params=CarryParameters(lookback_events=lookback),
        )
    information = funding_information_test(funding, validation_start, validation_end, params)
    years_positive = sum(value > 0 for value in primary["metrics"]["annual_returns"].values())
    info_lower = information["month_block_95pct_interval_bps"][0]
    return_per_exposure_increment = (
        primary["metrics"]["return_per_exposed_day"] - always_on["metrics"]["return_per_exposed_day"]
        if primary["metrics"]["return_per_exposed_day"] is not None and always_on["metrics"]["return_per_exposed_day"] is not None
        else None
    )
    gates = {
        "best_three_month_concentration": primary["concentration"]["best_three_month_positive_pnl_fraction"] is not None
        and primary["concentration"]["best_three_month_positive_pnl_fraction"] <= 0.60,
        "best_trade_concentration": primary["concentration"]["best_trade_positive_pnl_fraction"] is not None
        and primary["concentration"]["best_trade_positive_pnl_fraction"] <= 0.60,
        "funding_cashflow_positive": Decimal(primary["attribution"]["funding_cashflow"]) > 0,
        "information_separation": info_lower is not None and info_lower > 0,
        "lookback_14d_positive": robustness["lookback_14d"]["metrics"]["net_return"] > 0,
        "lookback_42d_positive": robustness["lookback_42d"]["metrics"]["net_return"] > 0,
        "minimum_trades": primary["metrics"]["trade_count"] >= 4,
        "no_margin_breach": primary["counts"]["margin_breaches"] == 0 and primary["counts"]["shock_margin_breaches"] == 0,
        "primary_drawdown": primary["metrics"]["maximum_drawdown"] <= 0.10,
        "primary_net_positive": primary["metrics"]["net_return"] > 0,
        "primary_profit_factor": _gate_number(primary["metrics"]["profit_factor"], 1.10),
        "primary_sharpe": _gate_number(primary["metrics"]["sharpe"], 0.50),
        "return_per_exposed_day_beats_always_on": return_per_exposure_increment is not None and return_per_exposure_increment > 0,
        "severe_net_positive": severe["metrics"]["net_return"] > 0,
        "validation_years_positive": years_positive == 2,
    }
    passed = all(gates.values())
    controls = {
        "always_on_matched_carry_primary": always_on,
        "btc_spot_buy_and_hold_49pct_primary": _spot_control(spot, validation_start, validation_end, scenarios[primary_id]),
        "flat": {"net_return": 0.0},
        "signal_windows_funding_only_primary": {
            "net_return": float((Decimal(primary["attribution"]["funding_cashflow"]) - Decimal(primary["attribution"]["explicit_fees"]) - Decimal(primary["attribution"]["implicit_cost"])) / Decimal("1000"))
        },
        "signal_windows_without_funding_primary": no_funding,
    }
    report = {
        "accepted_strategy_arms": [],
        "actionable_arm_id": "no_trade",
        "controls": controls,
        "data_audit": {
            "funding_events": len(funding),
            "futures_hours": len(future),
            "mark_hours": len(mark),
            "premium_index_consumed": False,
            "spot": spot_audit,
            "year_2026_accessed": False,
        },
        "decision": "development_candidate_passed_not_promotable" if passed else "development_strategy_rejected",
        "experiment_id": contract["experiment_id"],
        "gates": gates,
        "information_test": information,
        "no_regime_model_or_parameter_tuning": True,
        "promotion_evidence": False,
        "results": results,
        "return_per_exposed_day_increment_vs_always_on": return_per_exposure_increment,
        "robustness": robustness,
        "strategy_passed_frozen_development_gates": passed,
    }
    report_path = output / "report.json"
    report_path.write_bytes(canonical_bytes(report))
    trades_path = output / "validation-primary-trades.jsonl"
    with trades_path.open("wb") as handle:
        for trade in primary["trades"]:
            handle.write(canonical_bytes(trade))
    evidence = {
        "experiment_id": contract["experiment_id"],
        "files": [
            {"path": str(path.relative_to(ROOT)), "sha256": sha256_path(path)}
            for path in (
                CONTRACT_PATH,
                ROOT / "config/mandates/retail-btc-delta-neutral-development-v2.json",
                ROOT / "research/btc/reports/BTC_POSITIVE_FUNDING_CARRY_PLAN.md",
                ROOT / "src/trading_platform/btc_carry.py",
                ROOT / "scripts/backtest_btc_positive_funding_carry.py",
                ROOT / "tests/test_btc_carry.py",
                report_path,
                trades_path,
            )
        ],
    }
    (output / "evidence-manifest.json").write_bytes(canonical_bytes(evidence))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    report = run(output)
    summary = {
        "decision": report["decision"],
        "gates": report["gates"],
        "validation_primary": report["results"]["validation"]["candle-primary-30bps-rt-v1"]["metrics"],
        "validation_severe": report["results"]["validation"]["candle-severe-80bps-rt-v1"]["metrics"],
    }
    print(json.dumps(summary, sort_keys=True, indent=2))
    return 0 if report["strategy_passed_frozen_development_gates"] else 2


if __name__ == "__main__":
    sys.exit(main())
