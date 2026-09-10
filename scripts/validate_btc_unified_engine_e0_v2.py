#!/usr/bin/env python3
"""Validate E0-v2 clarification and its preserved pre-E1 failure boundary."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "research/btc/contracts/btc-unified-backtest-engine-e0-v2.json"
PLAN = ROOT / "research/btc/reports/BTC_UNIFIED_BACKTEST_ENGINE_E0_V2_PLAN.md"
REVIEW = ROOT / "research/btc/reports/BTC_UNIFIED_BACKTEST_ENGINE_E0_V2_REVIEW.md"


class ValidationError(ValueError):
    pass


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError(f"duplicate key: {key}")
        result[key] = value
    return result


def canonical(value: Any, *, pretty: bool = True) -> str:
    options = {"sort_keys": True, "ensure_ascii": False, "allow_nan": False}
    if pretty:
        return json.dumps(value, indent=2, **options) + "\n"
    return json.dumps(value, separators=(",", ":"), **options)


def load(path: Path = CONTRACT) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    value = json.loads(raw, object_pairs_hook=_pairs, parse_constant=lambda value: (_ for _ in ()).throw(ValidationError(value)))
    if not isinstance(value, dict) or raw != canonical(value):
        raise ValidationError(f"noncanonical JSON: {path}")
    return value


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def validate(contract: dict[str, Any]) -> dict[str, bool]:
    require(contract.get("qualification_id") == "btc-unified-backtest-engine-e0-v2", "wrong ID")
    action = contract.get("action_boundary", {})
    require(action.get("actionable_arm_id") == "no_trade", "not fail closed")
    require(action.get("accepted_strategy_arms") == [], "accepted arm present")
    require(action.get("historical_market_rows_results_metrics_or_strategy_logic_allowed") is False, "historical access allowed")

    predecessor = contract.get("predecessor", {})
    for path_key, digest_key in (("contract_path", "contract_sha256"), ("plan_path", "plan_sha256")):
        path = ROOT / predecessor[path_key]
        require(path.is_file() and sha256_path(path) == predecessor[digest_key], "predecessor changed")
    for item in contract.get("invalid_E1_v1_draft_evidence", []):
        path = ROOT / item["path"]
        require(path.is_file() and sha256_path(path) == item["sha256"], "invalid draft evidence changed")
    require(not (ROOT / "src/trading_platform/unified_btc_accounting.py").exists(), "old source draft active")
    require(not (ROOT / "tests/test_unified_btc_accounting_e1.py").exists(), "old test draft active")

    choices = contract.get("clarifications_replacing_ambiguous_v1_wording", {})
    require(set(choices) == {
        "adverse_intrabar_mark", "atomic_pair_net_spot_and_neutralization",
        "decimal_and_quantization", "exit_cost_reserve", "initial_margin",
        "liquidation_cost", "partial_collateral_release", "terminal_execution",
    }, "clarification set changed")
    require("pre_reduction" in choices["partial_collateral_release"]["denominator"], "release denominator open")
    require("additive" in choices["initial_margin"]["method"], "initial margin method open")
    require(choices["liquidation_cost"]["ordinary_close_commission"] == "not_charged", "liquidation cost open")
    require("reconciliation_tolerance_only" in choices["decimal_and_quantization"]["universal_quote_quantum_role"], "quantum role open")
    require(choices["adverse_intrabar_mark"]["long_perpetual"] == "interval_low_first", "long adverse mark open")
    require(choices["adverse_intrabar_mark"]["short_perpetual"] == "interval_high_first", "short adverse mark open")
    require("increases_absolute" in choices["terminal_execution"]["prohibited"], "terminal increase allowed")
    require("actual_BTC_inventory" in choices["atomic_pair_net_spot_and_neutralization"]["net_spot_quantity"], "pair net spot open")
    return {
        "active_ambiguous_draft_absent": True,
        "all_eight_clarifications_exact": True,
        "canonical_contract": True,
        "invalid_draft_evidence_verified": True,
        "no_trade_boundary": True,
        "predecessor_verified": True,
    }


def qualify(output: Path) -> dict[str, Any]:
    output = output.resolve()
    require(not output.exists(), "output exists")
    contract = load()
    gates = validate(contract)
    require(PLAN.is_file() and REVIEW.is_file(), "plan/review missing")
    output.mkdir(parents=True)
    report = {
        "actionable_arm_id": "no_trade",
        "contract_sha256": sha256_path(CONTRACT),
        "decision": "e0_v2_passed_fresh_E1_synthetic_only_permitted",
        "gates": gates,
        "historical_market_rows_or_strategy_results_accessed": 0,
        "next_permitted_phase": "fresh_E1_Decimal_kernel_and_synthetic_tests_only",
        "plan_sha256": sha256_path(PLAN),
        "qualification_id": contract["qualification_id"],
        "review_sha256": sha256_path(REVIEW),
    }
    report_path = output / "qualification-report.json"
    report_path.write_text(canonical(report), encoding="utf-8")
    files = (CONTRACT, PLAN, REVIEW, Path(__file__), report_path)
    manifest = {
        "actionable_arm_id": "no_trade",
        "artifacts": [
            {"path": str(path.relative_to(ROOT)), "sha256": sha256_path(path), "size_bytes": path.stat().st_size}
            for path in files
        ],
        "decision": report["decision"],
        "qualification_id": contract["qualification_id"],
    }
    (output / "evidence-manifest.json").write_text(canonical(manifest), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(canonical(qualify(args.output), pretty=False))


if __name__ == "__main__":
    main()
