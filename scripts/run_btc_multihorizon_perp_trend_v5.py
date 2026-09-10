#!/usr/bin/env python3
"""Execute the single frozen historical BTC multi-horizon perpetual trend v3 run."""

from __future__ import annotations

import hashlib
import json
import math
import random
import sys
from collections import defaultdict
from decimal import Decimal, ROUND_DOWN
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
for _path in (ROOT, ROOT / "src"):
    sys.path.insert(0, str(_path))

from scripts.backtest_btc_positive_funding_carry import (
    B2_SOURCE, RECOVERY_SOURCE, HOUR_MS, load_archive_bars, load_funding,
    load_scenarios, merge_recovery_mark,
)
from trading_platform.btc_carry import utc_ms
from trading_platform.btc_multihorizon_trend import (
    multihorizon_score, risk_fraction, seeded_control_directions, shocked_margin_ratio,
    target_direction,
)


CONTRACT = ROOT / "research/btc/contracts/btc-multihorizon-perp-trend-v5.json"
OUTPUT = ROOT / "artifacts/agent-level-experiment/btc-focused/multihorizon-perp-trend-v5"
BPS = Decimal("10000")
STEP = Decimal("0.00001")


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _signals(bars: dict[int, Any], start: int, end: int) -> dict[str, dict[int, tuple[int, float]]]:
    closes: list[float] = []
    random_values = iter(seeded_control_directions(3000))
    result = {name: {} for name in ("candidate_fixed", "candidate_ewma", "simple_28d", "always_long", "random")}
    day = start - start % (24 * HOUR_MS)
    while day <= end:
        completed = day - HOUR_MS
        execution = day + HOUR_MS
        if completed in bars:
            closes.append(float(bars[completed].close))
        random_direction = next(random_values)
        if len(closes) >= 85 and execution <= end:
            score = multihorizon_score(closes)
            direction = target_direction(score)
            daily_returns = [math.log(b / a) for a, b in zip(closes, closes[1:])]
            variance = sum(value * value for value in daily_returns[:20]) / 20
            for value in daily_returns[20:]:
                variance = 0.94 * variance + 0.06 * value * value
            vol = math.sqrt(variance)
            simple = 1 if closes[-1] > closes[-29] else (-1 if closes[-1] < closes[-29] else 0)
            result["candidate_fixed"][execution] = (direction, 0.25)
            result["candidate_ewma"][execution] = (direction, risk_fraction(vol))
            result["simple_28d"][execution] = (simple, 0.25)
            result["always_long"][execution] = (1, 0.25)
            result["random"][execution] = (random_direction, 0.25)
        day += 24 * HOUR_MS
    return result


def _metrics(daily: list[tuple[int, Decimal]], episodes: list[Decimal], exposure_hours: float, start_equity: Decimal) -> dict[str, Any]:
    values = [float(value) for _, value in daily]
    returns = [b / a - 1 for a, b in zip(values, values[1:]) if a > 0]
    years = max(1 / 365, len(returns) / 365)
    net = values[-1] / float(start_equity) - 1
    mean = sum(returns) / len(returns) if returns else 0
    variance = sum((x - mean) ** 2 for x in returns) / max(1, len(returns) - 1)
    vol = math.sqrt(variance) * math.sqrt(365)
    sharpe = mean / math.sqrt(variance) * math.sqrt(365) if variance > 0 else 0
    downside = math.sqrt(sum(min(0, x) ** 2 for x in returns) / max(1, len(returns))) * math.sqrt(365)
    peak = values[0]
    maxdd = 0.0
    for value in values:
        peak = max(peak, value)
        maxdd = max(maxdd, 1 - value / peak)
    positive = sum(float(x) for x in episodes if x > 0)
    negative = -sum(float(x) for x in episodes if x < 0)
    annual: dict[str, float] = {}
    monthly: dict[str, list[float]] = defaultdict(list)
    by_year: dict[int, list[float]] = defaultdict(list)
    for timestamp, value in daily:
        from datetime import datetime, timezone
        observed = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
        by_year[observed.year].append(float(value))
        monthly[f"{observed.year:04d}-{observed.month:02d}"].append(float(value))
    for year, series in by_year.items():
        annual[str(year)] = series[-1] / series[0] - 1 if len(series) > 1 else 0
    monthly_returns = [series[-1] / series[0] - 1 for series in monthly.values() if len(series) > 1]
    positive_months = sorted((value for value in monthly_returns if value > 0), reverse=True)
    concentration = sum(positive_months[:3]) / sum(positive_months) if positive_months else None
    generator = random.Random(20260905)
    bootstrap_means = sorted(
        sum(generator.choice(monthly_returns) for _ in monthly_returns) / len(monthly_returns)
        for _ in range(10000)
    ) if monthly_returns else []
    return {
        "annual_returns": annual, "cagr": (1 + net) ** (1 / years) - 1, "maximum_drawdown": maxdd,
        "net_return": net, "profit_factor": positive / negative if negative else None,
        "sharpe": sharpe, "sortino": mean * 365 / downside if downside else None,
        "volatility": vol, "closed_position_episodes": len(episodes),
        "return_per_absolute_exposure_hour": net / exposure_hours if exposure_hours else None,
        "best_three_month_positive_return_fraction": concentration,
        "monthly_mean_return_bootstrap_95pct_lower": bootstrap_means[249] if bootstrap_means else None,
    }


