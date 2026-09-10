from __future__ import annotations

import math
from datetime import datetime, timezone
from pathlib import Path

import pytest

from trading_platform.research_condition_scores import realized_variation_components
from trading_platform.research_jump import (
    JumpForecast,
    JumpObservation,
    JumpResearchError,
    average_precision,
    brier_loss,
    build_four_hour_jump_observations,
    build_jump_forecasts,
    calibration_bins,
    log_loss,
    month_block_bootstrap,
    score_jump_forecasts,
)
from trading_platform.research_ledger import FIVE_MINUTES_MS
from trading_platform.research_volatility import CandlePoint


DIGEST = "a" * 64
FOUR_HOURS_MS = 48 * FIVE_MINUTES_MS


def _block_candles(
    returns: list[float],
    *,
    block_start_ms: int = FOUR_HOURS_MS,
    segment: str = "s1",
) -> list[CandlePoint]:
    """Build one complete four-hour block plus its contiguous prior close."""

    assert len(returns) == 48
    close = 100.0
    candles = [
        CandlePoint(
            segment=segment,
            open_ms=block_start_ms - FIVE_MINUTES_MS,
            open=close,
            high=close,
            low=close,
            close=close,
            source_row=0,
        )
    ]
    for index, log_return in enumerate(returns, start=1):
        prior = close
        close = prior * math.exp(log_return)
        candles.append(
            CandlePoint(
                segment=segment,
                open_ms=block_start_ms + (index - 1) * FIVE_MINUTES_MS,
                open=prior,
                high=max(prior, close),
                low=min(prior, close),
                close=close,
                source_row=index,
            )
        )
    return candles


def _jump_observations(
    count: int,
    *,
    segment: str = "s1",
    start_block: int = 1,
    event_every: int = 10,
) -> list[JumpObservation]:
    output = []
    for index in range(count):
        event = int(index % event_every == 0)
        share = 0.8 if event else 0.1 + 0.01 * (index % 5)
        rv = 0.001 + 0.00001 * (index % 7)
        output.append(
            JumpObservation(
                observed_ms=(start_block + index) * FOUR_HOURS_MS,
                segment=segment,
                realized_variance=rv,
                bipower_variation=rv * (1 - share),
                nonnegative_jump_variation=rv * share,
                jump_share=share,
                event_indicator=event,
                source_digest=DIGEST,
            )
        )
    return output


def _forecast(
    index: int,
    *,
    target_event: int,
    candidate_probability: float,
    control_probability: float = 0.5,
    target_intensity: float | None = None,
    candidate_intensity: float | None = None,
    control_intensity: float = 0.5,
    decision_ms: int | None = None,
) -> JumpForecast:
    target = float(target_event) if target_intensity is None else target_intensity
    candidate = target if candidate_intensity is None else candidate_intensity
    decision = (
        (365 * 6 + index) * FOUR_HOURS_MS if decision_ms is None else decision_ms
    )
    return JumpForecast(
        decision_ms=decision,
        target_end_ms=decision + FOUR_HOURS_MS,
        horizon_blocks=1,
        segment="s1",
        control_probability=control_probability,
        candidate_probability=candidate_probability,
        control_intensity=control_intensity,
        candidate_intensity=candidate,
        target_event=target_event,
        target_intensity=target,
        source_digest=DIGEST,
    )


def test_complete_block_matches_frozen_mcs2_bipower_formula():
    returns = [0.001] * 48
    returns[23] = 0.2
    expected = realized_variation_components(returns)
    candles = _block_candles(returns)

    rows, audit = build_four_hour_jump_observations(
        candles,
        start_ms=FOUR_HOURS_MS,
        end_ms=2 * FOUR_HOURS_MS,
        source_digest=DIGEST,
    )

    assert len(rows) == 1
    row = rows[0]
    assert row.observed_ms == 2 * FOUR_HOURS_MS
    assert row.realized_variance == pytest.approx(expected.realized_variance)
    assert row.bipower_variation == pytest.approx(expected.bipower_variation)
    assert row.nonnegative_jump_variation == pytest.approx(
        expected.nonnegative_jump_variation
    )
    assert row.jump_share == pytest.approx(expected.jump_share)
    assert row.event_indicator == int(expected.jump_share >= 0.5)
    assert audit["expected_blocks"] == 1
    assert audit["valid_blocks"] == 1


