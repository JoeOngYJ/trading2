"""Offline parsers and fail-closed comparison for cash-ETF corporate actions."""

from __future__ import annotations

import html
import json
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable, Mapping
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile


class CashEtfActionError(ValueError):
    """Raised when an issuer action source is invalid or incomplete."""


_XLSX_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_COMPONENT_RE = re.compile(
    rb'<div data-componentname="DistributionV3"><walrus-render-on-client[^>]*componentprops="([^"]+)"',
    re.DOTALL,
)


def canonical_json(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True, separators=(",", ": ")
    ) + "\n"


def load_contract(repo_root: Path, successor_path: Path) -> dict[str, Any]:
    successor = json.loads(successor_path.read_text(encoding="utf-8"))
    predecessor_path = repo_root / successor["predecessor"]["path"]
    predecessor = json.loads(predecessor_path.read_text(encoding="utf-8"))
    merged = dict(predecessor)
    merged["experiment_id"] = successor["experiment_id"]
    merged["activated_at"] = successor["activated_at"]
    merged["artifact_policy"] = dict(predecessor["artifact_policy"])
    merged["artifact_policy"]["artifact_root"] = successor["changes_from_predecessor"]["artifact_root"]
    merged["source_allowlist"] = successor["changes_from_predecessor"]["source_allowlist"]
    merged["successor_contract_path"] = str(successor_path.relative_to(repo_root))
    return merged


def _cell_column(reference: str) -> str:
    return "".join(character for character in reference if character.isalpha())


def _xlsx_rows(payload: bytes) -> list[dict[str, str]]:
    try:
        archive = ZipFile(BytesIO(payload))
        shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
        sheet_root = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    except (BadZipFile, KeyError, ET.ParseError) as exc:
        raise CashEtfActionError("invalid State Street distributions workbook") from exc
    shared = [
        "".join(node.text or "" for node in item.iter(_XLSX_NS + "t"))
        for item in shared_root.findall(_XLSX_NS + "si")
    ]
    raw_rows: list[dict[str, str]] = []
    for row in sheet_root.findall(".//" + _XLSX_NS + "row"):
        values: dict[str, str] = {}
        for cell in row.findall(_XLSX_NS + "c"):
            value_node = cell.find(_XLSX_NS + "v")
            value = "" if value_node is None else value_node.text or ""
            if cell.get("t") == "s" and value:
                value = shared[int(value)]
            values[_cell_column(str(cell.get("r", "")))] = value.strip()
        raw_rows.append(values)
    if not raw_rows:
        raise CashEtfActionError("empty State Street distributions workbook")
    headings = raw_rows[0]
    expected = {
        "A": "FUND NAME",
        "B": "TICKER",
        "C": "CUSIP",
        "D": "EX-DATE",
        "E": "RECORD DATE",
        "F": "PAYABLE DATE",
        "G": "DIVIDEND ($)",
        "H": "SHORT TERM CAPITAL GAIN ($)",
        "I": "LONG TERM CAPITAL GAIN ($)",
    }
    if any(headings.get(column) != label for column, label in expected.items()):
        raise CashEtfActionError("State Street workbook schema changed")
    return raw_rows[1:]


def parse_state_street_distributions(
    payload: bytes, symbols: Iterable[str], start: str, end: str
) -> dict[str, list[dict[str, str]]]:
    requested = set(symbols)
    result = {symbol: [] for symbol in sorted(requested)}
    seen: set[tuple[str, str]] = set()
    for row in _xlsx_rows(payload):
        symbol = row.get("B", "")
        if symbol not in requested:
            continue
        try:
            ex_date = datetime.strptime(row["D"], "%m/%d/%Y").date().isoformat()
            record_date = datetime.strptime(row["E"], "%m/%d/%Y").date().isoformat()
            payable_date = datetime.strptime(row["F"], "%m/%d/%Y").date().isoformat()
            components = [Decimal(row[column] or "0") for column in ("G", "H", "I")]
        except (KeyError, ValueError, InvalidOperation) as exc:
            raise CashEtfActionError(f"invalid State Street row for {symbol}") from exc
        if not start <= ex_date <= end:
            continue
        key = (symbol, ex_date)
        if key in seen:
            raise CashEtfActionError(f"duplicate State Street distribution: {symbol} {ex_date}")
        seen.add(key)
        result[symbol].append(
            {
                "amount_per_share": format(sum(components), "f"),
                "currency": "USD",
                "ex_date": ex_date,
                "issuer_cusip": row.get("C", ""),
                "payable_date": payable_date,
                "record_date": record_date,
            }
        )
    for events in result.values():
        events.sort(key=lambda row: row["ex_date"])
    return result


