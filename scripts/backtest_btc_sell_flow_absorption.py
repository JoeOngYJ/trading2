#!/usr/bin/env python3
"""Backtest the frozen BTC sell-flow absorption hypothesis on development data only."""

from __future__ import annotations

import argparse
import bisect
import csv
import gzip
import hashlib
import json
import math
import random
import statistics
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence


FIVE_MINUTES_MS = 300_000
HOUR_MS = 3_600_000
DAY_MS = 86_400_000
EVALUATION_START_MS = 1_546_300_800_000  # 2019-01-01T00:00:00Z
EVALUATION_END_MS = 1_767_225_600_000  # 2026-01-01T00:00:00Z
INITIAL_EQUITY = 1_000.0


@dataclass(frozen=True, slots=True)
class FiveMinuteBar:
    segment: int
    time_ms: int
    open: float
    high: float
    low: float
    close: float
    base_volume: float
    quote_volume: float
    taker_buy_base: float


@dataclass(frozen=True, slots=True)
class HourBar:
    segment: int
    time_ms: int
    open: float
    high: float
    low: float
    close: float
    quote_volume: float
    flow_imbalance: float
    log_return: float
    start_five_minute_index: int
    end_five_minute_index: int


@dataclass(frozen=True, slots=True)
class FeatureSnapshot:
    intercept: float
    beta: float
    flow_q05: float
    flow_q10: float
    flow_q15: float
    residual_q85: float
    residual_q90: float
    residual_q95: float
    volume_q50: float
    volume_q75: float
    volume_q90: float
    return_q10: float


@dataclass(frozen=True, slots=True)
class ModelParameters:
    feature_lookback_hours: int = 720
    flow_quantile: float = 0.10
    absorption_quantile: float = 0.90
    volume_quantile: float = 0.75
    holding_period_hours: int = 12
    stop_fraction: float = 0.015
    allocation_fraction: float = 0.20
    maximum_entries_per_day: int = 1


