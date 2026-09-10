"""Unchanged fixed BTC breakout adapted to offline counterfactual arm contracts."""

from __future__ import annotations

import statistics
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from trading_platform.research_ledger import (
    DAY_MS,
    FIVE_MINUTES_MS,
    AggregateCandle,
    SourceCandle,
)
from trading_platform.research_routing import ArmForecast, canonical_digest


UTC = timezone.utc


@dataclass(frozen=True, slots=True)
class BreakoutForecastRecord:
    bar_index: int
    forecast: ArmForecast

    def as_dict(self) -> dict[str, Any]:
        payload = {"bar_index": self.bar_index, **self.forecast.as_dict()}
        return {**payload, "forecast_digest": canonical_digest(payload)}


def breakout_forecasts(
    bars: list[AggregateCandle],
    *,
    lookback: int,
    evaluation_start_ms: int,
    evidence_digest: str,
) -> list[BreakoutForecastRecord]:
    output: list[BreakoutForecastRecord] = []
    for index, bar in enumerate(bars):
        if bar.close_ms <= evaluation_start_ms or index < lookback:
            continue
        prior = bars[index - lookback : index]
        same_segment = all(item.segment == bar.segment for item in prior)
        triggered = same_segment and bar.close > max(item.high for item in prior)
        lineage = canonical_digest(
            {
                "arm_evidence_digest": evidence_digest,
                "bar": bar.as_dict(),
                "lookback": lookback,
                "prior": [item.as_dict() for item in prior],
            }
        )
        decision = datetime.fromtimestamp(bar.close_ms / 1000, tz=UTC)
        output.append(
            BreakoutForecastRecord(
                bar_index=index,
                forecast=ArmForecast(
                    arm_id="btc_breakout_20d_10d",
                    arm_version="1",
                    decision_at=decision,
                    available_at=decision,
                    expires_at=decision + timedelta(milliseconds=FIVE_MINUTES_MS),
                    forecast_score=1.0 if triggered else 0.0,
                    confidence=1.0,
                    horizon="14d_maximum",
                    abstention_reason=None if triggered else (
                        "entry_channel_not_breached"
                        if same_segment
                        else "insufficient_same_segment_history"
                    ),
                    lineage_digest=lineage,
                ),
            )
        )
    return output


def signal_indices(forecasts: list[BreakoutForecastRecord]) -> list[int]:
    return [item.bar_index for item in forecasts if item.forecast.abstention_reason is None]


def exit_execution_rows(
    rows: list[SourceCandle], bars: list[AggregateCandle], lookback: int
) -> dict[int, str]:
    exits: dict[int, str] = {}
    for index, bar in enumerate(bars):
        if index < lookback:
            continue
        prior = bars[index - lookback : index]
        entry_row = bar.end_row + 1
        if (
            all(item.segment == bar.segment for item in prior)
            and bar.close < min(item.low for item in prior)
            and entry_row < len(rows)
            and rows[entry_row].segment == bar.segment
            and rows[entry_row].open_ms == bar.close_ms
        ):
            exits[entry_row] = "exit_channel"
    return exits


def resolve_exit(
    rows: list[SourceCandle],
    entry_row: int,
    planned_exits: dict[int, str],
    stop_fraction: float,
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
    rows: list[SourceCandle],
    bars: list[AggregateCandle],
    signals: list[int],
    planned_exits: dict[int, str],
    *,
    side_cost_bps: float,
    price_protection_bps: float,
    evaluation_start_ms: int,
    evaluation_end_ms: int,
    stop_fraction: float = 0.04,
    maximum_holding_days: int = 14,
    allocation: float = 0.10,
) -> dict[str, Any]:
    cash = 1000.0
    trades: list[dict[str, Any]] = []
    expired = frequency_blocked = busy_blocked = 0
    unavailable_until = -1
    entry_decisions: deque[int] = deque()
    for signal_index in signals:
        bar = bars[signal_index]
        entry_row = bar.end_row + 1
        if entry_row <= unavailable_until:
            busy_blocked += 1
            continue
        if (
            entry_row >= len(rows)
            or rows[entry_row].segment != bar.segment
            or rows[entry_row].open_ms != bar.close_ms
        ):
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
            rows, entry_row, planned_exits, stop_fraction, maximum_holding_days
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
        trades.append(
            {
                "cash_after": cash_after,
                "cash_before": cash,
                "entry_fill": entry_fill,
                "entry_month": datetime.fromtimestamp(entry.open_ms / 1000, tz=UTC).strftime(
                    "%Y-%m"
                ),
                "entry_ms": entry.open_ms,
                "entry_reference": entry.open,
                "entry_row": entry_row,
                "entry_year": datetime.fromtimestamp(entry.open_ms / 1000, tz=UTC).year,
                "exit_fill": exit_fill,
                "exit_ms": rows[exit_row].open_ms,
                "exit_reason": reason,
                "exit_reference": exit_reference,
                "exit_row": exit_row,
                "gross_reference_return": exit_reference / entry.open - 1.0,
                "holding_days": (rows[exit_row].open_ms - entry.open_ms) / DAY_MS,
                "pnl_quote": pnl,
                "quantity": quantity,
                "remaining_cash": remaining_cash,
                "return_on_allocated": proceeds / budget - 1.0,
                "signal_ms": decision_ms,
            }
        )
        cash = cash_after
        unavailable_until = exit_row
    return summarize_simulation(
        rows,
        trades,
        cash,
        side_cost_bps,
        expired,
        frequency_blocked,
        busy_blocked,
        evaluation_start_ms,
        evaluation_end_ms,
    )


