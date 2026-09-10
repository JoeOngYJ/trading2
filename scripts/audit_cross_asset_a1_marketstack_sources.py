#!/usr/bin/env python3
"""Audit immutable Marketstack pilot bytes without computing returns or signals."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from trading_platform.cross_asset_marketstack_audit import (
    MarketstackAuditError,
    audit_corporate_actions,
    audit_eod,
    audit_eod_identity,
    audit_identity,
    canonical_json,
    load_contract,
    parse_json_response,
    parse_response,
    sha256_file,
    validate_source_manifest,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = (
    REPO_ROOT / "config/experiments/cross-asset-a1-marketstack-free-source-pilot-v3.json"
)
DEFAULT_MANIFEST = (
    REPO_ROOT
    / "artifacts/agent-level-experiment/cross-asset/a1-marketstack-free-source-pilot-v3/source-manifest.json"
)


def _artifact(path: Path) -> dict[str, object]:
    return {
        "bytes": path.stat().st_size,
        "path": path.resolve(strict=True).relative_to(REPO_ROOT).as_posix(),
        "sha256": sha256_file(path),
    }


def run(contract_path: Path, manifest_path: Path) -> tuple[Path, Path]:
    contract_path = contract_path.resolve(strict=True)
    manifest_path = manifest_path.resolve(strict=True)
    if contract_path != DEFAULT_CONTRACT.resolve(strict=True) or manifest_path != DEFAULT_MANIFEST.resolve(
        strict=True
    ):
        raise MarketstackAuditError("only the canonical frozen Marketstack pilot is allowed")
    contract = load_contract(contract_path, REPO_ROOT)
    indexed = validate_source_manifest(REPO_ROOT, manifest_path, contract)
    sessions = contract["boundaries"]["expected_lse_sessions"]
    start = contract["boundaries"]["pilot_start_inclusive"]
    end = contract["boundaries"]["pilot_end_inclusive"]
    results: list[dict[str, object]] = []
    for instrument in contract["instruments"]:
        ticker = instrument["ticker"]
        eod_payload = parse_response(indexed[(ticker, "eod")].read_bytes(), f"{ticker} eod")
        if contract.get("pilot_identity_source", "") == (
            "eod_name_symbol_exchange_price_currency_plus_checksummed_issuer_control"
        ):
            identity = audit_eod_identity(eod_payload, instrument)
        else:
            identity = audit_identity(
                parse_json_response(indexed[(ticker, "tickers")].read_bytes(), f"{ticker} tickers"),
                instrument,
            )
        eod = audit_eod(eod_payload, instrument, sessions)
        splits = audit_corporate_actions(
            parse_response(indexed[(ticker, "splits")].read_bytes(), f"{ticker} splits"),
            instrument,
            "splits",
            start,
            end,
        )
        dividends = audit_corporate_actions(
            parse_response(indexed[(ticker, "dividends")].read_bytes(), f"{ticker} dividends"),
            instrument,
            "dividends",
            start,
            end,
        )
        results.append(
            {
                "corporate_actions": [splits, dividends],
                "eod": eod,
                "identity": identity,
                "ticker": ticker,
            }
        )
    semantics = {
        "availability_fallback_frozen": contract["sources"]["marketstack_free"][
            "availability_fallback_frozen"
        ],
        "raw_plus_separate_corporate_actions_policy_frozen": contract["sources"][
            "marketstack_free"
        ]["raw_plus_separate_corporate_actions_policy_frozen"],
        "research_reuse_terms_documented": contract["sources"]["marketstack_free"][
            "research_reuse_terms_documented"
        ],
    }
    source_accepted = all(semantics.values())
    decision = (
        "candidate_source_accepted_for_full_history_contract"
        if source_accepted
        else "candidate_source_rejected_for_full_history_contract"
    )
    audited_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    report = {
        "a1_stage_passed": False,
        "audited_at": audited_at,
        "bulk_download_authorized": False,
        "decision": decision,
        "economic_metrics_computed": False,
        "instrument_results": results,
        "next_action": (
            "freeze_a_separate_full_history_acquisition_contract"
            if source_accepted
            else "retain_A1_blocked_and_select_a_new_source_or_document_the_missing_semantics_under_a_new_experiment_id"
        ),
        "pilot_id": contract["pilot_id"],
        "pnl_computed": False,
        "sealed_partition_accessed": False,
        "source_accepted": source_accepted,
        "strategy_signals_generated": False,
        "technical_response_checks_passed": True,
        "unresolved_non_pilot_semantics": [
            "adjusted_field_methodology",
            "exact_same_day_publication_time",
            "archival_use_after_account_termination"
        ],
    }
    output_root = manifest_path.parent
    report_path = output_root / "audit-report.json"
    evidence_path = output_root / "evidence-manifest.json"
    if report_path.exists() or evidence_path.exists():
        raise MarketstackAuditError("write-once audit artifacts already exist")
    report_path.write_text(canonical_json(report), encoding="utf-8")
    source_paths = [manifest_path, report_path, *sorted(indexed.values())]
    evidence = {
        "artifacts": [_artifact(path) for path in source_paths],
        "contract_sha256": sha256_file(contract_path),
        "decision": decision,
        "pilot_id": contract["pilot_id"],
        "schema_version": "cross-asset-a1-marketstack-evidence-manifest-v1",
    }
    evidence_path.write_text(canonical_json(evidence), encoding="utf-8")
    return report_path, evidence_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit the frozen Marketstack A1 response set.")
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--source-manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    try:
        report, evidence = run(args.contract, args.source_manifest)
    except MarketstackAuditError as exc:
        parser.error(str(exc))
    print(f"audit report written: {report.relative_to(REPO_ROOT)}")
    print(f"evidence manifest written: {evidence.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
