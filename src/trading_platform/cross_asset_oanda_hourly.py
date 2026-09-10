"""Offline validation and normalization for the frozen OANDA A1 hourly history.

Network access is deliberately excluded from this module.  The bounded downloader is the
only component allowed to perform provider GET requests.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Mapping, TextIO
from zoneinfo import ZoneInfo


CONTRACT_SCHEMA = "cross-asset-a1-oanda-hourly-history-contract-v1"
EXPERIMENT_ID = "cross-asset-a1-oanda-hourly-history-v1"
MANDATE_SCHEMA = "cross-asset-research-mandate-v6"
MANDATE_ID = "retail-cross-asset-research-v6"
SOURCE_SCHEMA = "cross-asset-a1-oanda-hourly-source-manifest-v1"
REPORT_SCHEMA = "cross-asset-a1-oanda-hourly-audit-v1"
EVIDENCE_SCHEMA = "cross-asset-a1-oanda-hourly-evidence-v1"
INSTRUMENT_IDS = (
    "SPX500_USD",
    "NAS100_USD",
    "DE30_EUR",
    "UK100_GBP",
    "XAU_USD",
    "EUR_USD",
    "USD_JPY",
)


class OandaHourlyError(ValueError):
    """Raised when frozen hourly source evidence fails closed."""


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
        value = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OandaHourlyError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict) or raw != canonical_json(value):
        raise OandaHourlyError(f"{label} must be a canonical JSON object")
    return value


def _utc(raw: Any, label: str) -> datetime:
    if not isinstance(raw, str) or not raw.endswith("Z"):
        raise OandaHourlyError(f"{label} must be an explicit UTC Z timestamp")
    try:
        value = datetime.fromisoformat(raw[:-1] + "+00:00")
    except ValueError as exc:
        raise OandaHourlyError(f"invalid {label}") from exc
    if value.utcoffset() != timedelta(0):
        raise OandaHourlyError(f"{label} must be UTC")
    return value


def _repo_file(root: Path, raw: Any, label: str) -> Path:
    if not isinstance(raw, str) or not raw or Path(raw).is_absolute():
        raise OandaHourlyError(f"{label} must be repository-relative")
    boundary = root.resolve(strict=True)
    try:
        candidate = (boundary / raw).resolve(strict=True)
        candidate.relative_to(boundary)
    except (OSError, ValueError) as exc:
        raise OandaHourlyError(f"invalid {label}") from exc
    if not candidate.is_file():
        raise OandaHourlyError(f"{label} is not a regular file")
    return candidate


def load_contract(contract_path: Path, mandate_path: Path, repo_root: Path) -> dict[str, Any]:
    mandate = _load_canonical(mandate_path, "hourly OANDA mandate")
    if (mandate.get("schema_version"), mandate.get("mandate_id"), mandate.get("status")) != (
        MANDATE_SCHEMA,
        MANDATE_ID,
        "frozen_a1_oanda_hourly_read_only_data_qualification_only",
    ):
        raise OandaHourlyError("unexpected or unfrozen hourly OANDA mandate")
    authority = mandate.get("authority", {})
    for key in (
        "execution_credentials_allowed",
        "live_funds_allowed",
        "live_trading_authorized",
        "order_submission_allowed",
        "paper_trading_authorized",
    ):
        if authority.get(key) is not False:
            raise OandaHourlyError(f"unsafe hourly mandate authority: {key}")
    if authority.get("maximum_live_allocation_gbp") != 0:
        raise OandaHourlyError("hourly mandate live allocation must be zero")
    token = mandate.get("data_provider_token_policy", {})
    if token.get("allowed_http_method") != "GET" or token.get("allowed_resource_classes") != [
        "historical_instrument_candles"
    ]:
        raise OandaHourlyError("hourly mandate may access historical candles by GET only")
    for key in (
        "broker_private_state_access_allowed",
        "database_or_message_bus_tokens_allowed",
        "may_be_logged_or_serialized",
        "order_or_order_preview_access_allowed",
        "repository_storage_allowed",
        "runtime_order_or_signal_access_allowed",
    ):
        if token.get(key) is not False:
            raise OandaHourlyError(f"unsafe hourly token policy: {key}")
    scope = mandate.get("execution_scope", {})
    if tuple(scope.get("candidate_oanda_instruments", ())) != INSTRUMENT_IDS:
        raise OandaHourlyError("hourly mandate candidate universe changed")
    if scope.get("approved_execution_instrument_ids") != []:
        raise OandaHourlyError("hourly mandate cannot approve execution instruments")
    if scope.get("oanda_execution_authorized") is not False:
        raise OandaHourlyError("hourly mandate cannot authorize OANDA execution")

    contract = _load_canonical(contract_path, "hourly OANDA contract")
    if (contract.get("schema_version"), contract.get("experiment_id"), contract.get("status")) != (
        CONTRACT_SCHEMA,
        EXPERIMENT_ID,
        "frozen",
    ):
        raise OandaHourlyError("unexpected or unfrozen hourly OANDA contract")
    _utc(contract.get("frozen_at"), "contract frozen_at")
    mandate_record = contract.get("mandate", {})
    bound_mandate = _repo_file(repo_root, mandate_record.get("path"), "bound mandate")
    if bound_mandate != mandate_path.resolve(strict=True) or sha256_file(bound_mandate) != mandate_record.get(
        "sha256"
    ):
        raise OandaHourlyError("hourly mandate checksum changed")
    catalogue = contract.get("frozen_catalogue", {})
    catalogue_path = _repo_file(repo_root, catalogue.get("path"), "frozen catalogue")
    if sha256_file(catalogue_path) != catalogue.get("sha256"):
        raise OandaHourlyError("frozen catalogue checksum changed")
    names = {
        item.get("name")
        for item in json.loads(catalogue_path.read_bytes()).get("instruments", ())
        if isinstance(item, Mapping)
    }
    if not set(INSTRUMENT_IDS).issubset(names):
        raise OandaHourlyError("frozen catalogue omits an hourly candidate")
    candidates = contract.get("candidate_instruments")
    if not isinstance(candidates, list) or tuple(x.get("instrument_id") for x in candidates) != INSTRUMENT_IDS:
        raise OandaHourlyError("hourly contract universe changed")
    boundary = contract.get("evidence_boundary", {})
    if boundary != {
        "end_exclusive": "2026-01-01T00:00:00Z",
        "sealed_2026_price_access_allowed": False,
        "start_inclusive": "2010-01-01T00:00:00Z",
    }:
        raise OandaHourlyError("hourly evidence boundary changed")
    plan = contract.get("request_plan", {})
    boundaries = plan.get("chunk_boundaries")
    if (
        plan.get("allowed_http_method") != "GET"
        or plan.get("maximum_requests") != 224
        or plan.get("permitted_endpoint_template") != "/v3/instruments/{instrument}/candles"
        or plan.get("candle_query") != {"granularity": "H1", "price": "BA", "smooth": "false"}
        or not isinstance(boundaries, list)
        or len(boundaries) != 33
        or boundaries[0] != boundary["start_inclusive"]
        or boundaries[-1] != boundary["end_exclusive"]
    ):
        raise OandaHourlyError("hourly request plan changed")
    parsed_boundaries = [_utc(value, "chunk boundary") for value in boundaries]
    if any(b <= a for a, b in zip(parsed_boundaries, parsed_boundaries[1:])):
        raise OandaHourlyError("hourly chunk boundaries are not increasing")
    if len(build_request_specs(contract)) != 224:
        raise OandaHourlyError("hourly request count changed")
    rules = contract.get("acceptance_rules", {})
    if rules.get("strategy_evaluation_authorized_by_this_experiment") is not False:
        raise OandaHourlyError("hourly source qualification cannot authorize a strategy")
    if rules.get("missing_required_window_bar_disposition") != "no_trade":
        raise OandaHourlyError("missing hourly inputs must fail closed to no_trade")
    for key, value in contract.get("prohibitions", {}).items():
        if value is not False:
            raise OandaHourlyError(f"unsafe hourly permission: {key}")
    return contract


@dataclass(frozen=True, slots=True)
class HourlyRequestSpec:
    filename: str
    instrument_id: str
    parameters: Mapping[str, str]
    path_template: str


def build_request_specs(contract: Mapping[str, Any]) -> tuple[HourlyRequestSpec, ...]:
    plan = contract["request_plan"]
    query = plan["candle_query"]
    boundaries = plan["chunk_boundaries"]
    result = []
    for candidate in contract["candidate_instruments"]:
        instrument = candidate["instrument_id"]
        for index, (start, end) in enumerate(zip(boundaries, boundaries[1:]), start=1):
            result.append(
                HourlyRequestSpec(
                    filename=f"{instrument.casefold()}-h1-{index:02d}.json",
                    instrument_id=instrument,
                    parameters={**query, "from": start, "to": end},
                    path_template=plan["permitted_endpoint_template"],
                )
            )
    return tuple(result)


def validate_runtime_identity(contract: Mapping[str, Any], api_url: str, account_id: str) -> None:
    if api_url != contract["source_access"]["api_base_url"]:
        raise OandaHourlyError("configured OANDA host differs from frozen host")
    if not account_id or sha256_bytes(account_id.encode()) != contract["source_access"]["account_id_sha256"]:
        raise OandaHourlyError("configured OANDA account differs from frozen digest")


def _decimal(raw: Any, label: str) -> Decimal:
    if raw is None or isinstance(raw, bool):
        raise OandaHourlyError(f"missing price field: {label}")
    try:
        value = Decimal(str(raw))
    except InvalidOperation as exc:
        raise OandaHourlyError(f"invalid price field: {label}") from exc
    if not value.is_finite() or value <= 0:
        raise OandaHourlyError(f"non-positive price field: {label}")
    return value


def parse_candle_row(row: Any, instrument: str, lower: datetime, upper: datetime) -> tuple[datetime, dict[str, Any]]:
    if not isinstance(row, Mapping) or row.get("complete") is not True:
        raise OandaHourlyError(f"incomplete hourly candle for {instrument}")
    observed = _utc(row.get("time"), "hourly candle time")
    if observed < lower or observed >= upper or observed.minute or observed.second or observed.microsecond:
        raise OandaHourlyError(f"hourly candle outside frozen chunk for {instrument}")
    normalized: dict[str, Any] = {
        "available_at": (observed + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
        "instrument_id": instrument,
        "observed_at": observed.isoformat().replace("+00:00", "Z"),
        "volume": row.get("volume"),
    }
    if isinstance(row.get("volume"), bool) or not isinstance(row.get("volume"), int) or row["volume"] < 0:
        raise OandaHourlyError(f"invalid hourly volume for {instrument}")
    sides: dict[str, dict[str, Decimal]] = {}
    for side in ("bid", "ask"):
        values = row.get(side)
        if not isinstance(values, Mapping):
            raise OandaHourlyError(f"missing {side} hourly candle for {instrument}")
        parsed = {field: _decimal(values.get(field), f"{side}.{field}") for field in "ohlc"}
        if parsed["l"] > min(parsed["o"], parsed["c"]) or parsed["h"] < max(
            parsed["o"], parsed["c"]
        ) or parsed["l"] > parsed["h"]:
            raise OandaHourlyError(f"invalid {side} OHLC for {instrument}")
        sides[side] = parsed
        normalized[side] = {field: str(parsed[field]) for field in "ohlc"}
    if any(sides["ask"][field] < sides["bid"][field] for field in "ohlc"):
        raise OandaHourlyError(f"crossed bid/ask hourly candle for {instrument}")
    return observed, normalized


def validate_source_manifest(contract: Mapping[str, Any], artifact_root: Path) -> dict[str, Any]:
    manifest = _load_canonical(artifact_root / "source-manifest.json", "hourly source manifest")
    if manifest.get("schema_version") != SOURCE_SCHEMA or manifest.get("experiment_id") != EXPERIMENT_ID:
        raise OandaHourlyError("unexpected hourly source manifest")
    if manifest.get("account_id_sha256") != contract["source_access"]["account_id_sha256"]:
        raise OandaHourlyError("hourly source account binding changed")
    if manifest.get("api_base_url") != contract["source_access"]["api_base_url"]:
        raise OandaHourlyError("hourly source host changed")
    _utc(manifest.get("retrieved_at"), "source retrieved_at")
    expected = {f"raw/{spec.filename}": spec for spec in build_request_specs(contract)}
    sources = manifest.get("sources")
    if not isinstance(sources, list) or len(sources) != len(expected):
        raise OandaHourlyError("hourly source manifest request count changed")
    seen: set[str] = set()
    for source in sources:
        if not isinstance(source, Mapping):
            raise OandaHourlyError("invalid hourly source record")
        relative = source.get("path")
        spec = expected.get(relative)
        if spec is None or relative in seen:
            raise OandaHourlyError("unexpected or duplicate hourly source path")
        seen.add(relative)
        if (
            source.get("http_method") != "GET"
            or source.get("http_status") != 200
            or source.get("endpoint_template") != spec.path_template
            or source.get("instrument_id") != spec.instrument_id
            or source.get("parameters") != dict(spec.parameters)
        ):
            raise OandaHourlyError("hourly source request lineage changed")
        if any(key.casefold() in {"authorization", "token", "accountid"} for key in source.get("parameters", {})):
            raise OandaHourlyError("credential material appears in hourly source parameters")
        try:
            path = (artifact_root / str(relative)).resolve(strict=True)
            path.relative_to(artifact_root.resolve(strict=True))
        except (OSError, ValueError) as exc:
            raise OandaHourlyError("hourly source path escapes artifact root") from exc
        if sha256_file(path) != source.get("sha256") or path.stat().st_size != source.get("bytes"):
            raise OandaHourlyError(f"hourly source checksum mismatch: {relative}")
    return manifest


def _session_result(
    timestamps: Iterable[datetime], candidate: Mapping[str, Any], contract: Mapping[str, Any]
) -> dict[str, Any]:
    profile = contract["session_profiles"][candidate["session_profile"]]
    zone = ZoneInfo(profile["timezone"])
    required_hours = set(profile["local_candle_start_hours"])
    daily: dict[date, set[int]] = defaultdict(set)
    for observed in timestamps:
        local = observed.astimezone(zone)
        if local.hour in required_hours:
            daily[local.date()].add(local.hour)
    observed_days = len(daily)
    complete_days = sum(hours == required_hours for hours in daily.values())
    incomplete_days = observed_days - complete_days
    fraction = Decimal(incomplete_days) / Decimal(observed_days) if observed_days else Decimal(1)
    return {
        "complete_session_days": complete_days,
        "incomplete_observed_session_days": incomplete_days,
        "incomplete_observed_session_fraction": format(fraction.quantize(Decimal("0.00000001")), "f"),
        "observed_session_days": observed_days,
        "session_profile": candidate["session_profile"],
    }


def audit_and_normalize(
    contract: Mapping[str, Any], artifact_root: Path, normalized_root: Path
) -> dict[str, Any]:
    manifest = validate_source_manifest(contract, artifact_root)
    manifest_by_path = {source["path"]: source for source in manifest["sources"]}
    specs = build_request_specs(contract)
    normalized_root.mkdir(parents=True, exist_ok=False)
    results = []
    normalized_files = []
    for candidate in contract["candidate_instruments"]:
        instrument = candidate["instrument_id"]
        instrument_specs = [spec for spec in specs if spec.instrument_id == instrument]
        seen: dict[datetime, str] = {}
        ordered: list[datetime] = []
        overlap_count = 0
        output_path = normalized_root / f"{instrument.casefold()}-h1.jsonl"
        with output_path.open("w", encoding="utf-8", newline="\n") as output:
            for spec in instrument_specs:
                source_path = f"raw/{spec.filename}"
                raw = (artifact_root / source_path).read_bytes()
                try:
                    payload = json.loads(raw)
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise OandaHourlyError(f"invalid JSON response: {spec.filename}") from exc
                if not isinstance(payload, Mapping) or payload.get("instrument") != instrument or payload.get(
                    "granularity"
                ) != "H1" or not isinstance(payload.get("candles"), list):
                    raise OandaHourlyError(f"hourly response identity mismatch: {spec.filename}")
                lower = _utc(spec.parameters["from"], "chunk start")
                upper = _utc(spec.parameters["to"], "chunk end")
                previous: datetime | None = None
                for row in payload["candles"]:
                    observed, normalized = parse_candle_row(row, instrument, lower, upper)
                    if previous is not None and observed <= previous:
                        raise OandaHourlyError(f"non-increasing hourly response: {spec.filename}")
                    previous = observed
                    fingerprint = canonical_json_line(row)
                    if observed in seen:
                        if seen[observed] != fingerprint:
                            raise OandaHourlyError(f"conflicting duplicate hourly candle for {instrument}")
                        overlap_count += 1
                        continue
                    if ordered and observed <= ordered[-1]:
                        raise OandaHourlyError(f"reversed hourly chunk boundary for {instrument}")
                    seen[observed] = fingerprint
                    ordered.append(observed)
                    normalized["source_sha256"] = manifest_by_path[source_path]["sha256"]
                    output.write(canonical_json_line(normalized) + "\n")
        gaps = []
        max_gap = Decimal(0)
        for previous, current in zip(ordered, ordered[1:]):
            hours = Decimal(str((current - previous).total_seconds() / 3600))
            max_gap = max(max_gap, hours)
            if hours > Decimal(contract["acceptance_rules"]["maximum_internal_gap_hours"]):
                gaps.append(
                    {
                        "from": previous.isoformat().replace("+00:00", "Z"),
                        "hours": format(hours.normalize(), "f"),
                        "to": current.isoformat().replace("+00:00", "Z"),
                    }
                )
        session = _session_result(ordered, candidate, contract)
        rules = contract["acceptance_rules"]
        failures = []
        first = ordered[0] if ordered else None
        last = ordered[-1] if ordered else None
        if first is None or first > _utc(rules["history_first_candle_on_or_before"], "first gate"):
            failures.append("history_starts_after_frozen_gate")
        if last is None or last < _utc(rules["history_last_candle_on_or_after"], "last gate"):
            failures.append("history_ends_before_frozen_gate")
        if session["complete_session_days"] < rules["complete_session_day_minimum"]:
            failures.append("insufficient_complete_session_days")
        if Decimal(session["incomplete_observed_session_fraction"]) > Decimal(
            rules["incomplete_observed_session_fraction_maximum"]
        ):
            failures.append("incomplete_observed_session_fraction_exceeds_gate")
        if gaps:
            failures.append("internal_gap_exceeds_frozen_gate")
        result = {
            **session,
            "candidate_role": candidate["required_role"],
            "decision": "candidate_pass" if not failures else "candidate_reject",
            "failures": failures,
            "first_candle_at": None if first is None else first.isoformat().replace("+00:00", "Z"),
            "hourly_candles": len(ordered),
            "identical_overlap_count": overlap_count,
            "instrument_id": instrument,
            "last_candle_at": None if last is None else last.isoformat().replace("+00:00", "Z"),
            "maximum_observed_gap_hours": format(max_gap.normalize(), "f"),
            "outage_gaps": gaps,
        }
        results.append(result)
        normalized_files.append(
            {
                "bytes": output_path.stat().st_size,
                "path": str(output_path.relative_to(artifact_root)),
                "sha256": sha256_file(output_path),
            }
        )
    passed = [item for item in results if item["decision"] == "candidate_pass"]
    roles = {item["candidate_role"] for item in passed}
    required_roles = set(contract["acceptance_rules"]["minimum_core_roles"])
    a1_passed = len(passed) >= contract["acceptance_rules"]["a1_pass_requires_at_least_candidate_count"] and required_roles.issubset(roles)
    return {
        "a1_stage_passed": a1_passed,
        "accepted_strategy_arms": [],
        "actionable_arm_id": "no_trade",
        "approved_execution_instruments": [],
        "decision": "a1_hourly_source_qualification_passed" if a1_passed else "a1_hourly_source_qualification_rejected",
        "experiment_id": EXPERIMENT_ID,
        "instrument_results": results,
        "normalized_files": normalized_files,
        "passed_candidate_count": len(passed),
        "qualified_for_strategy_evaluation": a1_passed,
        "returns_or_pnl_computed": False,
        "schema_version": REPORT_SCHEMA,
        "sealed_2026_price_accessed": False,
    }