def extract_ishares_distributions(
    payload: bytes, symbol: str, start: str, end: str
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    match = _COMPONENT_RE.search(payload)
    if not match:
        raise CashEtfActionError(f"DistributionV3 component missing for {symbol}")
    try:
        component = json.loads(html.unescape(match.group(1).decode("utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CashEtfActionError(f"invalid DistributionV3 component for {symbol}") from exc
    columns = {
        row.get("name"): row.get("value")
        for row in component.get("distributionTableData", [])
        if row.get("name") in {"recordDate", "exDate", "payableDate", "totalDistribution"}
    }
    if set(columns) != {"recordDate", "exDate", "payableDate", "totalDistribution"}:
        raise CashEtfActionError(f"incomplete DistributionV3 columns for {symbol}")
    lengths = {len(value) for value in columns.values() if isinstance(value, list)}
    if len(lengths) != 1 or len(columns) != 4:
        raise CashEtfActionError(f"misaligned DistributionV3 columns for {symbol}")
    events: list[dict[str, str]] = []
    seen: set[str] = set()
    for index in range(next(iter(lengths))):
        raw_date = str(columns["exDate"][index])
        if not re.fullmatch(r"\d{8}", raw_date):
            raise CashEtfActionError(f"invalid iShares ex-date for {symbol}")
        ex_date = datetime.strptime(raw_date, "%Y%m%d").date().isoformat()
        if not start <= ex_date <= end:
            continue
        if ex_date in seen:
            raise CashEtfActionError(f"duplicate iShares distribution: {symbol} {ex_date}")
        seen.add(ex_date)
        events.append(
            {
                "amount_per_share": format(Decimal(str(columns["totalDistribution"][index])), "f"),
                "currency": "USD",
                "ex_date": ex_date,
                "payable_date": datetime.strptime(
                    str(columns["payableDate"][index]), "%Y%m%d"
                ).date().isoformat(),
                "record_date": datetime.strptime(
                    str(columns["recordDate"][index]), "%Y%m%d"
                ).date().isoformat(),
            }
        )
    events.sort(key=lambda row: row["ex_date"])
    action_only = {
        "distributionTableData": [
            row
            for row in component["distributionTableData"]
            if row.get("name") in {"recordDate", "exDate", "payableDate", "totalDistribution"}
        ]
    }
    return action_only, events


def read_provider_actions(path: Path, start: str, end: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CashEtfActionError(f"invalid provider JSONL line {line_number}: {path}") from exc
        action_date = row.get("action_date")
        if isinstance(action_date, str) and start <= action_date <= end:
            rows.append(row)
    return rows


def compare_distributions(
    provider: Iterable[Mapping[str, Any]], official: Iterable[Mapping[str, Any]]
) -> dict[str, Any]:
    provider_by_date = {str(row["action_date"]): row for row in provider}
    official_by_date = {str(row["ex_date"]): row for row in official}
    missing_from_provider = sorted(set(official_by_date) - set(provider_by_date))
    missing_from_official = sorted(set(provider_by_date) - set(official_by_date))
    amount_mismatches: list[dict[str, str]] = []
    for action_date in sorted(set(provider_by_date) & set(official_by_date)):
        provider_raw = str(provider_by_date[action_date]["amount_per_share"])
        official_raw = str(official_by_date[action_date]["amount_per_share"])
        decimals = len(provider_raw.partition(".")[2])
        tolerance = Decimal(5).scaleb(-(decimals + 1))
        difference = abs(Decimal(provider_raw) - Decimal(official_raw))
        if difference > tolerance:
            amount_mismatches.append(
                {
                    "absolute_difference": format(difference, "f"),
                    "action_date": action_date,
                    "official_amount": official_raw,
                    "provider_amount": provider_raw,
                    "tolerance": format(tolerance, "f"),
                }
            )
    passed = not missing_from_provider and not missing_from_official and not amount_mismatches
    return {
        "amount_mismatches": amount_mismatches,
        "matched_event_count": len(set(provider_by_date) & set(official_by_date)) - len(amount_mismatches),
        "missing_from_official": missing_from_official,
        "missing_from_provider": missing_from_provider,
        "official_event_count": len(official_by_date),
        "passed": passed,
        "provider_event_count": len(provider_by_date),
    }
