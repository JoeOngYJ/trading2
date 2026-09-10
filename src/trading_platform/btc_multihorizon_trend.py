"""Pure offline research primitives for BTC multi-horizon trend v2."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from typing import Iterable


ZERO = Decimal("0")
BPS = Decimal("10000")
STEP = Decimal("0.00001")


class TrendResearchError(ValueError):
    pass


def ewma_daily_variance(returns: list[float], decay: float = 0.94) -> float:
    if len(returns) < 20 or decay != 0.94 or any(not math.isfinite(x) for x in returns):
        raise TrendResearchError("EWMA requires at least 20 finite daily returns and frozen decay")
    variance = sum(value * value for value in returns[:20]) / 20
    for value in returns[20:]:
        variance = decay * variance + (1 - decay) * value * value
    if not math.isfinite(variance) or variance <= 0:
        raise TrendResearchError("EWMA variance must be positive and finite")
    return variance


def multihorizon_score(daily_closes: list[float], horizons: tuple[int, ...] = (7, 28, 84)) -> float:
    if horizons != (7, 28, 84) or len(daily_closes) < 85:
        raise TrendResearchError("frozen score requires 85 positive daily closes")
    if any(not math.isfinite(value) or value <= 0 for value in daily_closes):
        raise TrendResearchError("daily closes must be positive and finite")
    returns = [math.log(right / left) for left, right in zip(daily_closes, daily_closes[1:])]
    volatility = math.sqrt(ewma_daily_variance(returns))
    current = daily_closes[-1]
    components = []
    for horizon in horizons:
        raw = math.log(current / daily_closes[-1 - horizon]) / (math.sqrt(horizon) * volatility)
        components.append(max(-2.0, min(2.0, raw)))
    return sum(components) / 3


def target_direction(score: float) -> int:
    if not math.isfinite(score):
        raise TrendResearchError("score must be finite")
    if score > 0.25:
        return 1
    if score < -0.25:
        return -1
    return 0


def risk_fraction(daily_volatility: float) -> float:
    if not math.isfinite(daily_volatility) or daily_volatility <= 0:
        raise TrendResearchError("daily volatility must be positive and finite")
    return min(0.25, 0.40 / (math.sqrt(365) * daily_volatility))


def funding_cashflow(direction: int, quantity: Decimal, mark: Decimal, rate: Decimal) -> Decimal:
    if direction not in {-1, 0, 1} or quantity < 0 or mark <= 0:
        raise TrendResearchError("invalid funding inputs")
    return -Decimal(direction) * quantity * mark * rate


def shocked_margin_ratio(
    direction: int,
    quantity: Decimal,
    entry_mark: Decimal,
    current_mark: Decimal,
    collateral: Decimal,
) -> Decimal:
    if direction not in {-1, 1} or min(quantity, entry_mark, current_mark, collateral) <= 0:
        raise TrendResearchError("invalid margin state")
    shock = current_mark * (Decimal("0.5") if direction == 1 else Decimal("1.5"))
    equity = collateral + Decimal(direction) * quantity * (shock - entry_mark)
    maintenance = quantity * shock * Decimal("0.1")
    return equity / maintenance


def seeded_control_directions(count: int, seed: int = 20260905) -> list[int]:
    if count < 0 or seed != 20260905:
        raise TrendResearchError("invalid frozen random control request")
    generator = random.Random(seed)
    result = []
    for _ in range(count):
        value = generator.random()
        result.append(1 if value < 0.45 else (0 if value < 0.55 else -1))
    return result


@dataclass(frozen=True)
class SyntheticHour:
    timestamp: int
    open: Decimal
    close: Decimal
    mark: Decimal
    funding_rate: Decimal | None = None


def simulate_synthetic(
    bars: Iterable[SyntheticHour],
    execution_targets: dict[int, int],
    *,
    fee_bps: Decimal = Decimal("10"),
    implicit_bps: Decimal = Decimal("5"),
    severe_bps: Decimal = Decimal("20"),
    starting_equity: Decimal = Decimal("1000"),
) -> dict[str, object]:
    """Exercise accounting and safety semantics on explicitly synthetic bars only."""
    ordered = list(bars)
    if not ordered or any(bar.open <= 0 or bar.close <= 0 or bar.mark <= 0 for bar in ordered):
        raise TrendResearchError("invalid synthetic bars")
    if any(right.timestamp <= left.timestamp for left, right in zip(ordered, ordered[1:])):
        raise TrendResearchError("timestamps must be unique and increasing")
    hour = 3_600_000
    equity = starting_equity
    signed_quantity = ZERO
    entry_mark = ZERO
    collateral = ZERO
    previous_close = ordered[0].open
    pending_risk_exit = False
    costs = ZERO
    funding_total = ZERO
    price_pnl = ZERO
    fills: list[dict[str, object]] = []

    def trade(bar: SyntheticHour, target_direction_value: int, reason: str, severe: bool = False) -> None:
        nonlocal signed_quantity, entry_mark, collateral, equity, costs
        if target_direction_value not in {-1, 0, 1}:
            raise TrendResearchError("invalid target direction")
        fraction = Decimal("0.25")
        target_abs = (equity * fraction / bar.open).quantize(STEP, rounding=ROUND_DOWN)
        target = Decimal(target_direction_value) * target_abs
        delta = target - signed_quantity
        rate = severe_bps if severe else fee_bps + implicit_bps
        transaction_cost = abs(delta) * bar.open * rate / BPS
        equity -= transaction_cost
        costs += transaction_cost
        if delta:
            fills.append({"timestamp": bar.timestamp, "quantity_delta": str(delta), "reason": reason, "cost": str(transaction_cost)})
        signed_quantity = target
        if target:
            entry_mark = bar.mark
            collateral = equity * Decimal("0.75")
        else:
            entry_mark = collateral = ZERO

    last_timestamp: int | None = None
    for bar in ordered:
        gap = last_timestamp is not None and bar.timestamp != last_timestamp + hour
        if gap and signed_quantity:
            trade(bar, 0, "data_gap_neutralization", severe=True)
        if pending_risk_exit and signed_quantity:
            trade(bar, 0, "margin_buffer_risk_exit", severe=True)
            pending_risk_exit = False
        if bar.timestamp in execution_targets:
            trade(bar, execution_targets[bar.timestamp], "scheduled_rebalance")
        hourly_pnl = signed_quantity * (bar.close - previous_close)
        equity += hourly_pnl
        price_pnl += hourly_pnl
        if bar.funding_rate is not None and signed_quantity:
            cashflow = funding_cashflow(1 if signed_quantity > 0 else -1, abs(signed_quantity), bar.mark, bar.funding_rate)
            equity += cashflow
            funding_total += cashflow
        if signed_quantity:
            ratio = shocked_margin_ratio(1 if signed_quantity > 0 else -1, abs(signed_quantity), entry_mark, bar.mark, collateral)
            pending_risk_exit = ratio < Decimal("2")
        previous_close = bar.close
        last_timestamp = bar.timestamp
    return {
        "actionable_arm_id": "no_trade",
        "costs": str(costs),
        "ending_equity": str(equity),
        "fills": fills,
        "funding_cashflow": str(funding_total),
        "price_pnl": str(price_pnl),
        "synthetic_only": True,
    }
