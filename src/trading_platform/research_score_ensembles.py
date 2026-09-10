"""Synthetic-only contracts for target-aware score calibration and combination.

The module deliberately has no strategy, PnL, position, order, database, transport, exchange or
market-data integration.  It cannot create a universal market score.  Different targets remain a
vector; only forecasts with identical target semantics may enter a predeclared convex ensemble.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from trading_platform.research_condition_scores import MarketConditionScore


EVIDENCE_STATUSES = frozenset({"accepted", "benchmark", "development", "rejected"})
ENSEMBLE_MEMBER_EVIDENCE = frozenset({"accepted", "benchmark"})
PERMITTED_USES = frozenset(
    {
        "control",
        "diagnostic",
        "risk_cap_candidate",
        "same_target_ensemble",
        "strategy_condition_candidate",
    }
)
NON_ACTIONABLE_USES = frozenset({"control", "diagnostic"})


class ScoreEnsembleError(ValueError):
    """Raised when score combination cannot remain causal and target-consistent."""


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ScoreEnsembleError(f"{label} must be a non-empty string")
    return value.strip()


def _utc(value: datetime, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ScoreEnsembleError(f"{label} must be timezone-aware UTC")
    if value.utcoffset() != timedelta(0):
        raise ScoreEnsembleError(f"{label} must use UTC")
    return value


def _iso(value: datetime) -> str:
    return _utc(value, "timestamp").isoformat().replace("+00:00", "Z")


def _finite(value: float, label: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ScoreEnsembleError(f"{label} must be finite")
    return number


def _fraction(value: float, label: str) -> float:
    number = _finite(value, label)
    if not 0 <= number <= 1:
        raise ScoreEnsembleError(f"{label} must be within [0, 1]")
    return number


def _digest(value: str, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or value.lower() != value:
        raise ScoreEnsembleError(f"{label} must be a lowercase SHA-256 digest")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ScoreEnsembleError(f"{label} must be hexadecimal") from exc
    return value


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _identity(score_id: str, score_version: str) -> str:
    return f"{score_id}@{score_version}"


@dataclass(frozen=True, slots=True)
class ScoreCatalogueEntry:
    """Immutable semantics and evidence policy for one score implementation."""

    score_id: str
    score_version: str
    axis: str
    target_id: str
    horizon_seconds: int
    score_kind: str
    units: str
    evidence_status: str
    permitted_uses: tuple[str, ...]
    evidence_digest: str

    def __post_init__(self) -> None:
        for name in ("score_id", "score_version", "axis", "target_id", "score_kind", "units"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if not isinstance(self.horizon_seconds, int) or self.horizon_seconds <= 0:
            raise ScoreEnsembleError("horizon_seconds must be a positive integer")
        if self.score_kind not in {"continuous", "probability"}:
            raise ScoreEnsembleError(f"unsupported score kind: {self.score_kind}")
        if self.evidence_status not in EVIDENCE_STATUSES:
            raise ScoreEnsembleError(f"unsupported evidence status: {self.evidence_status}")
        uses = tuple(sorted(set(self.permitted_uses)))
        if not uses or uses != self.permitted_uses or any(use not in PERMITTED_USES for use in uses):
            raise ScoreEnsembleError("permitted_uses must be non-empty, unique, sorted known uses")
        if self.evidence_status in {"development", "rejected"} and any(
            use not in NON_ACTIONABLE_USES for use in uses
        ):
            raise ScoreEnsembleError(
                "development or rejected scores may be retained only as diagnostics or controls"
            )
        object.__setattr__(self, "evidence_digest", _digest(self.evidence_digest, "evidence_digest"))

    @property
    def identity(self) -> str:
        return _identity(self.score_id, self.score_version)

    def matches(self, score: MarketConditionScore) -> bool:
        return (
            score.score_id == self.score_id
            and score.score_version == self.score_version
            and score.axis == self.axis
            and score.horizon_seconds == self.horizon_seconds
            and score.score_kind == self.score_kind
            and score.units == self.units
            and score.evidence_status == self.evidence_status
        )

    def _payload(self) -> dict[str, Any]:
        return {
            "axis": self.axis,
            "evidence_digest": self.evidence_digest,
            "evidence_status": self.evidence_status,
            "horizon_seconds": self.horizon_seconds,
            "permitted_uses": list(self.permitted_uses),
            "score_id": self.score_id,
            "score_kind": self.score_kind,
            "score_version": self.score_version,
            "target_id": self.target_id,
            "units": self.units,
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self._payload())

    def as_dict(self) -> dict[str, Any]:
        return {**self._payload(), "digest": self.digest}


@dataclass(frozen=True, slots=True)
class ScoreCatalogue:
    """Deterministic collection of score meanings; it contains no score values."""

    catalogue_id: str
    catalogue_version: str
    entries: tuple[ScoreCatalogueEntry, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "catalogue_id", _text(self.catalogue_id, "catalogue_id"))
        object.__setattr__(
            self, "catalogue_version", _text(self.catalogue_version, "catalogue_version")
        )
        identities: set[str] = set()
        for entry in self.entries:
            if entry.identity in identities:
                raise ScoreEnsembleError(f"duplicate catalogue score identity: {entry.identity}")
            identities.add(entry.identity)
        if not identities:
            raise ScoreEnsembleError("score catalogue cannot be empty")
        object.__setattr__(self, "entries", tuple(sorted(self.entries, key=lambda row: row.identity)))

    def entry(self, score_id: str, score_version: str) -> ScoreCatalogueEntry:
        wanted = _identity(_text(score_id, "score_id"), _text(score_version, "score_version"))
        for item in self.entries:
            if item.identity == wanted:
                return item
        raise ScoreEnsembleError(f"score is absent from catalogue: {wanted}")

    def _payload(self) -> dict[str, Any]:
        return {
            "catalogue_id": self.catalogue_id,
            "catalogue_version": self.catalogue_version,
            "entry_digests": [entry.digest for entry in self.entries],
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self._payload())

    def as_dict(self) -> dict[str, Any]:
        return {**self._payload(), "digest": self.digest}


@dataclass(frozen=True, slots=True)
class CalibrationSample:
    """One historical score value with explicit point-in-time availability."""

    observed_at: datetime
    available_at: datetime
    value: float
    catalogue_entry_digest: str
    lineage_digest: str

    def __post_init__(self) -> None:
        observed = _utc(self.observed_at, "observed_at")
        available = _utc(self.available_at, "available_at")
        if observed > available:
            raise ScoreEnsembleError("calibration sample cannot be available before observation")
        object.__setattr__(self, "value", _finite(self.value, "value"))
        object.__setattr__(
            self,
            "catalogue_entry_digest",
            _digest(self.catalogue_entry_digest, "catalogue_entry_digest"),
        )
        object.__setattr__(self, "lineage_digest", _digest(self.lineage_digest, "lineage_digest"))

    @property
    def digest(self) -> str:
        return canonical_digest(
            {
                "available_at": _iso(self.available_at),
                "catalogue_entry_digest": self.catalogue_entry_digest,
                "lineage_digest": self.lineage_digest,
                "observed_at": _iso(self.observed_at),
                "value": self.value,
            }
        )


@dataclass(frozen=True, slots=True)
class CalibratedScore:
    """Past-only percentile retaining raw semantics; never an action score."""

    raw_score_digest: str
    catalogue_entry_digest: str
    target_id: str
    horizon_seconds: int
    fit_cutoff: datetime
    available_at: datetime
    expires_at: datetime
    history_count: int
    percentile: float | None
    lower_percentile: float | None
    upper_percentile: float | None
    evidence_status: str
    history_digests: tuple[str, ...]
    unknown_reason: str | None = None
    display_only: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "raw_score_digest", _digest(self.raw_score_digest, "raw_score_digest"))
        object.__setattr__(
            self,
            "catalogue_entry_digest",
            _digest(self.catalogue_entry_digest, "catalogue_entry_digest"),
        )
        object.__setattr__(self, "target_id", _text(self.target_id, "target_id"))
        if not isinstance(self.horizon_seconds, int) or self.horizon_seconds <= 0:
            raise ScoreEnsembleError("horizon_seconds must be positive")
        _utc(self.fit_cutoff, "fit_cutoff")
        available = _utc(self.available_at, "available_at")
        expires = _utc(self.expires_at, "expires_at")
        if available >= expires:
            raise ScoreEnsembleError("calibrated score must expire after availability")
        if not isinstance(self.history_count, int) or self.history_count < 0:
            raise ScoreEnsembleError("history_count must be a non-negative integer")
        if self.evidence_status not in EVIDENCE_STATUSES:
            raise ScoreEnsembleError("unsupported evidence status")
        for digest in self.history_digests:
            _digest(digest, "history_digest")
        if tuple(sorted(set(self.history_digests))) != self.history_digests:
            raise ScoreEnsembleError("history_digests must be unique and sorted")
        values = (self.percentile, self.lower_percentile, self.upper_percentile)
        if self.unknown_reason is None:
            if any(value is None for value in values):
                raise ScoreEnsembleError("known calibration requires point and interval percentiles")
            point, lower, upper = (_fraction(value, "percentile") for value in values)  # type: ignore[arg-type]
            if lower > point or point > upper:
                raise ScoreEnsembleError("calibrated interval must contain point percentile")
            object.__setattr__(self, "percentile", point)
            object.__setattr__(self, "lower_percentile", lower)
            object.__setattr__(self, "upper_percentile", upper)
        else:
            object.__setattr__(self, "unknown_reason", _text(self.unknown_reason, "unknown_reason"))
            if any(value is not None for value in values):
                raise ScoreEnsembleError("unknown calibration cannot contain numeric percentiles")
        if self.display_only is not True:
            raise ScoreEnsembleError("calibrated percentile must remain display/model-input only")

    def _payload(self) -> dict[str, Any]:
        return {
            "available_at": _iso(self.available_at),
            "catalogue_entry_digest": self.catalogue_entry_digest,
            "display_only": self.display_only,
            "evidence_status": self.evidence_status,
            "expires_at": _iso(self.expires_at),
            "fit_cutoff": _iso(self.fit_cutoff),
            "history_count": self.history_count,
            "history_digests": list(self.history_digests),
            "horizon_seconds": self.horizon_seconds,
            "lower_percentile": self.lower_percentile,
            "percentile": self.percentile,
            "raw_score_digest": self.raw_score_digest,
            "target_id": self.target_id,
            "unknown_reason": self.unknown_reason,
            "upper_percentile": self.upper_percentile,
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self._payload())

    def as_dict(self) -> dict[str, Any]:
        return {**self._payload(), "digest": self.digest}


def _midrank_percentile(history: Sequence[float], value: float) -> float:
    less = sum(item < value for item in history)
    equal = sum(item == value for item in history)
    return (less + 0.5 * equal) / len(history)


def calibrate_empirical_percentile(
    *,
    score: MarketConditionScore,
    catalogue_entry: ScoreCatalogueEntry,
    samples: Sequence[CalibrationSample],
    decision_at: datetime,
    minimum_history: int,
) -> CalibratedScore:
    """Calibrate against values available by ``score.fit_cutoff`` only."""

    decision = _utc(decision_at, "decision_at")
    if not isinstance(minimum_history, int) or minimum_history <= 0:
        raise ScoreEnsembleError("minimum_history must be a positive integer")
    if not catalogue_entry.matches(score):
        raise ScoreEnsembleError("score does not match its catalogue semantics or evidence")
    if score.available_at > decision:
        raise ScoreEnsembleError("cannot calibrate a future-dependent score")
    history: list[CalibrationSample] = []
    for sample in samples:
        if sample.catalogue_entry_digest != catalogue_entry.digest:
            raise ScoreEnsembleError("calibration sample belongs to a different score definition")
        if sample.available_at > score.fit_cutoff:
            raise ScoreEnsembleError("calibration history was not available by score fit cutoff")
        history.append(sample)
    ordered = tuple(sorted(history, key=lambda row: (row.available_at, row.observed_at, row.digest)))
    digests = tuple(sorted(sample.digest for sample in ordered))
    unknown_reason: str | None = None
    if score.unknown_reason is not None:
        unknown_reason = f"raw_score_unknown:{score.unknown_reason}"
    elif decision >= score.expires_at:
        unknown_reason = "raw_score_stale_at_decision"
    elif len(ordered) < minimum_history:
        unknown_reason = "insufficient_calibration_history"
    if unknown_reason is not None:
        return CalibratedScore(
            raw_score_digest=score.digest,
            catalogue_entry_digest=catalogue_entry.digest,
            target_id=catalogue_entry.target_id,
            horizon_seconds=score.horizon_seconds,
            fit_cutoff=score.fit_cutoff,
            available_at=score.available_at,
            expires_at=score.expires_at,
            history_count=len(ordered),
            percentile=None,
            lower_percentile=None,
            upper_percentile=None,
            evidence_status=score.evidence_status,
            history_digests=digests,
            unknown_reason=unknown_reason,
        )
    values = tuple(sample.value for sample in ordered)
    assert score.point_estimate is not None
    assert score.lower_bound is not None
    assert score.upper_bound is not None
    return CalibratedScore(
        raw_score_digest=score.digest,
        catalogue_entry_digest=catalogue_entry.digest,
        target_id=catalogue_entry.target_id,
        horizon_seconds=score.horizon_seconds,
        fit_cutoff=score.fit_cutoff,
        available_at=score.available_at,
        expires_at=score.expires_at,
        history_count=len(values),
        percentile=_midrank_percentile(values, score.point_estimate),
        lower_percentile=_midrank_percentile(values, score.lower_bound),
        upper_percentile=_midrank_percentile(values, score.upper_bound),
        evidence_status=score.evidence_status,
        history_digests=digests,
    )


@dataclass(frozen=True, slots=True)
class ConvexEnsembleSpec:
    """Frozen weights for forecasts sharing one exact target contract."""

    ensemble_id: str
    ensemble_version: str
    axis: str
    target_id: str
    horizon_seconds: int
    score_kind: str
    units: str
    weights: Mapping[str, float]

    def __post_init__(self) -> None:
        for name in ("ensemble_id", "ensemble_version", "axis", "target_id", "score_kind", "units"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if not isinstance(self.horizon_seconds, int) or self.horizon_seconds <= 0:
            raise ScoreEnsembleError("horizon_seconds must be a positive integer")
        if self.score_kind not in {"continuous", "probability"}:
            raise ScoreEnsembleError("unsupported score kind")
        normalized: dict[str, float] = {}
        for raw_identity, raw_weight in self.weights.items():
            identity = _text(raw_identity, "weight identity")
            if identity in normalized:
                raise ScoreEnsembleError(f"duplicate weight identity: {identity}")
            weight = _finite(raw_weight, f"weight[{identity}]")
            if weight < 0:
                raise ScoreEnsembleError("ensemble weights must be non-negative")
            normalized[identity] = weight
        if len(normalized) < 2:
            raise ScoreEnsembleError("same-target ensemble requires at least two members")
        if not math.isclose(sum(normalized.values()), 1.0, rel_tol=0, abs_tol=1e-12):
            raise ScoreEnsembleError("ensemble weights must sum to one")
        if any(weight == 0 for weight in normalized.values()):
            raise ScoreEnsembleError("zero-weight entries are not ensemble members")
        object.__setattr__(self, "weights", MappingProxyType(dict(sorted(normalized.items()))))

    def _payload(self) -> dict[str, Any]:
        return {
            "axis": self.axis,
            "ensemble_id": self.ensemble_id,
            "ensemble_version": self.ensemble_version,
            "horizon_seconds": self.horizon_seconds,
            "score_kind": self.score_kind,
            "target_id": self.target_id,
            "units": self.units,
            "weights": dict(self.weights),
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self._payload())

    def as_dict(self) -> dict[str, Any]:
        return {**self._payload(), "digest": self.digest}


@dataclass(frozen=True, slots=True)
class SameTargetEnsembleScore:
    """Development-only ensemble output with no strategy or action mapping."""

    ensemble_id: str
    ensemble_version: str
    instrument: str
    venues: tuple[str, ...]
    axis: str
    target_id: str
    horizon_seconds: int
    score_kind: str
    units: str
    fit_cutoff: datetime
    observed_at: datetime
    available_at: datetime
    expires_at: datetime
    point_estimate: float
    lower_bound: float
    upper_bound: float
    confidence: float
    member_score_digests: tuple[str, ...]
    spec_digest: str
    evidence_status: str = "development"
    actionable_arm_id: str = "no_trade"
    strategy_action_created: bool = False

    def __post_init__(self) -> None:
        for name in (
            "ensemble_id",
            "ensemble_version",
            "instrument",
            "axis",
            "target_id",
            "score_kind",
            "units",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if not self.venues or tuple(sorted(set(self.venues))) != self.venues:
            raise ScoreEnsembleError("venues must be non-empty, unique and sorted")
        cutoff = _utc(self.fit_cutoff, "fit_cutoff")
        observed = _utc(self.observed_at, "observed_at")
        available = _utc(self.available_at, "available_at")
        expires = _utc(self.expires_at, "expires_at")
        if cutoff > observed or observed > available or available >= expires:
            raise ScoreEnsembleError("invalid ensemble timestamp ordering")
        point = _finite(self.point_estimate, "point_estimate")
        lower = _finite(self.lower_bound, "lower_bound")
        upper = _finite(self.upper_bound, "upper_bound")
        if lower > point or point > upper:
            raise ScoreEnsembleError("ensemble interval must contain point estimate")
        if self.score_kind == "probability" and not 0 <= lower <= point <= upper <= 1:
            raise ScoreEnsembleError("probability ensemble must stay within [0, 1]")
        object.__setattr__(self, "confidence", _fraction(self.confidence, "confidence"))
        if tuple(sorted(set(self.member_score_digests))) != self.member_score_digests:
            raise ScoreEnsembleError("member score digests must be unique and sorted")
        for digest in self.member_score_digests:
            _digest(digest, "member_score_digest")
        object.__setattr__(self, "spec_digest", _digest(self.spec_digest, "spec_digest"))
        if self.evidence_status != "development":
            raise ScoreEnsembleError("new ensemble output must remain development evidence")
        if self.actionable_arm_id != "no_trade" or self.strategy_action_created:
            raise ScoreEnsembleError("score ensemble cannot create strategy or executable action")

    def _payload(self) -> dict[str, Any]:
        return {
            "actionable_arm_id": self.actionable_arm_id,
            "available_at": _iso(self.available_at),
            "axis": self.axis,
            "confidence": self.confidence,
            "ensemble_id": self.ensemble_id,
            "ensemble_version": self.ensemble_version,
            "evidence_status": self.evidence_status,
            "expires_at": _iso(self.expires_at),
            "fit_cutoff": _iso(self.fit_cutoff),
            "horizon_seconds": self.horizon_seconds,
            "instrument": self.instrument,
            "lower_bound": self.lower_bound,
            "member_score_digests": list(self.member_score_digests),
            "observed_at": _iso(self.observed_at),
            "point_estimate": self.point_estimate,
            "score_kind": self.score_kind,
            "spec_digest": self.spec_digest,
            "strategy_action_created": self.strategy_action_created,
            "target_id": self.target_id,
            "units": self.units,
            "upper_bound": self.upper_bound,
            "venues": list(self.venues),
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self._payload())

    def as_dict(self) -> dict[str, Any]:
        return {**self._payload(), "digest": self.digest}


def combine_same_target(
    *,
    spec: ConvexEnsembleSpec,
    members: Sequence[tuple[ScoreCatalogueEntry, MarketConditionScore]],
    decision_at: datetime,
) -> SameTargetEnsembleScore:
    """Combine predeclared eligible forecasts; never fit or revise weights."""

    decision = _utc(decision_at, "decision_at")
    by_identity: dict[str, tuple[ScoreCatalogueEntry, MarketConditionScore]] = {}
    for entry, score in members:
        if entry.identity in by_identity:
            raise ScoreEnsembleError(f"duplicate ensemble member: {entry.identity}")
        by_identity[entry.identity] = (entry, score)
    if set(by_identity) != set(spec.weights):
        raise ScoreEnsembleError("ensemble members do not exactly match frozen weight identities")

    instruments: set[str] = set()
    venues: set[str] = set()
    ordered: list[tuple[float, MarketConditionScore]] = []
    for identity, weight in spec.weights.items():
        entry, score = by_identity[identity]
        if not entry.matches(score):
            raise ScoreEnsembleError(f"member does not match catalogue entry: {identity}")
        if (
            entry.axis != spec.axis
            or entry.target_id != spec.target_id
            or entry.horizon_seconds != spec.horizon_seconds
            or entry.score_kind != spec.score_kind
            or entry.units != spec.units
        ):
            raise ScoreEnsembleError("ensemble member target, axis, horizon, kind or units differ")
        if entry.evidence_status not in ENSEMBLE_MEMBER_EVIDENCE:
            raise ScoreEnsembleError(f"ensemble member has unusable evidence: {identity}")
        if "same_target_ensemble" not in entry.permitted_uses:
            raise ScoreEnsembleError(f"ensemble use is not permitted for member: {identity}")
        if not score.eligible_for_conditioning(decision):
            raise ScoreEnsembleError(f"ensemble member is unknown, stale or unavailable: {identity}")
        instruments.add(score.instrument)
        venues.add(score.venue)
        ordered.append((weight, score))
    if len(instruments) != 1:
        raise ScoreEnsembleError("ensemble members must forecast the same instrument")

    def weighted(attribute: str) -> float:
        total = 0.0
        for weight, score in ordered:
            value = getattr(score, attribute)
            assert value is not None
            total += weight * value
        return total

    return SameTargetEnsembleScore(
        ensemble_id=spec.ensemble_id,
        ensemble_version=spec.ensemble_version,
        instrument=next(iter(instruments)),
        venues=tuple(sorted(venues)),
        axis=spec.axis,
        target_id=spec.target_id,
        horizon_seconds=spec.horizon_seconds,
        score_kind=spec.score_kind,
        units=spec.units,
        fit_cutoff=max(score.fit_cutoff for _, score in ordered),
        observed_at=max(score.observed_at for _, score in ordered),
        available_at=max(score.available_at for _, score in ordered),
        expires_at=min(score.expires_at for _, score in ordered),
        point_estimate=weighted("point_estimate"),
        lower_bound=weighted("lower_bound"),
        upper_bound=weighted("upper_bound"),
        confidence=min(score.confidence for _, score in ordered),
        member_score_digests=tuple(sorted(score.digest for _, score in ordered)),
        spec_digest=spec.digest,
    )
