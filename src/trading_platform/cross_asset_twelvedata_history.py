"""Fail-closed contracts and offline audit helpers for Twelve Data full history."""

from __future__ import annotations

import json
import copy
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping, Sequence

from trading_platform.cross_asset_calendar import load_calendar
from trading_platform.cross_asset_twelvedata_audit import (
    TwelveDataAuditError,
    audit_time_series,
    canonical_json,
    load_contract as load_pilot_contract,
    parse_response,
    sha256_file,
)


CONTRACT_SCHEMA = "cross-asset-a1-twelvedata-full-history-contract-v1"
EXPERIMENT_ID = "cross-asset-a1-twelvedata-full-history-v1"
SUCCESSOR_EXPERIMENT_ID = "cross-asset-a1-twelvedata-full-history-v2"
MANIFEST_SCHEMA = "cross-asset-a1-twelvedata-full-history-source-manifest-v1"
EVIDENCE_SCHEMA = "cross-asset-a1-twelvedata-full-history-evidence-manifest-v1"
SYMBOLS = ("SPY", "EFA", "EEM", "IEF", "TLT", "GLD", "DBC", "BIL", "GBP/USD")
ETF_SYMBOLS = SYMBOLS[:-1]


class TwelveDataHistoryError(ValueError):
    """Raised when the frozen full-history contract or data fails closed."""


def _read_canonical(path: Path, label: str) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
        payload = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TwelveDataHistoryError(f"cannot read {label}: {path}") from exc
    if not isinstance(payload, dict) or raw != canonical_json(payload):
        raise TwelveDataHistoryError(f"{label} must be a canonical JSON object")
    return payload


def _repo_file(root: Path, raw_path: Any, label: str) -> Path:
    if not isinstance(raw_path, str) or not raw_path or Path(raw_path).is_absolute():
        raise TwelveDataHistoryError(f"{label} must be repository-relative")
    boundary = root.resolve(strict=True)
    try:
        path = (boundary / raw_path).resolve(strict=True)
        path.relative_to(boundary)
    except (OSError, ValueError) as exc:
        raise TwelveDataHistoryError(f"invalid {label}: {raw_path}") from exc
    if not path.is_file():
        raise TwelveDataHistoryError(f"{label} is not a regular file")
    return path


def _require_utc(raw: Any, label: str) -> datetime:
    if not isinstance(raw, str):
        raise TwelveDataHistoryError(f"{label} must be an explicit UTC timestamp")
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise TwelveDataHistoryError(f"invalid {label}") from exc
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise TwelveDataHistoryError(f"{label} must use explicit UTC")
    return value


