#!/usr/bin/env python3
"""Audit the immutable OANDA A1 source responses without computing returns."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from trading_platform.cross_asset_oanda_audit import (
    EVIDENCE_SCHEMA,
    build_audit_report,
    canonical_json,
    load_contract,
    sha256_file,
    validate_source_manifest,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = REPO_ROOT / "config/experiments/cross-asset-a1-oanda-source-pilot-v1.json"
DEFAULT_MANDATE = REPO_ROOT / "config/mandates/retail-cross-asset-research-v5.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--mandate", type=Path, default=DEFAULT_MANDATE)
    args = parser.parse_args()

    contract = load_contract(args.contract, args.mandate)
    artifact_root = REPO_ROOT / contract["output"]["artifact_root"]
    validate_source_manifest(contract, artifact_root)
    report_path = artifact_root / "audit-report.json"
    evidence_path = artifact_root / "evidence-manifest.json"
    if report_path.exists() or evidence_path.exists():
        raise SystemExit("refusing to replace immutable OANDA audit evidence")
    report = build_audit_report(contract, artifact_root / "raw")
    report_path.write_text(canonical_json(report), encoding="utf-8")
    evidence = {
        "a1_stage_passed": False,
        "artifacts": [
            {
                "path": str(args.contract.relative_to(REPO_ROOT)),
                "sha256": sha256_file(args.contract),
            },
            {
                "path": str(args.mandate.relative_to(REPO_ROOT)),
                "sha256": sha256_file(args.mandate),
            },
            {
                "path": str((artifact_root / "source-manifest.json").relative_to(REPO_ROOT)),
                "sha256": sha256_file(artifact_root / "source-manifest.json"),
            },
            {
                "path": str(report_path.relative_to(REPO_ROOT)),
                "sha256": sha256_file(report_path),
            },
        ],
        "decision": report["decision"],
        "experiment_id": contract["experiment_id"],
        "generated_at": utc_now(),
        "qualified_for_strategy_evaluation": False,
        "schema_version": EVIDENCE_SCHEMA,
        "source_pilot_passed": report["source_pilot_passed"],
    }
    evidence_path.write_text(canonical_json(evidence), encoding="utf-8")
    print(
        json.dumps(
            {
                "decision": report["decision"],
                "passed_candidate_count": report["passed_candidate_count"],
                "source_pilot_passed": report["source_pilot_passed"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
