"""Fail-closed source-only helpers for the cash-ETF issuer action ledger gate."""

from __future__ import annotations

import hashlib
import html
import json
import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Mapping

from trading_platform.cash_etf_actions import compare_distributions


class CashEtfIssuerActionError(ValueError):
    """Raised when the frozen issuer-source contract cannot be proved."""


EXPERIMENT_ID = "cash-etf-c1-issuer-action-ledger-source-v1"
SCHEMA_VERSION = "cash-etf-c1-issuer-action-ledger-source-contract-v1"


def canonical_json(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True, separators=(",", ": ")
    ) + "\n"


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_contract(path: Path) -> dict[str, Any]:
    contract = json.loads(path.read_text(encoding="utf-8"))
    if contract.get("experiment_id") != EXPERIMENT_ID or contract.get("status") != "frozen":
        raise CashEtfIssuerActionError("unexpected or unfrozen issuer-action contract")
    sources = contract.get("source_allowlist")
    maximum = contract.get("operational_limits", {}).get("maximum_responses")
    if not isinstance(sources, list) or len(sources) != maximum:
        raise CashEtfIssuerActionError("source allowlist violates frozen response limit")
    if contract.get("whole_universe_gate") != (
        "all_seven_distribution_and_split_histories_must_pass_before_numeric_ledger_or_c2"
    ):
        raise CashEtfIssuerActionError("whole-universe gate changed")
    return contract


def verify_frozen_inputs(repo: Path, contract: Mapping[str, Any]) -> None:
    predecessor = contract["predecessor"]
    if sha256_file(repo / predecessor["path"]) != predecessor["sha256"]:
        raise CashEtfIssuerActionError("predecessor checksum changed")
    for record in contract["inherited_action_sources"]:
        if sha256_file(repo / record["path"]) != record["sha256"]:
            raise CashEtfIssuerActionError(f"inherited action source changed: {record['path']}")
    for key in ("prior_reconciliation_report", "provider_dbc_dividends"):
        record = contract[key]
        if sha256_file(repo / record["path"]) != record["sha256"]:
            raise CashEtfIssuerActionError(f"frozen input changed: {record['path']}")


def normalize_html_text(payload: bytes) -> str:
    decoded = payload.decode("utf-8", errors="replace")
    without_tags = re.sub(r"<[^>]+>", " ", decoded)
    return re.sub(r"\s+", " ", html.unescape(without_tags)).strip()


def _money(raw: str) -> str:
    value = raw.strip().replace(",", "")
    if value in {"—", "–", "-", "&#8212;"}:
        return "0"
    return format(Decimal(value), "f")


def extract_dbc_distribution_table(text: str) -> dict[int, str]:
    """Extract the three-year DBC distributions-per-share table when present."""

    pattern = re.compile(
        r"Years Ended December\s+31,?\s+"
        r"(20\d{2})\s+(20\d{2})\s+(20\d{2})\s+"
        r"Distributions per General Share\s+\$\s*(—|–|-|[0-9.,]+)\s+"
        r"\$\s*(—|–|-|[0-9.,]+)\s+\$\s*(—|–|-|[0-9.,]+)",
        flags=re.IGNORECASE,
    )
    matches = list(pattern.finditer(text))
    if not matches:
        return {}
    years_and_values: dict[int, str] = {}
    for match in matches:
        for year, value in zip(match.groups()[:3], match.groups()[3:], strict=True):
            normalized = _money(value)
            previous = years_and_values.get(int(year))
            if previous is not None and previous != normalized:
                raise CashEtfIssuerActionError(f"conflicting DBC annual distribution for {year}")
            years_and_values[int(year)] = normalized
    return years_and_values


def extract_explicit_zero_distribution_years(text: str) -> set[int]:
    result: set[int] = set()
    for match in re.finditer(
        r"No distributions were paid(?: to Shareholders)?(?: during| for) the "
        r"(?:Year|Years|year|years) Ended December\s+31,?\s+([^\.]{0,90})",
        text,
    ):
        result.update(int(year) for year in re.findall(r"20\d{2}", match.group(1)))
    return result


