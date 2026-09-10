"""Immutable offline event records for BTC breakout-driver research.

This module deliberately does not retrieve data or consume prices.  It validates archived
event metadata, preserves publication and retrieval timing, and constructs deterministic
retrospective association controls.  It has no network, exchange, database, signal, order,
or production-runtime integration.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from types import MappingProxyType
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse
from zoneinfo import ZoneInfo


NEW_YORK = ZoneInfo("America/New_York")
UTC = timezone.utc

DRIVER_SUBTYPES = MappingProxyType(
    {
        "exchange_incident": frozenset({"official_exchange_notice"}),
        "macro": frozenset(
            {
                "cpi",
                "employment_situation",
                "fomc_minutes",
                "fomc_press_conference",
                "fomc_statement",
                "gdp",
                "pce",
            }
        ),
        "protocol": frozenset({"bitcoin_halving"}),
        "regulatory": frozenset({"sec_publication"}),
    }
)
SOURCE_AUTHORITIES = frozenset(
    {"official_primary", "qualified_public_surprise", "curated_secondary"}
)
AVAILABILITY_QUALITIES = frozenset(
    {
        "conflicting",
        "date_only",
        "exact_publication_time",
        "retrospective_unknown",
        "scheduled_time_only",
    }
)
TIME_BASES = frozenset({"America/New_York", "UTC"})
TIMING_QUALITIES = frozenset({"exact_publication_time", "scheduled_time_only"})
MATCH_STRATA_KEYS = frozenset(
    {"past_only_compression_percentile_decile", "past_only_sigma24_decile"}
)
DECILES = frozenset(range(10))
CONTROL_OFFSETS_WEEKS = (-2, -1, 1, 2)
ASSOCIATION_WINDOW = timedelta(hours=4)
DECILE_METHOD = "past_only_empirical_midrank_floor_10p_cap_9_ties_average_rank"
SURPRISE_METHODS = frozenset(
    {"initial_minus_expectation", "qualified_public_standardized_surprise"}
)
OFFICIAL_SOURCE_HOSTS = frozenset(
    {
        "bea.gov",
        "binance.com",
        "bitcoincore.org",
        "bitfinex.com",
        "bls.gov",
        "bybit.com",
        "chicagofed.org",
        "coinbase.com",
        "federalreserve.gov",
        "kraken.com",
        "okx.com",
        "sec.gov",
    }
)

CONTRACT_EVENT_FAMILIES = MappingProxyType(
    {
        ("exchange_incident", "official_exchange_notice"): "major_exchange_material_events",
        ("macro", "cpi"): "US_CPI",
        ("macro", "employment_situation"): "US_employment_situation",
        ("macro", "fomc_minutes"): "FOMC_decisions",
        ("macro", "fomc_press_conference"): "FOMC_decisions",
        ("macro", "fomc_statement"): "FOMC_decisions",
        ("macro", "gdp"): "US_GDP",
        ("macro", "pce"): "US_PCE_price_index",
        ("protocol", "bitcoin_halving"): "Bitcoin_protocol_material_events",
        ("regulatory", "sec_publication"): "SEC_BTC_material_actions",
    }
)
VALUE_STATUSES = frozenset({"initial", "not_applicable", "revised", "unchanged"})


class DriverLedgerError(ValueError):
    """Raised when driver metadata is ambiguous, future-dependent, or inconsistent."""


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DriverLedgerError(f"{label} must be a non-empty string")
    return value.strip()


def _utc(value: datetime, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise DriverLedgerError(f"{label} must be timezone-aware UTC")
    if value.utcoffset() != timedelta(0):
        raise DriverLedgerError(f"{label} must use UTC")
    return value.astimezone(UTC)


def _optional_utc(value: datetime | None, label: str) -> datetime | None:
    return None if value is None else _utc(value, label)


def _iso(value: datetime) -> str:
    return _utc(value, "timestamp").isoformat().replace("+00:00", "Z")


def _digest(value: str, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or value.lower() != value:
        raise DriverLedgerError(f"{label} must be a lowercase SHA-256 digest")
    try:
        int(value, 16)
    except ValueError as exc:
        raise DriverLedgerError(f"{label} must be hexadecimal") from exc
    return value


def _https_url(value: str, label: str) -> str:
    url = _text(value, label)
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise DriverLedgerError(f"{label} must be an absolute credential-free HTTPS URL")
    return url


def _qualified_source_url(value: str, label: str, *, synthetic_fixture: bool) -> str:
    url = _https_url(value, label)
    if synthetic_fixture:
        return url
    host = (urlparse(url).hostname or "").lower()
    if not any(host == allowed or host.endswith(f".{allowed}") for allowed in OFFICIAL_SOURCE_HOSTS):
        raise DriverLedgerError(f"{label} is not on a frozen official-source domain")
    return url


def _optional_decimal(value: object | None, label: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise DriverLedgerError(f"{label} must be a finite decimal")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise DriverLedgerError(f"{label} must be a finite decimal") from exc
    if not number.is_finite():
        raise DriverLedgerError(f"{label} must be a finite decimal")
    if number == 0:
        return "0"
    rendered = format(number.normalize(), "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


def _sorted_unique(values: Sequence[str], label: str) -> tuple[str, ...]:
    normalized = tuple(sorted(_text(value, label) for value in values))
    if len(normalized) != len(set(normalized)):
        raise DriverLedgerError(f"{label} contains duplicates")
    return normalized


def _frozen_strata(values: Mapping[str, object], label: str) -> Mapping[str, object]:
    if not isinstance(values, Mapping) or not values:
        raise DriverLedgerError(f"{label} must be a non-empty mapping")
    normalized: dict[str, object] = {}
    for raw_key, raw_value in values.items():
        key = _text(raw_key, f"{label} key")
        if isinstance(raw_value, bool):
            raise DriverLedgerError(f"{label}[{key}] cannot be boolean")
        value = raw_value if isinstance(raw_value, int) else _text(str(raw_value), f"{label}[{key}]")
        if key in normalized:
            raise DriverLedgerError(f"{label} contains duplicate key: {key}")
        normalized[key] = value
    return MappingProxyType(dict(sorted(normalized.items())))


def causal_midrank_decile(value: float, past_values: Sequence[float]) -> int:
    """Map a value to a causal 0..9 empirical decile with average-rank tie handling."""

    if isinstance(value, bool) or not math.isfinite(float(value)):
        raise DriverLedgerError("decile value must be finite")
    if not past_values:
        raise DriverLedgerError("past_values cannot be empty")
    normalized: list[float] = []
    for item in past_values:
        if isinstance(item, bool) or not math.isfinite(float(item)):
            raise DriverLedgerError("past_values must be finite")
        normalized.append(float(item))
    number = float(value)
    less = sum(item < number for item in normalized)
    equal = sum(item == number for item in normalized)
    percentile = (less + 0.5 * equal) / len(normalized)
    return min(9, int(math.floor(10.0 * percentile)))


def canonical_json(value: Any) -> str:
    """Return newline-terminated deterministic JSON."""

    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True, separators=(",", ": ")
    ) + "\n"


def canonical_digest(value: Any) -> str:
    rendered = json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def new_york_to_utc(value: datetime, *, fold: int | None = None) -> datetime:
    """Convert a naive New York wall time to UTC, rejecting DST gaps and ambiguity.

    ``fold`` must be supplied for repeated fall-back wall times.  Supplying it for an
    ordinary wall time is allowed only as zero.  This keeps archived conversion evidence
    explicit instead of relying on a host's local timezone.
    """

    if not isinstance(value, datetime) or value.tzinfo is not None:
        raise DriverLedgerError("New York wall time must be a naive datetime")
    if fold not in {None, 0, 1}:
        raise DriverLedgerError("fold must be 0, 1, or omitted")

    candidates: list[tuple[int, datetime]] = []
    for candidate_fold in (0, 1):
        aware = value.replace(tzinfo=NEW_YORK, fold=candidate_fold)
        converted = aware.astimezone(UTC)
        round_trip = converted.astimezone(NEW_YORK)
        if round_trip.replace(tzinfo=None) == value and round_trip.fold == candidate_fold:
            candidates.append((candidate_fold, converted))
    unique = {candidate for _, candidate in candidates}
    if not unique:
        raise DriverLedgerError("New York wall time falls in a DST gap")
    if len(unique) > 1:
        if fold is None:
            raise DriverLedgerError("New York wall time is DST-ambiguous; fold is required")
        return next(converted for candidate_fold, converted in candidates if candidate_fold == fold)
    if fold == 1:
        raise DriverLedgerError("fold=1 is invalid for an unambiguous New York wall time")
    return next(iter(unique))


def _validate_time_basis(
    utc_value: datetime | None,
    basis: str | None,
    local_value: datetime | None,
    fold: int | None,
    label: str,
) -> tuple[str | None, datetime | None, int | None]:
    if utc_value is None:
        if basis is not None or local_value is not None or fold is not None:
            raise DriverLedgerError(f"{label} time evidence exists without {label}_at")
        return None, None, None
    selected = "UTC" if basis is None else basis
    if selected not in TIME_BASES:
        raise DriverLedgerError(f"unsupported {label}_time_basis: {selected}")
    if selected == "UTC":
        if local_value is not None or fold is not None:
            raise DriverLedgerError(f"UTC {label} cannot contain New York wall-time evidence")
        return selected, None, None
    if local_value is None:
        raise DriverLedgerError(f"America/New_York {label} requires its source wall time")
    converted = new_york_to_utc(local_value, fold=fold)
    if converted != utc_value:
        raise DriverLedgerError(f"{label} UTC value does not match New York wall time")
    return selected, local_value, fold


@dataclass(frozen=True, slots=True)
class DriverEvent:
    """One archived event observation; never a claim that the event caused a price move."""

    event_id: str
    family: str
    subtype: str
    title: str
    observed_at: datetime
    available_at: datetime
    retrieved_at: datetime
    ledger_cutoff_at: datetime
    source_url: str
    source_digest: str
    source_authority: str
    availability_quality: str
    vintage_or_revision_id: str
    value_status: str
    synthetic_fixture: bool = False
    scheduled_at: datetime | None = None
    actual_at: datetime | None = None
    scheduled_time_basis: str | None = None
    scheduled_local: datetime | None = None
    scheduled_fold: int | None = None
    actual_time_basis: str | None = None
    actual_local: datetime | None = None
    actual_fold: int | None = None
    value_unit: str | None = None
    initial_value: object | None = None
    previous_value: object | None = None
    revised_value: object | None = None
    revision_observed_at: datetime | None = None
    revision_available_at: datetime | None = None
    expectation_value: object | None = None
    expectation_observed_at: datetime | None = None
    expectation_available_at: datetime | None = None
    expectation_source_url: str | None = None
    expectation_source_digest: str | None = None
    surprise_value: object | None = None
    surprise_method: str | None = None
    batch_id: str | None = None
    batch_members: Sequence[str] = ()
    confounds: Sequence[str] = ()
    eligible_for_timing_test: bool = False
    eligible_for_directional_test: bool = False
    eligible_for_association_test: bool = False

    def __post_init__(self) -> None:
        for name in ("event_id", "title"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if self.family not in DRIVER_SUBTYPES:
            raise DriverLedgerError(f"unsupported driver family: {self.family}")
        if self.subtype not in DRIVER_SUBTYPES[self.family]:
            raise DriverLedgerError(f"unsupported {self.family} subtype: {self.subtype}")
        if self.source_authority not in SOURCE_AUTHORITIES:
            raise DriverLedgerError(f"unsupported source_authority: {self.source_authority}")
        if self.availability_quality not in AVAILABILITY_QUALITIES:
            raise DriverLedgerError(
                f"unsupported availability_quality: {self.availability_quality}"
            )
        object.__setattr__(
            self,
            "vintage_or_revision_id",
            _text(self.vintage_or_revision_id, "vintage_or_revision_id"),
        )
        if self.value_status not in VALUE_STATUSES:
            raise DriverLedgerError(f"unsupported value_status: {self.value_status}")
        if not isinstance(self.synthetic_fixture, bool):
            raise DriverLedgerError("synthetic_fixture must be boolean")
        object.__setattr__(
            self,
            "source_url",
            _qualified_source_url(
                self.source_url, "source_url", synthetic_fixture=self.synthetic_fixture
            ),
        )
        object.__setattr__(self, "source_digest", _digest(self.source_digest, "source_digest"))

        observed = _utc(self.observed_at, "observed_at")
        available = _utc(self.available_at, "available_at")
        retrieved = _utc(self.retrieved_at, "retrieved_at")
        cutoff = _utc(self.ledger_cutoff_at, "ledger_cutoff_at")
        scheduled = _optional_utc(self.scheduled_at, "scheduled_at")
        actual = _optional_utc(self.actual_at, "actual_at")
        if observed > available or available > retrieved or retrieved > cutoff:
            raise DriverLedgerError(
                "timestamps must satisfy observed_at <= available_at <= retrieved_at "
                "<= ledger_cutoff_at"
            )
        if actual is not None and actual > observed:
            raise DriverLedgerError("actual_at cannot follow observed_at")
        for name, value in (("scheduled_at", scheduled), ("actual_at", actual)):
            if value is not None and value > cutoff:
                raise DriverLedgerError(f"{name} cannot be future-dated beyond ledger cutoff")
        if scheduled is None and actual is None:
            raise DriverLedgerError("an event requires scheduled_at or actual_at")

        scheduled_basis, scheduled_local, scheduled_fold = _validate_time_basis(
            scheduled,
            self.scheduled_time_basis,
            self.scheduled_local,
            self.scheduled_fold,
            "scheduled",
        )
        actual_basis, actual_local, actual_fold = _validate_time_basis(
            actual,
            self.actual_time_basis,
            self.actual_local,
            self.actual_fold,
            "actual",
        )
        object.__setattr__(self, "scheduled_time_basis", scheduled_basis)
        object.__setattr__(self, "scheduled_local", scheduled_local)
        object.__setattr__(self, "scheduled_fold", scheduled_fold)
        object.__setattr__(self, "actual_time_basis", actual_basis)
        object.__setattr__(self, "actual_local", actual_local)
        object.__setattr__(self, "actual_fold", actual_fold)

        if self.availability_quality == "exact_publication_time" and actual is None:
            raise DriverLedgerError("exact publication quality requires actual_at")
        if self.availability_quality == "scheduled_time_only" and scheduled is None:
            raise DriverLedgerError("scheduled-time-only quality requires scheduled_at")

        normalized_values = {}
        for name in (
            "initial_value",
            "previous_value",
            "revised_value",
            "expectation_value",
            "surprise_value",
        ):
            normalized_values[name] = _optional_decimal(getattr(self, name), name)
            object.__setattr__(self, name, normalized_values[name])
        has_value = any(value is not None for value in normalized_values.values())
        if has_value:
            object.__setattr__(self, "value_unit", _text(self.value_unit, "value_unit"))
        elif self.value_unit is not None:
            raise DriverLedgerError("value_unit cannot exist without a numeric value")
        if self.value_status == "not_applicable" and has_value:
            raise DriverLedgerError("not_applicable value_status cannot contain numeric values")
        if self.value_status in {"initial", "unchanged"} and self.initial_value is None:
            raise DriverLedgerError(f"{self.value_status} value_status requires initial_value")
        if self.value_status == "initial" and self.revised_value is not None:
            raise DriverLedgerError("initial value_status cannot contain a revision")
        if self.value_status == "revised" and self.revised_value is None:
            raise DriverLedgerError("revised value_status requires revised_value")

        revision_observed = _optional_utc(self.revision_observed_at, "revision_observed_at")
        revision_available = _optional_utc(self.revision_available_at, "revision_available_at")
        if self.revised_value is None:
            if revision_observed is not None or revision_available is not None:
                raise DriverLedgerError("revision timestamps require revised_value")
        else:
            if self.initial_value is None or revision_observed is None or revision_available is None:
                raise DriverLedgerError(
                    "revised_value requires initial_value and both revision timestamps"
                )
            if not (available <= revision_observed <= revision_available <= retrieved):
                raise DriverLedgerError(
                    "revision timestamps must be point-in-time and no later than retrieval"
                )

        expectation_observed = _optional_utc(
            self.expectation_observed_at, "expectation_observed_at"
        )
        expectation_available = _optional_utc(
            self.expectation_available_at, "expectation_available_at"
        )
        if self.expectation_value is None:
            if (
                expectation_observed is not None
                or expectation_available is not None
                or self.expectation_source_url is not None
                or self.expectation_source_digest is not None
            ):
                raise DriverLedgerError("expectation lineage requires expectation_value")
        else:
            if (
                expectation_observed is None
                or expectation_available is None
                or self.expectation_source_url is None
                or self.expectation_source_digest is None
            ):
                raise DriverLedgerError(
                    "expectation_value requires timestamps and independent source lineage"
                )
            object.__setattr__(
                self,
                "expectation_source_url",
                _qualified_source_url(
                    self.expectation_source_url,
                    "expectation_source_url",
                    synthetic_fixture=self.synthetic_fixture,
                ),
            )
            object.__setattr__(
                self,
                "expectation_source_digest",
                _digest(self.expectation_source_digest, "expectation_source_digest"),
            )
            event_anchor = actual or scheduled
            assert event_anchor is not None
            if not (
                expectation_observed <= expectation_available <= event_anchor
                and expectation_available <= retrieved
            ):
                raise DriverLedgerError("expectation was not available before the event")
        if self.surprise_value is None:
            if self.surprise_method is not None:
                raise DriverLedgerError("surprise_method requires surprise_value")
        else:
            object.__setattr__(self, "surprise_method", _text(self.surprise_method, "surprise_method"))
            if self.surprise_method not in SURPRISE_METHODS:
                raise DriverLedgerError(f"unsupported surprise_method: {self.surprise_method}")
            if self.expectation_value is None:
                raise DriverLedgerError("surprise_value requires point-in-time expectation_value")
            if self.surprise_method == "initial_minus_expectation":
                if self.initial_value is None:
                    raise DriverLedgerError("raw surprise requires initial_value")
                expected = Decimal(self.initial_value) - Decimal(self.expectation_value)
                if expected != Decimal(self.surprise_value):
                    raise DriverLedgerError("surprise_value does not equal initial minus expectation")
            if (
                self.surprise_method == "qualified_public_standardized_surprise"
                and self.source_authority != "qualified_public_surprise"
            ):
                raise DriverLedgerError(
                    "standardized surprise requires qualified_public_surprise source authority"
                )

        members = _sorted_unique(self.batch_members, "batch_members")
        confounds = _sorted_unique(self.confounds, "confounds")
        if self.batch_id is None:
            if members:
                raise DriverLedgerError("batch_members require batch_id")
        else:
            object.__setattr__(self, "batch_id", _text(self.batch_id, "batch_id"))
            if self.event_id not in members:
                raise DriverLedgerError("batch_members must include this event_id")
        object.__setattr__(self, "batch_members", members)
        object.__setattr__(self, "confounds", confounds)

        if self.source_authority == "curated_secondary" and (
            self.eligible_for_timing_test
            or self.eligible_for_directional_test
            or self.eligible_for_association_test
        ):
            raise DriverLedgerError("curated secondary records are descriptive only")
        if self.eligible_for_timing_test:
            if self.availability_quality not in TIMING_QUALITIES:
                raise DriverLedgerError("timing eligibility overstates timestamp quality")
        if self.eligible_for_directional_test:
            if (
                self.availability_quality != "exact_publication_time"
                or self.surprise_value is None
                or self.expectation_available_at is None
                or self.source_authority == "curated_secondary"
            ):
                raise DriverLedgerError("directional eligibility requires qualified point-in-time surprise")
        if self.eligible_for_association_test:
            if (
                self.availability_quality != "exact_publication_time"
                or actual is None
                or self.source_authority == "curated_secondary"
            ):
                raise DriverLedgerError(
                    "association eligibility requires exact qualified publication timing"
                )

    def _payload(self) -> dict[str, Any]:
        def local(value: datetime | None) -> str | None:
            return None if value is None else value.isoformat(timespec="seconds")

        return {
            "actual_at": None if self.actual_at is None else _iso(self.actual_at),
            "actual_fold": self.actual_fold,
            "actual_local": local(self.actual_local),
            "actual_time_basis": self.actual_time_basis,
            "availability_quality": self.availability_quality,
            "available_at": _iso(self.available_at),
            "batch_id": self.batch_id,
            "batch_members": list(self.batch_members),
            "confounds": list(self.confounds),
            "eligibility": {
                "association_test": self.eligible_for_association_test,
                "directional_test": self.eligible_for_directional_test,
                "timing_test": self.eligible_for_timing_test,
            },
            "event_id": self.event_id,
            "event_family": CONTRACT_EVENT_FAMILIES[(self.family, self.subtype)],
            "expectation_available_at": (
                None if self.expectation_available_at is None else _iso(self.expectation_available_at)
            ),
            "expectation_observed_at": (
                None if self.expectation_observed_at is None else _iso(self.expectation_observed_at)
            ),
            "expectation_source_digest": self.expectation_source_digest,
            "expectation_source_url": self.expectation_source_url,
            "expectation_value": self.expectation_value,
            "family": self.family,
            "initial_value": self.initial_value,
            "ledger_cutoff_at": _iso(self.ledger_cutoff_at),
            "observed_at": _iso(self.observed_at),
            "previous_value": self.previous_value,
            "retrieved_at": _iso(self.retrieved_at),
            "revised_value": self.revised_value,
            "revision_available_at": (
                None if self.revision_available_at is None else _iso(self.revision_available_at)
            ),
            "revision_observed_at": (
                None if self.revision_observed_at is None else _iso(self.revision_observed_at)
            ),
            "scheduled_at": None if self.scheduled_at is None else _iso(self.scheduled_at),
            "scheduled_fold": self.scheduled_fold,
            "scheduled_local": local(self.scheduled_local),
            "scheduled_time_basis": self.scheduled_time_basis,
            "source_authority": self.source_authority,
            "source_digest": self.source_digest,
            "source_sha256": self.source_digest,
            "source_url": self.source_url,
            "subtype": self.subtype,
            "synthetic_fixture": self.synthetic_fixture,
            "surprise_method": self.surprise_method,
            "surprise_value": self.surprise_value,
            "title": self.title,
            "value_unit": self.value_unit,
            "value_status": self.value_status,
            "vintage_or_revision_id": self.vintage_or_revision_id,
            "release_at": _iso(self.actual_at or self.scheduled_at),
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self._payload())

    def as_dict(self) -> dict[str, Any]:
        return {**self._payload(), "record_digest": self.digest}


def validate_driver_events(events: Sequence[DriverEvent]) -> tuple[DriverEvent, ...]:
    """Validate identities, ordering, and simultaneous-release batches."""

    checked = tuple(sorted(events, key=lambda item: ((item.actual_at or item.scheduled_at), item.event_id)))
    if not checked:
        raise DriverLedgerError("driver ledger cannot be empty")
    ids = [event.event_id for event in checked]
    if len(ids) != len(set(ids)):
        raise DriverLedgerError("driver ledger contains duplicate event_id")
    cutoffs = {event.ledger_cutoff_at for event in checked}
    if len(cutoffs) != 1:
        raise DriverLedgerError("driver ledger events must share one ledger cutoff")

    by_time: dict[datetime, list[DriverEvent]] = {}
    by_batch: dict[str, list[DriverEvent]] = {}
    for event in checked:
        anchor = event.actual_at or event.scheduled_at
        assert anchor is not None
        by_time.setdefault(anchor, []).append(event)
        if event.batch_id is not None:
            by_batch.setdefault(event.batch_id, []).append(event)

    for anchor, simultaneous in by_time.items():
        if len(simultaneous) == 1:
            continue
        batch_ids = {event.batch_id for event in simultaneous}
        if len(batch_ids) != 1 or None in batch_ids:
            raise DriverLedgerError(
                f"simultaneous events at {_iso(anchor)} require one explicit batch"
            )
    for batch_id, batch in by_batch.items():
        if len(batch) < 2:
            raise DriverLedgerError(f"batch {batch_id} has no independently recorded companion")
        expected = tuple(sorted(event.event_id for event in batch))
        if any(event.batch_members != expected for event in batch):
            raise DriverLedgerError(f"batch {batch_id} has inconsistent membership")
        anchors = {event.actual_at or event.scheduled_at for event in batch}
        if len(anchors) != 1:
            raise DriverLedgerError(f"batch {batch_id} members do not share an event timestamp")
    return checked


@dataclass(frozen=True, slots=True)
class DriverLedger:
    events: Sequence[DriverEvent]
    schema_version: str = "btc-breakout-driver-ledger-v1"

    def __post_init__(self) -> None:
        if self.schema_version != "btc-breakout-driver-ledger-v1":
            raise DriverLedgerError("unsupported driver-ledger schema")
        object.__setattr__(self, "events", validate_driver_events(self.events))

    def _payload(self) -> dict[str, Any]:
        return {
            "event_count": len(self.events),
            "events": [event.as_dict() for event in self.events],
            "ledger_cutoff_at": _iso(self.events[0].ledger_cutoff_at),
            "schema_version": self.schema_version,
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self._payload())

    def as_dict(self) -> dict[str, Any]:
        return {**self._payload(), "digest": self.digest}


@dataclass(frozen=True, slots=True)
class EventMatchAnchor:
    event_id: str
    event_at: datetime
    strata_observed_at: datetime
    strata_available_at: datetime
    pre_event_strata: Mapping[str, object]
    event_digest: str
    feature_digest: str
    decile_method: str = DECILE_METHOD

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_id", _text(self.event_id, "event_id"))
        event_at = _utc(self.event_at, "event_at")
        observed = _utc(self.strata_observed_at, "strata_observed_at")
        available = _utc(self.strata_available_at, "strata_available_at")
        if observed > available or available > event_at:
            raise DriverLedgerError("event strata must be available no later than event_at")
        object.__setattr__(self, "pre_event_strata", _frozen_strata(self.pre_event_strata, "pre_event_strata"))
        object.__setattr__(self, "event_digest", _digest(self.event_digest, "event_digest"))
        object.__setattr__(self, "feature_digest", _digest(self.feature_digest, "feature_digest"))
        if self.decile_method != DECILE_METHOD:
            raise DriverLedgerError("event anchor uses an unsupported decile method")


@dataclass(frozen=True, slots=True)
class NonEventWindowCandidate:
    window_id: str
    window_at: datetime
    strata_observed_at: datetime
    strata_available_at: datetime
    pre_event_strata: Mapping[str, object]
    source_digest: str
    retrieved_at: datetime
    ledger_cutoff_at: datetime
    decile_method: str = DECILE_METHOD
    contains_known_event: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "window_id", _text(self.window_id, "window_id"))
        window = _utc(self.window_at, "window_at")
        observed = _utc(self.strata_observed_at, "strata_observed_at")
        available = _utc(self.strata_available_at, "strata_available_at")
        if observed > available or available > window:
            raise DriverLedgerError("candidate strata must be available no later than window_at")
        retrieved = _utc(self.retrieved_at, "retrieved_at")
        cutoff = _utc(self.ledger_cutoff_at, "ledger_cutoff_at")
        if window > retrieved or retrieved > cutoff:
            raise DriverLedgerError(
                "candidate timestamps must satisfy window_at <= retrieved_at <= ledger_cutoff_at"
            )
        object.__setattr__(self, "pre_event_strata", _frozen_strata(self.pre_event_strata, "pre_event_strata"))
        object.__setattr__(self, "source_digest", _digest(self.source_digest, "source_digest"))
        if self.decile_method != DECILE_METHOD:
            raise DriverLedgerError("candidate uses an unsupported decile method")

    @property
    def digest(self) -> str:
        return canonical_digest(
            {
                "contains_known_event": self.contains_known_event,
                "decile_method": self.decile_method,
                "pre_event_strata": dict(self.pre_event_strata),
                "ledger_cutoff_at": _iso(self.ledger_cutoff_at),
                "retrieved_at": _iso(self.retrieved_at),
                "source_digest": self.source_digest,
                "strata_available_at": _iso(self.strata_available_at),
                "strata_observed_at": _iso(self.strata_observed_at),
                "window_at": _iso(self.window_at),
                "window_id": self.window_id,
            }
        )


@dataclass(frozen=True, slots=True)
class MatchedNonEventWindow:
    event_id: str
    event_at: datetime
    window_id: str
    window_at: datetime
    pre_event_strata: Mapping[str, object]
    event_digest: str
    feature_digest: str
    candidate_digest: str
    lag_seconds: int
    control_offset_weeks: int
    retrospective_association_only: bool
    eligible_for_online_use: bool = False
    match_timezone: str = "America/New_York"

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "candidate_digest": self.candidate_digest,
            "control_offset_weeks": self.control_offset_weeks,
            "decile_method": DECILE_METHOD,
            "eligible_for_online_use": self.eligible_for_online_use,
            "event_at": _iso(self.event_at),
            "event_id": self.event_id,
            "event_digest": self.event_digest,
            "feature_digest": self.feature_digest,
            "lag_seconds": self.lag_seconds,
            "match_timezone": self.match_timezone,
            "pre_event_strata": dict(self.pre_event_strata),
            "retrospective_association_only": self.retrospective_association_only,
            "window_at": _iso(self.window_at),
            "window_id": self.window_id,
        }
        return {**payload, "digest": canonical_digest(payload)}


@dataclass(frozen=True, slots=True)
class MatchedWindowSelection:
    """Auditable output from one frozen deterministic matching policy."""

    matches: tuple[MatchedNonEventWindow, ...]
    unmatched_event_ids: tuple[str, ...]
    reused_candidate_ids: tuple[str, ...]
    control_offsets_weeks: tuple[int, ...]
    matching_policy: str
    driver_ledger_digest: str
    matching_contract_digest: str

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "matches": [item.as_dict() for item in self.matches],
            "control_offsets_weeks": list(self.control_offsets_weeks),
            "matching_policy": self.matching_policy,
            "driver_ledger_digest": self.driver_ledger_digest,
            "matching_contract_digest": self.matching_contract_digest,
            "reused_candidate_ids": list(self.reused_candidate_ids),
            "unmatched_event_ids": list(self.unmatched_event_ids),
        }
        return {**payload, "digest": canonical_digest(payload)}


def _validate_required_strata(
    values: Mapping[str, object]
) -> None:
    if set(values) != MATCH_STRATA_KEYS:
        raise DriverLedgerError("pre-event strata do not match the frozen required keys")
    for key in MATCH_STRATA_KEYS:
        if isinstance(values[key], bool) or values[key] not in DECILES:
            raise DriverLedgerError(f"pre-event stratum {key} is outside its frozen bins")


def _control_offset_weeks(event_at: datetime, candidate_at: datetime) -> int | None:
    event_local = event_at.astimezone(NEW_YORK).replace(tzinfo=None)
    candidate_local = candidate_at.astimezone(NEW_YORK).replace(tzinfo=None)
    for offset in CONTROL_OFFSETS_WEEKS:
        if candidate_local == event_local + timedelta(weeks=offset):
            return offset
    return None


def construct_matched_non_event_windows(
    ledger: DriverLedger,
    anchors: Sequence[EventMatchAnchor],
    candidates: Sequence[NonEventWindowCandidate],
    *,
    require_full_match: bool = True,
) -> MatchedWindowSelection:
    """Build exact adjacent-week association placebos under the frozen driver contract.

    Positive-offset controls use information observed after the target event and are marked
    retrospective-only.  No returned control is an online model feature.
    """

    ordered_anchors = tuple(sorted(anchors, key=lambda item: (item.event_at, item.event_id)))
    if not ordered_anchors:
        raise DriverLedgerError("match anchors cannot be empty")
    anchor_ids = [item.event_id for item in ordered_anchors]
    if len(anchor_ids) != len(set(anchor_ids)):
        raise DriverLedgerError("match anchors contain duplicate event_id")
    ledger_by_id = {event.event_id: event for event in ledger.events}
    for anchor in ordered_anchors:
        bound_event = ledger_by_id.get(anchor.event_id)
        if bound_event is None:
            raise DriverLedgerError(f"match anchor is absent from driver ledger: {anchor.event_id}")
        bound_time = bound_event.actual_at or bound_event.scheduled_at
        if anchor.event_at != bound_time or anchor.event_digest != bound_event.digest:
            raise DriverLedgerError(f"match anchor does not match driver ledger: {anchor.event_id}")
        if not bound_event.eligible_for_association_test:
            raise DriverLedgerError(
                f"match anchor is not association-eligible: {anchor.event_id}"
            )
        if bound_event.batch_id is not None:
            raise DriverLedgerError(
                f"batched release requires a separately checksummed batch anchor: {anchor.event_id}"
            )
        _validate_required_strata(anchor.pre_event_strata)
    ordered_candidates = tuple(sorted(candidates, key=lambda item: (item.window_at, item.window_id)))
    ids = [item.window_id for item in ordered_candidates]
    if len(ids) != len(set(ids)):
        raise DriverLedgerError("non-event candidates contain duplicate window_id")
    used: set[str] = set()
    result: list[MatchedNonEventWindow] = []
    unmatched: list[str] = []
    qualified_times = tuple(
        event.actual_at or event.scheduled_at
        for event in ledger.events
        if event.eligible_for_timing_test
    )

    for anchor in ordered_anchors:
        eligible: list[NonEventWindowCandidate] = []
        for candidate in ordered_candidates:
            _validate_required_strata(candidate.pre_event_strata)
            offset = _control_offset_weeks(anchor.event_at, candidate.window_at)
            if candidate.contains_known_event or offset is None:
                continue
            if candidate.window_id in used:
                continue
            if any(
                abs(candidate.window_at - qualified_at) <= ASSOCIATION_WINDOW
                for qualified_at in qualified_times
            ):
                continue
            if dict(candidate.pre_event_strata) != dict(anchor.pre_event_strata):
                continue
            eligible.append(candidate)
        eligible.sort(
            key=lambda item: (
                abs(_control_offset_weeks(anchor.event_at, item.window_at) or 0),
                item.window_at,
                item.window_id,
            )
        )
        chosen_by_offset: dict[int, NonEventWindowCandidate] = {}
        for candidate in eligible:
            offset = _control_offset_weeks(anchor.event_at, candidate.window_at)
            assert offset is not None
            chosen_by_offset.setdefault(offset, candidate)
        chosen = [chosen_by_offset[offset] for offset in CONTROL_OFFSETS_WEEKS if offset in chosen_by_offset]
        if len(chosen) != len(CONTROL_OFFSETS_WEEKS):
            unmatched.append(anchor.event_id)
        if require_full_match and len(chosen) != len(CONTROL_OFFSETS_WEEKS):
            raise DriverLedgerError(f"incomplete frozen control offsets for event {anchor.event_id}")
        for candidate in chosen:
            used.add(candidate.window_id)
            lag = int((anchor.event_at - candidate.window_at).total_seconds())
            offset = _control_offset_weeks(anchor.event_at, candidate.window_at)
            assert offset is not None
            result.append(
                MatchedNonEventWindow(
                    event_id=anchor.event_id,
                    event_at=anchor.event_at,
                    window_id=candidate.window_id,
                    window_at=candidate.window_at,
                    pre_event_strata=anchor.pre_event_strata,
                    event_digest=anchor.event_digest,
                    feature_digest=anchor.feature_digest,
                    candidate_digest=candidate.digest,
                    lag_seconds=lag,
                    control_offset_weeks=offset,
                    retrospective_association_only=offset > 0,
                )
            )
    policy = "exact_adjacent_week_deciles_without_replacement_timestamp_tiebreak"
    matching_contract = {
        "association_window_hours": int(ASSOCIATION_WINDOW.total_seconds() // 3600),
        "control_offsets_weeks": list(CONTROL_OFFSETS_WEEKS),
        "decile_method": DECILE_METHOD,
        "matching_policy": policy,
        "required_strata_keys": sorted(MATCH_STRATA_KEYS),
    }
    return MatchedWindowSelection(
        matches=tuple(result),
        unmatched_event_ids=tuple(unmatched),
        reused_candidate_ids=(),
        control_offsets_weeks=CONTROL_OFFSETS_WEEKS,
        matching_policy=policy,
        driver_ledger_digest=ledger.digest,
        matching_contract_digest=canonical_digest(matching_contract),
    )
