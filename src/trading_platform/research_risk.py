"""Offline multidimensional BTC risk contracts and downward-only fusion.

This module is deliberately separate from the legacy single-model ``RegimeState`` and
from all production signal, execution, database, transport, and exchange code.  It maps
independently validated risk caps to a research-only allocation budget; it never creates
an order, position, directional forecast, or strategy decision.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Any, Mapping, Sequence


RISK_AXES = frozenset(
    {"volatility", "downside_tail", "jump_change", "implied_risk", "liquidity_execution"}
)
RISK_CLOCKS = frozenset({"daily", "4h"})
USABLE_EVIDENCE = frozenset({"benchmark", "accepted"})
ALL_EVIDENCE = frozenset({"benchmark", "accepted", "development", "rejected"})


class ResearchRiskError(ValueError):
    """Raised when a risk contract is invalid or cannot fail closed."""


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ResearchRiskError(f"{label} must be a non-empty string")
    return value.strip()


def _utc(value: datetime, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ResearchRiskError(f"{label} must be timezone-aware UTC")
    if value.utcoffset() != timedelta(0):
        raise ResearchRiskError(f"{label} must use UTC")
    return value


def _iso(value: datetime) -> str:
    return _utc(value, "timestamp").isoformat().replace("+00:00", "Z")


def _finite(value: float, label: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ResearchRiskError(f"{label} must be finite")
    return number


def _fraction(value: float, label: str) -> float:
    number = _finite(value, label)
    if not 0 <= number <= 1:
        raise ResearchRiskError(f"{label} must be within [0, 1]")
    return number


def _digest(value: str, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or value.lower() != value:
        raise ResearchRiskError(f"{label} must be a lowercase SHA-256 digest")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ResearchRiskError(f"{label} must be hexadecimal") from exc
    return value


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _frozen_digests(values: Mapping[str, str], label: str) -> Mapping[str, str]:
    normalized: dict[str, str] = {}
    for raw_key, raw_value in values.items():
        key = _text(raw_key, f"{label} key")
        if key in normalized:
            raise ResearchRiskError(f"duplicate {label} key: {key}")
        normalized[key] = _digest(raw_value, f"{label}[{key}]")
    if not normalized:
        raise ResearchRiskError(f"{label} cannot be empty")
    return MappingProxyType(dict(sorted(normalized.items())))


@dataclass(frozen=True, slots=True)
class RiskForecast:
    detector_id: str
    detector_version: str
    instrument: str
    axis: str
    clock: str
    horizon_seconds: int
    observed_at: datetime
    available_at: datetime
    expires_at: datetime
    fit_cutoff: datetime
    units: str
    point_estimate: float | None
    lower_bound: float | None
    upper_bound: float | None
    confidence: float
    evidence_status: str
    lineage_digests: Mapping[str, str]
    unknown_reason: str | None = None

    def __post_init__(self) -> None:
        for name in ("detector_id", "detector_version", "instrument", "units"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if self.axis not in RISK_AXES:
            raise ResearchRiskError(f"unsupported risk axis: {self.axis}")
        if self.clock not in RISK_CLOCKS:
            raise ResearchRiskError(f"unsupported risk clock: {self.clock}")
        if not isinstance(self.horizon_seconds, int) or self.horizon_seconds <= 0:
            raise ResearchRiskError("horizon_seconds must be a positive integer")
        observed = _utc(self.observed_at, "observed_at")
        available = _utc(self.available_at, "available_at")
        expires = _utc(self.expires_at, "expires_at")
        cutoff = _utc(self.fit_cutoff, "fit_cutoff")
        if cutoff > observed or observed > available or available >= expires:
            raise ResearchRiskError(
                "timestamps must satisfy fit_cutoff <= observed_at <= available_at < expires_at"
            )
        if self.evidence_status not in ALL_EVIDENCE:
            raise ResearchRiskError(f"unsupported evidence status: {self.evidence_status}")
        object.__setattr__(self, "confidence", _fraction(self.confidence, "confidence"))
        object.__setattr__(
            self, "lineage_digests", _frozen_digests(self.lineage_digests, "lineage_digests")
        )
        values = (self.point_estimate, self.lower_bound, self.upper_bound)
        if self.unknown_reason is None:
            if any(value is None for value in values):
                raise ResearchRiskError("known risk forecast requires point and interval estimates")
            point, lower, upper = (_finite(value, "forecast value") for value in values)  # type: ignore[arg-type]
            if lower > point or point > upper:
                raise ResearchRiskError("forecast interval must contain point estimate")
            object.__setattr__(self, "point_estimate", point)
            object.__setattr__(self, "lower_bound", lower)
            object.__setattr__(self, "upper_bound", upper)
        else:
            object.__setattr__(self, "unknown_reason", _text(self.unknown_reason, "unknown_reason"))
            if any(value is not None for value in values):
                raise ResearchRiskError("unknown risk forecast cannot carry numeric estimates")

    def usable_at(self, decision_at: datetime) -> bool:
        decision = _utc(decision_at, "decision_at")
        return (
            self.unknown_reason is None
            and self.evidence_status in USABLE_EVIDENCE
            and self.available_at <= decision < self.expires_at
        )

    def _payload(self) -> dict[str, Any]:
        return {
            "available_at": _iso(self.available_at),
            "axis": self.axis,
            "clock": self.clock,
            "confidence": self.confidence,
            "detector_id": self.detector_id,
            "detector_version": self.detector_version,
            "evidence_status": self.evidence_status,
            "expires_at": _iso(self.expires_at),
            "fit_cutoff": _iso(self.fit_cutoff),
            "horizon_seconds": self.horizon_seconds,
            "instrument": self.instrument,
            "lineage_digests": dict(self.lineage_digests),
            "lower_bound": self.lower_bound,
            "observed_at": _iso(self.observed_at),
            "point_estimate": self.point_estimate,
            "units": self.units,
            "unknown_reason": self.unknown_reason,
            "upper_bound": self.upper_bound,
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self._payload())

    def as_dict(self) -> dict[str, Any]:
        return {**self._payload(), "digest": self.digest}


@dataclass(frozen=True, slots=True)
class RiskPanel:
    decision_at: datetime
    forecasts: tuple[RiskForecast, ...]

    def __post_init__(self) -> None:
        decision = _utc(self.decision_at, "decision_at")
        identities: set[tuple[str, str, str, int]] = set()
        for forecast in self.forecasts:
            identity = (
                forecast.detector_id,
                forecast.axis,
                forecast.clock,
                forecast.horizon_seconds,
            )
            if identity in identities:
                raise ResearchRiskError("duplicate detector/axis/clock/horizon forecast")
            if forecast.available_at > decision:
                raise ResearchRiskError("risk panel contains a future-dependent forecast")
            identities.add(identity)
        ordered = tuple(
            sorted(
                self.forecasts,
                key=lambda item: (item.axis, item.clock, item.horizon_seconds, item.detector_id),
            )
        )
        object.__setattr__(self, "forecasts", ordered)

    def _payload(self) -> dict[str, Any]:
        return {
            "decision_at": _iso(self.decision_at),
            "forecast_digests": [forecast.digest for forecast in self.forecasts],
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self._payload())

    def as_dict(self) -> dict[str, Any]:
        return {**self._payload(), "digest": self.digest}


@dataclass(frozen=True, slots=True)
class RiskCap:
    detector_id: str
    detector_version: str
    axis: str
    clock: str
    available_at: datetime
    expires_at: datetime
    maximum_allocation_fraction: float
    evidence_status: str
    lineage_digest: str
    unknown_reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "detector_id", _text(self.detector_id, "detector_id"))
        object.__setattr__(
            self, "detector_version", _text(self.detector_version, "detector_version")
        )
        if self.axis not in RISK_AXES or self.clock not in RISK_CLOCKS:
            raise ResearchRiskError("risk cap has unsupported axis or clock")
        available = _utc(self.available_at, "available_at")
        expires = _utc(self.expires_at, "expires_at")
        if available >= expires:
            raise ResearchRiskError("risk cap must expire after availability")
        object.__setattr__(
            self,
            "maximum_allocation_fraction",
            _fraction(self.maximum_allocation_fraction, "maximum_allocation_fraction"),
        )
        if self.evidence_status not in ALL_EVIDENCE:
            raise ResearchRiskError(f"unsupported evidence status: {self.evidence_status}")
        object.__setattr__(self, "lineage_digest", _digest(self.lineage_digest, "lineage_digest"))
        if self.unknown_reason is not None:
            object.__setattr__(self, "unknown_reason", _text(self.unknown_reason, "unknown_reason"))

    def usable_at(self, decision_at: datetime) -> bool:
        decision = _utc(decision_at, "decision_at")
        return (
            self.unknown_reason is None
            and self.evidence_status in USABLE_EVIDENCE
            and self.available_at <= decision < self.expires_at
        )

    @property
    def digest(self) -> str:
        return canonical_digest(
            {
                "available_at": _iso(self.available_at),
                "axis": self.axis,
                "clock": self.clock,
                "detector_id": self.detector_id,
                "detector_version": self.detector_version,
                "evidence_status": self.evidence_status,
                "expires_at": _iso(self.expires_at),
                "lineage_digest": self.lineage_digest,
                "maximum_allocation_fraction": self.maximum_allocation_fraction,
                "unknown_reason": self.unknown_reason,
            }
        )


@dataclass(frozen=True, slots=True)
class RiskBudgetDecision:
    decision_at: datetime
    position_open: bool
    requested_allocation_fraction: float
    prior_allocation_fraction: float
    final_allocation_fraction: float
    required_axes: tuple[str, ...]
    applied_cap_digests: tuple[str, ...]
    reasons: tuple[str, ...]
    actionable_arm_id: str = "no_trade"
    order_intent_created: bool = False

    def __post_init__(self) -> None:
        _utc(self.decision_at, "decision_at")
        for name in (
            "requested_allocation_fraction",
            "prior_allocation_fraction",
            "final_allocation_fraction",
        ):
            object.__setattr__(self, name, _fraction(getattr(self, name), name))
        if tuple(sorted(set(self.required_axes))) != self.required_axes:
            raise ResearchRiskError("required_axes must be unique and sorted")
        if not self.reasons:
            raise ResearchRiskError("risk budget decision requires reasons")
        if self.position_open and self.final_allocation_fraction > self.prior_allocation_fraction:
            raise ResearchRiskError("intratrade risk decision cannot increase allocation")
        if self.actionable_arm_id != "no_trade" or self.order_intent_created:
            raise ResearchRiskError("offline risk decision cannot become executable")

    @property
    def digest(self) -> str:
        return canonical_digest(
            {
                "actionable_arm_id": self.actionable_arm_id,
                "applied_cap_digests": list(self.applied_cap_digests),
                "decision_at": _iso(self.decision_at),
                "final_allocation_fraction": self.final_allocation_fraction,
                "order_intent_created": self.order_intent_created,
                "position_open": self.position_open,
                "prior_allocation_fraction": self.prior_allocation_fraction,
                "reasons": list(self.reasons),
                "requested_allocation_fraction": self.requested_allocation_fraction,
                "required_axes": list(self.required_axes),
            }
        )


@dataclass(frozen=True, slots=True)
class DownwardOnlyRiskFusionPolicy:
    policy_id: str
    policy_version: str
    required_axes: tuple[str, ...]
    maximum_allocation_fraction: float = 0.25
    automatic_releveraging_allowed: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_id", _text(self.policy_id, "policy_id"))
        object.__setattr__(self, "policy_version", _text(self.policy_version, "policy_version"))
        axes = tuple(sorted(set(self.required_axes)))
        if not axes or axes != self.required_axes or any(axis not in RISK_AXES for axis in axes):
            raise ResearchRiskError("required_axes must be non-empty, unique, sorted risk axes")
        object.__setattr__(
            self,
            "maximum_allocation_fraction",
            _fraction(self.maximum_allocation_fraction, "maximum_allocation_fraction"),
        )

    def decide(
        self,
        *,
        decision_at: datetime,
        requested_allocation_fraction: float,
        prior_allocation_fraction: float,
        position_open: bool,
        caps: Sequence[RiskCap],
    ) -> RiskBudgetDecision:
        decision = _utc(decision_at, "decision_at")
        requested = min(
            _fraction(requested_allocation_fraction, "requested_allocation_fraction"),
            self.maximum_allocation_fraction,
        )
        prior = _fraction(prior_allocation_fraction, "prior_allocation_fraction")
        if position_open and prior <= 0:
            raise ResearchRiskError("open position requires positive prior allocation")
        if not position_open and prior != 0:
            raise ResearchRiskError("new entry decision requires zero prior allocation")

        usable_by_axis: dict[str, list[RiskCap]] = {axis: [] for axis in self.required_axes}
        for cap in caps:
            if cap.axis in usable_by_axis and cap.usable_at(decision):
                usable_by_axis[cap.axis].append(cap)
        missing = tuple(axis for axis, values in usable_by_axis.items() if not values)
        if missing:
            return RiskBudgetDecision(
                decision_at=decision,
                position_open=position_open,
                requested_allocation_fraction=requested,
                prior_allocation_fraction=prior,
                final_allocation_fraction=0,
                required_axes=self.required_axes,
                applied_cap_digests=(),
                reasons=("fail_closed_missing_or_unusable_required_axes:" + ",".join(missing),),
            )

        applicable = tuple(
            sorted(
                (cap for values in usable_by_axis.values() for cap in values),
                key=lambda cap: (cap.axis, cap.detector_id, cap.detector_version),
            )
        )
        starting = prior if position_open else requested
        final = min(starting, *(cap.maximum_allocation_fraction for cap in applicable))
        reasons = (
            "downward_only_intratrade_cap" if position_open else "risk_capped_new_entry",
            "minimum_of_usable_required_axis_caps",
            "automatic_releveraging_disabled",
        )
        return RiskBudgetDecision(
            decision_at=decision,
            position_open=position_open,
            requested_allocation_fraction=requested,
            prior_allocation_fraction=prior,
            final_allocation_fraction=final,
            required_axes=self.required_axes,
            applied_cap_digests=tuple(cap.digest for cap in applicable),
            reasons=reasons,
        )
