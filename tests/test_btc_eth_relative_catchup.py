from __future__ import annotations

from decimal import Decimal

import pytest

np = pytest.importorskip("numpy", reason="R2 research tests require requirements-research.txt")
pd = pytest.importorskip("pandas", reason="R2 research tests require requirements-research.txt")

from scripts.backtest_btc_eth_relative_catchup import run_backtest, signal_has_complete_path
from trading_platform.execution_model import ExecutionScenario
from trading_platform.research_relative import (
    RelativeSignal,
    complete_four_hour_bars,
    make_relative_signals,
    relative_feature_frame,
)


def candles(periods: int, start: str = "2024-01-01T00:00:00Z") -> pd.DataFrame:
    dates = pd.date_range(start, periods=periods, freq="15min")
    close = 100 * np.exp(np.linspace(0, 0.1, periods))
    return pd.DataFrame(
        {
            "date": dates,
            "open": close,
            "high": close * 1.001,
            "low": close * 0.999,
            "close": close,
            "volume": 1.0,
        }
    )


def scenario(fee: str = "0", implicit: str = "0") -> ExecutionScenario:
    return ExecutionScenario(
        scenario_id=f"test-{fee}-{implicit}",
        mode="candle_taker",
        taker_fee_bps=Decimal(fee),
        maker_fee_bps=Decimal("0"),
        implicit_cost_bps_per_side=Decimal(implicit),
        price_protection_bps=Decimal("1000"),
    )


def one_signal(entry: pd.Timestamp, holding_hours: int = 24) -> RelativeSignal:
    return RelativeSignal(
        variant="primary_relative_catchup",
        bar_start=entry - pd.Timedelta(hours=4),
        decision_time=entry,
        entry_time=entry,
        exit_time=entry + pd.Timedelta(hours=holding_hours),
        btc_return_4h=-0.01,
        eth_return_4h=0.01,
        btc_return_24h=0.01,
        eth_return_24h=0.02,
        alpha=0.0,
        beta=1.0,
        residual=-0.02,
        residual_threshold=-0.01,
    )


def test_complete_four_hour_bars_drop_incomplete_and_reset_after_gap():
    frame = candles(48)
    frame = frame.drop(index=20).reset_index(drop=True)
    bars = complete_four_hour_bars(frame)
    assert list(bars["bar_start"]) == [
        pd.Timestamp("2024-01-01T00:00:00Z"),
        pd.Timestamp("2024-01-01T08:00:00Z"),
    ]
    assert bars["segment"].tolist() == [1, 2]


def test_relative_regression_and_threshold_use_prior_rows_only():
    btc = candles(16 * 80)
    eth = candles(16 * 80).assign(close=lambda x: x["close"] * 1.01)
    original = relative_feature_frame(btc, eth, window=20, quantile=0.1)
    target_bar = original.loc[45, "bar_start"]
    target_rows = btc["date"].dt.floor("4h").eq(target_bar)
    changed_btc = btc.copy()
    changed_btc.loc[target_rows, ["open", "high", "low", "close"]] *= 0.8
    changed = relative_feature_frame(changed_btc, eth, window=20, quantile=0.1)
    for field in ("alpha", "beta", "residual_threshold"):
        assert changed.loc[45, field] == pytest.approx(original.loc[45, field])
    assert changed.loc[45, "residual"] != pytest.approx(original.loc[45, "residual"])


def test_future_price_changes_do_not_change_current_signal():
    rng = np.random.default_rng(42)
    btc = candles(16 * 100)
    eth = candles(16 * 100)
    btc["close"] *= np.exp(np.cumsum(rng.normal(0, 0.002, len(btc))))
    btc["open"] = btc["close"]
    btc["high"] = btc["close"] * 1.001
    btc["low"] = btc["close"] * 0.999
    eth["close"] *= np.exp(np.cumsum(rng.normal(0, 0.002, len(eth))))
    eth["open"] = eth["close"]
    eth["high"] = eth["close"] * 1.001
    eth["low"] = eth["close"] * 0.999
    original = relative_feature_frame(btc, eth, 20, 0.1)
    cutoff = original.loc[60, "bar_start"]
    future = btc["date"].gt(cutoff + pd.Timedelta(hours=4))
    changed_btc = btc.copy()
    changed_btc.loc[future, ["open", "high", "low", "close"]] *= 2
    changed = relative_feature_frame(changed_btc, eth, 20, 0.1)
    columns = ["alpha", "beta", "residual", "residual_threshold"]
    pd.testing.assert_series_equal(original.loc[60, columns], changed.loc[60, columns])


def test_signal_enters_only_after_completed_four_hour_bar():
    features = pd.DataFrame(
        {
            "bar_start": [pd.Timestamp("2025-01-01T00:00:00Z")],
            "btc_return_4h": [-0.02],
            "eth_return_4h": [0.01],
            "btc_return_24h": [0.01],
            "eth_return_24h": [0.02],
            "joint_return_24h": [0.015],
            "alpha": [0.0],
            "beta": [1.0],
            "residual": [-0.03],
            "residual_threshold": [-0.02],
        }
    )
    signals = make_relative_signals(
        features,
        "primary_relative_catchup",
        24,
        pd.Timestamp("2025-01-01T00:00:00Z"),
        pd.Timestamp("2026-01-01T00:00:00Z"),
    )
    assert signals[0].decision_time == pd.Timestamp("2025-01-01T04:00:00Z")
    assert signals[0].entry_time == signals[0].decision_time
    assert signals[0].exit_time == pd.Timestamp("2025-01-02T04:00:00Z")


def test_execution_path_requires_every_fifteen_minute_row():
    frame = candles(120)
    prices = frame.set_index("date", drop=False)
    signal = one_signal(frame.loc[16, "date"])
    assert signal_has_complete_path(signal, prices)
    assert not signal_has_complete_path(signal, prices.drop(signal.entry_time + pd.Timedelta(hours=1)))


def test_shared_capital_runner_caps_exposure_and_costs_reduce_result():
    frame = candles(160)
    signal = one_signal(frame.loc[16, "date"])
    free_result, free_trades = run_backtest(frame, [signal], scenario())
    cost_result, _ = run_backtest(frame, [signal], scenario("10", "5"))
    assert free_result["filled_trades"] == 1
    assert len(free_trades) == 1
    assert free_result["maximum_entry_gross_exposure_fraction"] <= 0.25 + 1e-9
    assert cost_result["net_return"] < free_result["net_return"]
