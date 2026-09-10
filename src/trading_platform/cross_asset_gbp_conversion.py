"""Offline qualification helpers for the A2 GBP conversion-only source."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Any, Mapping

from trading_platform.cross_asset_oanda_hourly import (
    OandaHourlyError,
    _load_canonical,
    _repo_file,
    _utc,
    canonical_json,
    canonical_json_line,
    parse_candle_row,
    sha256_file,
)


CONTRACT_SCHEMA = "cross-asset-a2-gbp-conversion-source-contract-v1"
EXPERIMENT_ID = "cross-asset-a2-gbp-conversion-source-v1"
SOURCE_SCHEMA = "cross-asset-a2-gbp-conversion-source-manifest-v1"
REPORT_SCHEMA = "cross-asset-a2-gbp-conversion-audit-v1"
EVIDENCE_SCHEMA = "cross-asset-a2-gbp-conversion-evidence-v1"


def load_contract(contract_path: Path, mandate_path: Path, repo_root: Path) -> dict[str, Any]:
    mandate = _load_canonical(mandate_path, "A2 conversion mandate")
    if (
        mandate.get("schema_version"),
        mandate.get("mandate_id"),
        mandate.get("status"),
    ) != (
        "cross-asset-research-mandate-v7",
        "retail-cross-asset-research-v7",
        "frozen_a2_offline_strategy_research_and_conversion_data_only",
    ):
        raise OandaHourlyError("unexpected A2 conversion mandate")
    authority = mandate.get("authority", {})
    for key in (
        "execution_credentials_allowed",
        "live_funds_allowed",
        "live_trading_authorized",
        "order_submission_allowed",
        "paper_trading_authorized",
    ):
        if authority.get(key) is not False:
            raise OandaHourlyError(f"unsafe A2 conversion authority: {key}")
    scope = mandate.get("execution_scope", {})
    if scope.get("conversion_only_oanda_instruments") != ["GBP_USD"]:
        raise OandaHourlyError("conversion-only universe changed")
    if scope.get("approved_execution_instrument_ids") != []:
        raise OandaHourlyError("conversion mandate cannot approve execution")

    contract = _load_canonical(contract_path, "A2 conversion contract")
    if (
        contract.get("schema_version"),
        contract.get("experiment_id"),
        contract.get("status"),
    ) != (CONTRACT_SCHEMA, EXPERIMENT_ID, "frozen"):
        raise OandaHourlyError("unexpected A2 conversion contract")
    if contract.get("instrument") != {
        "eligible_as_strategy_instrument": False,
        "instrument_id": "GBP_USD",
        "purpose": "point_in_time_gbp_pnl_translation_only",
    }:
        raise OandaHourlyError("GBP conversion purpose changed")
    for key, value in contract.get("prohibitions", {}).items():
        if value is not False:
            raise OandaHourlyError(f"unsafe A2 conversion permission: {key}")
    bound_mandate = _repo_file(repo_root, contract["mandate"]["path"], "conversion mandate")
    if bound_mandate != mandate_path.resolve(strict=True) or sha256_file(bound_mandate) != contract[
        "mandate"
    ]["sha256"]:
        raise OandaHourlyError("A2 conversion mandate checksum changed")
    base = _repo_file(repo_root, contract["base_hourly_contract"]["path"], "base hourly contract")
    if sha256_file(base) != contract["base_hourly_contract"]["sha256"]:
        raise OandaHourlyError("base hourly contract checksum changed")
    catalogue = _repo_file(repo_root, contract["frozen_catalogue"]["path"], "frozen catalogue")
    if sha256_file(catalogue) != contract["frozen_catalogue"]["sha256"]:
        raise OandaHourlyError("frozen catalogue checksum changed")
    names = {row.get("name") for row in json.loads(catalogue.read_bytes()).get("instruments", ())}
    if "GBP_USD" not in names:
        raise OandaHourlyError("GBP_USD absent from frozen catalogue")
    plan = contract.get("request_plan", {})
    if (
        plan.get("allowed_http_method") != "GET"
        or plan.get("maximum_requests") != 32
        or plan.get("candle_query") != {"granularity": "H1", "price": "BA", "smooth": "false"}
    ):
        raise OandaHourlyError("conversion request plan changed")
    return contract


def build_request_specs(contract: Mapping[str, Any], repo_root: Path) -> list[dict[str, Any]]:
    base = _load_canonical(
        _repo_file(repo_root, contract["base_hourly_contract"]["path"], "base hourly contract"),
        "base hourly contract",
    )
    boundaries = base["request_plan"]["chunk_boundaries"]
    query = contract["request_plan"]["candle_query"]
    specs = [
        {
            "filename": f"gbp_usd-h1-{index:02d}.json",
            "instrument_id": "GBP_USD",
            "parameters": {**query, "from": start, "to": end},
            "path_template": contract["request_plan"]["permitted_endpoint_template"],
        }
        for index, (start, end) in enumerate(zip(boundaries, boundaries[1:]), start=1)
    ]
    if len(specs) != 32:
        raise OandaHourlyError("conversion request count changed")
    return specs


def validate_source_manifest(contract: Mapping[str, Any], repo_root: Path, artifact_root: Path) -> dict[str, Any]:
    manifest = _load_canonical(artifact_root / "source-manifest.json", "conversion source manifest")
    if manifest.get("schema_version") != SOURCE_SCHEMA or manifest.get("experiment_id") != EXPERIMENT_ID:
        raise OandaHourlyError("unexpected conversion source manifest")
    if manifest.get("account_id_sha256") != contract["source_access"]["account_id_sha256"]:
        raise OandaHourlyError("conversion source account binding changed")
    _utc(manifest.get("retrieved_at"), "conversion retrieved_at")
    specs = build_request_specs(contract, repo_root)
    expected = {f"raw/{spec['filename']}": spec for spec in specs}
    sources = manifest.get("sources")
    if not isinstance(sources, list) or len(sources) != 32:
        raise OandaHourlyError("conversion source count changed")
    for source in sources:
        relative = source.get("path")
        spec = expected.get(relative)
        if spec is None:
            raise OandaHourlyError("unexpected conversion source path")
        path = artifact_root / relative
        if (
            source.get("http_method") != "GET"
            or source.get("http_status") != 200
            or source.get("parameters") != spec["parameters"]
            or source.get("instrument_id") != "GBP_USD"
            or sha256_file(path) != source.get("sha256")
            or path.stat().st_size != source.get("bytes")
        ):
            raise OandaHourlyError("conversion source lineage changed")
    return manifest


def audit_and_normalize(
    contract: Mapping[str, Any], repo_root: Path, artifact_root: Path, output_path: Path
) -> dict[str, Any]:
    manifest = validate_source_manifest(contract, repo_root, artifact_root)
    source_map = {row["path"]: row for row in manifest["sources"]}
    timestamps = []
    seen: dict[Any, str] = {}
    overlaps = 0
    with output_path.open("w", encoding="utf-8", newline="\n") as output:
        for spec in build_request_specs(contract, repo_root):
            relative = f"raw/{spec['filename']}"
            payload = json.loads((artifact_root / relative).read_bytes())
            if (
                not isinstance(payload, Mapping)
                or payload.get("instrument") != "GBP_USD"
                or payload.get("granularity") != "H1"
                or not isinstance(payload.get("candles"), list)
            ):
                raise OandaHourlyError("conversion response identity changed")
            lower = _utc(spec["parameters"]["from"], "conversion chunk start")
            upper = _utc(spec["parameters"]["to"], "conversion chunk end")
            previous = None
            for raw_row in payload["candles"]:
                observed, row = parse_candle_row(raw_row, "GBP_USD", lower, upper)
                if previous is not None and observed <= previous:
                    raise OandaHourlyError("conversion response times are not increasing")
                previous = observed
                fingerprint = canonical_json_line(raw_row)
                if observed in seen:
                    if seen[observed] != fingerprint:
                        raise OandaHourlyError("conflicting conversion duplicate")
                    overlaps += 1
                    continue
                if timestamps and observed <= timestamps[-1]:
                    raise OandaHourlyError("reversed conversion chunk boundary")
                seen[observed] = fingerprint
                timestamps.append(observed)
                row["source_sha256"] = source_map[relative]["sha256"]
                output.write(canonical_json_line(row) + "\n")
    max_gap = max(
        ((current - previous).total_seconds() / 3600 for previous, current in zip(timestamps, timestamps[1:])),
        default=0,
    )
    rules = contract["acceptance_rules"]
    failures = []
    if len(timestamps) < rules["complete_candles_minimum"]:
        failures.append("insufficient_complete_candles")
    if not timestamps or timestamps[0] > _utc(rules["first_candle_on_or_before"], "conversion first gate"):
        failures.append("history_starts_after_gate")
    if not timestamps or timestamps[-1] < _utc(rules["last_candle_on_or_after"], "conversion last gate"):
        failures.append("history_ends_before_gate")
    if max_gap > rules["maximum_internal_gap_hours"]:
        failures.append("internal_gap_exceeds_gate")
    return {
        "complete_hourly_candles": len(timestamps),
        "decision": "conversion_source_pass" if not failures else "conversion_source_reject",
        "eligible_as_strategy_instrument": False,
        "experiment_id": EXPERIMENT_ID,
        "failures": failures,
        "first_candle_at": timestamps[0].isoformat().replace("+00:00", "Z") if timestamps else None,
        "identical_overlap_count": overlaps,
        "instrument_id": "GBP_USD",
        "last_candle_at": timestamps[-1].isoformat().replace("+00:00", "Z") if timestamps else None,
        "maximum_observed_gap_hours": str(int(max_gap)),
        "qualified_for_gbp_conversion": not failures,
        "returns_or_pnl_computed": False,
        "schema_version": REPORT_SCHEMA,
        "sealed_2026_price_accessed": False,
    }
