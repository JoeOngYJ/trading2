#!/usr/bin/env python3
"""Audit immutable Twelve Data A1 pilot bytes and write source-only evidence."""

from __future__ import annotations

import argparse
from pathlib import Path

from trading_platform.cross_asset_twelvedata_audit import (
    EVIDENCE_SCHEMA,
    TwelveDataAuditError,
    audit_manifest_outcome,
    canonical_json,
    load_contract,
    sha256_file,
    utc_now,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = (
    REPO_ROOT / "config/experiments/cross-asset-a1-twelvedata-economic-proxy-pilot-v2.json"
)
DEFAULT_MANIFEST = (
    REPO_ROOT
    / "artifacts/agent-level-experiment/cross-asset/a1-twelvedata-economic-proxy-pilot-v2/source-manifest.json"
)


def _artifact(path: Path) -> dict[str, object]:
    return {
        "bytes": path.stat().st_size,
        "path": path.resolve(strict=True).relative_to(REPO_ROOT.resolve(strict=True)).as_posix(),
        "sha256": sha256_file(path),
    }


def run(contract_path: Path, manifest_path: Path) -> tuple[Path, Path]:
    contract = load_contract(contract_path)
    results, failures = audit_manifest_outcome(REPO_ROOT, manifest_path, contract)
    output_root = manifest_path.parent
    report_path = output_root / "audit-report.json"
    evidence_path = output_root / "evidence-manifest.json"
    if report_path.exists() or evidence_path.exists():
        raise TwelveDataAuditError("write-once audit artifacts already exist")
    source_accepted = not failures
    decision = (
        "candidate_source_accepted_for_full_history_contract"
        if source_accepted
        else "candidate_source_rejected_for_full_history_contract"
    )
    report = {
        "a1_stage_passed": False,
        "audited_at": utc_now(),
        "bulk_download_authorized": False,
        "decision": decision,
        "economic_metrics_computed": False,
        "gate_failures": failures,
        "instrument_results": results,
        "next_action": (
            "freeze_a_separate_full_history_acquisition_contract_before_any_bulk_request"
            if source_accepted
            else "preserve_this_rejection_and_freeze_any_corrected_source_pilot_under_a_new_experiment_id"
        ),
        "pilot_id": contract["pilot_id"],
        "pnl_computed": False,
        "sealed_partition_accessed": False,
        "source_accepted": source_accepted,
        "strategy_signals_generated": False,
        "technical_response_checks_passed": source_accepted,
        "unresolved_full_history_contract_items": [
            "archival_use_after_subscription_termination",
            "full_history_correction_and_revision_policy",
            "all_instrument_corporate_action_completeness",
            "research_proxy_to_later_execution_instrument_mapping"
        ]
    }
    report_path.write_text(canonical_json(report), encoding="utf-8")
    source_paths = [manifest_path, report_path, *sorted((output_root / "raw").glob("*.json"))]
    evidence = {
        "artifacts": [_artifact(path) for path in source_paths],
        "contract_sha256": sha256_file(contract_path),
        "decision": report["decision"],
        "pilot_id": contract["pilot_id"],
        "schema_version": EVIDENCE_SCHEMA,
    }
    evidence_path.write_text(canonical_json(evidence), encoding="utf-8")
    return report_path, evidence_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit the frozen Twelve Data A1 response set.")
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--source-manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    try:
        report, evidence = run(args.contract, args.source_manifest)
    except TwelveDataAuditError as exc:
        parser.error(str(exc))
    print(f"audit report written: {report.relative_to(REPO_ROOT)}")
    print(f"evidence manifest written: {evidence.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
