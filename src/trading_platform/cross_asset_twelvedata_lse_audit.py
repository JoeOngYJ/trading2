"""Fail-closed validation for the exact-line Twelve Data LSE A1 pilot.

This module is offline-only. Network acquisition is isolated in the companion downloader.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

from trading_platform.cross_asset_twelvedata_audit import (
    TwelveDataAuditError,
    audit_corporate_actions,
    audit_earliest,
    audit_time_series,
    canonical_json,
    parse_response,
    sha256_file,
)


CONTRACT_SCHEMA = "cross-asset-a1-executable-universe-feasibility-contract-v1"
REVIEW_ID = "cross-asset-a1-executable-universe-feasibility-v1"
MANIFEST_SCHEMA = "cross-asset-a1-twelvedata-lse-source-manifest-v1"
EVIDENCE_SCHEMA = "cross-asset-a1-executable-universe-feasibility-evidence-manifest-v1"
PUBLIC_FACTS_SCHEMA = "cross-asset-a1-public-executable-universe-feasibility-facts-v1"


def load_contract(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    payload = __import__("json").loads(raw)
    if raw != canonical_json(payload):
        raise TwelveDataAuditError("LSE feasibility contract is not canonical")
    if (
        payload.get("schema_version") != CONTRACT_SCHEMA
        or payload.get("review_id") != REVIEW_ID
        or payload.get("status") != "frozen"
    ):
        raise TwelveDataAuditError("unexpected or unfrozen LSE feasibility contract")
    instruments = payload.get("candidate_paths", {}).get("exact_lse_cash", {}).get(
        "expected_instruments"
    )
    expected = (
        ("SWDA", "SWDA:LSE", "XLON", "GBp", "IE00B4L5Y983"),
        ("VAGS", "VAGS:LSE", "XLON", "GBP", "IE00BG47K971"),
        ("SGLN", "SGLN:LSE", "XLON", "GBp", "IE00B4ND3602"),
        ("COMM", "COMM:LSE", "XLON", "GBp", "IE00BDFL4P12"),
    )
    if not isinstance(instruments, list) or tuple(
        (
            item.get("symbol"),
            item.get("provider_symbol"),
            item.get("expected_mic"),
            item.get("expected_currency"),
            item.get("expected_isin"),
        )
        for item in instruments
    ) != expected:
        raise TwelveDataAuditError("exact LSE pilot universe changed")
    request_plan = payload["candidate_paths"]["exact_lse_cash"]["request_plan"]
    if (
        request_plan.get("maximum_requests") != 16
        or request_plan.get("maximum_weighted_credits") != 168
        or request_plan.get("minute_credit_ceiling") != 55
    ):
        raise TwelveDataAuditError("exact LSE request ceiling changed")
    for key, value in payload.get("prohibitions", {}).items():
        if value is not False:
            raise TwelveDataAuditError(f"unsafe exact LSE permission: {key}")
    payload["_contract_sha256"] = sha256_file(path)
    return payload


@dataclass(frozen=True, slots=True)
class RequestSpec:
    endpoint: str
    filename: str
    parameters: Mapping[str, str]
    path: str
    phase: int
    provider_symbol: str
    symbol: str
    weight: int


def build_request_specs(contract: Mapping[str, Any]) -> tuple[RequestSpec, ...]:
    cash = contract["candidate_paths"]["exact_lse_cash"]
    plan = cash["request_plan"]
    paths = plan["endpoint_paths"]
    weights = plan["endpoint_credit_weights"]
    boundary = cash["pilot_boundary"]
    specs: list[RequestSpec] = []
    for instrument in cash["expected_instruments"]:
        symbol = instrument["symbol"]
        provider = instrument["provider_symbol"]
        slug = symbol.casefold()
        specs.extend(
            [
                RequestSpec(
                    "earliest_timestamp",
                    f"{slug}-earliest-timestamp.json",
                    {"interval": plan["interval"], "symbol": provider},
                    paths["earliest_timestamp"],
                    1,
                    provider,
                    symbol,
                    weights["earliest_timestamp"],
                ),
                RequestSpec(
                    "time_series",
                    f"{slug}-time-series.json",
                    {
                        "adjust": plan["adjust"],
                        "end_date": boundary["end_inclusive"],
                        "interval": plan["interval"],
                        "order": plan["order"],
                        "outputsize": str(plan["outputsize"]),
                        "start_date": boundary["start_inclusive"],
                        "symbol": provider,
                        "timezone": plan["timezone"],
                    },
                    paths["time_series"],
                    1,
                    provider,
                    symbol,
                    weights["time_series"],
                ),
            ]
        )
    for phase, instrument in enumerate(cash["expected_instruments"], start=2):
        symbol = instrument["symbol"]
        provider = instrument["provider_symbol"]
        for endpoint in ("dividends", "splits"):
            specs.append(
                RequestSpec(
                    endpoint,
                    f"{symbol.casefold()}-{endpoint}.json",
                    {
                        "end_date": plan["corporate_action_end"],
                        "start_date": plan["corporate_action_start"],
                        "symbol": provider,
                    },
                    paths[endpoint],
                    phase,
                    provider,
                    symbol,
                    weights[endpoint],
                )
            )
    if len(specs) != plan["maximum_requests"]:
        raise TwelveDataAuditError("exact LSE request count changed")
    if sum(spec.weight for spec in specs) != plan["maximum_weighted_credits"]:
        raise TwelveDataAuditError("exact LSE weighted credits changed")
    phase_weights = {
        phase: sum(spec.weight for spec in specs if spec.phase == phase)
        for phase in sorted({spec.phase for spec in specs})
    }
    if phase_weights != {1: 8, 2: 40, 3: 40, 4: 40, 5: 40}:
        raise TwelveDataAuditError("exact LSE phase schedule changed")
    if any("apikey" in key.casefold() for spec in specs for key in spec.parameters):
        raise TwelveDataAuditError("request plan attempts to persist a token")
    return tuple(specs)


def load_public_feasibility_facts(
    path: Path, contract: Mapping[str, Any]
) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    payload = __import__("json").loads(raw)
    if raw != canonical_json(payload):
        raise TwelveDataAuditError("public feasibility facts are not canonical")
    if (
        payload.get("schema_version") != PUBLIC_FACTS_SCHEMA
        or payload.get("review_id") != REVIEW_ID
        or payload.get("decision") != "public_feasibility_only_no_universe_selected"
        or payload.get("universe_selected") is not False
        or payload.get("strategy_evaluation_performed") is not False
        or payload.get("economic_metrics_computed") is not False
        or payload.get("sealed_2026_partition_accessed") is not False
    ):
        raise TwelveDataAuditError("unsafe or mismatched public feasibility facts")
    expected_symbols = tuple(
        item["symbol"]
        for item in contract["candidate_paths"]["broader_derivatives_and_fx"]["candidates"]
    )
    findings = payload.get("candidate_findings")
    if not isinstance(findings, list) or tuple(
        item.get("symbol") for item in findings
    ) != expected_symbols:
        raise TwelveDataAuditError("public feasibility candidate universe changed")
    required_fields = {
        "account_access_state",
        "capital_compatibility",
        "commission_inputs",
        "data_state",
        "expiry_or_funding",
        "instrument",
        "legal_state",
        "margin_snapshot",
        "multiplier_and_tick",
        "notional_snapshot",
        "settlement_or_actions",
        "status",
        "symbol",
    }
    if any(set(item) != required_fields for item in findings):
        raise TwelveDataAuditError("public feasibility fact fields changed")
    allowed_domains = set(contract["source_access"]["official_public_domains"])
    sources = payload.get("source_facts")
    if not isinstance(sources, list) or not sources:
        raise TwelveDataAuditError("public feasibility sources are missing")
    for source in sources:
        if set(source) != {"claim", "source_url"}:
            raise TwelveDataAuditError("public feasibility source fields changed")
        parsed = urlparse(str(source["source_url"]))
        if parsed.scheme != "https" or not any(
            parsed.hostname == domain or str(parsed.hostname).endswith(f".{domain}")
            for domain in allowed_domains
        ):
            raise TwelveDataAuditError("public feasibility source is not an allowed official domain")
    return payload


def _compatible_instrument(instrument: Mapping[str, Any]) -> dict[str, Any]:
    return {
        **instrument,
        "corporate_action_identity_via_time_series": True,
        "expected_mic_code": instrument["expected_mic"],
    }


def validate_source_manifest(
    repo_root: Path, manifest_path: Path, contract: Mapping[str, Any]
) -> dict[tuple[str, str], Path]:
    raw = manifest_path.read_text(encoding="utf-8")
    manifest = __import__("json").loads(raw)
    if raw != canonical_json(manifest):
        raise TwelveDataAuditError("exact LSE source manifest is not canonical")
    if (
        manifest.get("schema_version") != MANIFEST_SCHEMA
        or manifest.get("review_id") != REVIEW_ID
        or manifest.get("contract_sha256") != contract.get("_contract_sha256")
        or manifest.get("authentication") != "authorization_header_redacted_not_serialized"
    ):
        raise TwelveDataAuditError("exact LSE source manifest lineage changed")
    records = manifest.get("responses")
    specs = build_request_specs(contract)
    if not isinstance(records, list) or len(records) != len(specs):
        raise TwelveDataAuditError("exact LSE response count changed")
    expected = {(spec.symbol, spec.endpoint): spec for spec in specs}
    indexed: dict[tuple[str, str], Path] = {}
    for record in records:
        key = (str(record.get("symbol")), str(record.get("endpoint")))
        if key not in expected or key in indexed:
            raise TwelveDataAuditError("unexpected or duplicate exact LSE response")
        spec = expected[key]
        if (
            record.get("parameters") != dict(spec.parameters)
            or record.get("phase") != spec.phase
            or record.get("weight") != spec.weight
            or record.get("provider_symbol") != spec.provider_symbol
        ):
            raise TwelveDataAuditError("exact LSE request lineage changed")
        relative = record.get("path")
        if not isinstance(relative, str) or Path(relative).is_absolute():
            raise TwelveDataAuditError("unsafe exact LSE artifact path")
        path = (repo_root / relative).resolve(strict=True)
        path.relative_to(repo_root.resolve(strict=True))
        if (
            path.name != spec.filename
            or record.get("sha256") != sha256_file(path)
            or record.get("bytes") != path.stat().st_size
        ):
            raise TwelveDataAuditError("exact LSE response checksum changed")
        indexed[key] = path
    lowered = canonical_json(manifest).casefold().replace(
        "authorization_header_redacted_not_serialized", ""
    )
    if "authorization:" in lowered or "api_key" in lowered or "apikey " in lowered:
        raise TwelveDataAuditError("exact LSE manifest may contain credential material")
    return indexed


def audit_manifest_outcome(
    repo_root: Path, manifest_path: Path, contract: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    indexed = validate_source_manifest(repo_root, manifest_path, contract)
    cash = contract["candidate_paths"]["exact_lse_cash"]
    plan = cash["request_plan"]
    results: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for instrument in cash["expected_instruments"]:
        symbol = instrument["symbol"]
        compatible = _compatible_instrument(instrument)
        result: dict[str, Any] = {"symbol": symbol}
        try:
            result["earliest"] = audit_earliest(
                parse_response(indexed[(symbol, "earliest_timestamp")].read_bytes(), f"{symbol} earliest"),
                compatible,
            )
        except TwelveDataAuditError as exc:
            result["earliest_error"] = str(exc)
            failures.append({"error": str(exc), "gate": "earliest_history", "symbol": symbol})
        try:
            result["time_series"] = audit_time_series(
                parse_response(indexed[(symbol, "time_series")].read_bytes(), f"{symbol} series"),
                compatible,
                cash["expected_pilot_sessions"],
            )
        except TwelveDataAuditError as exc:
            result["time_series_error"] = str(exc)
            failures.append({"error": str(exc), "gate": "daily_series", "symbol": symbol})
        for endpoint in ("dividends", "splits"):
            try:
                action = audit_corporate_actions(
                    parse_response(indexed[(symbol, endpoint)].read_bytes(), f"{symbol} {endpoint}"),
                    compatible,
                    endpoint,
                    plan["corporate_action_start"],
                    plan["corporate_action_end"],
                )
                result.setdefault("corporate_actions", []).append(action)
            except TwelveDataAuditError as exc:
                result.setdefault("corporate_action_errors", []).append(
                    {"endpoint": endpoint, "error": str(exc)}
                )
                failures.append({"error": str(exc), "gate": endpoint, "symbol": symbol})
        results.append(result)
    return results, failures
