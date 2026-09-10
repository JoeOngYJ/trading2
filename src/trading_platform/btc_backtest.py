"""Deterministic offline BTC long/flat candle backtest core.

Strategy adapters supply causal trade plans. This module owns validation, simulated execution,
cash/inventory accounting, mandate risk state, mark-to-market metrics, and result lineage. It has
no network, database, message-bus, exchange-client, or production-signal integration.
"""

from __future__ import annotations

import math
import statistics
from collections import Counter, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Iterable

from trading_platform.execution_model import (
    ExecutionScenario,
    MarketRules,
    OrderIntent,
    OrderKind,
    OrderStatus,
    PortfolioLedger,
    Side,
    canonical_data,
    sha256_digest,
    simulate_candle_taker,
)
from trading_platform.research_ledger import DAY_MS, FIVE_MINUTES_MS, SourceCandle


UTC = timezone.utc
ZERO = Decimal("0")
ONE = Decimal("1")
BPS = Decimal("10000")


class BtcBacktestError(ValueError):
    """Raised when a backtest input is non-causal, ambiguous, or outside the frozen core."""


@dataclass(frozen=True, slots=True)
class BtcTradePlan:
    plan_id: str
    decision_ms: int
    information_cutoff_ms: int
    decision_price: Decimal
    entry_row: int
    exit_decision_ms: int
    exit_row: int
    exit_reference_price: Decimal
    exit_reason: str
    allocation_fraction: Decimal
    planned_stop_fraction: Decimal

    def __post_init__(self) -> None:
        if not self.plan_id or self.decision_ms < 0 or self.information_cutoff_ms < 0:
            raise BtcBacktestError("plan identity and timestamps are required")
        if self.information_cutoff_ms > self.decision_ms:
            raise BtcBacktestError("information cutoff is after the decision")
        if self.decision_price <= 0 or self.exit_reference_price <= 0:
            raise BtcBacktestError("decision and exit prices must be positive")
        if self.entry_row < 0 or self.exit_row < self.entry_row:
            raise BtcBacktestError("entry/exit rows are reversed")
        if self.exit_decision_ms < self.decision_ms:
            raise BtcBacktestError("exit decision precedes entry decision")
        if not self.exit_reason:
            raise BtcBacktestError("exit reason is required")
        if not ZERO < self.allocation_fraction <= ONE:
            raise BtcBacktestError("allocation must be in (0, 1]")
        if not ZERO <= self.planned_stop_fraction < ONE:
            raise BtcBacktestError("planned stop must be in [0, 1)")


@dataclass(frozen=True, slots=True)
class BtcBacktestConfig:
    run_id: str
    evaluation_start_ms: int
    evaluation_end_ms: int
    starting_equity: Decimal = Decimal("1000")
    maximum_allocation_fraction: Decimal = Decimal("0.25")
    maximum_planned_risk_fraction: Decimal = Decimal("0.005")
    daily_loss_stop_fraction: Decimal = Decimal("0.015")
    strategy_drawdown_stop_fraction: Decimal = Decimal("0.10")
    maximum_entries_per_utc_day: int = 1
    maximum_entries_per_rolling_seven_days: int = 4

    def __post_init__(self) -> None:
        if not self.run_id or self.evaluation_start_ms >= self.evaluation_end_ms:
            raise BtcBacktestError("run ID and increasing evaluation boundary are required")
        if self.starting_equity <= 0:
            raise BtcBacktestError("starting equity must be positive")
        for value in (
            self.maximum_allocation_fraction,
            self.maximum_planned_risk_fraction,
            self.daily_loss_stop_fraction,
            self.strategy_drawdown_stop_fraction,
        ):
            if not ZERO < value < ONE:
                raise BtcBacktestError("risk fractions must be in (0, 1)")
        if self.maximum_entries_per_utc_day <= 0 or self.maximum_entries_per_rolling_seven_days <= 0:
            raise BtcBacktestError("entry-frequency limits must be positive")


