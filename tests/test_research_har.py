from __future__ import annotations

import math
from pathlib import Path

import pytest

from trading_platform.research_har import (
    DailyRealizedVariance,
    ForecastComparison,
    HARSample,
    build_daily_realized_variances,
    build_har_samples,
    build_rv_ewma,
    fit_har_model,
    score_forecasts,
)
from trading_platform.research_ledger import DAY_MS, FIVE_MINUTES_MS
from trading_platform.research_volatility import CandlePoint


DIGEST = "a" * 64


def _candle(index: int, open_ms: int, *, segment: str = "0") -> CandlePoint:
    close = 100.0 + index * 0.01
    return CandlePoint(
        segment=segment,
        open_ms=open_ms,
        open=close - 0.005,
        high=close + 0.01,
        low=close - 0.01,
        close=close,
        source_row=index,
    )


def _daily(count: int, *, segment: str = "0", start_day: int = 1):
    return [
        DailyRealizedVariance(
            observed_ms=(start_day + index) * DAY_MS,
            segment=segment,
            realized_variance=0.0001 * (1 + (index % 11) / 20),
            source_digest=DIGEST,
        )
        for index in range(count)
    ]


def test_daily_realized_variance_requires_complete_same_segment_utc_day():
    start = DAY_MS
    candles = [
        _candle(index, start - FIVE_MINUTES_MS + index * FIVE_MINUTES_MS)
        for index in range(289)
    ]
    values, audit = build_daily_realized_variances(
        candles,
        start_ms=start,
        end_ms=start + DAY_MS,
        source_digest=DIGEST,
    )
    assert len(values) == 1
    assert values[0].observed_ms == start + DAY_MS
    assert audit["valid_days"] == 1

    contaminated = list(candles)
    contaminated[100] = _candle(
        100, contaminated[100].open_ms, segment="changed"
    )
    values, audit = build_daily_realized_variances(
        contaminated,
        start_ms=start,
        end_ms=start + DAY_MS,
        source_digest=DIGEST,
    )
    assert values == []
    assert audit["excluded"]["incomplete_or_cross_segment_day"] == 1


def test_har_features_and_labels_never_cross_gap_or_segment():
    continuous = _daily(35)
    samples = build_har_samples(continuous, 1)
    assert samples
    first = samples[0]
    assert first.features[0] == continuous[21].realized_variance
    assert first.features[1] == pytest.approx(
        sum(item.realized_variance for item in continuous[17:22]) / 5
    )
    assert first.target_variance == continuous[22].realized_variance

    changed = list(continuous)
    changed[20] = DailyRealizedVariance(
        observed_ms=changed[20].observed_ms,
        segment="1",
        realized_variance=changed[20].realized_variance,
        source_digest=DIGEST,
    )
    changed_samples = build_har_samples(changed, 1)
    assert all(not (item.decision_ms - 21 * DAY_MS <= changed[20].observed_ms <= item.target_end_ms) for item in changed_samples)


def test_monthly_fit_embargo_ignores_targets_not_ended_by_cutoff():
    samples = [
        HARSample(
            decision_ms=index * DAY_MS,
            target_end_ms=(index + 1) * DAY_MS,
            horizon_days=1,
            segment="0",
            features=(
                0.0001 * (1 + index / 1000),
                0.0002 * (1 + (index % 17) / 100),
                0.0003 * (1 + (index % 29) / 100),
            ),
            target_variance=0.00015 * (1 + (index % 31) / 100),
            source_digest=DIGEST,
        )
        for index in range(320)
    ]
    cutoff = 300 * DAY_MS
    baseline = fit_har_model(
        samples,
        cutoff_ms=cutoff,
        horizon_days=1,
        minimum_training_samples=250,
        ridge_penalty=1e-6,
        variance_floor=1e-12,
    )
    changed = list(samples)
    future = changed[305]
    changed[305] = HARSample(
        decision_ms=future.decision_ms,
        target_end_ms=future.target_end_ms,
        horizon_days=1,
        segment=future.segment,
        features=future.features,
        target_variance=10.0,
        source_digest=future.source_digest,
    )
    compared = fit_har_model(
        changed,
        cutoff_ms=cutoff,
        horizon_days=1,
        minimum_training_samples=250,
        ridge_penalty=1e-6,
        variance_floor=1e-12,
    )
    assert baseline is not None and compared is not None
    assert baseline.digest == compared.digest
    assert baseline.training_samples == 300


def test_same_input_ewma_resets_after_segment_boundary():
    first = _daily(30, segment="0")
    second = _daily(30, segment="1", start_day=40)
    forecasts = build_rv_ewma(
        [*first, *second], decay_lambda=0.94, initialization_observations=30
    )
    assert first[-1].observed_ms in forecasts
    assert second[0].observed_ms not in forecasts
    assert second[-1].observed_ms in forecasts


def test_scoring_uses_common_rows_and_reports_stable_improvement():
    rows = []
    for index in range(120):
        realized = 0.0001 * (1 + (index % 12) / 10)
        rows.append(
            ForecastComparison(
                decision_ms=(365 + index) * DAY_MS,
                target_end_ms=(366 + index) * DAY_MS,
                horizon_days=1,
                realized_variance=realized,
                har_forecast=realized * 1.01,
                close_ewma_forecast=realized * 1.35,
                rv_ewma_forecast=realized * 1.20,
                model_cutoff_ms=365 * DAY_MS,
                model_digest=DIGEST,
                source_digest=DIGEST,
            )
        )
    score = score_forecasts(rows, bootstrap_replications=500, bootstrap_seed=7)
    assert score["har"]["mean_qlike"] < score["controls"]["rv_ewma"]["mean_qlike"]
    assert score["month_bootstrap_qlike_improvement_vs_rv_ewma"]["lower_95"] > 0
    assert score["calibration_quartiles"]["4"]["mean_realized_variance"] > score["calibration_quartiles"]["1"]["mean_realized_variance"]


def test_har_module_has_no_runtime_or_external_service_imports():
    source = (Path(__file__).parents[1] / "src/trading_platform/research_har.py").read_text(
        encoding="utf-8"
    )
    forbidden = ("requests", "sqlalchemy", "nats", "freqtrade", "ccxt", "order_intent")
    assert not any(f"import {name}" in source or f"from {name}" in source for name in forbidden)
