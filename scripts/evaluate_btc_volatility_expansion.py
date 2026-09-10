#!/usr/bin/env python3
"""Evaluate the frozen BTC volatility-expansion hypothesis on development data only."""
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
from decimal import Decimal
from pathlib import Path

from trading_platform.execution_model import (
    CostBreakdown,
    ExecutionScenario,
    MarketRules,
    OrderIntent,
    OrderKind,
    OrderStatus,
    PortfolioLedger,
    Side,
    load_scenarios,
    resolve_long_exit_in_candle,
    simulate_candle_taker,
)


FIVE_MINUTES_MS = 300_000
HOUR_MS = 3_600_000
FOUR_HOURS_MS = 14_400_000
DAY_MS = 86_400_000
CONFIRMATION_START_MS = 1_672_531_200_000  # 2023-01-01T00:00:00Z
CONFIRMATION_END_MS = 1_767_225_600_000  # 2026-01-01T00:00:00Z
CONFIRMATION_YEARS = (2023, 2024, 2025)


@dataclass(frozen=True)
class Row:
    segment: int
    open_ms: int
    open: float
    high: float
    low: float
    close: float
    base_volume: float
    quote_volume: float
    taker_buy_base: float
    taker_sell_base: float


@dataclass(frozen=True)
class Bar:
    segment: int
    open_ms: int
    close_ms: int
    open: float
    high: float
    low: float
    close: float
    base_volume: float
    quote_volume: float
    taker_buy_base: float
    taker_sell_base: float
    start_row: int
    end_row: int


@dataclass(frozen=True)
class SignalPoint:
    bar_index: int
    segment: int
    open_ms: int
    close_ms: int
    trigger_close: float
    trigger_low: float
    range_fraction: float
    return_shock: float
    range_ratio: float
    quote_volume_ratio: float
    close_location: float
    taker_imbalance: float
    compression_quantile: float
    rv24: float
    raw_return_24h: float
    entry_row: int


@dataclass(frozen=True)
class Thresholds:
    return_shock: float = 2.0
    range_ratio: float = 2.0
    quote_volume_ratio: float = 1.5
    compression_quantile: float = 0.20
    close_location: float = 0.80


def quantile(values: list[float], probability: float) -> float:
    if not values:
        raise ValueError("quantile requires values")
    if not 0 <= probability <= 1:
        raise ValueError("probability must be in [0, 1]")
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] * (high - position) + ordered[high] * (position - low)


def load_rows(path: Path) -> list[Row]:
    rows: list[Row] = []
    with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
        for source in csv.DictReader(handle):
            row = Row(
                segment=int(source["segment_id"]),
                open_ms=int(source["open_time_ms"]),
                open=float(source["open"]),
                high=float(source["high"]),
                low=float(source["low"]),
                close=float(source["close"]),
                base_volume=float(source["base_volume"]),
                quote_volume=float(source["quote_volume"]),
                taker_buy_base=float(source["taker_buy_base_volume"]),
                taker_sell_base=float(source["taker_sell_base_volume"]),
            )
            if not (
                row.open > 0
                and row.low > 0
                and row.low <= row.open <= row.high
                and row.low <= row.close <= row.high
                and row.base_volume >= 0
                and row.quote_volume >= 0
                and row.taker_buy_base >= 0
                and row.taker_sell_base >= 0
                and all(math.isfinite(value) for value in (
                    row.open, row.high, row.low, row.close, row.base_volume,
                    row.quote_volume, row.taker_buy_base, row.taker_sell_base,
                ))
            ):
                raise ValueError(f"invalid source row at {row.open_ms}")
            rows.append(row)
    return rows


def aggregate_bars(rows: list[Row], width_ms: int) -> tuple[list[Bar], int]:
    count = width_ms // FIVE_MINUTES_MS
    bars: list[Bar] = []
    used: set[int] = set()
    index = 0
    while index < len(rows):
        first = rows[index]
        if first.open_ms % width_ms:
            index += 1
            continue
        end = index + count
        bucket = rows[index:end]
        complete = len(bucket) == count and all(
            row.segment == first.segment
            and row.open_ms == first.open_ms + offset * FIVE_MINUTES_MS
            for offset, row in enumerate(bucket)
        )
        if not complete:
            index += 1
            continue
        bars.append(Bar(
            segment=first.segment,
            open_ms=first.open_ms,
            close_ms=first.open_ms + width_ms,
            open=first.open,
            high=max(row.high for row in bucket),
            low=min(row.low for row in bucket),
            close=bucket[-1].close,
            base_volume=sum(row.base_volume for row in bucket),
            quote_volume=sum(row.quote_volume for row in bucket),
            taker_buy_base=sum(row.taker_buy_base for row in bucket),
            taker_sell_base=sum(row.taker_sell_base for row in bucket),
            start_row=index,
            end_row=end - 1,
        ))
        used.update(range(index, end))
        index = end
    return bars, len(rows) - len(used)


