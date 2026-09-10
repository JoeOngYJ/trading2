import importlib.util
import sys
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "backtest_btc_sell_flow_absorption.py"
SPEC = importlib.util.spec_from_file_location("backtest_btc_sell_flow_absorption", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def make_bar(index: int, *, segment: int = 0, price: float = 100.0, low: float | None = None):
    return MODULE.FiveMinuteBar(
        segment=segment,
        time_ms=index * MODULE.FIVE_MINUTES_MS,
        open=price,
        high=price + 1,
        low=price - 1 if low is None else low,
        close=price,
        base_volume=10,
        quote_volume=1000,
        taker_buy_base=4,
    )


def test_quantile_is_deterministic():
    assert MODULE.quantile([0.0, 10.0], 0.9) == 9.0
    assert MODULE.quantile([4.0, 1.0, 3.0, 2.0], 0.5) == 2.5


def test_hour_aggregation_requires_exact_contiguous_twelve_bars():
    bars = [make_bar(index) for index in range(12)]
    hours = MODULE.aggregate_complete_hours(bars)
    assert len(hours) == 1
    assert hours[0].time_ms == 0
    assert hours[0].flow_imbalance == -0.2

    gapped = bars[:6] + [make_bar(index) for index in range(7, 12)]
    assert MODULE.aggregate_complete_hours(gapped) == []


def test_feature_snapshot_excludes_current_hour_and_resets_on_gap():
    hours = []
    for index in range(25):
        hours.append(MODULE.HourBar(
            segment=0,
            time_ms=index * MODULE.HOUR_MS,
            open=100,
            high=101,
            low=99,
            close=100,
            quote_volume=1000 + index,
            flow_imbalance=-0.2 + index * 0.01,
            log_return=index * 0.0001,
            start_five_minute_index=index * 12,
            end_five_minute_index=index * 12 + 11,
        ))
    snapshots = MODULE.compute_feature_snapshots(hours, 24)
    assert all(item is None for item in snapshots[:24])
    assert snapshots[24] is not None

    changed = list(hours)
    changed[24] = MODULE.HourBar(**{
        field: getattr(changed[24], field) for field in changed[24].__dataclass_fields__
    } | {"flow_imbalance": -0.99, "log_return": 0.5})
    assert MODULE.compute_feature_snapshots(changed, 24)[24] == snapshots[24]

    changed[24] = MODULE.HourBar(**{
        field: getattr(changed[24], field) for field in changed[24].__dataclass_fields__
    } | {"segment": 1})
    assert MODULE.compute_feature_snapshots(changed, 24)[24] is None


def test_trade_enters_next_bar_and_resolves_gap_below_stop_conservatively():
    bars = [make_bar(index) for index in range(30)]
    bars[12] = make_bar(12, price=100)
    bars[13] = make_bar(13, price=98)
    hour = MODULE.HourBar(
        segment=0,
        time_ms=0,
        open=100,
        high=101,
        low=99,
        close=100,
        quote_volume=1000,
        flow_imbalance=-0.5,
        log_return=0,
        start_five_minute_index=0,
        end_five_minute_index=11,
    )
    parameters = MODULE.ModelParameters(holding_period_hours=1, stop_fraction=0.015)
    scenario = MODULE.ExecutionScenario("test", side_cost_fraction=0.0015, price_protection_fraction=0.001)
    trade = MODULE.independent_trade(0, [hour], bars, parameters, scenario)
    assert trade is not None
    assert trade["entry_index"] == 12
    assert trade["exit_index"] == 13
    assert trade["exit_reason"] == "stop_gap"
    assert trade["exit_price"] == 98


def test_price_protection_expires_gap_up():
    bars = [make_bar(index) for index in range(30)]
    bars[12] = make_bar(12, price=101)
    hour = MODULE.HourBar(
        segment=0,
        time_ms=0,
        open=100,
        high=101,
        low=99,
        close=100,
        quote_volume=1000,
        flow_imbalance=-0.5,
        log_return=0,
        start_five_minute_index=0,
        end_five_minute_index=11,
    )
    outcome = MODULE.independent_trade(
        0,
        [hour],
        bars,
        MODULE.ModelParameters(holding_period_hours=1),
        MODULE.ExecutionScenario("test", side_cost_fraction=0.0015, price_protection_fraction=0.001),
    )
    assert outcome is not None
    assert outcome["status"] == "expired_price_protection"
