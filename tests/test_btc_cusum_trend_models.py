from __future__ import annotations

import dataclasses
import gzip
import hashlib
import importlib.util
import json
import math
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from trading_platform.btc_cusum_trend_models import (
    M2_FEATURES,
    OUTER_YEARS,
    ComparisonMetrics,
    ContinuousModelEvaluation,
    ContinuousOutcomeObservation,
    CusumTrendModelError,
    FoldRequirements,
    OOFPrediction,
    RegressionMetrics,
    canonical_digest,
    continuous_outcomes_from_cusum_records,
    evaluate_continuous_models,
    evaluate_tne2_gates,
    paired_comparison,
    regression_metrics,
    validate_observations,
)
from trading_platform.btc_cusum_trend_events import CusumTrendLabel, CusumTrigger, ONE_HOUR_MS


UTC = timezone.utc
ROOT = Path(__file__).resolve().parents[1]
DIGEST = hashlib.sha256(b"synthetic-only").hexdigest()
SMALL = FoldRequirements(
    min_outer_train=40,
    min_outer_evaluation=15,
    min_inner_train=20,
    min_inner_evaluation=10,
    min_inner_folds=2,
)


def features(decision: datetime, index: int) -> dict[str, float]:
    hour = decision.weekday() * 24 + decision.hour
    angle = 2.0 * math.pi * hour / 168.0
    run_hours = 2 + index % 12
    return {
        "momentum_24h_z": math.sin(index / 7.0),
        "momentum_72h_z": math.cos(index / 11.0),
        "sigma24_over_sigma7d": 0.5 + (index % 8) / 10.0,
        "hour_of_week_sin": math.sin(angle),
        "hour_of_week_cos": math.cos(angle),
        "cusum_run_hours": float(run_hours),
        "cusum_positive_contributor_count": float(1 + index % run_hours),
        "cusum_trigger_score_over_threshold_excess": (index % 9) / 8.0,
        "cusum_max_one_hour_contribution_fraction": 0.1 + (index % 7) / 10.0,
    }


def observation(
    event_id: str,
    decision: datetime,
    index: int,
    *,
    target: float | None = None,
    **overrides: object,
) -> ContinuousOutcomeObservation:
    values = features(decision, index)
    outcome = (
        0.08 * values["momentum_24h_z"]
        + 0.55 * values["cusum_trigger_score_over_threshold_excess"]
        - 0.25 * values["cusum_max_one_hour_contribution_fraction"]
        + 0.01 * ((index % 5) - 2)
        if target is None
        else target
    )
    payload: dict[str, object] = {
        "event_id": event_id,
        "segment": "synthetic-segment",
        "decision_at": decision,
        "feature_available_at": {name: decision for name in M2_FEATURES},
        "target_observed_at": decision + timedelta(hours=72),
        "target_available_at": decision + timedelta(hours=72),
        "normalized_72h_log_return": outcome,
        "features": values,
        "source_digest": DIGEST,
        "feature_digest": DIGEST,
    }
    payload.update(overrides)
    return ContinuousOutcomeObservation(**payload)  # type: ignore[arg-type]


def synthetic_panel(*, constant_target: float | None = None) -> tuple[ContinuousOutcomeObservation, ...]:
    rows = []
    index = 0
    for year in range(2017, 2026):
        start = datetime(year, 1, 5, tzinfo=UTC)
        for offset in range(30):
            decision = start + timedelta(days=5 * offset, hours=offset % 4)
            rows.append(
                observation(
                    f"synthetic-{year}-{offset:02d}",
                    decision,
                    index,
                    target=constant_target,
                )
            )
            index += 1
    return tuple(rows)


