#!/usr/bin/env python3
"""Run the frozen BTC online-regime breakout experiment on development data only."""
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
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


FIVE_MINUTES_MS = 300_000
FOUR_HOURS_MS = 14_400_000
DAY_MS = 86_400_000
EVALUATION_START_MS = 1_546_300_800_000  # 2019-01-01
EVALUATION_END_MS = 1_767_225_600_000  # 2026-01-01


@dataclass(frozen=True)
class Row:
    segment: int
    open_ms: int
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class Bar:
    segment: int
    open_ms: int
    close_ms: int
    open: float
    high: float
    low: float
    close: float
    start_row: int
    end_row: int


@dataclass(frozen=True)
class NIG:
    mean: float
    kappa: float
    alpha: float
    beta: float


@dataclass(frozen=True)
class RegimeState:
    segment: int
    day_open_ms: int
    available_ms: int
    close: float
    state: str
    change_probability: float
    map_run_length: int
    posterior_mean: float
    posterior_se: float
    drift_z: float


def canonical_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def quantile(values: list[float], probability: float) -> float:
    if not values:
        raise ValueError("quantile requires values")
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    low, high = math.floor(position), math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] * (high - position) + ordered[high] * (position - low)


def load_rows(path: Path) -> list[Row]:
    if path.is_symlink():
        raise ValueError("symlink input is prohibited")
    rows: list[Row] = []
    previous: Row | None = None
    with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
        for number, source in enumerate(csv.DictReader(handle), start=2):
            row = Row(
                segment=int(source["segment_id"]), open_ms=int(source["open_time_ms"]),
                open=float(source["open"]), high=float(source["high"]),
                low=float(source["low"]), close=float(source["close"]),
            )
            prices = (row.open, row.high, row.low, row.close)
            if not (all(math.isfinite(value) and value > 0 for value in prices)
                    and row.low <= min(row.open, row.close)
                    and row.high >= max(row.open, row.close)):
                raise ValueError(f"invalid OHLC at source line {number}")
            if previous is not None:
                if row.open_ms <= previous.open_ms:
                    raise ValueError(f"non-increasing timestamp at source line {number}")
                if row.segment == previous.segment and row.open_ms != previous.open_ms + FIVE_MINUTES_MS:
                    raise ValueError(f"gap inside segment at source line {number}")
            rows.append(row)
            previous = row
    if not rows:
        raise ValueError("empty input")
    return rows


def aggregate_bars(rows: list[Row], width_ms: int) -> tuple[list[Bar], int]:
    count = width_ms // FIVE_MINUTES_MS
    bars: list[Bar] = []
    used = 0
    index = 0
    while index < len(rows):
        first = rows[index]
        if first.open_ms % width_ms:
            index += 1
            continue
        bucket = rows[index:index + count]
        complete = len(bucket) == count and all(
            item.segment == first.segment
            and item.open_ms == first.open_ms + offset * FIVE_MINUTES_MS
            for offset, item in enumerate(bucket)
        )
        if not complete:
            index += 1
            continue
        bars.append(Bar(
            first.segment, first.open_ms, first.open_ms + width_ms, first.open,
            max(item.high for item in bucket), min(item.low for item in bucket),
            bucket[-1].close, index, index + count - 1,
        ))
        used += count
        index += count
    return bars, len(rows) - used


def nig_update(model: NIG, value: float) -> NIG:
    kappa = model.kappa + 1.0
    return NIG(
        (model.kappa * model.mean + value) / kappa,
        kappa,
        model.alpha + 0.5,
        model.beta + model.kappa * (value - model.mean) ** 2 / (2.0 * kappa),
    )


def student_log_predictive(model: NIG, value: float) -> float:
    degrees = 2.0 * model.alpha
    scale2 = model.beta * (model.kappa + 1.0) / (model.alpha * model.kappa)
    scale2 = max(scale2, 1e-18)
    standardized2 = (value - model.mean) ** 2 / scale2
    return (
        math.lgamma((degrees + 1.0) / 2.0) - math.lgamma(degrees / 2.0)
        - 0.5 * math.log(degrees * math.pi * scale2)
        - (degrees + 1.0) / 2.0 * math.log1p(standardized2 / degrees)
    )


