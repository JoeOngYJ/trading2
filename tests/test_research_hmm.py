from __future__ import annotations

import math
from datetime import datetime, timezone

import pytest

from trading_platform.research_hmm import (
    FEATURE_IDS,
    FeatureRow,
    ResearchHMMError,
    RobustScaler,
    fit_student_t_hmm,
    month_block_state_difference,
    state_path_statistics,
)
from trading_platform.research_routing import RegimeState, canonical_digest


UTC = timezone.utc


def test_robust_scaler_is_past_only_and_clips():
    rows = [(float(index),) * len(FEATURE_IDS) for index in range(1, 10)]
    scaler = RobustScaler.fit(rows, floor=1e-6, clip=8)
    assert scaler.medians == (5.0,) * len(FEATURE_IDS)
    assert scaler.transform((1_000.0,) * len(FEATURE_IDS)) == (8,) * len(FEATURE_IDS)
    with pytest.raises(ResearchHMMError, match="dimensionality"):
        scaler.transform((1.0,))


def test_student_t_hmm_converges_and_canonicalizes_stress_state():
    values = []
    for block in range(8):
        center = -1.5 if block % 2 == 0 else 2.0
        for offset in range(30):
            wobble = 0.05 * math.sin(offset)
            values.append(tuple(center + wobble * (dimension + 1) for dimension in range(4)))
    fit = fit_student_t_hmm(values)
    assert fit.converged
    assert sum(fit.locations[0]) < sum(fit.locations[1])
    assert fit.transition[0][0] >= 0.9
    assert fit.transition[1][1] >= 0.9


def _state(day: int, stress: float) -> RegimeState:
    timestamp = datetime(2024, 1, day, tzinfo=UTC)
    return RegimeState(
        model_id="fixture",
        model_version="v1",
        instrument="BTC/USDT",
        interval="1d",
        segment="fixture",
        observed_at=timestamp,
        available_at=timestamp,
        fit_cutoff=datetime(2024, 1, 1, tzinfo=UTC),
        probabilities={"ordinary_risk": 1 - stress, "stress_risk": stress},
        confidence=max(stress, 1 - stress),
        entropy=-sum(value * math.log(value) for value in (stress, 1 - stress) if value),
        state_age=1,
        transition_probability=0.1,
        transition_reason="fixture",
        cutoffs={"hard_stress_probability": 0.5},
    )


def test_state_path_statistics_counts_runs_and_occupancy():
    states = [_state(day, stress) for day, stress in enumerate((0.1, 0.2, 0.8, 0.9, 0.2), 1)]
    result = state_path_statistics(states)
    assert result["transitions"] == 2
    assert result["occupancy"] == {"ordinary_risk": 0.6, "stress_risk": 0.4}
    assert result["median_dwell"] == {"ordinary_risk": 1.5, "stress_risk": 2}


def test_month_block_difference_is_deterministic_and_positive():
    labels = []
    for month in ("2024-01", "2024-02", "2024-03"):
        labels.extend(
            [
                {"label_month": month, "state": "ordinary_risk", "risk": 1.0},
                {"label_month": month, "state": "stress_risk", "risk": 3.0},
            ]
        )
    first = month_block_state_difference(labels, "risk", seed=7, replications=100)
    second = month_block_state_difference(labels, "risk", seed=7, replications=100)
    assert first == second
    assert first["observed_difference"] == 2.0
    assert first["ci95"] == [2.0, 2.0]


def test_feature_row_serialization_rejects_digest_drift():
    row = FeatureRow(
        observed_ms=1_704_067_200_000,
        available_ms=1_704_067_200_000,
        values=(1.0, 1.0, 1.0, 1.0),
        feature_digest=canonical_digest({"wrong": True}),
        source_digest="0" * 64,
    )
    with pytest.raises(ResearchHMMError, match="digest"):
        row.as_dict()
