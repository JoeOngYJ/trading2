from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

from trading_platform.research_breakout_mechanism import (
    FIVE_MINUTES_MS,
    ResearchBreakoutMechanismError,
    build_directional_efficiency,
    fixed_seven_day_return,
    linear_quantile,
    matched_random_control,
    month_block_efficiency_difference,
    parse_utc_ms,
)


def bar(index: int, close: float, segment: str = "0") -> dict:
    decision_ms = 1_700_000_000_000 + index * 14_400_000
    return {
        "close": close,
        "close_at": __import__("datetime").datetime.fromtimestamp(
            decision_ms / 1000, tz=__import__("datetime").timezone.utc
        ).isoformat().replace("+00:00", "Z"),
        "segment": segment,
    }


def candle(index: int, *, segment: str = "0", base_ms: int = 0, price: float = 100.0):
    return SimpleNamespace(
        close=price,
        high=price,
        low=price,
        open=price,
        open_ms=base_ms + index * FIVE_MINUTES_MS,
        segment=segment,
        source_row=index,
    )


def test_parse_utc_and_linear_quantile_fail_closed():
    assert parse_utc_ms("1970-01-01T00:00:01Z") == 1000
    assert linear_quantile([0.0, 10.0], 0.25) == 2.5
    with pytest.raises(ResearchBreakoutMechanismError):
        parse_utc_ms("2026-01-01T00:00:00")
    with pytest.raises(ResearchBreakoutMechanismError):
        linear_quantile([], 0.5)


def test_efficiency_uses_current_and_past_only():
    bars = [bar(index, 100.0 * math.exp(index * 0.001)) for index in range(10)]
    first = build_directional_efficiency(bars, lookback=2, cutoff_history=3)
    changed = [*bars, bar(10, 1.0)]
    second = build_directional_efficiency(changed, lookback=2, cutoff_history=3)
    assert first == second[: len(first)]
    assert first[0]["value"] == pytest.approx(1.0)
    assert first[2]["classification"] == "unknown"
    assert first[3]["classification"] == "high"


def test_efficiency_resets_on_segment_crossing():
    bars = [bar(index, 100 + index, "0" if index < 5 else "1") for index in range(9)]
    rows = build_directional_efficiency(bars, lookback=2, cutoff_history=2)
    by_index = {row["bar_index"]: row for row in rows}
    assert 5 not in by_index and 6 not in by_index
    assert by_index[7]["classification"] == "unknown"


def test_fixed_seven_day_return_requires_exact_endpoint_and_segment():
    size = 2017
    rows = [candle(index, price=100.0) for index in range(size)]
    rows[-1] = candle(size - 1, price=110.0)
    assert fixed_seven_day_return(rows, 0, "0") == pytest.approx(math.log(1.1))
    rows[-1] = candle(size - 1, segment="1", price=110.0)
    assert fixed_seven_day_return(rows, 0, "0") is None


def test_matched_random_control_is_seeded_and_year_matched():
    candidates = [
        {"fixed_7d_log_return": value, "year": year}
        for year in (2020, 2021)
        for value in (0.0, 0.1, 0.2)
    ]
    observed = [
        {"entry_year": 2020, "fixed_7d_log_return": 0.2},
        {"entry_year": 2021, "fixed_7d_log_return": 0.2},
    ]
    first = matched_random_control(candidates, observed, seed=7, replications=100)
    second = matched_random_control(candidates, observed, seed=7, replications=100)
    assert first == second
    assert first["sample_counts_by_year"] == {"2020": 1, "2021": 1}
    assert first["empirical_percentile"] > 0.5


def test_month_block_bootstrap_preserves_blocks_and_direction():
    trades = [
        {"efficiency_class": group, "entry_month": month, "return_on_allocated": value}
        for month in ("2020-01", "2020-02", "2020-03")
        for group, value in (("high", 0.03), ("low", -0.01))
    ]
    result = month_block_efficiency_difference(trades, seed=5, replications=100)
    assert result["difference"] == pytest.approx(0.04)
    assert result["ci95"][0] == pytest.approx(0.04)
    assert result["valid_replications"] == 100
