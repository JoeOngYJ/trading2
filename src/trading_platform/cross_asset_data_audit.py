"""Pure, offline validation for the frozen cross-asset A1 source pilot."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping, Sequence

from trading_platform.cross_asset_program import canonical_json, sha256_file


EXPECTED_PILOT_ID = "cross-asset-a1-lse-source-pilot-v1"
EXPECTED_SCHEMA = "cross-asset-a1-source-pilot-contract-v1"
EXPECTED_TICKERS = ("SWDA", "VAGS", "SGLN", "COMM")
EXPECTED_COLUMNS = ("Date", "Open", "High", "Low", "Close", "Volume")


class CrossAssetDataAuditError(ValueError):
    """Raised when source bytes or their lineage fail the frozen A1 contract."""


def _decimal(raw: str, label: str) -> Decimal:
    try:
        value = Decimal(raw)
    except (InvalidOperation, ValueError) as exc:
        raise CrossAssetDataAuditError(f"invalid {label}: {raw}") from exc
    if not value.is_finite():
        raise CrossAssetDataAuditError(f"non-finite {label}")
    return value


def validate_a1_contract(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != EXPECTED_SCHEMA:
        raise CrossAssetDataAuditError("unsupported A1 pilot schema")
    if payload.get("pilot_id") != EXPECTED_PILOT_ID or payload.get("status") != "frozen":
        raise CrossAssetDataAuditError("unexpected or unfrozen A1 pilot")
    if payload.get("strategy_evaluation_authorized") is not False:
        raise CrossAssetDataAuditError("A1 cannot authorize strategy evaluation")
    prohibited = payload.get("prohibitions", {})
    for key in (
        "bulk_download_allowed",
        "credentials_allowed",
        "derivative_data_allowed",
        "economic_metrics_allowed",
        "execution_approval_allowed",
        "partial_ob0_access_allowed",
        "pnl_allowed",
        "protected_service_access_allowed",
        "strategy_parameters_allowed",
        "strategy_signals_allowed",
    ):
        if prohibited.get(key) is not False:
            raise CrossAssetDataAuditError(f"A1 prohibition changed: {key}")
    if payload.get("jurisdiction", {}).get("execution_access_approved") is not False:
        raise CrossAssetDataAuditError("A1 cannot approve execution access")
    instruments = payload.get("instruments")
    if not isinstance(instruments, list) or tuple(item.get("ticker") for item in instruments) != EXPECTED_TICKERS:
        raise CrossAssetDataAuditError("A1 exact instrument order or membership changed")
    identities = [item.get("instrument_id") for item in instruments]
    if len(set(identities)) != len(identities):
        raise CrossAssetDataAuditError("A1 instrument identities must be unique")
    for item in instruments:
        if item.get("exchange") != "London Stock Exchange" or item.get("listing_currency") != "GBP":
            raise CrossAssetDataAuditError("A1 instruments must use the frozen GBP LSE lines")
        if not all(item.get(key) for key in ("isin", "sedol", "ric", "stooq_symbol")):
            raise CrossAssetDataAuditError("A1 instrument mapping is incomplete")
    boundaries = payload.get("boundaries", {})
    sessions = boundaries.get("expected_lse_sessions")
    if not isinstance(sessions, list) or len(sessions) != 22 or len(set(sessions)) != 22:
        raise CrossAssetDataAuditError("A1 must freeze exactly 22 unique LSE sessions")
    parsed = [date.fromisoformat(value) for value in sessions]
    if parsed != sorted(parsed) or any(value.weekday() >= 5 for value in parsed):
        raise CrossAssetDataAuditError("A1 expected sessions are invalid or unordered")
    source = payload.get("sources", {}).get("stooq_daily_csv", {})
    if source.get("maximum_requests") != 4 or source.get("accepted_before_pilot") is not False:
        raise CrossAssetDataAuditError("A1 Stooq request or acceptance boundary changed")
    if tuple(source.get("expected_columns", ())) != EXPECTED_COLUMNS:
        raise CrossAssetDataAuditError("A1 expected CSV schema changed")
    if source.get("credentials_required") is not False:
        raise CrossAssetDataAuditError("A1 pilot cannot require credentials")


def load_frozen_contract(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    payload = json.loads(raw)
    if not isinstance(payload, dict) or raw != canonical_json(payload):
        raise CrossAssetDataAuditError("A1 contract is not canonical JSON")
    validate_a1_contract(payload)
    return payload


@dataclass(frozen=True, slots=True)
class ParsedDailyCsv:
    ticker: str
    rows: int
    first_session: str
    last_session: str
    raw_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "first_session": self.first_session,
            "last_session": self.last_session,
            "raw_sha256": self.raw_sha256,
            "rows": self.rows,
            "ticker": self.ticker,
        }


def parse_stooq_daily_csv(
    payload: bytes, *, ticker: str, expected_sessions: Sequence[str]
) -> ParsedDailyCsv:
    if ticker not in EXPECTED_TICKERS:
        raise CrossAssetDataAuditError(f"unexpected ticker: {ticker}")
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CrossAssetDataAuditError(f"{ticker} CSV is not UTF-8") from exc
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if tuple(reader.fieldnames or ()) != EXPECTED_COLUMNS:
        raise CrossAssetDataAuditError(f"{ticker} CSV has unexpected columns")
    observed: list[str] = []
    for row in reader:
        if None in row or any(row.get(column) in (None, "") for column in EXPECTED_COLUMNS):
            raise CrossAssetDataAuditError(f"{ticker} CSV has a missing or extra field")
        try:
            session = date.fromisoformat(str(row["Date"]))
        except ValueError as exc:
            raise CrossAssetDataAuditError(f"{ticker} CSV has an invalid session date") from exc
        open_price = _decimal(str(row["Open"]), "open")
        high = _decimal(str(row["High"]), "high")
        low = _decimal(str(row["Low"]), "low")
        close = _decimal(str(row["Close"]), "close")
        volume = _decimal(str(row["Volume"]), "volume")
        if low <= 0 or low > min(open_price, close) or high < max(open_price, close):
            raise CrossAssetDataAuditError(f"{ticker} CSV has invalid OHLC bounds")
        if volume < 0 or volume != volume.to_integral_value():
            raise CrossAssetDataAuditError(f"{ticker} CSV has invalid volume")
        observed.append(session.isoformat())
    if not observed:
        raise CrossAssetDataAuditError(f"{ticker} CSV is empty")
    if observed != list(expected_sessions):
        raise CrossAssetDataAuditError(
            f"{ticker} session coverage mismatch: {len(observed)} rows"
        )
    return ParsedDailyCsv(
        ticker=ticker,
        rows=len(observed),
        first_session=observed[0],
        last_session=observed[-1],
        raw_sha256=hashlib.sha256(payload).hexdigest(),
    )


def verify_manifest_file(root: Path, record: Mapping[str, Any]) -> Path:
    raw = record.get("path")
    if not isinstance(raw, str) or not raw or Path(raw).is_absolute():
        raise CrossAssetDataAuditError("manifest path must be repository-relative")
    boundary = root.resolve(strict=True)
    try:
        path = (boundary / raw).resolve(strict=True)
        path.relative_to(boundary)
    except (OSError, ValueError) as exc:
        raise CrossAssetDataAuditError(f"invalid manifest path: {raw}") from exc
    if record.get("sha256") != sha256_file(path):
        raise CrossAssetDataAuditError(f"manifest checksum mismatch: {raw}")
    return path