def trigger_and_label(
    *,
    decision: datetime = datetime(2020, 5, 4, 12, tzinfo=UTC),
    trigger_id: str = "synthetic-trigger",
) -> tuple[dict[str, object], dict[str, object]]:
    trigger_ms = int(decision.timestamp() * 1000)
    hour = decision.weekday() * 24 + decision.hour
    angle = 2.0 * math.pi * hour / 168.0
    trigger = CusumTrigger(
        experiment_id="btc-cusum-trend-onset-tne1-v1",
        trigger_id=trigger_id,
        source_digest=DIGEST,
        segment=7,
        trigger_ms=trigger_ms,
        trigger_close=100.0,
        sigma_hourly=0.01,
        current_return=0.02,
        z_raw=2.0,
        z_clipped=2.0,
        contribution=1.75,
        cusum_before=3.0,
        cusum_after=4.75,
        threshold_excess=0.25,
        active_hours=3,
        positive_contributors=3,
        run_started_ms=trigger_ms - 2 * ONE_HOUR_MS,
        momentum_24h_log=0.05,
        momentum_72h_log=0.08,
        momentum_24h_z=1.2,
        momentum_72h_z=1.1,
        sigma24_over_sigma7d=0.4,
        hour_of_week_sine=math.sin(angle),
        hour_of_week_cosine=math.cos(angle),
        max_one_hour_positive_contribution_fraction=0.4,
        first_eligible_5m_ms=trigger_ms,
        first_eligible_price=100.0,
        model_ready=True,
        unavailable_reason=None,
        suppression_until_ms=trigger_ms + 72 * ONE_HOUR_MS,
    )
    label = CusumTrendLabel(
        experiment_id=trigger.experiment_id,
        trigger_id=trigger.trigger_id,
        trigger_digest=trigger.record_digest,
        source_digest=trigger.source_digest,
        segment=trigger.segment,
        fill_ms=trigger_ms,
        endpoint_ms=trigger_ms + 72 * ONE_HOUR_MS,
        observed_hours=72,
        censored=False,
        censor_reason=None,
        target_normalized_72h=0.75,
        diagnostic_first_passage="positive_one_daily_vol",
        diagnostic_first_passage_ms=trigger_ms + 10 * ONE_HOUR_MS,
    )
    return trigger.as_dict(), label.as_dict()


def metric(mse: float, mae: float = 0.5) -> RegressionMetrics:
    return RegressionMetrics(20, mse, mae, 0.0, 1.0)


def gate_evaluation(**overrides: object) -> ContinuousModelEvaluation:
    pooled = overrides.get(
        "pooled_metrics", {"M0": metric(1.0), "M1": metric(0.9), "M2": metric(0.7)}
    )
    per_year = overrides.get(
        "per_year_metrics",
        {
            year: {
                "M0": metric(1.0),
                "M1": metric(0.9),
                "M2": metric(0.8 if year < 2025 else 0.95),
            }
            for year in OUTER_YEARS
        },
    )
    comparison = overrides.get(
        "comparison",
        ComparisonMetrics(
            baseline_model_id="M1",
            candidate_model_id="M2",
            mse_improvement=0.2,
            mae_improvement=0.01,
            bootstrap_lower=0.02,
            bootstrap_upper=0.3,
            bootstrap_repetitions=10_000,
            bootstrap_seed=20260901,
            bootstrap_method="circular_moving_block_complete_utc_calendar",
            bootstrap_block_months=3,
            bootstrap_calendar_start="2021-01",
            bootstrap_calendar_end="2025-12",
            best_three_months=("2021-01", "2022-01", "2023-01"),
            excluding_best_three_mse_improvement=0.01,
            top_three_positive_improvement_fraction=0.4,
            top_year_positive_improvement_fraction=0.5,
        ),
    )
    predictions = overrides.get(
        "predictions",
        tuple(
            OOFPrediction(
                event_id=f"gate-{year}-{month:02d}",
                decision_at=datetime(year, month, 5, tzinfo=UTC),
                evaluation_year=year,
                actual=0.25,
                m0=0.0,
                m1=0.1,
                m2=0.2,
                selected_model_id="M2",
            )
            for year in OUTER_YEARS
            for month in range(1, 13)
        ),
    )
    return ContinuousModelEvaluation((), predictions, pooled, per_year, (comparison,))  # type: ignore[arg-type]


