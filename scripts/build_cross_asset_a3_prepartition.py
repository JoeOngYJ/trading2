#!/usr/bin/env python3
"""Build the frozen A3 timestamp-only source partitions once."""

from __future__ import annotations

import argparse
from pathlib import Path

from trading_platform.cross_asset_oanda_hourly import canonical_json
from trading_platform.cross_asset_prepartition import build_prepartitions, evidence_manifest


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "config/experiments/cross-asset-a3-timestamp-prepartition-v1.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    args = parser.parse_args()
    build_prepartitions(args.contract, ROOT)
    evidence = evidence_manifest(args.contract, ROOT)
    artifact_root = ROOT / "artifacts/agent-level-experiment/cross-asset/a3-timestamp-prepartition-v1"
    evidence_path = artifact_root / "evidence-manifest.json"
    if evidence_path.exists():
        raise ValueError("refusing to rewrite immutable A3 prepartition evidence")
    evidence_path.write_text(canonical_json(evidence), encoding="utf-8")
    print(canonical_json({"decision": evidence["decision"], "artifact": str(evidence_path)}), end="")


if __name__ == "__main__":
    main()
