#!/usr/bin/env python3
"""Audit and normalize the immutable conversion-only GBP/USD source offline."""

from __future__ import annotations

import argparse
from pathlib import Path

from trading_platform.cross_asset_gbp_conversion import (
    EVIDENCE_SCHEMA,
    audit_and_normalize,
    load_contract,
)
from trading_platform.cross_asset_oanda_hourly import canonical_json, sha256_file


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--contract",
        type=Path,
        default=ROOT / "config/experiments/cross-asset-a2-gbp-conversion-source-v1.json",
    )
    parser.add_argument(
        "--mandate", type=Path, default=ROOT / "config/mandates/retail-cross-asset-research-v7.json"
    )
    args = parser.parse_args()
    contract = load_contract(args.contract, args.mandate, ROOT)
    artifact_root = ROOT / contract["output"]["artifact_root"]
    normalized = artifact_root / "normalized-gbp_usd-h1.jsonl"
    report_path = artifact_root / "audit-report.json"
    evidence_path = artifact_root / "evidence-manifest.json"
    if normalized.exists() or report_path.exists() or evidence_path.exists():
        raise ValueError("refusing to replace immutable conversion audit outputs")
    report = audit_and_normalize(contract, ROOT, artifact_root, normalized)
    report_path.write_text(canonical_json(report), encoding="utf-8")
    evidence = {
        "artifacts": [
            {"path": str(args.contract.relative_to(ROOT)), "sha256": sha256_file(args.contract)},
            {"path": str((artifact_root / "source-manifest.json").relative_to(ROOT)), "sha256": sha256_file(artifact_root / "source-manifest.json")},
            {"path": str(normalized.relative_to(ROOT)), "sha256": sha256_file(normalized)},
            {"path": str(report_path.relative_to(ROOT)), "sha256": sha256_file(report_path)},
        ],
        "decision": report["decision"],
        "eligible_as_strategy_instrument": False,
        "experiment_id": contract["experiment_id"],
        "qualified_for_gbp_conversion": report["qualified_for_gbp_conversion"],
        "returns_or_pnl_computed": False,
        "schema_version": EVIDENCE_SCHEMA,
        "sealed_2026_price_accessed": False,
    }
    evidence_path.write_text(canonical_json(evidence), encoding="utf-8")
    print(canonical_json({"decision": report["decision"], "rows": report["complete_hourly_candles"]}), end="")


if __name__ == "__main__":
    main()