def four_hour_context(bars: list[Bar]) -> dict[int, tuple[list[int], list[float], list[float]]]:
    """Return segment -> (close times, latest rv24, rank in prior-180 reference)."""
    grouped: dict[int, list[Bar]] = defaultdict(list)
    for bar in bars:
        grouped[bar.segment].append(bar)
    result: dict[int, tuple[list[int], list[float], list[float]]] = {}
    for segment, items in grouped.items():
        returns: list[float | None] = [None]
        returns.extend(math.log(items[i].close / items[i - 1].close) for i in range(1, len(items)))
        rv: list[float | None] = [None] * len(items)
        for i in range(6, len(items)):
            window = returns[i - 5:i + 1]
            if all(value is not None for value in window):
                rv[i] = math.sqrt(sum(float(value) ** 2 for value in window))
        times: list[int] = []
        latest_values: list[float] = []
        ranks: list[float] = []
        for i, value in enumerate(rv):
            if value is None or i < 180:
                continue
            reference = [candidate for candidate in rv[i - 180:i] if candidate is not None]
            if len(reference) != 180:
                continue
            # Invert the frozen type-7 quantile. Then value <= quantile(reference, q)
            # exactly when q is at least this position (apart from harmless fp epsilon).
            ordered = sorted(reference)
            insertion = bisect.bisect_left(ordered, value)
            if insertion == 0:
                rank = 0.0
            elif insertion == len(ordered):
                rank = 1.000000000001
            elif ordered[insertion] == value:
                rank = insertion / (len(ordered) - 1)
            else:
                lower = ordered[insertion - 1]
                upper = ordered[insertion]
                fraction = (value - lower) / (upper - lower)
                rank = (insertion - 1 + fraction) / (len(ordered) - 1)
            times.append(items[i].close_ms)
            latest_values.append(value)
            ranks.append(rank)
        result[segment] = (times, latest_values, ranks)
    return result


def build_signal_points(rows: list[Row], one_hour: list[Bar], four_hour: list[Bar]) -> list[SignalPoint]:
    context = four_hour_context(four_hour)
    by_segment: dict[int, list[tuple[int, Bar]]] = defaultdict(list)
    for index, bar in enumerate(one_hour):
        by_segment[bar.segment].append((index, bar))
    points: list[SignalPoint] = []
    for segment, indexed in by_segment.items():
        context_times, context_values, context_ranks = context.get(segment, ([], [], []))
        bars = [bar for _, bar in indexed]
        returns = [math.log(bar.close / bar.open) for bar in bars]
        log_ranges = [math.log(bar.high / bar.low) for bar in bars]
        range_fractions = [(bar.high - bar.low) / bar.close for bar in bars]
        for local_index in range(168, len(bars) - 24):
            bar = bars[local_index]
            prior_returns = returns[local_index - 168:local_index]
            return_median = statistics.median(prior_returns)
            sigma = 1.4826 * statistics.median(
                abs(value - return_median) for value in prior_returns
            )
            range_median = statistics.median(log_ranges[local_index - 168:local_index])
            volume_median = statistics.median(
                item.quote_volume for item in bars[local_index - 168:local_index]
            )
            range_fraction = statistics.median(
                range_fractions[local_index - 168:local_index]
            )
            if sigma <= 0 or range_median <= 0 or volume_median <= 0 or bar.high <= bar.low:
                continue
            context_index = bisect.bisect_right(context_times, bar.open_ms) - 1
            if context_index < 0:
                continue
            future = bars[local_index + 24]
            if future.open_ms != bar.open_ms + 24 * HOUR_MS:
                continue
            entry_row = bar.end_row + 1
            if (
                entry_row >= len(rows)
                or rows[entry_row].segment != segment
                or rows[entry_row].open_ms != bar.close_ms
            ):
                continue
            imbalance = (
                (bar.taker_buy_base - bar.taker_sell_base) / bar.base_volume
                if bar.base_volume > 0 else math.nan
            )
            values = (
                returns[local_index] / sigma,
                log_ranges[local_index] / range_median,
                bar.quote_volume / volume_median,
                (bar.close - bar.low) / (bar.high - bar.low),
                imbalance,
                context_ranks[context_index],
                context_values[context_index],
                math.log(future.close / bar.close),
                range_fraction,
            )
            if not all(math.isfinite(value) for value in values):
                continue
            points.append(SignalPoint(
                bar_index=indexed[local_index][0], segment=segment,
                open_ms=bar.open_ms, close_ms=bar.close_ms,
                trigger_close=bar.close, trigger_low=bar.low,
                range_fraction=range_fraction, return_shock=values[0],
                range_ratio=values[1], quote_volume_ratio=values[2],
                close_location=values[3], taker_imbalance=values[4],
                compression_quantile=values[5], rv24=values[6], raw_return_24h=values[7],
                entry_row=entry_row,
            ))
    return sorted(points, key=lambda point: point.open_ms)