def load_runner(name: str):
    path = ROOT / "scripts/run_btc_cusum_trend_models.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, value: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_jsonl_gzip(path: Path, rows: list[dict[str, object]]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = b"".join(
        (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode()
        for row in rows
    )
    path.write_bytes(gzip.compress(raw, mtime=0))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def model_runner_fixture(tmp_path: Path, *, model_allowed: bool = True) -> Path:
    bindings = []
    roles = {
        "model_module": "src/trading_platform/btc_cusum_trend_models.py",
        "model_runner": "scripts/run_btc_cusum_trend_models.py",
        "model_tests": "tests/test_btc_cusum_trend_models.py",
    }
    for role in (
        "source",
        "source_manifest",
        "design",
        "research_standard",
        "mandate",
        "cost_model",
        "event_module",
        "event_runner",
        "event_tests",
        "calibration_script",
        "predecessor_result",
    ):
        roles[role] = f"bound/{role}.txt"
    for role, relative in roles.items():
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if role in {"model_module", "model_runner", "model_tests"}:
            shutil.copyfile(ROOT / relative, destination)
        else:
            destination.write_text(f"synthetic binding for {role}\n", encoding="utf-8")
        bindings.append(
            {"path": relative, "role": role, "sha256": hashlib.sha256(destination.read_bytes()).hexdigest()}
        )

    triggers: list[dict[str, object]] = []
    labels: list[dict[str, object]] = []
    index = 0
    for year in range(2017, 2026):
        for offset in range(30):
            decision = datetime(year, 1, 5, tzinfo=UTC) + timedelta(days=5 * offset, hours=offset % 4)
            trigger, label = trigger_and_label(
                decision=decision, trigger_id=f"runner-{year}-{offset:02d}"
            )
            label["target_normalized_72h"] = 0.2 * math.sin(index / 7) + 0.01 * (index % 3)
            label["record_digest"] = canonical_digest(
                {key: value for key, value in label.items() if key != "record_digest"}
            )
            triggers.append(trigger)
            labels.append(label)
            index += 1
    trigger_relative = "prereq/triggers.jsonl.gz"
    label_relative = "prereq/labels.jsonl.gz"
    trigger_sha = write_jsonl_gzip(tmp_path / trigger_relative, triggers)
    label_sha = write_jsonl_gzip(tmp_path / label_relative, labels)
    contract = {
        "action_boundary": {"actionable_arm_id": "no_trade"},
        "bound_inputs": bindings,
        "experiment_id": "btc-cusum-trend-onset-tne1-v1",
        "model_gates": {
            "m1_mse_better_than_m0": True,
            "m2_mse_better_than_m0": True,
            "m2_mse_better_than_m1": True,
            "m2_relative_mse_improvement_minimum": 0.02,
            "m2_month_block_bootstrap_lower_strictly_positive": True,
            "m2_mae_improvement_minimum": 0.0,
            "m2_annual_wins_minimum": 4,
            "m2_best_three_month_exclusion_strictly_positive": True,
            "m2_top_year_positive_improvement_fraction_maximum": 0.5,
            "standalone_best_three_event_month_exclusion_strictly_positive": True,
            "standalone_month_block_bootstrap_lower_strictly_positive": True,
            "standalone_pooled_actual_mean_strictly_positive": True,
            "standalone_positive_annual_means_minimum": 4,
        },
        "model_rules": {
            "bootstrap_block_months": 3,
            "bootstrap_method": "circular_moving_block_complete_utc_calendar",
            "bootstrap_repetitions": 10_000,
            "bootstrap_seed": 20260901,
            "continuation_bootstrap_seed": 20260903,
            "embargo_hours": 72,
            "fold_requirements": dataclasses.asdict(SMALL),
            "inner_folds": "expanding_chronological",
            "label_horizon_hours": 72,
            "m1_features": list(M2_FEATURES[:5]),
            "m2_additional_features": list(M2_FEATURES[5:]),
            "outer_evaluation_years": list(OUTER_YEARS),
            "primary_metric": "pooled_oof_mse_normalized_72h_log_return",
            "ridge_alphas": [0.01, 0.1, 1.0, 10.0, 100.0],
            "standardization": "training_only",
            "total_boundary_separation_hours": 144,
        },
        "outputs": {
            "trigger": {
                "catalogue": trigger_relative,
                "report": "prereq/trigger-report.json",
                "manifest": "prereq/trigger-manifest.json",
            },
            "label": {
                "catalogue": label_relative,
                "report": "prereq/label-report.json",
                "manifest": "prereq/label-manifest.json",
            },
            "model": {
                "catalogue": "out/predictions.jsonl.gz",
                "report": "out/model-report.json",
                "manifest": "out/model-manifest.json",
            },
        },
        "status": "frozen_before_historical_trigger_access",
    }
    contract_path = tmp_path / "contract.json"
    contract_sha = write_json(contract_path, contract)
    trigger_report = {
        "contract_sha256": contract_sha,
        "experiment_id": contract["experiment_id"],
        "model_ready_trigger_count": len(triggers),
    }
    trigger_report_sha = write_json(tmp_path / "prereq/trigger-report.json", trigger_report)
    trigger_manifest = {
        "artifacts": [
            {"path": trigger_relative, "sha256": trigger_sha},
            {"path": "prereq/trigger-report.json", "sha256": trigger_report_sha},
        ],
        "contract_sha256": contract_sha,
        "experiment_id": contract["experiment_id"],
        "phase": "trigger",
    }
    write_json(tmp_path / "prereq/trigger-manifest.json", trigger_manifest)
    label_report = {
        "contract_sha256": contract_sha,
        "experiment_id": contract["experiment_id"],
        "label_count": len(labels),
        "model_phase_allowed": model_allowed,
        "trigger_report_sha256": trigger_report_sha,
    }
    label_report_sha = write_json(tmp_path / "prereq/label-report.json", label_report)
    label_manifest = {
        "artifacts": [
            {"path": label_relative, "sha256": label_sha},
            {"path": "prereq/label-report.json", "sha256": label_report_sha},
        ],
        "contract_sha256": contract_sha,
        "experiment_id": contract["experiment_id"],
        "phase": "label",
    }
    write_json(tmp_path / "prereq/label-manifest.json", label_manifest)
    return contract_path


