#!/usr/bin/env python3
"""Build the frozen pragmatic C1 cash-ETF total-return ledgers offline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from trading_platform.cash_etf_pragmatic_ledger import (
    CashEtfPragmaticLedgerError,
    SYMBOLS,
    build_ledger_rows,
    canonical_json,
    canonical_json_line,
    convert_ledger_to_gbp,
    load_contract,
    official_distributions,
    parse_fred_dexusuk_patch,
    read_action_rows,
    read_price_rows,
    sha256_file,
    split_candidates,
)


def write_once(path: Path, content: str) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main() -> None:
    repo = Path(__file__).resolve().parents[1]
    contract_path = repo / "config/experiments/cash-etf-c1-pragmatic-action-ledger-v5.json"
    contract = load_contract(repo, contract_path)
    artifact_root = repo / contract["artifact_policy"]["artifact_root"]
    if artifact_root.exists():
        raise FileExistsError(f"artifact root already exists: {artifact_root}")

    start = contract["boundary"]["start_inclusive"]
    end = contract["boundary"]["end_inclusive"]
    input_by_symbol = {row["symbol"]: row for row in contract["inputs"]["symbols"]}
    distributions = official_distributions(repo, contract)
    expected_counts = contract["acceptance_gates"]["distribution_event_counts"]
    if {symbol: len(distributions[symbol]) for symbol in SYMBOLS} != expected_counts:
        raise CashEtfPragmaticLedgerError("official distribution event counts changed")

    prices_by_symbol: dict[str, list[dict[str, Any]]] = {}
    post_boundary_deserialized: dict[str, int] = {}
    for symbol in SYMBOLS:
        source = input_by_symbol[symbol]
        rows, count = read_price_rows(repo / source["daily_path"], symbol, start, end)
        prices_by_symbol[symbol] = rows
        post_boundary_deserialized[symbol] = count
    reference_sessions = [row["session"] for row in prices_by_symbol["SPY"]]
    for symbol in SYMBOLS:
        if [row["session"] for row in prices_by_symbol[symbol]] != reference_sessions:
            raise CashEtfPragmaticLedgerError(f"daily session set differs from SPY: {symbol}")
    fx_input = contract["inputs"]["fx"]
    fx_rows, fx_post_boundary_deserialized = read_price_rows(
        repo / fx_input["path"], "GBP/USD", start, end, allow_null_volume=True
    )
    fx_sessions = {row["session"] for row in fx_rows}
    missing_fx_sessions = sorted(set(reference_sessions) - fx_sessions)
    patch_config = contract["fx_patch"]
    if missing_fx_sessions != sorted(patch_config["expected_dates"]):
        raise CashEtfPragmaticLedgerError(
            f"GBP/USD missing-session set changed: {missing_fx_sessions}"
        )
    request = Request(patch_config["source_url"], method=patch_config["http_method"])
    with urlopen(request, timeout=30) as response:  # noqa: S310 - frozen official HTTPS URL
        response_bytes = response.read(int(patch_config["maximum_response_bytes"]) + 1)
    patch = parse_fred_dexusuk_patch(response_bytes, patch_config)
    patch_path = artifact_root / "sources" / "fred-dexusuk-four-date-patch.json"
    write_once(patch_path, canonical_json(patch))
    fx_rows.extend(patch["rows"])
    fx_rows.sort(key=lambda row: row["session"])
    fx_sessions = {row["session"] for row in fx_rows}
    if len(fx_sessions) != len(fx_rows) or any(
        session not in fx_sessions for session in reference_sessions
    ):
        raise CashEtfPragmaticLedgerError("patched GBP/USD session set is invalid")

    split_config = contract["split_candidate_detection"]
    permitted = {
        (row["symbol"], row["date"], row["ratio"]) for row in split_config["permitted_candidates"]
    }
    split_events: dict[str, list[dict[str, Any]]] = {}
    candidate_report: dict[str, list[dict[str, str]]] = {}
    for symbol in SYMBOLS:
        source = input_by_symbol[symbol]
        provider_splits = read_action_rows(repo / source["provider_splits_path"], start, end)
        candidates = split_candidates(
            prices_by_symbol[symbol],
            split_config["candidate_ratios"],
            split_config["maximum_relative_distance"],
            split_config["minimum_absolute_return"],
        )
        candidate_report[symbol] = candidates
        if symbol == "BIL":
            if len(provider_splits) != 1:
                raise CashEtfPragmaticLedgerError("BIL exact split event missing")
            event = provider_splits[0]
            if (
                event.get("action_date") != "2017-11-30"
                or event.get("from_factor") != "1"
                or event.get("to_factor") != "2"
            ):
                raise CashEtfPragmaticLedgerError("BIL split identity changed")
            split_events[symbol] = [event]
        else:
            if provider_splits:
                raise CashEtfPragmaticLedgerError(f"unexpected provider split: {symbol}")
            split_events[symbol] = []
        for candidate in candidates:
            key = (symbol, candidate["date"], candidate["suspected_ratio"])
            if key not in permitted:
                raise CashEtfPragmaticLedgerError(
                    f"unresolved split-like discontinuity: {symbol} {candidate['date']}"
                )
        if symbol != "BIL" and source.get("document_index_path") is None:
            raise CashEtfPragmaticLedgerError(f"missing issuer document index: {symbol}")

    gld_provider = read_action_rows(
        repo / input_by_symbol["GLD"]["provider_dividends_path"], start, end
    )
    if gld_provider:
        raise CashEtfPragmaticLedgerError("GLD provider distribution file is not empty")

    ledger_paths: list[dict[str, Any]] = []
    instrument_results: list[dict[str, Any]] = []
    for symbol in SYMBOLS:
        usd_ledger = build_ledger_rows(
            symbol, prices_by_symbol[symbol], distributions[symbol], split_events[symbol]
        )
        ledger = convert_ledger_to_gbp(usd_ledger, fx_rows)
        output_path = artifact_root / "ledgers" / f"{symbol.lower()}-total-return.jsonl"
        write_once(output_path, "\n".join(canonical_json_line(row) for row in ledger) + "\n")
        relative_path = str(output_path.relative_to(repo))
        digest = sha256_file(output_path)
        ledger_paths.append({"path": relative_path, "sha256": digest})
        instrument_results.append(
            {
                "distribution_event_count": len(distributions[symbol]),
                "end_session": ledger[-1]["session"],
                "instrument_passed": True,
                "ledger_currency": "GBP",
                "ledger_path": relative_path,
                "ledger_sha256": digest,
                "post_boundary_rows_deserialized": post_boundary_deserialized[symbol],
                "row_count": len(ledger),
                "split_event_count": len(split_events[symbol]),
                "split_like_candidates": candidate_report[symbol],
                "start_session": ledger[0]["session"],
                "symbol": symbol,
            }
        )

    report = {
        "accepted_strategy_arms": [],
        "actionable_arm_id": "no_trade",
        "approved_execution_instruments": [],
        "data_purchase_performed": False,
        "decision": "passed",
        "experiment_id": contract["experiment_id"],
        "fx_post_boundary_rows_deserialized": fx_post_boundary_deserialized,
        "official_fx_patch_observation_count": len(patch["rows"]),
        "official_fx_patch_path": str(patch_path.relative_to(repo)),
        "official_fx_patch_sha256": sha256_file(patch_path),
        "instrument_results": instrument_results,
        "numeric_total_return_ledger_built": True,
        "numeric_locked_partitions_deserialized": False,
        "provider_dividends_used_for_cash_credit": False,
        "schema_version": "cash-etf-c1-pragmatic-action-ledger-report-v1",
        "strategy_evaluation_run": False,
        "whole_universe_gate_passed": True,
    }
    report_path = artifact_root / "ledger-report.json"
    write_once(report_path, canonical_json(report))

    source_manifest = {
        "contract_path": str(contract_path.relative_to(repo)),
        "experiment_id": contract["experiment_id"],
        "input_groups": contract["inputs"],
        "official_fx_patch": {
            "path": str(patch_path.relative_to(repo)),
            "sha256": sha256_file(patch_path),
        },
        "output_ledgers": ledger_paths,
        "schema_version": "cash-etf-c1-pragmatic-action-ledger-source-manifest-v1",
    }
    source_manifest_path = artifact_root / "source-manifest.json"
    write_once(source_manifest_path, canonical_json(source_manifest))

    core_artifacts = [
        contract_path,
        repo / "src/trading_platform/cash_etf_pragmatic_ledger.py",
        Path(__file__).resolve(),
        report_path,
        source_manifest_path,
        patch_path,
        *[repo / row["path"] for row in ledger_paths],
    ]
    evidence = {
        "accepted_strategy_arms": [],
        "actionable_arm_id": "no_trade",
        "approved_execution_instruments": [],
        "artifacts": [
            {"path": str(path.relative_to(repo)), "sha256": sha256_file(path)}
            for path in core_artifacts
        ],
        "data_purchase_performed": False,
        "decision": "pragmatic_action_ledger_passed",
        "experiment_id": contract["experiment_id"],
        "numeric_total_return_ledger_built": True,
        "schema_version": "cash-etf-c1-pragmatic-action-ledger-evidence-v2",
        "strategy_evaluation_run": False,
    }
    write_once(artifact_root / "evidence-manifest.json", canonical_json(evidence))
    print(canonical_json(report), end="")


if __name__ == "__main__":
    main()
