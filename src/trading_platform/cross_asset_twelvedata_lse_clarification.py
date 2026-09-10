"""Offline audit for the exact-line Twelve Data LSE boundary clarification."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from trading_platform.cross_asset_twelvedata_audit import (
    TwelveDataAuditError,
    audit_corporate_actions,
    audit_earliest,
    audit_time_series,
    canonical_json,
    parse_response,
    sha256_file,
)
from trading_platform.cross_asset_twelvedata_lse_audit import (
    load_contract as load_v1_contract,
    validate_source_manifest as validate_v1_source_manifest,
)


CONTRACT_SCHEMA = "cross-asset-a1-exact-lse-boundary-clarification-contract-v1"
REVIEW_ID = "cross-asset-a1-executable-universe-feasibility-v2"
MANIFEST_SCHEMA = "cross-asset-a1-twelvedata-lse-clarification-source-manifest-v1"
EVIDENCE_SCHEMA = "cross-asset-a1-exact-lse-boundary-clarification-evidence-manifest-v1"


def load_contract(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    payload = __import__("json").loads(raw)
    if raw != canonical_json(payload):
        raise TwelveDataAuditError("LSE clarification contract is not canonical")
    if (
        payload.get("schema_version") != CONTRACT_SCHEMA
        or payload.get("review_id") != REVIEW_ID
        or payload.get("status") != "frozen"
    ):
        raise TwelveDataAuditError("unexpected or unfrozen LSE clarification contract")
    expected = ("SWDA:LSE", "VAGS:LSE", "SGLN:LSE", "COMM:LSE")
    instruments = payload.get("expected_instruments")
    if not isinstance(instruments, list) or tuple(
        item.get("provider_symbol") for item in instruments
    ) != expected:
        raise TwelveDataAuditError("exact LSE clarification universe changed")
    plan = payload.get("request_plan", {})
    if (
        plan.get("maximum_requests") != 4
        or plan.get("maximum_weighted_credits") != 4
        or plan.get("start_date_inclusive") != "2025-02-03"
        or plan.get("end_date_exclusive") != "2025-03-01"
        or plan.get("documented_time_series_end_date_semantics")
        != "exclusive_upper_boundary"
    ):
        raise TwelveDataAuditError("exact LSE clarification request boundary changed")
    reuse = payload.get("reuse_policy", {})
    if (
        reuse.get("allowed_endpoints")
        != ["dividends", "earliest_timestamp", "splits"]
        or reuse.get("corporate_action_order_rule")
        != "dates_must_be_unique_and_strictly_monotonic_ascending_or_descending"
        or reuse.get("raw_bytes_may_be_modified") is not False
        or reuse.get("reused_source_manifest_must_validate_under_v1_contract") is not True
    ):
        raise TwelveDataAuditError("exact LSE clarification reuse policy changed")
    for key, value in payload.get("prohibitions", {}).items():
        if value is not False:
            raise TwelveDataAuditError(f"unsafe exact LSE clarification permission: {key}")
    payload["_contract_sha256"] = sha256_file(path)
    return payload


@dataclass(frozen=True, slots=True)
class RequestSpec:
    filename: str
    parameters: Mapping[str, str]
    path: str
    provider_symbol: str
    symbol: str


def build_request_specs(contract: Mapping[str, Any]) -> tuple[RequestSpec, ...]:
    plan = contract["request_plan"]
    specs = tuple(
        RequestSpec(
            filename=f"{item['symbol'].casefold()}-time-series.json",
            parameters={
                "adjust": plan["adjust"],
                "end_date": plan["end_date_exclusive"],
                "interval": plan["interval"],
                "order": plan["order"],
                "outputsize": str(plan["outputsize"]),
                "start_date": plan["start_date_inclusive"],
                "symbol": item["provider_symbol"],
                "timezone": plan["timezone"],
            },
            path=plan["endpoint_path"],
            provider_symbol=item["provider_symbol"],
            symbol=item["symbol"],
        )
        for item in contract["expected_instruments"]
    )
    if len(specs) != 4 or any(
        "apikey" in key.casefold() for spec in specs for key in spec.parameters
    ):
        raise TwelveDataAuditError("exact LSE clarification request plan changed")
    return specs


def validate_source_manifest(
    repo_root: Path, manifest_path: Path, contract: Mapping[str, Any]
) -> dict[str, Path]:
    raw = manifest_path.read_text(encoding="utf-8")
    manifest = __import__("json").loads(raw)
    if raw != canonical_json(manifest):
        raise TwelveDataAuditError("LSE clarification source manifest is not canonical")
    if (
        manifest.get("schema_version") != MANIFEST_SCHEMA
        or manifest.get("review_id") != REVIEW_ID
        or manifest.get("contract_sha256") != contract.get("_contract_sha256")
        or manifest.get("authentication")
        != "authorization_header_redacted_not_serialized"
    ):
        raise TwelveDataAuditError("LSE clarification source lineage changed")
    records = manifest.get("responses")
    specs = build_request_specs(contract)
    if not isinstance(records, list) or len(records) != len(specs):
        raise TwelveDataAuditError("LSE clarification response count changed")
    expected = {spec.symbol: spec for spec in specs}
    indexed: dict[str, Path] = {}
    for record in records:
        symbol = str(record.get("symbol"))
        if symbol not in expected or symbol in indexed:
            raise TwelveDataAuditError("unexpected or duplicate LSE clarification response")
        spec = expected[symbol]
        if (
            record.get("endpoint") != "time_series"
            or record.get("parameters") != dict(spec.parameters)
            or record.get("provider_symbol") != spec.provider_symbol
            or record.get("weight") != 1
        ):
            raise TwelveDataAuditError("LSE clarification request lineage changed")
        relative = record.get("path")
        if not isinstance(relative, str) or Path(relative).is_absolute():
            raise TwelveDataAuditError("unsafe LSE clarification artifact path")
        path = (repo_root / relative).resolve(strict=True)
        path.relative_to(repo_root.resolve(strict=True))
        if (
            path.name != spec.filename
            or record.get("sha256") != sha256_file(path)
            or record.get("bytes") != path.stat().st_size
        ):
            raise TwelveDataAuditError("LSE clarification response checksum changed")
        indexed[symbol] = path
    return indexed


def _compatible_instrument(instrument: Mapping[str, Any]) -> dict[str, Any]:
    return {
        **instrument,
        "corporate_action_identity_via_time_series": True,
        "expected_mic_code": instrument["expected_mic"],
    }


def _audit_direction_agnostic_actions(
    payload: Mapping[str, Any],
    instrument: Mapping[str, Any],
    endpoint: str,
    start: str,
    end: str,
) -> dict[str, Any]:
    rows = payload.get(endpoint)
    if not isinstance(rows, list):
        raise TwelveDataAuditError(f"{endpoint} response has no {endpoint} array")
    field = "ex_date" if endpoint == "dividends" else "date"
    dates = [row.get(field) for row in rows if isinstance(row, Mapping)]
    if len(dates) != len(rows) or len(dates) != len(set(dates)):
        raise TwelveDataAuditError(f"{endpoint} records must have unique dates")
    if dates not in (sorted(dates), sorted(dates, reverse=True)):
        raise TwelveDataAuditError(f"{endpoint} records are not monotonic")
    normalized = copy.deepcopy(payload)
    normalized[endpoint] = sorted(rows, key=lambda row: row[field])
    result = audit_corporate_actions(normalized, instrument, endpoint, start, end)
    return {**result, "provider_order": "descending" if dates == sorted(dates, reverse=True) and dates else "ascending"}


def audit_outcome(
    repo_root: Path,
    contract: Mapping[str, Any],
    manifest_path: Path,
    v1_contract_path: Path,
    v1_manifest_path: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    new_series = validate_source_manifest(repo_root, manifest_path, contract)
    v1_contract = load_v1_contract(v1_contract_path)
    v1_indexed = validate_v1_source_manifest(repo_root, v1_manifest_path, v1_contract)
    failures: list[dict[str, str]] = []
    results: list[dict[str, Any]] = []
    start = v1_contract["candidate_paths"]["exact_lse_cash"]["request_plan"][
        "corporate_action_start"
    ]
    end = v1_contract["candidate_paths"]["exact_lse_cash"]["request_plan"][
        "corporate_action_end"
    ]
    for instrument in contract["expected_instruments"]:
        symbol = instrument["symbol"]
        compatible = _compatible_instrument(instrument)
        result: dict[str, Any] = {"symbol": symbol}
        checks = (
            (
                "earliest_history",
                lambda: audit_earliest(
                    parse_response(
                        v1_indexed[(symbol, "earliest_timestamp")].read_bytes(),
                        f"{symbol} reused earliest",
                    ),
                    compatible,
                ),
                "earliest",
            ),
            (
                "daily_series",
                lambda: audit_time_series(
                    parse_response(new_series[symbol].read_bytes(), f"{symbol} clarification series"),
                    compatible,
                    contract["expected_pilot_sessions"],
                ),
                "time_series",
            ),
        )
        for gate, check, field in checks:
            try:
                result[field] = check()
            except TwelveDataAuditError as exc:
                result[f"{field}_error"] = str(exc)
                failures.append({"error": str(exc), "gate": gate, "symbol": symbol})
        for endpoint in ("dividends", "splits"):
            try:
                action = _audit_direction_agnostic_actions(
                    parse_response(
                        v1_indexed[(symbol, endpoint)].read_bytes(),
                        f"{symbol} reused {endpoint}",
                    ),
                    compatible,
                    endpoint,
                    start,
                    end,
                )
                result.setdefault("corporate_actions", []).append(action)
            except TwelveDataAuditError as exc:
                result.setdefault("corporate_action_errors", []).append(
                    {"endpoint": endpoint, "error": str(exc)}
                )
                failures.append({"error": str(exc), "gate": endpoint, "symbol": symbol})
        results.append(result)
    return results, failures