def summarize_simulation(
    rows: list[SourceCandle],
    trades: list[dict[str, Any]],
    final_cash: float,
    side_cost_bps: float,
    expired: int,
    frequency_blocked: int,
    busy_blocked: int,
    evaluation_start_ms: int,
    evaluation_end_ms: int,
) -> dict[str, Any]:
    eval_rows = [
        index
        for index, row in enumerate(rows)
        if evaluation_start_ms <= row.open_ms < evaluation_end_ms
    ]
    active = 0
    peak = 1000.0
    max_drawdown = 0.0
    annual_end: dict[int, float] = {}
    trade_position = 0
    cash = 1000.0
    current: dict[str, Any] | None = trades[0] if trades else None
    for index in eval_rows:
        row = rows[index]
        while current is not None and index > current["exit_row"]:
            cash = current["cash_after"]
            trade_position += 1
            current = trades[trade_position] if trade_position < len(trades) else None
        if current is not None and current["entry_row"] <= index <= current["exit_row"]:
            equity = (
                current["cash_after"]
                if index == current["exit_row"]
                else current["remaining_cash"] + current["quantity"] * row.close
            )
            active += 1
        else:
            equity = cash
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, equity / peak - 1.0)
        annual_end[datetime.fromtimestamp(row.open_ms / 1000, tz=UTC).year] = equity
    years: dict[str, float] = {}
    prior = 1000.0
    for year in sorted(annual_end):
        years[str(year)] = annual_end[year] / prior - 1.0
        prior = annual_end[year]
    returns = [item["return_on_allocated"] for item in trades]
    gains = sum(item["pnl_quote"] for item in trades if item["pnl_quote"] > 0)
    losses = -sum(item["pnl_quote"] for item in trades if item["pnl_quote"] < 0)
    months: dict[str, dict[str, Any]] = {}
    for month in sorted({item["entry_month"] for item in trades}):
        selected = [item for item in trades if item["entry_month"] == month]
        months[month] = {
            "pnl_quote": sum(item["pnl_quote"] for item in selected),
            "trades": len(selected),
        }
    positive_months = [item["pnl_quote"] for item in months.values() if item["pnl_quote"] > 0]
    concentration = (
        sum(sorted(positive_months, reverse=True)[:3]) / sum(positive_months)
        if positive_months
        else None
    )
    years_elapsed = (evaluation_end_ms - evaluation_start_ms) / (365.2425 * DAY_MS)
    net_return = final_cash / 1000.0 - 1.0
    cagr = (final_cash / 1000.0) ** (1.0 / years_elapsed) - 1.0
    calmar = cagr / abs(max_drawdown) if max_drawdown < 0 else None
    reasons = {item["exit_reason"] for item in trades}
    return {
        "busy_signal_count": busy_blocked,
        "cagr": cagr,
        "calendar_year_returns": years,
        "calmar": calmar,
        "ending_equity": final_cash,
        "exit_reasons": dict(
            sorted((reason, sum(trade["exit_reason"] == reason for trade in trades)) for reason in reasons)
        ),
        "expired_entry_count": expired,
        "exposure_fraction": active / len(eval_rows) if eval_rows else 0.0,
        "frequency_blocked_count": frequency_blocked,
        "maximum_drawdown_fraction": -max_drawdown,
        "mean_net_trade_bps": statistics.fmean(returns) * 10_000 if returns else None,
        "mean_net_trade_return": statistics.fmean(returns) if returns else None,
        "monthly_results": months,
        "net_return": net_return,
        "positive_calendar_years": sum(value > 0 for value in years.values()),
        "profit_factor": gains / losses if losses else None,
        "round_trip_cost_bps": side_cost_bps * 2,
        "side_cost_bps": side_cost_bps,
        "starting_equity": 1000.0,
        "top_three_profitable_months_share": concentration,
        "trade_count": len(trades),
        "trades": trades,
        "win_rate": sum(value > 0 for value in returns) / len(returns) if returns else None,
    }


def segmented_buy_hold(
    rows: list[SourceCandle],
    *,
    side_cost_bps: float,
    evaluation_start_ms: int,
    evaluation_end_ms: int,
    allocation: float = 0.10,
) -> dict[str, Any]:
    selected = [row for row in rows if evaluation_start_ms <= row.open_ms < evaluation_end_ms]
    grouped: dict[int, list[SourceCandle]] = defaultdict(list)
    for row in selected:
        grouped[row.segment].append(row)
    cash = 1000.0
    peak = cash
    maximum_drawdown = 0.0
    side_cost = side_cost_bps / 10_000.0
    segments: list[dict[str, Any]] = []
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
        segments.append(
            {
                "entry_ms": first.open_ms,
                "exit_ms": last.open_ms,
                "return_on_allocated": proceeds / budget - 1.0,
                "segment": segment,
            }
        )
        cash = cash_after
    years_elapsed = (evaluation_end_ms - evaluation_start_ms) / (365.2425 * DAY_MS)
    return {
        "allocation_fraction": allocation,
        "cagr": (cash / 1000.0) ** (1.0 / years_elapsed) - 1.0,
        "maximum_drawdown_fraction": -maximum_drawdown,
        "net_return": cash / 1000.0 - 1.0,
        "segment_returns": segments,
        "segments": len(segments),
    }
