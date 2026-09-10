"""Synthetic-only continuous-outcome infrastructure for BTC CUSUM trend-onset research.

The module accepts already constructed immutable observations.  It performs no data retrieval,
market access, strategy simulation, PnL, routing, or runtime integration.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import MappingProxyType
from typing import Any, Mapping, Sequence

import numpy as np

from trading_platform.btc_cusum_trend_events import (
    LABEL_HOURS as EVENT_LABEL_HOURS,
    ONE_HOUR_MS,
    CusumTrendLabel,
    CusumTrigger,
    CusumTrendEventError,
    trigger_from_record,
)


UTC = timezone.utc
OUTER_YEARS = (2021, 2022, 2023, 2024, 2025)
RIDGE_ALPHAS = (0.01, 0.1, 1.0, 10.0, 100.0)
LABEL_HORIZON = timedelta(hours=72)
EMBARGO = timedelta(hours=72)
TOTAL_BOUNDARY_SEPARATION = LABEL_HORIZON + EMBARGO
BOOTSTRAP_BLOCK_MONTHS = 3
MODEL_COMPARISON_BOOTSTRAP_SEED = 20260901
CONTINUATION_BOOTSTRAP_SEED = 20260903
BOOTSTRAP_CALENDAR_MONTHS = tuple(
    f"{year:04d}-{month:02d}"
    for year in OUTER_YEARS
    for month in range(1, 13)
)

M1_FEATURES = (
    "momentum_24h_z",
    "momentum_72h_z",
    "sigma24_over_sigma7d",
    "hour_of_week_sin",
    "hour_of_week_cos",
)
M2_ADDITIONAL_FEATURES = (
    "cusum_run_hours",
    "cusum_positive_contributor_count",
    "cusum_trigger_score_over_threshold_excess",
    "cusum_max_one_hour_contribution_fraction",
)
M2_FEATURES = M1_FEATURES + M2_ADDITIONAL_FEATURES


class CusumTrendModelError(ValueError):
    """Raised when a continuous-outcome evaluation would cease to be causal."""


def _utc(value: datetime, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise CusumTrendModelError(f"{label} must be timezone-aware UTC")
    if value.utcoffset() != timedelta(0):
        raise CusumTrendModelError(f"{label} must use UTC")
    return value.astimezone(UTC)


def _iso(value: datetime) -> str:
    return _utc(value, "timestamp").isoformat().replace("+00:00", "Z")


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CusumTrendModelError(f"{label} must be a non-empty string")
    return value.strip()


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool):
        raise CusumTrendModelError(f"{label} must be finite")
    number = float(value)
    if not math.isfinite(number):
        raise CusumTrendModelError(f"{label} must be finite")
    return number


def _digest(value: str, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or value.lower() != value:
        raise CusumTrendModelError(f"{label} must be a lowercase SHA-256 digest")
    try:
        int(value, 16)
    except ValueError as exc:
        raise CusumTrendModelError(f"{label} must be hexadecimal") from exc
    return value


def canonical_digest(value: Any) -> str:
    rendered = json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ContinuousOutcomeObservation:
    event_id: str
    segment: str
    decision_at: datetime
    feature_available_at: Mapping[str, datetime]
    target_observed_at: datetime
    target_available_at: datetime
    normalized_72h_log_return: float | None
    features: Mapping[str, float]
    source_digest: str
    feature_digest: str
    censored: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_id", _text(self.event_id, "event_id"))
        object.__setattr__(self, "segment", _text(self.segment, "segment"))
        decision = _utc(self.decision_at, "decision_at")
        if any((decision.minute, decision.second, decision.microsecond)):
            raise CusumTrendModelError("decision_at must be an exact completed UTC hour")
        observed = _utc(self.target_observed_at, "target_observed_at")
        available = _utc(self.target_available_at, "target_available_at")
        if observed != decision + LABEL_HORIZON:
            raise CusumTrendModelError("target_observed_at must be exactly 72 hours after decision")
        if available < observed:
            raise CusumTrendModelError("target cannot be available before it is observed")
        if self.censored or self.normalized_72h_log_return is None:
            raise CusumTrendModelError("censored or missing continuous targets fail closed")
        object.__setattr__(
            self,
            "normalized_72h_log_return",
            _finite(self.normalized_72h_log_return, "normalized_72h_log_return"),
        )

        if set(self.features) != set(M2_FEATURES):
            raise CusumTrendModelError("features must match the frozen M2 feature set exactly")
        normalized_features = {
            name: _finite(self.features[name], f"features[{name}]") for name in M2_FEATURES
        }
        if set(self.feature_available_at) != set(M2_FEATURES):
            raise CusumTrendModelError(
                "feature_available_at must cover the frozen feature set exactly"
            )
        normalized_availability: dict[str, datetime] = {}
        for name in M2_FEATURES:
            timestamp = _utc(self.feature_available_at[name], f"feature_available_at[{name}]")
            if timestamp > decision:
                raise CusumTrendModelError(f"feature {name} is unavailable at decision_at")
            normalized_availability[name] = timestamp

        if normalized_features["sigma24_over_sigma7d"] <= 0.0:
            raise CusumTrendModelError("sigma24_over_sigma7d must be positive")
        run_hours = normalized_features["cusum_run_hours"]
        contributors = normalized_features["cusum_positive_contributor_count"]
        if run_hours < 1.0 or not run_hours.is_integer():
            raise CusumTrendModelError("cusum_run_hours must be a positive integer")
        if contributors < 1.0 or not contributors.is_integer() or contributors > run_hours:
            raise CusumTrendModelError(
                "cusum_positive_contributor_count must be an integer within the run"
            )
        if normalized_features["cusum_trigger_score_over_threshold_excess"] < 0.0:
            raise CusumTrendModelError("CUSUM trigger excess cannot be negative")
        maximum_fraction = normalized_features["cusum_max_one_hour_contribution_fraction"]
        if maximum_fraction < 0.0 or maximum_fraction > 1.0:
            raise CusumTrendModelError("maximum one-hour contribution fraction must be in [0, 1]")

        hour = decision.weekday() * 24 + decision.hour
        angle = 2.0 * math.pi * hour / 168.0
        if not math.isclose(
            normalized_features["hour_of_week_sin"], math.sin(angle), abs_tol=1e-12
        ) or not math.isclose(
            normalized_features["hour_of_week_cos"], math.cos(angle), abs_tol=1e-12
        ):
            raise CusumTrendModelError("hour-of-week encoding does not match decision_at")

        object.__setattr__(self, "features", MappingProxyType(normalized_features))
        object.__setattr__(
            self, "feature_available_at", MappingProxyType(normalized_availability)
        )
        object.__setattr__(self, "source_digest", _digest(self.source_digest, "source_digest"))
        object.__setattr__(self, "feature_digest", _digest(self.feature_digest, "feature_digest"))

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "censored": self.censored,
            "decision_at": _iso(self.decision_at),
            "event_id": self.event_id,
            "feature_available_at": {
                key: _iso(value) for key, value in self.feature_available_at.items()
            },
            "feature_digest": self.feature_digest,
            "features": dict(self.features),
            "normalized_72h_log_return": self.normalized_72h_log_return,
            "segment": self.segment,
            "source_digest": self.source_digest,
            "target_available_at": _iso(self.target_available_at),
            "target_observed_at": _iso(self.target_observed_at),
        }
        return {**payload, "record_digest": canonical_digest(payload)}


def _datetime_from_ms(value: int, label: str) -> datetime:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CusumTrendModelError(f"{label} must be a non-negative integer millisecond")
    if value % ONE_HOUR_MS:
        raise CusumTrendModelError(f"{label} must be an exact UTC hour")
    return datetime(1970, 1, 1, tzinfo=UTC) + timedelta(milliseconds=value)


def _label_from_record(record: Mapping[str, Any]) -> CusumTrendLabel:
    """Reconstruct one label only after its complete canonical record checksum passes."""

    expected = record.get("record_digest")
    payload = {key: value for key, value in record.items() if key != "record_digest"}
    if not isinstance(expected, str) or expected != canonical_digest(payload):
        raise CusumTrendModelError("label record digest mismatch")
    if record.get("actionable_arm_id") != "no_trade":
        raise CusumTrendModelError("label record is not research-only no_trade")

    def parse_ms(value: object, label: str, *, optional: bool = False) -> int | None:
        if value is None and optional:
            return None
        if not isinstance(value, str) or not value.endswith("Z"):
            raise CusumTrendModelError(f"{label} must be canonical UTC Z")
        try:
            parsed = datetime.fromisoformat(value[:-1] + "+00:00")
        except ValueError as exc:
            raise CusumTrendModelError(f"{label} is invalid") from exc
        if parsed.utcoffset() != timedelta(0):
            raise CusumTrendModelError(f"{label} must use UTC")
        return int(parsed.timestamp() * 1000)

    try:
        label = CusumTrendLabel(
            experiment_id=str(record.get("experiment_id")),
            trigger_id=str(record.get("trigger_id")),
            trigger_digest=str(record.get("trigger_digest")),
            source_digest=str(record.get("source_digest")),
            segment=int(record.get("segment")),
            fill_ms=int(parse_ms(record.get("fill_at"), "fill_at")),
            endpoint_ms=parse_ms(record.get("endpoint_at"), "endpoint_at", optional=True),
            observed_hours=int(record.get("observed_hours")),
            censored=record.get("censored"),
            censor_reason=(
                str(record["censor_reason"])
                if record.get("censor_reason") is not None
                else None
            ),
            target_normalized_72h=(
                float(record["target_normalized_72h"])
                if record.get("target_normalized_72h") is not None
                else None
            ),
            diagnostic_first_passage=(
                str(record["diagnostic_first_passage"])
                if record.get("diagnostic_first_passage") is not None
                else None
            ),
            diagnostic_first_passage_ms=parse_ms(
                record.get("diagnostic_first_passage_at"),
                "diagnostic_first_passage_at",
                optional=True,
            ),
        )
    except (TypeError, ValueError) as exc:
        raise CusumTrendModelError("label record fields are invalid") from exc
    if not isinstance(label.censored, bool):
        raise CusumTrendModelError("label censored must be boolean")
    if label.as_dict() != dict(record):
        raise CusumTrendModelError("label record is not the exact canonical schema")
    return label


def continuous_outcomes_from_cusum_records(
    trigger_records: Sequence[Mapping[str, Any]],
    label_records: Sequence[Mapping[str, Any]],
) -> tuple[ContinuousOutcomeObservation, ...]:
    """Join checksummed TNE1 records into the exact frozen TNE2 observation schema.

    This adapter does not infer, recompute, or alias any source field.  Every feature is known
    at the completed trigger hour, while the target becomes available only at the exact 72-hour
    same-segment endpoint.
    """

    if not trigger_records or not label_records:
        raise CusumTrendModelError("checksummed trigger and label records are required")
    triggers: dict[str, tuple[CusumTrigger, str]] = {}
    for record in trigger_records:
        try:
            trigger = trigger_from_record(record)
        except (CusumTrendEventError, TypeError, ValueError) as exc:
            raise CusumTrendModelError("trigger record validation failed") from exc
        if trigger.as_dict() != dict(record):
            raise CusumTrendModelError("trigger record is not the exact canonical schema")
        if trigger.trigger_id in triggers:
            raise CusumTrendModelError("duplicate trigger_id")
        triggers[trigger.trigger_id] = (trigger, trigger.record_digest)

    labels: dict[str, tuple[CusumTrendLabel, str]] = {}
    for record in label_records:
        label = _label_from_record(record)
        if label.trigger_id in labels:
            raise CusumTrendModelError("duplicate label trigger_id")
        labels[label.trigger_id] = (label, label.record_digest)
    if set(triggers) != set(labels):
        raise CusumTrendModelError("trigger and label IDs do not match exactly")

    observations: list[ContinuousOutcomeObservation] = []
    for trigger_id in sorted(triggers, key=lambda key: (triggers[key][0].trigger_ms, key)):
        trigger, trigger_digest = triggers[trigger_id]
        label, label_digest = labels[trigger_id]
        if trigger.record_digest != trigger_digest or label.record_digest != label_digest:
            raise CusumTrendModelError("record digest changed during adapter validation")
        if label.trigger_digest != trigger_digest:
            raise CusumTrendModelError("label does not bind the exact trigger digest")
        if label.experiment_id != trigger.experiment_id:
            raise CusumTrendModelError("trigger and label experiment IDs differ")
        if label.source_digest != trigger.source_digest:
            raise CusumTrendModelError("trigger and label source digests differ")
        if label.segment != trigger.segment:
            raise CusumTrendModelError("trigger and label segments differ")
        if not trigger.model_ready or trigger.unavailable_reason is not None:
            raise CusumTrendModelError("non-ready trigger cannot enter TNE2")
        if trigger.first_eligible_5m_ms is None or trigger.first_eligible_price is None:
            raise CusumTrendModelError("trigger fill identity is missing")
        if label.fill_ms != trigger.first_eligible_5m_ms or label.fill_ms != trigger.trigger_ms:
            raise CusumTrendModelError("trigger and label fill timestamps differ")
        if label.censored or label.target_normalized_72h is None:
            raise CusumTrendModelError("censored or missing label fails closed")
        if label.endpoint_ms is None:
            raise CusumTrendModelError("uncensored label endpoint is missing")
        if label.endpoint_ms != label.fill_ms + EVENT_LABEL_HOURS * ONE_HOUR_MS:
            raise CusumTrendModelError("label endpoint is not exactly 72 hours after fill")
        if label.observed_hours != EVENT_LABEL_HOURS or label.censor_reason is not None:
            raise CusumTrendModelError("complete label coverage fields are inconsistent")

        decision = _datetime_from_ms(trigger.trigger_ms, "trigger_ms")
        endpoint = _datetime_from_ms(label.endpoint_ms, "endpoint_ms")
        features = {
            "momentum_24h_z": trigger.momentum_24h_z,
            "momentum_72h_z": trigger.momentum_72h_z,
            "sigma24_over_sigma7d": trigger.sigma24_over_sigma7d,
            "hour_of_week_sin": trigger.hour_of_week_sine,
            "hour_of_week_cos": trigger.hour_of_week_cosine,
            "cusum_run_hours": float(trigger.active_hours),
            "cusum_positive_contributor_count": float(trigger.positive_contributors),
            "cusum_trigger_score_over_threshold_excess": trigger.threshold_excess,
            "cusum_max_one_hour_contribution_fraction": (
                trigger.max_one_hour_positive_contribution_fraction
            ),
        }
        availability = {name: decision for name in M2_FEATURES}
        digest_payload = {
            "event_id": trigger_id,
            "feature_available_at": {name: _iso(decision) for name in M2_FEATURES},
            "feature_schema": list(M2_FEATURES),
            "features": {name: features[name] for name in M2_FEATURES},
            "segment": str(trigger.segment),
            "source_digest": trigger.source_digest,
            "trigger_record_digest": trigger_digest,
        }
        observations.append(
            ContinuousOutcomeObservation(
                event_id=trigger_id,
                segment=str(trigger.segment),
                decision_at=decision,
                feature_available_at=availability,
                target_observed_at=endpoint,
                target_available_at=endpoint,
                normalized_72h_log_return=label.target_normalized_72h,
                features=features,
                source_digest=trigger.source_digest,
                feature_digest=canonical_digest(digest_payload),
                censored=False,
            )
        )
    return validate_observations(observations)


def validate_observations(
    observations: Sequence[ContinuousOutcomeObservation],
) -> tuple[ContinuousOutcomeObservation, ...]:
    checked = tuple(sorted(observations, key=lambda row: (row.decision_at, row.event_id)))
    if not checked:
        raise CusumTrendModelError("observations cannot be empty")
    event_ids = [row.event_id for row in checked]
    if len(event_ids) != len(set(event_ids)):
        raise CusumTrendModelError("observations contain duplicate event_id")
    decisions = [row.decision_at for row in checked]
    if len(decisions) != len(set(decisions)):
        raise CusumTrendModelError("observations contain duplicate decision_at")
    prior: ContinuousOutcomeObservation | None = None
    for row in checked:
        if prior is not None and row.decision_at < prior.target_observed_at:
            raise CusumTrendModelError("continuous target windows overlap")
        prior = row
    return checked


@dataclass(frozen=True, slots=True)
class FoldRequirements:
    min_outer_train: int = 80
    min_outer_evaluation: int = 20
    min_inner_train: int = 40
    min_inner_evaluation: int = 10
    min_inner_folds: int = 2

    def __post_init__(self) -> None:
        for name in (
            "min_outer_train",
            "min_outer_evaluation",
            "min_inner_train",
            "min_inner_evaluation",
            "min_inner_folds",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise CusumTrendModelError(f"{name} must be a positive integer")


@dataclass(frozen=True, slots=True)
class RidgeFit:
    model_id: str
    feature_names: tuple[str, ...]
    alpha: float
    means: tuple[float, ...]
    scales: tuple[float, ...]
    coefficients: tuple[float, ...]
    intercept: float

    def predict(self, rows: Sequence[ContinuousOutcomeObservation]) -> np.ndarray:
        matrix = _matrix(rows, self.feature_names)
        standardized = (matrix - np.asarray(self.means)) / np.asarray(self.scales)
        return self.intercept + standardized @ np.asarray(self.coefficients)


def _matrix(
    rows: Sequence[ContinuousOutcomeObservation], feature_names: Sequence[str]
) -> np.ndarray:
    return np.asarray(
        [[row.features[name] for name in feature_names] for row in rows], dtype=float
    )


def _targets(rows: Sequence[ContinuousOutcomeObservation]) -> np.ndarray:
    return np.asarray([row.normalized_72h_log_return for row in rows], dtype=float)


def fit_ridge(
    rows: Sequence[ContinuousOutcomeObservation], feature_names: Sequence[str], alpha: float, model_id: str
) -> RidgeFit:
    if alpha not in RIDGE_ALPHAS:
        raise CusumTrendModelError("ridge alpha is outside the frozen grid")
    if not rows:
        raise CusumTrendModelError("ridge training rows cannot be empty")
    names = tuple(feature_names)
    matrix = _matrix(rows, names)
    target = _targets(rows)
    means = matrix.mean(axis=0)
    scales = matrix.std(axis=0, ddof=0)
    scales = np.where(scales > 0.0, scales, 1.0)
    standardized = (matrix - means) / scales
    intercept = float(target.mean())
    centered_target = target - intercept
    gram = standardized.T @ standardized + float(alpha) * np.eye(len(names))
    coefficients = np.linalg.solve(gram, standardized.T @ centered_target)
    return RidgeFit(
        model_id=model_id,
        feature_names=names,
        alpha=float(alpha),
        means=tuple(float(value) for value in means),
        scales=tuple(float(value) for value in scales),
        coefficients=tuple(float(value) for value in coefficients),
        intercept=intercept,
    )


@dataclass(frozen=True, slots=True)
class InnerScore:
    model_id: str
    alpha: float | None
    mse: float
    mae: float
    prediction_count: int
    fold_count: int


@dataclass(frozen=True, slots=True)
class OuterFold:
    evaluation_year: int
    training_cutoff: datetime
    train_count: int
    evaluation_count: int
    inner_fold_count: int
    m1_alpha: float
    m2_alpha: float
    selected_model_id: str
    inner_scores: tuple[InnerScore, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "evaluation_count": self.evaluation_count,
            "evaluation_year": self.evaluation_year,
            "inner_fold_count": self.inner_fold_count,
            "inner_scores": [
                {
                    "alpha": row.alpha,
                    "fold_count": row.fold_count,
                    "mae": row.mae,
                    "model_id": row.model_id,
                    "mse": row.mse,
                    "prediction_count": row.prediction_count,
                }
                for row in self.inner_scores
            ],
            "m1_alpha": self.m1_alpha,
            "m2_alpha": self.m2_alpha,
            "selected_model_id": self.selected_model_id,
            "train_count": self.train_count,
            "training_cutoff": _iso(self.training_cutoff),
        }


@dataclass(frozen=True, slots=True)
class OOFPrediction:
    event_id: str
    decision_at: datetime
    evaluation_year: int
    actual: float
    m0: float
    m1: float
    m2: float
    selected_model_id: str

    def value(self, model_id: str) -> float:
        if model_id not in {"M0", "M1", "M2"}:
            raise CusumTrendModelError(f"unknown model_id: {model_id}")
        return float(getattr(self, model_id.lower()))

    def as_dict(self) -> dict[str, Any]:
        return {
            "actual": self.actual,
            "decision_at": _iso(self.decision_at),
            "evaluation_year": self.evaluation_year,
            "event_id": self.event_id,
            "m0": self.m0,
            "m1": self.m1,
            "m2": self.m2,
            "selected_model_id": self.selected_model_id,
        }


@dataclass(frozen=True, slots=True)
class RegressionMetrics:
    count: int
    mse: float
    mae: float
    calibration_intercept: float | None
    calibration_slope: float | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "calibration_intercept": self.calibration_intercept,
            "calibration_slope": self.calibration_slope,
            "count": self.count,
            "mae": self.mae,
            "mse": self.mse,
        }


def regression_metrics(actual: Sequence[float], predicted: Sequence[float]) -> RegressionMetrics:
    truth = np.asarray(actual, dtype=float)
    forecast = np.asarray(predicted, dtype=float)
    if len(truth) == 0 or len(truth) != len(forecast):
        raise CusumTrendModelError("metric arrays must be non-empty and equal length")
    if not np.all(np.isfinite(truth)) or not np.all(np.isfinite(forecast)):
        raise CusumTrendModelError("metric arrays must be finite")
    errors = truth - forecast
    variance = float(np.sum((forecast - forecast.mean()) ** 2))
    if variance <= 0.0:
        intercept = None
        slope = None
    else:
        slope = float(np.sum((forecast - forecast.mean()) * (truth - truth.mean())) / variance)
        intercept = float(truth.mean() - slope * forecast.mean())
    return RegressionMetrics(
        count=len(truth),
        mse=float(np.mean(errors**2)),
        mae=float(np.mean(np.abs(errors))),
        calibration_intercept=intercept,
        calibration_slope=slope,
    )


def _year_start(year: int) -> datetime:
    return datetime(year, 1, 1, tzinfo=UTC)


def _inner_splits(
    rows: Sequence[ContinuousOutcomeObservation], requirements: FoldRequirements
) -> tuple[tuple[tuple[ContinuousOutcomeObservation, ...], tuple[ContinuousOutcomeObservation, ...]], ...]:
    years = sorted({row.decision_at.year for row in rows})
    splits = []
    for year in years[1:]:
        start = _year_start(year)
        cutoff = start - EMBARGO
        train = tuple(row for row in rows if row.target_available_at <= cutoff)
        evaluation = tuple(row for row in rows if row.decision_at.year == year)
        if len(train) >= requirements.min_inner_train and len(evaluation) >= requirements.min_inner_evaluation:
            splits.append((train, evaluation))
    if len(splits) < requirements.min_inner_folds:
        raise CusumTrendModelError("insufficient chronological inner folds")
    return tuple(splits)


def _inner_scores(
    rows: Sequence[ContinuousOutcomeObservation], requirements: FoldRequirements
) -> tuple[InnerScore, ...]:
    splits = _inner_splits(rows, requirements)
    scores: list[InnerScore] = []

    m0_actual: list[float] = []
    m0_predicted: list[float] = []
    for train, evaluation in splits:
        m0_actual.extend(_targets(evaluation))
        m0_predicted.extend([float(_targets(train).mean())] * len(evaluation))
    metric = regression_metrics(m0_actual, m0_predicted)
    scores.append(InnerScore("M0", None, metric.mse, metric.mae, metric.count, len(splits)))

    for model_id, names in (("M1", M1_FEATURES), ("M2", M2_FEATURES)):
        for alpha in RIDGE_ALPHAS:
            actual: list[float] = []
            predicted: list[float] = []
            for train, evaluation in splits:
                fit = fit_ridge(train, names, alpha, model_id)
                actual.extend(_targets(evaluation))
                predicted.extend(fit.predict(evaluation))
            metric = regression_metrics(actual, predicted)
            scores.append(
                InnerScore(model_id, alpha, metric.mse, metric.mae, metric.count, len(splits))
            )
    return tuple(scores)


def _best_score(scores: Sequence[InnerScore], model_id: str) -> InnerScore:
    candidates = [score for score in scores if score.model_id == model_id]
    if not candidates:
        raise CusumTrendModelError(f"inner scores omit {model_id}")
    return min(candidates, key=lambda score: (score.mse, score.alpha or 0.0))


def _selected_model(scores: Sequence[InnerScore]) -> str:
    complexity = {"M0": 0, "M1": 1, "M2": 2}
    best = [_best_score(scores, model_id) for model_id in ("M0", "M1", "M2")]
    return min(
        best,
        key=lambda score: (score.mse, complexity[score.model_id], score.alpha or 0.0),
    ).model_id


@dataclass(frozen=True, slots=True)
class ComparisonMetrics:
    baseline_model_id: str
    candidate_model_id: str
    mse_improvement: float
    mae_improvement: float
    bootstrap_lower: float
    bootstrap_upper: float
    bootstrap_repetitions: int
    bootstrap_seed: int
    bootstrap_method: str
    bootstrap_block_months: int
    bootstrap_calendar_start: str
    bootstrap_calendar_end: str
    best_three_months: tuple[str, ...]
    excluding_best_three_mse_improvement: float | None
    top_three_positive_improvement_fraction: float | None
    top_year_positive_improvement_fraction: float | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "baseline_model_id": self.baseline_model_id,
            "best_three_months": list(self.best_three_months),
            "bootstrap_lower": self.bootstrap_lower,
            "bootstrap_method": self.bootstrap_method,
            "bootstrap_block_months": self.bootstrap_block_months,
            "bootstrap_calendar_end": self.bootstrap_calendar_end,
            "bootstrap_calendar_start": self.bootstrap_calendar_start,
            "bootstrap_repetitions": self.bootstrap_repetitions,
            "bootstrap_seed": self.bootstrap_seed,
            "bootstrap_upper": self.bootstrap_upper,
            "candidate_model_id": self.candidate_model_id,
            "excluding_best_three_mse_improvement": self.excluding_best_three_mse_improvement,
            "mae_improvement": self.mae_improvement,
            "mse_improvement": self.mse_improvement,
            "top_three_positive_improvement_fraction": self.top_three_positive_improvement_fraction,
            "top_year_positive_improvement_fraction": self.top_year_positive_improvement_fraction,
        }


def _circular_month_block_interval(
    values: np.ndarray,
    months: Sequence[str],
    *,
    bootstrap_repetitions: int,
    bootstrap_seed: int,
) -> tuple[float, float]:
    """Bootstrap an event-weighted mean using fixed circular 3-calendar-month blocks."""

    if len(values) != len(months) or len(values) == 0 or not np.all(np.isfinite(values)):
        raise CusumTrendModelError("month-block values must be non-empty, aligned and finite")
    if any(month not in BOOTSTRAP_CALENDAR_MONTHS for month in months):
        raise CusumTrendModelError("month-block rows must lie inside Jan-2021 through Dec-2025")
    if bootstrap_repetitions < 1 or isinstance(bootstrap_repetitions, bool):
        raise CusumTrendModelError("bootstrap_repetitions must be positive")
    month_indices = {
        key: np.flatnonzero(np.asarray(months) == key) for key in BOOTSTRAP_CALENDAR_MONTHS
    }
    generator = np.random.default_rng(bootstrap_seed)
    block_count = math.ceil(len(BOOTSTRAP_CALENDAR_MONTHS) / BOOTSTRAP_BLOCK_MONTHS)
    bootstrap = np.empty(bootstrap_repetitions, dtype=float)
    for repetition in range(bootstrap_repetitions):
        # Draw from the complete calendar grid.  Empty months stay in their block and therefore
        # preserve the observed event-arrival pattern without becoming fabricated observations.
        while True:
            starts = generator.integers(
                0, len(BOOTSTRAP_CALENDAR_MONTHS), size=block_count
            )
            selected_months = [
                BOOTSTRAP_CALENDAR_MONTHS[(int(start) + offset) % len(BOOTSTRAP_CALENDAR_MONTHS)]
                for start in starts
                for offset in range(BOOTSTRAP_BLOCK_MONTHS)
            ][: len(BOOTSTRAP_CALENDAR_MONTHS)]
            positions = [month_indices[month] for month in selected_months]
            populated = [indices for indices in positions if len(indices)]
            if populated:
                bootstrap[repetition] = float(np.mean(values[np.concatenate(populated)]))
                break
    lower, upper = np.quantile(bootstrap, (0.025, 0.975))
    return float(lower), float(upper)


def paired_comparison(
    predictions: Sequence[OOFPrediction],
    baseline_model_id: str,
    candidate_model_id: str,
    *,
    bootstrap_repetitions: int = 10_000,
    bootstrap_seed: int = 20260901,
) -> ComparisonMetrics:
    if bootstrap_repetitions < 1 or isinstance(bootstrap_repetitions, bool):
        raise CusumTrendModelError("bootstrap_repetitions must be positive")
    rows = tuple(predictions)
    if not rows:
        raise CusumTrendModelError("paired comparison requires predictions")
    actual = np.asarray([row.actual for row in rows])
    baseline = np.asarray([row.value(baseline_model_id) for row in rows])
    candidate = np.asarray([row.value(candidate_model_id) for row in rows])
    squared_delta = (actual - baseline) ** 2 - (actual - candidate) ** 2
    absolute_delta = np.abs(actual - baseline) - np.abs(actual - candidate)

    months = np.asarray([row.decision_at.strftime("%Y-%m") for row in rows])
    month_keys = tuple(sorted(set(months)))
    month_indices = [np.flatnonzero(months == key) for key in month_keys]
    lower, upper = _circular_month_block_interval(
        squared_delta,
        months,
        bootstrap_repetitions=bootstrap_repetitions,
        bootstrap_seed=bootstrap_seed,
    )

    month_sums = {
        key: float(squared_delta[indices].sum())
        for key, indices in zip(month_keys, month_indices, strict=True)
    }
    best_three = tuple(sorted(month_keys, key=lambda key: (-month_sums[key], key))[:3])
    retained = np.asarray([month not in best_three for month in months])
    excluding = float(np.mean(squared_delta[retained])) if np.any(retained) else None
    positive_total = sum(max(value, 0.0) for value in month_sums.values())
    top_three_fraction = (
        sum(max(month_sums[key], 0.0) for key in best_three) / positive_total
        if positive_total > 0.0
        else None
    )
    year_sums: dict[int, float] = {}
    for row, value in zip(rows, squared_delta, strict=True):
        year_sums[row.evaluation_year] = year_sums.get(row.evaluation_year, 0.0) + float(value)
    positive_year_total = sum(max(value, 0.0) for value in year_sums.values())
    top_year_fraction = (
        max(max(value, 0.0) for value in year_sums.values()) / positive_year_total
        if positive_year_total > 0.0
        else None
    )
    return ComparisonMetrics(
        baseline_model_id=baseline_model_id,
        candidate_model_id=candidate_model_id,
        mse_improvement=float(np.mean(squared_delta)),
        mae_improvement=float(np.mean(absolute_delta)),
        bootstrap_lower=float(lower),
        bootstrap_upper=float(upper),
        bootstrap_repetitions=bootstrap_repetitions,
        bootstrap_seed=bootstrap_seed,
        bootstrap_method="circular_moving_block_complete_utc_calendar",
        bootstrap_block_months=BOOTSTRAP_BLOCK_MONTHS,
        bootstrap_calendar_start=BOOTSTRAP_CALENDAR_MONTHS[0],
        bootstrap_calendar_end=BOOTSTRAP_CALENDAR_MONTHS[-1],
        best_three_months=best_three,
        excluding_best_three_mse_improvement=excluding,
        top_three_positive_improvement_fraction=top_three_fraction,
        top_year_positive_improvement_fraction=top_year_fraction,
    )


@dataclass(frozen=True, slots=True)
class ContinuousModelEvaluation:
    outer_folds: tuple[OuterFold, ...]
    predictions: tuple[OOFPrediction, ...]
    pooled_metrics: Mapping[str, RegressionMetrics]
    per_year_metrics: Mapping[int, Mapping[str, RegressionMetrics]]
    comparisons: tuple[ComparisonMetrics, ...]
    schema_version: str = "btc-cusum-trend-continuous-models-v1"

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "comparisons": [row.as_dict() for row in self.comparisons],
            "outer_folds": [row.as_dict() for row in self.outer_folds],
            "outer_years": list(OUTER_YEARS),
            "per_year_metrics": {
                str(year): {model: metric.as_dict() for model, metric in models.items()}
                for year, models in self.per_year_metrics.items()
            },
            "pooled_metrics": {
                model: metric.as_dict() for model, metric in self.pooled_metrics.items()
            },
            "predictions": [row.as_dict() for row in self.predictions],
            "schema_version": self.schema_version,
        }
        return {**payload, "digest": canonical_digest(payload)}


@dataclass(frozen=True, slots=True)
class TNE2GateCheck:
    gate_id: str
    passed: bool
    actual: float | None
    comparison: str
    threshold: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "actual": self.actual,
            "comparison": self.comparison,
            "gate_id": self.gate_id,
            "passed": self.passed,
            "threshold": self.threshold,
        }


@dataclass(frozen=True, slots=True)
class ContinuationMetrics:
    pooled_actual_mean: float
    bootstrap_lower: float
    bootstrap_upper: float
    bootstrap_repetitions: int
    bootstrap_seed: int
    bootstrap_method: str
    bootstrap_block_months: int
    annual_actual_means: Mapping[int, float]
    positive_annual_mean_count: int
    best_three_event_months: tuple[str, ...]
    excluding_best_three_actual_mean: float | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "annual_actual_means": {
                str(year): value for year, value in self.annual_actual_means.items()
            },
            "best_three_event_months": list(self.best_three_event_months),
            "bootstrap_block_months": self.bootstrap_block_months,
            "bootstrap_lower": self.bootstrap_lower,
            "bootstrap_method": self.bootstrap_method,
            "bootstrap_repetitions": self.bootstrap_repetitions,
            "bootstrap_seed": self.bootstrap_seed,
            "bootstrap_upper": self.bootstrap_upper,
            "excluding_best_three_actual_mean": self.excluding_best_three_actual_mean,
            "pooled_actual_mean": self.pooled_actual_mean,
            "positive_annual_mean_count": self.positive_annual_mean_count,
        }


@dataclass(frozen=True, slots=True)
class TNE2GateDecision:
    passed: bool
    checks: tuple[TNE2GateCheck, ...]
    continuation_metrics: ContinuationMetrics
    schema_version: str = "btc-cusum-trend-tne2-gates-v1"

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "actionable_arm_id": "no_trade",
            "checks": [check.as_dict() for check in self.checks],
            "continuation_metrics": self.continuation_metrics.as_dict(),
            "interpretation": "prediction_and_upside_continuation_evidence_only",
            "passed": self.passed,
            "pnl_or_strategy_approved": False,
            "schema_version": self.schema_version,
        }
        return {**payload, "digest": canonical_digest(payload)}


def _continuation_metrics(predictions: Sequence[OOFPrediction]) -> ContinuationMetrics:
    rows = tuple(predictions)
    if not rows:
        raise CusumTrendModelError("standalone continuation gates require OOF predictions")
    actual = np.asarray([row.actual for row in rows], dtype=float)
    months = np.asarray([row.decision_at.strftime("%Y-%m") for row in rows])
    if not np.all(np.isfinite(actual)):
        raise CusumTrendModelError("OOF actual outcomes must be finite")
    annual: dict[int, float] = {}
    for year in OUTER_YEARS:
        values = [row.actual for row in rows if row.evaluation_year == year]
        if not values or any(row.decision_at.year != row.evaluation_year for row in rows if row.evaluation_year == year):
            raise CusumTrendModelError(f"OOF continuation outcomes are invalid for {year}")
        annual[year] = float(np.mean(values))
    lower, upper = _circular_month_block_interval(
        actual,
        months,
        bootstrap_repetitions=10_000,
        bootstrap_seed=CONTINUATION_BOOTSTRAP_SEED,
    )
    populated_months = tuple(sorted(set(months)))
    month_sums = {
        month: float(actual[months == month].sum()) for month in populated_months
    }
    best_three = tuple(
        sorted(populated_months, key=lambda month: (-month_sums[month], month))[:3]
    )
    retained = np.asarray([month not in best_three for month in months])
    excluding = float(np.mean(actual[retained])) if np.any(retained) else None
    return ContinuationMetrics(
        pooled_actual_mean=float(actual.mean()),
        bootstrap_lower=lower,
        bootstrap_upper=upper,
        bootstrap_repetitions=10_000,
        bootstrap_seed=CONTINUATION_BOOTSTRAP_SEED,
        bootstrap_method="circular_moving_block_complete_utc_calendar",
        bootstrap_block_months=BOOTSTRAP_BLOCK_MONTHS,
        annual_actual_means=MappingProxyType(annual),
        positive_annual_mean_count=sum(value > 0.0 for value in annual.values()),
        best_three_event_months=best_three,
        excluding_best_three_actual_mean=excluding,
    )


def evaluate_tne2_gates(evaluation: ContinuousModelEvaluation) -> TNE2GateDecision:
    """Apply the pre-registered TNE2 gates once, without fitting or alternative search."""

    if set(evaluation.pooled_metrics) != {"M0", "M1", "M2"}:
        raise CusumTrendModelError("pooled metrics must contain exactly M0, M1 and M2")
    if set(evaluation.per_year_metrics) != set(OUTER_YEARS):
        raise CusumTrendModelError("annual metrics must contain exactly the frozen outer years")
    for year in OUTER_YEARS:
        if set(evaluation.per_year_metrics[year]) != {"M0", "M1", "M2"}:
            raise CusumTrendModelError(f"annual metrics for {year} are incomplete")
    matches = [
        row
        for row in evaluation.comparisons
        if row.baseline_model_id == "M1" and row.candidate_model_id == "M2"
    ]
    if len(matches) != 1:
        raise CusumTrendModelError("exactly one frozen M1-to-M2 paired comparison is required")
    comparison = matches[0]
    if (
        comparison.bootstrap_repetitions != 10_000
        or comparison.bootstrap_seed != MODEL_COMPARISON_BOOTSTRAP_SEED
        or comparison.bootstrap_method
        != "circular_moving_block_complete_utc_calendar"
        or comparison.bootstrap_block_months != BOOTSTRAP_BLOCK_MONTHS
        or comparison.bootstrap_calendar_start != BOOTSTRAP_CALENDAR_MONTHS[0]
        or comparison.bootstrap_calendar_end != BOOTSTRAP_CALENDAR_MONTHS[-1]
    ):
        raise CusumTrendModelError("M1-to-M2 comparison does not use the frozen bootstrap")
    m0 = evaluation.pooled_metrics["M0"]
    m1 = evaluation.pooled_metrics["M1"]
    m2 = evaluation.pooled_metrics["M2"]
    for metric in (m0, m1, m2):
        if metric.count < 1 or not math.isfinite(metric.mse) or not math.isfinite(metric.mae):
            raise CusumTrendModelError("gate metrics must be non-empty and finite")
    if m1.mse <= 0.0:
        relative_mse = 0.0 if m2.mse == 0.0 else -math.inf
    else:
        relative_mse = (m1.mse - m2.mse) / m1.mse
    annual_wins = sum(
        evaluation.per_year_metrics[year]["M2"].mse
        < evaluation.per_year_metrics[year]["M1"].mse
        for year in OUTER_YEARS
    )
    exclusion = comparison.excluding_best_three_mse_improvement
    top_year = comparison.top_year_positive_improvement_fraction
    continuation = _continuation_metrics(evaluation.predictions)
    continuation_exclusion = continuation.excluding_best_three_actual_mean
    checks = (
        TNE2GateCheck(
            "standalone_pooled_actual_mean",
            continuation.pooled_actual_mean > 0.0,
            continuation.pooled_actual_mean,
            ">",
            0.0,
        ),
        TNE2GateCheck(
            "standalone_month_block_bootstrap_lower",
            continuation.bootstrap_lower > 0.0,
            continuation.bootstrap_lower,
            ">",
            0.0,
        ),
        TNE2GateCheck(
            "standalone_positive_annual_means",
            continuation.positive_annual_mean_count >= 4,
            float(continuation.positive_annual_mean_count),
            ">=",
            4.0,
        ),
        TNE2GateCheck(
            "standalone_best_three_month_exclusion",
            continuation_exclusion is not None and continuation_exclusion > 0.0,
            continuation_exclusion,
            ">",
            0.0,
        ),
        TNE2GateCheck("m1_mse_better_than_m0", m1.mse < m0.mse, m0.mse - m1.mse, ">", 0.0),
        TNE2GateCheck("m2_mse_better_than_m0", m2.mse < m0.mse, m0.mse - m2.mse, ">", 0.0),
        TNE2GateCheck("m2_mse_better_than_m1", m2.mse < m1.mse, m1.mse - m2.mse, ">", 0.0),
        TNE2GateCheck("m2_relative_mse_improvement", relative_mse >= 0.02, relative_mse, ">=", 0.02),
        TNE2GateCheck(
            "m2_month_block_bootstrap_lower",
            comparison.bootstrap_lower > 0.0,
            comparison.bootstrap_lower,
            ">",
            0.0,
        ),
        TNE2GateCheck(
            "m2_mae_improvement",
            comparison.mae_improvement >= 0.0,
            comparison.mae_improvement,
            ">=",
            0.0,
        ),
        TNE2GateCheck("m2_annual_wins", annual_wins >= 4, float(annual_wins), ">=", 4.0),
        TNE2GateCheck(
            "m2_best_three_month_exclusion",
            exclusion is not None and exclusion > 0.0,
            float(exclusion) if exclusion is not None else None,
            ">",
            0.0,
        ),
        TNE2GateCheck(
            "m2_top_year_concentration",
            top_year is not None and top_year <= 0.5,
            float(top_year) if top_year is not None else None,
            "<=",
            0.5,
        ),
    )
    return TNE2GateDecision(
        passed=all(check.passed for check in checks),
        checks=checks,
        continuation_metrics=continuation,
    )


def evaluate_continuous_models(
    observations: Sequence[ContinuousOutcomeObservation],
    *,
    requirements: FoldRequirements = FoldRequirements(),
    bootstrap_repetitions: int = 10_000,
    bootstrap_seed: int = 20260901,
) -> ContinuousModelEvaluation:
    rows = validate_observations(observations)
    folds: list[OuterFold] = []
    predictions: list[OOFPrediction] = []

    for year in OUTER_YEARS:
        start = _year_start(year)
        cutoff = start - EMBARGO
        train = tuple(row for row in rows if row.target_available_at <= cutoff)
        evaluation = tuple(row for row in rows if row.decision_at.year == year)
        if len(train) < requirements.min_outer_train:
            raise CusumTrendModelError(f"outer year {year} has insufficient training rows")
        if len(evaluation) < requirements.min_outer_evaluation:
            raise CusumTrendModelError(f"outer year {year} has insufficient evaluation rows")
        inner = _inner_scores(train, requirements)
        m1_best = _best_score(inner, "M1")
        m2_best = _best_score(inner, "M2")
        selected = _selected_model(inner)
        m0_value = float(_targets(train).mean())
        m1_fit = fit_ridge(train, M1_FEATURES, float(m1_best.alpha), "M1")
        m2_fit = fit_ridge(train, M2_FEATURES, float(m2_best.alpha), "M2")
        m1_predictions = m1_fit.predict(evaluation)
        m2_predictions = m2_fit.predict(evaluation)
        for row, m1_value, m2_value in zip(
            evaluation, m1_predictions, m2_predictions, strict=True
        ):
            predictions.append(
                OOFPrediction(
                    event_id=row.event_id,
                    decision_at=row.decision_at,
                    evaluation_year=year,
                    actual=float(row.normalized_72h_log_return),
                    m0=m0_value,
                    m1=float(m1_value),
                    m2=float(m2_value),
                    selected_model_id=selected,
                )
            )
        folds.append(
            OuterFold(
                evaluation_year=year,
                training_cutoff=cutoff,
                train_count=len(train),
                evaluation_count=len(evaluation),
                inner_fold_count=_best_score(inner, "M0").fold_count,
                m1_alpha=float(m1_best.alpha),
                m2_alpha=float(m2_best.alpha),
                selected_model_id=selected,
                inner_scores=inner,
            )
        )

    ordered_predictions = tuple(
        sorted(predictions, key=lambda row: (row.decision_at, row.event_id))
    )
    pooled: dict[str, RegressionMetrics] = {}
    per_year: dict[int, Mapping[str, RegressionMetrics]] = {}
    for model_id in ("M0", "M1", "M2"):
        pooled[model_id] = regression_metrics(
            [row.actual for row in ordered_predictions],
            [row.value(model_id) for row in ordered_predictions],
        )
    for year in OUTER_YEARS:
        annual = [row for row in ordered_predictions if row.evaluation_year == year]
        per_year[year] = MappingProxyType(
            {
                model_id: regression_metrics(
                    [row.actual for row in annual], [row.value(model_id) for row in annual]
                )
                for model_id in ("M0", "M1", "M2")
            }
        )
    comparisons = (
        paired_comparison(
            ordered_predictions,
            "M0",
            "M1",
            bootstrap_repetitions=bootstrap_repetitions,
            bootstrap_seed=bootstrap_seed + 1,
        ),
        paired_comparison(
            ordered_predictions,
            "M1",
            "M2",
            bootstrap_repetitions=bootstrap_repetitions,
            bootstrap_seed=bootstrap_seed,
        ),
    )
    return ContinuousModelEvaluation(
        outer_folds=tuple(folds),
        predictions=ordered_predictions,
        pooled_metrics=MappingProxyType(pooled),
        per_year_metrics=MappingProxyType(per_year),
        comparisons=comparisons,
    )