def bocpd_states(
    daily: list[Bar], prior: NIG, *, expected_run_days: int = 90,
    maximum_run: int = 365, minimum_run: int = 10, positive_z: float = 0.75,
    negative_z: float = -0.75, maximum_change_probability: float = 0.50,
) -> list[RegimeState]:
    """Return filtered, never-smoothed BOCPD states available at each daily close."""
    hazard = 1.0 / expected_run_days
    result: list[RegimeState] = []
    probabilities: list[float] = [1.0]
    models: list[NIG] = [prior]
    previous_segment: int | None = None
    for bar in daily:
        if previous_segment != bar.segment:
            probabilities, models = [1.0], [prior]
        observation = math.log(bar.close / bar.open)
        logs: list[tuple[int, float, NIG]] = []
        change_terms = [
            math.log(probability) + math.log(hazard) + student_log_predictive(model, observation)
            for probability, model in zip(probabilities, models) if probability > 0
        ]
        change_max = max(change_terms)
        change_log_mass = change_max + math.log(
            sum(math.exp(value - change_max) for value in change_terms)
        )
        logs.append((0, change_log_mass, nig_update(prior, observation)))
        for run, (probability, model) in enumerate(zip(probabilities, models)):
            if run + 1 > maximum_run or probability <= 0:
                continue
            logs.append((
                run + 1,
                math.log(probability) + math.log1p(-hazard) + student_log_predictive(model, observation),
                nig_update(model, observation),
            ))
        largest = max(item[1] for item in logs)
        normalizer = largest + math.log(sum(math.exp(item[1] - largest) for item in logs))
        by_run = sorted((run, math.exp(logp - normalizer), model) for run, logp, model in logs)
        probabilities = [item[1] for item in by_run]
        models = [item[2] for item in by_run]
        map_index = max(range(len(probabilities)), key=probabilities.__getitem__)
        map_run = by_run[map_index][0]
        model = models[map_index]
        variance = model.beta / max(model.alpha - 1.0, 1e-12)
        posterior_se = math.sqrt(variance / model.kappa)
        z_score = model.mean / posterior_se if posterior_se > 0 else 0.0
        change_probability = probabilities[0]
        if map_run >= minimum_run and z_score >= positive_z and change_probability <= maximum_change_probability:
            state = "positive"
        elif map_run >= minimum_run and z_score <= negative_z:
            state = "negative"
        else:
            state = "uncertain"
        result.append(RegimeState(
            bar.segment, bar.open_ms, bar.close_ms, bar.close, state,
            change_probability, map_run, model.mean, posterior_se, z_score,
        ))
        previous_segment = bar.segment
    return result


def latest_states(four_hour: list[Bar], states: list[RegimeState]) -> list[str | None]:
    grouped: dict[int, list[RegimeState]] = defaultdict(list)
    for state in states:
        grouped[state.segment].append(state)
    output: list[str | None] = []
    for bar in four_hour:
        candidates = grouped.get(bar.segment, [])
        available = [item.available_ms for item in candidates]
        position = bisect.bisect_right(available, bar.close_ms) - 1
        output.append(candidates[position].state if position >= 0 else None)
    return output


def channel_signals(bars: list[Bar], lookback: int, start_ms: int = EVALUATION_START_MS) -> list[int]:
    signals: list[int] = []
    for index, bar in enumerate(bars):
        if bar.close_ms <= start_ms or index < lookback:
            continue
        prior = bars[index - lookback:index]
        if all(item.segment == bar.segment for item in prior) and bar.close > max(item.high for item in prior):
            signals.append(index)
    return signals


def exit_execution_rows(rows: list[Row], bars: list[Bar], lookback: int) -> dict[int, str]:
    exits: dict[int, str] = {}
    for index, bar in enumerate(bars):
        if index < lookback:
            continue
        prior = bars[index - lookback:index]
        entry_row = bar.end_row + 1
        if (all(item.segment == bar.segment for item in prior)
                and bar.close < min(item.low for item in prior)
                and entry_row < len(rows)
                and rows[entry_row].segment == bar.segment
                and rows[entry_row].open_ms == bar.close_ms):
            exits[entry_row] = "exit_channel"
    return exits


def regime_exit_rows(rows: list[Row], bars: list[Bar], latest: list[str | None]) -> dict[int, str]:
    exits: dict[int, str] = {}
    for index, bar in enumerate(bars):
        if latest[index] == "positive":
            continue
        row = bar.end_row + 1
        if row < len(rows) and rows[row].segment == bar.segment and rows[row].open_ms == bar.close_ms:
            exits[row] = "regime_ceased_positive"
    return exits


def resolve_exit(
    rows: list[Row], entry_row: int, planned_exits: dict[int, str], stop_fraction: float,
    maximum_holding_days: int,
) -> tuple[int, float, str]:
    entry = rows[entry_row]
    stop = entry.open * (1.0 - stop_fraction)
    maximum_time = entry.open_ms + maximum_holding_days * DAY_MS
    for index in range(entry_row, len(rows)):
        row = rows[index]
        if row.segment != entry.segment:
            previous = rows[index - 1]
            return index - 1, previous.close, "source_segment_end"
        if row.low <= stop:
            return index, min(row.open, stop), "protective_stop"
        next_is_segment = index + 1 == len(rows) or rows[index + 1].segment != row.segment
        if next_is_segment:
            return index, row.close, "source_segment_end"
        if row.open_ms >= maximum_time:
            return index, row.open, "maximum_holding_time"
        if index in planned_exits:
            return index, row.open, planned_exits[index]
    return len(rows) - 1, rows[-1].close, "source_segment_end"