def _run_variant(bars: dict[int, Any], marks: dict[int, Any], funding: dict[int, Any], start: int, end: int,
                 targets: dict[int, tuple[int, float]], scenario: Any) -> dict[str, Any]:
    equity = Decimal("1000")
    signed_qty = Decimal("0")
    entry_mark = collateral = Decimal("0")
    previous_close = bars[start].open
    price_pnl = funding_pnl = costs = Decimal("0")
    exposure_hours = 0.0
    daily: list[tuple[int, Decimal]] = [(start, equity)]
    episodes: list[Decimal] = []
    episode_start: Decimal | None = None
    last_direction = 0
    risk_exits = 0
    minimum_ratio: Decimal | None = None
    pending_risk = False

    def transact(timestamp: int, price: Decimal, direction: int, fraction: float, severe: bool = False) -> None:
        nonlocal equity, signed_qty, costs, entry_mark, collateral, episode_start, last_direction
        old_direction = 1 if signed_qty > 0 else (-1 if signed_qty < 0 else 0)
        target_abs = (equity * Decimal(str(fraction)) / price).quantize(STEP, rounding=ROUND_DOWN) if direction else Decimal("0")
        target = Decimal(direction) * target_abs
        delta = target - signed_qty
        bps = Decimal("40") if severe else scenario.fee_bps_per_fill + scenario.implicit_bps_per_fill
        charge = abs(delta) * price * bps / BPS
        equity -= charge; costs += charge
        if old_direction != direction:
            if episode_start is not None:
                episodes.append(equity - episode_start)
            episode_start = equity if direction else None
        signed_qty = target; last_direction = direction
        if direction:
            entry_mark = marks[timestamp].open
            collateral = equity * Decimal("0.75")
        else:
            entry_mark = collateral = Decimal("0")

    for timestamp in range(start, end + HOUR_MS, HOUR_MS):
        bar = bars[timestamp]; mark = marks[timestamp]
        open_pnl = signed_qty * (bar.open - previous_close)
        equity += open_pnl; price_pnl += open_pnl
        if pending_risk and signed_qty:
            transact(timestamp, bar.open, 0, 0, severe=True); risk_exits += 1; pending_risk = False
        event = funding.get(timestamp)
        if event is not None and signed_qty:
            cashflow = -signed_qty * mark.open * event.rate
            equity += cashflow; funding_pnl += cashflow
        if timestamp in targets:
            direction, fraction = targets[timestamp]
            transact(timestamp, bar.open, direction, fraction)
        close_pnl = signed_qty * (bar.close - bar.open)
        equity += close_pnl; price_pnl += close_pnl
        if signed_qty:
            exposure_hours += float(abs(signed_qty) * bar.close / equity)
            ratio = shocked_margin_ratio(last_direction, abs(signed_qty), entry_mark, mark.close, collateral)
            minimum_ratio = ratio if minimum_ratio is None else min(minimum_ratio, ratio)
            pending_risk = ratio < Decimal("2")
        previous_close = bar.close
        if timestamp % (24 * HOUR_MS) == 23 * HOUR_MS:
            daily.append((timestamp, equity))
    if signed_qty:
        transact(end, bars[end].close, 0, 0)
    if daily[-1][0] != end:
        daily.append((end, equity))
    else:
        daily[-1] = (end, equity)
    return {
        "attribution": {"price_pnl": str(price_pnl), "funding_cashflow": str(funding_pnl), "costs": str(costs)},
        "minimum_shocked_margin_ratio": str(minimum_ratio) if minimum_ratio is not None else None,
        "metrics": _metrics(daily, episodes, exposure_hours, Decimal("1000")),
        "risk_exits": risk_exits,
    }


