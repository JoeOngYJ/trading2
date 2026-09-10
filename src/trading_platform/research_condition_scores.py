"""Synthetic-safe contracts and primitives for market-condition scores.

This module performs no I/O and has no strategy or execution integration.  Mathematical
primitives are descriptive transforms; they do not become forecasts until a separately
frozen chronological experiment validates them against a future target.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from trading_platform.research_market_conditions import (
    CONDITION_AXES,
    MarketConditionError,
    MarketConditionObservation,
    validate_observation_sequence,
)


SCORE_KINDS = frozenset({"continuous", "probability"})
EVIDENCE_STATUSES = frozenset({"accepted", "benchmark", "development", "rejected"})
CONDITIONING_EVIDENCE = frozenset({"accepted", "benchmark"})
DAYS_PER_YEAR = 365.2425


class ConditionScoreError(ValueError):
    """Raised when a score or primitive cannot be evaluated safely."""


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConditionScoreError(f"{label} must be a non-empty string")
    return value.strip()


def _utc(value: datetime, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ConditionScoreError(f"{label} must be timezone-aware UTC")
    if value.utcoffset() != timedelta(0):
        raise ConditionScoreError(f"{label} must use UTC")
    return value


def _iso(value: datetime) -> str:
    return _utc(value, "timestamp").isoformat().replace("+00:00", "Z")


def _finite(value: float, label: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ConditionScoreError(f"{label} must be finite")
    return number


def _fraction(value: float, label: str) -> float:
    number = _finite(value, label)
    if not 0 <= number <= 1:
        raise ConditionScoreError(f"{label} must be within [0, 1]")
    return number


def _digest(value: str, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or value.lower() != value:
        raise ConditionScoreError(f"{label} must be a lowercase SHA-256 digest")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ConditionScoreError(f"{label} must be hexadecimal") from exc
    return value


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _frozen_digests(values: Mapping[str, str], label: str) -> Mapping[str, str]:
    if not values:
        raise ConditionScoreError(f"{label} cannot be empty")
    normalized: dict[str, str] = {}
    for raw_key, raw_value in values.items():
        key = _text(raw_key, f"{label} key")
        if key in normalized:
            raise ConditionScoreError(f"{label} contains duplicate key: {key}")
        normalized[key] = _digest(raw_value, f"{label}[{key}]")
    return MappingProxyType(dict(sorted(normalized.items())))


def _series(values: Sequence[float], label: str, minimum: int) -> tuple[float, ...]:
    normalized = tuple(_finite(value, f"{label}[{index}]") for index, value in enumerate(values))
    if len(normalized) < minimum:
        raise ConditionScoreError(f"{label} requires at least {minimum} observations")
    return normalized


@dataclass(frozen=True, slots=True)
class MarketConditionScore:
    """One target-specific forecast with no action mapping."""

    score_id: str
    score_version: str
    instrument: str
    venue: str
    axis: str
    score_kind: str
    horizon_seconds: int
    fit_cutoff: datetime
    observed_at: datetime
    available_at: datetime
    expires_at: datetime
    units: str
    point_estimate: float | None
    lower_bound: float | None
    upper_bound: float | None
    confidence: float
    evidence_status: str
    lineage_digests: Mapping[str, str]
    unknown_reason: str | None = None

    def __post_init__(self) -> None:
        for name in ("score_id", "score_version", "instrument", "venue", "units"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if self.axis not in CONDITION_AXES:
            raise ConditionScoreError(f"unsupported score axis: {self.axis}")
        if self.score_kind not in SCORE_KINDS:
            raise ConditionScoreError(f"unsupported score kind: {self.score_kind}")
        if not isinstance(self.horizon_seconds, int) or self.horizon_seconds <= 0:
            raise ConditionScoreError("horizon_seconds must be a positive integer")
        cutoff = _utc(self.fit_cutoff, "fit_cutoff")
        observed = _utc(self.observed_at, "observed_at")
        available = _utc(self.available_at, "available_at")
        expires = _utc(self.expires_at, "expires_at")
        if cutoff > observed or observed > available or available >= expires:
            raise ConditionScoreError(
                "timestamps must satisfy fit_cutoff <= observed_at <= available_at < expires_at"
            )
        object.__setattr__(self, "confidence", _fraction(self.confidence, "confidence"))
        if self.evidence_status not in EVIDENCE_STATUSES:
            raise ConditionScoreError(f"unsupported evidence status: {self.evidence_status}")
        object.__setattr__(
            self, "lineage_digests", _frozen_digests(self.lineage_digests, "lineage_digests")
        )
        estimates = (self.point_estimate, self.lower_bound, self.upper_bound)
        if self.unknown_reason is None:
            if any(value is None for value in estimates):
                raise ConditionScoreError("known score requires point and interval estimates")
            point, lower, upper = (
                _finite(value, "score estimate") for value in estimates  # type: ignore[arg-type]
            )
            if lower > point or point > upper:
                raise ConditionScoreError("score interval must contain the point estimate")
            if self.score_kind == "probability" and not (
                0 <= lower <= point <= upper <= 1
            ):
                raise ConditionScoreError("probability score estimates must be within [0, 1]")
            object.__setattr__(self, "point_estimate", point)
            object.__setattr__(self, "lower_bound", lower)
            object.__setattr__(self, "upper_bound", upper)
        else:
            object.__setattr__(self, "unknown_reason", _text(self.unknown_reason, "unknown_reason"))
            if any(value is not None for value in estimates):
                raise ConditionScoreError("unknown score cannot contain numeric estimates")

    def available_for_research(self, decision_at: datetime) -> bool:
        decision = _utc(decision_at, "decision_at")
        return (
            self.unknown_reason is None
            and self.available_at <= decision < self.expires_at
        )

    def eligible_for_conditioning(self, decision_at: datetime) -> bool:
        return self.available_for_research(decision_at) and self.evidence_status in CONDITIONING_EVIDENCE

    def _payload(self) -> dict[str, Any]:
        return {
            "available_at": _iso(self.available_at),
            "axis": self.axis,
            "confidence": self.confidence,
            "evidence_status": self.evidence_status,
            "expires_at": _iso(self.expires_at),
            "fit_cutoff": _iso(self.fit_cutoff),
            "horizon_seconds": self.horizon_seconds,
            "instrument": self.instrument,
            "lineage_digests": dict(self.lineage_digests),
            "lower_bound": self.lower_bound,
            "observed_at": _iso(self.observed_at),
            "point_estimate": self.point_estimate,
            "score_id": self.score_id,
            "score_kind": self.score_kind,
            "score_version": self.score_version,
            "units": self.units,
            "unknown_reason": self.unknown_reason,
            "upper_bound": self.upper_bound,
            "venue": self.venue,
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self._payload())

    def as_dict(self) -> dict[str, Any]:
        return {**self._payload(), "digest": self.digest}


@dataclass(frozen=True, slots=True)
class MarketConditionScorePanel:
    """A deterministic collection that deliberately exposes no aggregate score."""

    decision_at: datetime
    scores: Sequence[MarketConditionScore]

    def __post_init__(self) -> None:
        decision = _utc(self.decision_at, "decision_at")
        identities: set[tuple[str, str, int]] = set()
        for score in self.scores:
            identity = (score.score_id, score.axis, score.horizon_seconds)
            if identity in identities:
                raise ConditionScoreError("score panel contains a duplicate score/axis/horizon")
            if score.available_at > decision:
                raise ConditionScoreError("score panel contains a future-dependent score")
            identities.add(identity)
        object.__setattr__(
            self,
            "scores",
            tuple(
                sorted(
                    self.scores,
                    key=lambda score: (score.axis, score.horizon_seconds, score.score_id),
                )
            ),
        )

    def _payload(self) -> dict[str, Any]:
        return {
            "decision_at": _iso(self.decision_at),
            "score_digests": [score.digest for score in self.scores],
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self._payload())

    def as_dict(self) -> dict[str, Any]:
        return {**self._payload(), "digest": self.digest}


def completed_field_values(
    observations: Sequence[MarketConditionObservation],
    *,
    field_name: str,
    decision_at: datetime,
    minimum: int = 1,
) -> tuple[float, ...]:
    """Extract one field only after every observation was available to the decision."""

    field = _text(field_name, "field_name")
    if not isinstance(minimum, int) or minimum <= 0:
        raise ConditionScoreError("minimum must be a positive integer")
    try:
        checked = validate_observation_sequence(observations, require_single_segment=True)
    except MarketConditionError as exc:
        raise ConditionScoreError(str(exc)) from exc
    decision = _utc(decision_at, "decision_at")
    values: list[float] = []
    for observation in checked:
        if not observation.available_for(decision):
            reason = observation.unknown_reason or "future_availability"
            raise ConditionScoreError(f"observation is not causally available: {reason}")
        if field not in observation.field_values:
            raise ConditionScoreError(f"observation is missing field: {field}")
        values.append(observation.field_values[field])
    return _series(values, field, minimum)


def volatility_scaled_return(returns: Sequence[float]) -> float:
    values = _series(returns, "returns", 2)
    denominator = math.sqrt(sum(value * value for value in values))
    if denominator == 0:
        raise ConditionScoreError("volatility-scaled return requires non-zero variation")
    return sum(values) / denominator


def directional_efficiency(returns: Sequence[float]) -> float:
    values = _series(returns, "returns", 2)
    path_length = sum(abs(value) for value in values)
    if path_length == 0:
        raise ConditionScoreError("directional efficiency requires a non-zero path")
    return abs(sum(values)) / path_length


def lag_one_autocovariance(returns: Sequence[float]) -> float:
    values = _series(returns, "returns", 3)
    mean = sum(values) / len(values)
    return sum(
        (values[index] - mean) * (values[index - 1] - mean)
        for index in range(1, len(values))
    ) / (len(values) - 1)


def overlapping_variance_ratio(returns: Sequence[float], aggregation_horizon: int) -> float:
    if not isinstance(aggregation_horizon, int) or aggregation_horizon < 2:
        raise ConditionScoreError("aggregation_horizon must be an integer of at least two")
    values = _series(returns, "returns", aggregation_horizon + 2)
    one_mean = sum(values) / len(values)
    one_variance = sum((value - one_mean) ** 2 for value in values) / len(values)
    if one_variance == 0:
        raise ConditionScoreError("variance ratio requires non-zero one-period variance")
    aggregated = tuple(
        sum(values[index : index + aggregation_horizon])
        for index in range(len(values) - aggregation_horizon + 1)
    )
    aggregated_mean = aggregation_horizon * one_mean
    aggregated_variance = sum(
        (value - aggregated_mean) ** 2 for value in aggregated
    ) / len(aggregated)
    return aggregated_variance / (aggregation_horizon * one_variance)


def standardized_displacement(reference_values: Sequence[float], current_value: float) -> float:
    reference = _series(reference_values, "reference_values", 2)
    current = _finite(current_value, "current_value")
    mean = sum(reference) / len(reference)
    variance = sum((value - mean) ** 2 for value in reference) / (len(reference) - 1)
    if variance == 0:
        raise ConditionScoreError("standardized displacement requires non-zero reference variance")
    return (current - mean) / math.sqrt(variance)


@dataclass(frozen=True, slots=True)
class RealizedVariationComponents:
    realized_variance: float
    positive_semivariance: float
    negative_semivariance: float
    bipower_variation: float
    nonnegative_jump_variation: float
    jump_share: float

    def as_dict(self) -> dict[str, float]:
        return {
            "bipower_variation": self.bipower_variation,
            "jump_share": self.jump_share,
            "negative_semivariance": self.negative_semivariance,
            "nonnegative_jump_variation": self.nonnegative_jump_variation,
            "positive_semivariance": self.positive_semivariance,
            "realized_variance": self.realized_variance,
        }


def realized_variation_components(returns: Sequence[float]) -> RealizedVariationComponents:
    values = _series(returns, "returns", 2)
    realized = sum(value * value for value in values)
    positive = sum(value * value for value in values if value > 0)
    negative = sum(value * value for value in values if value < 0)
    adjacent_products = sum(
        abs(values[index - 1]) * abs(values[index]) for index in range(1, len(values))
    )
    bipower = (math.pi / 2) * (len(values) / (len(values) - 1)) * adjacent_products
    jump = max(realized - bipower, 0.0)
    share = jump / realized if realized > 0 else 0.0
    return RealizedVariationComponents(realized, positive, negative, bipower, jump, share)


def mean_amihud_price_impact_proxy(
    returns: Sequence[float], quote_volumes: Sequence[float]
) -> float:
    values = _series(returns, "returns", 1)
    volumes = _series(quote_volumes, "quote_volumes", 1)
    if len(values) != len(volumes):
        raise ConditionScoreError("returns and quote_volumes must have equal length")
    if any(volume <= 0 for volume in volumes):
        raise ConditionScoreError("quote volumes must be strictly positive")
    return sum(abs(value) / volume for value, volume in zip(values, volumes, strict=True)) / len(values)


def corwin_schultz_high_low_spread_proxy(
    first_high: float,
    first_low: float,
    second_high: float,
    second_low: float,
) -> float:
    high_1 = _finite(first_high, "first_high")
    low_1 = _finite(first_low, "first_low")
    high_2 = _finite(second_high, "second_high")
    low_2 = _finite(second_low, "second_low")
    if low_1 <= 0 or low_2 <= 0 or high_1 < low_1 or high_2 < low_2:
        raise ConditionScoreError("high-low proxy requires positive highs not below lows")
    log_range_1 = math.log(high_1 / low_1)
    log_range_2 = math.log(high_2 / low_2)
    beta = log_range_1**2 + log_range_2**2
    gamma = math.log(max(high_1, high_2) / min(low_1, low_2)) ** 2
    denominator = 3 - 2 * math.sqrt(2)
    alpha = (
        (math.sqrt(2 * beta) - math.sqrt(beta)) / denominator
        - math.sqrt(gamma / denominator)
    )
    alpha = max(alpha, 0.0)
    exponential = math.exp(alpha)
    return 2 * (exponential - 1) / (1 + exponential)


def annualized_completed_funding(
    completed_funding_rates: Sequence[float], *, interval_hours: float = 8
) -> float:
    rates = _series(completed_funding_rates, "completed_funding_rates", 1)
    hours = _finite(interval_hours, "interval_hours")
    if hours <= 0:
        raise ConditionScoreError("interval_hours must be strictly positive")
    return (sum(rates) / len(rates)) * (24 / hours) * DAYS_PER_YEAR


def completed_short_perpetual_funding(completed_funding_rates: Sequence[float]) -> float:
    return sum(_series(completed_funding_rates, "completed_funding_rates", 1))


def perpetual_basis_fraction(*, spot_price: float, perpetual_price: float) -> float:
    spot = _finite(spot_price, "spot_price")
    perpetual = _finite(perpetual_price, "perpetual_price")
    if spot <= 0 or perpetual <= 0:
        raise ConditionScoreError("spot and perpetual prices must be strictly positive")
    return perpetual / spot - 1