def select_events(points: list[SignalPoint], thresholds: Thresholds) -> list[SignalPoint]:
    selected: list[SignalPoint] = []
    last_by_segment: dict[int, int] = {}
    for point in points:
        if not (
            point.compression_quantile <= thresholds.compression_quantile
            and point.return_shock >= thresholds.return_shock
            and point.range_ratio >= thresholds.range_ratio
            and point.quote_volume_ratio >= thresholds.quote_volume_ratio
            and point.close_location >= thresholds.close_location
            and point.taker_imbalance > 0
        ):
            continue
        if point.bar_index <= last_by_segment.get(point.segment, -10_000) + 24:
            continue
        selected.append(point)
        last_by_segment[point.segment] = point.bar_index
    return selected


def market_rules(snapshot_path: Path) -> MarketRules:
    payload = json.loads(snapshot_path.read_text())
    values = payload["normalized_rules"]
    return MarketRules(**{
        key: Decimal(values[key]) if key not in {"symbol", "effective_at", "source", "schema_version"} else values[key]
        for key in MarketRules.__dataclass_fields__
    })


def add_cost(total: dict[str, Decimal], cost: CostBreakdown) -> None:
    for name in CostBreakdown.__dataclass_fields__:
        total[name] += getattr(cost, name)


def annualized_ratios(daily_equity: list[tuple[int, float]]) -> tuple[float | None, float | None]:
    if len(daily_equity) < 2:
        return None, None
    returns = [daily_equity[i][1] / daily_equity[i - 1][1] - 1 for i in range(1, len(daily_equity))]
    if len(returns) < 2:
        return None, None
    mean = statistics.fmean(returns)
    deviation = statistics.stdev(returns)
    downside = math.sqrt(statistics.fmean(min(value, 0) ** 2 for value in returns))
    sharpe = mean / deviation * math.sqrt(365) if deviation else None
    sortino = mean / downside * math.sqrt(365) if downside else None
    return sharpe, sortino


