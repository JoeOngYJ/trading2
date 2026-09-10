#!/usr/bin/env python3
"""Record the no-download OANDA source successor after the frozen 2005 oil gap."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from trading_platform.cross_asset_oanda_audit import (
    build_successor_report,
    canonical_json,
    load_successor_contract,
    sha256_file,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = REPO_ROOT / "config/experiments/cross-asset-a1-oanda-source-pilot-v2.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    args = parser.parse_args()
    contract = load_successor_contract(args.contract, REPO_ROOT)
    artifact_root = REPO_ROOT / contract["changes_from_predecessor"]["output_artifact_root"]
    if artifact_root.exists():
        raise SystemExit("refusing to replace immutable OANDA successor evidence")
    report = build_successor_report(contract, REPO_ROOT)
    artifact_root.mkdir(parents=True)
    report_path = artifact_root / "audit-report.json"
    report_path.write_text(canonical_json(report), encoding="utf-8")
    evidence = {
        "a1_stage_passed": False,
        "artifacts": [
            {
                "path": str(args.contract.relative_to(REPO_ROOT)),
                "sha256": sha256_file(args.contract),
            },
            {
                "path": str(report_path.relative_to(REPO_ROOT)),
                "sha256": sha256_file(report_path),
            },
        ],
        "decision": report["decision"],
        "experiment_id": contract["experiment_id"],
        "generated_at": utc_now(),
        "new_provider_requests": 0,
        "qualified_for_strategy_evaluation": False,
        "schema_version": "cross-asset-a1-oanda-source-successor-evidence-v1",
        "source_pilot_passed": True,
    }
    evidence_path = artifact_root / "evidence-manifest.json"
    evidence_path.write_text(canonical_json(evidence), encoding="utf-8")
    print(
        json.dumps(
            {
                "decision": report["decision"],
                "new_provider_requests": 0,
                "passed_candidate_count": report["passed_candidate_count"],
                "source_pilot_passed": True,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
