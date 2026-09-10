"""Corrected parser and successor loader for the C1 issuer-action source gate."""

from __future__ import annotations

import json
import re
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Mapping

from trading_platform.cash_etf_actions import compare_distributions
from trading_platform.cash_etf_issuer_actions import (
    CashEtfIssuerActionError,
    extract_dbc_distribution_table,
    extract_dbc_event_detail,
    sha256_file,
)


EXPERIMENT_ID = "cash-etf-c1-issuer-action-ledger-source-v2"


def load_successor_contract(repo: Path, path: Path) -> dict[str, Any]:
    successor = json.loads(path.read_text(encoding="utf-8"))
    if successor.get("experiment_id") != EXPERIMENT_ID or successor.get("status") != "frozen":
        raise CashEtfIssuerActionError("unexpected or unfrozen successor contract")
    predecessor_record = successor["predecessor"]
    predecessor_path = repo / predecessor_record["path"]
    if sha256_file(predecessor_path) != predecessor_record["sha256"]:
        raise CashEtfIssuerActionError("issuer-action v1 contract checksum changed")
    if sha256_file(repo / predecessor_record["evidence_path"]) != predecessor_record["evidence_sha256"]:
        raise CashEtfIssuerActionError("issuer-action v1 evidence checksum changed")
    contract = json.loads(predecessor_path.read_text(encoding="utf-8"))
    contract["experiment_id"] = successor["experiment_id"]
    contract["activated_at"] = successor["activated_at"]
    contract["artifact_policy"] = dict(contract["artifact_policy"])
    contract["artifact_policy"]["artifact_root"] = successor["changes_from_predecessor"][
        "artifact_root"
    ]
    replacement = successor["changes_from_predecessor"]["source_replacement"]
    replaced = 0
    for source in contract["source_allowlist"]:
        if source["source_id"] == replacement["source_id"]:
            source["url"] = replacement["url"]
            replaced += 1
    if replaced != 1:
        raise CashEtfIssuerActionError("GLD source replacement was not unique")
    contract["successor_contract_path"] = str(path.relative_to(repo))
    return contract


def extract_explicit_zero_distribution_years(text: str) -> set[int]:
    result: set[int] = set()
    for match in re.finditer(
        r"No distributions were paid(?: to Shareholders)?(?: during| for) the "
        r"(?:year|years) ended December\s+31,?\s+([^\.]{0,90})",
        text,
        flags=re.IGNORECASE,
    ):
        result.update(int(year) for year in re.findall(r"20\d{2}", match.group(1)))
    return result


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
            amount = table.get(year, "0" if year in zero_years else "")
            if not amount:
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
    for expected in contract["frozen_dbc_expected_events"]:
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