def test_observation_is_immutable_causal_and_checksum_serializable():
    decision = datetime(2020, 5, 4, 12, tzinfo=UTC)
    row = observation("one", decision, 3)
    assert row.target_observed_at - row.decision_at == timedelta(hours=72)
    assert row.as_dict()["record_digest"]
    with pytest.raises(dataclasses.FrozenInstanceError):
        row.event_id = "changed"  # type: ignore[misc]
    with pytest.raises(TypeError):
        row.features["momentum_24h_z"] = 10.0  # type: ignore[index]


def test_tne1_adapter_binds_checksums_lineage_fill_and_frozen_features():
    trigger, label = trigger_and_label()
    first = continuous_outcomes_from_cusum_records((trigger,), (label,))
    second = continuous_outcomes_from_cusum_records((dict(trigger),), (dict(label),))
    assert first[0].as_dict() == second[0].as_dict()
    row = first[0]
    assert tuple(row.features) == M2_FEATURES
    assert set(row.feature_available_at.values()) == {row.decision_at}
    assert row.features["cusum_run_hours"] == 3.0
    assert row.features["cusum_trigger_score_over_threshold_excess"] == 0.25
    assert row.target_observed_at == row.decision_at + timedelta(hours=72)
    assert row.feature_digest != DIGEST
    changed_label = dict(label)
    changed_label["target_normalized_72h"] = -4.0
    changed_label["record_digest"] = canonical_digest(
        {key: value for key, value in changed_label.items() if key != "record_digest"}
    )
    changed = continuous_outcomes_from_cusum_records((trigger,), (changed_label,))[0]
    assert changed.feature_digest == row.feature_digest


