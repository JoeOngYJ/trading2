"""Pure, fail-closed validation for the frozen Marketstack A1 source pilot.

This module never performs network, database, message-bus, exchange, signal, order, or
position operations.  It validates immutable response bytes after acquisition by the
separate downloader.
"""

from __future__ import annotations

import hashlib
import json
import math
import copy
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlencode, urlparse


CONTRACT_SCHEMA = "cross-asset-a1-marketstack-source-pilot-contract-v1"
PILOT_ID = "cross-asset-a1-marketstack-free-source-pilot-v1"
SUCCESSOR_PILOT_ID = "cross-asset-a1-marketstack-free-source-pilot-v2"
FINAL_PILOT_ID = "cross-asset-a1-marketstack-free-source-pilot-v3"
MANIFEST_SCHEMA = "cross-asset-a1-marketstack-source-manifest-v1"
EXPECTED_TICKERS = ("SWDA", "VAGS", "SGLN", "COMM")
EXPECTED_ISINS = {
    "SWDA": "IE00B4L5Y983",
    "VAGS": "IE00BG47K971",
    "SGLN": "IE00B4ND3602",
    "COMM": "IE00BDFL4P12",
}
EXPECTED_QUOTE_UNITS = {"SWDA": "GBX", "VAGS": "GBP", "SGLN": "GBX", "COMM": "GBX"}
EXPECTED_MULTIPLIERS = {
    "SWDA": Decimal("0.01"),
    "VAGS": Decimal("1"),
    "SGLN": Decimal("0.01"),
    "COMM": Decimal("0.01"),
}
ALLOWED_ENDPOINTS = ("tickers", "eod", "splits", "dividends")


class MarketstackAuditError(ValueError):
    """Raised when source bytes or lineage do not satisfy the frozen pilot."""


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
        raise MarketstackAuditError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict) or raw != canonical_json(value):
        raise MarketstackAuditError(f"{label} must be a canonical JSON object")
    return value


def _repo_file(repo_root: Path, raw_path: Any, label: str) -> Path:
    if not isinstance(raw_path, str) or not raw_path or Path(raw_path).is_absolute():
        raise MarketstackAuditError(f"{label} must be repository-relative")
    root = repo_root.resolve(strict=True)
    try:
        path = (root / raw_path).resolve(strict=True)
        path.relative_to(root)
    except (OSError, ValueError) as exc:
        raise MarketstackAuditError(f"invalid {label}: {raw_path}") from exc
    if not path.is_file():
        raise MarketstackAuditError(f"{label} is not a regular file: {raw_path}")
    return path


def _require_utc(raw: Any, label: str) -> datetime:
    if not isinstance(raw, str) or not raw:
        raise MarketstackAuditError(f"{label} must be an explicit UTC timestamp")
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MarketstackAuditError(f"invalid {label}: {raw}") from exc
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise MarketstackAuditError(f"{label} must use explicit UTC")
    return value