def simulate(
    rows: list[Row], bars: list[Bar], signal_indices: list[int], planned_exits: dict[int, str],
    *, side_cost_bps: float, price_protection_bps: float, stop_fraction: float = 0.04,
    maximum_holding_days: int = 14, allocation: float = 0.10,
) -> dict:
    cash = 1000.0
    trades: list[dict] = []
    expired = frequency_blocked = busy_blocked = 0
    unavailable_until = -1
    entry_decisions: deque[int] = deque()
    for signal_index in signal_indices:
        bar = bars[signal_index]
        entry_row = bar.end_row + 1
        if entry_row <= unavailable_until:
            busy_blocked += 1
            continue
        if entry_row >= len(rows) or rows[entry_row].segment != bar.segment or rows[entry_row].open_ms != bar.close_ms:
            expired += 1
            continue
        decision_ms = bar.close_ms
        while entry_decisions and entry_decisions[0] < decision_ms - 7 * DAY_MS:
            entry_decisions.popleft()
        same_day = any(value // DAY_MS == decision_ms // DAY_MS for value in entry_decisions)
        if same_day or len(entry_decisions) >= 4:
            frequency_blocked += 1
            continue
        entry_decisions.append(decision_ms)
        entry = rows[entry_row]
        if entry.open > bar.close * (1.0 + price_protection_bps / 10_000.0):
            expired += 1
            continue
        exit_row, exit_reference, reason = resolve_exit(
            rows, entry_row, planned_exits, stop_fraction, maximum_holding_days,
        )
        side_cost = side_cost_bps / 10_000.0
        budget = cash * allocation
        entry_fill = entry.open * (1.0 + side_cost)
        quantity = budget / entry_fill
        remaining_cash = cash - budget
        exit_fill = exit_reference * (1.0 - side_cost)
        proceeds = quantity * exit_fill
        cash_after = remaining_cash + proceeds
        pnl = cash_after - cash
        trades.append({
            "signal_ms": decision_ms, "entry_ms": entry.open_ms,
            "entry_row": entry_row, "entry_reference": entry.open, "entry_fill": entry_fill,
            "exit_ms": rows[exit_row].open_ms, "exit_row": exit_row,
            "exit_reference": exit_reference, "exit_fill": exit_fill, "exit_reason": reason,
            "holding_days": (rows[exit_row].open_ms - entry.open_ms) / DAY_MS,
            "gross_reference_return": exit_reference / entry.open - 1.0,
            "return_on_allocated": proceeds / budget - 1.0,
            "pnl_quote": pnl, "cash_before": cash, "cash_after": cash_after,
            "remaining_cash": remaining_cash, "quantity": quantity,
            "entry_month": datetime.fromtimestamp(entry.open_ms / 1000, tz=timezone.utc).strftime("%Y-%m"),
            "entry_year": datetime.fromtimestamp(entry.open_ms / 1000, tz=timezone.utc).year,
        })
        cash = cash_after
        unavailable_until = exit_row
    return summarize_simulation(rows, trades, cash, side_cost_bps, expired, frequency_blocked, busy_blocked)


def summarize_simulation(
    rows: list[Row], trades: list[dict], final_cash: float, side_cost_bps: float,
    expired: int, frequency_blocked: int, busy_blocked: int,
) -> dict:
    eval_rows = [index for index, row in enumerate(rows) if EVALUATION_START_MS <= row.open_ms < EVALUATION_END_MS]
    active = 0
    peak = 1000.0
    max_drawdown = 0.0
    annual_end: dict[int, float] = {}
    trade_position = 0
    cash = 1000.0
    current: dict | None = trades[0] if trades else None
    for index in eval_rows:
        row = rows[index]
        while current is not None and index > current["exit_row"]:
            cash = current["cash_after"]
            trade_position += 1
            current = trades[trade_position] if trade_position < len(trades) else None
        if current is not None and current["entry_row"] <= index <= current["exit_row"]:
            if index == current["exit_row"]:
                equity = current["cash_after"]
            else:
                equity = current["remaining_cash"] + current["quantity"] * row.close
            active += 1
        else:
            equity = cash
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, equity / peak - 1.0)
        annual_end[datetime.fromtimestamp(row.open_ms / 1000, tz=timezone.utc).year] = equity
    years: dict[str, float] = {}
    prior = 1000.0
    for year in sorted(annual_end):
        years[str(year)] = annual_end[year] / prior - 1.0
        prior = annual_end[year]
    returns = [item["return_on_allocated"] for item in trades]
    gains = sum(item["pnl_quote"] for item in trades if item["pnl_quote"] > 0)
    losses = -sum(item["pnl_quote"] for item in trades if item["pnl_quote"] < 0)
    months: dict[str, dict] = {}
    for month in sorted({item["entry_month"] for item in trades}):
        selected = [item for item in trades if item["entry_month"] == month]
        months[month] = {"trades": len(selected), "pnl_quote": sum(item["pnl_quote"] for item in selected)}
    positive_months = [item["pnl_quote"] for item in months.values() if item["pnl_quote"] > 0]
    concentration = sum(sorted(positive_months, reverse=True)[:3]) / sum(positive_months) if positive_months else None
    years_elapsed = (EVALUATION_END_MS - EVALUATION_START_MS) / (365.2425 * DAY_MS)
    net_return = final_cash / 1000.0 - 1.0
    cagr = (final_cash / 1000.0) ** (1.0 / years_elapsed) - 1.0
    calmar = cagr / abs(max_drawdown) if max_drawdown < 0 else None
    return {
        "side_cost_bps": side_cost_bps, "round_trip_cost_bps": side_cost_bps * 2,
        "starting_equity": 1000.0, "ending_equity": final_cash,
        "net_return": net_return, "cagr": cagr, "maximum_drawdown_fraction": -max_drawdown,
        "calmar": calmar, "trade_count": len(trades),
        "mean_net_trade_return": statistics.fmean(returns) if returns else None,
        "mean_net_trade_bps": statistics.fmean(returns) * 10_000 if returns else None,
        "profit_factor": gains / losses if losses else None,
        "win_rate": sum(value > 0 for value in returns) / len(returns) if returns else None,
        "exposure_fraction": active / len(eval_rows) if eval_rows else 0.0,
        "expired_entry_count": expired, "frequency_blocked_count": frequency_blocked,
        "busy_signal_count": busy_blocked, "positive_calendar_years": sum(value > 0 for value in years.values()),
        "calendar_year_returns": years, "monthly_results": months,
        "top_three_profitable_months_share": concentration,
        "exit_reasons": dict(sorted((reason, sum(t["exit_reason"] == reason for t in trades)) for reason in {t["exit_reason"] for t in trades})),
        "trades": trades,
    }


