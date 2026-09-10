from __future__ import annotations

import pytest
from pathlib import Path

pd = pytest.importorskip("pandas", reason="multi-asset backtest tests require requirements-research.txt")

from scripts.backtest_multi_asset_top2 import DEVELOPMENT_END, Signal, cadence_signals, validate_frame


def valid_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.date_range("2025-01-01", periods=3, freq="15min", tz="UTC"),
            "open": [100.0, 101.0, 102.0],
            "high": [101.0, 102.0, 103.0],
            "low": [99.0, 100.0, 101.0],
            "close": [100.5, 101.5, 102.5],
            "volume": [1.0, 2.0, 3.0],
        }
    )


def test_validation_rejects_duplicate_timestamp(tmp_path: Path):
    frame = valid_frame()
    frame.loc[2, "date"] = frame.loc[1, "date"]
    with pytest.raises(ValueError, match="duplicate"):
        validate_frame(frame, "BTC/USDT", tmp_path / "fixture.feather")


def test_validation_excludes_2026_before_feature_work(tmp_path: Path):
    frame = pd.concat(
        [valid_frame(), valid_frame().assign(date=pd.date_range(DEVELOPMENT_END, periods=3, freq="15min"))],
        ignore_index=True,
    )
    checked = validate_frame(frame, "BTC/USDT", tmp_path / "fixture.feather")
    assert checked["date"].max() < DEVELOPMENT_END
    assert not checked["date"].dt.year.eq(2026).any()


def test_daily_control_is_frozen_midnight_utc_signal():
    base = pd.Timestamp("2025-01-01T00:00:00Z")
    signals = [
        Signal(base + pd.Timedelta(hours=hour), base + pd.Timedelta(hours=hour, minutes=15),
               base + pd.Timedelta(hours=hour, minutes=15), ("BTC/USDT", "ETH/USDT"),
               ("BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT"), (1.0, 0.9))
        for hour in (0, 4, 8, 24, 28)
    ]
    assert cadence_signals(signals, "daily") == [signals[0], signals[3]]


def test_signal_entry_is_after_completed_signal_candle():
    signal_time = pd.Timestamp("2025-01-01T04:00:00Z")
    signal = Signal(signal_time, signal_time + pd.Timedelta(minutes=15), signal_time + pd.Timedelta(minutes=15),
                    ("BTC/USDT", "ETH/USDT"), ("BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT"), (1.0, 0.9))
    assert signal.decision_time == signal.signal_time + pd.Timedelta(minutes=15)
    assert signal.entry_time >= signal.decision_time