def test_jump_measure_is_unsigned_and_zero_realized_variance_is_valid():
    positive = [0.001] * 48
    negative = list(positive)
    positive[23] = 0.2
    negative[23] = -0.2
    positive_rows, _ = build_four_hour_jump_observations(
        _block_candles(positive),
        start_ms=FOUR_HOURS_MS,
        end_ms=2 * FOUR_HOURS_MS,
        source_digest=DIGEST,
    )
    negative_rows, _ = build_four_hour_jump_observations(
        _block_candles(negative),
        start_ms=FOUR_HOURS_MS,
        end_ms=2 * FOUR_HOURS_MS,
        source_digest=DIGEST,
    )
    assert positive_rows[0].realized_variance == pytest.approx(
        negative_rows[0].realized_variance
    )
    assert positive_rows[0].bipower_variation == pytest.approx(
        negative_rows[0].bipower_variation
    )
    assert positive_rows[0].jump_share == pytest.approx(negative_rows[0].jump_share)
    assert positive_rows[0].event_indicator == negative_rows[0].event_indicator

    zero_rows, audit = build_four_hour_jump_observations(
        _block_candles([0.0] * 48),
        start_ms=FOUR_HOURS_MS,
        end_ms=2 * FOUR_HOURS_MS,
        source_digest=DIGEST,
    )
    assert audit["valid_blocks"] == 1
    assert zero_rows[0].realized_variance == 0.0
    assert zero_rows[0].nonnegative_jump_variation == 0.0
    assert zero_rows[0].jump_share == 0.0
    assert zero_rows[0].event_indicator == 0


def test_block_builder_rejects_gaps_segment_crossings_and_bad_boundaries():
    candles = _block_candles([0.001] * 48)
    missing = candles[:20] + candles[21:]
    rows, audit = build_four_hour_jump_observations(
        missing,
        start_ms=FOUR_HOURS_MS,
        end_ms=2 * FOUR_HOURS_MS,
        source_digest=DIGEST,
    )
    assert rows == []
    assert audit["excluded"]["incomplete_or_cross_segment_block"] == 1

    crossed = list(candles)
    item = crossed[20]
    crossed[20] = CandlePoint(
        segment="s2",
        open_ms=item.open_ms,
        open=item.open,
        high=item.high,
        low=item.low,
        close=item.close,
        source_row=item.source_row,
    )
    rows, audit = build_four_hour_jump_observations(
        crossed,
        start_ms=FOUR_HOURS_MS,
        end_ms=2 * FOUR_HOURS_MS,
        source_digest=DIGEST,
    )
    assert rows == []
    assert audit["excluded"]["incomplete_or_cross_segment_block"] == 1

    with pytest.raises(JumpResearchError, match="boundary"):
        build_four_hour_jump_observations(
            candles,
            start_ms=FOUR_HOURS_MS + FIVE_MINUTES_MS,
            end_ms=2 * FOUR_HOURS_MS,
            source_digest=DIGEST,
        )


