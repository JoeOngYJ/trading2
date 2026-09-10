from __future__ import annotations

import math
from pathlib import Path

import pytest

from trading_platform.research_downside import (
    DailyDownsideObservation,
    DownsideResearchError,
    DownsideSample,
    build_daily_downside_observations,
    build_downside_samples,
    build_horizon_tail_losses,
    es_calibration_moment,
    fit_downside_model,
    fz0_loss,
    historical_var_es,
    month_block_bootstrap,
    pinball_loss,
)
from trading_platform.research_ledger import DAY_MS, FIVE_MINUTES_MS
from trading_platform.research_volatility import CandlePoint


DIGEST = "a" * 64


def _day_candles(
    returns: list[float],
    *,
    day_start_ms: int = DAY_MS,
    segment: str = "s1",
) -> list[CandlePoint]:
    """Build one complete UTC day plus its contiguous prior close."""

    assert len(returns) == 288
    candles: list[CandlePoint] = []
    close = 100.0
    candles.append(
        CandlePoint(
            segment=segment,
            open_ms=day_start_ms - FIVE_MINUTES_MS,
            open=close,
            high=close,
            low=close,
            close=close,
            source_row=0,
        )
    )
    for index, log_return in enumerate(returns, start=1):
        prior = close
        close = prior * math.exp(log_return)
        candles.append(
            CandlePoint(
                segment=segment,
                open_ms=day_start_ms + (index - 1) * FIVE_MINUTES_MS,
                open=prior,
                high=max(prior, close),
                low=min(prior, close),
                close=close,
                source_row=index,
            )
        )
    return candles


def _daily(
    count: int,
    *,
    segment: str = "s1",
    start_day: int = 1,
) -> list[DailyDownsideObservation]:
    return [
        DailyDownsideObservation(
            observed_ms=(start_day + index) * DAY_MS,
            segment=segment,
            daily_log_return=0.001 * ((index % 7) - 2),
            negative_semivariance=0.0001 * (1 + (index % 11) / 10),
            source_digest=DIGEST,
        )
        for index in range(count)
    ]


def _sample(index: int, *, target: float | None = None) -> DownsideSample:
    return DownsideSample(
        decision_ms=index * DAY_MS,
        target_end_ms=(index + 1) * DAY_MS,
        horizon_days=1,
        segment="s1",
        features=(
            0.0001 * (1 + index / 1000),
            0.0002 * (1 + (index % 17) / 100),
            0.0003 * (1 + (index % 29) / 100),
        ),
        target_negative_semivariance=(
            0.00015 * (1 + (index % 31) / 100) if target is None else target
        ),
        target_tail_loss=0.01 * ((index % 9) - 3),
        source_digest=DIGEST,
    )


def test_complete_day_uses_prior_close_and_exact_negative_semivariance():
    returns = [0.001] * 288
    returns[0] = -0.01
    returns[143] = -0.02
    candles = _day_candles(returns)

    rows, audit = build_daily_downside_observations(
        candles,
        start_ms=DAY_MS,
        end_ms=2 * DAY_MS,
        source_digest=DIGEST,
    )

    assert len(rows) == 1
    assert rows[0].observed_ms == 2 * DAY_MS
    assert rows[0].daily_log_return == pytest.approx(sum(returns))
    assert rows[0].negative_semivariance == pytest.approx(0.01**2 + 0.02**2)
    assert audit["valid_days"] == 1
    assert audit["expected_calendar_days"] == 1


def test_complete_day_rejects_gap_and_segment_crossing():
    candles = _day_candles([0.001] * 288)
    missing = candles[:100] + candles[101:]
    rows, audit = build_daily_downside_observations(
        missing,
        start_ms=DAY_MS,
        end_ms=2 * DAY_MS,
        source_digest=DIGEST,
    )
    assert rows == []
    assert audit["excluded"]["incomplete_or_cross_segment_day"] == 1

    crossed = list(candles)
    item = crossed[100]
    crossed[100] = CandlePoint(
        segment="s2",
        open_ms=item.open_ms,
        open=item.open,
        high=item.high,
        low=item.low,
        close=item.close,
        source_row=item.source_row,
    )
    rows, audit = build_daily_downside_observations(
        crossed,
        start_ms=DAY_MS,
        end_ms=2 * DAY_MS,
        source_digest=DIGEST,
    )
    assert rows == []
    assert audit["excluded"]["incomplete_or_cross_segment_day"] == 1


def test_zero_negative_semivariance_is_valid():
    candles = _day_candles([0.001] * 288)
    rows, audit = build_daily_downside_observations(
        candles,
        start_ms=DAY_MS,
        end_ms=2 * DAY_MS,
        source_digest=DIGEST,
    )
    assert len(rows) == 1
    assert rows[0].negative_semivariance == 0.0
    assert audit["valid_days"] == 1


def test_samples_use_22_completed_days_and_complete_future_targets_only():
    observations = _daily(35)
    one_day = build_downside_samples(observations, horizon_days=1)
    assert one_day
    first = one_day[0]
    assert first.decision_ms == observations[21].observed_ms
    assert first.target_end_ms == observations[22].observed_ms
    assert first.features[0] == observations[21].negative_semivariance
    assert first.features[1] == pytest.approx(
        sum(item.negative_semivariance for item in observations[17:22]) / 5
    )
    assert first.features[2] == pytest.approx(
        sum(item.negative_semivariance for item in observations[:22]) / 22
    )
    assert first.target_negative_semivariance == observations[22].negative_semivariance
    assert first.target_tail_loss == pytest.approx(-observations[22].daily_log_return)

    seven_day = build_downside_samples(observations, horizon_days=7)
    assert seven_day
    assert seven_day[0].target_negative_semivariance == pytest.approx(
        sum(item.negative_semivariance for item in observations[22:29])
    )
    assert seven_day[0].target_tail_loss == pytest.approx(
        -sum(item.daily_log_return for item in observations[22:29])
    )


