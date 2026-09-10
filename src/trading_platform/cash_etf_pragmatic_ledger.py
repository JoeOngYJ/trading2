"""Offline causal total-return ledger construction for the pragmatic cash-ETF C1 gate.

This module has no network, broker, database, message-bus, signal, order, or position
dependency.  It combines frozen raw unadjusted daily prices with frozen official issuer
corporate actions and deliberately treats the provider action feed as diagnostic only.
"""

from __future__ import annotations

import hashlib
import csv
import io
import json
import re
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation, getcontext
from pathlib import Path
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

from trading_platform.cash_etf_actions import parse_state_street_distributions


getcontext().prec = 28

EXPERIMENT_IDS = {
    "cash-etf-c1-pragmatic-action-ledger-v1",
    "cash-etf-c1-pragmatic-action-ledger-v2",
    "cash-etf-c1-pragmatic-action-ledger-v3",
    "cash-etf-c1-pragmatic-action-ledger-v4",
    "cash-etf-c1-pragmatic-action-ledger-v5",
}
SYMBOLS = ("BIL", "DBC", "EFA", "GLD", "IEF", "SPY", "TLT")
_SESSION_RE = re.compile(r'"session":"(\d{4}-\d{2}-\d{2})"')


class CashEtfPragmaticLedgerError(ValueError):
    """Raised when an input or pragmatic action gate fails closed."""


def canonical_json(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True, separators=(",", ": ")
    ) + "\n"


