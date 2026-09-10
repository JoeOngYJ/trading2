"""Offline competing-risk models for frozen BTC breakout episodes.

The module operates on already-catalogued development episodes.  It has no market-data,
network, database, execution, signal, order, position, or PnL integration.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Protocol, Sequence

import numpy as np


MAX_HOURS = 168
EMBARGO_HOURS = 336
CAUSES = ("continuation", "range_reentry")
PRIMARY_STATIC_FEATURES = (
    "compression_percentile",
    "confirmation_delay_hours",
    "frozen_range_width",
    "range_width_over_sigma7d",
    "sigma24_over_sigma7d",
    "normalized_confirmation_penetration",
    "confirmation_hour_fraction_above_range",
    "hour_of_week_sine",
    "hour_of_week_cosine",
)
AGE_FEATURES = (
    "age_hour_scaled",
    "age_bin_1_6",
    "age_bin_7_24",
    "age_bin_25_72",
    "age_bin_73_168",
)


class BreakoutModelError(ValueError):
    """Raised when model input is ambiguous, non-causal, or non-finite."""


def _utc_ms(value: str) -> int:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise BreakoutModelError("timestamp must be canonical UTC Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise BreakoutModelError("invalid timestamp") from exc
    if parsed.tzinfo != timezone.utc:
        raise BreakoutModelError("timestamp must use UTC")
    return int(parsed.timestamp() * 1000)


def canonical_digest(value: object) -> str:
    rendered = json.dumps(
        value, allow_nan=False, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class FollowthroughEpisode:
    episode_id: str
    confirmation_ms: int
    label_available_ms: int
    event_type: str | None
    event_hour: int | None
    observed_hours: int
    segment_censored: bool
    confirmation_month: str
    features: tuple[float, ...]

    def __post_init__(self) -> None:
        if not self.episode_id:
            raise BreakoutModelError("episode_id is required")
        if self.confirmation_ms <= 0 or self.label_available_ms < self.confirmation_ms:
            raise BreakoutModelError("episode timestamps are invalid")
        if self.event_type not in {*CAUSES, None}:
            raise BreakoutModelError("unsupported competing event")
        if not 1 <= self.observed_hours <= MAX_HOURS:
            raise BreakoutModelError("observed_hours must be in 1..168")
        elapsed = self.label_available_ms - self.confirmation_ms
        if self.event_type is None:
            if self.event_hour is not None:
                raise BreakoutModelError("censored episode cannot have event_hour")
            if self.segment_censored:
                if not (
                    self.confirmation_ms + self.observed_hours * 3_600_000
                    <= self.label_available_ms
                    < self.confirmation_ms + (self.observed_hours + 1) * 3_600_000
                ) or self.observed_hours >= MAX_HOURS:
                    raise BreakoutModelError("segment censor availability disagrees with observed_hours")
            elif elapsed != MAX_HOURS * 3_600_000 or self.observed_hours != MAX_HOURS:
                raise BreakoutModelError("administrative censor must be exactly 168 hours")
        elif self.event_hour is None or not 1 <= self.event_hour <= self.observed_hours:
            raise BreakoutModelError("event hour must be observed")
        elif elapsed % 3_600_000:
            raise BreakoutModelError("event availability must fall on an exact completed hour")
        elif self.label_available_ms != self.confirmation_ms + self.event_hour * 3_600_000:
            raise BreakoutModelError("event availability does not match event_hour")
        elif self.observed_hours != self.event_hour:
            raise BreakoutModelError("event observed_hours must equal event_hour")
        elif self.segment_censored:
            raise BreakoutModelError("observed event cannot also be segment-censored")
        if len(self.features) != len(PRIMARY_STATIC_FEATURES):
            raise BreakoutModelError("wrong primary feature count")
        if not all(math.isfinite(value) for value in self.features):
            raise BreakoutModelError("features must be finite")
        expected_month = datetime.fromtimestamp(
            self.confirmation_ms / 1000, tz=timezone.utc
        ).strftime("%Y-%m")
        if self.confirmation_month != expected_month:
            raise BreakoutModelError("confirmation_month does not match confirmation timestamp")

    @property
    def confirmation_year(self) -> int:
        return datetime.fromtimestamp(self.confirmation_ms / 1000, tz=timezone.utc).year

    @property
    def event_class(self) -> int | None:
        if self.event_type is None:
            return None
        return 1 if self.event_type == "continuation" else 2


def episode_from_catalogue(record: Mapping[str, Any]) -> FollowthroughEpisode:
    """Convert one model-ready BEX1 record without opening any price source."""

    if record.get("model_ready") is not True:
        raise BreakoutModelError("catalogue episode is not model-ready")
    confirmation_ms = _utc_ms(record.get("confirmation_at"))
    outcome = record.get("competing_outcome")
    outcome_ms = (
        _utc_ms(record["competing_outcome_at"])
        if record.get("competing_outcome_at") is not None
        else None
    )
    censor_ms = _utc_ms(record["censor_at"]) if record.get("censor_at") else None
    available_ms = outcome_ms if outcome_ms is not None else censor_ms
    if available_ms is None:
        raise BreakoutModelError("episode lacks label availability")
    elapsed = available_ms - confirmation_ms
    if elapsed < 3_600_000:
        raise BreakoutModelError("label availability precedes first complete outcome hour")
    if outcome is not None and elapsed % 3_600_000:
        raise BreakoutModelError("event availability is not an exact completed hour")
    observed_hours = min(MAX_HOURS, elapsed // 3_600_000)
    event_hour = min(MAX_HOURS, elapsed // 3_600_000) if outcome else None
    confirmation_delay = record.get("confirmation_delay_hours")
    if not isinstance(confirmation_delay, int) or not 1 <= confirmation_delay <= MAX_HOURS:
        raise BreakoutModelError("confirmation delay must be in 1..168 hours")
    hour = record.get("hour_of_week")
    if not isinstance(hour, int) or not 0 <= hour < 168:
        raise BreakoutModelError("invalid hour_of_week")
    phase = 2.0 * math.pi * hour / 168.0
    features = (
        float(record["compression_percentile"]),
        float(confirmation_delay),
        float(record["range_width_log"]),
        float(record["range_width_over_sigma7d"]),
        float(record["sigma24_over_sigma7d"]),
        float(record["confirmation_log_penetration_over_sigma24"]),
        float(record["confirmation_hour_fraction_5m_closes_above_upper"]),
        math.sin(phase),
        math.cos(phase),
    )
    month = datetime.fromtimestamp(confirmation_ms / 1000, tz=timezone.utc).strftime("%Y-%m")
    return FollowthroughEpisode(
        episode_id=str(record["episode_id"]),
        confirmation_ms=confirmation_ms,
        label_available_ms=available_ms,
        event_type=outcome,
        event_hour=event_hour,
        observed_hours=int(observed_hours),
        segment_censored=bool(record.get("path_segment_censored")) and outcome is None,
        confirmation_month=month,
        features=features,
    )


def age_basis(hour: int) -> tuple[float, ...]:
    if not 1 <= hour <= MAX_HOURS:
        raise BreakoutModelError("age hour must be in 1..168")
    return (
        hour / MAX_HOURS,
        float(hour <= 6),
        float(7 <= hour <= 24),
        float(25 <= hour <= 72),
        float(hour >= 73),
    )


@dataclass(frozen=True, slots=True)
class PersonPeriodData:
    episode_ids: tuple[str, ...]
    hours: np.ndarray
    features: np.ndarray
    labels: np.ndarray


def make_person_period(episodes: Sequence[FollowthroughEpisode]) -> PersonPeriodData:
    if not episodes:
        raise BreakoutModelError("episodes are required")
    ids: list[str] = []
    hours: list[int] = []
    rows: list[tuple[float, ...]] = []
    labels: list[int] = []
    seen: set[str] = set()
    for episode in sorted(episodes, key=lambda item: (item.confirmation_ms, item.episode_id)):
        if episode.episode_id in seen:
            raise BreakoutModelError("duplicate episode_id")
        seen.add(episode.episode_id)
        stop = episode.event_hour or episode.observed_hours
        for hour in range(1, stop + 1):
            label = 0
            if episode.event_hour == hour:
                label = int(episode.event_class)
            ids.append(episode.episode_id)
            hours.append(hour)
            rows.append(episode.features + age_basis(hour))
            labels.append(label)
    matrix = np.asarray(rows, dtype=np.float64)
    target = np.asarray(labels, dtype=np.int64)
    if not np.isfinite(matrix).all():
        raise BreakoutModelError("person-period features must be finite")
    return PersonPeriodData(tuple(ids), np.asarray(hours), matrix, target)


@dataclass(frozen=True, slots=True)
class ChronologicalFold:
    evaluation_year: int
    training_episode_ids: tuple[str, ...]
    evaluation_episode_ids: tuple[str, ...]


def outer_year_folds(
    episodes: Sequence[FollowthroughEpisode], years: Sequence[int] = (2021, 2022, 2023, 2024, 2025)
) -> tuple[ChronologicalFold, ...]:
    if len({episode.episode_id for episode in episodes}) != len(episodes):
        raise BreakoutModelError("duplicate episode_id")
    folds: list[ChronologicalFold] = []
    ordered = sorted(episodes, key=lambda item: (item.confirmation_ms, item.episode_id))
    for year in years:
        eval_start = int(datetime(year, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
        embargo_start = eval_start - EMBARGO_HOURS * 3_600_000
        training = tuple(
            episode.episode_id
            for episode in ordered
            if episode.label_available_ms < embargo_start
        )
        evaluation = tuple(
            episode.episode_id for episode in ordered if episode.confirmation_year == year
        )
        folds.append(ChronologicalFold(year, training, evaluation))
    return tuple(folds)


def cause_counts(episodes: Sequence[FollowthroughEpisode]) -> dict[str, int]:
    return {
        "episodes": len(episodes),
        "continuation": sum(item.event_type == "continuation" for item in episodes),
        "range_reentry": sum(item.event_type == "range_reentry" for item in episodes),
        "censored": sum(item.event_type is None for item in episodes),
    }


class HazardModel(Protocol):
    def predict_hazards(self, static_features: Sequence[float]) -> np.ndarray: ...


class EmpiricalAgeHazard:
    """Jeffreys-smoothed age-specific competing hazards (M0)."""

    def __init__(self) -> None:
        self._hazards: np.ndarray | None = None

    def fit(self, episodes: Sequence[FollowthroughEpisode]) -> "EmpiricalAgeHazard":
        if not episodes:
            raise BreakoutModelError("M0 needs training episodes")
        hazards = np.zeros((MAX_HOURS, 3), dtype=np.float64)
        for hour in range(1, MAX_HOURS + 1):
            at_risk = [episode for episode in episodes if episode.observed_hours >= hour and (episode.event_hour is None or episode.event_hour >= hour)]
            n = len(at_risk)
            if n == 0:
                raise BreakoutModelError(f"M0 has no training risk-set support at hour {hour}")
            event1 = sum(ep.event_type == "continuation" and ep.event_hour == hour for ep in at_risk)
            event2 = sum(ep.event_type == "range_reentry" and ep.event_hour == hour for ep in at_risk)
            denom = n + 1.5
            hazards[hour - 1, 1] = (event1 + 0.5) / denom
            hazards[hour - 1, 2] = (event2 + 0.5) / denom
            hazards[hour - 1, 0] = max(0.0, 1.0 - hazards[hour - 1, 1:].sum())
            hazards[hour - 1] /= hazards[hour - 1].sum()
        self._hazards = hazards
        return self

    def predict_hazards(self, static_features: Sequence[float]) -> np.ndarray:
        if self._hazards is None:
            raise BreakoutModelError("M0 is not fitted")
        if len(static_features) != len(PRIMARY_STATIC_FEATURES):
            raise BreakoutModelError("wrong static feature count")
        return self._hazards.copy()


class NumpyMultinomialHazard:
    """Deterministic standardized L2 multinomial hazard (M1)."""

    def __init__(self, l2: float, *, max_iter: int = 5000, tolerance: float = 1e-6) -> None:
        if l2 <= 0 or not math.isfinite(l2):
            raise BreakoutModelError("M1 L2 must be positive")
        self.l2 = float(l2)
        self.max_iter = max_iter
        self.tolerance = tolerance
        self.mean_: np.ndarray | None = None
        self.scale_: np.ndarray | None = None
        self.weights_: np.ndarray | None = None

    @staticmethod
    def _softmax(logits: np.ndarray) -> np.ndarray:
        shifted = logits - logits.max(axis=1, keepdims=True)
        exp = np.exp(shifted)
        return exp / exp.sum(axis=1, keepdims=True)

    def _loss(self, x: np.ndarray, y: np.ndarray, weights: np.ndarray) -> float:
        probabilities = self._softmax(x @ weights)
        nll = -np.log(np.maximum(probabilities[np.arange(len(y)), y], 1e-15)).mean()
        return float(nll + 0.5 * self.l2 * np.sum(weights[1:] ** 2))

    def fit(self, episodes: Sequence[FollowthroughEpisode]) -> "NumpyMultinomialHazard":
        data = make_person_period(episodes)
        if set(np.unique(data.labels)) != {0, 1, 2}:
            raise BreakoutModelError("M1 training lacks a required class")
        mean = data.features.mean(axis=0)
        scale = data.features.std(axis=0, ddof=0)
        if not np.isfinite(mean).all() or not np.isfinite(scale).all() or np.any(scale <= 0):
            raise BreakoutModelError("M1 training feature scale is zero or non-finite")
        standardized = (data.features - mean) / scale
        x = np.column_stack((np.ones(len(standardized)), standardized))
        weights = np.zeros((x.shape[1], 3), dtype=np.float64)
        current = self._loss(x, data.labels, weights)
        converged = False
        for iteration in range(self.max_iter):
            probabilities = self._softmax(x @ weights)
            target = np.eye(3, dtype=np.float64)[data.labels]
            gradient = x.T @ (probabilities - target) / len(x)
            gradient[1:] += self.l2 * weights[1:]
            if float(np.linalg.norm(gradient)) <= self.tolerance:
                converged = True
                break
            step = 1.0 / math.sqrt(iteration + 1.0)
            accepted = False
            for _ in range(25):
                candidate = weights - step * gradient
                loss = self._loss(x, data.labels, candidate)
                if loss <= current:
                    accepted = True
                    break
                step *= 0.5
            if not accepted:
                raise BreakoutModelError("M1 line search failed")
            change = abs(current - loss)
            weights = candidate
            current = loss
            if change < self.tolerance:
                converged = True
                break
        if not converged:
            raise BreakoutModelError("M1 did not converge within max_iter")
        if not np.isfinite(weights).all():
            raise BreakoutModelError("M1 fit produced non-finite weights")
        self.mean_, self.scale_, self.weights_ = mean, scale, weights
        return self

    def predict_hazards(self, static_features: Sequence[float]) -> np.ndarray:
        if self.mean_ is None or self.scale_ is None or self.weights_ is None:
            raise BreakoutModelError("M1 is not fitted")
        if len(static_features) != len(PRIMARY_STATIC_FEATURES):
            raise BreakoutModelError("wrong static feature count")
        rows = np.asarray(
            [tuple(float(value) for value in static_features) + age_basis(hour) for hour in range(1, MAX_HOURS + 1)],
            dtype=np.float64,
        )
        x = np.column_stack((np.ones(MAX_HOURS), (rows - self.mean_) / self.scale_))
        probabilities = self._softmax(x @ self.weights_)
        validate_hazards(probabilities)
        return probabilities


class SklearnHistogramHazard:
    """Pinned scikit-learn histogram-gradient hazard adapter (M2)."""

    def __init__(self, **parameters: Any) -> None:
        self.parameters = dict(parameters)
        self.model: Any | None = None

    def fit(self, episodes: Sequence[FollowthroughEpisode]) -> "SklearnHistogramHazard":
        try:
            from sklearn.ensemble import HistGradientBoostingClassifier
        except ImportError as exc:
            raise BreakoutModelError("qualified scikit-learn is unavailable") from exc
        data = make_person_period(episodes)
        model = HistGradientBoostingClassifier(
            early_stopping=False,
            max_bins=64,
            max_iter=150,
            min_samples_leaf=50,
            random_state=20260901,
            **self.parameters,
        )
        model.fit(data.features, data.labels)
        if tuple(model.classes_) != (0, 1, 2):
            raise BreakoutModelError("M2 training lacks a required class")
        self.model = model
        return self

    def predict_hazards(self, static_features: Sequence[float]) -> np.ndarray:
        if self.model is None:
            raise BreakoutModelError("M2 is not fitted")
        rows = np.asarray(
            [tuple(float(value) for value in static_features) + age_basis(hour) for hour in range(1, MAX_HOURS + 1)]
        )
        probabilities = np.asarray(self.model.predict_proba(rows), dtype=np.float64)
        validate_hazards(probabilities)
        return probabilities


class XGBoostHazard:
    """Pinned CPU-only XGBoost hazard adapter (M3)."""

    def __init__(self, **parameters: Any) -> None:
        self.parameters = dict(parameters)
        self.model: Any | None = None

    def fit(self, episodes: Sequence[FollowthroughEpisode]) -> "XGBoostHazard":
        try:
            from xgboost import XGBClassifier
        except ImportError as exc:
            raise BreakoutModelError("qualified xgboost-cpu is unavailable") from exc
        data = make_person_period(episodes)
        if set(np.unique(data.labels)) != {0, 1, 2}:
            raise BreakoutModelError("M3 training lacks a required class")
        model = XGBClassifier(
            colsample_bytree=1.0,
            device="cpu",
            min_child_weight=20,
            n_estimators=150,
            n_jobs=1,
            objective="multi:softprob",
            random_state=20260901,
            subsample=1.0,
            tree_method="hist",
            **self.parameters,
        )
        model.fit(data.features, data.labels)
        self.model = model
        return self

    def predict_hazards(self, static_features: Sequence[float]) -> np.ndarray:
        if self.model is None:
            raise BreakoutModelError("M3 is not fitted")
        rows = np.asarray(
            [tuple(float(value) for value in static_features) + age_basis(hour) for hour in range(1, MAX_HOURS + 1)]
        )
        probabilities = np.asarray(self.model.predict_proba(rows), dtype=np.float64)
        validate_hazards(probabilities)
        return probabilities


def validate_hazards(probabilities: np.ndarray) -> None:
    if probabilities.shape != (MAX_HOURS, 3):
        raise BreakoutModelError("hazard matrix must be 168 by 3")
    if not np.isfinite(probabilities).all() or np.any(probabilities < 0):
        raise BreakoutModelError("hazard probabilities must be finite and nonnegative")
    if not np.allclose(probabilities.sum(axis=1), 1.0, atol=1e-10, rtol=0):
        raise BreakoutModelError("hazard probabilities must sum to one")


def apply_temperature(probabilities: np.ndarray, temperature: float) -> np.ndarray:
    validate_hazards(probabilities)
    if temperature <= 0 or not math.isfinite(temperature):
        raise BreakoutModelError("temperature must be positive")
    logits = np.log(np.maximum(probabilities, 1e-15)) / temperature
    logits -= logits.max(axis=1, keepdims=True)
    calibrated = np.exp(logits)
    calibrated /= calibrated.sum(axis=1, keepdims=True)
    validate_hazards(calibrated)
    return calibrated


def hazards_to_curves(probabilities: np.ndarray) -> np.ndarray:
    """Return columns [continuation CIF, re-entry CIF, event-free survival]."""

    validate_hazards(probabilities)
    curves = np.zeros((MAX_HOURS, 3), dtype=np.float64)
    survival = 1.0
    continuation = 0.0
    reentry = 0.0
    for index, row in enumerate(probabilities):
        continuation += survival * row[1]
        reentry += survival * row[2]
        survival *= row[0]
        curves[index] = (continuation, reentry, survival)
    if np.any(np.diff(curves[:, 0]) < -1e-12) or np.any(np.diff(curves[:, 1]) < -1e-12):
        raise BreakoutModelError("cumulative incidence must be non-decreasing")
    if np.any(np.diff(curves[:, 2]) > 1e-12):
        raise BreakoutModelError("survival must be non-increasing")
    if not np.allclose(curves.sum(axis=1), 1.0, atol=1e-10, rtol=0):
        raise BreakoutModelError("risk curves must remain on the simplex")
    return curves


def censor_survival(episodes: Sequence[FollowthroughEpisode]) -> np.ndarray:
    """Training-only Kaplan-Meier survival for early segment censoring."""

    survival = np.ones(MAX_HOURS, dtype=np.float64)
    current = 1.0
    for hour in range(1, MAX_HOURS + 1):
        # Left-continuous G(h-): a path observed through hour h contributes at h.
        survival[hour - 1] = current
        at_risk = sum(ep.observed_hours >= hour for ep in episodes)
        censored = sum(
            ep.segment_censored and ep.event_type is None and ep.observed_hours == hour
            for ep in episodes
        )
        if at_risk:
            current *= 1.0 - censored / at_risk
    return survival


def validate_curves(curves: np.ndarray) -> None:
    if curves.shape != (MAX_HOURS, 3):
        raise BreakoutModelError("risk curves must be 168 by 3")
    if not np.isfinite(curves).all() or np.any(curves < 0):
        raise BreakoutModelError("risk curves must be finite and nonnegative")
    if not np.allclose(curves.sum(axis=1), 1.0, atol=1e-10, rtol=0):
        raise BreakoutModelError("risk curves must remain on the simplex")
    if np.any(np.diff(curves[:, 0]) < -1e-12) or np.any(np.diff(curves[:, 1]) < -1e-12):
        raise BreakoutModelError("cumulative incidence must be non-decreasing")
    if np.any(np.diff(curves[:, 2]) > 1e-12):
        raise BreakoutModelError("survival must be non-increasing")


def integrated_brier_score(
    training_episodes: Sequence[FollowthroughEpisode],
    evaluation_episodes: Sequence[FollowthroughEpisode],
    predicted_curves: Mapping[str, np.ndarray],
) -> float:
    """IPCW integrated three-state competing-risk Brier score over hours 1..168."""

    if not training_episodes or not evaluation_episodes:
        raise BreakoutModelError("IBS needs non-empty train and evaluation episodes")
    train_ids = [item.episode_id for item in training_episodes]
    eval_ids = [item.episode_id for item in evaluation_episodes]
    if len(train_ids) != len(set(train_ids)) or len(eval_ids) != len(set(eval_ids)):
        raise BreakoutModelError("IBS episode IDs must be unique")
    if set(train_ids) & set(eval_ids):
        raise BreakoutModelError("IBS training and evaluation episodes must be disjoint")
    censor_km = censor_survival(training_episodes)
    if np.any(censor_km <= 0.05):
        raise BreakoutModelError("training censor survival is at or below frozen 5pct support")
    for episode in evaluation_episodes:
        curves = predicted_curves.get(episode.episode_id)
        if curves is None:
            raise BreakoutModelError("missing episode risk curve")
        validate_curves(curves)
    losses: list[float] = []
    for hour in range(1, MAX_HOURS + 1):
        weighted_loss = 0.0
        weight_total = 0.0
        for episode in evaluation_episodes:
            curves = predicted_curves.get(episode.episode_id)
            if curves is None:
                raise BreakoutModelError("missing episode risk curve")
            if episode.event_hour is not None and episode.event_hour <= hour:
                target = np.zeros(3)
                target[int(episode.event_class) - 1] = 1.0
                weight = 1.0 / censor_km[episode.event_hour - 1]
            elif episode.observed_hours >= hour:
                target = np.array((0.0, 0.0, 1.0))
                weight = 1.0 / censor_km[hour - 1]
            else:
                continue
            weighted_loss += weight * float(np.sum((curves[hour - 1] - target) ** 2))
            weight_total += weight
        if weight_total:
            losses.append(weighted_loss / weight_total)
    if len(losses) != MAX_HOURS:
        raise BreakoutModelError("evaluation lacks observable support across the full 168h grid")
    return float(np.mean(losses))


def episode_brier_contributions(
    training_episodes: Sequence[FollowthroughEpisode],
    evaluation_episodes: Sequence[FollowthroughEpisode],
    predicted_curves: Mapping[str, np.ndarray],
) -> dict[str, float]:
    """Return paired episode-level time-mean IPCW losses using one frozen training KM."""

    censor_km = censor_survival(training_episodes)
    if np.any(censor_km <= 0.05):
        raise BreakoutModelError("training censor survival is at or below frozen 5pct support")
    eval_ids = [episode.episode_id for episode in evaluation_episodes]
    if len(eval_ids) != len(set(eval_ids)):
        raise BreakoutModelError("evaluation episode IDs must be unique")
    weights_by_hour: list[dict[str, tuple[float, np.ndarray]]] = []
    for hour in range(1, MAX_HOURS + 1):
        entries: dict[str, tuple[float, np.ndarray]] = {}
        for episode in evaluation_episodes:
            if episode.event_hour is not None and episode.event_hour <= hour:
                target = np.zeros(3)
                target[int(episode.event_class) - 1] = 1.0
                weight = 1.0 / censor_km[episode.event_hour - 1]
            elif episode.observed_hours >= hour:
                target = np.array((0.0, 0.0, 1.0))
                weight = 1.0 / censor_km[hour - 1]
            else:
                continue
            entries[episode.episode_id] = (weight, target)
        if not entries:
            raise BreakoutModelError("evaluation lacks full 168h Brier support")
        weights_by_hour.append(entries)
    output: dict[str, float] = {}
    count = len(evaluation_episodes)
    for episode in evaluation_episodes:
        curves = predicted_curves.get(episode.episode_id)
        if curves is None:
            raise BreakoutModelError("missing episode risk curve")
        validate_curves(curves)
        hourly = []
        for hour, entries in enumerate(weights_by_hour, start=1):
            if episode.episode_id not in entries:
                hourly.append(0.0)
                continue
            weight, target = entries[episode.episode_id]
            denominator = sum(item[0] for item in entries.values())
            hourly.append(
                count
                * weight
                * float(np.sum((curves[hour - 1] - target) ** 2))
                / denominator
            )
        output[episode.episode_id] = float(np.mean(hourly))
    return output


def paired_month_block_interval(
    episode_differences: Mapping[str, tuple[str, float]],
    *,
    replications: int = 2000,
    seed: int = 20260901,
) -> tuple[float, float, float]:
    """Resample contiguous calendar-month blocks while keeping whole episode IDs."""

    if replications <= 0 or not episode_differences:
        raise BreakoutModelError("bootstrap requires observations and replications")
    by_month: dict[str, list[float]] = {}
    for episode_id, (month, difference) in episode_differences.items():
        if not episode_id or len(month) != 7 or not math.isfinite(difference):
            raise BreakoutModelError("invalid bootstrap episode")
        by_month.setdefault(month, []).append(float(difference))
    first = datetime.strptime(min(by_month), "%Y-%m").replace(tzinfo=timezone.utc)
    last = datetime.strptime(max(by_month), "%Y-%m").replace(tzinfo=timezone.utc)
    months: list[str] = []
    cursor = first
    while cursor <= last:
        months.append(cursor.strftime("%Y-%m"))
        cursor = datetime(
            cursor.year + (1 if cursor.month == 12 else 0),
            1 if cursor.month == 12 else cursor.month + 1,
            1,
            tzinfo=timezone.utc,
        )
    block_length = 3
    if len(months) < block_length:
        raise BreakoutModelError("bootstrap needs at least three complete calendar months")
    observed = [value for month in months for value in by_month.get(month, ())]
    rng = np.random.default_rng(seed)
    replicates: list[float] = []
    starts = len(months) - block_length + 1
    for _ in range(replications):
        sampled_months: list[str] = []
        while len(sampled_months) < len(months):
            start = int(rng.integers(0, starts))
            sampled_months.extend(months[start : start + block_length])
        sampled = [
            value
            for month in sampled_months[: len(months)]
            for value in by_month.get(month, ())
        ]
        if sampled:
            replicates.append(float(np.mean(sampled)))
    if len(replicates) < max(1, int(replications * 0.95)):
        raise BreakoutModelError("insufficient valid month-block bootstrap replications")
    replicate_array = np.asarray(replicates)
    return (
        float(np.mean(observed)),
        float(np.quantile(replicate_array, 0.025, method="linear")),
        float(np.quantile(replicate_array, 0.975, method="linear")),
    )


def predict_episode_curves(
    model: HazardModel, episodes: Iterable[FollowthroughEpisode], temperature: float = 1.0
) -> dict[str, np.ndarray]:
    output: dict[str, np.ndarray] = {}
    for episode in episodes:
        probabilities = model.predict_hazards(episode.features)
        output[episode.episode_id] = hazards_to_curves(
            apply_temperature(probabilities, temperature)
        )
    return output
