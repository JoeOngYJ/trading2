#!/usr/bin/env python3
"""Qualify the offline BTC backtest core against synthetic and frozen golden evidence."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from trading_platform.btc_backtest import (
    BtcBacktestConfig,
    BtcTradePlan,
    run_long_flat_backtest,
)
from trading_platform.execution_model import MarketRules, load_scenarios, sha256_digest
from trading_platform.research_ledger import FIVE_MINUTES_MS, SourceCandle


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "research/btc/contracts/btc-backtest-core-qualification-v1.json"
DEFAULT_OUTPUT = ROOT / "artifacts/agent-level-experiment/btc-focused/backtest-core-qualification-v1"
CORE_PATH = ROOT / "src/trading_platform/btc_backtest.py"
TEST_PATH = ROOT / "tests/test_btc_backtest_core.py"


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def exact_metric_subset(value: dict[str, Any], expected: dict[str, Any]) -> dict[str, Any]:
    return {key: value[key] for key in expected}


def import_audit(path: Path) -> dict[str, Any]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    prohibited = {"ccxt", "freqtrade", "httpx", "nats", "psycopg", "requests"}
    violations = sorted(imports.intersection(prohibited))
    return {"imports": sorted(imports), "passed": not violations, "violations": violations}


def synthetic_fixture() -> tuple[list[SourceCandle], list[BtcTradePlan], str]:
    prices = (100.0, 100.0, 101.0, 102.0, 104.0, 104.0)
    rows = [
        SourceCandle(
            segment=1,
            open_ms=index * FIVE_MINUTES_MS,
            open=price,
            high=price * 1.01,
            low=price * 0.99,
            close=price,
            base_volume=1.0,
            quote_volume=price,
            source_row=index,
        )
        for index, price in enumerate(prices)
    ]
    plans = [
        BtcTradePlan(
            plan_id="synthetic-causal-long",
            decision_ms=rows[1].open_ms,
            information_cutoff_ms=rows[1].open_ms,
            decision_price=Decimal("100"),
            entry_row=1,
            exit_decision_ms=rows[4].open_ms,
            exit_row=4,
            exit_reference_price=Decimal("104"),
            exit_reason="synthetic_time_exit",
            allocation_fraction=Decimal("0.10"),
            planned_stop_fraction=Decimal("0.04"),
        )
    ]
    digest = sha256_digest([row.as_dict() for row in rows])
    return rows, plans, digest


def qualify(contract_path: Path, output: Path) -> dict[str, Any]:
    if not output.is_absolute():
        output = (ROOT / output).resolve()
    if contract_path.resolve() != DEFAULT_CONTRACT.resolve():
        raise ValueError("exact frozen B3 contract is required")
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if (
        contract.get("qualification_id") != "btc-backtest-core-qualification-v1"
        or contract.get("status") != "frozen_before_core_implementation_and_qualification"
    ):
        raise ValueError("B3 contract identity or frozen status changed")
    if output.exists() and any(output.iterdir()):
        raise ValueError("refusing to overwrite a non-empty B3 output directory")
    output.mkdir(parents=True, exist_ok=True)

    bound_results = []
    for item in contract["bound_inputs"]:
        path = ROOT / item["path"]
        actual = sha256_path(path)
        bound_results.append({"actual_sha256": actual, **item, "passed": actual == item["sha256"]})
    bound_passed = all(item["passed"] for item in bound_results)

    breakout_path = ROOT / "artifacts/agent-level-experiment/btc-regime-routing/s1-ledger-v1/breakout-reproduction-report.json"
    breakout = json.loads(breakout_path.read_text(encoding="utf-8"))
    breakout_actual = exact_metric_subset(
        breakout["scenarios"]["candle-primary-30bps-rt-v1"],
        contract["expected_golden_controls"]["fixed_20d_10d_breakout_30bps"],
    )
    breakout_expected = contract["expected_golden_controls"]["fixed_20d_10d_breakout_30bps"]

    sma_path = ROOT / "artifacts/agent-level-experiment/btc-taker-history/btc-4h-sma-10-30-execution-model-v1-report.json"
    sma = json.loads(sma_path.read_text(encoding="utf-8"))
    sma_primary = next(
        item for item in sma["scenarios"] if item["scenario_id"] == "candle-primary-30bps-rt-v1"
    )
    sma_expected = contract["expected_golden_controls"]["sma_10_30_4h_25pct_30bps"]
    sma_actual = {
        "cagr": sma_primary["cagr"],
        "maximum_drawdown_fraction": -sma_primary["max_drawdown"],
        "net_return": sma_primary["return"],
        "profit_factor": sma_primary["profit_factor"],
        "trade_count": sma_primary["trades"],
    }

    rows, plans, fixture_digest = synthetic_fixture()
    scenarios = load_scenarios(ROOT / "config/execution_scenarios.json")
    rules = MarketRules(
        symbol="BTCUSDT",
        effective_at="synthetic-qualification-fixture",
        tick_size=Decimal("0.01"),
        step_size=Decimal("0.00001"),
        min_quantity=Decimal("0.00001"),
        min_notional=Decimal("1"),
        source="synthetic_qualification_fixture",
    )
    config = BtcBacktestConfig(
        run_id="btc-backtest-core-synthetic-qualification-v1",
        evaluation_start_ms=rows[0].open_ms,
        evaluation_end_ms=rows[-1].open_ms + FIVE_MINUTES_MS,
    )
    first = run_long_flat_backtest(
        rows,
        plans,
        config=config,
        scenario=scenarios["candle-primary-30bps-rt-v1"],
        rules=rules,
        input_digest=fixture_digest,
    )
    second = run_long_flat_backtest(
        rows,
        plans,
        config=config,
        scenario=scenarios["candle-primary-30bps-rt-v1"],
        rules=rules,
        input_digest=fixture_digest,
    )
    replay_identical = canonical_bytes(first) == canonical_bytes(second)
    import_result = import_audit(CORE_PATH)

    gates = {
        "bound_inputs_unchanged": bound_passed,
        "core_imports_offline_only": import_result["passed"],
        "golden_breakout_metrics_exact": breakout_actual == breakout_expected,
        "golden_sma_metrics_exact": sma_actual == sma_expected,
        "strategy_and_regime_evaluation_not_run": first["no_strategy_selection_or_regime_model_run"] is True,
        "synthetic_core_replay_byte_identical": replay_identical,
        "synthetic_core_trade_and_cost_accounting": first["metrics"]["trade_count"] == 1
        and Decimal(first["costs"]["total_execution_cost_quote"]) > 0,
    }
    passed = all(gates.values())
    synthetic_path = output / "synthetic-core-result.json"
    synthetic_path.write_bytes(canonical_bytes(first))
    report = {
        "accepted_strategy_arms": [],
        "actionable_arm_id": "no_trade",
        "bound_inputs": bound_results,
        "core_implementation": {"path": str(CORE_PATH.relative_to(ROOT)), "sha256": sha256_path(CORE_PATH)},
        "decision": "b3_passed_engineering_only" if passed else "b3_rejected",
        "gates": gates,
        "golden_controls": {
            "fixed_20d_10d_breakout_30bps": {"actual": breakout_actual, "expected": breakout_expected},
            "sma_10_30_4h_25pct_30bps": {"actual": sma_actual, "expected": sma_expected},
        },
        "import_audit": import_result,
        "new_strategy_outcome_evaluated": False,
        "partial_L2_or_2026_accessed": False,
        "qualification_id": contract["qualification_id"],
        "regime_model_fitted": False,
        "schema_version": "btc-backtest-core-qualification-report-v1",
        "synthetic_result": {"path": str(synthetic_path.relative_to(ROOT)), "sha256": sha256_path(synthetic_path)},
        "test_contract": {"path": str(TEST_PATH.relative_to(ROOT)), "sha256": sha256_path(TEST_PATH)},
    }
    report_path = output / "qualification-report.json"
    report_path.write_bytes(canonical_bytes(report))
    manifest = {
        "files": [
            {"path": str(path.relative_to(ROOT)), "sha256": sha256_path(path)}
            for path in (synthetic_path, report_path)
        ],
        "qualification_id": contract["qualification_id"],
    }
    manifest_path = output / "evidence-manifest.json"
    manifest_path.write_bytes(canonical_bytes(manifest))
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = qualify(args.contract, args.output)
    print(json.dumps({"decision": report["decision"], "gates": report["gates"]}, sort_keys=True))


if __name__ == "__main__":
    main()
