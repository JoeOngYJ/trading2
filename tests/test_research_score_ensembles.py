from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.qualify_btc_score_combination_foundation import DEFAULT_CONTRACT, run
from trading_platform.research_condition_scores import MarketConditionScore
from trading_platform.research_score_ensembles import (
    CalibrationSample,
    ConvexEnsembleSpec,
    ScoreCatalogue,
    ScoreCatalogueEntry,
    ScoreEnsembleError,
    calibrate_empirical_percentile,
    combine_same_target,
)


UTC = timezone.utc
NOW = datetime(2025, 1, 2, 12, tzinfo=UTC)
DIGEST_A = "a" * 64
DIGEST_B = "b" * 64


def entry(score_id: str, **updates: object) -> ScoreCatalogueEntry:
    values = {
        "score_id": score_id,
        "score_version": "v1",
        "axis": "volatility",
        "target_id": "btc_realized_variance_1d",
        "horizon_seconds": 86400,
        "score_kind": "continuous",
        "units": "variance_fraction",
        "evidence_status": "accepted" if score_id != "ewma" else "benchmark",
        "permitted_uses": ("diagnostic", "same_target_ensemble"),
        "evidence_digest": DIGEST_A,
    }
    values.update(updates)
    return ScoreCatalogueEntry(**values)  # type: ignore[arg-type]


def score(score_id: str, **updates: object) -> MarketConditionScore:
    values = {
        "score_id": score_id,
        "score_version": "v1",
        "instrument": "BTCUSDT",
        "venue": "OFFLINE_FIXTURE",
        "axis": "volatility",
        "score_kind": "continuous",
        "horizon_seconds": 86400,
        "fit_cutoff": NOW - timedelta(days=30),
        "observed_at": NOW - timedelta(hours=1),
        "available_at": NOW - timedelta(hours=1),
        "expires_at": NOW + timedelta(hours=23),
        "units": "variance_fraction",
        "point_estimate": 0.4 if score_id == "ewma" else 0.6,
        "lower_bound": 0.3 if score_id == "ewma" else 0.5,
        "upper_bound": 0.5 if score_id == "ewma" else 0.7,
        "confidence": 0.8,
        "evidence_status": "benchmark" if score_id == "ewma" else "accepted",
        "lineage_digests": {"fixture": DIGEST_B},
    }
    values.update(updates)
    return MarketConditionScore(**values)  # type: ignore[arg-type]


def samples(definition: ScoreCatalogueEntry) -> tuple[CalibrationSample, ...]:
    return tuple(
        CalibrationSample(
            observed_at=NOW - timedelta(days=45 - index),
            available_at=NOW - timedelta(days=44 - index),
            value=value,
            catalogue_entry_digest=definition.digest,
            lineage_digest=chr(99 + index) * 64,
        )
        for index, value in enumerate((0.1, 0.4, 0.4, 0.8))
    )


def spec(**updates: object) -> ConvexEnsembleSpec:
    values = {
        "ensemble_id": "synthetic-rv-combination",
        "ensemble_version": "v1",
        "axis": "volatility",
        "target_id": "btc_realized_variance_1d",
        "horizon_seconds": 86400,
        "score_kind": "continuous",
        "units": "variance_fraction",
        "weights": {"ewma@v1": 0.75, "har@v1": 0.25},
    }
    values.update(updates)
    return ConvexEnsembleSpec(**values)  # type: ignore[arg-type]


def test_catalogue_is_deterministic_and_rejected_use_is_non_actionable():
    ewma = entry("ewma")
    har = entry("har")
    first = ScoreCatalogue("btc-scores", "v1", (har, ewma))
    second = ScoreCatalogue("btc-scores", "v1", (ewma, har))
    assert first.as_dict() == second.as_dict()
    assert first.entry("ewma", "v1") == ewma
    with pytest.raises(ScoreEnsembleError, match="duplicate"):
        ScoreCatalogue("btc-scores", "v1", (ewma, ewma))
    with pytest.raises(ScoreEnsembleError, match="diagnostics or controls"):
        entry(
            "rejected-score",
            evidence_status="rejected",
            permitted_uses=("diagnostic", "same_target_ensemble"),
        )


def test_causal_midrank_calibration_preserves_status_and_is_display_only():
    definition = entry("ewma")
    calibrated = calibrate_empirical_percentile(
        score=score("ewma"),
        catalogue_entry=definition,
        samples=samples(definition),
        decision_at=NOW,
        minimum_history=4,
    )
    assert calibrated.percentile == 0.5
    assert calibrated.lower_percentile == 0.25
    assert calibrated.upper_percentile == 0.75
    assert calibrated.evidence_status == "benchmark"
    assert calibrated.display_only


