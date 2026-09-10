"""Pure, fail-closed validation for the frozen Twelve Data A1 source pilot.

This module performs no network, database, message-bus, exchange, signal, order, or
position operations. It validates immutable provider bytes acquired by the separate
transactional downloader.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse


CONTRACT_SCHEMA = "cross-asset-a1-twelvedata-source-pilot-contract-v1"
PILOT_ID = "cross-asset-a1-twelvedata-economic-proxy-pilot-v1"
SUCCESSOR_PILOT_ID = "cross-asset-a1-twelvedata-economic-proxy-pilot-v2"
MANIFEST_SCHEMA = "cross-asset-a1-twelvedata-source-manifest-v1"
EVIDENCE_SCHEMA = "cross-asset-a1-twelvedata-evidence-manifest-v1"
EXPECTED_SYMBOLS = ("SPY", "EFA", "EEM", "IEF", "TLT", "GLD", "DBC", "BIL", "GBP/USD")
ALLOWED_ENDPOINTS = ("earliest_timestamp", "time_series", "dividends", "splits")


class TwelveDataAuditError(ValueError):
    """Raised when contract, source bytes, or lineage fail the frozen pilot."""


def canonical_json(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True, separators=(",", ": ")
    ) + "\n"


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_canonical(path: Path, label: str) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
        value = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TwelveDataAuditError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict) or raw != canonical_json(value):
        raise TwelveDataAuditError(f"{label} must be a canonical JSON object")
    return value


def _repo_file(repo_root: Path, raw_path: Any, label: str) -> Path:
    if not isinstance(raw_path, str) or not raw_path or Path(raw_path).is_absolute():
        raise TwelveDataAuditError(f"{label} must be repository-relative")
    root = repo_root.resolve(strict=True)
    try:
        path = (root / raw_path).resolve(strict=True)
        path.relative_to(root)
    except (OSError, ValueError) as exc:
        raise TwelveDataAuditError(f"invalid {label}: {raw_path}") from exc
    if not path.is_file():
        raise TwelveDataAuditError(f"{label} is not a regular file: {raw_path}")
    return path


def _parse_date(raw: Any, label: str) -> date:
    if not isinstance(raw, str) or not raw:
        raise TwelveDataAuditError(f"{label} must be a date")
    token = raw[:10]
    try:
        value = date.fromisoformat(token)
    except ValueError as exc:
        raise TwelveDataAuditError(f"invalid {label}: {raw}") from exc
    if len(raw) > 10:
        try:
            datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError as exc:
            raise TwelveDataAuditError(f"invalid {label}: {raw}") from exc
    return value


def _require_utc(raw: Any, label: str) -> datetime:
    if not isinstance(raw, str) or not raw:
        raise TwelveDataAuditError(f"{label} must be an explicit UTC timestamp")
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise TwelveDataAuditError(f"invalid {label}: {raw}") from exc
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise TwelveDataAuditError(f"{label} must use explicit UTC")
    return value


def _strict_json(raw: bytes, label: str) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8", errors="strict")
        value = json.loads(
            text,
            parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise TwelveDataAuditError(f"{label} is not strict UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise TwelveDataAuditError(f"{label} must be a JSON object")
    if value.get("status") == "error" or value.get("code") is not None and value.get("message"):
        raise TwelveDataAuditError(f"{label} contains a provider error")
    return value


def parse_response(raw: bytes, label: str) -> dict[str, Any]:
    return _strict_json(raw, label)


def load_contract(path: Path, repo_root: Path | None = None) -> dict[str, Any]:
    contract = _read_canonical(path, "Twelve Data pilot contract")
    if contract.get("schema_version") == "cross-asset-a1-twelvedata-source-pilot-amendment-v1":
        root = repo_root or path.resolve(strict=True).parents[2]
        if contract.get("pilot_id") != SUCCESSOR_PILOT_ID or contract.get("supersedes") != PILOT_ID:
            raise TwelveDataAuditError("unexpected Twelve Data successor lineage")
        if contract.get("status") != "frozen" or contract.get("no_other_contract_field_changes") is not True:
            raise TwelveDataAuditError("Twelve Data successor must be frozen and minimal")
        base_record = contract.get("base_contract", {})
        base_path = _repo_file(root, base_record.get("path"), "base Twelve Data contract")
        if sha256_file(base_path) != base_record.get("sha256"):
            raise TwelveDataAuditError("base Twelve Data contract checksum changed")
        failure_record = contract.get("frozen_failure_evidence", {})
        failure_path = _repo_file(root, failure_record.get("path"), "Twelve Data v1 evidence")
        if sha256_file(failure_path) != failure_record.get("sha256"):
            raise TwelveDataAuditError("Twelve Data v1 evidence checksum changed")
        changes = contract.get("changes_from_predecessor", {})
        expected_root = "artifacts/agent-level-experiment/cross-asset/a1-twelvedata-economic-proxy-pilot-v2"
        if changes.get("output_artifact_root") != expected_root:
            raise TwelveDataAuditError("Twelve Data successor artifact root changed")
        if changes.get("time_series_query_boundary") != {
            "end_date": "2025-03-03",
            "start_date": "2025-01-31",
        }:
            raise TwelveDataAuditError("Twelve Data successor query buffer changed")
        if changes.get("corporate_action_query_boundary") != {
            "end_date": "2025-02-28",
            "start_date": "2025-02-03",
        }:
            raise TwelveDataAuditError("Twelve Data corporate-action boundary changed")
        effective = copy.deepcopy(load_contract(base_path, root))
        effective["activated_at"] = contract["activated_at"]
        effective["pilot_id"] = SUCCESSOR_PILOT_ID
        effective["output"]["artifact_root"] = expected_root
        effective["sources"]["twelvedata_grow"]["query_parameters"].update(
            changes["time_series_query_boundary"]
        )
        effective["sources"]["twelvedata_grow"]["corporate_action_query_parameters"] = (
            changes["corporate_action_query_boundary"]
        )
        effective["sources"]["twelvedata_grow"]["allow_boundary_buffer_rows"] = True
        effective["sources"]["twelvedata_grow"]["corporate_action_identity_via_time_series"] = True
        for item in effective["instruments"]:
            symbol = item["symbol"]
            if symbol in changes["earliest_date_not_after"]:
                item["earliest_date_not_after"] = changes["earliest_date_not_after"][symbol]
            if symbol in changes["expected_listing_identity"]:
                identity = changes["expected_listing_identity"][symbol]
                item["expected_exchange_values"] = [identity["exchange"]]
                item["expected_mic_code"] = identity["mic_code"]
            if symbol == "SPY":
                item["corporate_action_identity_via_time_series"] = True
        effective["_contract_sha256"] = sha256_file(path)
        return effective
    if contract.get("schema_version") != CONTRACT_SCHEMA or contract.get("pilot_id") != PILOT_ID:
        raise TwelveDataAuditError("unexpected Twelve Data pilot contract")
    if contract.get("status") != "frozen" or contract.get("strategy_evaluation_authorized") is not False:
        raise TwelveDataAuditError("pilot must be frozen and source-only")
    prohibitions = contract.get("prohibitions", {})
    for key in (
        "bulk_download_allowed",
        "derivative_data_allowed",
        "economic_metrics_allowed",
        "execution_approval_allowed",
        "execution_credentials_allowed",
        "partial_ob0_access_allowed",
        "pnl_allowed",
        "protected_service_access_allowed",
        "strategy_parameters_allowed",
        "strategy_signals_allowed",
    ):
        if prohibitions.get(key) is not False:
            raise TwelveDataAuditError(f"unsafe Twelve Data pilot setting: {key}")
    access = contract.get("source_access", {})
    if access.get("api_token_environment_variable") != "TWELVEDATA_API_KEY":
        raise TwelveDataAuditError("unexpected token environment variable")
    if access.get("authorization_header_scheme") != "apikey":
        raise TwelveDataAuditError("authorization must use the frozen header scheme")
    if access.get("research_data_provider_api_token_allowed") is not True:
        raise TwelveDataAuditError("research data token is not authorized")
    if access.get("existing_paid_subscription_use_authorized") is not True:
        raise TwelveDataAuditError("existing paid subscription use is not authorized")
    for key in (
        "api_token_may_be_logged_or_serialized",
        "broker_or_exchange_credentials_allowed",
        "further_paid_upgrade_authorized",
    ):
        if access.get(key) is not False:
            raise TwelveDataAuditError(f"unsafe Twelve Data access setting: {key}")
    instruments = contract.get("instruments")
    if not isinstance(instruments, list) or tuple(item.get("symbol") for item in instruments) != EXPECTED_SYMBOLS:
        raise TwelveDataAuditError("exact Twelve Data pilot universe changed")
    if len({item.get("instrument_id") for item in instruments}) != len(EXPECTED_SYMBOLS):
        raise TwelveDataAuditError("duplicate or missing instrument identity")
    for item in instruments:
        _parse_date(item.get("earliest_date_not_after"), f"{item.get('symbol')} earliest threshold")
        if not all(item.get(key) for key in ("asset_role", "expected_currency", "expected_type")):
            raise TwelveDataAuditError(f"incomplete identity contract for {item.get('symbol')}")
    boundaries = contract.get("boundaries", {})
    etf_sessions = boundaries.get("expected_us_etf_sessions")
    fx_sessions = boundaries.get("expected_fx_sessions")
    if not isinstance(etf_sessions, list) or len(etf_sessions) != 19 or etf_sessions != sorted(set(etf_sessions)):
        raise TwelveDataAuditError("pilot must freeze 19 ordered US ETF sessions")
    if not isinstance(fx_sessions, list) or len(fx_sessions) != 20 or fx_sessions != sorted(set(fx_sessions)):
        raise TwelveDataAuditError("pilot must freeze 20 ordered FX sessions")
    source = contract.get("sources", {}).get("twelvedata_grow", {})
    base = source.get("api_base_url")
    parsed = urlparse(str(base))
    if parsed.scheme != "https" or parsed.hostname != "api.twelvedata.com" or parsed.path not in ("", "/"):
        raise TwelveDataAuditError("Twelve Data host changed")
    if source.get("adjustment_mode") != "none":
        raise TwelveDataAuditError("pilot must request unadjusted daily data")
    if source.get("maximum_requests") != 20 or source.get("maximum_symbols") != 9:
        raise TwelveDataAuditError("pilot request or symbol ceiling changed")
    if source.get("maximum_weighted_credits") != 58 or source.get("minute_credit_ceiling") != 55:
        raise TwelveDataAuditError("pilot weighted-credit boundary changed")
    if source.get("accepted_before_pilot") is not False:
        raise TwelveDataAuditError("candidate cannot be accepted before the pilot")
    terms = source.get("research_reuse_terms", {})
    if terms.get("personal_internal_noncommercial_use_documented") is not True:
        raise TwelveDataAuditError("personal internal use terms are unresolved")
    if terms.get("archival_use_after_subscription_termination_resolved") is not False:
        raise TwelveDataAuditError("post-subscription archival uncertainty must remain explicit")
    _require_utc(terms.get("observed_at"), "terms observed_at")
    if contract.get("decision_rule", {}).get("a1_stage_passed_by_pilot") is not False:
        raise TwelveDataAuditError("source pilot cannot pass A1")
    contract["_contract_sha256"] = sha256_file(path)
    return contract


@dataclass(frozen=True, slots=True)
class RequestSpec:
    endpoint: str
    filename: str
    path: str
    persisted_parameters: Mapping[str, str]
    phase: int
    symbol: str
    weight: int


def build_request_specs(contract: Mapping[str, Any]) -> tuple[RequestSpec, ...]:
    """Build a token-free, deterministic plan for the frozen API requests."""

    source = contract["sources"]["twelvedata_grow"]
    endpoint_paths = source["endpoint_paths"]
    weights = source["endpoint_credit_weights"]
    common = source["query_parameters"]
    corporate_common = source.get(
        "corporate_action_query_parameters",
        {"end_date": common["end_date"], "start_date": common["start_date"]},
    )
    specs: list[RequestSpec] = []
    for instrument in contract["instruments"]:
        symbol = instrument["symbol"]
        slug = symbol.casefold().replace("/", "-")
        specs.append(
            RequestSpec(
                endpoint="earliest_timestamp",
                filename=f"{slug}-earliest-timestamp.json",
                path=endpoint_paths["earliest_timestamp"],
                persisted_parameters={"interval": common["interval"], "symbol": symbol},
                phase=1,
                symbol=symbol,
                weight=weights["earliest_timestamp"],
            )
        )
        specs.append(
            RequestSpec(
                endpoint="time_series",
                filename=f"{slug}-time-series.json",
                path=endpoint_paths["time_series"],
                persisted_parameters={**common, "symbol": symbol},
                phase=1,
                symbol=symbol,
                weight=weights["time_series"],
            )
        )
    for endpoint in ("dividends", "splits"):
        specs.append(
            RequestSpec(
                endpoint=endpoint,
                filename=f"spy-{endpoint}.json",
                path=endpoint_paths[endpoint],
                persisted_parameters={
                    "end_date": corporate_common["end_date"],
                    "start_date": corporate_common["start_date"],
                    "symbol": "SPY",
                },
                phase=2,
                symbol="SPY",
                weight=weights[endpoint],
            )
        )
    if len(specs) != source["maximum_requests"]:
        raise TwelveDataAuditError("request plan does not equal the frozen request count")
    if sum(item.weight for item in specs) != source["maximum_weighted_credits"]:
        raise TwelveDataAuditError("request plan violates the weighted-credit ceiling")
    phase_weights = {
        phase: sum(item.weight for item in specs if item.phase == phase) for phase in (1, 2)
    }
    if phase_weights != {1: 18, 2: 40}:
        raise TwelveDataAuditError("request phases violate the frozen rate-limit schedule")
    if any("apikey" in key.casefold() for item in specs for key in item.persisted_parameters):
        raise TwelveDataAuditError("request plan attempts to persist a token")
    return tuple(specs)


def audit_identity(meta: Any, instrument: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(meta, Mapping):
        raise TwelveDataAuditError(f"{instrument['symbol']} response has no metadata")
    symbol = instrument["symbol"]
    if meta.get("symbol") != symbol:
        raise TwelveDataAuditError(f"{symbol} metadata symbol mismatch")
    if meta.get("type") != instrument["expected_type"]:
        raise TwelveDataAuditError(f"{symbol} metadata type mismatch")
    if symbol == "GBP/USD":
        base = meta.get("currency_base")
        quote = meta.get("currency_quote")
        if base not in instrument["expected_fx_base_values"] or quote not in instrument["expected_fx_quote_values"]:
            raise TwelveDataAuditError("GBP/USD base or quote identity mismatch")
        return {"currency_base": base, "currency_quote": quote, "symbol": symbol, "type": meta["type"]}
    if meta.get("currency") != instrument["expected_currency"]:
        raise TwelveDataAuditError(f"{symbol} metadata currency mismatch")
    if meta.get("mic_code") != instrument["expected_mic_code"]:
        raise TwelveDataAuditError(f"{symbol} MIC mismatch")
    if meta.get("exchange") not in instrument["expected_exchange_values"]:
        raise TwelveDataAuditError(f"{symbol} exchange mismatch")
    return {
        "currency": meta["currency"],
        "exchange": meta["exchange"],
        "mic_code": meta["mic_code"],
        "symbol": symbol,
        "type": meta["type"],
    }


def audit_earliest(payload: Mapping[str, Any], instrument: Mapping[str, Any]) -> dict[str, Any]:
    observed = _parse_date(payload.get("datetime"), f"{instrument['symbol']} earliest datetime")
    threshold = _parse_date(
        instrument["earliest_date_not_after"], f"{instrument['symbol']} earliest threshold"
    )
    if observed > threshold:
        raise TwelveDataAuditError(f"{instrument['symbol']} history begins after the frozen threshold")
    return {"earliest_date": observed.isoformat(), "threshold": threshold.isoformat()}


def _decimal(record: Mapping[str, Any], field: str, *, positive: bool = False) -> Decimal:
    value = record.get(field)
    if isinstance(value, bool) or value is None:
        raise TwelveDataAuditError(f"missing numeric field: {field}")
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise TwelveDataAuditError(f"invalid numeric field: {field}") from exc
    if not number.is_finite() or positive and number <= 0:
        raise TwelveDataAuditError(f"invalid numeric field: {field}")
    return number


def audit_time_series(
    payload: Mapping[str, Any],
    instrument: Mapping[str, Any],
    expected_sessions: Sequence[str],
    *,
    allow_boundary_buffer: bool = False,
) -> dict[str, Any]:
    identity = audit_identity(payload.get("meta"), instrument)
    rows = payload.get("values")
    if not isinstance(rows, list) or not rows:
        raise TwelveDataAuditError(f"{instrument['symbol']} session coverage mismatch")
    observed: list[str] = []
    has_volume = instrument["symbol"] != "GBP/USD"
    for row in rows:
        if not isinstance(row, Mapping):
            raise TwelveDataAuditError("daily row must be an object")
        raw_session = row.get("datetime")
        if not isinstance(raw_session, str) or len(raw_session) != 10:
            raise TwelveDataAuditError("daily datetime must be a date-only session label")
        session = _parse_date(raw_session, "daily session").isoformat()
        observed.append(session)
        open_price = _decimal(row, "open", positive=True)
        high = _decimal(row, "high", positive=True)
        low = _decimal(row, "low", positive=True)
        close = _decimal(row, "close", positive=True)
        if high < max(open_price, close) or low > min(open_price, close) or high < low:
            raise TwelveDataAuditError(f"{instrument['symbol']} invalid OHLC relationship")
        if has_volume:
            if _decimal(row, "volume") < 0:
                raise TwelveDataAuditError(f"{instrument['symbol']} volume cannot be negative")
        elif row.get("volume") not in (None, "") and _decimal(row, "volume") < 0:
            raise TwelveDataAuditError("GBP/USD volume cannot be negative")
    if observed != sorted(set(observed)):
        raise TwelveDataAuditError(f"{instrument['symbol']} session sequence mismatch")
    if allow_boundary_buffer:
        expected_set = set(expected_sessions)
        inside = [value for value in observed if value in expected_set]
        illegal = [
            value
            for value in observed
            if value not in expected_set and expected_sessions[0] <= value <= expected_sessions[-1]
        ]
        if illegal or inside != list(expected_sessions):
            raise TwelveDataAuditError(f"{instrument['symbol']} session coverage mismatch")
    elif observed != list(expected_sessions):
        raise TwelveDataAuditError(f"{instrument['symbol']} session coverage mismatch")
    return {
        "buffer_rows": len(observed) - len(expected_sessions),
        "first_session": expected_sessions[0],
        "identity": identity,
        "last_session": expected_sessions[-1],
        "rows": len(expected_sessions),
        "volume_required": has_volume,
    }


def audit_corporate_actions(
    payload: Mapping[str, Any], instrument: Mapping[str, Any], endpoint: str, start: str, end: str
) -> dict[str, Any]:
    if endpoint not in ("dividends", "splits"):
        raise TwelveDataAuditError("unsupported corporate-action endpoint")
    meta = payload.get("meta")
    if not isinstance(meta, Mapping):
        raise TwelveDataAuditError(f"{endpoint} response has no metadata")
    if instrument.get("corporate_action_identity_via_time_series") is True:
        if (
            meta.get("symbol") != instrument["symbol"]
            or meta.get("currency") != instrument["expected_currency"]
            or meta.get("mic_code") != instrument["expected_mic_code"]
        ):
            raise TwelveDataAuditError(f"{endpoint} identity mismatch")
    else:
        audit_identity(meta, instrument)
    rows = payload.get(endpoint)
    if not isinstance(rows, list):
        raise TwelveDataAuditError(f"{endpoint} response has no {endpoint} array")
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    observed_dates: list[str] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise TwelveDataAuditError(f"{endpoint} row must be an object")
        field = "ex_date" if endpoint == "dividends" else "date"
        action_date = _parse_date(row.get(field), f"{endpoint} date")
        if not start_date <= action_date <= end_date:
            raise TwelveDataAuditError(f"{endpoint} record crosses the pilot boundary")
        if endpoint == "dividends":
            _decimal(row, "amount", positive=True)
        else:
            ratio = row.get("ratio")
            if not isinstance(ratio, str) or ":" not in ratio:
                raise TwelveDataAuditError("split ratio must use provider ratio notation")
            left, right = ratio.split(":", 1)
            if Decimal(left) <= 0 or Decimal(right) <= 0:
                raise TwelveDataAuditError("split ratio must be positive")
        observed_dates.append(action_date.isoformat())
    if observed_dates != sorted(set(observed_dates)):
        raise TwelveDataAuditError(f"{endpoint} records must be ordered and unique")
    return {"endpoint": endpoint, "records": len(rows)}


def validate_source_manifest(
    repo_root: Path, manifest_path: Path, contract: Mapping[str, Any]
) -> dict[tuple[str, str], Path]:
    manifest = _read_canonical(manifest_path, "Twelve Data source manifest")
    if manifest.get("schema_version") != MANIFEST_SCHEMA or manifest.get("pilot_id") != contract["pilot_id"]:
        raise TwelveDataAuditError("source manifest lineage mismatch")
    if manifest.get("contract_sha256") != contract.get("_contract_sha256"):
        raise TwelveDataAuditError("source manifest contract checksum mismatch")
    _require_utc(manifest.get("retrieved_at"), "manifest retrieved_at")
    if manifest.get("authentication") != "authorization_header_redacted_not_serialized":
        raise TwelveDataAuditError("manifest authentication policy changed")
    records = manifest.get("responses")
    specs = build_request_specs(contract)
    if not isinstance(records, list) or len(records) != len(specs):
        raise TwelveDataAuditError("manifest response count mismatch")
    expected = {(item.symbol, item.endpoint): item for item in specs}
    indexed: dict[tuple[str, str], Path] = {}
    for record in records:
        if not isinstance(record, Mapping):
            raise TwelveDataAuditError("manifest response record must be an object")
        key = (str(record.get("symbol")), str(record.get("endpoint")))
        if key not in expected or key in indexed:
            raise TwelveDataAuditError("manifest has an unexpected or duplicate response")
        spec = expected[key]
        if record.get("parameters") != dict(spec.persisted_parameters):
            raise TwelveDataAuditError("manifest request parameters changed")
        if record.get("phase") != spec.phase or record.get("weight") != spec.weight:
            raise TwelveDataAuditError("manifest rate-limit lineage changed")
        path = _repo_file(repo_root, record.get("path"), "Twelve Data raw response")
        if path.name != spec.filename or record.get("sha256") != sha256_file(path):
            raise TwelveDataAuditError("raw response checksum or filename mismatch")
        if record.get("bytes") != path.stat().st_size:
            raise TwelveDataAuditError("raw response byte count mismatch")
        indexed[key] = path
    serialized_without_policy = canonical_json(manifest).casefold().replace(
        "authorization_header_redacted_not_serialized", ""
    )
    if "authorization:" in serialized_without_policy or "api_key" in serialized_without_policy or "apikey " in serialized_without_policy:
        raise TwelveDataAuditError("manifest may contain credential material")
    return indexed


def audit_manifest_payloads(
    repo_root: Path, manifest_path: Path, contract: Mapping[str, Any]
) -> list[dict[str, Any]]:
    indexed = validate_source_manifest(repo_root, manifest_path, contract)
    boundaries = contract["boundaries"]
    results: list[dict[str, Any]] = []
    for instrument in contract["instruments"]:
        symbol = instrument["symbol"]
        sessions = (
            boundaries["expected_fx_sessions"]
            if symbol == "GBP/USD"
            else boundaries["expected_us_etf_sessions"]
        )
        earliest = audit_earliest(
            parse_response(indexed[(symbol, "earliest_timestamp")].read_bytes(), f"{symbol} earliest"),
            instrument,
        )
        series = audit_time_series(
            parse_response(indexed[(symbol, "time_series")].read_bytes(), f"{symbol} time series"),
            instrument,
            sessions,
            allow_boundary_buffer=contract["sources"]["twelvedata_grow"].get(
                "allow_boundary_buffer_rows", False
            ),
        )
        results.append({"earliest": earliest, "symbol": symbol, "time_series": series})
    spy = contract["instruments"][0]
    for endpoint in ("dividends", "splits"):
        result = audit_corporate_actions(
            parse_response(indexed[("SPY", endpoint)].read_bytes(), f"SPY {endpoint}"),
            spy,
            endpoint,
            boundaries["pilot_start_inclusive"],
            boundaries["pilot_end_inclusive"],
        )
        results[0].setdefault("corporate_actions", []).append(result)
    return results


def audit_manifest_outcome(
    repo_root: Path, manifest_path: Path, contract: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Evaluate every frozen gate so a rejected pilot retains complete diagnostics."""

    indexed = validate_source_manifest(repo_root, manifest_path, contract)
    boundaries = contract["boundaries"]
    results: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for instrument in contract["instruments"]:
        symbol = instrument["symbol"]
        sessions = (
            boundaries["expected_fx_sessions"]
            if symbol == "GBP/USD"
            else boundaries["expected_us_etf_sessions"]
        )
        result: dict[str, Any] = {"symbol": symbol}
        try:
            result["earliest"] = audit_earliest(
                parse_response(
                    indexed[(symbol, "earliest_timestamp")].read_bytes(), f"{symbol} earliest"
                ),
                instrument,
            )
        except TwelveDataAuditError as exc:
            result["earliest_error"] = str(exc)
            failures.append({"error": str(exc), "gate": "earliest_history", "symbol": symbol})
        try:
            result["time_series"] = audit_time_series(
                parse_response(
                    indexed[(symbol, "time_series")].read_bytes(), f"{symbol} time series"
                ),
                instrument,
                sessions,
                allow_boundary_buffer=contract["sources"]["twelvedata_grow"].get(
                    "allow_boundary_buffer_rows", False
                ),
            )
        except TwelveDataAuditError as exc:
            result["time_series_error"] = str(exc)
            failures.append({"error": str(exc), "gate": "daily_series", "symbol": symbol})
        results.append(result)
    spy = contract["instruments"][0]
    for endpoint in ("dividends", "splits"):
        try:
            result = audit_corporate_actions(
                parse_response(indexed[("SPY", endpoint)].read_bytes(), f"SPY {endpoint}"),
                spy,
                endpoint,
                boundaries["pilot_start_inclusive"],
                boundaries["pilot_end_inclusive"],
            )
            results[0].setdefault("corporate_actions", []).append(result)
        except TwelveDataAuditError as exc:
            results[0].setdefault("corporate_action_errors", []).append(
                {"endpoint": endpoint, "error": str(exc)}
            )
            failures.append({"error": str(exc), "gate": endpoint, "symbol": "SPY"})
    return results, failures


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