def test_tne1_adapter_fails_on_tampering_lineage_and_censoring():
    trigger, label = trigger_and_label()
    tampered = dict(trigger)
    tampered["momentum_24h_z"] = 999.0
    with pytest.raises(CusumTrendModelError, match="trigger record validation"):
        continuous_outcomes_from_cusum_records((tampered,), (label,))

    wrong_lineage = dict(label)
    wrong_lineage["trigger_digest"] = "f" * 64
    wrong_lineage["record_digest"] = canonical_digest(
        {key: value for key, value in wrong_lineage.items() if key != "record_digest"}
    )
    with pytest.raises(CusumTrendModelError, match="exact trigger digest"):
        continuous_outcomes_from_cusum_records((trigger,), (wrong_lineage,))

    original = CusumTrendLabel(
        experiment_id=str(label["experiment_id"]),
        trigger_id=str(label["trigger_id"]),
        trigger_digest=str(label["trigger_digest"]),
        source_digest=str(label["source_digest"]),
        segment=int(label["segment"]),
        fill_ms=int(datetime.fromisoformat(str(label["fill_at"]).replace("Z", "+00:00")).timestamp() * 1000),
        endpoint_ms=None,
        observed_hours=20,
        censored=True,
        censor_reason="source_end",
        target_normalized_72h=None,
        diagnostic_first_passage=None,
        diagnostic_first_passage_ms=None,
    )
    with pytest.raises(CusumTrendModelError, match="censored"):
        continuous_outcomes_from_cusum_records((trigger,), (original.as_dict(),))


def test_tne1_adapter_rejects_fill_source_segment_id_and_horizon_mismatches():
    trigger, label = trigger_and_label()
    cases = (
        ("fill_at", "2020-05-04T13:00:00Z", "fill timestamps"),
        ("source_digest", "e" * 64, "source digests"),
        ("segment", "8", "segments"),
        ("endpoint_at", "2020-05-07T13:00:00Z", "exactly 72"),
        ("trigger_id", "other", "IDs do not match"),
    )
    for key, value, message in cases:
        changed = dict(label)
        changed[key] = value
        if key == "endpoint_at":
            changed["available_at"] = value
        changed["record_digest"] = canonical_digest(
            {name: item for name, item in changed.items() if name != "record_digest"}
        )
        with pytest.raises(CusumTrendModelError, match=message):
            continuous_outcomes_from_cusum_records((trigger,), (changed,))


def test_bad_feature_availability_censoring_and_target_horizon_fail_closed():
    decision = datetime(2020, 5, 4, 12, tzinfo=UTC)
    availability = {name: decision for name in M2_FEATURES}
    availability["momentum_24h_z"] = decision + timedelta(hours=1)
    with pytest.raises(CusumTrendModelError, match="unavailable"):
        observation("future-feature", decision, 1, feature_available_at=availability)
    with pytest.raises(CusumTrendModelError, match="censored"):
        observation(
            "censored",
            decision,
            1,
            censored=True,
            normalized_72h_log_return=None,
        )
    with pytest.raises(CusumTrendModelError, match="exactly 72"):
        observation(
            "wrong-horizon",
            decision,
            1,
            target_observed_at=decision + timedelta(hours=71),
        )


def test_feature_semantics_and_hour_encoding_fail_closed():
    decision = datetime(2020, 5, 4, 12, tzinfo=UTC)
    invalid = features(decision, 2)
    invalid["cusum_positive_contributor_count"] = invalid["cusum_run_hours"] + 1.0
    with pytest.raises(CusumTrendModelError, match="within the run"):
        observation("contributors", decision, 2, features=invalid)
    invalid = features(decision, 2)
    invalid["hour_of_week_sin"] = 0.0
    with pytest.raises(CusumTrendModelError, match="hour-of-week"):
        observation("clock", decision, 2, features=invalid)


def test_sequence_rejects_duplicate_ids_timestamps_and_overlapping_labels():
    first = observation("first", datetime(2020, 1, 1, tzinfo=UTC), 1)
    duplicate_id = observation("first", datetime(2020, 1, 5, tzinfo=UTC), 2)
    with pytest.raises(CusumTrendModelError, match="duplicate event_id"):
        validate_observations((first, duplicate_id))
    duplicate_time = observation("second", first.decision_at, 2)
    with pytest.raises(CusumTrendModelError, match="duplicate decision_at"):
        validate_observations((first, duplicate_time))
    overlap = observation("overlap", first.decision_at + timedelta(hours=48), 2)
    with pytest.raises(CusumTrendModelError, match="overlap"):
        validate_observations((first, overlap))