def test_four_hour_and_one_day_targets_are_strictly_future_and_causal():
    observations = _jump_observations(190)
    four_hour = build_jump_forecasts(observations, horizon_blocks=1)
    assert four_hour
    first = four_hour[0]
    history = observations[:180]
    assert first.decision_ms == observations[179].observed_ms
    assert first.target_end_ms == observations[180].observed_ms
    assert first.target_event == observations[180].event_indicator
    assert first.target_intensity == observations[180].jump_share
    assert first.control_probability == pytest.approx(
        (sum(item.event_indicator for item in history) + 0.5) / 181
    )
    assert first.control_intensity == pytest.approx(
        sum(item.jump_share for item in history) / 180
    )
    assert first.candidate_probability == pytest.approx(first.control_probability)
    assert first.candidate_intensity == pytest.approx(first.control_intensity)

    one_day = build_jump_forecasts(observations, horizon_blocks=6)
    assert one_day
    future = observations[180:186]
    assert one_day[0].target_end_ms == observations[185].observed_ms
    assert one_day[0].target_event == int(any(item.event_indicator for item in future))
    assert one_day[0].target_intensity == pytest.approx(
        sum(item.jump_share for item in future) / 6
    )
    assert one_day[0].candidate_probability == pytest.approx(
        1 - (1 - first.candidate_probability) ** 6
    )


def test_ewma_updates_through_current_block_and_resets_after_segment_or_gap():
    observations = _jump_observations(182)
    rows = build_jump_forecasts(observations, horizon_blocks=1)
    assert len(rows) == 2
    initialized_probability = rows[0].candidate_probability
    initialized_intensity = rows[0].candidate_intensity
    assert rows[1].candidate_probability == pytest.approx(
        0.94 * initialized_probability + 0.06 * observations[180].event_indicator
    )
    assert rows[1].candidate_intensity == pytest.approx(
        0.94 * initialized_intensity + 0.06 * observations[180].jump_share
    )

    first_segment = _jump_observations(181, segment="a", start_block=1)
    second_segment = _jump_observations(181, segment="b", start_block=200)
    reset = build_jump_forecasts([*first_segment, *second_segment], horizon_blocks=1)
    assert len(reset) == 2
    assert [item.segment for item in reset] == ["a", "b"]
    assert all(item.candidate_probability == pytest.approx(item.control_probability) for item in reset)
    assert all(item.candidate_intensity == pytest.approx(item.control_intensity) for item in reset)

    before_gap = _jump_observations(181, segment="same", start_block=1)
    after_gap = _jump_observations(181, segment="same", start_block=200)
    gap_reset = build_jump_forecasts([*before_gap, *after_gap], horizon_blocks=1)
    assert len(gap_reset) == 2
    assert all(
        item.candidate_probability == pytest.approx(item.control_probability)
        for item in gap_reset
    )


def test_mutating_future_targets_cannot_change_current_forecast_values():
    observations = _jump_observations(190)
    baseline = build_jump_forecasts(observations, horizon_blocks=1)[0]
    changed = list(observations)
    future = changed[180]
    changed[180] = JumpObservation(
        observed_ms=future.observed_ms,
        segment=future.segment,
        realized_variance=future.realized_variance,
        bipower_variation=0.0,
        nonnegative_jump_variation=future.realized_variance,
        jump_share=1.0,
        event_indicator=1,
        source_digest=future.source_digest,
    )
    compared = build_jump_forecasts(changed, horizon_blocks=1)[0]
    assert compared.target_event == 1
    assert compared.target_intensity == 1.0
    assert compared.control_probability == baseline.control_probability
    assert compared.candidate_probability == baseline.candidate_probability
    assert compared.control_intensity == baseline.control_intensity
    assert compared.candidate_intensity == baseline.candidate_intensity


def test_probability_losses_are_exact_clipped_and_fail_closed():
    assert brier_loss(0.8, 1) == pytest.approx(0.04)
    assert brier_loss(0.2, 0) == pytest.approx(0.04)
    assert log_loss(0.8, 1, clip=1e-6) == pytest.approx(-math.log(0.8))
    assert log_loss(0.2, 0, clip=1e-6) == pytest.approx(-math.log(0.8))
    assert log_loss(0.0, 1, clip=1e-6) == pytest.approx(-math.log(1e-6))
    assert log_loss(1.0, 0, clip=1e-6) == pytest.approx(-math.log(1e-6))

    for probability, target in ((-0.1, 0), (1.1, 1), (0.5, 2)):
        with pytest.raises(JumpResearchError):
            brier_loss(probability, target)
        with pytest.raises(JumpResearchError):
            log_loss(probability, target, clip=1e-6)
    with pytest.raises(JumpResearchError):
        log_loss(0.5, 1, clip=0.0)


