from decimal import Decimal

import pytest

from trading_platform.btc_carry import (
    CarryBacktestError,
    CarryCostScenario,
    CarryParameters,
    FundingEvent,
    HOUR_MS,
    HourBar,
    funding_score_bps,
    run_carry_backtest,
)


def test_funding_rejects_future_or_late_observation():
    with pytest.raises(CarryBacktestError):
        FundingEvent(8 * HOUR_MS, 8 * HOUR_MS + 1000, Decimal("0.0001"))


def test_score_uses_only_observed_complete_events():
    events = [FundingEvent(i * 8 * HOUR_MS, i * 8 * HOUR_MS + 10, Decimal("0.0001")) for i in range(3)]
    assert funding_score_bps(events, 16 * HOUR_MS + 5, 3) is None
    assert funding_score_bps(events, 16 * HOUR_MS + 10, 3) == Decimal("3.0000")


def test_score_fails_on_schedule_gap():
    events = [
        FundingEvent(0, 0, Decimal("0.0001")),
        FundingEvent(8 * HOUR_MS, 8 * HOUR_MS, Decimal("0.0001")),
        FundingEvent(24 * HOUR_MS, 24 * HOUR_MS, Decimal("0.0001")),
    ]
    assert funding_score_bps(events, 24 * HOUR_MS, 3) is None


def test_matched_carry_receives_positive_funding_and_is_deterministic():
    start = 3 * 24 * HOUR_MS
    end = start + 35 * 24 * HOUR_MS
    spot = {}
    future = {}
    mark = {}
    for timestamp in range(0, end + HOUR_MS, HOUR_MS):
        spot[timestamp] = HourBar(timestamp, Decimal("100"), Decimal("100"), "a")
        future[timestamp] = HourBar(timestamp, Decimal("100"), Decimal("100"), "a")
        mark[timestamp] = HourBar(timestamp, Decimal("100"), Decimal("100"), "a")
    funding = [FundingEvent(timestamp, timestamp, Decimal("0.001")) for timestamp in range(0, end + HOUR_MS, 8 * HOUR_MS)]
    params = CarryParameters(lookback_events=3, entry_threshold_bps=Decimal("1"), exit_threshold_bps=Decimal("0"))
    scenario = CarryCostScenario("test", Decimal("0"), Decimal("0"))
    first = run_carry_backtest(
        spot=spot, future=future, mark=mark, funding=funding, start_ms=start, end_ms=end,
        scenario=scenario, params=params,
    )
    second = run_carry_backtest(
        spot=spot, future=future, mark=mark, funding=funding, start_ms=start, end_ms=end,
        scenario=scenario, params=params,
    )
    assert first == second
    assert Decimal(first["attribution"]["funding_cashflow"]) > 0
    assert Decimal(first["attribution"]["basis_convergence_pnl"]) == 0
    assert all(trade["quantity_BTC"] for trade in first["trades"])


def test_costs_reduce_equity():
    start = 3 * 24 * HOUR_MS
    end = start + 14 * 24 * HOUR_MS
    bars = {timestamp: HourBar(timestamp, Decimal("100"), Decimal("100"), "a") for timestamp in range(0, end + HOUR_MS, HOUR_MS)}
    funding = [FundingEvent(timestamp, timestamp, Decimal("0.001")) for timestamp in range(0, end + HOUR_MS, 8 * HOUR_MS)]
    params = CarryParameters(lookback_events=3, entry_threshold_bps=Decimal("1"), exit_threshold_bps=Decimal("0"))
    cheap = run_carry_backtest(
        spot=bars, future=bars, mark=bars, funding=funding, start_ms=start, end_ms=end,
        scenario=CarryCostScenario("cheap", Decimal("0"), Decimal("0")), params=params,
    )
    costly = run_carry_backtest(
        spot=bars, future=bars, mark=bars, funding=funding, start_ms=start, end_ms=end,
        scenario=CarryCostScenario("costly", Decimal("10"), Decimal("5")), params=params,
    )
    assert Decimal(costly["metrics"]["final_equity"]) < Decimal(cheap["metrics"]["final_equity"])


def test_gap_forces_severe_neutralization():
    start = 3 * 24 * HOUR_MS
    end = start + 14 * 24 * HOUR_MS
    spot = {timestamp: HourBar(timestamp, Decimal("100"), Decimal("100"), "a") for timestamp in range(0, end + HOUR_MS, HOUR_MS)}
    gap_hour = start + 8 * 24 * HOUR_MS
    del spot[gap_hour]
    future = {timestamp: HourBar(timestamp, Decimal("100"), Decimal("100"), "a") for timestamp in range(0, end + HOUR_MS, HOUR_MS)}
    mark = dict(future)
    funding = [FundingEvent(timestamp, timestamp, Decimal("0.001")) for timestamp in range(0, end + HOUR_MS, 8 * HOUR_MS)]
    result = run_carry_backtest(
        spot=spot, future=future, mark=mark, funding=funding, start_ms=start, end_ms=end,
        scenario=CarryCostScenario("test", Decimal("0"), Decimal("0")),
        params=CarryParameters(lookback_events=3, entry_threshold_bps=Decimal("1"), exit_threshold_bps=Decimal("0")),
    )
    assert any(trade["exit_reason"] == "data_gap_neutralization" for trade in result["trades"])
    assert Decimal(result["attribution"]["implicit_cost"]) > 0
