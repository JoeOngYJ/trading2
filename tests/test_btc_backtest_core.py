from __future__ import annotations

import ast
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from trading_platform.btc_backtest import (
    BtcBacktestConfig,
    BtcBacktestError,
    BtcTradePlan,
    run_long_flat_backtest,
)
from trading_platform.execution_model import MarketRules, load_scenarios
from trading_platform.research_ledger import FIVE_MINUTES_MS, SourceCandle


ROOT = Path(__file__).resolve().parents[1]
D = Decimal


def candle(index: int, price: float = 100.0, *, segment: int = 1, open_ms: int | None = None) -> SourceCandle:
    timestamp = index * FIVE_MINUTES_MS if open_ms is None else open_ms
    return SourceCandle(
        segment=segment,
        open_ms=timestamp,
        open=price,
        high=price * 1.01,
        low=price * 0.99,
        close=price,
        base_volume=1.0,
        quote_volume=price,
        source_row=index,
    )


def plan(
    rows: list[SourceCandle],
    plan_id: str = "p1",
    entry: int = 1,
    exit: int = 3,
    decision_price: str = "100",
    exit_price: str = "105",
    allocation: str = "0.10",
    stop: str = "0.04",
) -> BtcTradePlan:
    return BtcTradePlan(
        plan_id=plan_id,
        decision_ms=rows[entry].open_ms,
        information_cutoff_ms=rows[entry].open_ms,
        decision_price=D(decision_price),
        entry_row=entry,
        exit_decision_ms=rows[exit].open_ms,
        exit_row=exit,
        exit_reference_price=D(exit_price),
        exit_reason="time_exit",
        allocation_fraction=D(allocation),
        planned_stop_fraction=D(stop),
    )


def config(rows: list[SourceCandle], run_id: str = "fixture") -> BtcBacktestConfig:
    return BtcBacktestConfig(
        run_id=run_id,
        evaluation_start_ms=rows[0].open_ms,
        evaluation_end_ms=rows[-1].open_ms + FIVE_MINUTES_MS,
    )


@pytest.fixture
def primary():
    return load_scenarios(ROOT / "config/execution_scenarios.json")["candle-primary-30bps-rt-v1"]


@pytest.fixture
def rules():
    return MarketRules(
        symbol="BTCUSDT",
        effective_at="synthetic-fixture",
        tick_size=D("0.01"),
        step_size=D("0.00001"),
        min_quantity=D("0.00001"),
        min_notional=D("1"),
        source="synthetic_qualification_fixture",
    )


def test_profitable_plan_has_fees_metrics_and_no_actionable_route(primary, rules):
    rows = [candle(index) for index in range(6)]
    result = run_long_flat_backtest(
        rows,
        [plan(rows)],
        config=config(rows),
        scenario=primary,
        rules=rules,
        input_digest="a" * 64,
    )
    assert result["actionable_arm_id"] == "no_trade"
    assert result["metrics"]["trade_count"] == 1
    assert result["metrics"]["net_return"] > 0
    assert D(result["costs"]["explicit_fees_quote"]) > 0
    assert D(result["costs"]["implicit_cost_quote"]) > 0
    assert len(result["result_digest"]) == 64


def test_result_is_deterministic(primary, rules):
    rows = [candle(index) for index in range(6)]
    kwargs = dict(config=config(rows), scenario=primary, rules=rules, input_digest="b" * 64)
    first = run_long_flat_backtest(rows, [plan(rows)], **kwargs)
    second = run_long_flat_backtest(rows, [plan(rows)], **kwargs)
    assert first == second


def test_entry_must_be_exactly_at_decision_observation(primary, rules):
    rows = [candle(index) for index in range(6)]
    invalid = plan(rows)
    invalid = replace(
        invalid,
        decision_ms=invalid.decision_ms - FIVE_MINUTES_MS,
        information_cutoff_ms=invalid.information_cutoff_ms - FIVE_MINUTES_MS,
    )
    with pytest.raises(BtcBacktestError, match="first exact observation"):
        run_long_flat_backtest(
            rows, [invalid], config=config(rows), scenario=primary, rules=rules, input_digest="c" * 64
        )