@dataclass(frozen=True, slots=True)
class ExecutionScenario:
    scenario_id: str
    side_cost_fraction: float
    price_protection_fraction: float


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def quantile(values: Sequence[float], probability: float, *, presorted: bool = False) -> float:
    if not values:
        raise ValueError("quantile requires at least one value")
    if not 0 <= probability <= 1:
        raise ValueError("probability must be between zero and one")
    ordered = values if presorted else sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def isoformat_ms(value: int) -> str:
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def load_development_bars(data_path: Path, manifest_path: Path, expected_digest: str) -> list[FiveMinuteBar]:
    for path in (data_path, manifest_path):
        if path.is_symlink():
            raise ValueError(f"symlink input refused: {path}")
        if not path.is_file():
            raise ValueError(f"missing input: {path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    digest = sha256_file(data_path)
    if manifest.get("partition") != "development-2017-2025":
        raise ValueError("only the development-2017-2025 partition is permitted")
    if not manifest.get("accepted"):
        raise ValueError("development manifest is not accepted")
    if manifest.get("dataset_sha256") != digest or digest != expected_digest:
        raise ValueError("development dataset checksum mismatch")

    bars: list[FiveMinuteBar] = []
    with gzip.open(data_path, "rt", encoding="utf-8", newline="") as handle:
        for raw in csv.DictReader(handle):
            bar = FiveMinuteBar(
                segment=int(raw["segment_id"]),
                time_ms=int(raw["open_time_ms"]),
                open=float(raw["open"]),
                high=float(raw["high"]),
                low=float(raw["low"]),
                close=float(raw["close"]),
                base_volume=float(raw["base_volume"]),
                quote_volume=float(raw["quote_volume"]),
                taker_buy_base=float(raw["taker_buy_base_volume"]),
            )
            if not (bar.low <= bar.open <= bar.high and bar.low <= bar.close <= bar.high):
                raise ValueError(f"invalid OHLC at {bar.time_ms}")
            if bar.base_volume < 0 or not 0 <= bar.taker_buy_base <= bar.base_volume or bar.quote_volume < 0:
                raise ValueError(f"invalid volume at {bar.time_ms}")
            bars.append(bar)
    if len(bars) != manifest.get("rows"):
        raise ValueError("development row count mismatch")
    return bars


def aggregate_complete_hours(bars: Sequence[FiveMinuteBar]) -> list[HourBar]:
    hours: list[HourBar] = []
    group: list[tuple[int, FiveMinuteBar]] = []
    active_key: tuple[int, int] | None = None

    def flush() -> None:
        if not group:
            return
        first_index, first = group[0]
        hour_start = first.time_ms // HOUR_MS * HOUR_MS
        expected = [hour_start + offset * FIVE_MINUTES_MS for offset in range(12)]
        if len(group) != 12 or [bar.time_ms for _, bar in group] != expected:
            return
        total_base = sum(bar.base_volume for _, bar in group)
        total_buy = sum(bar.taker_buy_base for _, bar in group)
        if total_base <= 0:
            return
        last_index, last = group[-1]
        hours.append(
            HourBar(
                segment=first.segment,
                time_ms=hour_start,
                open=first.open,
                high=max(bar.high for _, bar in group),
                low=min(bar.low for _, bar in group),
                close=last.close,
                quote_volume=sum(bar.quote_volume for _, bar in group),
                flow_imbalance=(2 * total_buy - total_base) / total_base,
                log_return=math.log(last.close / first.open),
                start_five_minute_index=first_index,
                end_five_minute_index=last_index,
            )
        )

    for index, bar in enumerate(bars):
        key = (bar.segment, bar.time_ms // HOUR_MS)
        if active_key is not None and key != active_key:
            flush()
            group = []
        group.append((index, bar))
        active_key = key
    flush()
    return hours


def ols(values_x: Sequence[float], values_y: Sequence[float]) -> tuple[float, float]:
    if len(values_x) != len(values_y) or len(values_x) < 2:
        raise ValueError("OLS requires paired observations")
    mean_x = statistics.fmean(values_x)
    mean_y = statistics.fmean(values_y)
    denominator = sum((value - mean_x) ** 2 for value in values_x)
    beta = 0.0 if denominator <= 1e-18 else sum(
        (x - mean_x) * (y - mean_y) for x, y in zip(values_x, values_y)
    ) / denominator
    return mean_y - beta * mean_x, beta


def compute_feature_snapshots(hours: Sequence[HourBar], lookback: int) -> list[FeatureSnapshot | None]:
    if lookback < 24:
        raise ValueError("lookback must be at least 24 hours")
    snapshots: list[FeatureSnapshot | None] = [None] * len(hours)
    segment_indices: dict[int, list[int]] = defaultdict(list)
    for index, hour in enumerate(hours):
        segment_indices[hour.segment].append(index)

    for indices in segment_indices.values():
        for position in range(lookback, len(indices)):
            current_index = indices[position]
            window_indices = indices[position - lookback : position]
            first = hours[window_indices[0]]
            current = hours[current_index]
            if current.time_ms - first.time_ms != lookback * HOUR_MS:
                continue
            flow = [hours[index].flow_imbalance for index in window_indices]
            returns = [hours[index].log_return for index in window_indices]
            volumes = [hours[index].quote_volume for index in window_indices]
            intercept, beta = ols(flow, returns)
            residuals = [value_y - (intercept + beta * value_x) for value_x, value_y in zip(flow, returns)]
            flow.sort()
            residuals.sort()
            volumes.sort()
            sorted_returns = sorted(returns)
            snapshots[current_index] = FeatureSnapshot(
                intercept=intercept,
                beta=beta,
                flow_q05=quantile(flow, 0.05, presorted=True),
                flow_q10=quantile(flow, 0.10, presorted=True),
                flow_q15=quantile(flow, 0.15, presorted=True),
                residual_q85=quantile(residuals, 0.85, presorted=True),
                residual_q90=quantile(residuals, 0.90, presorted=True),
                residual_q95=quantile(residuals, 0.95, presorted=True),
                volume_q50=quantile(volumes, 0.50, presorted=True),
                volume_q75=quantile(volumes, 0.75, presorted=True),
                volume_q90=quantile(volumes, 0.90, presorted=True),
                return_q10=quantile(sorted_returns, 0.10, presorted=True),
            )
    return snapshots


def threshold(snapshot: FeatureSnapshot, name: str, probability: float) -> float:
    mapping = {
        ("flow", 0.05): snapshot.flow_q05,
        ("flow", 0.10): snapshot.flow_q10,
        ("flow", 0.15): snapshot.flow_q15,
        ("residual", 0.85): snapshot.residual_q85,
        ("residual", 0.90): snapshot.residual_q90,
        ("residual", 0.95): snapshot.residual_q95,
        ("volume", 0.50): snapshot.volume_q50,
        ("volume", 0.75): snapshot.volume_q75,
        ("volume", 0.90): snapshot.volume_q90,
    }
    try:
        return mapping[(name, round(probability, 2))]
    except KeyError as exc:
        raise ValueError(f"unsupported frozen {name} quantile: {probability}") from exc


def select_signals(
    hours: Sequence[HourBar],
    snapshots: Sequence[FeatureSnapshot | None],
    parameters: ModelParameters,
    mode: str = "absorption",
) -> list[int]:
    selected: list[int] = []
    for index, (hour, snapshot) in enumerate(zip(hours, snapshots)):
        if snapshot is None or not EVALUATION_START_MS <= hour.time_ms < EVALUATION_END_MS:
            continue
        volume_ok = hour.quote_volume >= threshold(snapshot, "volume", parameters.volume_quantile)
        if mode == "absorption":
            residual = hour.log_return - (snapshot.intercept + snapshot.beta * hour.flow_imbalance)
            qualifies = (
                hour.flow_imbalance <= threshold(snapshot, "flow", parameters.flow_quantile)
                and residual >= threshold(snapshot, "residual", parameters.absorption_quantile)
                and volume_ok
            )
        elif mode == "extreme_sell_only":
            qualifies = hour.flow_imbalance <= threshold(snapshot, "flow", parameters.flow_quantile) and volume_ok
        elif mode == "price_only_reversal":
            qualifies = hour.log_return <= snapshot.return_q10 and volume_ok
        else:
            raise ValueError(f"unsupported signal mode: {mode}")
        if qualifies:
            selected.append(index)
    return selected


def load_execution_scenarios(path: Path, scenario_ids: Sequence[str]) -> dict[str, ExecutionScenario]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    available = {item["scenario_id"]: item for item in payload.get("scenarios", [])}
    result: dict[str, ExecutionScenario] = {}
    for scenario_id in scenario_ids:
        raw = available.get(scenario_id)
        if raw is None or raw.get("mode") != "candle_taker":
            raise ValueError(f"missing candle-taker scenario: {scenario_id}")
        side_bps = sum(float(raw.get(key, 0)) for key in (
            "taker_fee_bps", "implicit_cost_bps_per_side", "residual_impact_bps"
        ))
        result[scenario_id] = ExecutionScenario(
            scenario_id=scenario_id,
            side_cost_fraction=side_bps / 10_000,
            price_protection_fraction=float(raw["price_protection_bps"]) / 10_000,
        )
    return result


def independent_trade(
    signal_index: int,
    hours: Sequence[HourBar],
    bars: Sequence[FiveMinuteBar],
    parameters: ModelParameters,
    scenario: ExecutionScenario,
) -> dict[str, float | int | str] | None:
    hour = hours[signal_index]
    entry_index = hour.end_five_minute_index + 1
    exit_index = entry_index + parameters.holding_period_hours * 12
    if entry_index >= len(bars) or exit_index >= len(bars):
        return None
    entry_bar = bars[entry_index]
    exit_bar = bars[exit_index]
    expected_entry_time = hour.time_ms + HOUR_MS
    expected_exit_time = expected_entry_time + parameters.holding_period_hours * HOUR_MS
    if (
        entry_bar.segment != hour.segment
        or exit_bar.segment != hour.segment
        or entry_bar.time_ms != expected_entry_time
        or exit_bar.time_ms != expected_exit_time
    ):
        return None
    entry_price = entry_bar.open
    if entry_price > hour.close * (1 + scenario.price_protection_fraction):
        return {
            "status": "expired_price_protection",
            "signal_index": signal_index,
            "signal_time_ms": hour.time_ms,
            "entry_time_ms": entry_bar.time_ms,
        }

    stop_price = entry_price * (1 - parameters.stop_fraction)
    actual_exit_index = exit_index
    actual_exit_price = exit_bar.open
    exit_reason = "time"
    for index in range(entry_index, exit_index):
        bar = bars[index]
        if bar.segment != hour.segment:
            return None
        if bar.open <= stop_price:
            actual_exit_index = index
            actual_exit_price = bar.open
            exit_reason = "stop_gap"
            break
        if bar.low <= stop_price:
            actual_exit_index = index
            actual_exit_price = stop_price
            exit_reason = "stop"
            break

    side_cost = scenario.side_cost_fraction
    gross_return = actual_exit_price / entry_price - 1
    net_return = actual_exit_price / entry_price * (1 - side_cost) ** 2 - 1
    return {
        "status": "filled",
        "signal_index": signal_index,
        "signal_time_ms": hour.time_ms,
        "entry_index": entry_index,
        "entry_time_ms": entry_bar.time_ms,
        "entry_price": entry_price,
        "exit_index": actual_exit_index,
        "exit_time_ms": bars[actual_exit_index].time_ms,
        "exit_price": actual_exit_price,
        "exit_reason": exit_reason,
        "gross_return": gross_return,
        "net_return": net_return,
    }


def max_drawdown_path(
    equity: float,
    high_water: float,
    trade: Mapping[str, float | int | str],
    bars: Sequence[FiveMinuteBar],
    parameters: ModelParameters,
    scenario: ExecutionScenario,
) -> tuple[float, float]:
    allocation = equity * parameters.allocation_fraction
    cash = equity - allocation
    quantity = allocation * (1 - scenario.side_cost_fraction) / float(trade["entry_price"])
    maximum_drawdown = 0.0
    for index in range(int(trade["entry_index"]), int(trade["exit_index"]) + 1):
        liquidation_equity = cash + quantity * bars[index].close * (1 - scenario.side_cost_fraction)
        high_water = max(high_water, liquidation_equity)
        maximum_drawdown = min(maximum_drawdown, liquidation_equity / high_water - 1)
    return high_water, maximum_drawdown


def simulate(
    signal_indices: Sequence[int],
    hours: Sequence[HourBar],
    bars: Sequence[FiveMinuteBar],
    parameters: ModelParameters,
    scenario: ExecutionScenario,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    equity = INITIAL_EQUITY
    high_water = equity
    maximum_drawdown = 0.0
    busy_until_ms = -1
    used_days: set[int] = set()
    invalid_paths = expired = overlap_skips = daily_skips = 0
    trades: list[dict[str, object]] = []
    annual_factors = {str(year): 1.0 for year in range(2019, 2026)}
    monthly_factors: dict[str, float] = defaultdict(lambda: 1.0)
    monthly_pnl: dict[str, float] = defaultdict(float)

    for signal_index in signal_indices:
        signal_time = hours[signal_index].time_ms
        if signal_time < busy_until_ms:
            overlap_skips += 1
            continue
        day = signal_time // DAY_MS
        if day in used_days:
            daily_skips += 1
            continue
        outcome = independent_trade(signal_index, hours, bars, parameters, scenario)
        if outcome is None:
            invalid_paths += 1
            continue
        used_days.add(day)
        if outcome["status"] != "filled":
            expired += 1
            continue
        busy_until_ms = int(outcome["exit_time_ms"])
        starting_equity = equity
        high_water, path_drawdown = max_drawdown_path(
            equity, high_water, outcome, bars, parameters, scenario
        )
        maximum_drawdown = min(maximum_drawdown, path_drawdown)
        account_return = parameters.allocation_fraction * float(outcome["net_return"])
        equity *= 1 + account_return
        high_water = max(high_water, equity)
        maximum_drawdown = min(maximum_drawdown, equity / high_water - 1)
        entry_time = int(outcome["entry_time_ms"])
        year = str(datetime.fromtimestamp(entry_time / 1000, tz=timezone.utc).year)
        month = datetime.fromtimestamp(entry_time / 1000, tz=timezone.utc).strftime("%Y-%m")
        annual_factors[year] *= 1 + account_return
        monthly_factors[month] *= 1 + account_return
        monthly_pnl[month] += equity - starting_equity
        trades.append({
            **outcome,
            "signal_time": isoformat_ms(int(outcome["signal_time_ms"])),
            "entry_time": isoformat_ms(entry_time),
            "exit_time": isoformat_ms(int(outcome["exit_time_ms"])),
            "account_return": account_return,
            "starting_equity": starting_equity,
            "ending_equity": equity,
        })

    net_returns = [float(trade["net_return"]) for trade in trades]
    account_pnl = [float(trade["ending_equity"]) - float(trade["starting_equity"]) for trade in trades]
    positive = sum(value for value in account_pnl if value > 0)
    negative = -sum(value for value in account_pnl if value < 0)
    profit_factor = positive / negative if negative > 0 else (math.inf if positive > 0 else 0.0)
    annual_returns = {year: factor - 1 for year, factor in annual_factors.items()}
    positive_month_pnl = sorted((value for value in monthly_pnl.values() if value > 0), reverse=True)
    concentration = (
        sum(positive_month_pnl[:3]) / sum(positive_month_pnl) if positive_month_pnl else None
    )
    years = (EVALUATION_END_MS - EVALUATION_START_MS) / (365.2425 * DAY_MS)
    metrics: dict[str, object] = {
        "candidate_signals": len(signal_indices),
        "filled_trades": len(trades),
        "expired_price_protection": expired,
        "invalid_future_paths": invalid_paths,
        "overlap_skips": overlap_skips,
        "daily_entry_skips": daily_skips,
        "ending_equity": equity,
        "total_return": equity / INITIAL_EQUITY - 1,
        "cagr": (equity / INITIAL_EQUITY) ** (1 / years) - 1,
        "maximum_drawdown": maximum_drawdown,
        "mean_net_trade_return": statistics.fmean(net_returns) if net_returns else None,
        "median_net_trade_return": statistics.median(net_returns) if net_returns else None,
        "win_rate": sum(value > 0 for value in net_returns) / len(net_returns) if net_returns else None,
        "profit_factor": profit_factor,
        "stop_rate": sum(str(trade["exit_reason"]).startswith("stop") for trade in trades) / len(trades) if trades else None,
        "annual_returns": annual_returns,
        "positive_calendar_years": sum(value > 0 for value in annual_returns.values()),
        "monthly_returns": {month: factor - 1 for month, factor in sorted(monthly_factors.items())},
        "top_three_profitable_months_share": concentration,
    }
    return metrics, trades


def month_block_bootstrap(trades: Sequence[Mapping[str, object]], seed: int, replications: int) -> list[float]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for trade in trades:
        grouped[str(trade["entry_time"])[:7]].append(float(trade["net_return"]))
    months = list(grouped.values())
    if not months:
        return []
    rng = random.Random(seed)
    estimates: list[float] = []
    for _ in range(replications):
        sampled = [months[rng.randrange(len(months))] for _ in months]
        estimates.append(statistics.fmean(value for month in sampled for value in month))
    return estimates


def market_monthly_returns(hours: Sequence[HourBar]) -> dict[str, float]:
    grouped: dict[str, list[HourBar]] = defaultdict(list)
    for hour in hours:
        if EVALUATION_START_MS <= hour.time_ms < EVALUATION_END_MS:
            grouped[datetime.fromtimestamp(hour.time_ms / 1000, tz=timezone.utc).strftime("%Y-%m")].append(hour)
    return {
        month: values[-1].close / values[0].open - 1
        for month, values in grouped.items()
        if values
    }


def beta_attribution(strategy_monthly: Mapping[str, float], market_monthly: Mapping[str, float]) -> dict[str, float | int | None]:
    months = sorted(set(strategy_monthly) & set(market_monthly))
    if len(months) < 3:
        return {"months": len(months), "monthly_alpha": None, "beta": None}
    x = [market_monthly[month] for month in months]
    y = [strategy_monthly[month] for month in months]
    intercept, beta = ols(x, y)
    return {"months": len(months), "monthly_alpha": intercept, "beta": beta}


def buy_hold_control(hours: Sequence[HourBar], scenario: ExecutionScenario, allocation: float) -> dict[str, float]:
    eligible = [hour for hour in hours if EVALUATION_START_MS <= hour.time_ms < EVALUATION_END_MS]
    entry = eligible[0].open
    exit_price = eligible[-1].close
    asset_net = exit_price / entry * (1 - scenario.side_cost_fraction) ** 2 - 1
    return {"asset_net_return": asset_net, "account_return": allocation * asset_net}


def matched_random_test(
    primary_trades: Sequence[Mapping[str, object]],
    primary_signal_set: set[int],
    hours: Sequence[HourBar],
    bars: Sequence[FiveMinuteBar],
    snapshots: Sequence[FeatureSnapshot | None],
    parameters: ModelParameters,
    scenario: ExecutionScenario,
    seed: int,
    simulations: int,
) -> dict[str, object]:
    pools: dict[tuple[str, int], list[float]] = defaultdict(list)
    for index, (hour, snapshot) in enumerate(zip(hours, snapshots)):
        if snapshot is None or index in primary_signal_set or not EVALUATION_START_MS <= hour.time_ms < EVALUATION_END_MS:
            continue
        outcome = independent_trade(index, hours, bars, parameters, scenario)
        if not outcome or outcome["status"] != "filled":
            continue
        date = datetime.fromtimestamp(hour.time_ms / 1000, tz=timezone.utc)
        pools[(date.strftime("%Y-%m"), date.hour)].append(float(outcome["net_return"]))

    required: dict[tuple[str, int], int] = defaultdict(int)
    for trade in primary_trades:
        date = datetime.fromtimestamp(int(trade["signal_time_ms"]) / 1000, tz=timezone.utc)
        required[(date.strftime("%Y-%m"), date.hour)] += 1
    missing = {str(key): count for key, count in required.items() if len(pools.get(key, [])) < count}
    if missing or not primary_trades:
        return {"valid": False, "reason": "insufficient_matched_pool", "missing": missing}

    observed = statistics.fmean(float(trade["net_return"]) for trade in primary_trades)
    rng = random.Random(seed)
    estimates: list[float] = []
    for _ in range(simulations):
        sampled: list[float] = []
        for key, count in sorted(required.items()):
            sampled.extend(rng.sample(pools[key], count))
        estimates.append(statistics.fmean(sampled))
    exceedances = sum(value >= observed for value in estimates)
    estimates.sort()
    return {
        "valid": True,
        "simulations": simulations,
        "observed_mean_net_trade_return": observed,
        "random_mean": statistics.fmean(estimates),
        "random_ci95": [quantile(estimates, 0.025, presorted=True), quantile(estimates, 0.975, presorted=True)],
        "one_sided_p": (exceedances + 1) / (simulations + 1),
    }


def write_trades(path: Path, trades: Sequence[Mapping[str, object]]) -> None:
    fields = [
        "signal_index", "signal_time", "entry_time", "entry_price", "exit_time", "exit_price",
        "exit_reason", "gross_return", "net_return", "account_return", "starting_equity", "ending_equity",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for trade in trades:
            writer.writerow({field: trade[field] for field in fields})


def parameters_from_config(config: Mapping[str, object]) -> ModelParameters:
    model = config["primary_model"]
    mandate = config["mandate"]
    assert isinstance(model, Mapping) and isinstance(mandate, Mapping)
    return ModelParameters(
        feature_lookback_hours=int(model["feature_lookback_hours"]),
        flow_quantile=float(model["flow_quantile"]),
        absorption_quantile=float(model["absorption_quantile"]),
        volume_quantile=float(model["volume_quantile"]),
        holding_period_hours=int(model["holding_period_hours"]),
        stop_fraction=float(model["protective_stop_fraction_below_entry"]),
        allocation_fraction=float(mandate["account_fraction_per_entry"]),
        maximum_entries_per_day=int(mandate["maximum_entries_per_utc_day"]),
    )


def apply_sensitivity(parameters: ModelParameters, raw: Mapping[str, object]) -> ModelParameters:
    updates: dict[str, object] = {}
    aliases = {
        "protective_stop_fraction_below_entry": "stop_fraction",
    }
    for key, value in raw.items():
        if key == "variant":
            continue
        updates[aliases.get(key, key)] = value
    return replace(parameters, **updates)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("config/experiments/btc-sell-flow-absorption-v1.json"))
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--execution-scenarios", type=Path, default=Path("config/execution_scenarios.json"))
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    if config.get("experiment_id") != "btc-sell-flow-absorption-v1" or config.get("status") != "development_frozen":
        parser.error("frozen btc-sell-flow-absorption-v1 config required")
    data_config = config["data"]
    assert isinstance(data_config, Mapping)
    bars = load_development_bars(args.data, args.manifest, str(data_config["development_dataset_sha256"]))
    hours = aggregate_complete_hours(bars)
    parameters = parameters_from_config(config)

    sensitivity_specs = config["predeclared_sensitivities"]
    assert isinstance(sensitivity_specs, list)
    sensitivity_parameters = [apply_sensitivity(parameters, item) for item in sensitivity_specs]
    lookbacks = sorted({parameters.feature_lookback_hours, *(item.feature_lookback_hours for item in sensitivity_parameters)})
    snapshots_by_lookback = {lookback: compute_feature_snapshots(hours, lookback) for lookback in lookbacks}
    snapshots = snapshots_by_lookback[parameters.feature_lookback_hours]

    scenario_ids = list(config["execution_scenarios"])
    scenarios = load_execution_scenarios(args.execution_scenarios, scenario_ids)
    primary_scenario_id = "candle-primary-30bps-rt-v1"
    severe_scenario_id = "candle-severe-80bps-rt-v1"
    primary_scenario = scenarios[primary_scenario_id]

    primary_signals = select_signals(hours, snapshots, parameters, "absorption")
    scenario_results: dict[str, object] = {}
    scenario_trades: dict[str, list[dict[str, object]]] = {}
    for scenario_id, scenario in scenarios.items():
        metrics, trades = simulate(primary_signals, hours, bars, parameters, scenario)
        scenario_results[scenario_id] = metrics
        scenario_trades[scenario_id] = trades

    controls: dict[str, object] = {}
    for mode in ("extreme_sell_only", "price_only_reversal"):
        signals = select_signals(hours, snapshots, parameters, mode)
        metrics, _ = simulate(signals, hours, bars, parameters, primary_scenario)
        controls[mode] = metrics
    controls["btc_buy_hold"] = buy_hold_control(hours, primary_scenario, parameters.allocation_fraction)

    primary_trades = scenario_trades[primary_scenario_id]
    bootstrap = month_block_bootstrap(primary_trades, seed=20260902, replications=10_000)
    bootstrap.sort()
    bootstrap_result = {
        "replications": 10_000,
        "mean_net_trade_return": statistics.fmean(float(trade["net_return"]) for trade in primary_trades) if primary_trades else None,
        "ci95": [quantile(bootstrap, 0.025, presorted=True), quantile(bootstrap, 0.975, presorted=True)] if bootstrap else None,
    }
    matched_random = matched_random_test(
        primary_trades,
        set(primary_signals),
        hours,
        bars,
        snapshots,
        parameters,
        primary_scenario,
        seed=20260901,
        simulations=5_000,
    )

    sensitivities: list[dict[str, object]] = []
    for spec, variant_parameters in zip(sensitivity_specs, sensitivity_parameters):
        variant_snapshots = snapshots_by_lookback[variant_parameters.feature_lookback_hours]
        signals = select_signals(hours, variant_snapshots, variant_parameters, "absorption")
        metrics, _ = simulate(signals, hours, bars, variant_parameters, primary_scenario)
        sensitivities.append({"variant": spec["variant"], "parameters": spec, "metrics": metrics})

    primary_metrics = scenario_results[primary_scenario_id]
    severe_metrics = scenario_results[severe_scenario_id]
    sell_control = controls["extreme_sell_only"]
    primary_mean = primary_metrics["mean_net_trade_return"]
    sell_mean = sell_control["mean_net_trade_return"]
    sensitivity_positive = sum(float(item["metrics"]["total_return"]) > 0 for item in sensitivities)
    random_p = matched_random.get("one_sided_p") if matched_random.get("valid") else None
    bootstrap_lower = bootstrap_result["ci95"][0] if bootstrap_result["ci95"] else None

    gates = {
        "minimum_filled_primary_trades": int(primary_metrics["filled_trades"]) >= 100,
        "primary_30bps_total_return_positive": float(primary_metrics["total_return"]) > 0,
        "severe_80bps_total_return_positive": float(severe_metrics["total_return"]) > 0,
        "primary_profit_factor_minimum": float(primary_metrics["profit_factor"]) >= 1.20,
        "primary_max_drawdown_fraction_maximum": float(primary_metrics["maximum_drawdown"]) >= -0.10,
        "primary_mean_net_trade_bps_strictly_above": primary_mean is not None and float(primary_mean) > 0,
        "primary_month_block_bootstrap_lower_95_bps_strictly_above": bootstrap_lower is not None and float(bootstrap_lower) > 0,
        "candidate_minus_extreme_sell_only_mean_bps_strictly_above": primary_mean is not None and sell_mean is not None and float(primary_mean) > float(sell_mean),
        "calendar_hour_matched_random_one_sided_p_maximum": random_p is not None and float(random_p) <= 0.05,
        "positive_calendar_years_minimum": int(primary_metrics["positive_calendar_years"]) >= 5,
        "top_three_profitable_months_share_maximum": primary_metrics["top_three_profitable_months_share"] is not None and float(primary_metrics["top_three_profitable_months_share"]) <= 0.50,
        "positive_primary_cost_sensitivities_minimum": sensitivity_positive >= 8,
        "maximum_entry_gross_exposure_fraction": parameters.allocation_fraction <= 0.25,
        "maximum_planned_risk_fraction": parameters.allocation_fraction * (parameters.stop_fraction + 0.008) <= 0.005,
        "no_post_decision_information": True,
        "sealed_2026_not_read": True,
    }
    accepted = all(gates.values())

    market_monthly = market_monthly_returns(hours)
    strategy_monthly = {str(key): float(value) for key, value in primary_metrics["monthly_returns"].items()}
    report = {
        "schema_version": "btc-sell-flow-absorption-development-result-v1",
        "experiment_id": config["experiment_id"],
        "status": "development_accept" if accepted else "development_reject",
        "holdout_permitted": accepted,
        "holdout_read": False,
        "input": {
            "dataset_sha256": sha256_file(args.data),
            "rows_5m": len(bars),
            "complete_hours": len(hours),
            "evaluation_start": isoformat_ms(EVALUATION_START_MS),
            "evaluation_end_exclusive": isoformat_ms(EVALUATION_END_MS),
        },
        "parameters": parameters.__dict__ if hasattr(parameters, "__dict__") else {
            field: getattr(parameters, field) for field in parameters.__dataclass_fields__
        },
        "scenario_results": scenario_results,
        "controls": controls,
        "candidate_minus_extreme_sell_only_mean_net_bps": (
            (float(primary_mean) - float(sell_mean)) * 10_000 if primary_mean is not None and sell_mean is not None else None
        ),
        "month_block_bootstrap": bootstrap_result,
        "calendar_hour_matched_random": matched_random,
        "monthly_beta_attribution": beta_attribution(strategy_monthly, market_monthly),
        "sensitivities": sensitivities,
        "positive_primary_cost_sensitivities": sensitivity_positive,
        "gates": gates,
        "failed_gates": [name for name, passed in gates.items() if not passed],
        "decision": (
            "All development gates passed; the separately checksummed 2026 holdout may be evaluated only under a new explicit run."
            if accepted
            else "Reject this experiment before holdout and close further threshold variants of aggregate five-minute taker-flow."
        ),
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    report_path = args.output_dir / "development-report.json"
    trades_path = args.output_dir / "primary-trades.csv"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    write_trades(trades_path, primary_trades)
    manifest = {
        "schema_version": "research-artifact-manifest-v1",
        "experiment_id": config["experiment_id"],
        "config_sha256": sha256_file(args.config),
        "script_sha256": sha256_file(Path(__file__)),
        "development_dataset_sha256": sha256_file(args.data),
        "development_manifest_sha256": sha256_file(args.manifest),
        "execution_scenarios_sha256": sha256_file(args.execution_scenarios),
        "artifacts": {
            report_path.name: sha256_file(report_path),
            trades_path.name: sha256_file(trades_path),
        },
        "holdout_read": False,
    }
    manifest_path = args.output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "filled_trades": primary_metrics["filled_trades"],
        "primary_total_return": primary_metrics["total_return"],
        "primary_mean_net_trade_bps": float(primary_mean) * 10_000 if primary_mean is not None else None,
        "failed_gates": report["failed_gates"],
        "output_dir": str(args.output_dir),
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