def _validate_rows(rows: list[SourceCandle], config: BtcBacktestConfig) -> tuple[int, int]:
    if not rows:
        raise BtcBacktestError("source candles are required")
    previous: SourceCandle | None = None
    for index, row in enumerate(rows):
        if not all(math.isfinite(value) for value in (row.open, row.high, row.low, row.close)):
            raise BtcBacktestError(f"non-finite candle at row {index}")
        if min(row.open, row.high, row.low, row.close) <= 0:
            raise BtcBacktestError(f"non-positive candle at row {index}")
        if row.high < max(row.open, row.close) or row.low > min(row.open, row.close):
            raise BtcBacktestError(f"invalid OHLC ordering at row {index}")
        if previous is not None:
            if row.open_ms <= previous.open_ms:
                raise BtcBacktestError("source timestamps are reversed or duplicated")
            if row.segment == previous.segment and row.open_ms != previous.open_ms + FIVE_MINUTES_MS:
                raise BtcBacktestError("gap inside a source segment")
            if row.segment != previous.segment and row.open_ms == previous.open_ms + FIVE_MINUTES_MS:
                raise BtcBacktestError("unexplained segment change without a time discontinuity")
        previous = row
    selected = [
        index
        for index, row in enumerate(rows)
        if config.evaluation_start_ms <= row.open_ms < config.evaluation_end_ms
    ]
    if not selected:
        raise BtcBacktestError("evaluation boundary contains no source candles")
    return selected[0], selected[-1]


def _validate_plans(
    plans: list[BtcTradePlan], rows: list[SourceCandle], first_row: int, last_row: int
) -> dict[int, list[BtcTradePlan]]:
    identifiers: set[str] = set()
    by_entry: dict[int, list[BtcTradePlan]] = {}
    previous_key: tuple[int, str] | None = None
    for plan in plans:
        if plan.plan_id in identifiers:
            raise BtcBacktestError(f"duplicate plan ID: {plan.plan_id}")
        identifiers.add(plan.plan_id)
        if not first_row <= plan.entry_row <= plan.exit_row <= last_row:
            raise BtcBacktestError(f"plan rows leave the evaluation boundary: {plan.plan_id}")
        entry = rows[plan.entry_row]
        exit_row = rows[plan.exit_row]
        if entry.open_ms != plan.decision_ms:
            raise BtcBacktestError(f"entry is not the first exact observation at decision time: {plan.plan_id}")
        if plan.exit_decision_ms > exit_row.open_ms:
            raise BtcBacktestError(f"exit observation precedes exit decision: {plan.plan_id}")
        if entry.segment != exit_row.segment:
            raise BtcBacktestError(f"plan crosses a source segment: {plan.plan_id}")
        key = (plan.entry_row, plan.plan_id)
        if previous_key is not None and key < previous_key:
            raise BtcBacktestError("plans must be sorted by entry row then plan ID")
        previous_key = key
        by_entry.setdefault(plan.entry_row, []).append(plan)
    return by_entry


def _requested_quantity(
    budget: Decimal, observed_price: Decimal, scenario: ExecutionScenario
) -> Decimal:
    adverse_price = observed_price * (
        ONE + scenario.implicit_cost_bps_per_side / BPS
    )
    fee_factor = ONE + scenario.taker_fee_bps / BPS
    return budget / (adverse_price * fee_factor)


def _daily_statistics(daily_end: dict[str, Decimal]) -> tuple[float | None, float | None]:
    values = list(daily_end.values())
    returns = [float(right / left - ONE) for left, right in zip(values, values[1:]) if left > 0]
    if len(returns) < 2:
        return None, None
    mean = statistics.fmean(returns)
    volatility = statistics.stdev(returns)
    sharpe = mean / volatility * math.sqrt(365) if volatility > 0 else None
    downside = [min(value, 0.0) for value in returns]
    downside_deviation = math.sqrt(statistics.fmean(value * value for value in downside))
    sortino = mean / downside_deviation * math.sqrt(365) if downside_deviation > 0 else None
    return sharpe, sortino