def test_nested_expanding_evaluation_is_deterministic_and_m2_adds_signal():
    panel = synthetic_panel()
    one = evaluate_continuous_models(
        panel, requirements=SMALL, bootstrap_repetitions=300, bootstrap_seed=91
    )
    two = evaluate_continuous_models(
        tuple(reversed(panel)), requirements=SMALL, bootstrap_repetitions=300, bootstrap_seed=91
    )
    assert one.as_dict() == two.as_dict()
    assert tuple(fold.evaluation_year for fold in one.outer_folds) == OUTER_YEARS
    assert len(one.predictions) == 5 * 30
    assert one.pooled_metrics["M2"].mse < one.pooled_metrics["M1"].mse
    assert set(one.per_year_metrics) == set(OUTER_YEARS)
    assert one.as_dict()["digest"]


def test_tne2_gate_evaluator_applies_every_frozen_rule_deterministically():
    evaluation = gate_evaluation()
    first = evaluate_tne2_gates(evaluation)
    second = evaluate_tne2_gates(evaluation)
    assert first.passed
    assert first.as_dict() == second.as_dict()
    assert [check.gate_id for check in first.checks] == [
        "standalone_pooled_actual_mean",
        "standalone_month_block_bootstrap_lower",
        "standalone_positive_annual_means",
        "standalone_best_three_month_exclusion",
        "m1_mse_better_than_m0",
        "m2_mse_better_than_m0",
        "m2_mse_better_than_m1",
        "m2_relative_mse_improvement",
        "m2_month_block_bootstrap_lower",
        "m2_mae_improvement",
        "m2_annual_wins",
        "m2_best_three_month_exclusion",
        "m2_top_year_concentration",
    ]
    assert first.as_dict()["actionable_arm_id"] == "no_trade"
    assert not first.as_dict()["pnl_or_strategy_approved"]


@pytest.mark.parametrize(
    ("change", "failed_gate"),
    (
        ({"pooled_metrics": {"M0": metric(1.0), "M1": metric(1.1), "M2": metric(0.7)}}, "m1_mse_better_than_m0"),
        ({"pooled_metrics": {"M0": metric(1.0), "M1": metric(0.9), "M2": metric(0.89)}}, "m2_relative_mse_improvement"),
        ({"comparison": dataclasses.replace(gate_evaluation().comparisons[0], bootstrap_lower=0.0)}, "m2_month_block_bootstrap_lower"),
        ({"comparison": dataclasses.replace(gate_evaluation().comparisons[0], mae_improvement=-0.01)}, "m2_mae_improvement"),
        ({"comparison": dataclasses.replace(gate_evaluation().comparisons[0], excluding_best_three_mse_improvement=0.0)}, "m2_best_three_month_exclusion"),
        ({"comparison": dataclasses.replace(gate_evaluation().comparisons[0], top_year_positive_improvement_fraction=0.51)}, "m2_top_year_concentration"),
    ),
)
def test_tne2_gate_evaluator_fails_without_alternative_search(change, failed_gate):
    result = evaluate_tne2_gates(gate_evaluation(**change))
    assert not result.passed
    assert failed_gate in {check.gate_id for check in result.checks if not check.passed}


def test_tne2_standalone_continuation_gate_rejects_nonpositive_outcomes():
    negative = tuple(
        dataclasses.replace(row, actual=-0.25) for row in gate_evaluation().predictions
    )
    result = evaluate_tne2_gates(gate_evaluation(predictions=negative))
    failed = {check.gate_id for check in result.checks if not check.passed}
    assert {
        "standalone_pooled_actual_mean",
        "standalone_month_block_bootstrap_lower",
        "standalone_positive_annual_means",
        "standalone_best_three_month_exclusion",
    }.issubset(failed)


