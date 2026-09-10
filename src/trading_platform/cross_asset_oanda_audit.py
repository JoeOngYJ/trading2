"""Fail-closed, price-blind qualification helpers for the OANDA A1 source pilot.

This module is deliberately offline. Network access lives only in the bounded downloader.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping, Sequence


CONTRACT_SCHEMA = "cross-asset-a1-oanda-source-pilot-contract-v1"
EXPERIMENT_ID = "cross-asset-a1-oanda-source-pilot-v1"
SUCCESSOR_EXPERIMENT_ID = "cross-asset-a1-oanda-source-pilot-v2"
SUCCESSOR_SCHEMA = "cross-asset-a1-oanda-source-pilot-amendment-v1"
MANDATE_SCHEMA = "cross-asset-research-mandate-v5"
MANDATE_ID = "retail-cross-asset-research-v5"
SOURCE_MANIFEST_SCHEMA = "cross-asset-a1-oanda-source-manifest-v1"
REPORT_SCHEMA = "cross-asset-a1-oanda-source-audit-v1"
EVIDENCE_SCHEMA = "cross-asset-a1-oanda-source-evidence-v1"
INSTRUMENT_IDS = (
    "SPX500_USD",
    "XAU_USD",
    "WTICO_USD",
    "EUR_USD",
    "USB10Y_USD",
)
REQUIRED_FAMILIES = frozenset({"global_equity", "gold", "energy", "foreign_exchange"})
CHUNK_BOUNDARIES = (
    "2005-01-01T00:00:00Z",
    "2010-01-01T00:00:00Z",
    "2014-01-01T00:00:00Z",
    "2018-01-01T00:00:00Z",
    "2022-01-01T00:00:00Z",
    "2026-01-01T00:00:00Z",
)


class OandaAuditError(ValueError):
    """Raised when the frozen OANDA contract or acquired data fails closed."""


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        indent=2,
        sort_keys=True,
        separators=(",", ": "),
    ) + "\n"


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_canonical(path: Path, label: str) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
        payload = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OandaAuditError(f"cannot read {label}: {path}") from exc
    if not isinstance(payload, dict) or raw != canonical_json(payload):
        raise OandaAuditError(f"{label} must be a canonical JSON object")
    return payload


def _repo_file(root: Path, raw: Any, label: str) -> Path:
    if not isinstance(raw, str) or not raw or Path(raw).is_absolute():
        raise OandaAuditError(f"{label} must be repository-relative")
    boundary = root.resolve(strict=True)
    try:
        path = (boundary / raw).resolve(strict=True)
        path.relative_to(boundary)
    except (OSError, ValueError) as exc:
        raise OandaAuditError(f"invalid {label}") from exc
    if not path.is_file():
        raise OandaAuditError(f"{label} must be a regular file")
    return path


def _utc(raw: Any, label: str) -> datetime:
    if not isinstance(raw, str) or not raw:
        raise OandaAuditError(f"{label} must be an explicit UTC timestamp")
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OandaAuditError(f"invalid {label}") from exc
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise OandaAuditError(f"{label} must use explicit UTC")
    return value


def load_contract(contract_path: Path, mandate_path: Path) -> dict[str, Any]:
    mandate = _load_canonical(mandate_path, "OANDA A1 mandate")
    if mandate.get("schema_version") != MANDATE_SCHEMA or mandate.get("mandate_id") != MANDATE_ID:
        raise OandaAuditError("unexpected OANDA A1 mandate")
    if mandate.get("status") != "frozen_a1_oanda_read_only_data_qualification_only":
        raise OandaAuditError("OANDA mandate is not frozen read-only")
    authority = mandate.get("authority", {})
    for key in (
        "live_trading_authorized",
        "order_submission_allowed",
        "paper_trading_authorized",
        "execution_credentials_allowed",
    ):
        if authority.get(key) is not False:
            raise OandaAuditError(f"unsafe OANDA mandate authority: {key}")
    if authority.get("maximum_live_allocation_gbp") != 0:
        raise OandaAuditError("OANDA mandate live allocation must remain zero")
    token_policy = mandate.get("data_provider_token_policy", {})
    if token_policy.get("allowed_http_method") != "GET":
        raise OandaAuditError("OANDA mandate must allow GET only")
    if token_policy.get("allowed_environment_variables") != [
        "OANDA_ACCOUNT_ID",
        "OANDA_API_TOKEN",
        "OANDA_API_URL",
    ]:
        raise OandaAuditError("OANDA environment allowlist changed")
    for key in (
        "broker_private_state_access_allowed",
        "database_or_message_bus_tokens_allowed",
        "may_be_logged_or_serialized",
        "order_or_order_preview_access_allowed",
        "repository_storage_allowed",
        "runtime_order_or_signal_access_allowed",
    ):
        if token_policy.get(key) is not False:
            raise OandaAuditError(f"unsafe OANDA token policy: {key}")
    scope = mandate.get("execution_scope", {})
    if scope.get("candidate_oanda_instruments") != list(INSTRUMENT_IDS):
        raise OandaAuditError("OANDA mandate candidate universe changed")
    if scope.get("approved_execution_instrument_ids") != []:
        raise OandaAuditError("OANDA mandate cannot approve execution instruments")
    if scope.get("oanda_data_research_authorized") is not True:
        raise OandaAuditError("OANDA data research is not authorized")
    if scope.get("oanda_execution_authorized") is not False:
        raise OandaAuditError("OANDA execution must remain prohibited")

    contract = _load_canonical(contract_path, "OANDA A1 source contract")
    if contract.get("schema_version") != CONTRACT_SCHEMA or contract.get("experiment_id") != EXPERIMENT_ID:
        raise OandaAuditError("unexpected OANDA A1 source contract")
    if contract.get("status") != "frozen":
        raise OandaAuditError("OANDA A1 source contract is not frozen")
    _utc(contract.get("frozen_at"), "frozen_at")
    candidates = contract.get("candidate_instruments")
    if not isinstance(candidates, list) or tuple(item.get("instrument_id") for item in candidates) != INSTRUMENT_IDS:
        raise OandaAuditError("OANDA pilot universe changed")
    if {item.get("family") for item in candidates[:4]} != REQUIRED_FAMILIES:
        raise OandaAuditError("OANDA required family set changed")
    rules = contract.get("acceptance_rules", {})
    if rules.get("a1_stage_passed_by_this_pilot") is not False:
        raise OandaAuditError("source pilot cannot pass A1")
    if rules.get("strategy_research_authorized_by_this_pilot") is not False:
        raise OandaAuditError("source pilot cannot authorize strategy research")
    if set(rules.get("required_families", ())) != REQUIRED_FAMILIES:
        raise OandaAuditError("source pilot required families changed")
    boundary = contract.get("evidence_boundary", {})
    if boundary.get("candle_start_inclusive") != CHUNK_BOUNDARIES[0]:
        raise OandaAuditError("OANDA pilot start changed")
    if boundary.get("candle_end_exclusive") != CHUNK_BOUNDARIES[-1]:
        raise OandaAuditError("OANDA pilot end changed")
    if boundary.get("sealed_2026_price_access_allowed") is not False:
        raise OandaAuditError("sealed 2026 prices must remain inaccessible")
    plan = contract.get("request_plan", {})
    if plan.get("allowed_http_method") != "GET" or plan.get("maximum_requests") != 26:
        raise OandaAuditError("OANDA request method or ceiling changed")
    if tuple(plan.get("chunk_boundaries", ())) != CHUNK_BOUNDARIES:
        raise OandaAuditError("OANDA request chunks changed")
    if plan.get("permitted_endpoint_templates") != [
        "/v3/accounts/{accountID}/instruments",
        "/v3/instruments/{instrument}/candles",
    ]:
        raise OandaAuditError("OANDA endpoint allowlist changed")
    if plan.get("candle_query") != {
        "alignmentTimezone": "America/New_York",
        "dailyAlignment": "17",
        "granularity": "D",
        "price": "BA",
        "smooth": "false",
    }:
        raise OandaAuditError("OANDA candle query changed")
    access = contract.get("source_access", {})
    if access.get("api_base_url") != "https://api-fxtrade.oanda.com":
        raise OandaAuditError("OANDA API host changed")
    if access.get("api_token_environment_variable") != "OANDA_API_TOKEN":
        raise OandaAuditError("OANDA token variable changed")
    if access.get("account_id_environment_variable") != "OANDA_ACCOUNT_ID":
        raise OandaAuditError("OANDA account variable changed")
    if access.get("api_token_may_be_logged_or_serialized") is not False:
        raise OandaAuditError("OANDA token serialization must remain prohibited")
    prohibitions = contract.get("prohibitions", {})
    for key, value in prohibitions.items():
        if value is not False:
            raise OandaAuditError(f"unsafe OANDA source permission: {key}")
    return contract


def load_successor_contract(path: Path, repo_root: Path) -> dict[str, Any]:
    successor = _load_canonical(path, "OANDA source successor")
    if successor.get("schema_version") != SUCCESSOR_SCHEMA:
        raise OandaAuditError("unexpected OANDA successor schema")
    if successor.get("experiment_id") != SUCCESSOR_EXPERIMENT_ID:
        raise OandaAuditError("unexpected OANDA successor experiment")
    if successor.get("supersedes") != EXPERIMENT_ID or successor.get("status") != "frozen":
        raise OandaAuditError("OANDA successor lineage changed")
    _utc(successor.get("activated_at"), "successor activated_at")
    base = successor.get("base_contract", {})
    base_path = _repo_file(repo_root, base.get("path"), "OANDA base contract")
    if sha256_file(base_path) != base.get("sha256"):
        raise OandaAuditError("OANDA base contract checksum changed")
    evidence = successor.get("frozen_predecessor_evidence", {})
    for key in ("audit_report", "evidence_manifest", "source_manifest"):
        record = evidence.get(key, {})
        evidence_path = _repo_file(repo_root, record.get("path"), f"OANDA predecessor {key}")
        if sha256_file(evidence_path) != record.get("sha256"):
            raise OandaAuditError(f"OANDA predecessor {key} checksum changed")
    expected_changes = {
        "new_provider_requests_allowed": False,
        "output_artifact_root": "artifacts/agent-level-experiment/cross-asset/a1-oanda-source-pilot-v2",
        "raw_source_reuse_required": True,
        "wtico_excluded_presegment_end": "2005-11-27T22:00:00Z",
        "wtico_usable_segment_start_inclusive": "2005-11-27T22:00:00Z",
    }
    if successor.get("changes_from_predecessor") != expected_changes:
        raise OandaAuditError("OANDA successor changes are not the frozen minimal segment change")
    return successor


def build_successor_report(successor: Mapping[str, Any], repo_root: Path) -> dict[str, Any]:
    evidence = successor["frozen_predecessor_evidence"]
    predecessor_path = _repo_file(
        repo_root, evidence["audit_report"]["path"], "OANDA predecessor report"
    )
    predecessor = _load_canonical(predecessor_path, "OANDA predecessor report")
    if predecessor.get("decision") != "oanda_source_pilot_rejected":
        raise OandaAuditError("OANDA predecessor was not the frozen rejection")
    results = predecessor.get("instrument_results")
    if not isinstance(results, list) or len(results) != len(INSTRUMENT_IDS):
        raise OandaAuditError("OANDA predecessor instrument results changed")
    oil = next((item for item in results if item.get("instrument_id") == "WTICO_USD"), None)
    if not isinstance(oil, Mapping):
        raise OandaAuditError("OANDA predecessor oil result is missing")
    expected_gap = {
        "from": "2005-11-22T22:00:00Z",
        "hours": "120",
        "to": "2005-11-27T22:00:00Z",
    }
    if oil.get("failures") != ["internal_gap_exceeds_98_hours"] or oil.get("gaps") != [expected_gap]:
        raise OandaAuditError("OANDA predecessor oil failure is not the frozen single gap")
    if any(
        item.get("decision") != "candidate_pass"
        for item in results
        if item.get("instrument_id") != "WTICO_USD"
    ):
        raise OandaAuditError("OANDA predecessor has an unexpected non-oil failure")

    base_artifact = predecessor_path.parent
    source_manifest_path = _repo_file(
        repo_root, evidence["source_manifest"]["path"], "OANDA predecessor source manifest"
    )
    base_contract_path = _repo_file(
        repo_root, successor["base_contract"]["path"], "OANDA base contract"
    )
    base_contract = _load_canonical(base_contract_path, "OANDA base contract")
    validate_source_manifest(base_contract, source_manifest_path.parent)
    specs = [item for item in build_request_specs(base_contract) if item.instrument_id == "WTICO_USD"]
    start = _utc(
        successor["changes_from_predecessor"]["wtico_usable_segment_start_inclusive"],
        "WTICO successor segment start",
    )
    post_segment = set()
    for spec in specs:
        payload = parse_json_bytes((base_artifact / "raw" / spec.filename).read_bytes(), spec.filename)
        for row in payload.get("candles", []):
            observed = _utc(row.get("time"), "WTICO candle time")
            if observed >= start:
                post_segment.add(observed)
    if len(post_segment) < 3500:
        raise OandaAuditError("WTICO post-gap segment is too short")
    if max(post_segment).isoformat().replace("+00:00", "Z") != oil.get("last_candle_at"):
        raise OandaAuditError("WTICO post-gap segment does not reach the frozen end")

    successor_results = []
    for item in results:
        copied = dict(item)
        if copied["instrument_id"] == "WTICO_USD":
            copied.update(
                {
                    "complete_daily_candles": len(post_segment),
                    "decision": "candidate_pass_segmented",
                    "excluded_predecessor_gap": expected_gap,
                    "failures": [],
                    "first_candle_at": successor["changes_from_predecessor"][
                        "wtico_usable_segment_start_inclusive"
                    ],
                    "gap_count": 0,
                    "gaps": [],
                    "predecessor_decision": "candidate_reject",
                }
            )
        successor_results.append(copied)
    return {
        "a1_stage_passed": False,
        "decision": "oanda_source_pilot_passed_for_successor_cost_and_semantics_qualification",
        "experiment_id": SUCCESSOR_EXPERIMENT_ID,
        "instrument_results": successor_results,
        "new_provider_requests": 0,
        "passed_candidate_count": len(successor_results),
        "qualified_for_strategy_evaluation": False,
        "raw_source_reused_by_checksum": True,
        "required_families_passed": sorted(REQUIRED_FAMILIES),
        "schema_version": "cross-asset-a1-oanda-source-successor-audit-v1",
        "source_pilot_passed": True,
    }


def validate_runtime_identity(contract: Mapping[str, Any], api_url: str, account_id: str) -> None:
    if api_url != contract["source_access"]["api_base_url"]:
        raise OandaAuditError("configured OANDA API URL differs from frozen host")
    if not account_id:
        raise OandaAuditError("OANDA account ID is missing")
    if sha256_bytes(account_id.encode("utf-8")) != contract["source_access"]["account_id_sha256"]:
        raise OandaAuditError("configured OANDA account differs from the frozen account digest")


@dataclass(frozen=True, slots=True)
class RequestSpec:
    filename: str
    instrument_id: str | None
    kind: str
    parameters: Mapping[str, str]
    path_template: str


def build_request_specs(contract: Mapping[str, Any]) -> tuple[RequestSpec, ...]:
    specs = [
        RequestSpec(
            filename="instrument-catalogue.json",
            instrument_id=None,
            kind="instrument_catalogue",
            parameters={},
            path_template="/v3/accounts/{accountID}/instruments",
        )
    ]
    query = contract["request_plan"]["candle_query"]
    boundaries = contract["request_plan"]["chunk_boundaries"]
    for candidate in contract["candidate_instruments"]:
        instrument_id = candidate["instrument_id"]
        for index, (start, end) in enumerate(zip(boundaries, boundaries[1:]), start=1):
            specs.append(
                RequestSpec(
                    filename=f"{instrument_id.casefold()}-daily-{index:02d}.json",
                    instrument_id=instrument_id,
                    kind="daily_candles",
                    parameters={**query, "from": start, "to": end},
                    path_template="/v3/instruments/{instrument}/candles",
                )
            )
    if len(specs) != contract["request_plan"]["maximum_requests"]:
        raise OandaAuditError("OANDA request count differs from frozen ceiling")
    return tuple(specs)


def parse_json_bytes(raw: bytes, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OandaAuditError(f"invalid JSON response: {label}") from exc
    if not isinstance(payload, dict):
        raise OandaAuditError(f"response must be an object: {label}")
    return payload


def catalogue_names(payload: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    rows = payload.get("instruments")
    if not isinstance(rows, list):
        raise OandaAuditError("instrument catalogue is missing instruments")
    result: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping) or not isinstance(row.get("name"), str):
            raise OandaAuditError("instrument catalogue contains an invalid row")
        name = row["name"]
        if name in result:
            raise OandaAuditError(f"instrument catalogue repeats {name}")
        result[name] = row
    return result


def _decimal(raw: Any, label: str) -> Decimal:
    if isinstance(raw, bool) or raw is None:
        raise OandaAuditError(f"missing candle field: {label}")
    try:
        value = Decimal(str(raw))
    except InvalidOperation as exc:
        raise OandaAuditError(f"invalid candle field: {label}") from exc
    if not value.is_finite() or value <= 0:
        raise OandaAuditError(f"non-positive candle field: {label}")
    return value


def audit_candle_payload(
    payload: Mapping[str, Any],
    instrument_id: str,
    start: str,
    end: str,
    *,
    allow_aligned_boundary_overlap: bool = False,
) -> tuple[datetime, ...]:
    if payload.get("instrument") != instrument_id or payload.get("granularity") != "D":
        raise OandaAuditError(f"candle identity mismatch for {instrument_id}")
    rows = payload.get("candles")
    if not isinstance(rows, list):
        raise OandaAuditError(f"candle response is missing rows for {instrument_id}")
    lower = _utc(start, "chunk start")
    upper = _utc(end, "chunk end")
    timestamps: list[datetime] = []
    for row in rows:
        if not isinstance(row, Mapping) or row.get("complete") is not True:
            raise OandaAuditError(f"incomplete candle for {instrument_id}")
        observed = _utc(row.get("time"), "candle time")
        earliest = lower - timedelta(hours=26) if allow_aligned_boundary_overlap else lower
        if observed < earliest or observed >= upper:
            raise OandaAuditError(f"candle outside frozen chunk for {instrument_id}")
        if timestamps and observed <= timestamps[-1]:
            raise OandaAuditError(f"non-increasing candle time for {instrument_id}")
        timestamps.append(observed)
        sides: dict[str, dict[str, Decimal]] = {}
        for side in ("bid", "ask"):
            values = row.get(side)
            if not isinstance(values, Mapping):
                raise OandaAuditError(f"missing {side} candle for {instrument_id}")
            parsed = {field: _decimal(values.get(field), f"{side}.{field}") for field in "ohlc"}
            if parsed["l"] > min(parsed["o"], parsed["c"]):
                raise OandaAuditError(f"invalid {side} low for {instrument_id}")
            if parsed["h"] < max(parsed["o"], parsed["c"]) or parsed["l"] > parsed["h"]:
                raise OandaAuditError(f"invalid {side} high for {instrument_id}")
            sides[side] = parsed
        if any(sides["ask"][field] < sides["bid"][field] for field in "ohlc"):
            raise OandaAuditError(f"crossed bid/ask candle for {instrument_id}")
        volume = row.get("volume")
        if isinstance(volume, bool) or not isinstance(volume, int) or volume < 0:
            raise OandaAuditError(f"invalid candle volume for {instrument_id}")
    return tuple(timestamps)


def audit_instrument_history(
    payloads: Sequence[Mapping[str, Any]],
    candidate: Mapping[str, Any],
    boundaries: Sequence[str] = CHUNK_BOUNDARIES,
) -> dict[str, Any]:
    instrument_id = str(candidate["instrument_id"])
    if len(payloads) != len(boundaries) - 1:
        raise OandaAuditError(f"wrong chunk count for {instrument_id}")
    timestamps: list[datetime] = []
    fingerprints: dict[datetime, str] = {}
    identical_boundary_overlaps = 0
    for index, (payload, start, end) in enumerate(zip(payloads, boundaries, boundaries[1:])):
        chunk = audit_candle_payload(
            payload,
            instrument_id,
            start,
            end,
            allow_aligned_boundary_overlap=index > 0,
        )
        for observed, row in zip(chunk, payload["candles"]):
            fingerprint = json.dumps(
                row,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            if observed in fingerprints:
                if fingerprints[observed] != fingerprint:
                    raise OandaAuditError(
                        f"conflicting duplicate chunk boundary for {instrument_id}"
                    )
                identical_boundary_overlaps += 1
                continue
            if timestamps and observed <= timestamps[-1]:
                raise OandaAuditError(f"reversed chunk boundary for {instrument_id}")
            timestamps.append(observed)
            fingerprints[observed] = fingerprint
    gaps = []
    for previous, current in zip(timestamps, timestamps[1:]):
        hours = (current - previous).total_seconds() / 3600
        if hours > 98:
            gaps.append(
                {
                    "from": previous.isoformat().replace("+00:00", "Z"),
                    "hours": format(Decimal(str(hours)).normalize(), "f"),
                    "to": current.isoformat().replace("+00:00", "Z"),
                }
            )
    first = timestamps[0] if timestamps else None
    last = timestamps[-1] if timestamps else None
    minimum_start = datetime.fromisoformat(candidate["minimum_usable_start_on_or_before"]).replace(
        tzinfo=timezone.utc
    )
    failures = []
    if len(timestamps) < int(candidate["minimum_complete_daily_candles"]):
        failures.append("insufficient_complete_daily_candles")
    if first is None or first > minimum_start + timedelta(days=1):
        failures.append("history_starts_after_frozen_minimum")
    if gaps:
        failures.append("internal_gap_exceeds_98_hours")
    return {
        "complete_daily_candles": len(timestamps),
        "decision": "candidate_pass" if not failures else "candidate_reject",
        "failures": failures,
        "first_candle_at": None if first is None else first.isoformat().replace("+00:00", "Z"),
        "gap_count": len(gaps),
        "gaps": gaps,
        "identical_boundary_overlap_count": identical_boundary_overlaps,
        "instrument_id": instrument_id,
        "last_candle_at": None if last is None else last.isoformat().replace("+00:00", "Z"),
    }


def build_audit_report(contract: Mapping[str, Any], raw_root: Path) -> dict[str, Any]:
    specs = build_request_specs(contract)
    catalogue_path = raw_root / specs[0].filename
    catalogue = catalogue_names(parse_json_bytes(catalogue_path.read_bytes(), specs[0].filename))
    results = []
    for candidate in contract["candidate_instruments"]:
        instrument_id = candidate["instrument_id"]
        catalogue_row = catalogue.get(instrument_id)
        if catalogue_row is None:
            results.append(
                {
                    "catalogue_display_name": None,
                    "catalogue_type": None,
                    "complete_daily_candles": 0,
                    "decision": "candidate_reject",
                    "failures": ["instrument_absent_from_account_catalogue"],
                    "family": candidate["family"],
                    "first_candle_at": None,
                    "gap_count": 0,
                    "gaps": [],
                    "identical_boundary_overlap_count": 0,
                    "instrument_id": instrument_id,
                    "last_candle_at": None,
                }
            )
            continue
        candle_specs = [item for item in specs if item.instrument_id == instrument_id]
        payloads = [parse_json_bytes((raw_root / item.filename).read_bytes(), item.filename) for item in candle_specs]
        result = audit_instrument_history(payloads, candidate)
        result.update(
            {
                "catalogue_display_name": catalogue_row.get("displayName"),
                "catalogue_type": catalogue_row.get("type"),
                "family": candidate["family"],
            }
        )
        results.append(result)
    passing_families = {
        item["family"] for item in results if item["decision"] == "candidate_pass"
    }
    source_pass = REQUIRED_FAMILIES.issubset(passing_families)
    return {
        "a1_stage_passed": False,
        "decision": (
            "oanda_source_pilot_passed_for_successor_cost_and_semantics_qualification"
            if source_pass
            else "oanda_source_pilot_rejected"
        ),
        "experiment_id": EXPERIMENT_ID,
        "instrument_results": results,
        "passed_candidate_count": sum(item["decision"] == "candidate_pass" for item in results),
        "qualified_for_strategy_evaluation": False,
        "required_families_passed": sorted(REQUIRED_FAMILIES.intersection(passing_families)),
        "schema_version": REPORT_SCHEMA,
        "source_pilot_passed": source_pass,
    }


def validate_source_manifest(
    contract: Mapping[str, Any], artifact_root: Path
) -> dict[str, Any]:
    manifest = _load_canonical(artifact_root / "source-manifest.json", "OANDA source manifest")
    if manifest.get("schema_version") != SOURCE_MANIFEST_SCHEMA:
        raise OandaAuditError("unexpected OANDA source manifest")
    if manifest.get("experiment_id") != EXPERIMENT_ID:
        raise OandaAuditError("OANDA source manifest experiment changed")
    if manifest.get("account_id_sha256") != contract["source_access"]["account_id_sha256"]:
        raise OandaAuditError("OANDA source manifest account binding changed")
    if manifest.get("api_base_url") != contract["source_access"]["api_base_url"]:
        raise OandaAuditError("OANDA source manifest host changed")
    _utc(manifest.get("retrieved_at"), "manifest retrieved_at")
    sources = manifest.get("sources")
    if not isinstance(sources, list) or not sources:
        raise OandaAuditError("OANDA source manifest has no sources")
    seen = set()
    for source in sources:
        if not isinstance(source, Mapping):
            raise OandaAuditError("invalid OANDA source record")
        if source.get("http_method") != "GET" or source.get("http_status") != 200:
            raise OandaAuditError("OANDA source record is not a successful GET")
        relative = source.get("path")
        if not isinstance(relative, str) or Path(relative).is_absolute():
            raise OandaAuditError("invalid OANDA raw path")
        if relative in seen:
            raise OandaAuditError("duplicate OANDA raw path")
        seen.add(relative)
        try:
            path = (artifact_root / relative).resolve(strict=True)
            path.relative_to(artifact_root.resolve(strict=True))
        except (OSError, ValueError) as exc:
            raise OandaAuditError("OANDA raw path escapes artifact root") from exc
        if not path.is_file() or sha256_file(path) != source.get("sha256"):
            raise OandaAuditError(f"OANDA raw checksum mismatch: {relative}")
        if path.stat().st_size != source.get("bytes"):
            raise OandaAuditError(f"OANDA raw byte count mismatch: {relative}")
        if "account" in str(source.get("endpoint_template", "")).casefold():
            if source.get("endpoint_template") != "/v3/accounts/{accountID}/instruments":
                raise OandaAuditError("unexpected account-scoped OANDA endpoint")
        if any(key.casefold() in {"authorization", "token", "accountid"} for key in source.get("parameters", {})):
            raise OandaAuditError("credential material appears in OANDA source parameters")
    expected_catalogue = "raw/instrument-catalogue.json"
    if expected_catalogue not in seen:
        raise OandaAuditError("OANDA source manifest is missing the instrument catalogue")
    return manifest