def run_long_flat_backtest(
    rows: Iterable[SourceCandle],
    plans: Iterable[BtcTradePlan],
    *,
    config: BtcBacktestConfig,
    scenario: ExecutionScenario,
    rules: MarketRules,
    input_digest: str,
) -> dict[str, Any]:
    """Run a causal single-position BTC long/flat backtest on immutable candle observations."""
    if scenario.mode != "candle_taker":
        raise BtcBacktestError("BTC candle core requires a candle_taker scenario")
    if len(input_digest) != 64:
        raise BtcBacktestError("a SHA-256 input digest is required")
    source = list(rows)
    ordered_plans = list(plans)
    first_row, last_row = _validate_rows(source, config)
    by_entry = _validate_plans(ordered_plans, source, first_row, last_row)

    ledger = PortfolioLedger(config.starting_equity)
    accepted_decisions: deque[int] = deque()
    daily_decision_counts: Counter[int] = Counter()
    active: dict[str, Any] | None = None
    trades: list[dict[str, Any]] = []
    equity_path: list[dict[str, Any]] = []
    daily_end: dict[str, Decimal] = {}
    annual_end: dict[str, Decimal] = {}
    counts: Counter[str] = Counter()
    exit_reasons: Counter[str] = Counter()
    peak = config.starting_equity
    maximum_drawdown = ZERO
    strategy_disabled = False
    strategy_disable_reason: str | None = None
    daily_loss_stop_days: set[int] = set()
    current_day: int | None = None
    day_start_equity = config.starting_equity
    total_cost = ZERO
    explicit_fees = ZERO
    implicit_cost = ZERO
    turnover = ZERO
    exposure_rows = 0

    for row_index in range(first_row, last_row + 1):
        row = source[row_index]
        row_open = Decimal(str(row.open))
        row_close = Decimal(str(row.close))
        day = row.open_ms // DAY_MS
        opening_equity = ledger.quote_balance + ledger.base_balance * row_open
        if current_day != day:
            current_day = day
            day_start_equity = opening_equity

        if active is not None and row_index == active["plan"].exit_row:
            plan: BtcTradePlan = active["plan"]
            order = OrderIntent(
                client_order_id=f"{config.run_id}:exit:{plan.plan_id}",
                side=Side.SELL,
                quantity=ledger.base_balance,
                decision_time_ns=plan.exit_decision_ms * 1_000_000,
                decision_price=plan.exit_reference_price,
                kind=OrderKind.PROTECTIVE,
                protective=True,
            )
            result = simulate_candle_taker(
                order,
                plan.exit_reference_price,
                row.open_ms * 1_000_000,
                scenario,
                rules,
            )
            if result.status is not OrderStatus.FILLED:
                raise BtcBacktestError(f"protective exit failed: {plan.plan_id}: {result.reason}")
            for fill in result.fills:
                ledger.apply_fill(fill)
                turnover += fill.notional
                explicit_fees += fill.commission.quote_value
                implicit_cost += abs(fill.price - plan.exit_reference_price) * fill.quantity
            total_cost += result.costs.total_quote
            pnl = ledger.quote_balance - active["entry_equity"]
            allocated = active["entry_allocated"]
            trades.append(
                {
                    "allocation_fraction": str(plan.allocation_fraction),
                    "entry_fill_price": str(active["entry_fill_price"]),
                    "entry_ms": source[plan.entry_row].open_ms,
                    "exit_fill_price": str(result.average_fill_price),
                    "exit_ms": row.open_ms,
                    "exit_reason": plan.exit_reason,
                    "holding_ms": row.open_ms - source[plan.entry_row].open_ms,
                    "plan_id": plan.plan_id,
                    "pnl_quote": str(pnl),
                    "return_on_allocated": str(pnl / allocated),
                }
            )
            exit_reasons[plan.exit_reason] += 1
            active = None

        for plan in by_entry.get(row_index, []):
            if active is not None:
                counts["busy"] += 1
                continue
            if strategy_disabled or day in daily_loss_stop_days:
                counts["risk_disabled"] += 1
                continue
            if plan.allocation_fraction > config.maximum_allocation_fraction:
                counts["allocation_rejected"] += 1
                continue
            planned_risk = plan.allocation_fraction * (
                plan.planned_stop_fraction
                + Decimal("2")
                * (scenario.taker_fee_bps + scenario.implicit_cost_bps_per_side)
                / BPS
            )
            if planned_risk > config.maximum_planned_risk_fraction:
                counts["planned_risk_rejected"] += 1
                continue
            while accepted_decisions and accepted_decisions[0] < plan.decision_ms - 7 * DAY_MS:
                accepted_decisions.popleft()
            if (
                daily_decision_counts[plan.decision_ms // DAY_MS]
                >= config.maximum_entries_per_utc_day
                or len(accepted_decisions) >= config.maximum_entries_per_rolling_seven_days
            ):
                counts["frequency_blocked"] += 1
                continue
            accepted_decisions.append(plan.decision_ms)
            daily_decision_counts[plan.decision_ms // DAY_MS] += 1
            budget = ledger.quote_balance * plan.allocation_fraction
            requested = _requested_quantity(budget, row_open, scenario)
            order = OrderIntent(
                client_order_id=f"{config.run_id}:entry:{plan.plan_id}",
                side=Side.BUY,
                quantity=requested,
                decision_time_ns=plan.decision_ms * 1_000_000,
                decision_price=plan.decision_price,
            )
            result = simulate_candle_taker(
                order, row_open, row.open_ms * 1_000_000, scenario, rules
            )
            if result.status is OrderStatus.EXPIRED:
                counts["expired"] += 1
                continue
            if result.status is not OrderStatus.FILLED:
                counts["rejected"] += 1
                continue
            entry_equity = ledger.quote_balance
            entry_allocated = sum(
                (fill.notional + fill.commission.quote_value for fill in result.fills), ZERO
            )
            for fill in result.fills:
                ledger.apply_fill(fill)
                turnover += fill.notional
                explicit_fees += fill.commission.quote_value
                implicit_cost += abs(fill.price - row_open) * fill.quantity
            total_cost += result.costs.total_quote
            active = {
                "entry_allocated": entry_allocated,
                "entry_equity": entry_equity,
                "entry_fill_price": result.average_fill_price,
                "plan": plan,
            }
            counts["filled_entries"] += 1

        equity = ledger.quote_balance + ledger.base_balance * row_close
        if ledger.base_balance:
            exposure_rows += 1
        peak = max(peak, equity)
        drawdown = equity / peak - ONE
        maximum_drawdown = min(maximum_drawdown, drawdown)
        day_loss = equity / day_start_equity - ONE if day_start_equity > 0 else ZERO
        if day_loss <= -config.daily_loss_stop_fraction:
            daily_loss_stop_days.add(day)
        if not strategy_disabled and drawdown <= -config.strategy_drawdown_stop_fraction:
            strategy_disabled = True
            strategy_disable_reason = "strategy_drawdown_stop"
        iso = datetime.fromtimestamp(row.open_ms / 1000, tz=UTC)
        daily_end[iso.strftime("%Y-%m-%d")] = equity
        annual_end[str(iso.year)] = equity
        equity_path.append(
            {
                "drawdown_fraction": str(-drawdown),
                "equity": str(equity),
                "open_ms": row.open_ms,
            }
        )

    if active is not None or ledger.base_balance != 0:
        raise BtcBacktestError("a plan left an open position at the evaluation boundary")

    ending_equity = ledger.quote_balance
    elapsed_days = (config.evaluation_end_ms - config.evaluation_start_ms) / DAY_MS
    elapsed_years = elapsed_days / 365.2425
    net_return = ending_equity / config.starting_equity - ONE
    cagr = (
        float((ending_equity / config.starting_equity) ** Decimal(str(1 / elapsed_years)) - ONE)
        if elapsed_days >= 30
        else None
    )
    gains = sum((Decimal(item["pnl_quote"]) for item in trades if Decimal(item["pnl_quote"]) > 0), ZERO)
    losses = -sum((Decimal(item["pnl_quote"]) for item in trades if Decimal(item["pnl_quote"]) < 0), ZERO)
    sharpe, sortino = _daily_statistics(daily_end)
    annual_returns: dict[str, float] = {}
    prior = config.starting_equity
    for year, value in annual_end.items():
        annual_returns[year] = float(value / prior - ONE)
        prior = value
    maximum_drawdown_fraction = float(-maximum_drawdown)
    metrics = {
        "annual_returns": annual_returns,
        "cagr": cagr,
        "calmar": cagr / maximum_drawdown_fraction if cagr is not None and maximum_drawdown_fraction else None,
        "ending_equity": str(ending_equity),
        "exposure_fraction": exposure_rows / len(equity_path),
        "maximum_drawdown_fraction": maximum_drawdown_fraction,
        "net_return": float(net_return),
        "profit_factor": float(gains / losses) if losses > 0 else None,
        "sharpe": sharpe,
        "sortino": sortino,
        "starting_equity": str(config.starting_equity),
        "trade_count": len(trades),
        "turnover_fraction_of_starting_equity": float(turnover / config.starting_equity),
        "win_rate": sum(Decimal(item["pnl_quote"]) > 0 for item in trades) / len(trades) if trades else None,
    }
    payload = canonical_data(
        {
            "actionable_arm_id": "no_trade",
            "config": config,
            "costs": {
                "explicit_fees_quote": explicit_fees,
                "implicit_cost_quote": implicit_cost,
                "total_execution_cost_quote": total_cost,
            },
            "counts": dict(sorted(counts.items())),
            "daily_loss_stop_days": [
                datetime.fromtimestamp(day * DAY_MS / 1000, tz=UTC).strftime("%Y-%m-%d")
                for day in sorted(daily_loss_stop_days)
            ],
            "equity_path": equity_path,
            "exit_reasons": dict(sorted(exit_reasons.items())),
            "input_digest": input_digest,
            "market_rules_checksum": rules.checksum,
            "metrics": metrics,
            "no_strategy_selection_or_regime_model_run": True,
            "scenario_checksum": scenario.checksum,
            "scenario_id": scenario.scenario_id,
            "schema_version": "btc-long-flat-backtest-result-v1",
            "strategy_disable_reason": strategy_disable_reason,
            "strategy_disabled": strategy_disabled,
            "trades": trades,
        }
    )
    return {**payload, "result_digest": sha256_digest(payload)}
