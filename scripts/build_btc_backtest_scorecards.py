#!/usr/bin/env python3
"""Build supplemental BTC scorecards from frozen, offline evidence through 2025."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from scripts import backtest_btc_positive_funding_carry as carry_runner
from trading_platform.btc_carry import CarryParameters, run_carry_backtest, utc_ms
from trading_platform.research_metrics import (
    DAY_MS,
    EquityObservation,
    TradeObservation,
    build_backtest_scorecard,
    canonical_bytes,
    validate_trial_registry,
)
from trading_platform.research_volatility import CandlePoint, load_candles, parse_utc_ms


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "research/btc/contracts/btc-backtest-scorecard-v1.json"
TRIAL_PATH = ROOT / "research/btc/STRATEGY_TRIALS.jsonl"
S2_ROOT = ROOT / "artifacts/agent-level-experiment/btc-regime-routing/s2-ewma-v2"
S2_CONTRACT_PATH = ROOT / "config/experiments/btc-regime-routing-s2-ewma-v2.json"
S5_REPORT_PATH = ROOT / "artifacts/agent-level-experiment/btc-regime-routing/s5-breakout-mechanism-v1/s5-breakout-mechanism-report.json"
CARRY_REPORT_PATH = ROOT / "artifacts/agent-level-experiment/btc-focused/positive-funding-carry-v1/report.json"
DEFAULT_OUTPUT = ROOT / "artifacts/agent-level-experiment/btc-focused/backtest-scorecard-v1"
UTC = timezone.utc


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path.relative_to(ROOT)}")
    return value


def verify_contract() -> dict[str, Any]:
    contract = load_json(CONTRACT_PATH)
    if (
        contract.get("schema_version") != "btc-backtest-scorecard-contract-v1"
        or contract.get("status") != "frozen_before_supplemental_recalculation"
        or contract.get("actionable_arm_id") != "no_trade"
        or contract.get("accepted_strategy_arms")
    ):
        raise ValueError("scorecard contract is not frozen and fail-closed")
    for item in contract["bound_inputs"]:
        path = ROOT / item["path"]
        if not path.is_file() or sha256_path(path) != item["sha256"]:
            raise ValueError(f"missing or changed bound scorecard input: {item['path']}")
    forbidden = set(contract["prohibited"])
    for required in (
        "2026_data_access",
        "partial_OB0_access",
        "network_or_protected_service_access",
        "credentials_or_orders",
        "regime_model_fitting",
        "strategy_parameter_tuning",
        "historical_report_overwrite",
    ):
        if required not in forbidden:
            raise ValueError(f"scorecard prohibition missing: {required}")
    return contract


def load_trials() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    raw = TRIAL_PATH.read_text(encoding="utf-8")
    if not raw.endswith("\n"):
        raise ValueError("trial registry must be newline terminated")
    rows: list[dict[str, Any]] = []
    for line in raw.splitlines():
        value = json.loads(line)
        if json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) != line:
            raise ValueError("trial registry must be canonical JSONL")
        rows.append(value)
    return rows, validate_trial_registry(rows)


def iter_gzip_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"JSONL object required: {path.relative_to(ROOT)}")
            yield value


def locked_daily_equity(
    candles: Sequence[CandlePoint],
    trade_rows: Sequence[Mapping[str, Any]],
    start_ms: int,
    end_ms: int,
) -> list[EquityObservation]:
    trades = sorted(trade_rows, key=lambda item: (int(item["entry_row"]), str(item["opportunity_id"])))
    for left, right in zip(trades, trades[1:]):
        if int(right["entry_row"]) <= int(left["exit_row"]):
            raise ValueError("locked scorecard trades overlap")
    trade_index = 0
    current = trades[0] if trades else None
    settled_cash = 1000.0
    daily_end: dict[date, float] = {}
    for index, candle in enumerate(candles):
        if candle.open_ms < start_ms or candle.open_ms >= end_ms:
            continue
        while current is not None and index > int(current["exit_row"]):
            settled_cash = float(current["cash_after"])
            trade_index += 1
            current = trades[trade_index] if trade_index < len(trades) else None
        if current is not None and int(current["entry_row"]) <= index <= int(current["exit_row"]):
            equity = (
                float(current["cash_after"])
                if index == int(current["exit_row"])
                else float(current["remaining_cash"]) + float(current["quantity"]) * candle.close
            )
        else:
            equity = settled_cash
        day = datetime.fromtimestamp(candle.open_ms / 1000, tz=UTC).date()
        daily_end[day] = equity
    output: list[EquityObservation] = []
    current_day = datetime.fromtimestamp(start_ms / 1000, tz=UTC).date()
    end_day = datetime.fromtimestamp(end_ms / 1000, tz=UTC).date()
    prior = 1000.0
    while current_day < end_day:
        if current_day in daily_end:
            prior = daily_end[current_day]
        output.append(
            EquityObservation(
                int(datetime.combine(current_day, datetime.min.time(), tzinfo=UTC).timestamp() * 1000),
                prior,
            )
        )
        current_day += timedelta(days=1)
    if not output:
        raise ValueError("locked simulation produced no daily equity")
    return output


def locked_trades(rows: Sequence[Mapping[str, Any]]) -> list[TradeObservation]:
    output: list[TradeObservation] = []
    for row in rows:
        allocation = float(row["allocation_fraction"])
        if allocation <= 0:
            continue
        allocated = float(row["cash_before"]) * allocation
        output.append(
            TradeObservation(
                trade_id=str(row["opportunity_id"]),
                entry_ms=int(row["entry_ms"]),
                exit_ms=int(row["exit_ms"]),
                pnl_quote=float(row["pnl_quote"]),
                allocated_quote=allocated,
                cost_quote=float(row["transaction_cost_quote"]),
                turnover_quote=2 * allocated,
            )
        )
    return output


def flat_like(path: Sequence[EquityObservation], starting: float = 1000.0) -> list[EquityObservation]:
    return [EquityObservation(item.day_ms, starting, item.segment) for item in path]


def score_directional(
    contract: Mapping[str, Any], trial_rows: Sequence[Mapping[str, Any]]
) -> tuple[dict[str, Any], dict[str, Any]]:
    s2_contract = load_json(S2_CONTRACT_PATH)
    s2_report = load_json(S2_ROOT / "s2-ewma-report.json")
    s2_manifest = load_json(S2_ROOT / "manifest.json")
    s5_report = load_json(S5_REPORT_PATH)
    candle_spec = s2_contract["data"]["s1_source_artifacts"]["candles-5m.jsonl.gz"]
    candle_path = ROOT / s2_contract["data"]["s1_source_root"] / "candles-5m.jsonl.gz"
    candles = load_candles(candle_path, candle_spec["sha256"], candle_spec["expected_rows"])
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in iter_gzip_jsonl(S2_ROOT / "simulation-trades.jsonl.gz"):
        grouped[(str(row["scenario_id"]), str(row["control_id"]))].append(row)
    start_ms = parse_utc_ms(s2_contract["data"]["evaluation_start"])
    end_ms = parse_utc_ms(s2_contract["data"]["evaluation_end_exclusive"])
    primary_id = "candle-primary-30bps-rt-v1"
    severe_id = "candle-severe-80bps-rt-v1"

    required_controls = (
        "flat_no_trade",
        "constant_capital_time_matched_breakout",
        "fixed_10_percent_segmented_btc_participation",
    )
    needed = {
        "fixed_10_percent_breakout",
        "primary_ewma_scaled_breakout",
        *required_controls,
    }
    paths = {
        identifier: locked_daily_equity(candles, grouped[(primary_id, identifier)], start_ms, end_ms)
        for identifier in sorted(needed)
    }
    severe_paths = {
        identifier: locked_daily_equity(candles, grouped[(severe_id, identifier)], start_ms, end_ms)
        for identifier in ("fixed_10_percent_breakout", "primary_ewma_scaled_breakout")
    }
    for identifier, path in paths.items():
        expected = float(s2_report["simulations"][primary_id][identifier]["ending_equity"])
        if not math.isclose(path[-1].equity, expected, rel_tol=0, abs_tol=1e-9):
            raise ValueError(f"legacy S2 daily-equity parity failed: {identifier}")
    for identifier, path in severe_paths.items():
        expected = float(s2_report["simulations"][severe_id][identifier]["ending_equity"])
        if not math.isclose(path[-1].equity, expected, rel_tol=0, abs_tol=1e-9):
            raise ValueError(f"legacy S2 severe parity failed: {identifier}")

    fixed_summary = s2_report["simulations"][primary_id]["fixed_10_percent_breakout"]
    fixed_rows = grouped[(primary_id, "fixed_10_percent_breakout")]
    fixed_cost = float(fixed_summary["total_transaction_cost_quote"])
    fixed_net = float(fixed_summary["ending_equity"]) - 1000.0
    fixed = build_backtest_scorecard(
        experiment_id="btc-fixed-20d-10d-breakout-legacy-control",
        strategy_family="btc-directional-trend",
        evaluation_role="alpha_strategy",
        evidence_partition="btc-development-2019-2025-consumed",
        source_digest=sha256_path(ROOT / s2_contract["data"]["s1_source_root"] / "manifest.json"),
        result_digest=sha256_path(S5_REPORT_PATH),
        original_disposition="development_mechanism_rejected",
        equity=paths["fixed_10_percent_breakout"],
        starting_equity=1000.0,
        trades=locked_trades(fixed_rows),
        controls={identifier: paths[identifier] for identifier in required_controls},
        required_control_ids=required_controls,
        dependence_days=14,
        severe_cost_net_return=float(
            s2_report["simulations"][severe_id]["fixed_10_percent_breakout"]["net_return"]
        ),
        cost_summary={
            "gross_profit_quote": fixed_net + fixed_cost,
            "net_profit_quote": fixed_net,
            "total_cost_quote": fixed_cost,
            "turnover_quote": float(fixed_summary["turnover_on_starting_equity"]) * 1000.0,
        },
        trial_history_complete=False,
        annual_trial_sharpes=[
            float(row["annualized_sharpe"])
            for row in trial_rows
            if row["strategy_family"] == "btc-directional-trend"
            and row.get("annualized_sharpe") is not None
        ],
        strategy_specific_gates=s5_report["gates"],
        bootstrap_replications=int(contract["statistics"]["bootstrap_replications"]),
    )

    ewma_summary = s2_report["simulations"][primary_id]["primary_ewma_scaled_breakout"]
    ewma_rows = grouped[(primary_id, "primary_ewma_scaled_breakout")]
    ewma_cost = float(ewma_summary["total_transaction_cost_quote"])
    ewma_net = float(ewma_summary["ending_equity"]) - 1000.0
    ewma = build_backtest_scorecard(
        experiment_id="btc-regime-routing-s2-ewma-v2",
        strategy_family="btc-directional-trend-risk-control",
        evaluation_role="risk_overlay",
        evidence_partition="btc-development-2019-2025-consumed",
        source_digest=sha256_path(S2_ROOT / "manifest.json"),
        result_digest=sha256_path(S2_ROOT / "s2-ewma-report.json"),
        original_disposition=str(s2_report["decision"]),
        equity=paths["primary_ewma_scaled_breakout"],
        starting_equity=1000.0,
        trades=locked_trades(ewma_rows),
        controls={
            "fixed_10_percent_breakout": paths["fixed_10_percent_breakout"],
            "flat_no_trade": paths["flat_no_trade"],
        },
        required_control_ids=["fixed_10_percent_breakout", "flat_no_trade"],
        dependence_days=14,
        severe_cost_net_return=float(
            s2_report["simulations"][severe_id]["primary_ewma_scaled_breakout"]["net_return"]
        ),
        cost_summary={
            "gross_profit_quote": ewma_net + ewma_cost,
            "net_profit_quote": ewma_net,
            "total_cost_quote": ewma_cost,
            "turnover_quote": float(ewma_summary["turnover_on_starting_equity"]) * 1000.0,
        },
        trial_history_complete=False,
        annual_trial_sharpes=[],
        strategy_specific_gates={
            "development_overlay_gate_met": bool(s2_report["development_overlay_gate_met"]),
            "historical_benchmark_disposition_preserved": s2_report["decision"] == "s2_passed_benchmark_frozen",
        },
        bootstrap_replications=int(contract["statistics"]["bootstrap_replications"]),
    )
    lineage = {
        "candle_rows": len(candles),
        "holdout_accessed": bool(s2_report["holdout_accessed"]),
        "manifest_decision": s2_manifest["decision"],
        "year_2026_accessed": False,
    }
    return fixed, {"scorecard": ewma, "lineage": lineage}


def reconstruct_carry_daily_equity(
    result: Mapping[str, Any],
    *,
    spot: Mapping[int, Any],
    future: Mapping[int, Any],
    mark: Mapping[int, Any],
    funding: Sequence[Any],
    scenario: Any,
    start_ms: int,
    end_ms: int,
    include_funding: bool = True,
) -> list[EquityObservation]:
    """Reconstruct daily marks from the immutable legacy trade ledger without changing it."""

    rows = sorted(result["trades"], key=lambda item: int(item["entry_ms"]))
    settled = Decimal("1000")
    index = 0
    output: list[EquityObservation] = []
    day_ms = start_ms - start_ms % DAY_MS
    final_day = end_ms - end_ms % DAY_MS
    while day_ms <= final_day:
        final_hour = day_ms + 23 * 3_600_000
        while index < len(rows) and int(rows[index]["exit_ms"]) <= final_hour:
            settled += Decimal(str(rows[index]["net_pnl"]))
            index += 1
        marked = settled
        if index < len(rows):
            row = rows[index]
            entry = int(row["entry_ms"])
            exit_time = int(row["exit_ms"])
            if entry <= final_hour < exit_time:
                if final_hour not in spot or final_hour not in future:
                    raise ValueError("carry scorecard daily mark is unavailable")
                quantity = Decimal(str(row["quantity_BTC"]))
                spot_entry_fill = spot[entry].open * (
                    Decimal("1") + scenario.implicit_bps_per_fill / Decimal("10000")
                )
                future_entry_fill = future[entry].open * (
                    Decimal("1") - scenario.implicit_bps_per_fill / Decimal("10000")
                )
                entry_fees = quantity * (spot_entry_fill + future_entry_fill) * scenario.fee_bps_per_fill / Decimal("10000")
                accrued = Decimal("0")
                if include_funding:
                    for event in funding:
                        if entry < event.scheduled_ms <= final_hour:
                            if event.scheduled_ms not in mark:
                                raise ValueError("carry funding mark is unavailable")
                            accrued += quantity * mark[event.scheduled_ms].open * event.rate
                marked += (
                    quantity * (spot[final_hour].close - spot_entry_fill)
                    + quantity * (future_entry_fill - future[final_hour].close)
                    + accrued
                    - entry_fees
                )
        output.append(EquityObservation(day_ms, float(marked)))
        day_ms += DAY_MS
    if not math.isclose(
        output[-1].equity,
        float(result["metrics"]["final_equity"]),
        rel_tol=0,
        abs_tol=1e-9,
    ):
        raise ValueError("carry daily-equity reconstruction does not match final equity")
    return output


def carry_trades(
    rows: Sequence[Mapping[str, Any]],
    spot: Mapping[int, Any],
    future: Mapping[int, Any],
) -> list[TradeObservation]:
    output: list[TradeObservation] = []
    for index, row in enumerate(rows):
        entry = int(row["entry_ms"])
        exit_time = int(row["exit_ms"])
        quantity = float(row["quantity_BTC"])
        entry_notional = quantity * (float(spot[entry].open) + float(future[entry].open))
        turnover = entry_notional + quantity * (
            float(spot[exit_time].open) + float(future[exit_time].open)
        )
        output.append(
            TradeObservation(
                trade_id=f"carry-{entry}-{index}",
                entry_ms=entry,
                exit_ms=exit_time,
                pnl_quote=float(row["net_pnl"]),
                allocated_quote=entry_notional,
                cost_quote=float(row["explicit_fees"]) + float(row["implicit_cost"]),
                turnover_quote=turnover,
            )
        )
    return output


def score_carry(
    contract: Mapping[str, Any], trial_rows: Sequence[Mapping[str, Any]]
) -> tuple[dict[str, Any], dict[str, Any]]:
    legacy = load_json(CARRY_REPORT_PATH)
    carry_contract = load_json(carry_runner.CONTRACT_PATH)
    carry_runner.verify_contract(carry_contract)
    b2 = load_json(carry_runner.B2_SOURCE)
    records = b2["archive_records"]
    future = carry_runner.load_archive_bars(
        [item for item in records if item["series"] == "klines"], "klines"
    )
    mark = carry_runner.load_archive_bars(
        [item for item in records if item["series"] == "markPriceKlines"], "markPriceKlines"
    )
    funding = carry_runner.load_funding(
        [item for item in records if item["series"] == "fundingRate"]
    )
    recovery = load_json(carry_runner.RECOVERY_SOURCE)
    carry_runner.merge_recovery_mark(mark, recovery)
    spot, spot_audit = carry_runner.load_spot_hourly()
    scenarios = carry_runner.load_scenarios()
    params = CarryParameters()
    start = utc_ms("2024-01-01T00:00:00Z")
    end = utc_ms("2025-12-31T23:00:00Z")
    primary_id = "candle-primary-30bps-rt-v1"
    severe_id = "candle-severe-80bps-rt-v1"
    primary = run_carry_backtest(
        spot=spot,
        future=future,
        mark=mark,
        funding=funding,
        start_ms=start,
        end_ms=end,
        scenario=scenarios[primary_id],
        params=params,
    )
    severe = run_carry_backtest(
        spot=spot,
        future=future,
        mark=mark,
        funding=funding,
        start_ms=start,
        end_ms=end,
        scenario=scenarios[severe_id],
        params=params,
    )
    always_on = run_carry_backtest(
        spot=spot,
        future=future,
        mark=mark,
        funding=funding,
        start_ms=start,
        end_ms=end,
        scenario=scenarios[primary_id],
        params=params,
        mode="always_on",
    )
    no_funding = run_carry_backtest(
        spot=spot,
        future=future,
        mark=mark,
        funding=funding,
        start_ms=start,
        end_ms=end,
        scenario=scenarios[primary_id],
        params=params,
        include_funding=False,
    )
    for name, actual, expected in (
        ("primary", primary, legacy["results"]["validation"][primary_id]),
        ("severe", severe, legacy["results"]["validation"][severe_id]),
        ("always_on", always_on, legacy["controls"]["always_on_matched_carry_primary"]),
        ("no_funding", no_funding, legacy["controls"]["signal_windows_without_funding_primary"]),
    ):
        for key in (
            "net_return",
            "cagr",
            "maximum_drawdown",
            "sharpe",
            "sortino",
            "profit_factor",
            "trade_count",
        ):
            left = actual["metrics"].get(key)
            right = expected["metrics"].get(key)
            if left == right:
                continue
            if isinstance(left, (int, float)) and isinstance(right, (int, float)) and math.isclose(
                float(left), float(right), rel_tol=0, abs_tol=1e-15
            ):
                continue
            raise ValueError(f"legacy carry parity failed: {name}.{key}: {left} != {right}")
    path = reconstruct_carry_daily_equity(
        primary, spot=spot, future=future, mark=mark, funding=funding,
        scenario=scenarios[primary_id], start_ms=start, end_ms=end,
    )
    controls = {
        "always_on_matched_carry": reconstruct_carry_daily_equity(
            always_on, spot=spot, future=future, mark=mark, funding=funding,
            scenario=scenarios[primary_id], start_ms=start, end_ms=end,
        ),
        "flat_no_trade": flat_like(path),
        "signal_windows_without_funding": reconstruct_carry_daily_equity(
            no_funding, spot=spot, future=future, mark=mark, funding=funding,
            scenario=scenarios[primary_id], start_ms=start, end_ms=end, include_funding=False,
        ),
    }
    net_profit = float(primary["metrics"]["final_equity"]) - 1000.0
    explicit = float(primary["attribution"]["explicit_fees"])
    implicit = float(primary["attribution"]["implicit_cost"])
    scorecard = build_backtest_scorecard(
        experiment_id="btc-positive-funding-carry-v1",
        strategy_family="btc-delta-neutral-funding-carry",
        evaluation_role="alpha_strategy",
        evidence_partition="btc-validation-2024-2025-consumed-not-promotion-holdout",
        source_digest=sha256_path(ROOT / "artifacts/agent-level-experiment/btc-focused/positive-funding-carry-v1/evidence-manifest.json"),
        result_digest=sha256_path(CARRY_REPORT_PATH),
        original_disposition=str(legacy["decision"]),
        equity=path,
        starting_equity=1000.0,
        trades=carry_trades(primary["trades"], spot, future),
        controls=controls,
        required_control_ids=[
            "always_on_matched_carry",
            "flat_no_trade",
            "signal_windows_without_funding",
        ],
        dependence_days=84,
        severe_cost_net_return=float(severe["metrics"]["net_return"]),
        cost_summary={
            "explicit_fees_quote": explicit,
            "gross_profit_quote": net_profit + explicit + implicit,
            "implicit_cost_quote": implicit,
            "net_profit_quote": net_profit,
            "turnover_quote": float(primary["metrics"]["turnover_quote"]),
        },
        trial_history_complete=False,
        annual_trial_sharpes=[
            float(row["annualized_sharpe"])
            for row in trial_rows
            if row["strategy_family"] == "btc-delta-neutral-funding-carry"
            and row.get("annualized_sharpe") is not None
        ],
        strategy_specific_gates=legacy["gates"],
        bootstrap_replications=int(contract["statistics"]["bootstrap_replications"]),
    )
    lineage = {
        "funding_events": len(funding),
        "futures_hours": len(future),
        "mark_hours": len(mark),
        "premium_index_consumed": False,
        "legacy_headline_metrics_exact": True,
        "spot_audit": spot_audit,
        "year_2026_accessed": False,
    }
    return scorecard, lineage


def write_json(path: Path, value: object) -> None:
    path.write_text(canonical_json(value), encoding="utf-8")


def run(output: Path) -> dict[str, Any]:
    contract = verify_contract()
    trial_rows, trial_summary = load_trials()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"refusing to overwrite immutable scorecard output: {output}")
    output.mkdir(parents=True, exist_ok=True)
    fixed, ewma_bundle = score_directional(contract, trial_rows)
    carry, carry_lineage = score_carry(contract, trial_rows)
    scorecards = {
        "btc-fixed-20d-10d-breakout-legacy-control": fixed,
        "btc-positive-funding-carry-v1": carry,
        "btc-regime-routing-s2-ewma-v2": ewma_bundle["scorecard"],
    }
    file_records: list[dict[str, Any]] = []
    for experiment_id, scorecard in sorted(scorecards.items()):
        path = output / f"{experiment_id}-scorecard.json"
        write_json(path, scorecard)
        file_records.append(
            {"name": path.name, "sha256": sha256_path(path)}
        )
    report = {
        "accepted_strategy_arms": [],
        "actionable_arm_id": "no_trade",
        "decision": "scorecard_infrastructure_passed_no_strategy_accepted",
        "experiment_id": contract["experiment_id"],
        "historical_dispositions_changed": False,
        "lineage": {
            "carry": carry_lineage,
            "directional": ewma_bundle["lineage"],
            "year_2026_accessed": False,
        },
        "promotion_evidence": False,
        "scorecard_dispositions": {
            key: value["supplemental_disposition"] for key, value in sorted(scorecards.items())
        },
        "schema_version": "btc-backtest-scorecard-report-v1",
        "trial_registry": trial_summary,
    }
    report_path = output / "report.json"
    write_json(report_path, report)
    file_records.append(
        {"name": report_path.name, "sha256": sha256_path(report_path)}
    )
    manifest = {
        "actionable_arm_id": "no_trade",
        "experiment_id": contract["experiment_id"],
        "files": sorted(file_records, key=lambda item: item["name"]),
        "implementations": {
            "metric_engine": sha256_path(ROOT / "src/trading_platform/research_metrics.py"),
            "runner": sha256_path(Path(__file__).resolve()),
        },
        "inputs": {
            "contract": sha256_path(CONTRACT_PATH),
            "trial_registry": sha256_path(TRIAL_PATH),
        },
        "network_or_protected_service_accessed": False,
        "partial_ob0_accessed": False,
        "promotion_evidence": False,
        "schema_version": "btc-backtest-scorecard-manifest-v1",
        "year_2026_accessed": False,
    }
    manifest_path = output / "manifest.json"
    write_json(manifest_path, manifest)
    return report


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return value


if __name__ == "__main__":
    result = run(parser().parse_args().output)
    print(canonical_json(result), end="")
