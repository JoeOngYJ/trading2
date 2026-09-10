"""Offline contracts for the A1 XLON and listed-futures expansion.

The types in this module are research records only.  They intentionally have no
runtime signal, order, broker, database, or network dependency.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping, Sequence


EXPERIMENT_ID = "cross-asset-a1-lse-futures-expansion-v1"
SCHEMA_VERSION = "cross-asset-a1-lse-futures-expansion-contract-v1"
LSE_INSTRUMENTS = (
    ("SWDA", "SWDA:LSE", "IE00B4L5Y983", "global_equity", "GBp", "0.01", "2009-10-05"),
    ("VAGS", "VAGS:LSE", "IE00BG47K971", "sovereign_bond", "GBP", "1", "2019-06-27"),
    ("SGLN", "SGLN:LSE", "IE00B4ND3602", "gold", "GBp", "0.01", "2011-04-18"),
    ("COMM", "COMM:LSE", "IE00BDFL4P12", "commodity", "GBp", "0.01", "2017-07-27"),
)
FUTURES = (
    ("MES", "ES", "XCME", "global_equity", "2009-10-05", "2019-05-06"),
    ("MGC", "GC", "XCEC", "gold", "2009-10-05", "2010-10-04"),
    ("MCL", "CL", "XNYM", "energy", "2009-10-05", "2021-07-12"),
    ("M6E", "6E", "XCME", "foreign_exchange", "2009-10-05", "2009-10-05"),
    ("MTN", "TN", "XCBT", "sovereign_rates", "2016-01-11", "2024-03-25"),
)
SOURCE_IDS = ("cme_datamine", "databento")
IMPLICIT_ROUND_TRIP_BPS = (10, 30, 80)


class A1ExpansionError(ValueError):
    """Raised when an A1 expansion record fails closed."""


@dataclass(frozen=True, slots=True)
class ProviderRequest:
    symbol: str
    endpoint: str
    path: str
    parameters: Mapping[str, str]
    filename: str
    phase: int
    weight: int


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        indent=2,
        sort_keys=True,
        separators=(",", ": "),
    ) + "\n"


def canonical_json_line(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def record_digest(record: Mapping[str, Any]) -> str:
    payload = {key: value for key, value in record.items() if key != "digest"}
    return hashlib.sha256(canonical_json_line(payload).encode("utf-8")).hexdigest()


def _utc(raw: str, label: str) -> datetime:
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise A1ExpansionError(f"invalid {label}") from exc
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise A1ExpansionError(f"{label} must use explicit UTC")
    return value


def _day(raw: str, label: str) -> date:
    try:
        return date.fromisoformat(raw)
    except (TypeError, ValueError) as exc:
        raise A1ExpansionError(f"invalid {label}") from exc


def _decimal(raw: Any, label: str, *, positive: bool = False) -> Decimal:
    if isinstance(raw, bool):
        raise A1ExpansionError(f"invalid {label}")
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, ValueError) as exc:
        raise A1ExpansionError(f"invalid {label}") from exc
    if not value.is_finite() or positive and value <= 0 or not positive and value < 0:
        raise A1ExpansionError(f"invalid {label}")
    return value


def _digest(raw: str, label: str) -> None:
    if not isinstance(raw, str) or len(raw) != 64:
        raise A1ExpansionError(f"invalid {label}")
    try:
        int(raw, 16)
    except ValueError as exc:
        raise A1ExpansionError(f"invalid {label}") from exc


@dataclass(frozen=True, slots=True)
class QualifiedInstrument:
    instrument_id: str
    family: str
    evidence_status: str
    usable_start: str
    usable_end: str
    currency: str
    evidence_digest: str
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if self.evidence_status not in {"candidate", "qualified", "rejected", "blocked"}:
            raise A1ExpansionError("invalid instrument evidence status")
        if _day(self.usable_start, "usable_start") > _day(self.usable_end, "usable_end"):
            raise A1ExpansionError("instrument usable boundary is reversed")
        if _day(self.usable_end, "usable_end").year >= 2026:
            raise A1ExpansionError("sealed 2026 observations are ineligible")
        _digest(self.evidence_digest, "instrument evidence digest")
        if self.evidence_status in {"rejected", "blocked"} and not self.rejection_reason:
            raise A1ExpansionError("failed instrument requires a reason")
        if self.evidence_status == "qualified" and self.rejection_reason is not None:
            raise A1ExpansionError("qualified instrument cannot have a rejection reason")


@dataclass(frozen=True, slots=True)
class FuturesContractObservation:
    venue: str
    root: str
    contract_id: str
    expiry: str
    observed_at: str
    available_at: str
    settlement: str
    volume: str
    open_interest: str
    source_digest: str

    def __post_init__(self) -> None:
        observed = _utc(self.observed_at, "observed_at")
        available = _utc(self.available_at, "available_at")
        if available < observed:
            raise A1ExpansionError("availability precedes observation")
        if observed.year >= 2026:
            raise A1ExpansionError("sealed 2026 observations are ineligible")
        if _day(self.expiry, "expiry") < observed.date():
            raise A1ExpansionError("observation follows contract expiry")
        _decimal(self.settlement, "settlement", positive=True)
        _decimal(self.volume, "volume")
        _decimal(self.open_interest, "open_interest")
        _digest(self.source_digest, "source digest")


@dataclass(frozen=True, slots=True)
class FuturesRollDecision:
    root: str
    decision_at: str
    effective_at: str
    old_contract_id: str
    new_contract_id: str
    reason: str
    sessions_before_delivery_risk: int
    lineage_digest: str

    def __post_init__(self) -> None:
        decision = _utc(self.decision_at, "roll decision_at")
        effective = _utc(self.effective_at, "roll effective_at")
        if effective <= decision:
            raise A1ExpansionError("roll must become effective after its decision")
        if decision.year >= 2026 or effective.year >= 2026:
            raise A1ExpansionError("sealed 2026 roll is ineligible")
        if self.old_contract_id == self.new_contract_id:
            raise A1ExpansionError("roll contracts must differ")
        if self.reason not in {"prior_session_volume_crossover", "forced_pre_delivery"}:
            raise A1ExpansionError("invalid roll reason")
        if self.sessions_before_delivery_risk < 5:
            raise A1ExpansionError("roll violates five-session delivery buffer")
        _digest(self.lineage_digest, "roll lineage digest")


@dataclass(frozen=True, slots=True)
class ParentMicroBridge:
    micro_root: str
    parent_root: str
    overlap_sessions: int
    maximum_settlement_difference_ticks: str
    status: str
    evidence_digest: str

    def __post_init__(self) -> None:
        expected = {item[0]: item[1] for item in FUTURES}
        if expected.get(self.micro_root) != self.parent_root:
            raise A1ExpansionError("parent/micro mapping changed")
        if self.status not in {"candidate", "accepted", "rejected"}:
            raise A1ExpansionError("invalid bridge status")
        if self.overlap_sessions < 0:
            raise A1ExpansionError("negative bridge overlap")
        _decimal(self.maximum_settlement_difference_ticks, "bridge settlement difference")
        _digest(self.evidence_digest, "bridge evidence digest")


@dataclass(frozen=True, slots=True)
class EffectiveCostSchedule:
    instrument_id: str
    effective_from: str
    explicit_per_side: Mapping[str, str]
    implicit_round_trip_bps: Sequence[int]
    cash_or_collateral_yield_policy: str
    source_digest: str

    def __post_init__(self) -> None:
        _day(self.effective_from, "cost effective_from")
        if tuple(self.implicit_round_trip_bps) != IMPLICIT_ROUND_TRIP_BPS:
            raise A1ExpansionError("implicit cost scenarios changed")
        if not self.explicit_per_side:
            raise A1ExpansionError("explicit cost schedule is empty")
        for key, value in self.explicit_per_side.items():
            _decimal(value, f"cost {key}")
        if self.cash_or_collateral_yield_policy != "zero_percent_primary":
            raise A1ExpansionError("cash/collateral yield policy changed")
        _digest(self.source_digest, "cost source digest")


def choose_source(candidates: Sequence[Mapping[str, Any]]) -> str | None:
    """Apply the frozen price/authority rule without requesting or inspecting prices."""
    passing: dict[str, Decimal] = {}
    for item in candidates:
        source_id = item.get("source_id")
        if source_id not in SOURCE_IDS:
            raise A1ExpansionError("unknown futures source candidate")
        gates = item.get("gates", {})
        required = {
            "authorized_distribution",
            "contract_definitions",
            "exact_boundary_coverage",
            "final_settlements",
            "private_research_retention",
            "publication_timestamps",
            "reproducible_retrieval",
        }
        if set(gates) != required or any(value not in {True, False} for value in gates.values()):
            raise A1ExpansionError("source gate set changed")
        if all(gates.values()):
            passing[str(source_id)] = _decimal(item.get("twelve_month_tco_usd"), "source TCO")
    if not passing:
        return None
    if len(passing) == 1:
        return next(iter(passing))
    cme = passing["cme_datamine"]
    vendor = passing["databento"]
    # Prefer the direct exchange unless the authorized vendor is over 10% cheaper.
    return "databento" if vendor < cme * Decimal("0.90") else "cme_datamine"


def build_lse_request_specs(contract: Mapping[str, Any]) -> tuple[ProviderRequest, ...]:
    acquisition = contract["lse_acquisition"]
    query = acquisition["query"]
    paths = acquisition["endpoint_paths"]
    weights = acquisition["endpoint_credit_weights"]
    end = acquisition["end_date_exclusive"]
    specs: list[ProviderRequest] = []
    for item in contract["listed_funds"]:
        slug = item["symbol"].casefold()
        specs.append(
            ProviderRequest(
                symbol=item["symbol"],
                endpoint="time_series",
                path=paths["time_series"],
                parameters={
                    **query,
                    "end_date": end,
                    "start_date": item["usable_start"],
                    "symbol": item["provider_symbol"],
                },
                filename=f"{slug}-time-series.json",
                phase=1,
                weight=int(weights["time_series"]),
            )
        )
    for phase, item in enumerate(contract["listed_funds"], start=1):
        slug = item["symbol"].casefold()
        for endpoint in ("dividends", "splits"):
            specs.append(
                ProviderRequest(
                    symbol=item["symbol"],
                    endpoint=endpoint,
                    path=paths[endpoint],
                    parameters={
                        "end_date": "2025-12-31",
                        "order": "ASC",
                        "outputsize": "5000",
                        "start_date": item["usable_start"],
                        "symbol": item["provider_symbol"],
                    },
                    filename=f"{slug}-{endpoint}.json",
                    phase=phase,
                    weight=int(weights[endpoint]),
                )
            )
    if len(specs) != acquisition["maximum_requests"]:
        raise A1ExpansionError("LSE request count changed")
    if sum(item.weight for item in specs) != acquisition["maximum_weighted_credits"]:
        raise A1ExpansionError("LSE weighted request budget changed")
    phase_weights = {
        phase: sum(item.weight for item in specs if item.phase == phase)
        for phase in range(1, 5)
    }
    if phase_weights != {1: 44, 2: 40, 3: 40, 4: 40}:
        raise A1ExpansionError("LSE phase budget changed")
    if any("apikey" in key.casefold() for item in specs for key in item.parameters):
        raise A1ExpansionError("LSE request attempts to serialize a token")
    return tuple(specs)


def load_contract(path: Path, repo_root: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
        payload = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise A1ExpansionError(f"cannot read A1 expansion contract: {path}") from exc
    if not isinstance(payload, dict) or raw != canonical_json(payload):
        raise A1ExpansionError("A1 expansion contract must be canonical JSON")
    validate_contract(payload, repo_root)
    return payload


def validate_contract(payload: Mapping[str, Any], repo_root: Path) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION or payload.get("experiment_id") != EXPERIMENT_ID:
        raise A1ExpansionError("unexpected A1 expansion contract")
    if payload.get("status") != "frozen":
        raise A1ExpansionError("A1 expansion contract must be frozen")
    lse = payload.get("listed_funds")
    expected_lse = tuple(
        (
            item.get("symbol"),
            item.get("provider_symbol"),
            item.get("isin"),
            item.get("family"),
            item.get("quote_unit"),
            item.get("price_to_gbp_multiplier"),
            item.get("usable_start"),
        )
        for item in lse or ()
    )
    if expected_lse != LSE_INSTRUMENTS or any(item.get("usable_end") != "2025-12-31" for item in lse or ()):
        raise A1ExpansionError("listed-fund universe or boundary changed")
    acquisition = payload.get("lse_acquisition", {})
    if acquisition.get("api_base_url") != "https://api.twelvedata.com":
        raise A1ExpansionError("LSE acquisition provider host changed")
    if acquisition.get("api_token_environment_variable") != "TWELVEDATA_API_KEY":
        raise A1ExpansionError("LSE acquisition token variable changed")
    if acquisition.get("api_token_may_be_logged_or_serialized") is not False:
        raise A1ExpansionError("LSE acquisition token cannot be serialized")
    if acquisition.get("existing_paid_subscription_use_authorized") is not True or acquisition.get("further_paid_upgrade_authorized") is not False:
        raise A1ExpansionError("LSE acquisition subscription boundary changed")
    if (
        acquisition.get("maximum_requests"),
        acquisition.get("maximum_weighted_credits"),
        acquisition.get("minute_credit_ceiling"),
    ) != (12, 164, 55):
        raise A1ExpansionError("LSE acquisition request budget changed")
    if acquisition.get("phase_offsets_seconds") != [0, 61, 122, 183]:
        raise A1ExpansionError("LSE acquisition phase schedule changed")
    if acquisition.get("end_date_exclusive") != "2026-01-01":
        raise A1ExpansionError("LSE acquisition exclusive end changed")
    if acquisition.get("query") != {
        "adjust": "none",
        "interval": "1day",
        "order": "ASC",
        "outputsize": "5000",
        "timezone": "UTC",
    }:
        raise A1ExpansionError("LSE acquisition query changed")
    futures = payload.get("listed_futures")
    expected_futures = tuple(
        (
            item.get("micro_root"),
            item.get("parent_root"),
            item.get("venue_mic"),
            item.get("family"),
            item.get("parent_usable_start"),
            item.get("micro_usable_start"),
        )
        for item in futures or ()
    )
    if expected_futures != FUTURES or any(item.get("usable_end") != "2025-12-31" for item in futures or ()):
        raise A1ExpansionError("futures universe or boundary changed")
    calendar_record = payload.get("xlon_calendar", {})
    if calendar_record.get("path") != "config/research/xlon-calendar-2009-2025-v1.json":
        raise A1ExpansionError("XLON calendar path changed")
    calendar_path = (repo_root / calendar_record["path"]).resolve(strict=True)
    if sha256_file(calendar_path) != calendar_record.get("sha256"):
        raise A1ExpansionError("XLON calendar checksum mismatch")
    comparison = payload.get("futures_source_comparison", {})
    if tuple(item.get("source_id") for item in comparison.get("candidates", ())) != SOURCE_IDS:
        raise A1ExpansionError("futures source candidates changed")
    if comparison.get("automatic_purchase_allowed") is not False:
        raise A1ExpansionError("futures data purchase requires user approval")
    if comparison.get("direct_source_tie_threshold_fraction") != "0.10":
        raise A1ExpansionError("source choice threshold changed")
    cost = payload.get("cost_policy", {})
    if tuple(cost.get("implicit_round_trip_bps", ())) != IMPLICIT_ROUND_TRIP_BPS:
        raise A1ExpansionError("cost scenarios changed")
    if cost.get("cash_and_collateral_yield") != "zero_percent_primary":
        raise A1ExpansionError("cash/collateral yield policy changed")
    roll = payload.get("roll_policy", {})
    if roll.get("minimum_sessions_before_delivery_risk") != 5:
        raise A1ExpansionError("delivery-risk buffer changed")
    if roll.get("vendor_continuous_series_allowed") is not False:
        raise A1ExpansionError("vendor continuous series must remain prohibited")
    for key, value in payload.get("prohibitions", {}).items():
        if value is not False:
            raise A1ExpansionError(f"unsafe A1 expansion permission: {key}")