def load_contract(path: Path, repo_root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    contract = _read_canonical(path, "Twelve Data full-history contract")
    if contract.get("schema_version") == "cross-asset-a1-twelvedata-full-history-amendment-v1":
        if contract.get("experiment_id") != SUCCESSOR_EXPERIMENT_ID or contract.get("supersedes") != EXPERIMENT_ID:
            raise TwelveDataHistoryError("unexpected full-history successor lineage")
        if contract.get("status") != "frozen" or contract.get("no_other_contract_field_changes") is not True:
            raise TwelveDataHistoryError("full-history successor must be frozen and minimal")
        base_record = contract.get("base_contract", {})
        base_path = _repo_file(repo_root, base_record.get("path"), "base history contract")
        if sha256_file(base_path) != base_record.get("sha256"):
            raise TwelveDataHistoryError("base history contract checksum changed")
        failure_record = contract.get("frozen_interruption_evidence", {})
        failure_path = _repo_file(repo_root, failure_record.get("path"), "history interruption evidence")
        if sha256_file(failure_path) != failure_record.get("sha256"):
            raise TwelveDataHistoryError("history interruption evidence checksum changed")
        expected_root = "artifacts/agent-level-experiment/cross-asset/a1-twelvedata-full-history-v2"
        if contract.get("changes_from_predecessor") != {"output_artifact_root": expected_root}:
            raise TwelveDataHistoryError("full-history successor changes are not minimal")
        effective, pilot, calendars = load_contract(base_path, repo_root)
        effective = copy.deepcopy(effective)
        effective["activated_at"] = contract["activated_at"]
        effective["experiment_id"] = SUCCESSOR_EXPERIMENT_ID
        effective["output"]["artifact_root"] = expected_root
        return effective, pilot, calendars
    if contract.get("schema_version") != CONTRACT_SCHEMA or contract.get("experiment_id") != EXPERIMENT_ID:
        raise TwelveDataHistoryError("unexpected Twelve Data full-history contract")
    if contract.get("status") != "frozen":
        raise TwelveDataHistoryError("full-history contract must be frozen")
    if tuple(contract.get("instruments", ())) != SYMBOLS:
        raise TwelveDataHistoryError("full-history universe changed")
    prohibitions = contract.get("prohibitions", {})
    for key in (
        "adjusted_price_use_allowed",
        "economic_metrics_allowed",
        "execution_approval_allowed",
        "execution_credentials_allowed",
        "feature_generation_allowed",
        "partial_ob0_access_allowed",
        "pnl_allowed",
        "protected_service_access_allowed",
        "return_calculation_allowed",
        "sealed_2026_access_allowed",
        "strategy_parameters_allowed",
        "strategy_signals_allowed",
    ):
        if prohibitions.get(key) is not False:
            raise TwelveDataHistoryError(f"unsafe history permission: {key}")
    access = contract.get("source_access", {})
    if access.get("api_base_url") != "https://api.twelvedata.com":
        raise TwelveDataHistoryError("provider host changed")
    if access.get("api_token_environment_variable") != "TWELVEDATA_API_KEY":
        raise TwelveDataHistoryError("provider token variable changed")
    if access.get("authorization_header_scheme") != "apikey":
        raise TwelveDataHistoryError("authorization scheme changed")
    if access.get("api_token_may_be_logged_or_serialized") is not False:
        raise TwelveDataHistoryError("token serialization must remain prohibited")
    if access.get("existing_paid_subscription_use_authorized") is not True:
        raise TwelveDataHistoryError("existing subscription use is not authorized")
    if access.get("further_paid_upgrade_authorized") is not False:
        raise TwelveDataHistoryError("full history cannot authorize another upgrade")
    lineage = contract.get("source_qualification_lineage", {})
    pilot_record = lineage.get("accepted_pilot_contract", {})
    pilot_path = _repo_file(repo_root, pilot_record.get("path"), "accepted pilot contract")
    if sha256_file(pilot_path) != pilot_record.get("sha256"):
        raise TwelveDataHistoryError("accepted pilot contract checksum changed")
    evidence_record = lineage.get("accepted_pilot_evidence", {})
    evidence_path = _repo_file(repo_root, evidence_record.get("path"), "accepted pilot evidence")
    if sha256_file(evidence_path) != evidence_record.get("sha256"):
        raise TwelveDataHistoryError("accepted pilot evidence checksum changed")
    pilot = load_pilot_contract(pilot_path, repo_root)
    if pilot.get("pilot_id") != "cross-asset-a1-twelvedata-economic-proxy-pilot-v2":
        raise TwelveDataHistoryError("history does not descend from accepted v2")
    evidence = _read_canonical(evidence_path, "accepted pilot evidence")
    if evidence.get("decision") != "candidate_source_accepted_for_full_history_contract":
        raise TwelveDataHistoryError("pilot evidence did not accept the source")
    calendar_record = contract.get("boundaries", {}).get("expected_calendar", {})
    calendar_path = _repo_file(repo_root, calendar_record.get("path"), "expected calendar")
    if sha256_file(calendar_path) != calendar_record.get("sha256"):
        raise TwelveDataHistoryError("expected calendar checksum changed")
    calendars = load_calendar(calendar_path)
    if calendars["us_exchange"]["session_count"] != calendar_record.get("us_session_count"):
        raise TwelveDataHistoryError("US calendar count changed")
    if calendars["fx"]["session_count"] != calendar_record.get("fx_session_count"):
        raise TwelveDataHistoryError("FX calendar count changed")
    request = contract.get("request_plan", {})
    if request.get("maximum_requests") != 25 or request.get("maximum_weighted_credits") != 329:
        raise TwelveDataHistoryError("history request budget changed")
    if request.get("minute_credit_ceiling") != 55:
        raise TwelveDataHistoryError("history minute credit ceiling changed")
    query = request.get("time_series_query", {})
    if query.get("adjust") != "none" or query.get("outputsize") != "5000":
        raise TwelveDataHistoryError("history must use unadjusted data within 5000 rows")
    if contract.get("decision_rule", {}).get("a1_stage_passed_by_history_contract") is not False:
        raise TwelveDataHistoryError("history contract cannot pass A1 by itself")
    retention = contract.get("retention_and_revision_policy", {})
    if retention.get("archival_use_after_subscription_termination") != "ineligible_pending_explicit_provider_permission":
        raise TwelveDataHistoryError("post-subscription uncertainty must fail closed")
    return contract, pilot, calendars


@dataclass(frozen=True, slots=True)
class HistoryRequestSpec:
    endpoint: str
    filename: str
    parameters: Mapping[str, str]
    path: str
    phase: int
    symbol: str
    weight: int


def build_request_specs(contract: Mapping[str, Any]) -> tuple[HistoryRequestSpec, ...]:
    plan = contract["request_plan"]
    time_query = plan["time_series_query"]
    action_query = plan["corporate_action_query"]
    weights = plan["endpoint_credit_weights"]
    phases = plan["phases"]
    phase_by_symbol = {
        phase["symbols"][0]: int(phase["phase"])
        for phase in phases[1:]
    }
    specs: list[HistoryRequestSpec] = []
    for symbol in SYMBOLS:
        slug = symbol.casefold().replace("/", "-")
        specs.append(
            HistoryRequestSpec(
                endpoint="time_series",
                filename=f"{slug}-time-series.json",
                parameters={**time_query, "symbol": symbol},
                path="/time_series",
                phase=1,
                symbol=symbol,
                weight=int(weights["time_series"]),
            )
        )
    for symbol in ETF_SYMBOLS:
        slug = symbol.casefold()
        for endpoint in ("dividends", "splits"):
            specs.append(
                HistoryRequestSpec(
                    endpoint=endpoint,
                    filename=f"{slug}-{endpoint}.json",
                    parameters={**action_query[endpoint], "symbol": symbol},
                    path=f"/{endpoint}",
                    phase=phase_by_symbol[symbol],
                    symbol=symbol,
                    weight=int(weights[endpoint]),
                )
            )
    if len(specs) != plan["maximum_requests"]:
        raise TwelveDataHistoryError("request count differs from the frozen contract")
    if sum(item.weight for item in specs) != plan["maximum_weighted_credits"]:
        raise TwelveDataHistoryError("weighted credits differ from the frozen contract")
    expected_phase_weights = {1: 9, **{phase: 40 for phase in range(2, 10)}}
    actual = {
        phase: sum(item.weight for item in specs if item.phase == phase) for phase in range(1, 10)
    }
    if actual != expected_phase_weights:
        raise TwelveDataHistoryError("rate-limit phase allocation changed")
    if any("apikey" in key.casefold() for item in specs for key in item.parameters):
        raise TwelveDataHistoryError("request plan attempts to persist a token")
    return tuple(specs)


def phase_offsets(contract: Mapping[str, Any]) -> dict[int, int]:
    result = {1: 0}
    for phase in contract["request_plan"]["phases"][1:]:
        result[int(phase["phase"])] = int(phase["minimum_seconds_after_phase_1_start"])
    if result != {1: 0, 2: 61, 3: 122, 4: 183, 5: 244, 6: 305, 7: 366, 8: 427, 9: 488}:
        raise TwelveDataHistoryError("rate-limit offsets changed")
    return result


def available_at(session: str) -> str:
    try:
        day = date.fromisoformat(session)
    except ValueError as exc:
        raise TwelveDataHistoryError(f"invalid session: {session}") from exc
    value = datetime.combine(day + timedelta(days=1), time(5), tzinfo=timezone.utc)
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def _canonical_decimal(raw: Any, field: str, *, positive: bool = False) -> str:
    if isinstance(raw, bool) or raw is None:
        raise TwelveDataHistoryError(f"missing numeric field: {field}")
    try:
        value = Decimal(str(raw))
    except InvalidOperation as exc:
        raise TwelveDataHistoryError(f"invalid numeric field: {field}") from exc
    if not value.is_finite() or positive and value <= 0:
        raise TwelveDataHistoryError(f"invalid numeric field: {field}")
    return format(value.normalize(), "f")


def normalized_price_lines(
    payload: Mapping[str, Any],
    instrument: Mapping[str, Any],
    expected_sessions: Sequence[str],
    source_digest: str,
) -> tuple[str, ...]:
    try:
        audit_time_series(
            payload,
            instrument,
            expected_sessions,
            allow_boundary_buffer=True,
        )
    except TwelveDataAuditError as exc:
        raise TwelveDataHistoryError(str(exc)) from exc
    expected = set(expected_sessions)
    rows = [row for row in payload["values"] if row.get("datetime") in expected]
    lines: list[str] = []
    for row in rows:
        session = str(row["datetime"])
        record = {
            "available_at": available_at(session),
            "close": _canonical_decimal(row.get("close"), "close", positive=True),
            "high": _canonical_decimal(row.get("high"), "high", positive=True),
            "instrument_id": instrument["instrument_id"],
            "interval": "1day",
            "low": _canonical_decimal(row.get("low"), "low", positive=True),
            "observed_at": f"{session}T00:00:00Z",
            "open": _canonical_decimal(row.get("open"), "open", positive=True),
            "session": session,
            "source_sha256": source_digest,
            "symbol": instrument["symbol"],
            "volume": (
                None
                if instrument["symbol"] == "GBP/USD" and row.get("volume") in (None, "")
                else _canonical_decimal(row.get("volume"), "volume")
            ),
        }
        lines.append(json.dumps(record, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")))
    if len(lines) != len(expected_sessions):
        raise TwelveDataHistoryError("normalized price row count mismatch")
    return tuple(lines)


def normalized_action_lines(
    payload: Mapping[str, Any],
    instrument: Mapping[str, Any],
    endpoint: str,
    source_digest: str,
    start: str,
    end: str,
) -> tuple[str, ...]:
    if endpoint not in {"dividends", "splits"}:
        raise TwelveDataHistoryError("unsupported corporate-action endpoint")
    meta = payload.get("meta")
    if not isinstance(meta, Mapping):
        raise TwelveDataHistoryError(f"{endpoint} response has no metadata")
    if (
        meta.get("symbol") != instrument["symbol"]
        or meta.get("currency") != instrument["expected_currency"]
        or meta.get("mic_code") != instrument["expected_mic_code"]
    ):
        raise TwelveDataHistoryError(f"{instrument['symbol']} {endpoint} identity mismatch")
    raw_rows = payload.get(endpoint)
    if not isinstance(raw_rows, list):
        raise TwelveDataHistoryError(f"{endpoint} response has no array")
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    rows: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    for raw_row in raw_rows:
        if not isinstance(raw_row, Mapping):
            raise TwelveDataHistoryError(f"{endpoint} row must be an object")
        field = "ex_date" if endpoint == "dividends" else "date"
        raw_day = raw_row.get(field)
        if not isinstance(raw_day, str):
            raise TwelveDataHistoryError(f"{endpoint} row has no date")
        try:
            action_day = date.fromisoformat(raw_day)
        except ValueError as exc:
            raise TwelveDataHistoryError(f"invalid {endpoint} date") from exc
        if not start_date <= action_day <= end_date:
            continue
        if raw_day in seen:
            raise TwelveDataHistoryError(f"duplicate {endpoint} action date")
        seen.add(raw_day)
        if endpoint == "dividends":
            _canonical_decimal(raw_row.get("amount"), "amount", positive=True)
        else:
            ratio = _canonical_decimal(raw_row.get("ratio"), "ratio", positive=True)
            if raw_row.get("from_factor") is not None and raw_row.get("to_factor") is not None:
                from_factor = Decimal(_canonical_decimal(raw_row.get("from_factor"), "from_factor", positive=True))
                to_factor = Decimal(_canonical_decimal(raw_row.get("to_factor"), "to_factor", positive=True))
                if Decimal(ratio) != to_factor / from_factor:
                    raise TwelveDataHistoryError("split ratio conflicts with from/to factors")
        rows.append(raw_row)
    rows.sort(key=lambda item: str(item["ex_date"] if endpoint == "dividends" else item["date"]))
    result: list[str] = []
    for row in rows:
        action_date = str(row["ex_date"] if endpoint == "dividends" else row["date"])
        record: dict[str, Any] = {
            "action_date": action_date,
            "action_type": "cash_distribution" if endpoint == "dividends" else "split",
            "available_at": available_at(action_date),
            "instrument_id": instrument["instrument_id"],
            "source_sha256": source_digest,
            "symbol": instrument["symbol"],
        }
        if endpoint == "dividends":
            record["amount_per_share"] = _canonical_decimal(row.get("amount"), "amount", positive=True)
            record["currency"] = instrument["expected_currency"]
        else:
            record["ratio"] = _canonical_decimal(row.get("ratio"), "ratio", positive=True)
            if row.get("description") is not None:
                record["description"] = str(row["description"])
        result.append(json.dumps(record, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")))
    return tuple(result)


def validate_source_manifest(
    repo_root: Path,
    manifest_path: Path,
    contract_path: Path,
    contract: Mapping[str, Any],
) -> tuple[dict[tuple[str, str], Path], dict[str, Any]]:
    manifest = _read_canonical(manifest_path, "full-history source manifest")
    if manifest.get("schema_version") != MANIFEST_SCHEMA or manifest.get("experiment_id") != contract["experiment_id"]:
        raise TwelveDataHistoryError("source manifest lineage mismatch")
    if manifest.get("contract_sha256") != sha256_file(contract_path):
        raise TwelveDataHistoryError("source manifest contract checksum mismatch")
    _require_utc(manifest.get("started_at"), "manifest started_at")
    _require_utc(manifest.get("completed_at"), "manifest completed_at")
    if manifest.get("authentication") != "authorization_header_redacted_not_serialized":
        raise TwelveDataHistoryError("manifest authentication policy changed")
    specs = build_request_specs(contract)
    records = manifest.get("responses")
    if not isinstance(records, list) or len(records) != len(specs):
        raise TwelveDataHistoryError("manifest response count mismatch")
    expected = {(item.symbol, item.endpoint): item for item in specs}
    indexed: dict[tuple[str, str], Path] = {}
    for record in records:
        if not isinstance(record, Mapping):
            raise TwelveDataHistoryError("manifest response record must be an object")
        key = (str(record.get("symbol")), str(record.get("endpoint")))
        if key not in expected or key in indexed:
            raise TwelveDataHistoryError("unexpected or duplicate manifest response")
        spec = expected[key]
        if record.get("parameters") != dict(spec.parameters):
            raise TwelveDataHistoryError("manifest request parameters changed")
        if record.get("phase") != spec.phase or record.get("weight") != spec.weight:
            raise TwelveDataHistoryError("manifest phase lineage changed")
        path = _repo_file(repo_root, record.get("path"), "raw history response")
        if path.name != spec.filename or record.get("sha256") != sha256_file(path):
            raise TwelveDataHistoryError("raw history checksum or filename mismatch")
        if record.get("bytes") != path.stat().st_size:
            raise TwelveDataHistoryError("raw history byte count mismatch")
        _require_utc(record.get("retrieved_at"), "response retrieved_at")
        indexed[key] = path
    return indexed, manifest
