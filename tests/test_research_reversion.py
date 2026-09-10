from __future__ import annotations

import math
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from trading_platform.research_persistence import PersistenceCandle
from trading_platform.research_reversion import (
    DisplacementRow,
    ReversionResearchError,
    build_displacement_rows,
    evaluate_matched_events,
    match_completed_controls,
    select_nonoverlapping_events,
)


UTC = timezone.utc
START = datetime(2018, 1, 1, tzinfo=UTC)


def candles(count: int, *, segment: str = "s1", offset: int = 0) -> list[PersistenceCandle]:
    closes = [100.0]
    for index in range(1, count):
        value = 0.001 + 0.004 * math.sin((index + offset) / 9) + 0.002 * math.cos((index + offset) / 17)
        closes.append(closes[-1] * math.exp(value))
    return [
        PersistenceCandle(
            segment=segment,
            open_at=START + timedelta(hours=4 * (index + offset)),
            close_at=START + timedelta(hours=4 * (index + offset + 1)),
            close=value,
        )
        for index, value in enumerate(closes)
    ]


def row(
    day: int,
    *,
    z: float,
    displacement: float,
    reversal: float = 0.01,
    rv: float = 0.001,
    horizon_bars: int = 6,
) -> DisplacementRow:
    observed = START + timedelta(days=day)
    return DisplacementRow(
        segment="s1",
        observed_at=observed,
        target_available_at=observed + timedelta(hours=4 * horizon_bars),
        horizon="1d",
        horizon_bars=horizon_bars,
        displacement=displacement,
        displacement_z=z,
        candidate_score=-z,
        past_realized_variance=rv,
        forward_return=-reversal if displacement > 0 else reversal,
        signed_reversal=reversal,
    )


def test_displacement_formula_uses_current_move_and_preceding_reference_only():
    source = candles(180)
    built = build_displacement_rows(
        source, {"4h": 1}, displacement_bars=6, reference_observations=126
    )["4h"]
    assert built
    first = built[0]
    closes = [item.close for item in source]
    index = 132
    displacements = [math.log(closes[end] / closes[end - 6]) for end in range(6, index + 1)]
    reference = displacements[:-1]
    expected_z = (displacements[-1] - sum(reference) / len(reference)) / statistics.stdev(reference)
    assert first.displacement == pytest.approx(displacements[-1])
    assert first.displacement_z == pytest.approx(expected_z)
    assert first.candidate_score == pytest.approx(-expected_z)
    assert first.target_available_at > first.observed_at


def test_feature_and_target_windows_reset_at_segment_boundaries():
    first = candles(150, segment="a")
    second = candles(150, segment="b", offset=150)
    built = build_displacement_rows(
        [*first, *second], {"1d": 6}, displacement_bars=6, reference_observations=126
    )["1d"]
    assert len(built) == 2 * (150 - 132 - 6)
    assert sum(item.segment == "a" for item in built) == 12
    assert sum(item.segment == "b" for item in built) == 12


def test_event_selection_is_chronological_and_target_nonoverlapping():
    candidates = [
        row(1, z=2.1, displacement=0.1),
        row(1, z=2.5, displacement=0.2),
        row(2, z=-2.2, displacement=-0.1),
        row(4, z=1.0, displacement=0.1),
    ]
    selected = select_nonoverlapping_events(
        candidates,
        threshold=2.0,
        evaluation_start=START,
        evaluation_end=START + timedelta(days=30),
    )
    assert [item.observed_at.day for item in selected] == [2, 3]
    assert selected[1].observed_at >= selected[0].target_available_at


def test_controls_are_past_completed_same_direction_similar_and_never_reused():
    events = [row(10, z=2.5, displacement=0.1), row(20, z=-2.5, displacement=-0.1)]
    controls = [
        row(3, z=0.2, displacement=0.02, reversal=0.002, rv=0.0011),
        row(12, z=-0.1, displacement=-0.02, reversal=-0.001, rv=0.0009),
        row(15, z=0.1, displacement=0.02, rv=0.02),
    ]
    matched = match_completed_controls(
        events,
        [*events, *controls],
        quiet_absolute_z_maximum=0.5,
        maximum_lookback_days=90,
        maximum_variance_ratio=2.0,
    )
    assert matched[0].control == controls[0]
    assert matched[1].control == controls[1]
    assert len({item.control.observed_at for item in matched if item.control}) == 2
    assert all(item.control.target_available_at < item.event.observed_at for item in matched if item.control)


def test_matching_rejects_overlapping_events():
    events = [row(10, z=2.5, displacement=0.1), row(10, z=-2.5, displacement=-0.1)]
    with pytest.raises(ReversionResearchError, match="overlap"):
        match_completed_controls(
            events,
            [],
            quiet_absolute_z_maximum=0.5,
            maximum_lookback_days=90,
            maximum_variance_ratio=2.0,
        )


def test_event_evaluation_uses_exact_seed_and_reports_positive_fixture():
    from trading_platform.research_reversion import MatchedEvent

    matched = []
    for month in range(1, 13):
        event = row(month * 20, z=2.5, displacement=0.1, reversal=0.02)
        control = row(month * 20 - 3, z=0.1, displacement=0.02, reversal=0.001)
        matched.append(MatchedEvent(event, control))
    first = evaluate_matched_events(matched, replications=200, seed=20260831)
    second = evaluate_matched_events(matched, replications=200, seed=20260831)
    assert first == second
    assert first["event_month_block_mean_reversal"]["ci95"][0] > 0
    assert first["matched_event_minus_control_month_block"]["ci95"][0] > 0


def test_module_imports_no_strategy_or_external_clients():
    source = (
        Path(__file__).resolve().parents[1] / "src/trading_platform/research_reversion.py"
    ).read_text(encoding="utf-8").lower()
    for forbidden in (
        "ccxt",
        "freqtrade",
        "httpx",
        "nats",
        "psycopg",
        "requests",
        "signalpayload",
        "orderintent",
    ):
        assert forbidden not in source