def test_future_evaluation_targets_cannot_change_any_fitted_oof_prediction():
    panel = synthetic_panel()
    base = evaluate_continuous_models(
        panel, requirements=SMALL, bootstrap_repetitions=100, bootstrap_seed=5
    )
    changed = tuple(
        dataclasses.replace(row, normalized_72h_log_return=row.normalized_72h_log_return + 100.0)
        if row.decision_at.year == 2025
        else row
        for row in panel
    )
    replay = evaluate_continuous_models(
        changed, requirements=SMALL, bootstrap_repetitions=100, bootstrap_seed=5
    )
    base_forecasts = [(row.m0, row.m1, row.m2) for row in base.predictions]
    changed_forecasts = [(row.m0, row.m1, row.m2) for row in replay.predictions]
    assert base_forecasts == changed_forecasts
    assert [(f.m1_alpha, f.m2_alpha) for f in base.outer_folds] == [
        (f.m1_alpha, f.m2_alpha) for f in replay.outer_folds
    ]


def test_boundary_purges_unavailable_label_then_applies_separate_72h_embargo():
    panel = list(synthetic_panel())
    panel.append(observation("included-boundary", datetime(2020, 12, 25, tzinfo=UTC), 500))
    panel.append(observation("purged-boundary", datetime(2020, 12, 29, tzinfo=UTC), 501))
    result = evaluate_continuous_models(
        panel, requirements=SMALL, bootstrap_repetitions=50, bootstrap_seed=7
    )
    fold = result.outer_folds[0]
    assert fold.training_cutoff == datetime(2020, 12, 29, tzinfo=UTC)
    assert fold.train_count == 121  # 120 ordinary rows plus Dec 25; Dec 29 is purged.


def test_ties_choose_simpler_model_and_smallest_frozen_alpha():
    result = evaluate_continuous_models(
        synthetic_panel(constant_target=0.25),
        requirements=SMALL,
        bootstrap_repetitions=50,
        bootstrap_seed=3,
    )
    assert all(fold.selected_model_id == "M0" for fold in result.outer_folds)
    assert all(fold.m1_alpha == 0.01 and fold.m2_alpha == 0.01 for fold in result.outer_folds)


def test_regression_calibration_handles_constant_and_nonconstant_forecasts():
    constant = regression_metrics((1.0, 2.0, 3.0), (2.0, 2.0, 2.0))
    assert constant.mse == pytest.approx(2.0 / 3.0)
    assert constant.calibration_slope is None
    calibrated = regression_metrics((1.0, 3.0, 5.0), (0.0, 1.0, 2.0))
    assert calibrated.calibration_intercept == pytest.approx(1.0)
    assert calibrated.calibration_slope == pytest.approx(2.0)


