#!/usr/bin/env python3
"""Independent synthetic-only audit for BTC multi-horizon trend v2 T1."""

from __future__ import annotations

import hashlib
import json
import math
import sys
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from trading_platform.btc_multihorizon_trend import (
    SyntheticHour,
    ewma_daily_variance,
    funding_cashflow,
    multihorizon_score,
    seeded_control_directions,
    shocked_margin_ratio,
    simulate_synthetic,
    target_direction,
)


CONTRACT = ROOT / "research/btc/contracts/btc-multihorizon-perp-trend-v2.json"
OUTPUT = ROOT / "artifacts/agent-level-experiment/btc-focused/multihorizon-perp-trend-v2/t1"


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest


def run() -> dict[str, object]:
    if OUTPUT.exists():
        raise FileExistsError(f"refusing to overwrite immutable T1 output: {OUTPUT}")
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if contract["status"] != "frozen_before_signal_or_return_access_t1_synthetic_only":
        raise ValueError("v2 contract is not frozen for T1")
    for item in contract["bound_inputs"]:
        if sha256_path(ROOT / item["path"]) != item["sha256"]:
            raise ValueError(f"changed T1 input: {item['path']}")

    returns = [0.01] * 20 + [0.02]
    manual_variance = 0.94 * 0.0001 + 0.06 * 0.0004
    closes = [100 * math.exp(0.01 * index) for index in range(85)]
    score = multihorizon_score(closes)
    long_funding = funding_cashflow(1, Decimal("2"), Decimal("100"), Decimal("0.001"))
    short_funding = funding_cashflow(-1, Decimal("2"), Decimal("100"), Decimal("0.001"))
    long_ratio = shocked_margin_ratio(1, Decimal("1"), Decimal("100"), Decimal("100"), Decimal("75"))
    short_ratio = shocked_margin_ratio(-1, Decimal("1"), Decimal("100"), Decimal("100"), Decimal("75"))
    bars = [
        SyntheticHour(0, Decimal("100"), Decimal("100"), Decimal("100")),
        SyntheticHour(3_600_000, Decimal("100"), Decimal("100"), Decimal("100"), Decimal("0.001")),
        SyntheticHour(7_200_000, Decimal("100"), Decimal("100"), Decimal("100")),
    ]
    ledger = simulate_synthetic(bars, {0: 1, 3_600_000: -1})
    source_text = (ROOT / "src/trading_platform/btc_multihorizon_trend.py").read_text(encoding="utf-8")
    forbidden = [token for token in ("requests", "httpx", "nats", "psycopg", "freqtrade", "ccxt") if token in source_text]
    checks = {
        "contract_and_inputs_bound": True,
        "ewma_matches_independent_arithmetic": abs(ewma_daily_variance(returns) - manual_variance) < 1e-15,
        "smooth_rise_is_long": score > 0.25 and target_direction(score) == 1,
        "strict_flat_boundary": target_direction(0.25) == 0 and target_direction(-0.25) == 0,
        "positive_funding_long_pays_short_receives": long_funding == Decimal("-0.200") and short_funding == Decimal("0.200"),
        "adverse_stress_direction_correct": long_ratio == Decimal("5") and short_ratio < Decimal("2"),
        "reversal_is_two_sided_transaction": len(ledger["fills"]) == 2 and Decimal(ledger["fills"][1]["quantity_delta"]) < Decimal("-4.99"),
        "synthetic_ledger_remains_no_trade": ledger["synthetic_only"] is True and ledger["actionable_arm_id"] == "no_trade",
        "random_control_deterministic": seeded_control_directions(100) == seeded_control_directions(100),
        "no_network_database_exchange_import": not forbidden,
    }
    report = {
        "actionable_arm_id": "no_trade",
        "checks": checks,
        "decision": "t1_synthetic_implementation_passed" if all(checks.values()) else "t1_rejected",
        "experiment_id": contract["experiment_id"],
        "forbidden_import_tokens": forbidden,
        "historical_market_rows_accessed": 0,
        "historical_strategy_return_accessed": False,
        "t2_historical_run_permitted": all(checks.values()),
    }
    OUTPUT.mkdir(parents=True)
    report_path = OUTPUT / "audit-report.json"
    report_path.write_bytes(canonical_bytes(report))
    implementation = [
        ROOT / "src/trading_platform/btc_multihorizon_trend.py",
        ROOT / "research/btc/tests/test_multihorizon_perp_trend_t1.py",
        ROOT / "scripts/audit_btc_multihorizon_perp_trend_t1.py",
    ]
    manifest = {
        "actionable_arm_id": "no_trade",
        "artifacts": [{"path": str(report_path.relative_to(ROOT)), "sha256": sha256_path(report_path)}],
        "bound_contract": {"path": str(CONTRACT.relative_to(ROOT)), "sha256": sha256_path(CONTRACT)},
        "experiment_id": contract["experiment_id"],
        "implementation": [{"path": str(path.relative_to(ROOT)), "sha256": sha256_path(path)} for path in implementation],
        "no_historical_return_or_action_created": True,
        "schema_version": "btc-multihorizon-perp-trend-t1-manifest-v1",
    }
    manifest_path = OUTPUT / "evidence-manifest.json"
    manifest_path.write_bytes(canonical_bytes(manifest))
    return report


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True))
