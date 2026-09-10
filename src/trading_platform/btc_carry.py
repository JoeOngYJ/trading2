"""Offline paired BTC spot/perpetual carry backtesting primitives."""

from __future__ import annotations

import math
import random
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
from typing import Any, Iterable


UTC = timezone.utc
HOUR_MS = 3_600_000
DAY_MS = 24 * HOUR_MS
WEEK_MS = 7 * DAY_MS
BPS = Decimal("10000")
ZERO = Decimal("0")


class CarryBacktestError(ValueError):
    """Raised when carry inputs or causal boundaries fail closed."""


@dataclass(frozen=True, slots=True)
class HourBar:
    open_ms: int
    open: Decimal
    close: Decimal
    segment: str = "continuous"

    def __post_init__(self) -> None:
        if self.open_ms < 0 or self.open_ms % HOUR_MS:
            raise CarryBacktestError("hour bar timestamp must be a non-negative exact UTC hour")
        if self.open <= 0 or self.close <= 0 or not self.open.is_finite() or not self.close.is_finite():
            raise CarryBacktestError("hour bar prices must be finite and positive")
        if not self.segment:
            raise CarryBacktestError("hour bar segment is required")


@dataclass(frozen=True, slots=True)
class FundingEvent:
    scheduled_ms: int
    observed_ms: int
    rate: Decimal

    def __post_init__(self) -> None:
        if self.scheduled_ms < 0 or self.scheduled_ms % (8 * HOUR_MS):
            raise CarryBacktestError("funding schedule must be aligned to eight-hour UTC events")
        if not self.scheduled_ms <= self.observed_ms < self.scheduled_ms + 1000:
            raise CarryBacktestError("funding observation must be within one second after schedule")
        if not self.rate.is_finite():
            raise CarryBacktestError("funding rate must be finite")


@dataclass(frozen=True, slots=True)
class CarryCostScenario:
    scenario_id: str
    fee_bps_per_fill: Decimal
    implicit_bps_per_fill: Decimal

    def __post_init__(self) -> None:
        if not self.scenario_id or self.fee_bps_per_fill < 0 or self.implicit_bps_per_fill < 0:
            raise CarryBacktestError("cost scenario identity and non-negative costs are required")


@dataclass(frozen=True, slots=True)
class CarryParameters:
    lookback_events: int = 84
    entry_threshold_bps: Decimal = Decimal("60")
    exit_threshold_bps: Decimal = Decimal("30")
    maximum_holding_days: int = 84
    leg_fraction: Decimal = Decimal("0.49")
    quantity_step: Decimal = Decimal("0.00001")
    maintenance_margin_fraction: Decimal = Decimal("0.10")
    adverse_mark_shock_fraction: Decimal = Decimal("0.20")

    def __post_init__(self) -> None:
        if self.lookback_events <= 0 or self.maximum_holding_days <= 0:
            raise CarryBacktestError("positive lookback and holding period are required")
        if not ZERO < self.leg_fraction < Decimal("0.5"):
            raise CarryBacktestError("each leg must use less than half of equity")
        if self.quantity_step <= 0:
            raise CarryBacktestError("positive quantity step is required")
        if not ZERO < self.maintenance_margin_fraction < Decimal("1"):
            raise CarryBacktestError("maintenance margin fraction must be in (0, 1)")
        if not ZERO < self.adverse_mark_shock_fraction < Decimal("1"):
            raise CarryBacktestError("adverse mark shock must be in (0, 1)")


def utc_ms(value: str) -> int:
    if not value.endswith("Z"):
        raise CarryBacktestError("timestamp must use an explicit UTC Z suffix")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    return int(parsed.timestamp() * 1000)


def iso_utc(value: int) -> str:
    return datetime.fromtimestamp(value / 1000, tz=UTC).isoformat().replace("+00:00", "Z")


def funding_score_bps(events: list[FundingEvent], decision_ms: int, count: int) -> Decimal | None:
    available = [event for event in events if event.observed_ms <= decision_ms]
    if len(available) < count:
        return None
    window = available[-count:]
    if any(right.scheduled_ms - left.scheduled_ms != 8 * HOUR_MS for left, right in zip(window, window[1:])):
        return None
    return sum((event.rate for event in window), ZERO) * BPS


