#!/usr/bin/env python3
"""Acquire the bounded issuer-led C1 evidence and fail closed on unresolved histories."""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
import urllib.request
from pathlib import Path

from trading_platform.cash_etf_actions import read_provider_actions
from trading_platform.cash_etf_issuer_actions import (
    audit_dbc_sources,
    canonical_json,
    document_index_proves_zero_splits,
    gld_proves_zero_distributions,
    load_contract,
    normalize_html_text,
    sha256_bytes,
    sha256_file,
    verify_frozen_inputs,
)


def fetch(url: str, maximum_bytes: int) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "text/html,application/pdf,application/xhtml+xml",
            "User-Agent": "cash-etf-research/1.0 research@example.invalid",
        },
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        payload = response.read(maximum_bytes + 1)
    if len(payload) > maximum_bytes:
        raise ValueError(f"source response exceeds frozen maximum: {url}")
    return payload


def write_once(path: Path, payload: bytes) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def source_extract(source_id: str, text: str, response_sha256: str, url: str) -> dict[str, object]:
    patterns = [
        r"No distributions were paid[^.]{0,180}\.",
        r"A distribution for the year ended December[^.]{0,320}\.",
        r"Years Ended December 31[^.]{0,650}Distributions paid to Shares[^.]{0,180}",
        r"does not generate any income[^.]{0,220}\.",
        r"The Trust Indenture provides for distributions to Shareholders in only two circumstances[^.]{0,700}",
    ]
    extracts: list[str] = []
    for pattern in patterns:
        extracts.extend(match.group(0) for match in re.finditer(pattern, text, re.IGNORECASE))
    return {
        "complete_zero_split_scope_claim": document_index_proves_zero_splits(
            text, "2009-01-02", "2023-12-31"
        ),
        "extracts": extracts[:24],
        "mentions_form_8937": "form 8937" in text.lower(),
        "response_sha256": response_sha256,
        "source_id": source_id,
        "url": url,
    }


def extract_pdf_text(payload: bytes) -> str:
    with tempfile.TemporaryDirectory(prefix="cash-etf-rule-") as temporary:
        pdf_path = Path(temporary) / "rule.pdf"
        text_path = Path(temporary) / "rule.txt"
        pdf_path.write_bytes(payload)
        completed = subprocess.run(
            ["pdftotext", "-layout", str(pdf_path), str(text_path)],
            check=False,
            capture_output=True,
            timeout=30,
        )
        if completed.returncode != 0:
            raise ValueError("unable to extract NYSE Arca rule filing text")
        return text_path.read_text(encoding="utf-8", errors="replace")


