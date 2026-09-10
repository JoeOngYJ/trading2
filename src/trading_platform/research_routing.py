"""Offline-only contracts for counterfactual regime and strategy-arm research.

This module intentionally depends only on the Python standard library.  It has no adapter
to runtime signals, order intents, databases, message buses, exchanges, or position state.
S0 routing is descriptive: every :class:`RoutingDecision` is forced to ``no_trade``.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable


class ResearchRoutingError(ValueError):
    """Raised when an offline research contract cannot be validated safely."""


class EvidenceStatus(str, Enum):
    ELIGIBLE = "eligible"
    DEVELOPMENT = "development"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


COUNTERFACTUAL_STATUSES = frozenset(
    {EvidenceStatus.ELIGIBLE, EvidenceStatus.DEVELOPMENT, EvidenceStatus.ACCEPTED}
)
ACTIONABLE_ARM_ID = "no_trade"
COUNTERFACTUAL_DISPOSITION = "counterfactual_only"


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ResearchRoutingError(f"{label} must be a non-empty string")
    return value.strip()


def _utc(value: datetime, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ResearchRoutingError(f"{label} must be timezone-aware UTC")
    if value.utcoffset() != timedelta(0):
        raise ResearchRoutingError(f"{label} must use UTC, not a non-zero offset")
    return value


def _iso(value: datetime) -> str:
    return _utc(value, "timestamp").isoformat().replace("+00:00", "Z")


def _digest(value: str, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ResearchRoutingError(f"{label} must be a 64-character SHA-256 digest")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ResearchRoutingError(f"{label} must be hexadecimal") from exc
    if value != value.lower():
        raise ResearchRoutingError(f"{label} must use lowercase hexadecimal")
    return value


def _finite(value: float, label: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ResearchRoutingError(f"{label} must be finite")
    return number


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def canonical_digest(value: Any) -> str:
    """Return the SHA-256 of compact, key-sorted UTF-8 JSON."""

    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _frozen_values(
    values: Mapping[str, float] | Sequence[tuple[str, float]], label: str
) -> Mapping[str, float]:
    items = list(values.items()) if isinstance(values, Mapping) else list(values)
    if not items:
        raise ResearchRoutingError(f"{label} cannot be empty")
    normalized: dict[str, float] = {}
    for raw_key, raw_value in items:
        key = _text(raw_key, f"{label} key")
        if key in normalized:
            raise ResearchRoutingError(f"{label} contains duplicate key: {key}")
        normalized[key] = _finite(raw_value, f"{label}[{key}]")
    return MappingProxyType(dict(sorted(normalized.items())))


def _frozen_digests(values: Mapping[str, str], label: str) -> Mapping[str, str]:
    normalized: dict[str, str] = {}
    for raw_key, raw_value in values.items():
        key = _text(raw_key, f"{label} key")
        if key in normalized:
            raise ResearchRoutingError(f"{label} contains duplicate key: {key}")
        normalized[key] = _digest(raw_value, f"{label}[{key}]")
    return MappingProxyType(dict(sorted(normalized.items())))


@dataclass(frozen=True, slots=True)
class RegimeFeatureObservation:
    instrument: str
    interval: str
    segment: str
    observed_at: datetime
    available_at: datetime
    feature_values: Mapping[str, float] | Sequence[tuple[str, float]]
    source_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "instrument", _text(self.instrument, "instrument"))
        object.__setattr__(self, "interval", _text(self.interval, "interval"))
        object.__setattr__(self, "segment", _text(self.segment, "segment"))
        observed = _utc(self.observed_at, "observed_at")
        available = _utc(self.available_at, "available_at")
        if available < observed:
            raise ResearchRoutingError("available_at cannot precede observed_at")
        object.__setattr__(self, "source_digest", _digest(self.source_digest, "source_digest"))
        object.__setattr__(
            self, "feature_values", _frozen_values(self.feature_values, "feature_values")
        )

    def _payload(self) -> dict[str, Any]:
        return {
            "available_at": _iso(self.available_at),
            "feature_values": dict(self.feature_values),
            "instrument": self.instrument,
            "interval": self.interval,
            "observed_at": _iso(self.observed_at),
            "segment": self.segment,
            "source_digest": self.source_digest,
        }

    @property
    def feature_digest(self) -> str:
        return canonical_digest(self._payload())

    def as_dict(self) -> dict[str, Any]:
        return {**self._payload(), "feature_digest": self.feature_digest}


def validate_feature_sequence(
    observations: Sequence[RegimeFeatureObservation], *, require_single_segment: bool = True
) -> tuple[RegimeFeatureObservation, ...]:
    """Validate an ordered, causal observation slice without bridging source segments."""

    checked = tuple(observations)
    if not checked:
        raise ResearchRoutingError("feature observation sequence cannot be empty")
    first = checked[0]
    prior_available: datetime | None = None
    seen: set[tuple[str, datetime]] = set()
    for item in checked:
        if item.instrument != first.instrument or item.interval != first.interval:
            raise ResearchRoutingError("feature sequence changes instrument or interval")
        if require_single_segment and item.segment != first.segment:
            raise ResearchRoutingError("feature sequence crosses a source segment")
        identity = (item.segment, item.observed_at)
        if identity in seen:
            raise ResearchRoutingError("feature sequence contains a duplicate observation")
        if prior_available is not None and item.available_at <= prior_available:
            raise ResearchRoutingError("feature availability timestamps are not strictly increasing")
        seen.add(identity)
        prior_available = item.available_at
    return checked


@dataclass(frozen=True, slots=True)
class RegimeState:
    model_id: str
    model_version: str
    instrument: str
    interval: str
    segment: str
    observed_at: datetime
    available_at: datetime
    fit_cutoff: datetime
    probabilities: Mapping[str, float] | Sequence[tuple[str, float]]
    confidence: float
    entropy: float
    state_age: int
    transition_probability: float
    transition_reason: str
    cutoffs: Mapping[str, float] | Sequence[tuple[str, float]]
    stale_reason: str | None = None
    unknown_reason: str | None = None

    def __post_init__(self) -> None:
        for name in ("model_id", "model_version", "instrument", "interval", "segment"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        observed = _utc(self.observed_at, "observed_at")
        available = _utc(self.available_at, "available_at")
        cutoff = _utc(self.fit_cutoff, "fit_cutoff")
        if cutoff > observed or observed > available:
            raise ResearchRoutingError("regime timestamps must satisfy fit_cutoff <= observed_at <= available_at")
        probabilities = _frozen_values(self.probabilities, "probabilities")
        if any(value < 0 or value > 1 for value in probabilities.values()):
            raise ResearchRoutingError("state probabilities must be within [0, 1]")
        if not math.isclose(sum(probabilities.values()), 1.0, rel_tol=0, abs_tol=1e-12):
            raise ResearchRoutingError("state probabilities must sum to one")
        object.__setattr__(self, "probabilities", probabilities)
        confidence = _finite(self.confidence, "confidence")
        transition = _finite(self.transition_probability, "transition_probability")
        entropy = _finite(self.entropy, "entropy")
        if not 0 <= confidence <= 1 or not 0 <= transition <= 1 or entropy < 0:
            raise ResearchRoutingError("invalid confidence, transition probability, or entropy")
        if not isinstance(self.state_age, int) or self.state_age < 0:
            raise ResearchRoutingError("state_age must be a non-negative integer")
        object.__setattr__(self, "transition_reason", _text(self.transition_reason, "transition_reason"))
        object.__setattr__(self, "cutoffs", _frozen_values(self.cutoffs, "cutoffs"))
        if self.stale_reason is not None:
            object.__setattr__(self, "stale_reason", _text(self.stale_reason, "stale_reason"))
        if self.unknown_reason is not None:
            object.__setattr__(self, "unknown_reason", _text(self.unknown_reason, "unknown_reason"))

    @property
    def is_usable(self) -> bool:
        return self.stale_reason is None and self.unknown_reason is None

    def _payload(self) -> dict[str, Any]:
        return {
            "available_at": _iso(self.available_at),
            "confidence": self.confidence,
            "cutoffs": dict(self.cutoffs),
            "entropy": self.entropy,
            "fit_cutoff": _iso(self.fit_cutoff),
            "instrument": self.instrument,
            "interval": self.interval,
            "model_id": self.model_id,
            "model_version": self.model_version,
            "observed_at": _iso(self.observed_at),
            "probabilities": dict(self.probabilities),
            "segment": self.segment,
            "stale_reason": self.stale_reason,
            "state_age": self.state_age,
            "transition_probability": self.transition_probability,
            "transition_reason": self.transition_reason,
            "unknown_reason": self.unknown_reason,
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self._payload())

    def as_dict(self) -> dict[str, Any]:
        return {**self._payload(), "digest": self.digest}


@dataclass(frozen=True, slots=True)
class StrategyArmSpec:
    arm_id: str
    version: str
    family: str
    direction: str
    horizon: str
    maximum_cost_bps: float
    capacity_fraction: float
    evidence_status: EvidenceStatus | str
    evidence_digest: str
    counterfactual_only: bool = True

    def __post_init__(self) -> None:
        for name in ("arm_id", "version", "family", "direction", "horizon"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        try:
            status = EvidenceStatus(self.evidence_status)
        except ValueError as exc:
            raise ResearchRoutingError(f"invalid evidence status: {self.evidence_status}") from exc
        object.__setattr__(self, "evidence_status", status)
        cost = _finite(self.maximum_cost_bps, "maximum_cost_bps")
        capacity = _finite(self.capacity_fraction, "capacity_fraction")
        if cost < 0 or not 0 <= capacity <= 1:
            raise ResearchRoutingError("cost must be non-negative and capacity must be within [0, 1]")
        object.__setattr__(self, "evidence_digest", _digest(self.evidence_digest, "evidence_digest"))
        if not self.counterfactual_only:
            raise ResearchRoutingError("S0 strategy arms must remain counterfactual_only")
        if self.arm_id == ACTIONABLE_ARM_ID:
            if status is not EvidenceStatus.ELIGIBLE or self.direction != "flat" or capacity != 0:
                raise ResearchRoutingError("no_trade must be eligible, flat, and have zero capacity")

    def as_dict(self) -> dict[str, Any]:
        return {
            "arm_id": self.arm_id,
            "capacity_fraction": self.capacity_fraction,
            "counterfactual_only": self.counterfactual_only,
            "direction": self.direction,
            "evidence_digest": self.evidence_digest,
            "evidence_status": self.evidence_status.value,
            "family": self.family,
            "horizon": self.horizon,
            "maximum_cost_bps": self.maximum_cost_bps,
            "version": self.version,
        }


@dataclass(frozen=True, slots=True)
class ArmForecast:
    arm_id: str
    arm_version: str
    decision_at: datetime
    available_at: datetime
    expires_at: datetime
    forecast_score: float
    confidence: float
    horizon: str
    abstention_reason: str | None
    lineage_digest: str

    def __post_init__(self) -> None:
        for name in ("arm_id", "arm_version", "horizon"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        decision = _utc(self.decision_at, "decision_at")
        available = _utc(self.available_at, "available_at")
        expires = _utc(self.expires_at, "expires_at")
        if available > decision:
            raise ResearchRoutingError("forecast is future-dependent at decision_at")
        if expires <= decision:
            raise ResearchRoutingError("forecast is stale at decision_at")
        object.__setattr__(self, "forecast_score", _finite(self.forecast_score, "forecast_score"))
        confidence = _finite(self.confidence, "confidence")
        if not 0 <= confidence <= 1:
            raise ResearchRoutingError("forecast confidence must be within [0, 1]")
        if self.abstention_reason is not None:
            object.__setattr__(
                self, "abstention_reason", _text(self.abstention_reason, "abstention_reason")
            )
        object.__setattr__(self, "lineage_digest", _digest(self.lineage_digest, "lineage_digest"))

    def as_dict(self) -> dict[str, Any]:
        return {
            "abstention_reason": self.abstention_reason,
            "arm_id": self.arm_id,
            "arm_version": self.arm_version,
            "available_at": _iso(self.available_at),
            "confidence": self.confidence,
            "decision_at": _iso(self.decision_at),
            "expires_at": _iso(self.expires_at),
            "forecast_score": self.forecast_score,
            "horizon": self.horizon,
            "lineage_digest": self.lineage_digest,
        }


@dataclass(frozen=True, slots=True)
class RoutingDecision:
    decision_at: datetime
    considered_arm_ids: tuple[str, ...]
    counterfactual_arm_id: str
    actionable_arm_id: str
    disposition: str
    reasons: tuple[str, ...]
    lineage_digests: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _utc(self.decision_at, "decision_at")
        if tuple(sorted(set(self.considered_arm_ids))) != self.considered_arm_ids:
            raise ResearchRoutingError("considered_arm_ids must be unique and sorted")
        if self.counterfactual_arm_id not in self.considered_arm_ids:
            raise ResearchRoutingError("counterfactual winner must be a considered arm")
        if self.actionable_arm_id != ACTIONABLE_ARM_ID:
            raise ResearchRoutingError("S0 actionable_arm_id is permanently fixed to no_trade")
        if self.disposition != COUNTERFACTUAL_DISPOSITION:
            raise ResearchRoutingError("S0 routing disposition must be counterfactual_only")
        if not self.reasons:
            raise ResearchRoutingError("routing decision must include at least one reason")
        object.__setattr__(self, "lineage_digests", _frozen_digests(self.lineage_digests, "lineage_digests"))

    def _payload(self) -> dict[str, Any]:
        return {
            "actionable_arm_id": self.actionable_arm_id,
            "considered_arm_ids": list(self.considered_arm_ids),
            "counterfactual_arm_id": self.counterfactual_arm_id,
            "decision_at": _iso(self.decision_at),
            "disposition": self.disposition,
            "lineage_digests": dict(self.lineage_digests),
            "reasons": list(self.reasons),
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self._payload())

    def as_dict(self) -> dict[str, Any]:
        return {**self._payload(), "digest": self.digest}


@runtime_checkable
class RegimeModel(Protocol):
    """Causal research model interface; S0 defines it but does not implement a model."""

    def fit(self, observations: Sequence[RegimeFeatureObservation], cutoff: datetime) -> None: ...

    def forward_filter(self, observation: RegimeFeatureObservation) -> RegimeState: ...

    def snapshot(self) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class StrategyArmRegistry:
    registry_id: str
    arms: tuple[StrategyArmSpec, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "registry_id", _text(self.registry_id, "registry_id"))
        ordered = tuple(sorted(self.arms, key=lambda item: item.arm_id))
        ids = [item.arm_id for item in ordered]
        if len(ids) != len(set(ids)):
            raise ResearchRoutingError("strategy arm IDs must be unique")
        if ACTIONABLE_ARM_ID not in ids:
            raise ResearchRoutingError("strategy arm registry must contain no_trade")
        object.__setattr__(self, "arms", ordered)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "StrategyArmRegistry":
        if payload.get("schema_version") != "strategy-arm-registry-v1":
            raise ResearchRoutingError("unsupported strategy arm registry schema")
        arms = tuple(StrategyArmSpec(**raw) for raw in payload.get("arms", ()))
        return cls(registry_id=str(payload.get("registry_id", "")), arms=arms)

    def arm(self, arm_id: str) -> StrategyArmSpec:
        matches = [arm for arm in self.arms if arm.arm_id == arm_id]
        if not matches:
            raise ResearchRoutingError(f"forecast references an unregistered arm: {arm_id}")
        return matches[0]

    @property
    def counterfactual_arm_ids(self) -> tuple[str, ...]:
        return tuple(
            arm.arm_id for arm in self.arms if arm.evidence_status in COUNTERFACTUAL_STATUSES
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "arms": [arm.as_dict() for arm in self.arms],
            "registry_id": self.registry_id,
            "schema_version": "strategy-arm-registry-v1",
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class CounterfactualRouter:
    registry: StrategyArmRegistry

    def route(
        self,
        decision_at: datetime,
        forecasts: Sequence[ArmForecast],
        *,
        regime_state: RegimeState | None = None,
    ) -> RoutingDecision:
        decision = _utc(decision_at, "decision_at")
        if regime_state is not None and regime_state.available_at > decision:
            raise ResearchRoutingError("regime state is future-dependent at decision_at")
        by_arm: dict[str, ArmForecast] = {}
        excluded_rejected: list[str] = []
        for forecast in forecasts:
            if forecast.decision_at != decision:
                raise ResearchRoutingError("all forecasts must share the routing decision timestamp")
            spec = self.registry.arm(forecast.arm_id)
            if forecast.arm_version != spec.version:
                raise ResearchRoutingError(f"forecast version mismatch for {forecast.arm_id}")
            if forecast.arm_id in by_arm:
                raise ResearchRoutingError(f"duplicate forecast for arm: {forecast.arm_id}")
            if spec.evidence_status is EvidenceStatus.REJECTED:
                excluded_rejected.append(forecast.arm_id)
                continue
            by_arm[forecast.arm_id] = forecast

        required = set(self.registry.counterfactual_arm_ids)
        missing = tuple(sorted(required - set(by_arm)))
        unusable_state = regime_state is not None and not regime_state.is_usable
        if missing or unusable_state:
            reasons = ["fail_closed"]
            if missing:
                reasons.append("missing_forecasts:" + ",".join(missing))
            if unusable_state:
                reasons.append("regime_state_unknown_or_stale")
            if excluded_rejected:
                reasons.append("rejected_arms_excluded:" + ",".join(sorted(excluded_rejected)))
            return RoutingDecision(
                decision_at=decision,
                considered_arm_ids=(ACTIONABLE_ARM_ID,),
                counterfactual_arm_id=ACTIONABLE_ARM_ID,
                actionable_arm_id=ACTIONABLE_ARM_ID,
                disposition=COUNTERFACTUAL_DISPOSITION,
                reasons=tuple(reasons),
                lineage_digests={
                    "arm_registry": self.registry.digest,
                    **({"regime_state": regime_state.digest} if regime_state is not None else {}),
                },
            )

        candidates = [forecast for forecast in by_arm.values() if forecast.abstention_reason is None]
        if not candidates:
            winner = by_arm[ACTIONABLE_ARM_ID]
            rank_reason = "all_non_flat_arms_abstained"
        else:
            winner = sorted(
                candidates,
                key=lambda item: (-item.forecast_score, -item.confidence, item.arm_id, item.arm_version),
            )[0]
            rank_reason = "deterministic_score_confidence_arm_id_ranking"
        reasons = [rank_reason, "actionable_route_locked_to_no_trade_in_s0"]
        if excluded_rejected:
            reasons.append("rejected_arms_excluded:" + ",".join(sorted(excluded_rejected)))
        lineage = {"arm_registry": self.registry.digest}
        lineage.update({f"forecast:{arm_id}": row.lineage_digest for arm_id, row in by_arm.items()})
        if regime_state is not None:
            lineage["regime_state"] = regime_state.digest
        return RoutingDecision(
            decision_at=decision,
            considered_arm_ids=tuple(sorted(by_arm)),
            counterfactual_arm_id=winner.arm_id,
            actionable_arm_id=ACTIONABLE_ARM_ID,
            disposition=COUNTERFACTUAL_DISPOSITION,
            reasons=tuple(reasons),
            lineage_digests=lineage,
        )