def test_sample_windows_never_cross_gap_or_segment():
    first = _daily(30, segment="s1")
    second = _daily(30, segment="s2", start_day=40)
    samples = build_downside_samples([*first, *second], horizon_days=7)
    assert samples
    assert all(item.segment in {"s1", "s2"} for item in samples)
    assert all(item.target_end_ms - item.decision_ms == 7 * DAY_MS for item in samples)
    assert all(
        not (first[-1].observed_ms < item.target_end_ms and item.decision_ms < second[0].observed_ms)
        for item in samples
    )


def test_tail_history_uses_individually_complete_losses_without_feature_warmup():
    first = _daily(5, segment="s1")
    second = _daily(30, segment="s2", start_day=40)
    observations = [*first, *second]
    losses = build_horizon_tail_losses(observations, horizon_days=1)
    samples = build_downside_samples(observations, horizon_days=1)

    assert len(losses) == len(observations)
    assert any(item.target_end_ms == second[0].observed_ms for item in losses)
    assert all(item.decision_ms != second[0].observed_ms for item in samples)

    seven_day = build_horizon_tail_losses(observations, horizon_days=7)
    assert len(seven_day) == len(second) - 6
    assert all(item.segment == "s2" for item in seven_day)


def test_model_fit_excludes_labels_at_or_after_strict_month_cutoff():
    samples = [_sample(index) for index in range(320)]
    cutoff = 300 * DAY_MS
    baseline = fit_downside_model(
        samples,
        cutoff_ms=cutoff,
        horizon_days=1,
        minimum_training_samples=250,
        ridge_penalty=1e-6,
        log_floor=1e-12,
    )
    assert baseline is not None
    assert baseline.training_samples == 299

    changed = list(samples)
    changed[299] = _sample(299, target=10.0)  # target_end_ms equals cutoff: ineligible.
    changed[305] = _sample(305, target=20.0)  # target ends after cutoff: ineligible.
    compared = fit_downside_model(
        changed,
        cutoff_ms=cutoff,
        horizon_days=1,
        minimum_training_samples=250,
        ridge_penalty=1e-6,
        log_floor=1e-12,
    )
    assert compared is not None
    assert compared.training_samples == baseline.training_samples
    assert compared.digest == baseline.digest


def test_historical_var_es_uses_linear_quantile_and_inclusive_ties():
    var, es = historical_var_es([0.0, 1.0, 2.0, 2.0, 2.0, 4.0], confidence=0.8)
    # (n-1)*p = 4, so VaR is exactly the tied value 2.  The frozen ES
    # convention includes every observation greater than or equal to VaR.
    assert var == 2.0
    assert es == pytest.approx(2.5)

    interpolated_var, interpolated_es = historical_var_es(
        [0.0, 1.0, 2.0, 3.0, 4.0], confidence=0.875
    )
    assert interpolated_var == pytest.approx(3.5)
    assert interpolated_es == 4.0


def test_tail_losses_match_frozen_formulas_and_reject_invalid_domains():
    loss = 3.0
    var = 2.0
    es = 4.0
    confidence = 0.95
    tail_probability = 0.05

    assert pinball_loss(loss, var, confidence) == pytest.approx(0.95)
    assert pinball_loss(1.0, var, confidence) == pytest.approx(0.05)
    assert pinball_loss(var, var, confidence) == 0.0
    assert es_calibration_moment(loss, var, es, tail_probability) == pytest.approx(
        (loss - var) - tail_probability * (es - var)
    )
    assert es_calibration_moment(1.0, var, es, tail_probability) == pytest.approx(
        -tail_probability * (es - var)
    )
    assert fz0_loss(loss, var, es, tail_probability) == pytest.approx(
        math.log(es)
        + var / es
        + (loss - var) / (tail_probability * es)
        - 1
    )

    for invalid_var, invalid_es in ((0.0, 1.0), (2.0, 0.0), (2.0, 1.0)):
        with pytest.raises(DownsideResearchError):
            fz0_loss(loss, invalid_var, invalid_es, tail_probability)
    with pytest.raises(DownsideResearchError):
        historical_var_es([], confidence=confidence)
    with pytest.raises(DownsideResearchError):
        pinball_loss(loss, var, 1.0)


def test_month_block_bootstrap_is_seeded_and_deterministic():
    values = [0.1, 0.2, 0.3, 0.4]
    first = month_block_bootstrap(values, replications=200, seed=20260831)
    second = month_block_bootstrap(values, replications=200, seed=20260831)
    assert first == second
    assert first["valid_replications"] == 200
    assert first.get("months", first.get("month_blocks")) == 4
    interval = first.get("ci95", [first.get("lower_95"), first.get("upper_95")])
    assert interval[0] <= first.get("point_estimate", first.get("estimate")) <= interval[1]


def test_module_has_no_strategy_or_external_client_imports():
    source = (
        Path(__file__).resolve().parents[1]
        / "src/trading_platform/research_downside.py"
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