def load_contract(path: Path, repo_root: Path | None = None) -> dict[str, Any]:
    contract = _read_canonical(path, "Marketstack pilot contract")
    if contract.get("schema_version") == "cross-asset-a1-marketstack-source-pilot-eod-identity-amendment-v1":
        if repo_root is None:
            raise MarketstackAuditError("final successor contract requires a repository root")
        if contract.get("pilot_id") != FINAL_PILOT_ID or contract.get("supersedes") != SUCCESSOR_PILOT_ID:
            raise MarketstackAuditError("unexpected final Marketstack successor lineage")
        if contract.get("status") != "frozen" or contract.get("no_other_contract_field_changes") is not True:
            raise MarketstackAuditError("final Marketstack successor must be frozen and minimal")
        base_record = contract.get("base_contract", {})
        base_path = _repo_file(repo_root, base_record.get("path"), "base Marketstack contract")
        if sha256_file(base_path) != base_record.get("sha256"):
            raise MarketstackAuditError("base Marketstack contract checksum changed")
        failure_record = contract.get("frozen_failure_evidence", {})
        failure_path = _repo_file(repo_root, failure_record.get("path"), "Marketstack v2 failure")
        if sha256_file(failure_path) != failure_record.get("sha256"):
            raise MarketstackAuditError("Marketstack v2 failure checksum changed")
        changes = contract.get("changes_from_predecessor", {})
        if changes.get("request_endpoints") != ["eod", "splits", "dividends"]:
            raise MarketstackAuditError("final Marketstack endpoint set changed")
        if changes.get("total_planned_requests") != 12:
            raise MarketstackAuditError("final Marketstack request count changed")
        expected_root = "artifacts/agent-level-experiment/cross-asset/a1-marketstack-free-source-pilot-v3"
        if changes.get("output_artifact_root") != expected_root:
            raise MarketstackAuditError("final Marketstack artifact root changed")
        expected_identity = "eod_name_symbol_exchange_price_currency_plus_checksummed_issuer_control"
        if changes.get("identity_source") != expected_identity:
            raise MarketstackAuditError("final Marketstack identity source changed")
        effective = copy.deepcopy(load_contract(base_path, repo_root))
        effective["pilot_id"] = FINAL_PILOT_ID
        effective["activated_at"] = contract["activated_at"]
        effective["output"]["artifact_root"] = expected_root
        effective["pilot_request_endpoints"] = ["eod", "splits", "dividends"]
        effective["pilot_identity_source"] = expected_identity
        return effective
    if contract.get("schema_version") == "cross-asset-a1-marketstack-source-pilot-amendment-v1":
        if repo_root is None:
            raise MarketstackAuditError("successor contract requires a repository root")
        if contract.get("pilot_id") != SUCCESSOR_PILOT_ID or contract.get("supersedes") != PILOT_ID:
            raise MarketstackAuditError("unexpected Marketstack successor lineage")
        if contract.get("status") != "frozen" or contract.get("no_other_contract_field_changes") is not True:
            raise MarketstackAuditError("Marketstack successor must be frozen and minimal")
        base_record = contract.get("base_contract", {})
        base_path = _repo_file(repo_root, base_record.get("path"), "base Marketstack contract")
        if sha256_file(base_path) != base_record.get("sha256"):
            raise MarketstackAuditError("base Marketstack contract checksum changed")
        failure_record = contract.get("frozen_failure_evidence", {})
        failure_path = _repo_file(repo_root, failure_record.get("path"), "Marketstack failure evidence")
        if sha256_file(failure_path) != failure_record.get("sha256"):
            raise MarketstackAuditError("Marketstack failure evidence checksum changed")
        changes = contract.get("changes_from_predecessor", {})
        if changes.get("endpoint_paths") != {"tickers": "/tickers/{symbol}"}:
            raise MarketstackAuditError("successor ticker route changed")
        expected_root = "artifacts/agent-level-experiment/cross-asset/a1-marketstack-free-source-pilot-v2"
        if changes.get("output_artifact_root") != expected_root:
            raise MarketstackAuditError("successor artifact root changed")
        effective = copy.deepcopy(load_contract(base_path, repo_root))
        effective["pilot_id"] = SUCCESSOR_PILOT_ID
        effective["activated_at"] = contract["activated_at"]
        effective["output"]["artifact_root"] = expected_root
        effective["sources"]["marketstack_free"]["endpoint_paths"]["tickers"] = "/tickers/{symbol}"
        return effective
    if contract.get("schema_version") != CONTRACT_SCHEMA or contract.get("pilot_id") != PILOT_ID:
        raise MarketstackAuditError("unexpected Marketstack pilot contract")
    if contract.get("status") != "frozen" or contract.get("strategy_evaluation_authorized") is not False:
        raise MarketstackAuditError("pilot must be frozen and source-only")
    instruments = contract.get("instruments")
    if not isinstance(instruments, list) or tuple(item.get("ticker") for item in instruments) != EXPECTED_TICKERS:
        raise MarketstackAuditError("exact pilot universe changed")
    for item in instruments:
        ticker = item["ticker"]
        if item.get("isin") != EXPECTED_ISINS[ticker]:
            raise MarketstackAuditError(f"ISIN changed for {ticker}")
        if item.get("expected_vendor_exchange_code") != "XLON":
            raise MarketstackAuditError(f"exchange changed for {ticker}")
        if item.get("expected_vendor_quote_unit") != EXPECTED_QUOTE_UNITS[ticker]:
            raise MarketstackAuditError(f"quote unit changed for {ticker}")
        try:
            multiplier = Decimal(str(item.get("price_to_gbp_multiplier")))
        except InvalidOperation as exc:
            raise MarketstackAuditError(f"invalid GBP multiplier for {ticker}") from exc
        if multiplier != EXPECTED_MULTIPLIERS[ticker]:
            raise MarketstackAuditError(f"GBP multiplier changed for {ticker}")
    boundaries = contract.get("boundaries", {})
    sessions = boundaries.get("expected_lse_sessions")
    if not isinstance(sessions, list) or len(sessions) != 22 or sessions != sorted(set(sessions)):
        raise MarketstackAuditError("pilot must freeze 22 ordered, unique LSE sessions")
    source = contract.get("sources", {}).get("marketstack_free", {})
    if source.get("api_base_url") != "https://api.marketstack.com/v2":
        raise MarketstackAuditError("Marketstack host or API version changed")
    if source.get("maximum_requests") != 20 or source.get("maximum_symbols") != 4:
        raise MarketstackAuditError("free-pilot request boundary changed")
    if source.get("plan") != "free" or source.get("accepted_before_pilot") is not False:
        raise MarketstackAuditError("Marketstack must remain an unaccepted free candidate")
    if source.get("adjusted_fields_eligible_for_research") is not False:
        raise MarketstackAuditError("undocumented adjusted fields must remain ineligible")
    if source.get("raw_plus_separate_corporate_actions_policy_frozen") is not True:
        raise MarketstackAuditError("raw-price and corporate-action policy is missing")
    if source.get("availability_fallback_frozen") is not True:
        raise MarketstackAuditError("next-session availability fallback is missing")
    terms = source.get("research_reuse_terms", {})
    if source.get("research_reuse_terms_documented") is not True:
        raise MarketstackAuditError("private source-qualification terms are undocumented")
    if terms.get("private_source_qualification_while_account_active_documented") is not True:
        raise MarketstackAuditError("private source-qualification permission is unresolved")
    if terms.get("archival_use_after_account_termination_resolved") is not False:
        raise MarketstackAuditError("post-termination archival uncertainty must remain explicit")
    if terms.get("service_agreement_url") != "https://marketstack.com/agreement":
        raise MarketstackAuditError("Marketstack terms source changed")
    _require_utc(terms.get("observed_at"), "research terms observed_at")
    access = contract.get("source_access", {})
    if access.get("api_token_environment_variable") != "MARKETSTACK_API_KEY":
        raise MarketstackAuditError("unexpected token environment variable")
    if access.get("research_data_provider_api_token_allowed") is not True:
        raise MarketstackAuditError("research token has not been authorized")
    for key in (
        "api_token_may_be_logged_or_serialized",
        "broker_or_exchange_credentials_allowed",
        "paid_upgrade_authorized",
    ):
        if access.get(key) is not False:
            raise MarketstackAuditError(f"unsafe source access setting: {key}")
    if access.get("free_account_only") is not True:
        raise MarketstackAuditError("pilot must use the free account only")
    if repo_root is not None:
        controls = contract.get("sources", {}).get("issuer_identity", {}).get("checksummed_controls")
        if not isinstance(controls, list) or tuple(item.get("ticker") for item in controls) != EXPECTED_TICKERS:
            raise MarketstackAuditError("issuer identity controls are incomplete")
        for item in controls:
            control = _repo_file(repo_root, item.get("path"), "issuer identity control")
            if sha256_file(control) != item.get("sha256"):
                raise MarketstackAuditError(f"issuer identity checksum changed: {item.get('ticker')}")
    return contract