def test_average_precision_integrates_equal_score_groups_at_boundaries():
    probabilities = [0.9, 0.8, 0.8, 0.1]
    targets = [1, 0, 1, 0]
    # Recall rises by 1/2 at p=.9 with precision 1, then by 1/2 for the
    # entire tied p=.8 group with precision 2/3.
    assert average_precision(probabilities, targets) == pytest.approx(5 / 6)
    assert average_precision([0.5, 0.5, 0.5, 0.5], [1, 0, 1, 0]) == 0.5
    with pytest.raises(JumpResearchError):
        average_precision([0.5, 0.4], [0, 0])
    with pytest.raises(JumpResearchError):
        average_precision([0.5], [1, 0])


def test_calibration_uses_five_equal_count_bins_and_weighted_ece():
    probabilities = [0.05, 0.10, 0.25, 0.30, 0.45, 0.50, 0.65, 0.70, 0.85, 0.90]
    targets = [0, 0, 0, 1, 0, 1, 1, 1, 1, 1]
    result = calibration_bins(probabilities, targets, bins=5)
    ordered_bins = result["bins"]
    assert [item["count"] for item in ordered_bins] == [2, 2, 2, 2, 2]
    expected = sum(
        item["count"] / len(probabilities)
        * abs(item["mean_probability"] - item["event_rate"])
        for item in ordered_bins
    )
    assert result["ece"] == pytest.approx(expected)
    assert result == calibration_bins(probabilities, targets, bins=5)
    with pytest.raises(JumpResearchError):
        calibration_bins([0.1, 0.2], [0, 1], bins=5)


def test_scoring_uses_common_rows_and_rewards_better_probability_and_intensity():
    rows = []
    UTC = timezone.utc
    index = 0
    for year in (2020, 2021):
        for month in range(1, 13):
            month_start = int(datetime(year, month, 1, tzinfo=UTC).timestamp() * 1000)
            for block in range(10):
                target = int(block % 5 == 0)
                rows.append(
                    _forecast(
                        index,
                        target_event=target,
                        candidate_probability=0.8 if target else 0.05,
                        control_probability=0.2,
                        target_intensity=0.8 if target else 0.1,
                        candidate_intensity=0.75 if target else 0.12,
                        control_intensity=0.3,
                        decision_ms=month_start + block * FOUR_HOURS_MS,
                    )
                )
                index += 1
    score = score_jump_forecasts(
        rows, bootstrap_replications=200, bootstrap_seed=20260831
    )
    assert score["candidate"]["mean_brier"] < score["control"]["mean_brier"]
    assert score["candidate"]["mean_log_loss"] < score["control"]["mean_log_loss"]
    assert score["candidate"]["mean_intensity_mae"] < score["control"]["mean_intensity_mae"]
    assert score["candidate"]["mean_intensity_mse"] < score["control"]["mean_intensity_mse"]
    assert score["candidate"]["average_precision"] > score["control"]["average_precision"]
    assert score["event_prevalence"] == pytest.approx(0.2)


def test_month_block_bootstrap_is_seeded_and_deterministic():
    values = [0.1, 0.2, 0.3, 0.4]
    first = month_block_bootstrap(values, replications=200, seed=20260831)
    second = month_block_bootstrap(values, replications=200, seed=20260831)
    assert first == second
    assert first["valid_replications"] == 200
    assert first.get("months", first.get("month_blocks")) == 4
    interval = first.get("ci95", [first.get("lower_95"), first.get("upper_95")])
    point = first.get("point_estimate", first.get("estimate"))
    assert interval[0] <= point <= interval[1]


def test_module_has_no_strategy_or_external_client_imports():
    source = (
        Path(__file__).resolve().parents[1] / "src/trading_platform/research_jump.py"
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