def segmented_buy_hold(rows: list[Row], *, side_cost_bps: float, allocation: float = 0.10) -> dict:
    """Invest the frozen fraction at each accepted segment start and liquidate at its end."""
    selected = [row for row in rows if EVALUATION_START_MS <= row.open_ms < EVALUATION_END_MS]
    grouped: dict[int, list[Row]] = defaultdict(list)
    for row in selected:
        grouped[row.segment].append(row)
    cash = 1000.0
    peak = cash
    maximum_drawdown = 0.0
    side_cost = side_cost_bps / 10_000.0
    segments: list[dict] = []
    for segment in sorted(grouped, key=lambda key: grouped[key][0].open_ms):
        segment_rows = grouped[segment]
        first, last = segment_rows[0], segment_rows[-1]
        budget = cash * allocation
        quantity = budget / (first.open * (1.0 + side_cost))
        remaining = cash - budget
        for row in segment_rows:
            equity = remaining + quantity * row.close
            peak = max(peak, equity)
            maximum_drawdown = min(maximum_drawdown, equity / peak - 1.0)
        proceeds = quantity * last.close * (1.0 - side_cost)
        cash_after = remaining + proceeds
        segments.append({
            "segment": segment, "entry_ms": first.open_ms, "exit_ms": last.open_ms,
            "return_on_allocated": proceeds / budget - 1.0,
        })
        cash = cash_after
    years_elapsed = (EVALUATION_END_MS - EVALUATION_START_MS) / (365.2425 * DAY_MS)
    return {
        "allocation_fraction": allocation, "segments": len(segments),
        "net_return": cash / 1000.0 - 1.0,
        "cagr": (cash / 1000.0) ** (1.0 / years_elapsed) - 1.0,
        "maximum_drawdown_fraction": -maximum_drawdown,
        "segment_returns": segments,
    }


def month_bootstrap(values: list[tuple[str, float]], *, seed: int, replicates: int) -> list[float]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for month, value in values:
        grouped[month].append(value)
    months = sorted(grouped)
    if not months:
        return []
    rng = random.Random(seed)
    estimates: list[float] = []
    for _ in range(replicates):
        sample = [grouped[months[rng.randrange(len(months))]] for _ in months]
        estimates.append(statistics.fmean(value for block in sample for value in block))
    return sorted(estimates)


