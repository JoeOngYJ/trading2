#!/usr/bin/env python3
"""Fail-closed validation of the offline BTC regime-routing program context."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from trading_platform.research_program import ProgramContextError, validate_program_context


REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--program",
        type=Path,
        default=REPO_ROOT / "config/research/btc-regime-routing-program-v1.json",
    )
    parser.add_argument(
        "--status",
        type=Path,
        default=REPO_ROOT / "config/research/btc-regime-routing-status-v1.json",
    )
    parser.add_argument(
        "--s0-contract",
        type=Path,
        default=REPO_ROOT / "config/experiments/btc-regime-routing-s0-v1.json",
    )
    args = parser.parse_args()
    try:
        result = validate_program_context(REPO_ROOT, args.program, args.status, args.s0_contract)
    except ProgramContextError as exc:
        parser.error(str(exc))
    print(json.dumps({"decision": "context_valid", **result.as_dict()}, sort_keys=True))


if __name__ == "__main__":
    main()
