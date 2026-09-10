"""Offline audit and normalization for the frozen exact XLON history acquisition."""

from __future__ import annotations

import json
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping, Sequence

from trading_platform.cross_asset_a1_expansion import (
    A1ExpansionError,
    build_lse_request_specs,
    canonical_json,
    canonical_json_line,
    sha256_file,
)
from trading_platform.cross_asset_xlon_calendar import ExchangeSession


class LseHistoryError(ValueError):
    """Raised when exact XLON history fails its frozen source gates."""


def _decimal(raw: Any, label: str, *, positive: bool = False) -> Decimal:
    if raw is None or isinstance(raw, bool):
        raise LseHistoryError(f"missing numeric field: {label}")
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, ValueError) as exc:
        raise LseHistoryError(f"invalid numeric field: {label}") from exc
    if not value.is_finite() or positive and value <= 0 or not positive and value < 0:
        raise LseHistoryError(f"invalid numeric field: {label}")
    return value


def _text_decimal(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _next_available(session: str) -> str:
    day = datetime.fromisoformat(session).date() + timedelta(days=1)
    return datetime.combine(day, time(5), tzinfo=timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _meta(payload: Mapping[str, Any], instrument: Mapping[str, Any]) -> None:
    meta = payload.get("meta")
    if not isinstance(meta, dict):
        raise LseHistoryError(f"{instrument['symbol']} response lacks metadata")
    expected = {
        "currency": instrument["quote_unit"],
        "exchange": "LSE",
        "mic_code": "XLON",
        "symbol": instrument["symbol"],
    }
    if any(meta.get(key) != value for key, value in expected.items()):
        raise LseHistoryError(f"{instrument['symbol']} exact identity or quote unit changed")


def normalize_prices(
    payload: Mapping[str, Any],
    instrument: Mapping[str, Any],
    expected_sessions: Sequence[ExchangeSession],
    source_digest: str,
) -> tuple[str, ...]:
    _meta(payload, instrument)
    values = payload.get("values")
    if not isinstance(values, list):
        raise LseHistoryError(f"{instrument['symbol']} response lacks values")
    expected = {item.session_date: item for item in expected_sessions}
    by_date: dict[str, Mapping[str, Any]] = {}
    for row in values:
        if not isinstance(row, dict) or not isinstance(row.get("datetime"), str):
            raise LseHistoryError(f"{instrument['symbol']} contains an invalid price row")
        session = row["datetime"]
        if session in by_date:
            raise LseHistoryError(f"{instrument['symbol']} contains duplicate session {session}")
        if session not in expected:
            raise LseHistoryError(f"{instrument['symbol']} contains off-calendar session {session}")
        by_date[session] = row
    missing = sorted(set(expected) - set(by_date))
    if missing:
        raise LseHistoryError(
            f"{instrument['symbol']} is missing {len(missing)} expected XLON sessions"
        )
    multiplier = Decimal(instrument["price_to_gbp_multiplier"])
    lines: list[str] = []
    for session in sorted(expected):
        row = by_date[session]
        raw_prices = {
            field: _decimal(row.get(field), field, positive=True)
            for field in ("open", "high", "low", "close")
        }
        if raw_prices["low"] > min(raw_prices["open"], raw_prices["close"]):
            raise LseHistoryError(f"{instrument['symbol']} low exceeds open/close")
        if raw_prices["high"] < max(raw_prices["open"], raw_prices["close"]):
            raise LseHistoryError(f"{instrument['symbol']} high is below open/close")
        volume = _decimal(row.get("volume"), "volume")
        record = {
            "available_at": _next_available(session),
            "canonical_currency": "GBP",
            "close_gbp": _text_decimal(raw_prices["close"] * multiplier),
            "half_day": expected[session].half_day,
            "high_gbp": _text_decimal(raw_prices["high"] * multiplier),
            "instrument_id": instrument["symbol"],
            "interval": "1day",
            "low_gbp": _text_decimal(raw_prices["low"] * multiplier),
            "observed_at": expected[session].close_at,
            "open_gbp": _text_decimal(raw_prices["open"] * multiplier),
            "raw_close": _text_decimal(raw_prices["close"]),
            "raw_high": _text_decimal(raw_prices["high"]),
            "raw_low": _text_decimal(raw_prices["low"]),
            "raw_open": _text_decimal(raw_prices["open"]),
            "raw_quote_unit": instrument["quote_unit"],
            "session": session,
            "source_sha256": source_digest,
            "venue_mic": "XLON",
            "volume": _text_decimal(volume),
        }
        lines.append(canonical_json_line(record))
    return tuple(lines)


def normalize_actions(
    payload: Mapping[str, Any],
    instrument: Mapping[str, Any],
    endpoint: str,
    source_digest: str,
) -> tuple[str, ...]:
    if endpoint not in {"dividends", "splits"}:
        raise LseHistoryError("unsupported action endpoint")
    _meta(payload, instrument)
    values = payload.get(endpoint)
    if not isinstance(values, list):
        raise LseHistoryError(f"{instrument['symbol']} response lacks {endpoint}")
    date_key = "ex_date" if endpoint == "dividends" else "date"
    seen: set[str] = set()
    records: list[dict[str, Any]] = []
    for row in values:
        if not isinstance(row, dict) or not isinstance(row.get(date_key), str):
            raise LseHistoryError(f"{instrument['symbol']} contains invalid {endpoint}")
        action_date = row[date_key]
        try:
            parsed = datetime.fromisoformat(action_date).date()
        except ValueError as exc:
            raise LseHistoryError(f"{instrument['symbol']} contains invalid action date") from exc
        if not (datetime.fromisoformat(instrument["usable_start"]).date() <= parsed <= datetime(2025, 12, 31).date()):
            raise LseHistoryError(f"{instrument['symbol']} action is outside its boundary")
        if action_date in seen:
            raise LseHistoryError(f"{instrument['symbol']} contains duplicate action date")
        seen.add(action_date)
        if endpoint == "dividends":
            normalized_value = _text_decimal(_decimal(row.get("amount"), "dividend amount", positive=True))
            value_field = "raw_amount"
        else:
            ratio = row.get("ratio")
            if ratio is None:
                raise LseHistoryError(f"{instrument['symbol']} split lacks ratio")
            normalized_value = str(ratio)
            value_field = "raw_ratio"
        records.append(
            {
                "action_date": action_date,
                "action_type": endpoint[:-1],
                "cash_credit_eligible": False,
                "instrument_id": instrument["symbol"],
                "issuer_reconciliation_status": "pending",
                value_field: normalized_value,
                "source_sha256": source_digest,
                "venue_mic": "XLON",
            }
        )
    return tuple(canonical_json_line(item) for item in sorted(records, key=lambda item: item["action_date"]))


def load_source_manifest(path: Path, contract_path: Path, contract: Mapping[str, Any], repo_root: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
        payload = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LseHistoryError(f"cannot read LSE source manifest: {path}") from exc
    if not isinstance(payload, dict) or raw != canonical_json(payload):
        raise LseHistoryError("LSE source manifest must be canonical JSON")
    if payload.get("schema_version") != "cross-asset-a1-exact-xlon-history-source-manifest-v1":
        raise LseHistoryError("unexpected LSE source manifest schema")
    if payload.get("experiment_id") != contract["experiment_id"] or payload.get("contract_sha256") != sha256_file(contract_path):
        raise LseHistoryError("LSE source manifest contract lineage changed")
    specs = build_lse_request_specs(contract)
    responses = payload.get("responses")
    if not isinstance(responses, list) or len(responses) != len(specs):
        raise LseHistoryError("LSE source response count changed")
    expected = {(item.symbol, item.endpoint, item.filename) for item in specs}
    actual: set[tuple[str, str, str]] = set()
    for item in responses:
        file_name = Path(str(item.get("path", ""))).name
        actual.add((str(item.get("symbol")), str(item.get("endpoint")), file_name))
        raw_path = (repo_root / str(item.get("path", ""))).resolve(strict=True)
        raw_path.relative_to(repo_root.resolve(strict=True))
        if sha256_file(raw_path) != item.get("sha256"):
            raise LseHistoryError("LSE raw response checksum mismatch")
    if actual != expected:
        raise LseHistoryError("LSE source response set changed")
    return payload
