#!/usr/bin/env python3
"""Acquire issuer-only action evidence and compare it with frozen provider rows."""

from __future__ import annotations

import hashlib
import json
import re
import urllib.request
from pathlib import Path

from trading_platform.cash_etf_actions import (
    canonical_json,
    compare_distributions,
    extract_ishares_distributions,
    load_contract,
    parse_state_street_distributions,
    read_provider_actions,
)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch(url: str, maximum_bytes: int) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "cash-etf-research/1.0 source-only-reconciliation"},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = response.read(maximum_bytes + 1)
    if len(payload) > maximum_bytes:
        raise ValueError(f"source response exceeds frozen maximum: {url}")
    return payload


def write_once(path: Path, payload: bytes) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def text_extract(payload: bytes, patterns: list[str]) -> list[str]:
    text = re.sub(r"<[^>]+>", " ", payload.decode("utf-8", errors="replace"))
    text = re.sub(r"\s+", " ", text)
    found: list[str] = []
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            found.append(match.group(0).strip())
    return found


def main() -> None:
    repo = Path(__file__).resolve().parents[1]
    successor_path = repo / "config/experiments/cash-etf-c1-official-action-reconciliation-v2.json"
    contract = load_contract(repo, successor_path)
    root = repo / contract["artifact_policy"]["artifact_root"]
    if root.exists():
        raise FileExistsError(f"artifact root already exists: {root}")
    maximum_bytes = int(contract["operational_limits"]["maximum_response_bytes"])
    start = contract["boundary"]["start_inclusive"]
    end = contract["boundary"]["end_inclusive"]
    source_manifest: list[dict[str, object]] = []
    official_distributions: dict[str, list[dict[str, str]]] = {}
    source_findings: dict[str, object] = {}

    for source in contract["source_allowlist"]:
        source_id = source["source_id"]
        url = source["url"]
        try:
            payload = fetch(url, maximum_bytes)
            record: dict[str, object] = {
                "response_bytes": len(payload),
                "response_sha256": sha256_bytes(payload),
                "source_id": source_id,
                "url": url,
            }
            if source_id == "state_street_historical_distributions":
                path = root / "sources/state-street-historical-distributions.xlsx"
                write_once(path, payload)
                record["preserved_path"] = str(path.relative_to(repo))
                record["preserved_sha256"] = sha256_file(path)
                official_distributions.update(
                    parse_state_street_distributions(payload, ["BIL", "SPY"], start, end)
                )
            elif source_id.startswith("ishares_"):
                symbol = source_id.split("_")[1].upper()
                component, events = extract_ishares_distributions(payload, symbol, start, end)
                path = root / f"sources/ishares-{symbol.lower()}-distribution-component.json"
                write_once(path, canonical_json(component).encode("utf-8"))
                record["preserved_path"] = str(path.relative_to(repo))
                record["preserved_sha256"] = sha256_file(path)
                official_distributions[symbol] = events
            elif source_id == "state_street_bil_form_8937":
                path = root / "sources/bil-2017-form-8937.pdf"
                write_once(path, payload)
                record["preserved_path"] = str(path.relative_to(repo))
                record["preserved_sha256"] = sha256_file(path)
                source_findings["BIL_split"] = {
                    "effective_date": "2017-11-30",
                    "from_factor": "1",
                    "ratio": "1_for_2_reverse_share_split",
                    "to_factor": "2",
                    "verification": "visually_verified_from_official_image_only_form_8937",
                }
            else:
                patterns: list[str]
                if source_id == "gld_issuer_filed_no_income_statement":
                    patterns = [r"GLD does not generate any income.{0,240}"]
                elif source_id == "bil_issuer_filed_split_notice":
                    patterns = [r"scheduled reverse stock split.{0,220}"]
                elif source_id.startswith("invesco_dbc"):
                    patterns = [
                        r"Return of Capital Distributions per Share.{0,220}",
                        r"Income Distributions.{0,160}",
                        r"Invesco DB Commodity Index Tracking Fund.{0,160}",
                    ]
                else:
                    patterns = []
                extracts = text_extract(payload, patterns)
                path = root / f"sources/{source_id}-action-extract.json"
                extract_payload = {
                    "extracts": extracts,
                    "response_sha256": record["response_sha256"],
                    "source_id": source_id,
                    "url": url,
                }
                write_once(path, canonical_json(extract_payload).encode("utf-8"))
                record["preserved_path"] = str(path.relative_to(repo))
                record["preserved_sha256"] = sha256_file(path)
                source_findings[source_id] = extracts
            record["status"] = "acquired"
        except Exception as exc:  # fail closed while retaining other bounded evidence
            record = {
                "error": f"{type(exc).__name__}: {exc}",
                "source_id": source_id,
                "status": "failed",
                "url": url,
            }
        source_manifest.append(record)

    input_by_symbol = {row["symbol"]: row for row in contract["inputs"]}
    results: list[dict[str, object]] = []
    for symbol in ["SPY", "EFA", "IEF", "TLT", "GLD", "DBC", "BIL"]:
        provider_dividends = read_provider_actions(
            repo / input_by_symbol[symbol]["dividends_path"], start, end
        )
        provider_splits = read_provider_actions(
            repo / input_by_symbol[symbol]["splits_path"], start, end
        )
        if symbol in official_distributions:
            distribution = compare_distributions(provider_dividends, official_distributions[symbol])
            distribution_status = "passed" if distribution["passed"] else "failed"
        elif symbol == "GLD" and not provider_dividends and source_findings.get(
            "gld_issuer_filed_no_income_statement"
        ):
            distribution = {
                "official_event_count": 0,
                "passed": True,
                "provider_event_count": 0,
                "reason": "issuer_filed_statement_says_gld_generates_no_income",
            }
            distribution_status = "passed"
        else:
            distribution = {
                "passed": False,
                "provider_event_count": len(provider_dividends),
                "reason": "complete_official_distribution_series_unavailable",
            }
            distribution_status = "unresolved"

        if symbol == "BIL":
            split_passed = (
                len(provider_splits) == 1
                and provider_splits[0].get("action_date") == "2017-11-30"
                and provider_splits[0].get("from_factor") == "1"
                and provider_splits[0].get("to_factor") == "2"
                and "BIL_split" in source_findings
            )
            split = {
                "official_event_count": 1,
                "passed": split_passed,
                "provider_event_count": len(provider_splits),
            }
            split_status = "passed" if split_passed else "failed"
        else:
            split = {
                "passed": False,
                "provider_event_count": len(provider_splits),
                "reason": "affirmative_complete_official_zero_split_history_unavailable",
            }
            split_status = "unresolved"
        instrument_passed = distribution_status == "passed" and split_status == "passed"
        results.append(
            {
                "distribution_reconciliation": distribution,
                "distribution_status": distribution_status,
                "instrument_passed": instrument_passed,
                "split_reconciliation": split,
                "split_status": split_status,
                "symbol": symbol,
            }
        )

    acquired = [row for row in source_manifest if row["status"] == "acquired"]
    report = {
        "actionable_arm_id": "no_trade",
        "approved_execution_instruments": [],
        "decision": "passed" if all(row["instrument_passed"] for row in results) else "blocked",
        "economic_metrics_computed": False,
        "experiment_id": contract["experiment_id"],
        "forbidden_market_data_preserved": False,
        "instrument_results": results,
        "numeric_ledger_built": False,
        "schema_version": "cash-etf-c1-official-action-reconciliation-report-v1",
        "source_failures": len(source_manifest) - len(acquired),
        "source_successes": len(acquired),
        "strategy_evaluation_run": False,
    }
    report_path = root / "reconciliation-report.json"
    write_once(report_path, canonical_json(report).encode("utf-8"))
    manifest_path = root / "source-manifest.json"
    write_once(
        manifest_path,
        canonical_json(
            {
                "contract_path": contract["successor_contract_path"],
                "experiment_id": contract["experiment_id"],
                "schema_version": "cash-etf-c1-official-action-source-manifest-v1",
                "sources": source_manifest,
            }
        ).encode("utf-8"),
    )
    print(canonical_json(report), end="")


if __name__ == "__main__":
    main()
