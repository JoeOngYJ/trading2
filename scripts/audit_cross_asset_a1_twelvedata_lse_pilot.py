#!/usr/bin/env python3
"""Audit exact-line Twelve Data LSE pilot bytes without strategy computation."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from trading_platform.cross_asset_twelvedata_audit import (
    TwelveDataAuditError,
    canonical_json,
    sha256_file,
)
from trading_platform.cross_asset_twelvedata_lse_audit import (
    EVIDENCE_SCHEMA,
    audit_manifest_outcome,
    load_contract,
    load_public_feasibility_facts,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = REPO_ROOT / "config/experiments/cross-asset-a1-executable-universe-feasibility-v1.json"
DEFAULT_MANIFEST = REPO_ROOT / "artifacts/agent-level-experiment/cross-asset/a1-executable-universe-feasibility-v1/source-manifest.json"
DEFAULT_PUBLIC_FACTS = REPO_ROOT / "artifacts/agent-level-experiment/cross-asset/a1-executable-universe-feasibility-v1/public-feasibility-facts.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _artifact(path: Path) -> dict[str, object]:
    return {
        "bytes": path.stat().st_size,
        "path": path.resolve(strict=True).relative_to(REPO_ROOT.resolve(strict=True)).as_posix(),
        "sha256": sha256_file(path),
    }


def run(contract_path: Path, manifest_path: Path, public_facts_path: Path) -> tuple[Path, Path]:
    contract = load_contract(contract_path)
    public_facts = load_public_feasibility_facts(public_facts_path, contract)
    results, failures = audit_manifest_outcome(REPO_ROOT, manifest_path, contract)
    output_root = manifest_path.parent
    report_path = output_root / "audit-report.json"
    evidence_path = output_root / "evidence-manifest.json"
    if report_path.exists() or evidence_path.exists():
        raise TwelveDataAuditError("write-once exact LSE audit artifacts already exist")
    source_passed = not failures
    decision = "exact_lse_source_pilot_passed" if source_passed else "exact_lse_source_pilot_rejected"
    report = {
        "a1_stage_passed": False,
        "accepted_strategy_arms": [],
        "approved_execution_instruments": [],
        "audited_at": _utc_now(),
        "decision": decision,
        "economic_metrics_computed": False,
        "exact_lse_source_pilot_passed": source_passed,
        "gate_failures": failures,
        "instrument_results": results,
        "next_action": (
            "freeze_exact_lse_full_history_acquisition_and_action_reconciliation_v1"
            if source_passed
            else "select_one_broader_publicly_feasible_universe_before_any_new_data_purchase"
        ),
        "pnl_computed": False,
        "public_candidate_findings": public_facts["candidate_findings"],
        "public_feasibility_decision": public_facts["decision"],
        "public_feasibility_facts_sha256": sha256_file(public_facts_path),
        "returns_computed": False,
        "review_id": contract["review_id"],
        "sealed_2026_partition_accessed": False,
        "strategy_signals_generated": False,
    }
    report_path.write_text(canonical_json(report), encoding="utf-8")
    artifacts = [
        manifest_path,
        public_facts_path,
        report_path,
        *sorted((output_root / "raw").glob("*.json")),
    ]
    evidence = {
        "artifacts": [_artifact(path) for path in artifacts],
        "contract_sha256": sha256_file(contract_path),
        "decision": decision,
        "review_id": contract["review_id"],
        "schema_version": EVIDENCE_SCHEMA,
    }
    evidence_path.write_text(canonical_json(evidence), encoding="utf-8")
    return report_path, evidence_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit the frozen exact-line Twelve Data LSE pilot.")
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--source-manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--public-facts", type=Path, default=DEFAULT_PUBLIC_FACTS)
    args = parser.parse_args()
    try:
        report, evidence = run(args.contract, args.source_manifest, args.public_facts)
    except TwelveDataAuditError as exc:
        parser.error(str(exc))
    print(f"audit report written: {report.relative_to(REPO_ROOT)}")
    print(f"evidence manifest written: {evidence.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