def test_month_block_bootstrap_best_month_exclusion_and_concentration_are_deterministic():
    rows = []
    for index in range(12):
        decision = datetime(2021 + index // 6, index % 6 + 1, 5, tzinfo=UTC)
        actual = float(index % 4 - 1)
        rows.append(
            OOFPrediction(
                event_id=f"p-{index}",
                decision_at=decision,
                evaluation_year=decision.year,
                actual=actual,
                m0=0.0,
                m1=actual * 0.5,
                m2=actual,
                selected_model_id="M2",
            )
        )
    one = paired_comparison(rows, "M1", "M2", bootstrap_repetitions=200, bootstrap_seed=19)
    two = paired_comparison(rows, "M1", "M2", bootstrap_repetitions=200, bootstrap_seed=19)
    assert one == two
    assert one.bootstrap_method == "circular_moving_block_complete_utc_calendar"
    assert one.bootstrap_block_months == 3
    assert one.bootstrap_calendar_start == "2021-01"
    assert one.bootstrap_calendar_end == "2025-12"
    assert one.mse_improvement > 0.0
    assert len(one.best_three_months) == 3
    assert one.excluding_best_three_mse_improvement is not None
    assert 0.0 <= one.top_three_positive_improvement_fraction <= 1.0
    assert 0.0 <= one.top_year_positive_improvement_fraction <= 1.0


def test_insufficient_outer_or_inner_fold_counts_fail_closed():
    sparse = tuple(row for row in synthetic_panel() if row.decision_at.year <= 2021)
    with pytest.raises(CusumTrendModelError, match="insufficient"):
        evaluate_continuous_models(sparse, requirements=SMALL, bootstrap_repetitions=10)


def test_model_runner_is_contract_bound_atomic_no_clobber_and_no_trade(tmp_path):
    contract = model_runner_fixture(tmp_path)
    runner = load_runner("run_btc_cusum_models_success")
    result = runner.run(contract, "btc-cusum-trend-onset-tne1-v1", tmp_path)
    assert result["actionable_arm_id"] == "no_trade"
    assert not result["strategy_or_pnl_evaluated"]
    assert result["prediction_count"] == 150
    assert (tmp_path / "out/predictions.jsonl.gz").exists()
    assert (tmp_path / "out/model-report.json").exists()
    assert (tmp_path / "out/model-manifest.json").exists()
    with gzip.open(tmp_path / "out/predictions.jsonl.gz", "rt", encoding="utf-8") as handle:
        first = json.loads(next(handle))
    assert first["actionable_arm_id"] == "no_trade"
    assert first["experiment_id"] == "btc-cusum-trend-onset-tne1-v1"
    assert first["feature_digest"] and first["record_digest"]
    assert first["trigger_record_digest"] and first["label_record_digest"]
    assert first["observation_record_digest"]
    with pytest.raises(CusumTrendModelError, match="refusing to overwrite"):
        runner.run(contract, "btc-cusum-trend-onset-tne1-v1", tmp_path)


def test_model_runner_checks_permission_before_loading_label_values(tmp_path, monkeypatch):
    contract = model_runner_fixture(tmp_path, model_allowed=False)
    runner = load_runner("run_btc_cusum_models_blocked")
    called = False

    def forbidden(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("label values must remain unread")

    monkeypatch.setattr(runner, "_read_jsonl_gzip", forbidden)
    with pytest.raises(CusumTrendModelError, match="do not permit"):
        runner.run(contract, "btc-cusum-trend-onset-tne1-v1", tmp_path)
    assert not called


def test_model_runner_checks_bound_hashes_before_adapter(tmp_path, monkeypatch):
    contract = model_runner_fixture(tmp_path)
    runner = load_runner("run_btc_cusum_models_hash")
    (tmp_path / "bound/design.txt").write_text("changed", encoding="utf-8")
    called = False

    def forbidden(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("adapter must not run")

    monkeypatch.setattr(runner, "continuous_outcomes_from_cusum_records", forbidden)
    with pytest.raises(CusumTrendModelError, match="bound input checksum"):
        runner.run(contract, "btc-cusum-trend-onset-tne1-v1", tmp_path)
    assert not called


def test_model_runner_atomic_directory_failure_is_cleanly_retryable(tmp_path, monkeypatch):
    contract = model_runner_fixture(tmp_path)
    runner = load_runner("run_btc_cusum_models_atomic")
    original_fsync = runner.os.fsync

    def interrupted(_descriptor):
        raise OSError("synthetic interruption")

    monkeypatch.setattr(runner.os, "fsync", interrupted)
    with pytest.raises(OSError, match="synthetic interruption"):
        runner.run(contract, "btc-cusum-trend-onset-tne1-v1", tmp_path)
    assert not (tmp_path / "out").exists()
    assert not tuple(tmp_path.glob(".out.*.tmp"))
    monkeypatch.setattr(runner.os, "fsync", original_fsync)
    result = runner.run(contract, "btc-cusum-trend-onset-tne1-v1", tmp_path)
    assert result["prediction_count"] == 150


def test_model_runner_rejects_unrecognized_frozen_model_rule(tmp_path):
    contract_path = model_runner_fixture(tmp_path)
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["model_rules"]["unrecognized_rule"] = "silently-dangerous"
    contract_path.write_text(json.dumps(contract, sort_keys=True), encoding="utf-8")
    runner = load_runner("run_btc_cusum_models_extra_rule")
    with pytest.raises(CusumTrendModelError, match="exact frozen schema"):
        runner.run(contract_path, "btc-cusum-trend-onset-tne1-v1", tmp_path)