def extract_dbc_event_detail(text: str) -> dict[str, str]:
    pattern = re.compile(
        r"A distribution for the year ended December\s+31,\s+(20\d{2}) was paid on "
        r"([A-Z][a-z]+\s+\d{1,2},\s+20\d{2}) to holders of record as of "
        r"([A-Z][a-z]+\s+\d{1,2},\s+20\d{2}) at a rate of\s+\$\s*([0-9.]+)",
        flags=re.IGNORECASE,
    )
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise CashEtfIssuerActionError("expected exactly one DBC event-detail statement")
    year, payable, record, amount = matches[0].groups()
    return {
        "amount_per_share": _money(amount),
        "payable_date": datetime.strptime(payable, "%B %d, %Y").date().isoformat(),
        "record_date": datetime.strptime(record, "%B %d, %Y").date().isoformat(),
        "year": year,
    }


def audit_dbc_sources(
    contract: Mapping[str, Any], source_text: Mapping[str, str], provider: Iterable[Mapping[str, Any]]
) -> dict[str, Any]:
    expected_by_year = {
        int(year): str(amount)
        for year, amount in contract["frozen_dbc_expected_distribution_by_year"].items()
    }
    observed_by_year: dict[int, str] = {}
    covered_sources: dict[int, str] = {}
    for source in contract["source_allowlist"]:
        years = source.get("covered_years")
        if not years:
            continue
        source_id = source["source_id"]
        text = source_text[source_id]
        table = extract_dbc_distribution_table(text)
        zero_years = extract_explicit_zero_distribution_years(text)
        for year in years:
            if year in table:
                amount = table[year]
            elif year in zero_years:
                amount = "0"
            else:
                raise CashEtfIssuerActionError(f"DBC year {year} not explicitly covered")
            if Decimal(amount) != Decimal(expected_by_year[year]):
                raise CashEtfIssuerActionError(f"DBC frozen expectation mismatch for {year}")
            observed_by_year[year] = amount
            covered_sources[year] = source_id
    if set(observed_by_year) != set(range(2009, 2024)):
        raise CashEtfIssuerActionError("DBC annual source coverage is incomplete")

    detail_by_year: dict[int, dict[str, str]] = {}
    for source_id in (
        "dbc_2018_form_10k_event_detail",
        "dbc_2019_form_10k_event_detail",
        "dbc_2022_form_10k_event_detail",
        "dbc_2023_form_10k",
    ):
        detail = extract_dbc_event_detail(source_text[source_id])
        detail_by_year[int(detail.pop("year"))] = detail

    official_events: list[dict[str, str]] = []
    expected_events = contract["frozen_dbc_expected_events"]
    for expected in expected_events:
        year = int(expected["record_date"][:4])
        detail = detail_by_year.get(year)
        comparison = {key: expected[key] for key in ("amount_per_share", "payable_date", "record_date")}
        if detail != comparison:
            raise CashEtfIssuerActionError(f"DBC event detail mismatch for {year}")
        official_events.append(
            {
                "amount_per_share": detail["amount_per_share"],
                "currency": "USD",
                "ex_date": expected["derived_ex_date"],
                "ex_date_lineage": "issuer_record_date_plus_pre_2024_nyse_arca_rule_7_4_e",
                "payable_date": detail["payable_date"],
                "record_date": detail["record_date"],
            }
        )
    reconciliation = compare_distributions(provider, official_events)
    return {
        "annual_coverage": [
            {"amount_per_share": observed_by_year[year], "source_id": covered_sources[year], "year": year}
            for year in sorted(observed_by_year)
        ],
        "distribution_reconciliation": reconciliation,
        "event_details": official_events,
        "passed": reconciliation["passed"],
    }


def document_index_proves_zero_splits(text: str, start: str, end: str) -> bool:
    """Require an explicit completeness scope; absence of split words is never enough."""

    normalized = text.lower()
    required = (
        "complete corporate action history",
        start,
        end,
        "no stock splits or reverse stock splits",
    )
    return all(value in normalized for value in required)


def gld_proves_zero_distributions(texts: Iterable[str], start: str, end: str) -> bool:
    """Require explicit full-boundary zero-event wording, not merely 'no income'."""

    combined = " ".join(texts).lower()
    return all(
        value in combined
        for value in ("complete cash distribution history", start, end, "no cash distributions")
    )
