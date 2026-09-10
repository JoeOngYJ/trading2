from __future__ import annotations

import ast
import json
from decimal import Decimal
from pathlib import Path

import pytest

from trading_platform.btc_carry import (
    CarryBacktestError,
    CarryCostScenario,
    CarryParameters,
    FundingEvent,
    HOUR_MS,
    HourBar,
    utc_ms,
)
from trading_platform.btc_carry_risk_v2 import run_safe_carry_backtest


ROOT = Path(__file__).resolve().parents[1]


def _fixture(mark_close_at_entry: Decimal = Decimal("100")):
    start = utc_ms("2024-01-01T00:00:00Z")
    end = start + 14 * 24 * HOUR_MS
    spot = {}
    future = {}
    mark = {}
    for timestamp in range(start - 32 * HOUR_MS, end + HOUR_MS, HOUR_MS):
        spot[timestamp] = HourBar(timestamp, Decimal("100"), Decimal("100"), "a")
        future[timestamp] = HourBar(timestamp, Decimal("100"), Decimal("100"), "a")
        close = mark_close_at_entry if timestamp == start + HOUR_MS else Decimal("100")
        mark[timestamp] = HourBar(timestamp, Decimal("100"), close, "a")
    funding = [
        FundingEvent(timestamp, timestamp, Decimal("0.001"))
        for timestamp in range(start - 32 * HOUR_MS, end + HOUR_MS, 8 * HOUR_MS)
    ]
    return start, end, spot, future, mark, funding


def _params(leg_fraction: Decimal = Decimal("0.25")) -> CarryParameters:
    return CarryParameters(
        lookback_events=3,
        entry_threshold_bps=Decimal("1"),
        exit_threshold_bps=Decimal("0"),
        leg_fraction=leg_fraction,
    )


def test_safe_v2_requires_frozen_exposure_and_margin_ratio():
    start, end, spot, future, mark, funding = _fixture()
    scenario = CarryCostScenario("test", Decimal("0"), Decimal("0"))
    with pytest.raises(CarryBacktestError, match="25%"):
        run_safe_carry_backtest(
            spot=spot,
            future=future,
            mark=mark,
            funding=funding,
            start_ms=start,
            end_ms=end,
            scenario=scenario,
            params=_params(Decimal("0.24")),
        )
    with pytest.raises(CarryBacktestError, match="2.0"):
        run_safe_carry_backtest(
            spot=spot,
            future=future,
            mark=mark,
            funding=funding,
            start_ms=start,
            end_ms=end,
            scenario=scenario,
            params=_params(),
            minimum_shocked_margin_ratio=Decimal("1.99"),
        )


def test_completed_hour_buffer_signal_exits_at_next_hour_without_releveraging():
    start, end, spot, future, mark, funding = _fixture(Decimal("290"))
    result = run_safe_carry_backtest(
        spot=spot,
        future=future,
        mark=mark,
        funding=funding,
        start_ms=start,
        end_ms=end,
        scenario=CarryCostScenario("test", Decimal("0"), Decimal("0")),
        params=_params(),
    )
    first = result["trades"][0]
    assert first["entry_ms"] == start + HOUR_MS
    assert first["risk_signal_ms"] == start + 2 * HOUR_MS
    assert first["exit_ms"] == start + 2 * HOUR_MS
    assert first["exit_reason"] == "margin_buffer_risk_exit"
    assert result["counts"]["risk_exit_signals"] == 1
    assert result["counts"]["risk_exits"] == 1
    assert result["counts"]["margin_breaches"] == 0
    assert result["counts"]["shock_margin_breaches"] == 0
    assert result["metrics"]["trade_count"] == 2


def test_stable_safe_pair_is_deterministic_and_receives_funding():
    start, end, spot, future, mark, funding = _fixture()
    kwargs = dict(
        spot=spot,
        future=future,
        mark=mark,
        funding=funding,
        start_ms=start,
        end_ms=end,
        scenario=CarryCostScenario("test", Decimal("0"), Decimal("0")),
        params=_params(),
    )
    first = run_safe_carry_backtest(**kwargs)
    second = run_safe_carry_backtest(**kwargs)
    assert first == second
    assert Decimal(first["attribution"]["funding_cashflow"]) > 0
    assert first["counts"]["risk_exits"] == 0
    assert first["counts"]["entry_shocked_ratio_rejections"] == 0
    assert first["margin_diagnostics"][
        "minimum_shocked_margin_equity_to_maintenance_ratio"
    ] >= 2.0


def test_v2_module_imports_no_network_or_production_clients():
    forbidden = {"ccxt", "freqtrade", "httpx", "nats", "psycopg", "requests", "sqlalchemy"}
    imported: set[str] = set()
    for relative in (
        "src/trading_platform/btc_carry_risk_v2.py",
        "scripts/backtest_btc_safe_funding_carry_risk_v2.py",
    ):
        tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
    assert not (imported & forbidden)


def test_contract_freezes_only_risk_implementation_and_fails_closed():
    contract = json.loads(
        (
            ROOT
            / "research/btc/contracts/btc-safe-delta-neutral-funding-carry-v2.json"
        ).read_text(encoding="utf-8")
    )
    assert contract["status"] == "frozen_before_any_v2_return_calculation"
    assert contract["parameters"] == {
        "decision_time_utc": "Monday_00:05",
        "entry_exit_time_utc": "next_01:00",
        "entry_threshold_cumulative_funding_bps": 60,
        "exit_threshold_cumulative_funding_bps": 30,
        "lookback_funding_events": 84,
        "maximum_holding_days": 84,
        "maximum_notional_fraction_per_leg": 0.25,
        "quantity_step_BTC": "0.00001",
        "weekly_decision_interval_days": 7,
    }
    assert contract["risk_model"][
        "minimum_shocked_margin_equity_to_maintenance_ratio"
    ] == 2.0
    assert contract["action_boundary"]["actionable_arm_id"] == "no_trade"
    assert not any(
        value
        for key, value in contract["action_boundary"].items()
        if key != "actionable_arm_id"
    )