def run() -> dict[str, Any]:
    if OUTPUT.exists():
        raise FileExistsError(f"refusing to overwrite immutable historical output: {OUTPUT}")
    contract = json.loads(CONTRACT.read_text())
    if contract["status"] != "frozen_before_single_historical_run":
        raise ValueError("v3 contract not frozen")
    for item in contract["bound_inputs"]:
        if sha256_path(ROOT / item["path"]) != item["sha256"]:
            raise ValueError(f"changed v3 input: {item['path']}")
    source = json.loads(B2_SOURCE.read_text())
    records = source["archive_records"]
    bars = load_archive_bars([x for x in records if x["series"] == "klines"], "klines")
    marks = load_archive_bars([x for x in records if x["series"] == "markPriceKlines"], "markPriceKlines")
    merge_recovery_mark(marks, json.loads(RECOVERY_SOURCE.read_text()))
    funding_list = load_funding([x for x in records if x["series"] == "fundingRate"])
    funding = {x.scheduled_ms: x for x in funding_list}
    if len(bars) != 52608 or len(marks) != 52608 or len(funding) != 6576:
        raise ValueError("qualified ledgers changed")
    partitions = {
        "development": (utc_ms("2020-02-03T00:00:00Z"), utc_ms("2023-12-31T23:00:00Z")),
        "consumed_stability": (utc_ms("2024-01-01T00:00:00Z"), utc_ms("2025-12-31T23:00:00Z")),
    }
    scenarios = load_scenarios()
    results: dict[str, Any] = {}
    for partition, (start, end) in partitions.items():
        signals = _signals(bars, start, end)
        results[partition] = {}
        for scenario_id, scenario in scenarios.items():
            results[partition][scenario_id] = {
                name: _run_variant(bars, marks, funding, start, end, target, scenario)
                for name, target in signals.items()
            }
    primary = "candle-primary-30bps-rt-v1"; severe = "candle-severe-80bps-rt-v1"
    candidate_dev = results["development"][primary]["candidate_fixed"]
    candidate_eval = results["consumed_stability"][primary]["candidate_fixed"]
    gates = {
        "minimum_episodes": candidate_dev["metrics"]["closed_position_episodes"] + candidate_eval["metrics"]["closed_position_episodes"] >= 12,
        "primary_positive_both": candidate_dev["metrics"]["net_return"] > 0 and candidate_eval["metrics"]["net_return"] > 0,
        "severe_positive_both": results["development"][severe]["candidate_fixed"]["metrics"]["net_return"] > 0 and results["consumed_stability"][severe]["candidate_fixed"]["metrics"]["net_return"] > 0,
        "positive_2024_2025": all(value > 0 for value in candidate_eval["metrics"]["annual_returns"].values()),
        "primary_sharpe": candidate_dev["metrics"]["sharpe"] > 0.5 and candidate_eval["metrics"]["sharpe"] > 0.5,
        "primary_profit_factor": candidate_dev["metrics"]["profit_factor"] is not None and candidate_dev["metrics"]["profit_factor"] > 1.1,
        "maximum_drawdown": max(candidate_dev["metrics"]["maximum_drawdown"], candidate_eval["metrics"]["maximum_drawdown"]) <= 0.2,
        "beats_always_long_exposure_normalized": all(results[p][primary]["candidate_fixed"]["metrics"]["return_per_absolute_exposure_hour"] > results[p][primary]["always_long"]["metrics"]["return_per_absolute_exposure_hour"] for p in partitions),
        "beats_simple_28d_exposure_normalized": all(results[p][primary]["candidate_fixed"]["metrics"]["return_per_absolute_exposure_hour"] > results[p][primary]["simple_28d"]["metrics"]["return_per_absolute_exposure_hour"] for p in partitions),
        "margin_stress": all(results[p][primary]["candidate_fixed"]["risk_exits"] == 0 for p in partitions),
        "no_2026": max(bars) == utc_ms("2025-12-31T23:00:00Z"),
    }
    gates["best_three_month_concentration"] = all(results[p][primary]["candidate_fixed"]["metrics"]["best_three_month_positive_return_fraction"] <= 0.6 for p in partitions)
    gates["monthly_bootstrap_lower_bound"] = all(results[p][primary]["candidate_fixed"]["metrics"]["monthly_mean_return_bootstrap_95pct_lower"] > 0 for p in partitions)
    combined_annual = candidate_dev["metrics"]["annual_returns"] | candidate_eval["metrics"]["annual_returns"]
    gates["four_positive_calendar_years"] = sum(value > 0 for value in combined_annual.values()) >= 4
    passed = all(gates.values())
    report = {"accepted_strategy_arms": [], "actionable_arm_id": "no_trade", "decision": "development_candidate_passed_not_promotable" if passed else "rejected_frozen_gates", "experiment_id": contract["experiment_id"], "frozen_gates": gates, "promotion_evidence": False, "results": results, "year_2026_accessed": False}
    OUTPUT.mkdir(parents=True)
    report_path = OUTPUT / "report.json"; report_path.write_bytes(canonical_bytes(report))
    manifest = {"actionable_arm_id": "no_trade", "artifacts": [{"path": str(report_path.relative_to(ROOT)), "sha256": sha256_path(report_path)}], "bound_contract": {"path": str(CONTRACT.relative_to(ROOT)), "sha256": sha256_path(CONTRACT)}, "decision": report["decision"], "experiment_id": contract["experiment_id"], "schema_version": "btc-multihorizon-perp-trend-v3-manifest-v1"}
    manifest_path = OUTPUT / "evidence-manifest.json"; manifest_path.write_bytes(canonical_bytes(manifest))
    return report


if __name__ == "__main__":
    result = run()
    summary = {p: {s: result["results"][p][s]["candidate_fixed"]["metrics"] for s in result["results"][p]} for p in result["results"]}
    print(json.dumps({"decision": result["decision"], "gates": result["frozen_gates"], "candidate": summary}, indent=2, sort_keys=True))
