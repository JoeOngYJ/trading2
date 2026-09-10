#!/usr/bin/env python3
"""Validate the repository-owned cross-asset research context."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from trading_platform.cross_asset_program import CrossAssetContextError, validate_cross_asset_context


REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--program",
        type=Path,
        default=REPO_ROOT / "config/research/cross-asset-program-v6.json",
    )
    parser.add_argument(
        "--mandate",
        type=Path,
        default=REPO_ROOT / "config/mandates/retail-cross-asset-research-v7.json",
    )
    parser.add_argument(
        "--access",
        type=Path,
        default=REPO_ROOT / "config/research/cross-asset-instrument-access-v4.json",
    )
    parser.add_argument(
        "--data-contract",
        type=Path,
        default=REPO_ROOT / "config/research/cross-asset-data-contract-v6.json",
    )
    parser.add_argument(
        "--status",
        type=Path,
        default=REPO_ROOT / "config/research/cross-asset-status-v7.json",
    )
    args = parser.parse_args()
    try:
        result = validate_cross_asset_context(
            REPO_ROOT,
            args.program,
            args.mandate,
            args.access,
            args.data_contract,
            args.status,
        )
    except CrossAssetContextError as exc:
        parser.error(str(exc))
    print(json.dumps({"decision": "context_valid", **result.as_dict()}, sort_keys=True))


if __name__ == "__main__":
    main()
