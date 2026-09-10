#!/usr/bin/env python3
"""Build immutable cash-ETF C1 timestamp-only partitions."""

from __future__ import annotations

import json
from pathlib import Path

from trading_platform.cash_etf_prepartition import build_prepartitions, write_evidence_manifest


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    contract = root / "config/experiments/cash-etf-c1-prepartition-v1.json"
    manifest = build_prepartitions(contract, root)
    evidence = write_evidence_manifest(contract, root)
    print(
        json.dumps(
            {
                "decision": evidence["decision"],
                "partition_files": len(manifest["partitions"]),
                "source_qualification_blocker": evidence["source_qualification_blocker"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