def simulate_strategy(
    rows: list[Row], events: list[SignalPoint], scenario: ExecutionScenario,
    rules: MarketRules, start_ms: int = CONFIRMATION_START_MS,
    end_ms: int = CONFIRMATION_END_MS,
) -> dict:
    eligible = [event for event in events if start_ms <= event.open_ms < end_ms]
    schedule = {event.entry_row: event for event in eligible}
    ledger = PortfolioLedger(Decimal("1000"))
    position: dict | None = None
    costs = {name: Decimal("0") for name in CostBreakdown.__dataclass_fields__}
    trades: list[dict] = []
    entry_times: deque[int] = deque()
    entry_days: set[int] = set()
    missed = rejected = risk_distance_rejected = frequency_blocked = risk_blocked = 0
    forced_exits = stop_exits = time_exits = 0
    exposed = observed = 0
    turnover = Decimal("0")
    peak = Decimal("1000")
    maximum_drawdown = Decimal("0")
    strategy_halted = False
    daily_halted = False
    current_day: int | None = None
    day_start_equity = Decimal("1000")
    daily_ends: list[tuple[int, float]] = []

    def execute_exit(row: Row, reference: Decimal, reason: str, timestamp_ms: int) -> None:
        nonlocal position, turnover, forced_exits, stop_exits, time_exits
        assert position is not None and ledger.base_balance > 0
        intent = OrderIntent(
            client_order_id=f"{scenario.scenario_id}:exit:{timestamp_ms}:{reason}",
            side=Side.SELL, quantity=ledger.base_balance,
            decision_time_ns=timestamp_ms * 1_000_000,
            decision_price=Decimal(str(position["stop_price"] if reason.startswith("stop") else reference)),
            kind=OrderKind.PROTECTIVE, protective=True,
        )
        result = simulate_candle_taker(
            intent, reference, timestamp_ms * 1_000_000, scenario, rules,
        )
        if result.status is not OrderStatus.FILLED:
            raise RuntimeError(f"protective exit failed: {result.reason}")
        for fill in result.fills:
            ledger.apply_fill(fill)
            turnover += fill.notional
        add_cost(costs, result.costs)
        pnl = ledger.quote_balance - position["cash_before"]
        allocated = position["allocated"]
        raw_return = float(reference / position["entry_reference"] - Decimal("1"))
        trades.append({
            "entry_ms": position["entry_ms"], "exit_ms": timestamp_ms,
            "entry_year": datetime.fromtimestamp(position["event_ms"] / 1000, tz=timezone.utc).year,
            "entry_month": datetime.fromtimestamp(position["event_ms"] / 1000, tz=timezone.utc).strftime("%Y-%m"),
            "exit_reason": reason, "pnl_quote": float(pnl),
            "return_on_allocated": float(pnl / allocated), "gross_reference_return": raw_return,
            "compression_quantile_position": position["compression_quantile"],
            "rv24": position["rv24"],
            "holding_hours": (timestamp_ms - position["entry_ms"]) / HOUR_MS,
        })
        forced_exits += int(reason == "segment_boundary_exit")
        stop_exits += int(reason.startswith("stop"))
        time_exits += int(reason == "time_exit")
        position = None

    first_index = bisect.bisect_left([row.open_ms for row in rows], start_ms)
    for index in range(first_index, len(rows)):
        row = rows[index]
        entered_this_bar = False
        if row.open_ms >= end_ms + DAY_MS and position is None:
            break
        day = row.open_ms // DAY_MS
        equity_at_open = ledger.quote_balance + ledger.base_balance * Decimal(str(row.open))
        if day != current_day:
            if current_day is not None:
                daily_ends.append((current_day, float(equity_at_open)))
            current_day = day
            day_start_equity = equity_at_open
            daily_halted = False

        if position is not None:
            stop_resolution = resolve_long_exit_in_candle(
                Decimal(str(row.open)), Decimal(str(row.high)), Decimal(str(row.low)),
                Decimal(str(position["stop_price"])), None,
            )
            if stop_resolution:
                stop_reason, reference = stop_resolution
                execute_exit(row, reference, stop_reason, row.open_ms)
            elif row.open_ms >= position["entry_ms"] + 24 * HOUR_MS:
                execute_exit(row, Decimal(str(row.open)), "time_exit", row.open_ms)

        event = schedule.get(index)
        if event is not None:
            while entry_times and entry_times[0] <= row.open_ms - 7 * DAY_MS:
                entry_times.popleft()
            if position is not None or strategy_halted or daily_halted:
                risk_blocked += 1
            elif row.open_ms // DAY_MS in entry_days or len(entry_times) >= 4:
                frequency_blocked += 1
            else:
                equity = ledger.quote_balance
                estimated = Decimal(str(row.open)) * (
                    Decimal("1") + scenario.implicit_cost_bps_per_side / Decimal("10000")
                )
                stop = Decimal(str(event.trigger_low * (1 - 0.25 * event.range_fraction)))
                distance = (estimated - stop) / estimated
                if distance < Decimal("0.005") or distance > Decimal("0.05"):
                    risk_distance_rejected += 1
                else:
                    quantity = min(
                        Decimal("0.25") * equity / estimated,
                        Decimal("0.005") * equity / (estimated - stop),
                    )
                    cash_before = ledger.quote_balance
                    intent = OrderIntent(
                        client_order_id=f"{scenario.scenario_id}:entry:{row.open_ms}",
                        side=Side.BUY, quantity=quantity,
                        decision_time_ns=event.close_ms * 1_000_000,
                        decision_price=Decimal(str(event.trigger_close)),
                    )
                    result = simulate_candle_taker(
                        intent, Decimal(str(row.open)), row.open_ms * 1_000_000,
                        scenario, rules,
                    )
                    add_cost(costs, result.costs)
                    if result.status is OrderStatus.FILLED:
                        for fill in result.fills:
                            ledger.apply_fill(fill)
                            turnover += fill.notional
                        allocated = cash_before - ledger.quote_balance
                        position = {
                            "event_ms": event.open_ms, "entry_ms": row.open_ms,
                            "entry_reference": Decimal(str(row.open)),
                            "stop_price": stop, "cash_before": cash_before,
                            "allocated": allocated,
                            "compression_quantile": event.compression_quantile,
                            "rv24": event.rv24,
                        }
                        entered_this_bar = True
                        entry_times.append(row.open_ms)
                        entry_days.add(row.open_ms // DAY_MS)
                    elif result.status is OrderStatus.EXPIRED:
                        missed += 1
                    else:
                        rejected += 1

        # An entry fills at the 5m open, so the remainder of that same candle is
        # observable holding time and may hit the protective stop.
        if position is not None and entered_this_bar:
            stop_resolution = resolve_long_exit_in_candle(
                Decimal(str(row.open)), Decimal(str(row.high)), Decimal(str(row.low)),
                Decimal(str(position["stop_price"])), None,
            )
            if stop_resolution:
                stop_reason, reference = stop_resolution
                execute_exit(row, reference, stop_reason, row.open_ms)

        last_in_segment = index + 1 == len(rows) or rows[index + 1].segment != row.segment
        if position is not None and last_in_segment:
            execute_exit(
                row, Decimal(str(row.close)), "segment_boundary_exit",
                row.open_ms + FIVE_MINUTES_MS,
            )

        equity = ledger.quote_balance + ledger.base_balance * Decimal(str(row.close))
        observed += 1
        exposed += int(position is not None)
        peak = max(peak, equity)
        drawdown = equity / peak - Decimal("1")
        maximum_drawdown = min(maximum_drawdown, drawdown)
        if equity <= day_start_equity * Decimal("0.985"):
            daily_halted = True
        if equity <= peak * Decimal("0.90"):
            strategy_halted = True

    if current_day is not None:
        final_equity = ledger.quote_balance + ledger.base_balance * Decimal(str(rows[-1].close))
        daily_ends.append((current_day, float(final_equity)))
    else:
        final_equity = Decimal("1000")
    returns = [trade["return_on_allocated"] for trade in trades]
    gains = sum(value for value in returns if value > 0)
    losses = -sum(value for value in returns if value < 0)
    sharpe, sortino = annualized_ratios(daily_ends)
    annual_pnl: dict[str, float] = {}
    annual_trades: dict[str, int] = {}
    for year in CONFIRMATION_YEARS:
        selected = [trade for trade in trades if trade["entry_year"] == year]
        annual_pnl[str(year)] = sum(trade["pnl_quote"] for trade in selected)
        annual_trades[str(year)] = len(selected)
    monthly: dict[str, dict] = {}
    for month in sorted({trade["entry_month"] for trade in trades}):
        selected = [trade for trade in trades if trade["entry_month"] == month]
        monthly[month] = {
            "trades": len(selected),
            "pnl_quote": sum(trade["pnl_quote"] for trade in selected),
            "mean_net_trade_return": statistics.fmean(
                trade["return_on_allocated"] for trade in selected
            ),
        }
    compression_regimes: dict[str, dict] = {}
    for label, lower, upper in (
        ("q00_q05", 0.00, 0.05), ("q05_q10", 0.05, 0.10),
        ("q10_q15", 0.10, 0.15), ("q15_q20", 0.15, 0.200000000001),
    ):
        selected = [
            trade for trade in trades
            if lower <= trade["compression_quantile_position"] < upper
        ]
        compression_regimes[label] = {
            "trades": len(selected),
            "pnl_quote": sum(trade["pnl_quote"] for trade in selected),
            "mean_net_trade_return": statistics.fmean(
                trade["return_on_allocated"] for trade in selected
            ) if selected else None,
        }
    volatility_regimes: dict[str, dict] = {}
    if trades:
        rv_values = [trade["rv24"] for trade in trades]
        bounds = [
            -math.inf, quantile(rv_values, 0.25), quantile(rv_values, 0.50),
            quantile(rv_values, 0.75), math.inf,
        ]
        for position, label in enumerate(("sample_q1", "sample_q2", "sample_q3", "sample_q4")):
            selected = [
                trade for trade in trades
                if bounds[position] <= trade["rv24"] < bounds[position + 1]
            ]
            volatility_regimes[label] = {
                "lower": None if math.isinf(bounds[position]) else bounds[position],
                "upper": None if math.isinf(bounds[position + 1]) else bounds[position + 1],
                "trades": len(selected),
                "pnl_quote": sum(trade["pnl_quote"] for trade in selected),
                "mean_net_trade_return": statistics.fmean(
                    trade["return_on_allocated"] for trade in selected
                ) if selected else None,
            }
    return {
        "scenario_id": scenario.scenario_id,
        "scenario_sha256": scenario.checksum,
        "market_rules_sha256": rules.checksum,
        "starting_equity": 1000.0,
        "ending_equity": float(final_equity),
        "net_return": float(final_equity / Decimal("1000") - Decimal("1")),
        "mean_net_trade_return": statistics.fmean(returns) if returns else None,
        "median_net_trade_return": statistics.median(returns) if returns else None,
        "mean_gross_reference_return": statistics.fmean(
            trade["gross_reference_return"] for trade in trades
        ) if trades else None,
        "profit_factor": gains / losses if losses else None,
        "win_rate": sum(value > 0 for value in returns) / len(returns) if returns else None,
        "maximum_drawdown_fraction": float(-maximum_drawdown),
        "trade_count": len(trades), "eligible_event_count": len(eligible),
        "missed_entry_count": missed, "rejected_order_count": rejected,
        "risk_distance_rejected_count": risk_distance_rejected,
        "frequency_blocked_count": frequency_blocked, "risk_blocked_count": risk_blocked,
        "turnover_quote": float(turnover), "exposure_fraction": exposed / observed if observed else 0,
        "sharpe_daily_annualized": sharpe, "sortino_daily_annualized": sortino,
        "costs_quote": {name: float(value) for name, value in costs.items()},
        "total_cost_quote": float(sum(costs.values(), Decimal("0"))),
        "stop_exit_count": stop_exits, "time_exit_count": time_exits,
        "segment_boundary_exit_count": forced_exits,
        "annual_trade_count": annual_trades, "annual_pnl_quote": annual_pnl,
        "monthly_results": monthly,
        "compression_quantile_regimes": compression_regimes,
        "realized_volatility_sample_quartiles": volatility_regimes,
        "trades": trades,
    }


def bootstrap_days(trades: list[dict], seed: int = 20260825, replicates: int = 10_000) -> list[float]:
    grouped: dict[int, list[float]] = defaultdict(list)
    for trade in trades:
        grouped[trade["entry_ms"] // DAY_MS].append(trade["return_on_allocated"])
    days = list(grouped.values())
    if not days:
        return []
    rng = random.Random(seed)
    results = []
    for _ in range(replicates):
        sample = [days[rng.randrange(len(days))] for _ in days]
        results.append(statistics.fmean(value for day in sample for value in day))
    return sorted(results)


def raw_summary(events: list[SignalPoint]) -> dict:
    confirmation = [event for event in events if CONFIRMATION_START_MS <= event.open_ms < CONFIRMATION_END_MS]
    annual = {}
    for year in CONFIRMATION_YEARS:
        values = [
            event.raw_return_24h for event in confirmation
            if datetime.fromtimestamp(event.open_ms / 1000, tz=timezone.utc).year == year
        ]
        annual[str(year)] = {
            "events": len(values),
            "mean_log_return": statistics.fmean(values) if values else None,
            "median_log_return": statistics.median(values) if values else None,
            "positive_fraction": sum(value > 0 for value in values) / len(values) if values else None,
        }
    values = [event.raw_return_24h for event in confirmation]
    return {
        "events": len(values), "mean_log_return": statistics.fmean(values) if values else None,
        "mean_bps": statistics.fmean(values) * 10_000 if values else None,
        "median_log_return": statistics.median(values) if values else None,
        "annual": annual,
    }


def sensitivity_definitions() -> list[tuple[str, Thresholds]]:
    base = asdict(Thresholds())
    definitions = []
    for name, values in (
        ("return_shock", (1.75, 2.25)), ("range_ratio", (1.75, 2.25)),
        ("quote_volume_ratio", (1.25, 1.75)),
        ("compression_quantile", (0.15, 0.25)),
        ("close_location", (0.75, 0.85)),
    ):
        for value in values:
            changed = dict(base)
            changed[name] = value
            definitions.append((f"{name}={value}", Thresholds(**changed)))
    return definitions


def matched_buy_hold(rows: list[Row], scenario: ExecutionScenario, rules: MarketRules) -> dict:
    period = [row for row in rows if CONFIRMATION_START_MS <= row.open_ms < CONFIRMATION_END_MS]
    if not period:
        return {"error": "no rows"}
    ledger = PortfolioLedger(Decimal("1000"))
    quantity = Decimal("250") / Decimal(str(period[0].open))
    buy = OrderIntent("buy-hold-entry", Side.BUY, quantity, period[0].open_ms * 1_000_000, Decimal(str(period[0].open)))
    buy_result = simulate_candle_taker(buy, Decimal(str(period[0].open)), buy.decision_time_ns, scenario, rules)
    for fill in buy_result.fills:
        ledger.apply_fill(fill)
    peak = Decimal("1000")
    max_drawdown = Decimal("0")
    for row in period:
        equity = ledger.quote_balance + ledger.base_balance * Decimal(str(row.close))
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, equity / peak - Decimal("1"))
    last = period[-1]
    sell = OrderIntent(
        "buy-hold-exit", Side.SELL, ledger.base_balance,
        (last.open_ms + FIVE_MINUTES_MS) * 1_000_000, Decimal(str(last.close)),
        OrderKind.PROTECTIVE, protective=True,
    )
    sell_result = simulate_candle_taker(
        sell, Decimal(str(last.close)), sell.decision_time_ns, scenario, rules,
    )
    for fill in sell_result.fills:
        ledger.apply_fill(fill)
    return {
        "allocation_fraction": 0.25, "net_return": float(ledger.quote_balance / Decimal("1000") - 1),
        "maximum_drawdown_fraction": float(-max_drawdown),
        "entry_status": buy_result.status.value, "exit_status": sell_result.status.value,
    }


def verify_inputs(args: argparse.Namespace) -> tuple[dict, dict, str]:
    hypothesis = json.loads(args.hypothesis.read_text())
    manifest = json.loads(args.manifest.read_text())
    digest = hashlib.sha256(args.data.read_bytes()).hexdigest()
    if hypothesis.get("experiment_id") != "btc-volatility-expansion-continuation-v1":
        raise ValueError("exact frozen volatility-expansion hypothesis required")
    if hypothesis.get("status") != "frozen_pre_analysis":
        raise ValueError("hypothesis must be frozen_pre_analysis")
    if hypothesis.get("lineage", {}).get("holdout_permitted") is not False:
        raise ValueError("holdout must remain locked")
    if manifest.get("partition") != "development-2017-2025" or not manifest.get("accepted"):
        raise ValueError("accepted development partition required; holdout paths are prohibited")
    if manifest.get("dataset_sha256") != digest or hypothesis["lineage"]["development_dataset_sha256"] != digest:
        raise ValueError("development dataset checksum mismatch")
    if "holdout" in args.data.name.lower():
        raise ValueError("holdout data path is prohibited")
    hypothesis_digest = hashlib.sha256(args.hypothesis.read_bytes()).hexdigest()
    return hypothesis, manifest, hypothesis_digest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--hypothesis", type=Path, required=True)
    parser.add_argument("--scenario-config", type=Path, default=Path("config/execution_scenarios.json"))
    parser.add_argument("--market-rules", type=Path, default=Path("artifacts/real-data-research/BTCUSDT-market-rules-20260825.json"))
    parser.add_argument("--sma-control", type=Path, default=Path("artifacts/agent-level-experiment/btc-taker-history/btc-4h-sma-10-30-execution-model-v1-report.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    hypothesis, manifest, hypothesis_digest = verify_inputs(args)
    rows = load_rows(args.data)
    one_hour, discarded_1h = aggregate_bars(rows, HOUR_MS)
    four_hour, discarded_4h = aggregate_bars(rows, FOUR_HOURS_MS)
    points = build_signal_points(rows, one_hour, four_hour)
    events = select_events(points, Thresholds())
    scenarios = load_scenarios(args.scenario_config)
    rules = market_rules(args.market_rules)
    selected_ids = [
        hypothesis["orders_and_position"]["primary_execution_scenario_id"],
        *hypothesis["orders_and_position"]["stress_execution_scenario_ids"],
    ]
    scenario_results = {
        scenario_id: simulate_strategy(rows, events, scenarios[scenario_id], rules)
        for scenario_id in selected_ids
    }
    primary = scenario_results[selected_ids[0]]
    stress = scenario_results[selected_ids[1]]
    bootstrap = bootstrap_days(primary["trades"])
    bootstrap_ci = [quantile(bootstrap, 0.025), quantile(bootstrap, 0.975)] if bootstrap else [None, None]
    raw = raw_summary(events)
    sensitivities = {}
    positive_sensitivities = 0
    for name, thresholds in sensitivity_definitions():
        variant_events = select_events(points, thresholds)
        result = simulate_strategy(rows, variant_events, scenarios[selected_ids[0]], rules)
        positive = result["mean_net_trade_return"] is not None and result["mean_net_trade_return"] > 0
        positive_sensitivities += int(positive)
        sensitivities[name] = {
            "event_count": len([event for event in variant_events if CONFIRMATION_START_MS <= event.open_ms < CONFIRMATION_END_MS]),
            "trade_count": result["trade_count"],
            "mean_net_trade_return": result["mean_net_trade_return"],
            "net_return": result["net_return"], "positive_net_mean": positive,
        }
    annual_positive_pnl = [value for value in primary["annual_pnl_quote"].values() if value > 0]
    concentration = max(annual_positive_pnl) / sum(annual_positive_pnl) if annual_positive_pnl else None
    gates = {
        "minimum_30_executed_trades_each_confirmation_year": all(
            primary["annual_trade_count"][str(year)] >= 30 for year in CONFIRMATION_YEARS
        ),
        "positive_primary_raw_24h_mean_each_confirmation_year": all(
            raw["annual"][str(year)]["mean_log_return"] is not None
            and raw["annual"][str(year)]["mean_log_return"] > 0
            for year in CONFIRMATION_YEARS
        ),
        "pooled_primary_raw_24h_mean_at_least_45bps": raw["mean_bps"] is not None and raw["mean_bps"] >= 45,
        "primary_net_mean_trade_return_gt_zero": primary["mean_net_trade_return"] is not None and primary["mean_net_trade_return"] > 0,
        "primary_profit_factor_at_least_1_10": primary["profit_factor"] is not None and primary["profit_factor"] >= 1.10,
        "primary_bootstrap_95pct_lower_bound_gt_zero": bootstrap_ci[0] is not None and bootstrap_ci[0] > 0,
        "stress_40bps_net_mean_trade_return_gte_zero": stress["mean_net_trade_return"] is not None and stress["mean_net_trade_return"] >= 0,
        "maximum_drawdown_lte_10pct": primary["maximum_drawdown_fraction"] <= 0.10,
        "largest_positive_year_pnl_share_lte_50pct": concentration is not None and concentration <= 0.50,
        "at_least_7_of_10_sensitivities_positive_net_mean": positive_sensitivities >= 7,
    }
    accepted = all(gates.values())
    sma_control = json.loads(args.sma_control.read_text()) if args.sma_control.exists() else None
    report = {
        "schema_version": "btc-volatility-expansion-development-report-v1",
        "experiment_id": hypothesis["experiment_id"],
        "decision": "development_gates_passed_holdout_unlock_review_required" if accepted else "rejected_before_holdout",
        "accepted_for_holdout": accepted,
        "holdout_accessed": False,
        "implementation_file": str(Path(__file__)),
        "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "hypothesis_sha256": hypothesis_digest,
        "development_dataset_sha256": manifest["dataset_sha256"],
        "development_manifest_sha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
        "execution_scenarios_sha256": hashlib.sha256(args.scenario_config.read_bytes()).hexdigest(),
        "market_rules_snapshot_sha256": hashlib.sha256(args.market_rules.read_bytes()).hexdigest(),
        "rows_5m": len(rows), "bars_1h": len(one_hour), "bars_4h": len(four_hour),
        "discarded_source_rows_for_1h_aggregation": discarded_1h,
        "discarded_source_rows_for_4h_aggregation": discarded_4h,
        "feature_ready_1h_points": len(points), "frozen_event_count_all_development": len(events),
        "raw_confirmation": raw, "execution_scenarios": scenario_results,
        "bootstrap_primary_net_mean_ci95": bootstrap_ci,
        "bootstrap_replicates": 10_000, "bootstrap_seed": 20260825,
        "one_at_a_time_sensitivities": sensitivities,
        "positive_sensitivities_out_of_10": positive_sensitivities,
        "positive_year_pnl_concentration": concentration,
        "benchmarks": {
            "flat_no_trade": {"net_return": 0.0, "maximum_drawdown_fraction": 0.0},
            "buy_and_hold_25pct_primary_cost": matched_buy_hold(rows, scenarios[selected_ids[0]], rules),
            "sma_10_30_control_report": str(args.sma_control),
            "sma_10_30_control_report_sha256": hashlib.sha256(args.sma_control.read_bytes()).hexdigest() if args.sma_control.exists() else None,
            "sma_10_30_control": sma_control,
        },
        "development_gates": gates,
        "gate_failures": [name for name, passed in gates.items() if not passed],
        "change_control": "A failure rejects this experiment. Do not tune or open the holdout under this experiment ID.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "decision": report["decision"], "events": raw["events"],
        "primary": {key: primary[key] for key in (
            "trade_count", "net_return", "mean_net_trade_return", "profit_factor",
            "maximum_drawdown_fraction", "annual_trade_count", "annual_pnl_quote",
        )},
        "bootstrap_ci95": bootstrap_ci, "gates": gates,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