def _quantity(equity: Decimal, spot: Decimal, future: Decimal, params: CarryParameters) -> Decimal:
    target = equity * params.leg_fraction
    raw = min(target / spot, target / future)
    return raw.quantize(params.quantity_step, rounding=ROUND_DOWN)


def _metrics(daily_equity: list[tuple[int, Decimal]], trades: list[dict[str, Any]], start: Decimal) -> dict[str, Any]:
    if not daily_equity:
        raise CarryBacktestError("daily equity observations are required")
    values = [value for _, value in daily_equity]
    net = values[-1] / start - Decimal("1")
    returns = [float(right / left - Decimal("1")) for left, right in zip(values, values[1:]) if left > 0]
    years = max((daily_equity[-1][0] - daily_equity[0][0]) / (365.25 * DAY_MS), 1 / 365.25)
    cagr = float(values[-1] / start) ** (1 / years) - 1 if values[-1] > 0 else None
    peak = values[0]
    max_dd = Decimal("0")
    for value in values:
        peak = max(peak, value)
        if peak > 0:
            max_dd = max(max_dd, Decimal("1") - value / peak)
    sharpe = None
    sortino = None
    if len(returns) >= 2:
        volatility = statistics.stdev(returns)
        sharpe = statistics.fmean(returns) / volatility * math.sqrt(365) if volatility > 0 else None
        downside = [min(value, 0.0) for value in returns]
        downside_dev = math.sqrt(statistics.fmean(value * value for value in downside))
        sortino = statistics.fmean(returns) / downside_dev * math.sqrt(365) if downside_dev > 0 else None
    profits = [Decimal(item["net_pnl"]) for item in trades if Decimal(item["net_pnl"]) > 0]
    losses = [-Decimal(item["net_pnl"]) for item in trades if Decimal(item["net_pnl"]) < 0]
    profit_factor = float(sum(profits, ZERO) / sum(losses, ZERO)) if losses else (None if not profits else "Infinity")
    calmar = None if not cagr or max_dd == 0 else cagr / float(max_dd)
    return {
        "cagr": cagr,
        "calmar": calmar,
        "final_equity": str(values[-1]),
        "maximum_drawdown": float(max_dd),
        "net_return": float(net),
        "profit_factor": profit_factor,
        "sharpe": sharpe,
        "sortino": sortino,
        "trade_count": len(trades),
        "win_rate": None if not trades else len(profits) / len(trades),
    }


def _monthly_concentration(daily_equity: list[tuple[int, Decimal]], trades: list[dict[str, Any]]) -> dict[str, Any]:
    monthly: dict[str, Decimal] = {}
    for (left_ms, left), (right_ms, right) in zip(daily_equity, daily_equity[1:]):
        month = datetime.fromtimestamp(right_ms / 1000, tz=UTC).strftime("%Y-%m")
        monthly[month] = monthly.get(month, ZERO) + right - left
    positive_months = sorted((value for value in monthly.values() if value > 0), reverse=True)
    total_positive_month = sum(positive_months, ZERO)
    positive_trades = sorted((Decimal(item["net_pnl"]) for item in trades if Decimal(item["net_pnl"]) > 0), reverse=True)
    total_positive_trade = sum(positive_trades, ZERO)
    return {
        "best_three_month_positive_pnl_fraction": (
            None if total_positive_month == 0 else float(sum(positive_months[:3], ZERO) / total_positive_month)
        ),
        "best_trade_positive_pnl_fraction": (
            None if total_positive_trade == 0 else float(positive_trades[0] / total_positive_trade)
        ),
        "monthly_pnl": {key: str(value) for key, value in sorted(monthly.items())},
    }


