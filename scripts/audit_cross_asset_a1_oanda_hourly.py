#!/usr/bin/env python3
"""Audit and price-only normalize the immutable OANDA A1 hourly history offline."""

from __future__ import annotations

import argparse
from pathlib import Path

from trading_platform.cross_asset_oanda_hourly import (
    EVIDENCE_SCHEMA,
    canonical_json,
    audit_and_normalize,
    load_contract,
    sha256_file,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = REPO_ROOT / "config/experiments/cross-asset-a1-oanda-hourly-history-v1.json"
DEFAULT_MANDATE = REPO_ROOT / "config/mandates/retail-cross-asset-research-v6.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--mandate", type=Path, default=DEFAULT_MANDATE)
    args = parser.parse_args()
    contract = load_contract(args.contract, args.mandate, REPO_ROOT)
    root = REPO_ROOT / contract["output"]["artifact_root"]
    report_path = root / "audit-report.json"
    evidence_path = root / "evidence-manifest.json"
    if report_path.exists() or evidence_path.exists() or (root / "normalized").exists():
        raise ValueError("refusing to replace immutable hourly audit outputs")
    report = audit_and_normalize(contract, root, root / "normalized")
    report_path.write_text(canonical_json(report), encoding="utf-8")
    artifacts = [
        {"path": str(args.contract.resolve().relative_to(REPO_ROOT)), "sha256": sha256_file(args.contract)},
        {"path": str(args.mandate.resolve().relative_to(REPO_ROOT)), "sha256": sha256_file(args.mandate)},
        {"path": str((root / "source-manifest.json").relative_to(REPO_ROOT)), "sha256": sha256_file(root / "source-manifest.json")},
        {"path": str(report_path.relative_to(REPO_ROOT)), "sha256": sha256_file(report_path)},
    ]
    artifacts.extend(
        {"path": str((root / record["path"]).relative_to(REPO_ROOT)), "sha256": record["sha256"]}
        for record in report["normalized_files"]
    )
    evidence = {
        "a1_stage_passed": report["a1_stage_passed"],
        "accepted_strategy_arms": [],
        "actionable_arm_id": "no_trade",
        "approved_execution_instruments": [],
        "artifacts": artifacts,
        "decision": report["decision"],
        "experiment_id": contract["experiment_id"],
        "qualified_for_strategy_evaluation": report["qualified_for_strategy_evaluation"],
        "returns_or_pnl_computed": False,
        "schema_version": EVIDENCE_SCHEMA,
        "sealed_2026_price_accessed": False,
    }
    evidence_path.write_text(canonical_json(evidence), encoding="utf-8")
    print(canonical_json({"decision": report["decision"], "passed_candidate_count": report["passed_candidate_count"]}), end="")


if __name__ == "__main__":
    main()
