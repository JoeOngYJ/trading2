from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from trading_platform.btc_breakout_models import (
    BreakoutModelError,
    EmpiricalAgeHazard,
    FollowthroughEpisode,
    NumpyMultinomialHazard,
    age_basis,
    hazards_to_curves,
    integrated_brier_score,
    episode_brier_contributions,
    make_person_period,
    outer_year_folds,
    paired_month_block_interval,
    predict_episode_curves,
)


def ms(year: int, month: int = 1, day: int = 1, hour: int = 0) -> int:
    return int(datetime(year, month, day, hour, tzinfo=timezone.utc).timestamp() * 1000)


def episode(
    identity: str,
    year: int,
    event_type: str | None,
    event_hour: int | None,
    *,
    observed_hours: int = 168,
    offset: float = 0.0,
    segment_censored: bool = False,
) -> FollowthroughEpisode:
    confirmation = ms(year, 2, 1) + int(offset * 3_600_000)
    if event_type is not None:
        assert event_hour is not None
        observed_hours = event_hour
    available_hour = event_hour or observed_hours
    features = (
        0.2 + offset / 1000,
        1.0 + offset,
        0.03 + offset / 10000,
        0.8 + offset / 1000,
        0.4 + offset / 1000,
        0.2 + offset / 1000,
        0.75 + offset / 1000,
        np.sin(offset + 0.1),
        np.cos(offset + 0.1),
    )
    return FollowthroughEpisode(
        identity,
        confirmation,
        confirmation + available_hour * 3_600_000,
        event_type,
        event_hour,
        observed_hours,
        segment_censored,
        f"{year}-02",
        features,
    )


def training() -> list[FollowthroughEpisode]:
    values = []
    for index in range(18):
        cause = "continuation" if index % 3 == 0 else "range_reentry" if index % 3 == 1 else None
        hour = 12 + index * 7 if cause else None
        values.append(episode(f"e{index}", 2018 + index % 3, cause, hour, offset=float(index)))
    return values


def test_age_basis_is_shared_and_changes_across_episode_hours():
    assert age_basis(1) != age_basis(168)
    rows = make_person_period([episode("x", 2020, "continuation", 8)])
    assert rows.features.shape == (8, 14)
    assert not np.array_equal(rows.features[0], rows.features[-1])
    assert rows.labels.tolist()[-1] == 1


def test_person_period_reentry_and_censoring_are_not_expiry_classes():
    rows = make_person_period(
        [
            episode("r", 2020, "range_reentry", 3),
            episode("c", 2020, None, None, observed_hours=5, segment_censored=True),
        ]
    )
    assert set(rows.labels) == {0, 2}
    assert len(rows.labels) == 8


def test_outer_fold_purges_labels_inside_336h_embargo():
    eval_start = ms(2021)
    safe = episode("safe", 2020, None, None)
    unsafe = FollowthroughEpisode(
        "unsafe",
        eval_start - 268 * 3_600_000,
        eval_start - 100 * 3_600_000,
        None,
        None,
        168,
        False,
        "2020-12",
        safe.features,
    )
    evaluation = episode("evaluation", 2021, "continuation", 10)
    fold = outer_year_folds([safe, unsafe, evaluation], (2021,))[0]
    assert "safe" in fold.training_episode_ids
    assert "unsafe" not in fold.training_episode_ids
    assert fold.evaluation_episode_ids == ("evaluation",)


def test_empirical_hazard_and_curves_are_valid_and_age_specific():
    model = EmpiricalAgeHazard().fit(training())
    hazards = model.predict_hazards(training()[0].features)
    curves = hazards_to_curves(hazards)
    assert hazards.shape == (168, 3)
    assert np.allclose(hazards.sum(axis=1), 1)
    assert np.allclose(curves.sum(axis=1), 1)
    assert np.all(np.diff(curves[:, 2]) <= 0)


def test_numpy_linear_model_is_deterministic():
    episodes = training()
    first = NumpyMultinomialHazard(0.1).fit(episodes)
    second = NumpyMultinomialHazard(0.1).fit(episodes)
    one = first.predict_hazards(episodes[0].features)
    two = second.predict_hazards(episodes[0].features)
    assert np.array_equal(one, two)
    assert not np.array_equal(one[0], one[-1])


def test_zero_scale_feature_fails_closed_for_M1():
    repeated = [episode(str(index), 2020, "continuation" if index % 2 else "range_reentry", 10) for index in range(6)]
    with pytest.raises(BreakoutModelError, match="scale"):
        NumpyMultinomialHazard(0.1).fit(repeated)


def test_ipcw_ibs_is_finite_and_rewards_own_model_replay():
    train = training()
    evaluation = [episode("z1", 2021, "continuation", 20, offset=30), episode("z2", 2021, "range_reentry", 30, offset=31)]
    model = EmpiricalAgeHazard().fit(train)
    curves = predict_episode_curves(model, evaluation)
    score = integrated_brier_score(train, evaluation, curves)
    contributions = episode_brier_contributions(train, evaluation, curves)
    assert np.isfinite(score)
    assert score >= 0
    assert np.mean(list(contributions.values())) == pytest.approx(score)


def test_bootstrap_is_exact_seed_deterministic_and_keeps_episode_units():
    values = {
        "a": ("2021-01", 0.1),
        "b": ("2021-01", 0.2),
        "c": ("2021-02", -0.1),
        "d": ("2021-03", 0.4),
        "e": ("2021-04", -0.3),
        "f": ("2021-05", 0.5),
        "g": ("2021-06", 0.0),
    }
    assert paired_month_block_interval(values, replications=50) == paired_month_block_interval(values, replications=50)
    _, lower, upper = paired_month_block_interval(values, replications=200)
    assert lower < upper