def regime_information(states: list[RegimeState], daily: list[Bar], *, seed: int, replicates: int) -> dict:
    grouped_bars: dict[int, list[Bar]] = defaultdict(list)
    grouped_states: dict[int, list[RegimeState]] = defaultdict(list)
    for bar in daily:
        grouped_bars[bar.segment].append(bar)
    for state in states:
        grouped_states[state.segment].append(state)
    observations: list[tuple[str, str, float]] = []
    for segment, segment_states in grouped_states.items():
        bars = grouped_bars[segment]
        state_by_open = {state.day_open_ms: state for state in segment_states}
        for index in range(0, len(bars) - 7, 7):
            bar = bars[index]
            if bar.close_ms <= EVALUATION_START_MS:
                continue
            future = bars[index + 7]
            if future.open_ms != bar.open_ms + 7 * DAY_MS:
                continue
            state = state_by_open.get(bar.open_ms)
            if state is None:
                continue
            value = math.log(future.close / bar.close)
            month = datetime.fromtimestamp(state.available_ms / 1000, tz=timezone.utc).strftime("%Y-%m")
            observations.append((month, state.state, value))
    positive = [value for _, state, value in observations if state == "positive"]
    nonpositive = [value for _, state, value in observations if state != "positive"]
    difference = statistics.fmean(positive) - statistics.fmean(nonpositive) if positive and nonpositive else None
    grouped: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for month, state, value in observations:
        grouped[month].append((state, value))
    months = sorted(grouped)
    boot: list[float] = []
    if positive and nonpositive:
        rng = random.Random(seed + 1)
        for _ in range(replicates):
            sample = [grouped[months[rng.randrange(len(months))]] for _ in months]
            pos = [value for block in sample for state, value in block if state == "positive"]
            non = [value for block in sample for state, value in block if state != "positive"]
            if pos and non:
                boot.append(statistics.fmean(pos) - statistics.fmean(non))
    boot.sort()
    return {
        "non_overlapping_observations": len(observations), "positive_observations": len(positive),
        "nonpositive_observations": len(nonpositive), "positive_mean_log_return": statistics.fmean(positive) if positive else None,
        "nonpositive_mean_log_return": statistics.fmean(nonpositive) if nonpositive else None,
        "difference_log_return": difference, "difference_bps": difference * 10_000 if difference is not None else None,
        "month_bootstrap_ci95": [quantile(boot, 0.025), quantile(boot, 0.975)] if boot else [None, None],
    }


def scenario_costs(path: Path, selected_ids: list[str]) -> dict[str, dict]:
    payload = json.loads(path.read_text())
    scenarios = {item["scenario_id"]: item for item in payload["scenarios"]}
    result: dict[str, dict] = {}
    for scenario_id in selected_ids:
        item = scenarios[scenario_id]
        side = float(item["taker_fee_bps"]) + float(item["implicit_cost_bps_per_side"]) + float(item["residual_impact_bps"])
        result[scenario_id] = {"side_cost_bps": side, "price_protection_bps": float(item["price_protection_bps"])}
    return result


def verify_inputs(args: argparse.Namespace) -> tuple[dict, dict]:
    if args.data.is_symlink() or args.contract.is_symlink() or args.manifest.is_symlink():
        raise ValueError("symlink inputs are prohibited")
    if "holdout" in str(args.data).lower() or "2026-01-07" in str(args.data).lower():
        raise ValueError("holdout input is prohibited")
    contract = json.loads(args.contract.read_text())
    manifest = json.loads(args.manifest.read_text())
    digest = sha256(args.data)
    if contract.get("experiment_id") != "btc-online-regime-breakout-v1" or contract.get("status") != "development_frozen":
        raise ValueError("exact frozen experiment contract required")
    if manifest.get("partition") != "development-2017-2025" or not manifest.get("accepted"):
        raise ValueError("accepted development manifest required")
    expected = contract["data"]["development_dataset_sha256"]
    if digest != expected or manifest.get("dataset_sha256") != expected:
        raise ValueError("development dataset checksum mismatch")
    if contract["isolation"].get("network_access_allowed") is not False:
        raise ValueError("offline isolation contract required")
    return contract, manifest


