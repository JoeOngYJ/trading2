"""Fail-closed, source-only Twelve Data A1 v3 recovery helpers."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping, Sequence

from trading_platform.cross_asset_calendar_v2 import load_calendar
from trading_platform.cross_asset_twelvedata_audit import audit_time_series, canonical_json, load_contract as load_pilot_contract, parse_response, sha256_file
from trading_platform.cross_asset_twelvedata_history import ETF_SYMBOLS, SYMBOLS, TwelveDataHistoryError


SCHEMA = "cross-asset-a1-twelvedata-recovery-contract-v1"
EXPERIMENT_ID = "cross-asset-a1-twelvedata-recovery-v3"
MANIFEST_SCHEMA = "cross-asset-a1-twelvedata-recovery-source-manifest-v1"
EVIDENCE_SCHEMA = "cross-asset-a1-twelvedata-recovery-evidence-manifest-v1"


@dataclass(frozen=True, slots=True)
class RecoveryRequestSpec:
    endpoint: str
    filename: str
    parameters: Mapping[str, str]
    path: str
    phase: int
    symbol: str
    weight: int
    window_id: str


def _read_canonical(path: Path, label: str) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
        value = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TwelveDataHistoryError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict) or raw != canonical_json(value):
        raise TwelveDataHistoryError(f"{label} must be a canonical JSON object")
    return value


def _repo_file(root: Path, raw: Any, label: str) -> Path:
    if not isinstance(raw, str) or not raw or Path(raw).is_absolute():
        raise TwelveDataHistoryError(f"{label} must be repository-relative")
    boundary = root.resolve(strict=True)
    try:
        result = (boundary / raw).resolve(strict=True)
        result.relative_to(boundary)
    except (OSError, ValueError) as exc:
        raise TwelveDataHistoryError(f"invalid {label}") from exc
    if not result.is_file():
        raise TwelveDataHistoryError(f"missing {label}")
    return result


def load_contract(path: Path, repo_root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    contract = _read_canonical(path, "v3 recovery contract")
    if contract.get("schema_version") != SCHEMA or contract.get("experiment_id") != EXPERIMENT_ID or contract.get("status") != "frozen":
        raise TwelveDataHistoryError("unexpected or unfrozen v3 recovery contract")
    if tuple(contract.get("instruments", ())) != SYMBOLS:
        raise TwelveDataHistoryError("v3 recovery universe changed")
    base = contract.get("base_contract", {})
    base_path = _repo_file(repo_root, base.get("path"), "v2 base contract")
    if sha256_file(base_path) != base.get("sha256"):
        raise TwelveDataHistoryError("v2 base contract checksum changed")
    evidence = contract.get("frozen_v2_evidence", {})
    evidence_path = _repo_file(repo_root, evidence.get("path"), "v2 evidence")
    if sha256_file(evidence_path) != evidence.get("sha256"):
        raise TwelveDataHistoryError("v2 evidence checksum changed")
    calendar_record = contract.get("boundaries", {}).get("calendar", {})
    calendar_path = _repo_file(repo_root, calendar_record.get("path"), "corrected calendar")
    if sha256_file(calendar_path) != calendar_record.get("sha256"):
        raise TwelveDataHistoryError("corrected calendar checksum changed")
    calendar = load_calendar(calendar_path)
    inherited = contract.get("inherited_splits", {})
    inherited_path = _repo_file(repo_root, inherited.get("source_manifest_path"), "v2 source manifest")
    if sha256_file(inherited_path) != inherited.get("source_manifest_sha256"):
        raise TwelveDataHistoryError("inherited split manifest checksum changed")
    for key, value in contract.get("prohibitions", {}).items():
        if value is not False:
            raise TwelveDataHistoryError(f"unsafe v3 permission: {key}")
    plan = contract.get("request_plan", {})
    if (plan.get("maximum_requests"), plan.get("maximum_weighted_credits"), plan.get("minute_credit_ceiling"), plan.get("phase_count")) != (51, 507, 55, 13):
        raise TwelveDataHistoryError("v3 request budget changed")
    if contract.get("decision_rule", {}).get("a1_stage_passed_by_recovery") is not False:
        raise TwelveDataHistoryError("v3 cannot pass A1")
    if contract.get("retention_and_revision_policy", {}).get("archival_use_after_subscription_termination") != "ineligible_pending_explicit_provider_permission":
        raise TwelveDataHistoryError("archival uncertainty must remain fail-closed")
    base_contract = _read_canonical(repo_root / "config/experiments/cross-asset-a1-twelvedata-full-history-v1.json", "v1 history contract")
    pilot_record = base_contract["source_qualification_lineage"]["accepted_pilot_contract"]
    pilot_path = _repo_file(repo_root, pilot_record["path"], "accepted pilot")
    if sha256_file(pilot_path) != pilot_record["sha256"]:
        raise TwelveDataHistoryError("accepted pilot checksum changed")
    pilot = load_pilot_contract(pilot_path, repo_root)
    return contract, pilot, calendar


def build_request_specs(contract: Mapping[str, Any]) -> tuple[RecoveryRequestSpec, ...]:
    plan = contract["request_plan"]
    specs: list[RecoveryRequestSpec] = []
    for symbol in SYMBOLS:
        slug = symbol.casefold().replace("/", "-")
        for window in contract["time_series_windows"]:
            window_id = str(window["window_id"])
            specs.append(RecoveryRequestSpec("time_series", f"{slug}-time-series-{window_id}.json", {**plan["time_series_query"], "end_date": str(window["end_date"]), "start_date": str(window["start_date"]), "symbol": symbol}, "/time_series", 1, symbol, 1, window_id))
    dividend_specs: list[RecoveryRequestSpec] = []
    for symbol in ETF_SYMBOLS:
        for window in contract["dividend_windows"]:
            window_id = str(window["window_id"])
            dividend_specs.append(RecoveryRequestSpec("dividends", f"{symbol.casefold()}-dividends-{window_id}.json", {**plan["dividend_query"], "end_date": str(window["end_date"]), "start_date": str(window["start_date"]), "symbol": symbol}, "/dividends", 0, symbol, 20, window_id))
    for index, item in enumerate(dividend_specs):
        specs.append(RecoveryRequestSpec(item.endpoint, item.filename, item.parameters, item.path, 2 + index // 2, item.symbol, item.weight, item.window_id))
    if len(specs) != 51 or sum(item.weight for item in specs) != 507:
        raise TwelveDataHistoryError("v3 request construction differs from contract")
    phase_weights = {phase: sum(item.weight for item in specs if item.phase == phase) for phase in range(1, 14)}
    if phase_weights != {1: 27, **{phase: 40 for phase in range(2, 14)}}:
        raise TwelveDataHistoryError("v3 quota phases changed")
    if any("apikey" in key.casefold() for item in specs for key in item.parameters):
        raise TwelveDataHistoryError("v3 request attempts to serialize token")
    return tuple(specs)


def phase_offsets(contract: Mapping[str, Any]) -> dict[int, int]:
    spacing = int(contract["request_plan"]["phase_spacing_seconds"])
    result = {phase: (phase - 1) * spacing for phase in range(1, 14)}
    if spacing != 61 or result[13] != 732:
        raise TwelveDataHistoryError("v3 phase spacing changed")
    return result


def validate_source_manifest(repo_root: Path, manifest_path: Path, contract_path: Path, contract: Mapping[str, Any]) -> tuple[dict[tuple[str, str, str], Path], dict[str, Any]]:
    manifest = _read_canonical(manifest_path, "v3 source manifest")
    if manifest.get("schema_version") != MANIFEST_SCHEMA or manifest.get("experiment_id") != EXPERIMENT_ID or manifest.get("contract_sha256") != sha256_file(contract_path):
        raise TwelveDataHistoryError("v3 source manifest lineage mismatch")
    specs = build_request_specs(contract)
    records = manifest.get("responses")
    if not isinstance(records, list) or len(records) != len(specs):
        raise TwelveDataHistoryError("v3 response count mismatch")
    expected = {(x.symbol, x.endpoint, x.window_id): x for x in specs}
    indexed: dict[tuple[str, str, str], Path] = {}
    for record in records:
        key = (str(record.get("symbol")), str(record.get("endpoint")), str(record.get("window_id")))
        if key not in expected or key in indexed:
            raise TwelveDataHistoryError("unexpected or duplicate v3 response")
        spec = expected[key]
        if record.get("parameters") != dict(spec.parameters) or record.get("phase") != spec.phase or record.get("weight") != spec.weight:
            raise TwelveDataHistoryError("v3 request lineage mismatch")
        raw_path = _repo_file(repo_root, record.get("path"), "v3 raw response")
        if raw_path.name != spec.filename or record.get("sha256") != sha256_file(raw_path) or record.get("bytes") != raw_path.stat().st_size:
            raise TwelveDataHistoryError("v3 raw response checksum mismatch")
        indexed[key] = raw_path
    return indexed, manifest


def _decimal(raw: Any, label: str, positive: bool = False) -> Decimal:
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, ValueError) as exc:
        raise TwelveDataHistoryError(f"invalid {label}") from exc
    if not value.is_finite() or (positive and value <= 0):
        raise TwelveDataHistoryError(f"invalid {label}")
    return value


def _lineage_digest(paths: Sequence[Path]) -> str:
    values = [sha256_file(path) for path in paths]
    return hashlib.sha256(("\n".join(values) + "\n").encode()).hexdigest()


def _audit_action_identity(meta: Any, instrument: Mapping[str, Any]) -> None:
    if not isinstance(meta, Mapping) or meta.get("symbol") != instrument["symbol"] or meta.get("currency") != instrument["expected_currency"] or meta.get("mic_code") != instrument["expected_mic_code"]:
        raise TwelveDataHistoryError("corporate-action identity mismatch")


def _available_at(session: str) -> str:
    day = date.fromisoformat(session)
    return datetime.combine(day + timedelta(days=1), time(5), tzinfo=timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def merge_price_windows(paths: Sequence[Path], instrument: Mapping[str, Any], expected_sessions: Sequence[str], *, fx: bool, maximum_missing_fraction: Decimal = Decimal("0.005"), maximum_gap: int = 3, eligible_start: str = "2008-01-02") -> tuple[dict[str, Any], tuple[str, ...]]:
    merged: dict[str, Mapping[str, Any]] = {}
    for path in paths:
        payload = parse_response(path.read_bytes(), f"{instrument['symbol']} bounded time series")
        rows = payload.get("values")
        if not isinstance(rows, list) or not rows:
            raise TwelveDataHistoryError("bounded time-series window is empty")
        dates = [str(row.get("datetime")) for row in rows]
        unique = sorted(set(dates))
        audit_time_series(payload, instrument, unique)
        for row in rows:
            key = str(row["datetime"])
            if key in merged and dict(merged[key]) != dict(row):
                raise TwelveDataHistoryError(f"conflicting overlap on {key}")
            merged[key] = row
    boundary_rows = {key: value for key, value in merged.items() if "2008-01-02" <= key <= "2025-12-31"}
    expected = list(expected_sessions)
    expected_set = set(expected)
    actual_set = set(boundary_rows)
    missing = [value for value in expected if value not in actual_set]
    quarantined = sorted(actual_set - expected_set)
    if not fx and missing:
        raise TwelveDataHistoryError(f"missing {len(missing)} exchange sessions")
    if fx:
        if Decimal(len(missing)) / Decimal(len(expected)) > maximum_missing_fraction:
            raise TwelveDataHistoryError("FX missing-session fraction exceeds frozen maximum")
        longest = current = 0
        for value in expected:
            current = current + 1 if value in set(missing) else 0
            longest = max(longest, current)
        if longest > maximum_gap:
            raise TwelveDataHistoryError("FX consecutive gap exceeds frozen maximum")
    eligible_dates = [value for value in expected if value in boundary_rows and value >= eligible_start]
    lineage = _lineage_digest(paths)
    lines: list[str] = []
    for session in eligible_dates:
        row = boundary_rows[session]
        record = {
            "available_at": _available_at(session),
            "close": format(_decimal(row.get("close"), "close", True).normalize(), "f"),
            "high": format(_decimal(row.get("high"), "high", True).normalize(), "f"),
            "instrument_id": instrument["instrument_id"],
            "interval": "1day",
            "low": format(_decimal(row.get("low"), "low", True).normalize(), "f"),
            "observed_at": f"{session}T00:00:00Z",
            "open": format(_decimal(row.get("open"), "open", True).normalize(), "f"),
            "session": session,
            "source_lineage_sha256": lineage,
            "symbol": instrument["symbol"],
            "volume": None if fx and row.get("volume") in (None, "") else format(_decimal(row.get("volume"), "volume").normalize(), "f"),
        }
        lines.append(json.dumps(record, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")))
    return {"eligible_start": eligible_start, "missing_sessions": missing, "normalized_rows": len(lines), "quarantined_dates": quarantined, "source_lineage_sha256": lineage}, tuple(lines)


def merge_dividend_windows(paths: Sequence[Path], instrument: Mapping[str, Any], record_limit: int, minimum: int | None) -> tuple[dict[str, Any], tuple[str, ...]]:
    merged: dict[str, Mapping[str, Any]] = {}
    for path in paths:
        payload = parse_response(path.read_bytes(), f"{instrument['symbol']} bounded dividends")
        _audit_action_identity(payload.get("meta"), instrument)
        rows = payload.get("dividends")
        if not isinstance(rows, list) or len(rows) >= record_limit:
            raise TwelveDataHistoryError("bounded dividend response is empty/invalid or reaches frozen cap")
        local: set[str] = set()
        for row in rows:
            day = str(row.get("ex_date"))
            date.fromisoformat(day)
            _decimal(row.get("amount"), "dividend amount", True)
            if day in local:
                raise TwelveDataHistoryError("duplicate dividend date within window")
            local.add(day)
            if day in merged and dict(merged[day]) != dict(row):
                raise TwelveDataHistoryError(f"conflicting dividend overlap on {day}")
            merged[day] = row
    rows = [merged[key] for key in sorted(merged) if "2008-01-02" <= key <= "2025-12-31"]
    if minimum is not None and len(rows) < minimum:
        raise TwelveDataHistoryError(f"dividend count {len(rows)} below frozen minimum {minimum}")
    lineage = _lineage_digest(paths)
    lines = tuple(json.dumps({"action_date": str(row["ex_date"]), "action_type": "cash_distribution", "amount_per_share": format(_decimal(row["amount"], "amount", True).normalize(), "f"), "available_at": _available_at(str(row["ex_date"])), "currency": instrument["expected_currency"], "instrument_id": instrument["instrument_id"], "source_lineage_sha256": lineage, "symbol": instrument["symbol"]}, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")) for row in rows)
    return {"normalized_rows": len(lines), "source_lineage_sha256": lineage}, lines


def inherited_split_lines(repo_root: Path, contract: Mapping[str, Any], instrument: Mapping[str, Any]) -> tuple[dict[str, Any], tuple[str, ...]]:
    manifest_path = _repo_file(repo_root, contract["inherited_splits"]["source_manifest_path"], "v2 split manifest")
    manifest = _read_canonical(manifest_path, "v2 split manifest")
    record = next((item for item in manifest["responses"] if item["symbol"] == instrument["symbol"] and item["endpoint"] == "splits"), None)
    if record is None:
        raise TwelveDataHistoryError("inherited split response missing")
    raw_path = _repo_file(repo_root, record["path"], "inherited split response")
    if sha256_file(raw_path) != record["sha256"]:
        raise TwelveDataHistoryError("inherited split checksum changed")
    payload = parse_response(raw_path.read_bytes(), f"{instrument['symbol']} inherited splits")
    _audit_action_identity(payload.get("meta"), instrument)
    tolerance = Decimal(contract["inherited_splits"]["semantics"]["ratio_absolute_tolerance"])
    lines: list[str] = []
    for row in payload.get("splits", []):
        day = str(row.get("date")); date.fromisoformat(day)
        ratio = _decimal(row.get("ratio"), "split ratio", True)
        from_factor = _decimal(row.get("from_factor"), "from factor", True)
        to_factor = _decimal(row.get("to_factor"), "to factor", True)
        if abs(ratio - to_factor / from_factor) > tolerance:
            raise TwelveDataHistoryError("split price factor conflicts with provider factors")
        lines.append(json.dumps({"action_date": day, "action_type": "split", "available_at": _available_at(day), "description": str(row.get("description", "")), "from_factor": format(from_factor.normalize(), "f"), "instrument_id": instrument["instrument_id"], "price_multiplier": format(ratio.normalize(), "f"), "source_sha256": sha256_file(raw_path), "symbol": instrument["symbol"], "to_factor": format(to_factor.normalize(), "f"), "unit_multiplier": format((from_factor / to_factor).normalize(), "f")}, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")))
    return {"normalized_rows": len(lines), "source_sha256": sha256_file(raw_path)}, tuple(lines)
