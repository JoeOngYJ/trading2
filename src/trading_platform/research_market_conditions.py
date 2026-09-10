"""Offline contracts for causal BTC market-condition research.

The module is deliberately limited to immutable research observations and metadata-only
input availability.  It has no strategy, portfolio, signal, order, database, transport,
exchange, or runtime integration.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence


CONDITION_AXES = frozenset(
    {
        "carry",
        "downside_tail",
        "implied_risk",
        "jump_change",
        "liquidity_cost",
        "onchain_flow",
        "persistence",
        "reversion",
        "volatility",
    }
)
INPUT_STATUSES = frozenset(
    {
        "absent",
        "available_consumed_development",
        "benchmark_only",
        "blocked",
        "conditional_research",
        "proxy_only",
    }
)
RESEARCH_READY_STATUSES = frozenset(
    {"available_consumed_development", "benchmark_only", "conditional_research"}
)


class MarketConditionError(ValueError):
    """Raised when an offline market-condition contract fails closed."""


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MarketConditionError(f"{label} must be a non-empty string")
    return value.strip()


def _utc(value: datetime, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise MarketConditionError(f"{label} must be timezone-aware UTC")
    if value.utcoffset() != timedelta(0):
        raise MarketConditionError(f"{label} must use UTC")
    return value


def _iso(value: datetime) -> str:
    return _utc(value, "timestamp").isoformat().replace("+00:00", "Z")


def _digest(value: str, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or value.lower() != value:
        raise MarketConditionError(f"{label} must be a lowercase SHA-256 digest")
    try:
        int(value, 16)
    except ValueError as exc:
        raise MarketConditionError(f"{label} must be hexadecimal") from exc
    return value


def _finite(value: float, label: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise MarketConditionError(f"{label} must be finite")
    return number


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _frozen_values(
    values: Mapping[str, float] | Sequence[tuple[str, float]], label: str
) -> Mapping[str, float]:
    items = list(values.items()) if isinstance(values, Mapping) else list(values)
    normalized: dict[str, float] = {}
    for raw_key, raw_value in items:
        key = _text(raw_key, f"{label} key")
        if key in normalized:
            raise MarketConditionError(f"{label} contains duplicate key: {key}")
        normalized[key] = _finite(raw_value, f"{label}[{key}]")
    return MappingProxyType(dict(sorted(normalized.items())))


def _frozen_digests(values: Mapping[str, str], label: str) -> Mapping[str, str]:
    if not values:
        raise MarketConditionError(f"{label} cannot be empty")
    normalized: dict[str, str] = {}
    for raw_key, raw_value in values.items():
        key = _text(raw_key, f"{label} key")
        if key in normalized:
            raise MarketConditionError(f"{label} contains duplicate key: {key}")
        normalized[key] = _digest(raw_value, f"{label}[{key}]")
    return MappingProxyType(dict(sorted(normalized.items())))


def _sorted_unique(values: Sequence[str], label: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    normalized = tuple(sorted(_text(value, label) for value in values))
    if not allow_empty and not normalized:
        raise MarketConditionError(f"{label} cannot be empty")
    if len(normalized) != len(set(normalized)):
        raise MarketConditionError(f"{label} contains duplicates")
    return normalized


def _axes(values: Sequence[str], label: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    normalized = _sorted_unique(values, label, allow_empty=allow_empty)
    unknown = set(normalized) - CONDITION_AXES
    if unknown:
        raise MarketConditionError(f"{label} contains unsupported axes: {sorted(unknown)}")
    return normalized


def _relative_path(value: str, label: str) -> str:
    text = _text(value, label)
    path = Path(text)
    if path.is_absolute() or ".." in path.parts:
        raise MarketConditionError(f"{label} must be a safe repository-relative path")
    return path.as_posix()


@dataclass(frozen=True, slots=True)
class MarketConditionObservation:
    """One point-in-time feature observation, not a score or trading decision."""

    instrument: str
    venue: str
    axis: str
    interval: str
    segment: str
    window_started_at: datetime
    observed_at: datetime
    available_at: datetime
    field_values: Mapping[str, float] | Sequence[tuple[str, float]]
    lineage_digests: Mapping[str, str]
    unknown_reason: str | None = None

    def __post_init__(self) -> None:
        for name in ("instrument", "venue", "interval", "segment"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if self.axis not in CONDITION_AXES:
            raise MarketConditionError(f"unsupported market-condition axis: {self.axis}")
        started = _utc(self.window_started_at, "window_started_at")
        observed = _utc(self.observed_at, "observed_at")
        available = _utc(self.available_at, "available_at")
        if started > observed or observed > available:
            raise MarketConditionError(
                "timestamps must satisfy window_started_at <= observed_at <= available_at"
            )
        values = _frozen_values(self.field_values, "field_values")
        object.__setattr__(self, "lineage_digests", _frozen_digests(self.lineage_digests, "lineage_digests"))
        if self.unknown_reason is None:
            if not values:
                raise MarketConditionError("known observation requires at least one field value")
        else:
            object.__setattr__(self, "unknown_reason", _text(self.unknown_reason, "unknown_reason"))
            if values:
                raise MarketConditionError("unknown observation cannot contain field values")
        object.__setattr__(self, "field_values", values)

    def available_for(self, decision_at: datetime) -> bool:
        decision = _utc(decision_at, "decision_at")
        return self.unknown_reason is None and self.available_at <= decision

    def _payload(self) -> dict[str, Any]:
        return {
            "available_at": _iso(self.available_at),
            "axis": self.axis,
            "field_values": dict(self.field_values),
            "instrument": self.instrument,
            "interval": self.interval,
            "lineage_digests": dict(self.lineage_digests),
            "observed_at": _iso(self.observed_at),
            "segment": self.segment,
            "unknown_reason": self.unknown_reason,
            "venue": self.venue,
            "window_started_at": _iso(self.window_started_at),
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self._payload())

    def as_dict(self) -> dict[str, Any]:
        return {**self._payload(), "digest": self.digest}


def validate_observation_sequence(
    observations: Sequence[MarketConditionObservation], *, require_single_segment: bool = True
) -> tuple[MarketConditionObservation, ...]:
    """Validate a causal sequence without silently bridging source gaps."""

    checked = tuple(observations)
    if not checked:
        raise MarketConditionError("observation sequence cannot be empty")
    first = checked[0]
    prior_observed: datetime | None = None
    prior_available: datetime | None = None
    seen: set[tuple[str, datetime]] = set()
    for item in checked:
        identity_fields = (item.instrument, item.venue, item.axis, item.interval)
        if identity_fields != (first.instrument, first.venue, first.axis, first.interval):
            raise MarketConditionError("observation sequence changes instrument, venue, axis, or interval")
        if require_single_segment and item.segment != first.segment:
            raise MarketConditionError("observation sequence crosses a source segment")
        identity = (item.segment, item.observed_at)
        if identity in seen:
            raise MarketConditionError("observation sequence contains a duplicate")
        if prior_observed is not None and item.observed_at <= prior_observed:
            raise MarketConditionError("observed_at values must be strictly increasing")
        if prior_available is not None and item.available_at <= prior_available:
            raise MarketConditionError("available_at values must be strictly increasing")
        seen.add(identity)
        prior_observed = item.observed_at
        prior_available = item.available_at
    return checked


@dataclass(frozen=True, slots=True)
class InputAvailabilityRecord:
    """Metadata-only declaration of whether a dataset can support an axis."""

    dataset_id: str
    instrument: str
    status: str
    intervals: Sequence[str]
    supported_axes: Sequence[str]
    candidate_axes: Sequence[str]
    coverage_start: datetime | None
    coverage_end_exclusive: datetime | None
    manifest_path: str
    manifest_sha256: str
    point_in_time_ready: bool
    segment_policy: str
    blockers: Sequence[str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "dataset_id", _text(self.dataset_id, "dataset_id"))
        object.__setattr__(self, "instrument", _text(self.instrument, "instrument"))
        if self.status not in INPUT_STATUSES:
            raise MarketConditionError(f"unsupported input status: {self.status}")
        intervals = _sorted_unique(self.intervals, "intervals", allow_empty=self.status == "absent")
        supported = _axes(self.supported_axes, "supported_axes", allow_empty=True)
        candidates = _axes(self.candidate_axes, "candidate_axes", allow_empty=True)
        if set(supported) & set(candidates):
            raise MarketConditionError("supported_axes and candidate_axes must be disjoint")
        blockers = _sorted_unique(self.blockers, "blockers", allow_empty=True)
        start = self.coverage_start
        end = self.coverage_end_exclusive
        if (start is None) != (end is None):
            raise MarketConditionError("coverage boundaries must both be present or absent")
        if start is not None and end is not None:
            start = _utc(start, "coverage_start")
            end = _utc(end, "coverage_end_exclusive")
            if start >= end:
                raise MarketConditionError("coverage_start must precede coverage_end_exclusive")
        if self.status in RESEARCH_READY_STATUSES:
            if not self.point_in_time_ready or not supported or start is None:
                raise MarketConditionError("research-ready input requires point-in-time axes and coverage")
        else:
            if supported:
                raise MarketConditionError("blocked, absent, or proxy-only input cannot support an axis")
            if not candidates or not blockers:
                raise MarketConditionError("unavailable input requires candidate axes and blockers")
        object.__setattr__(self, "intervals", intervals)
        object.__setattr__(self, "supported_axes", supported)
        object.__setattr__(self, "candidate_axes", candidates)
        object.__setattr__(self, "blockers", blockers)
        object.__setattr__(self, "manifest_path", _relative_path(self.manifest_path, "manifest_path"))
        object.__setattr__(self, "manifest_sha256", _digest(self.manifest_sha256, "manifest_sha256"))
        object.__setattr__(self, "segment_policy", _text(self.segment_policy, "segment_policy"))

    def _payload(self) -> dict[str, Any]:
        return {
            "blockers": list(self.blockers),
            "candidate_axes": list(self.candidate_axes),
            "coverage_end_exclusive": _iso(self.coverage_end_exclusive) if self.coverage_end_exclusive else None,
            "coverage_start": _iso(self.coverage_start) if self.coverage_start else None,
            "dataset_id": self.dataset_id,
            "instrument": self.instrument,
            "intervals": list(self.intervals),
            "manifest_path": self.manifest_path,
            "manifest_sha256": self.manifest_sha256,
            "point_in_time_ready": self.point_in_time_ready,
            "segment_policy": self.segment_policy,
            "status": self.status,
            "supported_axes": list(self.supported_axes),
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self._payload())

    def as_dict(self) -> dict[str, Any]:
        return {**self._payload(), "digest": self.digest}


@dataclass(frozen=True, slots=True)
class InputAvailabilityMatrix:
    records: Sequence[InputAvailabilityRecord]

    def __post_init__(self) -> None:
        if not self.records:
            raise MarketConditionError("availability matrix cannot be empty")
        ordered = tuple(sorted(self.records, key=lambda item: item.dataset_id))
        identities = [item.dataset_id for item in ordered]
        if len(identities) != len(set(identities)):
            raise MarketConditionError("availability matrix contains duplicate dataset IDs")
        object.__setattr__(self, "records", ordered)

    def axis_summary(self) -> dict[str, dict[str, list[str]]]:
        summary: dict[str, dict[str, list[str]]] = {}
        for axis in sorted(CONDITION_AXES):
            summary[axis] = {
                "blocked_or_absent": [
                    item.dataset_id
                    for item in self.records
                    if axis in item.candidate_axes and item.status in {"absent", "blocked"}
                ],
                "proxy_only": [
                    item.dataset_id
                    for item in self.records
                    if axis in item.candidate_axes and item.status == "proxy_only"
                ],
                "research_ready": [
                    item.dataset_id for item in self.records if axis in item.supported_axes
                ],
            }
        return summary

    def _payload(self) -> dict[str, Any]:
        return {
            "axis_summary": self.axis_summary(),
            "record_digests": [item.digest for item in self.records],
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self._payload())

    def as_dict(self) -> dict[str, Any]:
        return {
            "axis_summary": self.axis_summary(),
            "digest": self.digest,
            "records": [item.as_dict() for item in self.records],
        }
