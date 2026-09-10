from __future__ import annotations

import ast
from pathlib import Path

from trading_platform.research_breakout import (
    breakout_forecasts,
    exit_execution_rows,
    resolve_exit,
    signal_indices,
)
from trading_platform.research_ledger import AggregateCandle, FIVE_MINUTES_MS, SourceCandle


ROOT = Path(__file__).resolve().parents[1]
FOUR_HOURS_MS = 48 * FIVE_MINUTES_MS


def bar(index: int, *, segment: int = 1, close: float = 100.0, high: float = 101.0, low: float = 99.0) -> AggregateCandle:
    return AggregateCandle(
        segment=segment,
        interval="4h",
        open_ms=index * FOUR_HOURS_MS,
        close_ms=(index + 1) * FOUR_HOURS_MS,
        open=100.0,
        high=high,
        low=low,
        close=close,
        base_volume=1.0,
        quote_volume=100.0,
        start_row=index * 48,
        end_row=(index + 1) * 48 - 1,
    )


def row(index: int, *, segment: int = 1, price: float = 100.0, low: float = 99.0) -> SourceCandle:
    return SourceCandle(
        segment=segment,
        open_ms=index * FIVE_MINUTES_MS,
        open=price,
        high=max(price, 101.0),
        low=low,
        close=price,
        base_volume=1.0,
        quote_volume=100.0,
        source_row=index,
    )


def test_breakout_uses_strict_prior_only_channel_and_counterfactual_forecast():
    bars = [bar(index) for index in range(120)]
    bars.append(bar(120, close=101.0, high=101.0))
    equal = breakout_forecasts(
        bars, lookback=120, evaluation_start_ms=0, evidence_digest="a" * 64
    )
    assert signal_indices(equal) == []
    bars[-1] = bar(120, close=101.0001, high=101.0001)
    triggered = breakout_forecasts(
        bars, lookback=120, evaluation_start_ms=0, evidence_digest="a" * 64
    )
    assert signal_indices(triggered) == [120]
    assert triggered[-1].forecast.arm_id == "btc_breakout_20d_10d"
    assert triggered[-1].forecast.decision_at == triggered[-1].forecast.available_at
    assert triggered[-1].forecast.abstention_reason is None


def test_breakout_history_and_exit_channel_never_cross_segments():
    bars = [bar(index) for index in range(120)]
    bars[-1] = bar(119, segment=2)
    bars.append(bar(120, segment=2, close=110, high=110))
    forecasts = breakout_forecasts(
        bars, lookback=120, evaluation_start_ms=0, evidence_digest="a" * 64
    )
    assert signal_indices(forecasts) == []

    rows = [row(index) for index in range((121 * 48) + 1)]
    assert exit_execution_rows(rows, bars, 60) == {}


def test_stop_has_precedence_and_gap_fill_is_conservative():
    rows = [row(0, price=100, low=100), row(1, price=94, low=90), row(2)]
    exit_row, reference, reason = resolve_exit(
        rows, 0, {1: "exit_channel"}, stop_fraction=0.04, maximum_holding_days=14
    )
    assert exit_row == 1
    assert reference == 94
    assert reason == "protective_stop"


def test_breakout_module_is_offline_and_has_no_execution_or_model_imports():
    path = ROOT / "src/trading_platform/research_breakout.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    assert "trading_platform.execution_model" not in imports
    assert not any(name in imports for name in {"ccxt", "httpx", "nats", "psycopg", "requests"})