@dataclass(frozen=True, slots=True)
class RequestSpec:
    endpoint: str
    ticker: str
    url: str
    persisted_parameters: Mapping[str, str]


def build_request_specs(contract: Mapping[str, Any], api_key: str) -> tuple[RequestSpec, ...]:
    """Build in-memory URLs while ensuring persisted parameters never contain the token."""

    if not isinstance(api_key, str) or not api_key.strip():
        raise MarketstackAuditError("MARKETSTACK_API_KEY is required")
    source = contract["sources"]["marketstack_free"]
    base = source["api_base_url"]
    if urlparse(base).scheme != "https" or urlparse(base).hostname != "api.marketstack.com":
        raise MarketstackAuditError("only the frozen HTTPS Marketstack host is allowed")
    common = dict(source["query_parameters"])
    specs: list[RequestSpec] = []
    endpoints = tuple(contract.get("pilot_request_endpoints", ALLOWED_ENDPOINTS))
    if not endpoints or any(endpoint not in ALLOWED_ENDPOINTS for endpoint in endpoints):
        raise MarketstackAuditError("request endpoint set is invalid")
    for instrument in contract["instruments"]:
        ticker = instrument["marketstack_symbol"]
        for endpoint in endpoints:
            if endpoint == "tickers":
                public = {}
            else:
                public = {**common, "symbols": ticker}
            actual = {**public, "access_key": api_key}
            path = source["endpoint_paths"][endpoint].format(symbol=ticker)
            specs.append(
                RequestSpec(
                    endpoint=endpoint,
                    ticker=ticker,
                    url=f"{base}{path}?{urlencode(actual)}",
                    persisted_parameters=public,
                )
            )
    if len(specs) > source["maximum_requests"]:
        raise MarketstackAuditError("request plan exceeds the frozen request budget")
    return tuple(specs)


