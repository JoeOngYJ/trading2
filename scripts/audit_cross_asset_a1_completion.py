#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from trading_platform.cross_asset_a1_completion import write_completion_evidence


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit frozen A1 completion evidence offline")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--contract",
        type=Path,
        default=Path("config/experiments/cross-asset-a1-completion-review-v1.json"),
    )
    parser.add_argument(
        "--facts",
        type=Path,
        default=Path(
            "artifacts/agent-level-experiment/cross-asset/a1-completion-review-v1/source-facts.json"
        ),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("artifacts/agent-level-experiment/cross-asset/a1-completion-review-v1"),
    )
    args = parser.parse_args()
    root = args.root.resolve()
    report, evidence = write_completion_evidence(
        root,
        (root / args.contract).resolve(),
        (root / args.facts).resolve(),
        (root / args.output_root).resolve(),
    )
    print(
        json.dumps(
            {
                "decision": "a1_blocked_completion_gates",
                "evidence_manifest": evidence.relative_to(root).as_posix(),
                "report": report.relative_to(root).as_posix(),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