def test_calibration_rejects_future_history_and_fails_closed_on_missing_or_stale_input():
    definition = entry("ewma")
    bad = CalibrationSample(
        observed_at=NOW - timedelta(days=29),
        available_at=NOW - timedelta(days=29),
        value=0.2,
        catalogue_entry_digest=definition.digest,
        lineage_digest=DIGEST_A,
    )
    with pytest.raises(ScoreEnsembleError, match="fit cutoff"):
        calibrate_empirical_percentile(
            score=score("ewma"),
            catalogue_entry=definition,
            samples=(*samples(definition), bad),
            decision_at=NOW,
            minimum_history=4,
        )
    insufficient = calibrate_empirical_percentile(
        score=score("ewma"),
        catalogue_entry=definition,
        samples=samples(definition)[:2],
        decision_at=NOW,
        minimum_history=4,
    )
    assert insufficient.percentile is None
    assert insufficient.unknown_reason == "insufficient_calibration_history"
    stale = calibrate_empirical_percentile(
        score=score("ewma", expires_at=NOW),
        catalogue_entry=definition,
        samples=samples(definition),
        decision_at=NOW,
        minimum_history=4,
    )
    assert stale.unknown_reason == "raw_score_stale_at_decision"


def test_same_target_convex_ensemble_is_deterministic_and_never_actionable():
    ewma_entry = entry("ewma")
    har_entry = entry("har")
    first = combine_same_target(
        spec=spec(),
        members=((ewma_entry, score("ewma")), (har_entry, score("har"))),
        decision_at=NOW,
    )
    second = combine_same_target(
        spec=spec(),
        members=((har_entry, score("har")), (ewma_entry, score("ewma"))),
        decision_at=NOW,
    )
    assert first.as_dict() == second.as_dict()
    assert first.point_estimate == pytest.approx(0.45)
    assert first.lower_bound == pytest.approx(0.35)
    assert first.upper_bound == pytest.approx(0.55)
    assert first.evidence_status == "development"
    assert first.actionable_arm_id == "no_trade"
    assert not first.strategy_action_created


@pytest.mark.parametrize(
    "update",
    (
        {"weights": {"ewma@v1": 0.6, "har@v1": 0.6}},
        {"weights": {"ewma@v1": 1.0, "har@v1": -0.0}},
        {"weights": {"ewma@v1": 1.0}},
    ),
)
def test_invalid_convex_weights_are_rejected(update: dict[str, object]):
    with pytest.raises(ScoreEnsembleError):
        spec(**update)


def test_ensemble_rejects_mixed_target_rejected_unknown_and_stale_members():
    ewma_entry = entry("ewma")
    har_entry = entry("har")
    with pytest.raises(ScoreEnsembleError, match="target, axis, horizon"):
        combine_same_target(
            spec=spec(),
            members=(
                (ewma_entry, score("ewma")),
                (entry("har", target_id="btc_realized_variance_7d"), score("har")),
            ),
            decision_at=NOW,
        )
    rejected_entry = entry(
        "har",
        evidence_status="rejected",
        permitted_uses=("diagnostic",),
    )
    with pytest.raises(ScoreEnsembleError, match="unusable evidence"):
        combine_same_target(
            spec=spec(),
            members=(
                (ewma_entry, score("ewma")),
                (rejected_entry, score("har", evidence_status="rejected")),
            ),
            decision_at=NOW,
        )
    with pytest.raises(ScoreEnsembleError, match="unknown, stale or unavailable"):
        combine_same_target(
            spec=spec(),
            members=(
                (ewma_entry, score("ewma")),
                (
                    har_entry,
                    score(
                        "har",
                        point_estimate=None,
                        lower_bound=None,
                        upper_bound=None,
                        unknown_reason="missing_input",
                    ),
                ),
            ),
            decision_at=NOW,
        )


def test_synthetic_qualification_is_byte_identical(tmp_path: Path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    run(DEFAULT_CONTRACT, first)
    run(DEFAULT_CONTRACT, second)
    for name in ("synthetic-qualification-report.json", "evidence-manifest.json"):
        assert (first / name).read_bytes() == (second / name).read_bytes()
        payload = json.loads((first / name).read_text(encoding="utf-8"))
        assert payload["actionable_arm_id"] == "no_trade" if name.startswith("synthetic") else True