def redact_secret(value: str, api_key: str) -> str:
    """Remove a provider token from exception strings before they can be persisted."""

    if not api_key:
        return value
    return value.replace(api_key, "<redacted>")


def parse_json_response(raw: bytes, label: str) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8", errors="strict")
        payload = json.loads(text, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise MarketstackAuditError(f"{label} is not strict UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise MarketstackAuditError(f"{label} must be a JSON object")
    if payload.get("error") is not None:
        raise MarketstackAuditError(f"{label} contains a provider error")
    return payload


def parse_response(raw: bytes, label: str) -> dict[str, Any]:
    payload = parse_json_response(raw, label)
    if not isinstance(payload.get("data"), list):
        raise MarketstackAuditError(f"{label} has no data array")
    return payload


def _exchange_code(record: Mapping[str, Any]) -> str:
    exchange = record.get("exchange")
    if isinstance(exchange, str):
        return exchange.upper()
    nested = record.get("stock_exchange")
    if isinstance(nested, Mapping):
        for key in ("mic", "acronym"):
            value = nested.get(key)
            if isinstance(value, str) and value:
                return value.upper()
    return ""


def audit_identity(payload: Mapping[str, Any], instrument: Mapping[str, Any]) -> dict[str, Any]:
    ticker = instrument["ticker"]
    candidates = payload.get("data") if isinstance(payload.get("data"), list) else [payload]
    matches = [item for item in candidates if isinstance(item, Mapping) and item.get("symbol") == ticker]
    exact = [item for item in matches if _exchange_code(item) == "XLON"]
    if len(exact) != 1:
        raise MarketstackAuditError(f"{ticker} must have exactly one XLON identity")
    record = exact[0]
    name = record.get("name")
    if not isinstance(name, str) or not all(
        str(token).casefold() in name.casefold() for token in instrument["expected_name_tokens"]
    ):
        raise MarketstackAuditError(f"{ticker} name does not bind to the frozen instrument")
    for field in ("isin", "sedol"):
        observed = record.get(field)
        expected = instrument[field]
        if observed not in (None, "") and str(observed).upper() != expected:
            raise MarketstackAuditError(f"{ticker} {field} conflicts with issuer evidence")
    return {
        "exchange": "XLON",
        "issuer_control_required": True,
        "name": name,
        "stable_id_returned": bool(record.get("isin") or record.get("sedol")),
        "ticker": ticker,
    }


def audit_eod_identity(payload: Mapping[str, Any], instrument: Mapping[str, Any]) -> dict[str, Any]:
    ticker = instrument["ticker"]
    rows = payload.get("data")
    if not isinstance(rows, list) or not rows:
        raise MarketstackAuditError(f"{ticker} EOD response has no identity-bearing rows")
    for row in rows:
        if not isinstance(row, Mapping) or row.get("symbol") != ticker or _exchange_code(row) != "XLON":
            raise MarketstackAuditError(f"{ticker} EOD identity conflicts with the frozen listing")
        name = row.get("name")
        if not isinstance(name, str) or not all(
            str(token).casefold() in name.casefold() for token in instrument["expected_name_tokens"]
        ):
            raise MarketstackAuditError(f"{ticker} EOD name does not bind to the issuer control")
        currency = row.get("price_currency")
        if not isinstance(currency, str) or currency.casefold() != "gbp":
            raise MarketstackAuditError(f"{ticker} EOD price currency is not GBP")
    return {
        "exchange": "XLON",
        "issuer_control_required": True,
        "name": rows[0]["name"],
        "price_currency": "GBP",
        "ticker": ticker,
    }


def _decimal(record: Mapping[str, Any], field: str, *, positive: bool = False) -> Decimal:
    value = record.get(field)
    if isinstance(value, bool) or value is None:
        raise MarketstackAuditError(f"missing numeric field: {field}")
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise MarketstackAuditError(f"invalid numeric field: {field}") from exc
    if not number.is_finite() or (positive and number <= 0):
        raise MarketstackAuditError(f"invalid numeric field: {field}")
    return number


def audit_eod(
    payload: Mapping[str, Any], instrument: Mapping[str, Any], expected_sessions: Sequence[str]
) -> dict[str, Any]:
    rows = payload["data"]
    if len(rows) != len(expected_sessions):
        raise MarketstackAuditError(f"{instrument['ticker']} does not have exact session coverage")
    observed_dates: list[str] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise MarketstackAuditError("EOD row must be an object")
        if row.get("symbol") != instrument["ticker"] or _exchange_code(row) != "XLON":
            raise MarketstackAuditError("EOD row identity changed")
        stamp = _require_utc(row.get("date"), "EOD date")
        if stamp.time().isoformat() != "00:00:00":
            raise MarketstackAuditError("EOD date must identify the session at UTC midnight")
        observed_dates.append(stamp.date().isoformat())
        raw_open = _decimal(row, "open", positive=True)
        raw_high = _decimal(row, "high", positive=True)
        raw_low = _decimal(row, "low", positive=True)
        raw_close = _decimal(row, "close", positive=True)
        if raw_low > min(raw_open, raw_close) or raw_high < max(raw_open, raw_close) or raw_low > raw_high:
            raise MarketstackAuditError("raw OHLC bounds are invalid")
        adj_open = _decimal(row, "adj_open", positive=True)
        adj_high = _decimal(row, "adj_high", positive=True)
        adj_low = _decimal(row, "adj_low", positive=True)
        adj_close = _decimal(row, "adj_close", positive=True)
        if adj_low > min(adj_open, adj_close) or adj_high < max(adj_open, adj_close) or adj_low > adj_high:
            raise MarketstackAuditError("adjusted OHLC bounds are invalid")
        volume = _decimal(row, "volume")
        adj_volume = _decimal(row, "adj_volume")
        if volume < 0 or adj_volume < 0 or volume != volume.to_integral_value() or adj_volume != adj_volume.to_integral_value():
            raise MarketstackAuditError("volume must be a non-negative integer")
        if _decimal(row, "split_factor", positive=True) <= 0 or _decimal(row, "dividend") < 0:
            raise MarketstackAuditError("corporate-action fields are invalid")
    if observed_dates != list(expected_sessions) or len(set(observed_dates)) != len(observed_dates):
        raise MarketstackAuditError(f"{instrument['ticker']} session sequence changed or has gaps")
    if any(value.startswith("2026-") for value in observed_dates):
        raise MarketstackAuditError("sealed 2026 data appeared in the pilot")
    return {
        "first_session": observed_dates[0],
        "last_session": observed_dates[-1],
        "price_to_gbp_multiplier": instrument["price_to_gbp_multiplier"],
        "quote_unit": instrument["expected_vendor_quote_unit"],
        "rows": len(rows),
        "ticker": instrument["ticker"],
    }


def audit_corporate_actions(
    payload: Mapping[str, Any], instrument: Mapping[str, Any], endpoint: str, start: str, end: str
) -> dict[str, Any]:
    if endpoint not in {"splits", "dividends"}:
        raise MarketstackAuditError("unexpected corporate-action endpoint")
    for row in payload["data"]:
        if not isinstance(row, Mapping) or row.get("symbol") != instrument["ticker"]:
            raise MarketstackAuditError("corporate-action identity changed")
        stamp = _require_utc(row.get("date"), f"{endpoint} date")
        day = stamp.date().isoformat()
        if not start <= day <= end:
            raise MarketstackAuditError("corporate action crosses the pilot boundary")
        if endpoint == "splits":
            _decimal(row, "split_factor", positive=True)
        else:
            if _decimal(row, "dividend") < 0:
                raise MarketstackAuditError("dividend cannot be negative")
    return {"endpoint": endpoint, "records": len(payload["data"]), "ticker": instrument["ticker"]}


def validate_source_manifest(
    repo_root: Path, manifest_path: Path, contract: Mapping[str, Any]
) -> dict[tuple[str, str], Path]:
    manifest = _read_canonical(manifest_path, "Marketstack source manifest")
    if manifest.get("schema_version") != MANIFEST_SCHEMA or manifest.get("pilot_id") != contract["pilot_id"]:
        raise MarketstackAuditError("unexpected source manifest")
    contract_path = repo_root / "config/experiments" / f"{contract['pilot_id']}.json"
    if manifest.get("contract_sha256") != sha256_file(contract_path):
        raise MarketstackAuditError("source manifest contract checksum mismatch")
    if manifest.get("strategy_data_evaluated") is not False or manifest.get("api_token_serialized") is not False:
        raise MarketstackAuditError("source manifest violates the source-only boundary")
    _require_utc(manifest.get("retrieved_at"), "retrieved_at")
    files = manifest.get("files")
    endpoints = tuple(contract.get("pilot_request_endpoints", ALLOWED_ENDPOINTS))
    expected_count = len(EXPECTED_TICKERS) * len(endpoints)
    if not isinstance(files, list) or len(files) != expected_count or manifest.get("request_count") != expected_count:
        raise MarketstackAuditError("source manifest request count changed")
    indexed: dict[tuple[str, str], Path] = {}
    for item in files:
        if not isinstance(item, Mapping):
            raise MarketstackAuditError("source file record must be an object")
        endpoint = item.get("endpoint")
        ticker = item.get("ticker")
        if endpoint not in endpoints or ticker not in EXPECTED_TICKERS:
            raise MarketstackAuditError("source file identity is outside the pilot")
        key = (str(ticker), str(endpoint))
        if key in indexed or item.get("error") is not None:
            raise MarketstackAuditError("source response is duplicate or failed")
        if item.get("credential_serialized") is not False:
            raise MarketstackAuditError("credential serialization flag is unsafe")
        parameters = item.get("request_parameters")
        if not isinstance(parameters, Mapping) or "access_key" in parameters:
            raise MarketstackAuditError("source manifest contains unsafe request parameters")
        path = _repo_file(repo_root, item.get("path"), "Marketstack response")
        if item.get("sha256") != sha256_file(path) or item.get("bytes") != path.stat().st_size:
            raise MarketstackAuditError("source response checksum or size mismatch")
        indexed[key] = path
    if set(indexed) != {(ticker, endpoint) for ticker in EXPECTED_TICKERS for endpoint in endpoints}:
        raise MarketstackAuditError("source manifest endpoint matrix is incomplete")
    return indexed


def finite_float(value: Decimal) -> float:
    """Convert an audited decimal for report serialization without allowing infinity."""

    result = float(value)
    if not math.isfinite(result):
        raise MarketstackAuditError("numeric conversion is not finite")
    return result