def run_carry_backtest(
    *,
    spot: dict[int, HourBar],
    future: dict[int, HourBar],
    mark: dict[int, HourBar],
    funding: list[FundingEvent],
    start_ms: int,
    end_ms: int,
    scenario: CarryCostScenario,
    params: CarryParameters,
    starting_equity: Decimal = Decimal("1000"),
    mode: str = "signal",
    include_funding: bool = True,
) -> dict[str, Any]:
    if mode not in {"signal", "always_on"}:
        raise CarryBacktestError("unsupported carry mode")
    if start_ms >= end_ms or start_ms % HOUR_MS or end_ms % HOUR_MS:
        raise CarryBacktestError("partition boundaries must be increasing exact hours")
    ordered_funding = sorted(funding, key=lambda event: event.scheduled_ms)
    if len({event.scheduled_ms for event in ordered_funding}) != len(ordered_funding):
        raise CarryBacktestError("duplicate funding schedule")
    hours = list(range(start_ms, end_ms + HOUR_MS, HOUR_MS))
    equity = starting_equity
    active: dict[str, Any] | None = None
    trades: list[dict[str, Any]] = []
    daily: list[tuple[int, Decimal]] = []
    funding_by_time = {event.scheduled_ms: event for event in ordered_funding}
    pending_action: str | None = None
    exposure_hours = 0
    margin_breaches = 0
    shock_margin_breaches = 0
    unavailable_hours = 0
    skipped_decisions = 0
    notional_mismatch_rejections = 0
    maximum_entry_notional_mismatch_fraction = ZERO
    total_funding = ZERO
    total_spot_raw = ZERO
    total_future_raw = ZERO
    total_fees = ZERO
    total_implicit = ZERO
    turnover = ZERO
    last_available_spot_hour: int | None = None

    def close_position(timestamp: int, reason: str, forced_severe: bool = False) -> None:
        nonlocal active, equity, total_spot_raw, total_future_raw, total_fees, total_implicit, turnover
        assert active is not None
        spot_bar = spot[timestamp]
        future_bar = future[timestamp]
        exit_fee = Decimal("20") if forced_severe else scenario.fee_bps_per_fill
        exit_implicit = Decimal("20") if forced_severe else scenario.implicit_bps_per_fill
        spot_exit_fill = spot_bar.open * (Decimal("1") - exit_implicit / BPS)
        future_exit_fill = future_bar.open * (Decimal("1") + exit_implicit / BPS)
        quantity = active["quantity"]
        spot_raw = quantity * (spot_bar.open - active["spot_entry_raw"])
        future_raw = quantity * (active["future_entry_raw"] - future_bar.open)
        spot_implicit = quantity * ((active["spot_entry_fill"] - active["spot_entry_raw"]) + (spot_bar.open - spot_exit_fill))
        future_implicit = quantity * ((active["future_entry_raw"] - active["future_entry_fill"]) + (future_exit_fill - future_bar.open))
        exit_fees = quantity * spot_exit_fill * exit_fee / BPS + quantity * future_exit_fill * exit_fee / BPS
        fees = active["entry_fees"] + exit_fees
        implicit = spot_implicit + future_implicit
        net = spot_raw + future_raw + active["funding"] - fees - implicit
        equity += net
        total_spot_raw += spot_raw
        total_future_raw += future_raw
        total_fees += fees
        total_implicit += implicit
        turnover += quantity * (active["spot_entry_fill"] + active["future_entry_fill"] + spot_exit_fill + future_exit_fill)
        trades.append({
            "basis_convergence_pnl": str(spot_raw + future_raw),
            "entry_ms": active["entry_ms"],
            "entry_score_bps": str(active["entry_score_bps"]),
            "exit_ms": timestamp,
            "exit_reason": reason,
            "explicit_fees": str(fees),
            "funding_cashflow": str(active["funding"]),
            "future_price_pnl": str(future_raw),
            "holding_hours": (timestamp - active["entry_ms"]) // HOUR_MS,
            "implicit_cost": str(implicit),
            "net_pnl": str(net),
            "quantity_BTC": str(quantity),
            "spot_price_pnl": str(spot_raw),
        })
        active = None

    for timestamp in hours:
        spot_bar = spot.get(timestamp)
        future_bar = future.get(timestamp)
        mark_bar = mark.get(timestamp)
        available = spot_bar is not None and future_bar is not None and mark_bar is not None
        if not available:
            unavailable_hours += 1
            continue
        if active is not None and last_available_spot_hour is not None:
            previous = spot[last_available_spot_hour]
            if timestamp != last_available_spot_hour + HOUR_MS or spot_bar.segment != previous.segment:
                close_position(timestamp, "data_gap_neutralization", forced_severe=True)
                pending_action = None
        last_available_spot_hour = timestamp

        event = funding_by_time.get(timestamp)
        if active is not None and event is not None and event.observed_ms < timestamp + HOUR_MS and timestamp > active["entry_ms"]:
            payment = active["quantity"] * mark_bar.open * event.rate if include_funding else ZERO
            active["funding"] += payment
            total_funding += payment

        weekday = datetime.fromtimestamp(timestamp / 1000, tz=UTC).weekday()
        hour = datetime.fromtimestamp(timestamp / 1000, tz=UTC).hour
        if weekday == 0 and hour == 0:
            decision_ms = timestamp + 5 * 60_000
            score = funding_score_bps(ordered_funding, decision_ms, params.lookback_events)
            if score is None:
                skipped_decisions += 1
                pending_action = None
            elif mode == "always_on":
                pending_action = "enter" if active is None else None
            elif active is None:
                pending_action = "enter" if score > params.entry_threshold_bps else None
            elif score <= params.exit_threshold_bps:
                pending_action = "exit_score"
            elif timestamp + HOUR_MS - active["entry_ms"] >= params.maximum_holding_days * DAY_MS:
                pending_action = "exit_time"
            else:
                pending_action = None
            if pending_action == "enter":
                pending_action = f"enter:{score}"

        if weekday == 0 and hour == 1 and pending_action:
            if pending_action.startswith("exit") and active is not None:
                close_position(timestamp, "score_exit" if pending_action == "exit_score" else "time_exit")
            elif pending_action.startswith("enter") and active is None:
                score = Decimal(pending_action.split(":", 1)[1])
                quantity = _quantity(equity, spot_bar.open, future_bar.open, params)
                mismatch = abs(spot_bar.open - future_bar.open) / max(spot_bar.open, future_bar.open)
                maximum_entry_notional_mismatch_fraction = max(maximum_entry_notional_mismatch_fraction, mismatch)
                if mismatch > Decimal("0.01"):
                    notional_mismatch_rejections += 1
                elif quantity <= 0:
                    skipped_decisions += 1
                else:
                    spot_fill = spot_bar.open * (Decimal("1") + scenario.implicit_bps_per_fill / BPS)
                    future_fill = future_bar.open * (Decimal("1") - scenario.implicit_bps_per_fill / BPS)
                    entry_fees = quantity * (spot_fill + future_fill) * scenario.fee_bps_per_fill / BPS
                    active = {
                        "collateral": equity * (Decimal("1") - params.leg_fraction),
                        "entry_fees": entry_fees,
                        "entry_ms": timestamp,
                        "entry_score_bps": score,
                        "funding": ZERO,
                        "future_entry_fill": future_fill,
                        "future_entry_raw": future_bar.open,
                        "quantity": quantity,
                        "spot_entry_fill": spot_fill,
                        "spot_entry_raw": spot_bar.open,
                    }
            pending_action = None

        if active is not None:
            exposure_hours += 1
            quantity = active["quantity"]
            margin_equity = active["collateral"] + quantity * (active["future_entry_fill"] - mark_bar.close) + active["funding"] - active["entry_fees"] / 2
            maintenance = quantity * mark_bar.close * params.maintenance_margin_fraction
            shocked_mark = mark_bar.close * (Decimal("1") + params.adverse_mark_shock_fraction)
            shocked_equity = active["collateral"] + quantity * (active["future_entry_fill"] - shocked_mark) + active["funding"] - active["entry_fees"] / 2
            shocked_maintenance = quantity * shocked_mark * params.maintenance_margin_fraction
            if margin_equity <= maintenance:
                margin_breaches += 1
                close_position(timestamp, "observed_margin_liquidation", forced_severe=True)
            elif shocked_equity <= shocked_maintenance:
                shock_margin_breaches += 1

        if hour == 23:
            marked = equity
            if active is not None:
                marked += (
                    active["quantity"] * (spot_bar.close - active["spot_entry_fill"])
                    + active["quantity"] * (active["future_entry_fill"] - future_bar.close)
                    + active["funding"]
                    - active["entry_fees"]
                )
            daily.append((timestamp, marked))

    final_hour = max(timestamp for timestamp in hours if timestamp in spot and timestamp in future and timestamp in mark)
    if active is not None:
        close_position(final_hour, "partition_end")
    if not daily or daily[-1][0] != final_hour:
        daily.append((final_hour, equity))
    else:
        daily[-1] = (final_hour, equity)

    metrics = _metrics(daily, trades, starting_equity)
    concentration = _monthly_concentration(daily, trades)
    annual_start: dict[str, Decimal] = {}
    annual_end: dict[str, Decimal] = {}
    for timestamp, value in daily:
        year = str(datetime.fromtimestamp(timestamp / 1000, tz=UTC).year)
        annual_start.setdefault(year, value)
        annual_end[year] = value
    annual_returns = {
        year: float(annual_end[year] / annual_start[year] - Decimal("1")) if annual_start[year] > 0 else None
        for year in sorted(annual_start)
    }
    metrics.update({
        "annual_returns": annual_returns,
        "exposure_days": exposure_hours / 24,
        "return_per_exposed_day": None if exposure_hours == 0 else metrics["net_return"] / (exposure_hours / 24),
        "turnover_quote": str(turnover),
    })
    return {
        "attribution": {
            "basis_convergence_pnl": str(total_spot_raw + total_future_raw),
            "explicit_fees": str(total_fees),
            "funding_cashflow": str(total_funding),
            "future_price_pnl": str(total_future_raw),
            "implicit_cost": str(total_implicit),
            "spot_price_pnl": str(total_spot_raw),
        },
        "concentration": concentration,
        "counts": {
            "margin_breaches": margin_breaches,
            "maximum_entry_notional_mismatch_fraction": float(maximum_entry_notional_mismatch_fraction),
            "notional_mismatch_rejections": notional_mismatch_rejections,
            "shock_margin_breaches": shock_margin_breaches,
            "skipped_decisions": skipped_decisions,
            "unavailable_hours": unavailable_hours,
        },
        "metrics": metrics,
        "mode": mode,
        "scenario_id": scenario.scenario_id,
        "trades": trades,
    }