def run_experiment(args: argparse.Namespace) -> dict:
    contract, manifest = verify_inputs(args)
    rows = load_rows(args.data)
    four_hour, discarded_4h = aggregate_bars(rows, FOUR_HOURS_MS)
    daily, discarded_daily = aggregate_bars(rows, DAY_MS)
    discovery = [math.log(bar.close / bar.open) for bar in daily if bar.close_ms <= EVALUATION_START_MS]
    if len(discovery) < 30:
        raise ValueError("insufficient pre-2019 daily observations")
    prior_variance = statistics.variance(discovery)
    frozen_prior = contract["online_regime"]["prior"]
    prior = NIG(float(frozen_prior["mean"]), float(frozen_prior["kappa"]), float(frozen_prior["alpha"]), prior_variance * (float(frozen_prior["alpha"]) - 1.0))
    regime_config = contract["online_regime"]
    states = bocpd_states(
        daily, prior, expected_run_days=regime_config["hazard_expected_run_days"],
        maximum_run=regime_config["maximum_run_length_days"],
        minimum_run=regime_config["minimum_map_run_days"],
        positive_z=regime_config["positive_drift_z_minimum"],
        negative_z=regime_config["negative_drift_z_maximum"],
        maximum_change_probability=regime_config["maximum_change_probability_for_positive_state"],
    )
    latest = latest_states(four_hour, states)
    breakout = contract["breakout_baseline"]
    base_signals = channel_signals(four_hour, breakout["entry_channel_bars"])
    combined_signals = [index for index in base_signals if latest[index] == "positive"]
    channel_exits = exit_execution_rows(rows, four_hour, breakout["exit_channel_bars"])
    costs = scenario_costs(args.scenario_config, contract["execution_scenarios"])
    scenario_results: dict[str, dict] = {}
    baseline_results: dict[str, dict] = {}
    for scenario_id, cost in costs.items():
        common = dict(
            side_cost_bps=cost["side_cost_bps"], price_protection_bps=cost["price_protection_bps"],
            stop_fraction=breakout["protective_stop_fraction_below_entry"],
            maximum_holding_days=breakout["maximum_holding_days"],
            allocation=contract["mandate"]["account_fraction_per_entry"],
        )
        baseline_results[scenario_id] = simulate(rows, four_hour, base_signals, channel_exits, **common)
        scenario_results[scenario_id] = simulate(rows, four_hour, combined_signals, channel_exits, **common)
    primary_id = contract["execution_scenarios"][0]
    primary = scenario_results[primary_id]
    baseline = baseline_results[primary_id]
    boot = month_bootstrap(
        [(trade["entry_month"], trade["return_on_allocated"]) for trade in primary["trades"]],
        seed=contract["statistics"]["bootstrap_seed"],
        replicates=contract["statistics"]["bootstrap_replications"],
    )
    trade_bootstrap = [quantile(boot, 0.025), quantile(boot, 0.975)] if boot else [None, None]
    eval_states = [state for state in states if EVALUATION_START_MS <= state.available_ms < EVALUATION_END_MS]
    occupancy = {name: sum(state.state == name for state in eval_states) / len(eval_states) for name in ("positive", "negative", "uncertain")}
    information = regime_information(
        states, daily, seed=contract["statistics"]["bootstrap_seed"],
        replicates=contract["statistics"]["bootstrap_replications"],
    )
    regime_signals = []
    for index in range(1, len(four_hour)):
        if four_hour[index].close_ms > EVALUATION_START_MS and latest[index] == "positive" and latest[index - 1] != "positive":
            regime_signals.append(index)
    regime_control = simulate(
        rows, four_hour, regime_signals, regime_exit_rows(rows, four_hour, latest),
        side_cost_bps=costs[primary_id]["side_cost_bps"],
        price_protection_bps=costs[primary_id]["price_protection_bps"],
        stop_fraction=breakout["protective_stop_fraction_below_entry"],
        maximum_holding_days=breakout["maximum_holding_days"],
        allocation=contract["mandate"]["account_fraction_per_entry"],
    )
    sensitivities: dict[str, dict] = {}
    positive_sensitivities = improved_sensitivities = 0
    for definition in contract["predeclared_sensitivities"]:
        params = {
            "entry_channel_bars": breakout["entry_channel_bars"],
            "exit_channel_bars": breakout["exit_channel_bars"],
            "hazard_expected_run_days": regime_config["hazard_expected_run_days"],
            "minimum_map_run_days": regime_config["minimum_map_run_days"],
            "positive_drift_z_minimum": regime_config["positive_drift_z_minimum"],
            "protective_stop_fraction_below_entry": breakout["protective_stop_fraction_below_entry"],
            "maximum_holding_days": breakout["maximum_holding_days"],
        }
        params.update({key: value for key, value in definition.items() if key != "variant"})
        variant_states = bocpd_states(
            daily, prior, expected_run_days=params["hazard_expected_run_days"],
            maximum_run=regime_config["maximum_run_length_days"], minimum_run=params["minimum_map_run_days"],
            positive_z=params["positive_drift_z_minimum"], negative_z=regime_config["negative_drift_z_maximum"],
            maximum_change_probability=regime_config["maximum_change_probability_for_positive_state"],
        )
        variant_latest = latest_states(four_hour, variant_states)
        variant_base_signals = channel_signals(four_hour, params["entry_channel_bars"])
        variant_combined_signals = [index for index in variant_base_signals if variant_latest[index] == "positive"]
        variant_exits = exit_execution_rows(rows, four_hour, params["exit_channel_bars"])
        common = dict(
            side_cost_bps=costs[primary_id]["side_cost_bps"],
            price_protection_bps=costs[primary_id]["price_protection_bps"],
            stop_fraction=params["protective_stop_fraction_below_entry"],
            maximum_holding_days=params["maximum_holding_days"],
            allocation=contract["mandate"]["account_fraction_per_entry"],
        )
        variant_base = simulate(rows, four_hour, variant_base_signals, variant_exits, **common)
        variant_combined = simulate(rows, four_hour, variant_combined_signals, variant_exits, **common)
        positive = variant_combined["net_return"] > 0
        improved = (variant_combined["calmar"] is not None and variant_base["calmar"] is not None
                    and variant_combined["calmar"] > variant_base["calmar"])
        positive_sensitivities += int(positive)
        improved_sensitivities += int(improved)
        sensitivities[definition["variant"]] = {
            "parameters": params, "combined": {key: variant_combined[key] for key in ("trade_count", "net_return", "cagr", "maximum_drawdown_fraction", "calmar", "mean_net_trade_bps")},
            "matched_breakout": {key: variant_base[key] for key in ("trade_count", "net_return", "cagr", "maximum_drawdown_fraction", "calmar", "mean_net_trade_bps")},
            "combined_positive": positive, "calmar_improved": improved,
        }
    severe = scenario_results[contract["execution_scenarios"][-1]]
    g = contract["acceptance_gates"]
    calmar_gate = (primary["calmar"] is not None and baseline["calmar"] is not None
                   and primary["calmar"] >= 1.25 * baseline["calmar"])
    cagr_gate = primary["cagr"] >= 0.8 * baseline["cagr"] if baseline["cagr"] > 0 else primary["cagr"] > 0
    gates = {
        "minimum_filled_primary_trades": primary["trade_count"] >= g["minimum_filled_primary_trades"],
        "primary_30bps_total_return_positive": primary["net_return"] > 0,
        "severe_80bps_total_return_positive": severe["net_return"] > 0,
        "primary_profit_factor_minimum": primary["profit_factor"] is not None and primary["profit_factor"] >= g["primary_profit_factor_minimum"],
        "primary_max_drawdown_fraction_maximum": primary["maximum_drawdown_fraction"] <= g["primary_max_drawdown_fraction_maximum"],
        "primary_mean_net_trade_positive": primary["mean_net_trade_bps"] is not None and primary["mean_net_trade_bps"] > 0,
        "primary_month_bootstrap_lower_positive": trade_bootstrap[0] is not None and trade_bootstrap[0] > 0,
        "positive_calendar_years_minimum": primary["positive_calendar_years"] >= g["positive_calendar_years_minimum"],
        "top_three_profitable_months_share_maximum": primary["top_three_profitable_months_share"] is not None and primary["top_three_profitable_months_share"] <= g["top_three_profitable_months_share_maximum"],
        "positive_state_occupancy_range": g["positive_state_occupancy_minimum"] <= occupancy["positive"] <= g["positive_state_occupancy_maximum"],
        "positive_state_next_7d_difference_positive": information["difference_log_return"] is not None and information["difference_log_return"] > 0,
        "regime_information_bootstrap_lower_positive": information["month_bootstrap_ci95"][0] is not None and information["month_bootstrap_ci95"][0] > 0,
        "combined_calmar_at_least_1_25x_breakout": calmar_gate,
        "combined_cagr_retains_80pct_breakout": cagr_gate,
        "combined_mean_trade_above_breakout": primary["mean_net_trade_bps"] is not None and baseline["mean_net_trade_bps"] is not None and primary["mean_net_trade_bps"] > baseline["mean_net_trade_bps"],
        "positive_sensitivities_minimum": positive_sensitivities >= g["positive_primary_cost_sensitivities_minimum"],
        "calmar_improving_sensitivities_minimum": improved_sensitivities >= g["sensitivities_improving_calmar_over_matched_breakout_minimum"],
        "maximum_entry_gross_exposure": contract["mandate"]["account_fraction_per_entry"] <= g["maximum_entry_gross_exposure_fraction"],
        "maximum_planned_risk": contract["mandate"]["account_fraction_per_entry"] * (breakout["protective_stop_fraction_below_entry"] + 0.008) <= g["maximum_planned_risk_fraction"],
        "no_post_decision_information": True,
        "sealed_2026_not_read": True,
    }
    accepted = all(gates.values())
    report = {
        "schema_version": "btc-online-regime-breakout-development-report-v1",
        "experiment_id": contract["experiment_id"],
        "decision": "development_gates_passed_holdout_unlock_review_required" if accepted else "rejected_before_holdout",
        "accepted_for_holdout_review": accepted, "holdout_accessed": False,
        "contract_sha256": sha256(args.contract), "implementation_sha256": sha256(Path(__file__)),
        "development_dataset_sha256": manifest["dataset_sha256"], "development_manifest_sha256": sha256(args.manifest),
        "execution_scenarios_sha256": sha256(args.scenario_config),
        "input_quality": {"rows_5m": len(rows), "bars_4h": len(four_hour), "bars_daily": len(daily), "discarded_rows_4h": discarded_4h, "discarded_rows_daily": discarded_daily, "source_segments": len({row.segment for row in rows})},
        "prior_calibration": {"observations": len(discovery), "sample_variance": prior_variance, "nig": asdict(prior)},
        "signals": {"breakout_conditions": len(base_signals), "positive_regime_breakouts": len(combined_signals), "rejected_breakouts": len(base_signals) - len(combined_signals)},
        "state_occupancy": occupancy, "regime_information_test": information,
        "primary_month_block_bootstrap_mean_trade_ci95": trade_bootstrap,
        "combined_execution_scenarios": scenario_results,
        "breakout_control_execution_scenarios": baseline_results,
        "controls": {
            "flat": {"net_return": 0.0, "maximum_drawdown_fraction": 0.0},
            "segmented_btc_buy_hold_primary_cost": segmented_buy_hold(
                rows, side_cost_bps=costs[primary_id]["side_cost_bps"],
                allocation=contract["mandate"]["account_fraction_per_entry"],
            ),
            "regime_only_primary_cost": regime_control,
        },
        "one_factor_sensitivities": sensitivities,
        "positive_sensitivities_out_of_12": positive_sensitivities,
        "calmar_improving_sensitivities_out_of_12": improved_sensitivities,
        "development_gates": gates, "gate_failures": [name for name, passed in gates.items() if not passed],
        "change_control": "Any failed gate rejects this experiment ID. Do not tune it or open the sealed 2026 partition.",
    }
    return report, states