def main() -> None:
    repo = Path(__file__).resolve().parents[1]
    contract_path = repo / "config/experiments/cash-etf-c1-issuer-action-ledger-source-v1.json"
    contract = load_contract(contract_path)
    verify_frozen_inputs(repo, contract)
    root = repo / contract["artifact_policy"]["artifact_root"]
    if root.exists():
        raise FileExistsError(f"artifact root already exists: {root}")

    maximum_bytes = int(contract["operational_limits"]["maximum_response_bytes"])
    source_manifest: list[dict[str, object]] = []
    source_text: dict[str, str] = {}
    pdf_text: dict[str, str] = {}
    for source in contract["source_allowlist"]:
        source_id = source["source_id"]
        url = source["url"]
        try:
            payload = fetch(url, maximum_bytes)
            response_sha = sha256_bytes(payload)
            if source_id == "nyse_arca_rule_7_4_e_2024_filing":
                preserved = root / "sources/nyse-arca-rule-7-4-e-2024-filing.pdf"
                write_once(preserved, payload)
                pdf_text[source_id] = extract_pdf_text(payload)
            else:
                text = normalize_html_text(payload)
                source_text[source_id] = text
                extract = source_extract(source_id, text, response_sha, url)
                preserved = root / f"sources/{source_id.replace('_', '-')}-action-extract.json"
                write_once(preserved, canonical_json(extract).encode("utf-8"))
            source_manifest.append(
                {
                    "preserved_path": str(preserved.relative_to(repo)),
                    "preserved_sha256": sha256_file(preserved),
                    "response_bytes": len(payload),
                    "response_sha256": response_sha,
                    "source_id": source_id,
                    "status": "acquired",
                    "url": url,
                }
            )
        except Exception as exc:  # retain bounded partial source evidence, but fail closed
            source_manifest.append(
                {
                    "error": f"{type(exc).__name__}: {exc}",
                    "source_id": source_id,
                    "status": "failed",
                    "url": url,
                }
            )

    rule_text = pdf_text.get("nyse_arca_rule_7_4_e_2024_filing", "")
    historical_rule_verified = all(
        phrase in re.sub(r"\s+", " ", rule_text).lower()
        for phrase in (
            "rule 7.4-e. ex-dividend or ex-right dates",
            "business day preceding the record date",
            "should such record date or such closing of transfer books occur upon a day other than a business day",
        )
    )

    provider_record = contract["provider_dbc_dividends"]
    provider_dbc = read_provider_actions(
        repo / provider_record["path"],
        contract["boundary"]["start_inclusive"],
        contract["boundary"]["end_inclusive"],
    )
    try:
        dbc_audit = audit_dbc_sources(contract, source_text, provider_dbc)
        if not historical_rule_verified:
            dbc_audit["passed"] = False
            dbc_audit["reason"] = "historical_nyse_arca_ex_date_rule_not_verified"
    except Exception as exc:
        dbc_audit = {
            "passed": False,
            "reason": f"{type(exc).__name__}: {exc}",
        }

    prior_record = contract["prior_reconciliation_report"]
    prior = json.loads((repo / prior_record["path"]).read_text(encoding="utf-8"))
    prior_by_symbol = {row["symbol"]: row for row in prior["instrument_results"]}
    index_source = {
        "SPY": "state_street_spy_document_index",
        "EFA": "ishares_efa_document_index",
        "IEF": "ishares_ief_document_index",
        "TLT": "ishares_tlt_document_index",
        "GLD": "spdr_gold_document_index",
        "DBC": "invesco_dbc_document_index",
    }
    start = contract["boundary"]["start_inclusive"]
    end = contract["boundary"]["end_inclusive"]
    results: list[dict[str, object]] = []
    for symbol in ("SPY", "EFA", "IEF", "TLT", "GLD", "DBC", "BIL"):
        prior_row = prior_by_symbol[symbol]
        if symbol == "DBC":
            distribution = dbc_audit
            distribution_status = "passed" if dbc_audit.get("passed") else "unresolved"
        elif symbol == "GLD":
            proved = gld_proves_zero_distributions(
                (
                    source_text.get("gld_issuer_filed_no_income_statement", ""),
                    source_text.get("gld_2023_form_10k", ""),
                ),
                start,
                end,
            )
            distribution = {
                "passed": proved,
                "provider_event_count": 0,
                "reason": (
                    "explicit_complete_zero_distribution_history"
                    if proved
                    else "no_income_and_trust_structure_do_not_prove_full_zero_distribution_history"
                ),
            }
            distribution_status = "passed" if proved else "unresolved"
        else:
            distribution = prior_row["distribution_reconciliation"]
            distribution_status = prior_row["distribution_status"]

        if symbol == "BIL":
            split = prior_row["split_reconciliation"]
            split_status = prior_row["split_status"]
        else:
            index_id = index_source[symbol]
            proved = document_index_proves_zero_splits(source_text.get(index_id, ""), start, end)
            split = {
                "passed": proved,
                "provider_event_count": prior_row["split_reconciliation"].get(
                    "provider_event_count", 0
                ),
                "reason": (
                    "explicit_complete_zero_split_archive"
                    if proved
                    else "official_page_or_index_lacks_explicit_full_boundary_completeness"
                ),
                "source_id": index_id,
            }
            split_status = "passed" if proved else "unresolved"
        results.append(
            {
                "distribution_reconciliation": distribution,
                "distribution_status": distribution_status,
                "instrument_passed": distribution_status == "passed" and split_status == "passed",
                "split_reconciliation": split,
                "split_status": split_status,
                "symbol": symbol,
            }
        )

    report = {
        "actionable_arm_id": "no_trade",
        "approved_execution_instruments": [],
        "decision": "passed" if all(row["instrument_passed"] for row in results) else "blocked",
        "economic_metrics_computed": False,
        "experiment_id": contract["experiment_id"],
        "forbidden_market_data_preserved": False,
        "historical_nyse_arca_rule_verified": historical_rule_verified,
        "instrument_results": results,
        "numeric_ledger_built": False,
        "schema_version": "cash-etf-c1-issuer-action-ledger-source-report-v1",
        "source_failures": sum(row["status"] == "failed" for row in source_manifest),
        "source_successes": sum(row["status"] == "acquired" for row in source_manifest),
        "strategy_evaluation_run": False,
    }
    report_path = root / "reconciliation-report.json"
    write_once(report_path, canonical_json(report).encode("utf-8"))
    manifest_path = root / "source-manifest.json"
    write_once(
        manifest_path,
        canonical_json(
            {
                "contract_path": str(contract_path.relative_to(repo)),
                "experiment_id": contract["experiment_id"],
                "schema_version": "cash-etf-c1-issuer-action-ledger-source-manifest-v1",
                "sources": source_manifest,
            }
        ).encode("utf-8"),
    )

    bound_paths = [contract_path, Path(__file__), repo / "src/trading_platform/cash_etf_issuer_actions.py"]
    bound_paths.extend(path for path in sorted(root.rglob("*")) if path.is_file())
    evidence = {
        "actionable_arm_id": "no_trade",
        "approved_execution_instruments": [],
        "artifacts": [
            {"path": str(path.relative_to(repo)), "sha256": sha256_file(path)}
            for path in bound_paths
        ],
        "decision": "issuer_action_source_gate_blocked" if report["decision"] == "blocked" else "issuer_action_source_gate_passed",
        "economic_metrics_computed": False,
        "experiment_id": contract["experiment_id"],
        "forbidden_market_data_preserved": False,
        "numeric_ledger_built": False,
        "schema_version": "cash-etf-c1-issuer-action-ledger-source-evidence-v1",
        "strategy_evaluation_run": False,
    }
    write_once(root / "evidence-manifest.json", canonical_json(evidence).encode("utf-8"))
    print(canonical_json(report), end="")


if __name__ == "__main__":
    main()