def test_gap_inside_segment_fails_closed(primary, rules):
    rows = [candle(0), candle(1), candle(2, open_ms=3 * FIVE_MINUTES_MS)]
    with pytest.raises(BtcBacktestError, match="gap inside"):
        run_long_flat_backtest(
            rows, [], config=config(rows), scenario=primary, rules=rules, input_digest="d" * 64
        )


def test_segment_crossing_plan_fails_closed(primary, rules):
    rows = [
        candle(0),
        candle(1),
        candle(2, segment=2, open_ms=3 * FIVE_MINUTES_MS),
        candle(3, segment=2, open_ms=4 * FIVE_MINUTES_MS),
    ]
    crossing = plan(rows, entry=1, exit=2)
    with pytest.raises(BtcBacktestError, match="crosses a source segment"):
        run_long_flat_backtest(
            rows, [crossing], config=config(rows), scenario=primary, rules=rules, input_digest="e" * 64
        )


def test_price_protection_expiry_is_recorded(primary, rules):
    rows = [candle(index, 100) for index in range(6)]
    expensive = plan(rows, decision_price="90")
    result = run_long_flat_backtest(
        rows,
        [expensive],
        config=config(rows),
        scenario=primary,
        rules=rules,
        input_digest="f" * 64,
    )
    assert result["counts"]["expired"] == 1
    assert result["metrics"]["trade_count"] == 0


def test_planned_risk_and_allocation_fail_closed(primary, rules):
    rows = [candle(index) for index in range(8)]
    excessive_risk = plan(rows, plan_id="risk", allocation="0.25", stop="0.04")
    excessive_allocation = plan(
        rows, plan_id="allocation", entry=4, exit=6, allocation="0.30", stop="0.001"
    )
    result = run_long_flat_backtest(
        rows,
        [excessive_risk, excessive_allocation],
        config=config(rows),
        scenario=primary,
        rules=rules,
        input_digest="1" * 64,
    )
    assert result["counts"]["planned_risk_rejected"] == 1
    assert result["counts"]["allocation_rejected"] == 1
    assert result["metrics"]["trade_count"] == 0


def test_daily_loss_stop_blocks_same_day_then_resets_without_blocking_exit(primary, rules):
    prices = [100.0] * 295
    prices[2] = prices[3] = 90.0
    rows = [candle(index, price) for index, price in enumerate(prices)]
    first = plan(rows, plan_id="loss", entry=1, exit=3, exit_price="90", stop="0.001", allocation="0.25")
    second = plan(rows, plan_id="same-day", entry=4, exit=6, exit_price="105")
    third = plan(rows, plan_id="next-day", entry=290, exit=292, exit_price="105")
    result = run_long_flat_backtest(
        rows,
        [first, second, third],
        config=config(rows),
        scenario=primary,
        rules=rules,
        input_digest="2" * 64,
    )
    assert result["daily_loss_stop_days"] == ["1970-01-01"]
    assert result["strategy_disabled"] is False
    assert result["counts"]["risk_disabled"] == 1
    assert result["metrics"]["trade_count"] == 2


def test_same_day_frequency_limit_is_deterministic(primary, rules):
    rows = [candle(index) for index in range(8)]
    first = plan(rows, plan_id="a", entry=1, exit=2, exit_price="101", stop="0.001")
    second = plan(rows, plan_id="b", entry=4, exit=6, exit_price="101", stop="0.001")
    result = run_long_flat_backtest(
        rows,
        [first, second],
        config=config(rows),
        scenario=primary,
        rules=rules,
        input_digest="3" * 64,
    )
    assert result["counts"]["frequency_blocked"] == 1
    assert result["metrics"]["trade_count"] == 1


def test_core_has_no_external_or_production_imports():
    path = ROOT / "src/trading_platform/btc_backtest.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    prohibited = {"ccxt", "freqtrade", "httpx", "nats", "psycopg", "requests"}
    assert not imports.intersection(prohibited)
    assert not any(name.startswith("trading_platform.signal") for name in imports)