def write_evidence(args: argparse.Namespace, report: dict, states: list[RegimeState]) -> None:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report_path = args.output_dir / "development-report.json"
    trades_path = args.output_dir / "primary-trades.csv"
    states_path = args.output_dir / "regime-states.csv"
    manifest_path = args.output_dir / "manifest.json"
    primary_id = json.loads(args.contract.read_text())["execution_scenarios"][0]
    trades = report["combined_execution_scenarios"][primary_id].pop("trades")
    for result in report["combined_execution_scenarios"].values():
        result.pop("trades", None)
    for result in report["breakout_control_execution_scenarios"].values():
        result.pop("trades", None)
    report["controls"]["regime_only_primary_cost"].pop("trades", None)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    trade_fields = ["signal_ms", "entry_ms", "entry_reference", "entry_fill", "exit_ms", "exit_reference", "exit_fill", "exit_reason", "holding_days", "gross_reference_return", "return_on_allocated", "pnl_quote", "entry_month", "entry_year"]
    with trades_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=trade_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(trades)
    state_fields = list(asdict(states[0])) if states else []
    with states_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=state_fields)
        if state_fields:
            writer.writeheader()
            writer.writerows(asdict(state) for state in states)
    manifest = {
        "schema_version": "research-evidence-manifest-v1", "experiment_id": report["experiment_id"],
        "decision": report["decision"], "holdout_accessed": False,
        "inputs": {str(args.data): sha256(args.data), str(args.manifest): sha256(args.manifest), str(args.contract): sha256(args.contract), str(args.scenario_config): sha256(args.scenario_config)},
        "artifacts": {path.name: {"sha256": sha256(path), "bytes": path.stat().st_size} for path in (report_path, trades_path, states_path)},
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--contract", type=Path, default=Path("config/experiments/btc-online-regime-breakout-v1.json"))
    parser.add_argument("--scenario-config", type=Path, default=Path("config/execution_scenarios.json"))
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report, states = run_experiment(args)
    write_evidence(args, report, states)
    primary_id = json.loads(args.contract.read_text())["execution_scenarios"][0]
    summary = {
        "decision": report["decision"], "signals": report["signals"],
        "primary": {key: report["combined_execution_scenarios"][primary_id][key] for key in ("trade_count", "net_return", "cagr", "maximum_drawdown_fraction", "calmar", "mean_net_trade_bps", "profit_factor", "positive_calendar_years")},
        "breakout_control": {key: report["breakout_control_execution_scenarios"][primary_id][key] for key in ("trade_count", "net_return", "cagr", "maximum_drawdown_fraction", "calmar", "mean_net_trade_bps", "profit_factor", "positive_calendar_years")},
        "state_occupancy": report["state_occupancy"], "regime_information": report["regime_information_test"],
        "gate_failures": report["gate_failures"],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