def funding_information_test(
    events: list[FundingEvent], start_ms: int, end_ms: int, params: CarryParameters, *, seed: int = 20260830, samples: int = 5000
) -> dict[str, Any]:
    observations: list[tuple[str, bool, float]] = []
    timestamp = start_ms
    while timestamp <= end_ms - 28 * DAY_MS:
        dt = datetime.fromtimestamp(timestamp / 1000, tz=UTC)
        if dt.weekday() == 0 and dt.hour == 0:
            decision = timestamp + 5 * 60_000
            score = funding_score_bps(events, decision, params.lookback_events)
            future = [event for event in events if decision < event.observed_ms <= decision + 28 * DAY_MS]
            if score is not None and len(future) == 84:
                future_bps = float(sum((event.rate for event in future), ZERO) * BPS)
                observations.append((dt.strftime("%Y-%m"), score > params.entry_threshold_bps, future_bps))
        timestamp += HOUR_MS
    high = [value for _, flag, value in observations if flag]
    low = [value for _, flag, value in observations if not flag]
    difference = None if not high or not low else statistics.fmean(high) - statistics.fmean(low)
    months = sorted({month for month, _, _ in observations})
    rng = random.Random(seed)
    boot: list[float] = []
    for _ in range(samples):
        chosen = [rng.choice(months) for _ in months]
        sample = [item for month in chosen for item in observations if item[0] == month]
        sample_high = [value for _, flag, value in sample if flag]
        sample_low = [value for _, flag, value in sample if not flag]
        if sample_high and sample_low:
            boot.append(statistics.fmean(sample_high) - statistics.fmean(sample_low))
    boot.sort()
    lower = None if not boot else boot[int(0.025 * (len(boot) - 1))]
    upper = None if not boot else boot[int(0.975 * (len(boot) - 1))]
    return {
        "entry_observations": len(high),
        "entry_minus_nonentry_next_28d_funding_bps": difference,
        "month_block_95pct_interval_bps": [lower, upper],
        "nonentry_observations": len(low),
        "observation_count": len(observations),
        "samples": samples,
        "seed": seed,
    }
