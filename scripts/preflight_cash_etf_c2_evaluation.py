#!/usr/bin/env python3
"""Fail-closed C2 preflight; never substitutes closes for required open execution prices."""

from __future__ import annotations

import json
from pathlib import Path

from trading_platform.cash_etf_pragmatic_ledger import canonical_json


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    ledger = root / "artifacts/agent-level-experiment/cash-etf/c1-pragmatic-action-ledger-v5/ledgers/spy-total-return.jsonl"
    first = json.loads(ledger.read_text(encoding="utf-8").splitlines()[0])
    required = {"open", "available_at", "total_return", "wealth_index"}
    missing = sorted(required - set(first))
    report = {
        "decision": "blocked_preflight_missing_execution_fields" if missing else "ready",
        "experiment_id": "cash-etf-c2-proxy-evaluation-v1",
        "missing_fields": missing,
        "no_close_for_open_substitution": True,
        "strategy_evaluation_run": False,
        "actionable_arm_id": "no_trade",
        "approved_execution_instruments": [],
        "schema_version": "cash-etf-c2-preflight-report-v1",
    }
    print(canonical_json(report), end="")
    raise SystemExit(2 if missing else 0)


if __name__ == "__main__":
    main()