def canonical_json_line(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def decimal_string(value: Decimal) -> str:
    if not value.is_finite():
        raise CashEtfPragmaticLedgerError("non-finite Decimal")
    raw = format(value, "f")
    if "." in raw:
        raw = raw.rstrip("0").rstrip(".")
    return "0" if raw in {"", "-0"} else raw


def _repo_file(repo: Path, raw: Any, expected_sha256: Any, label: str) -> Path:
    if not isinstance(raw, str) or not raw or Path(raw).is_absolute():
        raise CashEtfPragmaticLedgerError(f"invalid {label} path")
    boundary = repo.resolve(strict=True)
    try:
        path = (boundary / raw).resolve(strict=True)
        path.relative_to(boundary)
    except (OSError, ValueError) as exc:
        raise CashEtfPragmaticLedgerError(f"invalid {label} path: {raw}") from exc
    if not path.is_file() or sha256_file(path) != expected_sha256:
        raise CashEtfPragmaticLedgerError(f"changed or missing {label}: {raw}")
    return path


def load_contract(repo: Path, path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    try:
        contract = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CashEtfPragmaticLedgerError("invalid pragmatic ledger contract") from exc
    if raw != canonical_json(contract):
        raise CashEtfPragmaticLedgerError("pragmatic ledger contract is not canonical JSON")
    if contract.get("experiment_id") not in EXPERIMENT_IDS or contract.get("status") != "frozen":
        raise CashEtfPragmaticLedgerError("unexpected or unfrozen pragmatic ledger contract")
    if contract["experiment_id"] == "cash-etf-c1-pragmatic-action-ledger-v5":
        predecessor = contract["predecessor"]
        predecessor_path = _repo_file(repo, predecessor["path"], predecessor["sha256"], "pragmatic v4 contract")
        _repo_file(repo, predecessor["evidence_path"], predecessor["evidence_sha256"], "pragmatic v4 evidence")
        inherited = load_contract(repo, predecessor_path)
        inherited["experiment_id"] = contract["experiment_id"]
        inherited["activated_at"] = contract["activated_at"]
        inherited["artifact_policy"] = dict(inherited["artifact_policy"])
        inherited["artifact_policy"]["artifact_root"] = contract["changes_from_predecessor"]["artifact_root"]
        inherited["successor_contract_path"] = str(path.relative_to(repo))
        contract = inherited
    elif contract["experiment_id"] == "cash-etf-c1-pragmatic-action-ledger-v4":
        predecessor = contract.get("predecessor", {})
        predecessor_path = _repo_file(
            repo, predecessor.get("path"), predecessor.get("sha256"), "pragmatic v3 contract"
        )
        _repo_file(
            repo,
            predecessor.get("evidence_path"),
            predecessor.get("evidence_sha256"),
            "pragmatic v3 evidence",
        )
        inherited = load_contract(repo, predecessor_path)
        inherited["experiment_id"] = contract["experiment_id"]
        inherited["activated_at"] = contract["activated_at"]
        inherited["artifact_policy"] = dict(inherited["artifact_policy"])
        inherited["artifact_policy"]["artifact_root"] = contract["changes_from_predecessor"][
            "artifact_root"
        ]
        inherited["fx_patch"] = dict(contract["changes_from_predecessor"]["fx_patch"])
        inherited["successor_contract_path"] = str(path.relative_to(repo))
        contract = inherited
    elif contract["experiment_id"] == "cash-etf-c1-pragmatic-action-ledger-v3":
        predecessor = contract.get("predecessor", {})
        predecessor_path = _repo_file(
            repo, predecessor.get("path"), predecessor.get("sha256"), "pragmatic v2 contract"
        )
        _repo_file(
            repo,
            predecessor.get("evidence_path"),
            predecessor.get("evidence_sha256"),
            "pragmatic v2 evidence",
        )
        inherited = load_contract(repo, predecessor_path)
        inherited["experiment_id"] = contract["experiment_id"]
        inherited["activated_at"] = contract["activated_at"]
        inherited["artifact_policy"] = dict(inherited["artifact_policy"])
        inherited["artifact_policy"]["artifact_root"] = contract["changes_from_predecessor"][
            "artifact_root"
        ]
        inherited["boundary"] = dict(contract["changes_from_predecessor"]["boundary"])
        inherited["acceptance_gates"] = dict(inherited["acceptance_gates"])
        inherited["acceptance_gates"]["distribution_event_counts"] = dict(
            contract["changes_from_predecessor"]["distribution_event_counts"]
        )
        inherited["inputs"] = dict(inherited["inputs"])
        inherited["inputs"]["fx"] = dict(contract["changes_from_predecessor"]["fx_input"])
        inherited["ledger_currency"] = contract["changes_from_predecessor"]["ledger_currency"]
        inherited["locked_numeric_partition_policy"] = contract["changes_from_predecessor"][
            "locked_numeric_partition_policy"
        ]
        inherited["successor_contract_path"] = str(path.relative_to(repo))
        contract = inherited
    elif contract["experiment_id"] == "cash-etf-c1-pragmatic-action-ledger-v2":
        predecessor = contract.get("predecessor", {})
        predecessor_path = _repo_file(
            repo, predecessor.get("path"), predecessor.get("sha256"), "pragmatic v1 contract"
        )
        _repo_file(
            repo,
            predecessor.get("evidence_path"),
            predecessor.get("evidence_sha256"),
            "pragmatic v1 evidence",
        )
        inherited_raw = predecessor_path.read_text(encoding="utf-8")
        inherited = json.loads(inherited_raw)
        if inherited_raw != canonical_json(inherited):
            raise CashEtfPragmaticLedgerError("pragmatic v1 contract is not canonical JSON")
        inherited["experiment_id"] = contract["experiment_id"]
        inherited["activated_at"] = contract["activated_at"]
        inherited["artifact_policy"] = dict(inherited["artifact_policy"])
        inherited["artifact_policy"]["artifact_root"] = contract["changes_from_predecessor"][
            "artifact_root"
        ]
        inherited["acceptance_gates"] = dict(inherited["acceptance_gates"])
        inherited["acceptance_gates"]["distribution_event_counts"] = dict(
            inherited["acceptance_gates"]["distribution_event_counts"]
        )
        inherited["acceptance_gates"]["distribution_event_counts"].update(
            contract["changes_from_predecessor"]["distribution_event_counts"]
        )
        inherited["distribution_row_policy"] = contract["changes_from_predecessor"][
            "distribution_row_policy"
        ]
        inherited["successor_contract_path"] = str(path.relative_to(repo))
        contract = inherited
    if contract.get("forbidden_actions") != [
        "account_or_trial_creation",
        "data_purchase",
        "database_or_message_bus_access",
        "order_or_position_creation",
        "production_signal_creation",
        "strategy_evaluation",
    ]:
        raise CashEtfPragmaticLedgerError("pragmatic ledger safety boundary changed")
    symbol_rows = contract.get("inputs", {}).get("symbols", [])
    if tuple(row.get("symbol") for row in symbol_rows) != SYMBOLS:
        raise CashEtfPragmaticLedgerError("pragmatic ledger universe changed")

    for group in ("official_action_evidence", "predecessor_evidence"):
        for record in contract["inputs"][group]:
            _repo_file(repo, record.get("path"), record.get("sha256"), group)
    for record in symbol_rows:
        for stem in ("daily", "provider_dividends", "provider_splits"):
            _repo_file(
                repo,
                record.get(f"{stem}_path"),
                record.get(f"{stem}_sha256"),
                f"{record['symbol']} {stem}",
            )
        if record.get("document_index_path") is not None:
            _repo_file(
                repo,
                record.get("document_index_path"),
                record.get("document_index_sha256"),
                f"{record['symbol']} document index",
            )
    if contract["experiment_id"] in {
        "cash-etf-c1-pragmatic-action-ledger-v3",
        "cash-etf-c1-pragmatic-action-ledger-v4",
        "cash-etf-c1-pragmatic-action-ledger-v5",
    }:
        fx = contract["inputs"].get("fx", {})
        _repo_file(repo, fx.get("path"), fx.get("sha256"), "GBP/USD daily input")
        if fx.get("symbol") != "GBP/USD" or contract.get("ledger_currency") != "GBP":
            raise CashEtfPragmaticLedgerError("GBP ledger contract changed")
    return contract


def parse_fred_dexusuk_patch(response: bytes, config: Mapping[str, Any]) -> dict[str, Any]:
    """Select only the precommitted DEXUSUK dates from an official FRED CSV response."""

    if len(response) > int(config["maximum_response_bytes"]):
        raise CashEtfPragmaticLedgerError("FRED response exceeds frozen size limit")
    try:
        text = response.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CashEtfPragmaticLedgerError("FRED response is not UTF-8") from exc
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames not in (["observation_date", "DEXUSUK"], ["DATE", "DEXUSUK"]):
        raise CashEtfPragmaticLedgerError("unexpected FRED DEXUSUK columns")
    date_column = reader.fieldnames[0]
    expected = tuple(config["expected_dates"])
    selected: dict[str, str] = {}
    for row in reader:
        session = row.get(date_column)
        if session not in expected:
            continue
        if session in selected:
            raise CashEtfPragmaticLedgerError(f"duplicate FRED DEXUSUK date: {session}")
        try:
            value = Decimal(str(row["DEXUSUK"]))
        except (InvalidOperation, KeyError) as exc:
            raise CashEtfPragmaticLedgerError(f"invalid FRED DEXUSUK value: {session}") from exc
        if not value.is_finite() or value <= 0:
            raise CashEtfPragmaticLedgerError(f"invalid FRED DEXUSUK value: {session}")
        selected[str(session)] = decimal_string(value)
    missing = sorted(set(expected) - set(selected))
    if missing:
        raise CashEtfPragmaticLedgerError(f"missing FRED DEXUSUK dates: {missing}")
    response_digest = hashlib.sha256(response).hexdigest()
    new_york = ZoneInfo("America/New_York")
    rows: list[dict[str, Any]] = []
    for session in expected:
        observation_date = date.fromisoformat(session)
        observed_at = datetime.combine(observation_date, time(12), new_york).astimezone(timezone.utc)
        available_at = datetime.combine(
            observation_date + timedelta(days=10), time(23, 59, 59), timezone.utc
        )
        value = selected[session]
        rows.append(
            {
                "available_at": available_at.isoformat().replace("+00:00", "Z"),
                "close": value,
                "high": value,
                "instrument_id": "FX-SPOT-GBP-USD",
                "low": value,
                "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
                "open": value,
                "session": session,
                "source_lineage_sha256": response_digest,
                "symbol": "GBP/USD",
                "volume": None,
            }
        )
    return {
        "availability_policy": config["availability_policy"],
        "release_policy_evidence_url": config["release_policy_evidence_url"],
        "response_sha256": response_digest,
        "rows": rows,
        "series_id": config["expected_series_id"],
        "source_url": config["source_url"],
        "units": config["expected_units"],
    }


def _utc(raw: Any, label: str) -> datetime:
    if not isinstance(raw, str) or not raw.endswith("Z"):
        raise CashEtfPragmaticLedgerError(f"{label} must use explicit UTC Z")
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CashEtfPragmaticLedgerError(f"invalid {label}") from exc
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise CashEtfPragmaticLedgerError(f"{label} must use UTC")
    return value


def read_price_rows(
    path: Path,
    symbol: str,
    start: str,
    end: str,
    *,
    allow_null_volume: bool = False,
) -> tuple[list[dict[str, Any]], int]:
    """Read only the frozen boundary; rows after ``end`` are never JSON-deserialized."""

    rows: list[dict[str, Any]] = []
    previous_session: str | None = None
    post_boundary_rows_deserialized = 0
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        match = _SESSION_RE.search(raw)
        if not match:
            raise CashEtfPragmaticLedgerError(f"missing session token: {path}:{line_number}")
        session = match.group(1)
        if session < start:
            continue
        if session > end:
            break
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CashEtfPragmaticLedgerError(f"invalid price JSON: {path}:{line_number}") from exc
        if row.get("session") != session or row.get("symbol") != symbol:
            raise CashEtfPragmaticLedgerError(f"price identity mismatch: {path}:{line_number}")
        if previous_session is not None and session <= previous_session:
            raise CashEtfPragmaticLedgerError(f"duplicate or reversed price session: {symbol}")
        previous_session = session
        observed_at = _utc(row.get("observed_at"), f"{symbol} observed_at")
        available_at = _utc(row.get("available_at"), f"{symbol} available_at")
        if available_at <= observed_at:
            raise CashEtfPragmaticLedgerError(f"non-causal availability: {symbol} {session}")
        try:
            open_price = Decimal(str(row["open"]))
            high = Decimal(str(row["high"]))
            low = Decimal(str(row["low"]))
            close = Decimal(str(row["close"]))
            raw_volume = row["volume"]
            volume = Decimal(0) if allow_null_volume and raw_volume is None else Decimal(str(raw_volume))
        except (KeyError, InvalidOperation) as exc:
            raise CashEtfPragmaticLedgerError(f"invalid numeric price row: {symbol} {session}") from exc
        if (
            any(not value.is_finite() for value in (open_price, high, low, close, volume))
            or min(open_price, high, low, close) <= 0
            or volume < 0
            or high < max(open_price, close)
            or low > min(open_price, close)
        ):
            raise CashEtfPragmaticLedgerError(f"invalid OHLC bounds: {symbol} {session}")
        rows.append(row)
    if not rows or rows[0]["session"] != start:
        raise CashEtfPragmaticLedgerError(f"price start boundary missing: {symbol}")
    return rows, post_boundary_rows_deserialized


def read_action_rows(path: Path, start: str, end: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CashEtfPragmaticLedgerError(f"invalid action JSON: {path}:{line_number}") from exc
        action_date = row.get("action_date")
        if isinstance(action_date, str) and start <= action_date <= end:
            rows.append(row)
    return rows


def parse_ishares_component(path: Path, symbol: str, start: str, end: str) -> list[dict[str, str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    columns = {
        row.get("name"): row.get("value")
        for row in payload.get("distributionTableData", [])
        if row.get("name") in {"recordDate", "exDate", "payableDate", "totalDistribution"}
    }
    if set(columns) != {"recordDate", "exDate", "payableDate", "totalDistribution"}:
        raise CashEtfPragmaticLedgerError(f"incomplete iShares component: {symbol}")
    lengths = {len(value) for value in columns.values() if isinstance(value, list)}
    if len(lengths) != 1:
        raise CashEtfPragmaticLedgerError(f"misaligned iShares component: {symbol}")
    events: list[dict[str, str]] = []
    for index in range(next(iter(lengths))):
        raw_ex_date = str(columns["exDate"][index])
        ex_date = datetime.strptime(raw_ex_date, "%Y%m%d").date().isoformat()
        if not start <= ex_date <= end:
            continue
        events.append(
            {
                "amount_per_share": decimal_string(
                    Decimal(str(columns["totalDistribution"][index]))
                ),
                "currency": "USD",
                "ex_date": ex_date,
                "payable_date": datetime.strptime(
                    str(columns["payableDate"][index]), "%Y%m%d"
                ).date().isoformat(),
                "record_date": datetime.strptime(
                    str(columns["recordDate"][index]), "%Y%m%d"
                ).date().isoformat(),
                "source_role": "official_issuer_history",
            }
        )
    return sorted(events, key=lambda row: row["ex_date"])


def official_distributions(repo: Path, contract: Mapping[str, Any]) -> dict[str, list[dict[str, str]]]:
    records = {Path(row["path"]).name: row for row in contract["inputs"]["official_action_evidence"]}
    workbook_record = records["state-street-historical-distributions.xlsx"]
    workbook = _repo_file(repo, workbook_record["path"], workbook_record["sha256"], "workbook")
    start = contract["boundary"]["start_inclusive"]
    end = contract["boundary"]["end_inclusive"]
    result = parse_state_street_distributions(workbook.read_bytes(), ("BIL", "SPY"), start, end)
    for symbol, events in result.items():
        result[symbol] = [
            event for event in events if Decimal(str(event["amount_per_share"])) > 0
        ]
        for event in result[symbol]:
            event["source_role"] = "official_issuer_history"

    for symbol in ("EFA", "IEF", "TLT"):
        name = f"ishares-{symbol.lower()}-distribution-component.json"
        record = records[name]
        path = _repo_file(repo, record["path"], record["sha256"], f"{symbol} component")
        result[symbol] = parse_ishares_component(path, symbol, start, end)

    report_record = records["reconciliation-report.json"]
    report_path = _repo_file(
        repo, report_record["path"], report_record["sha256"], "issuer reconciliation report"
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    dbc = next(row for row in report["instrument_results"] if row["symbol"] == "DBC")
    result["DBC"] = [
        {**event, "source_role": "issuer_filed_event_detail"}
        for event in dbc["distribution_reconciliation"]["event_details"]
        if start <= event["ex_date"] <= end
    ]

    gld_record = records["gld-issuer-filed-no-income-statement-action-extract.json"]
    gld_path = _repo_file(repo, gld_record["path"], gld_record["sha256"], "GLD no-income extract")
    gld = json.loads(gld_path.read_text(encoding="utf-8"))
    if not any("does not generate any income" in text.lower() for text in gld.get("extracts", [])):
        raise CashEtfPragmaticLedgerError("GLD no-income statement missing")
    result["GLD"] = []
    return result


def split_candidates(
    rows: Iterable[Mapping[str, Any]], candidate_ratios: Iterable[str], tolerance: str, minimum: str
) -> list[dict[str, str]]:
    prices = list(rows)
    ratios = [Decimal(value) for value in candidate_ratios]
    maximum_distance = Decimal(tolerance)
    minimum_return = Decimal(minimum)
    result: list[dict[str, str]] = []
    for previous, current in zip(prices, prices[1:], strict=False):
        observed = Decimal(str(current["open"])) / Decimal(str(previous["close"]))
        if abs(observed - 1) < minimum_return:
            continue
        closest = min(ratios, key=lambda candidate: abs(observed / candidate - 1))
        relative_distance = abs(observed / closest - 1)
        if relative_distance <= maximum_distance:
            result.append(
                {
                    "date": str(current["session"]),
                    "observed_open_previous_close_ratio": decimal_string(observed),
                    "relative_distance": decimal_string(relative_distance),
                    "suspected_ratio": decimal_string(closest),
                }
            )
    return result


def build_ledger_rows(
    symbol: str,
    prices: list[Mapping[str, Any]],
    distributions: list[Mapping[str, Any]],
    splits: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    sessions = {str(row["session"]) for row in prices}
    distribution_by_date: dict[str, Mapping[str, Any]] = {}
    for event in distributions:
        ex_date = str(event["ex_date"])
        if ex_date not in sessions or ex_date in distribution_by_date:
            raise CashEtfPragmaticLedgerError(f"invalid distribution session: {symbol} {ex_date}")
        if Decimal(str(event["amount_per_share"])) <= 0:
            raise CashEtfPragmaticLedgerError(f"non-positive distribution: {symbol} {ex_date}")
        distribution_by_date[ex_date] = event
    split_by_date: dict[str, Mapping[str, Any]] = {}
    for event in splits:
        action_date = str(event["action_date"])
        if action_date not in sessions or action_date in split_by_date:
            raise CashEtfPragmaticLedgerError(f"invalid split session: {symbol} {action_date}")
        split_by_date[action_date] = event

    ledger: list[dict[str, Any]] = []
    wealth = Decimal(1)
    previous_close: Decimal | None = None
    for price in prices:
        session = str(price["session"])
        close = Decimal(str(price["close"]))
        distribution = distribution_by_date.get(session)
        cash = Decimal(str(distribution["amount_per_share"])) if distribution else Decimal(0)
        split = split_by_date.get(session)
        multiplier = (
            Decimal(str(split["from_factor"])) / Decimal(str(split["to_factor"]))
            if split
            else Decimal(1)
        )
        if previous_close is None:
            price_return = None
            total_return = None
        else:
            price_return_value = close * multiplier / previous_close - 1
            total_return_value = (close * multiplier + cash) / previous_close - 1
            wealth *= 1 + total_return_value
            price_return = decimal_string(price_return_value)
            total_return = decimal_string(total_return_value)
        ledger.append(
            {
                "available_at": price["available_at"],
                "close": decimal_string(close),
                "open": decimal_string(Decimal(str(price["open"]))),
                "distribution_amount_per_share": decimal_string(cash),
                "distribution_source_role": distribution.get("source_role") if distribution else None,
                "instrument_id": price["instrument_id"],
                "observed_at": price["observed_at"],
                "price_return": price_return,
                "session": session,
                "source_lineage_sha256": price["source_lineage_sha256"],
                "split_share_multiplier": decimal_string(multiplier),
                "symbol": symbol,
                "total_return": total_return,
                "wealth_index": decimal_string(wealth),
            }
        )
        previous_close = close
    return ledger


def convert_ledger_to_gbp(
    usd_ledger: Iterable[Mapping[str, Any]], fx_rows: Iterable[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Convert USD total-return factors to GBP at same-session causal FX closes."""

    ledger = list(usd_ledger)
    fx_by_session = {str(row["session"]): row for row in fx_rows}
    result: list[dict[str, Any]] = []
    previous_fx: Decimal | None = None
    gbp_wealth = Decimal(1)
    for row in ledger:
        session = str(row["session"])
        fx = fx_by_session.get(session)
        if fx is None:
            raise CashEtfPragmaticLedgerError(f"missing GBP/USD session: {session}")
        fx_close = Decimal(str(fx["close"]))
        if fx_close <= 0:
            raise CashEtfPragmaticLedgerError(f"invalid GBP/USD close: {session}")
        usd_return = row["total_return"]
        if previous_fx is None:
            gbp_return = None
        else:
            if usd_return is None:
                raise CashEtfPragmaticLedgerError("missing non-initial USD return")
            gbp_factor = (Decimal(1) + Decimal(str(usd_return))) * previous_fx / fx_close
            gbp_return_value = gbp_factor - 1
            gbp_wealth *= gbp_factor
            gbp_return = decimal_string(gbp_return_value)
        output = dict(row)
        output["available_at"] = max(
            (str(row["available_at"]), str(fx["available_at"])), key=lambda value: _utc(value, "availability")
        )
        output["currency"] = "GBP"
        output["gbp_close_equivalent"] = decimal_string(Decimal(str(row["close"])) / fx_close)
        output["gbp_open_equivalent"] = decimal_string(Decimal(str(row["open"])) / fx_close)
        output["gbp_usd_close"] = decimal_string(fx_close)
        output["gbp_usd_source_lineage_sha256"] = fx["source_lineage_sha256"]
        output["total_return_usd"] = output.pop("total_return")
        output["wealth_index_usd"] = output.pop("wealth_index")
        output["total_return"] = gbp_return
        output["wealth_index"] = decimal_string(gbp_wealth)
        result.append(output)
        previous_fx = fx_close
    return result
