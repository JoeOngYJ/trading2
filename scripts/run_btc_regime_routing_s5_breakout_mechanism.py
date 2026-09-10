#!/usr/bin/env python3
"""Run the frozen S5 fixed-breakout mechanism audit on consumed development evidence."""

from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path
from typing import Any

from scripts.run_btc_regime_routing_s2_ewma import (
    load_canonical,
    require_exact_path,
    require_output,
)
from trading_platform.research_breakout_mechanism import (
    ResearchBreakoutMechanismError,
    build_directional_efficiency,
    concentration,
    eligible_random_candidates,
    fixed_seven_day_return,
    grouped_attribution,
    matched_random_control,
    month_block_efficiency_difference,
    parse_utc_ms,
    validate_candles,
)
from trading_platform.research_ledger import iter_jsonl_gzip, sha256_file, write_jsonl_gzip
from trading_platform.research_program import canonical_json
from trading_platform.research_volatility import load_candles


REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = REPO_ROOT / "artifacts/agent-level-experiment/btc-regime-routing"
BASE_CONTRACT = REPO_ROOT / "config/experiments/btc-regime-routing-s5-breakout-mechanism-v1.json"
DEFAULT_CONTRACT = REPO_ROOT / "config/experiments/btc-regime-routing-s5-breakout-mechanism-v2.json"


def resolved_contract(path: Path) -> tuple[dict[str, Any], Path]:
    amendment_path = require_exact_path(path, DEFAULT_CONTRACT, "S5 successor contract")
    amendment = load_canonical(amendment_path, "S5 successor contract")
    if (
        amendment.get("schema_version")
        != "regime-routing-s5-breakout-mechanism-contract-amendment-v1"
        or amendment.get("experiment_id") != "btc-regime-routing-s5-breakout-mechanism-v2"
        or amendment.get("status") != "frozen"
        or amendment.get("base_contract_sha256") != sha256_file(BASE_CONTRACT)
    ):
        raise ResearchBreakoutMechanismError("exact frozen S5 successor contract is required")
    base = load_canonical(BASE_CONTRACT, "S5 base contract")
    if (
        base.get("schema_version") != "regime-routing-s5-breakout-mechanism-contract-v1"
        or base.get("experiment_id") != "btc-regime-routing-s5-breakout-mechanism-v1"
        or base.get("status") != "frozen"
    ):
        raise ResearchBreakoutMechanismError("S5 base contract identity changed")
    contract = copy.deepcopy(base)
    contract["clarifications"] = amendment["clarifications"]
    contract["experiment_id"] = amendment["experiment_id"]
    contract["frozen_at"] = amendment["frozen_at"]
    contract["resolved_contract_digests"] = {
        "amendment": sha256_file(amendment_path),
        "base": sha256_file(BASE_CONTRACT),
    }
    return contract, amendment_path


def required_input(spec: dict[str, Any], label: str) -> Path:
    relative = str(spec["path"])
    path = require_exact_path(REPO_ROOT / relative, REPO_ROOT / relative, label)
    if sha256_file(path) != spec["sha256"]:
        raise ResearchBreakoutMechanismError(f"{label} checksum mismatch")
    lowered = relative.lower()
    if "holdout" in lowered or "2026-01-07" in lowered:
        raise ResearchBreakoutMechanismError(f"sealed input prohibited: {label}")
    return path


def load_rows(path: Path, expected: int, label: str) -> list[dict[str, Any]]:
    rows = list(iter_jsonl_gzip(path))
    if len(rows) != expected:
        raise ResearchBreakoutMechanismError(
            f"{label} row count mismatch: {len(rows)} != {expected}"
        )
    return rows


def run(args: argparse.Namespace) -> dict[str, Any]:
    contract, amendment_path = resolved_contract(args.contract)
    if any(
        value is not False
        for key, value in contract["isolation"].items()
        if key.endswith("_allowed")
    ):
        raise ResearchBreakoutMechanismError("S5 isolation boundary enables prohibited access")
    if contract["arm_disposition_boundary"]["acceptance_allowed"] is not False:
        raise ResearchBreakoutMechanismError("S5 consumed evidence cannot accept an arm")
    output = require_output(args.output_dir)
    specs = contract["data"]["artifacts"]
    inputs = {name: required_input(spec, f"S5 {name}") for name, spec in specs.items()}

    bars_4h = load_rows(
        inputs["candles-4h.jsonl.gz"], specs["candles-4h.jsonl.gz"]["expected_rows"], "4h"
    )
    candles_5m = load_candles(
        inputs["candles-5m.jsonl.gz"],
        specs["candles-5m.jsonl.gz"]["sha256"],
        specs["candles-5m.jsonl.gz"]["expected_rows"],
    )
    validate_candles(bars_4h, candles_5m)
    raw_trades = load_rows(
        inputs["breakout-trades.jsonl.gz"],
        specs["breakout-trades.jsonl.gz"]["expected_rows"],
        "breakout trades",
    )
    s1_report = load_canonical(inputs["breakout-reproduction-report.json"], "S1 report")
    s1_manifest = load_canonical(inputs["manifest.json"], "S1 manifest")
    if s1_report.get("holdout_accessed") or s1_manifest.get("holdout_accessed"):
        raise ResearchBreakoutMechanismError("S1 lineage reports holdout access")

    feature_rows = build_directional_efficiency(
        bars_4h,
        lookback=120,
        cutoff_history=contract["mechanism_feature"]["minimum_cutoff_history"],
    )
    features_by_ms = {int(row["decision_ms"]): row for row in feature_rows}
    enriched: list[dict[str, Any]] = []
    scenarios: dict[str, list[dict[str, Any]]] = {}
    for trade in raw_trades:
        scenario_id = str(trade["scenario_id"])
        signal_ms = int(trade["signal_ms"])
        entry_row = int(trade["entry_row"])
        if signal_ms != int(trade["entry_ms"]) or candles_5m[entry_row].open_ms != signal_ms:
            raise ResearchBreakoutMechanismError("trade decision/entry lineage changed")
        feature = features_by_ms.get(signal_ms)
        if feature is None:
            raise ResearchBreakoutMechanismError("filled breakout lacks causal efficiency")
        fixed_return = fixed_seven_day_return(candles_5m, entry_row, candles_5m[entry_row].segment)
        row = {
            **trade,
            "efficiency_class": feature["classification"],
            "efficiency_lower_cutoff": feature["lower_tercile_cutoff"],
            "efficiency_upper_cutoff": feature["upper_tercile_cutoff"],
            "efficiency_value": feature["value"],
            "fixed_7d_log_return": fixed_return,
        }
        enriched.append(row)
        scenarios.setdefault(scenario_id, []).append(row)
    expected_scenarios = set(s1_report["scenarios"])
    if set(scenarios) != expected_scenarios:
        raise ResearchBreakoutMechanismError("S1 scenario identities changed")
    for scenario_id, trades in scenarios.items():
        expected = s1_report["scenarios"][scenario_id]
        if len(trades) != int(expected["trade_count"]):
            raise ResearchBreakoutMechanismError("S1 trade-count parity mismatch")
        mean = sum(float(row["return_on_allocated"]) for row in trades) / len(trades)
        if not math.isclose(mean, float(expected["mean_net_trade_return"]), rel_tol=0, abs_tol=1e-15):
            raise ResearchBreakoutMechanismError("S1 expectancy parity mismatch")

    scenario_by_cost = {
        int(round(float(s1_report["scenarios"][scenario]["round_trip_cost_bps"]))): scenario
        for scenario in sorted(scenarios)
    }
    primary_id = scenario_by_cost[30]
    severe_id = scenario_by_cost[80]
    primary = scenarios[primary_id]
    severe = scenarios[severe_id]
    primary_valid_7d = [row for row in primary if row["fixed_7d_log_return"] is not None]
    candidates = eligible_random_candidates(
        bars_4h,
        candles_5m,
        start_ms=parse_utc_ms(contract["data"]["development_start"]),
        end_ms=parse_utc_ms(contract["data"]["development_end_exclusive"]),
    )
    random_result = matched_random_control(
        candidates,
        primary_valid_7d,
        seed=contract["controls"]["random_control_seed"],
        replications=contract["controls"]["random_control_replications"],
    )
    random_rows = random_result.pop("replication_rows")
    bootstrap = month_block_efficiency_difference(
        primary,
        seed=contract["statistics"]["month_block_bootstrap_seed"],
        replications=contract["statistics"]["month_block_bootstrap_replications"],
    )
    concentration_result = concentration(primary)
    scenario_attribution: dict[str, Any] = {}
    for scenario_id, trades in sorted(scenarios.items()):
        scenario_attribution[scenario_id] = {
            "by_calendar_year": grouped_attribution(trades, "entry_year"),
            "by_efficiency_class": grouped_attribution(trades, "efficiency_class"),
            "by_exit_reason": grouped_attribution(trades, "exit_reason"),
            "round_trip_cost_bps": s1_report["scenarios"][scenario_id]["round_trip_cost_bps"],
            "trade_count": len(trades),
        }

    high_primary = scenario_attribution[primary_id]["by_efficiency_class"].get("high")
    high_severe = scenario_attribution[severe_id]["by_efficiency_class"].get("high")
    gates = {
        "best_three_profitable_months_concentration": (
            concentration_result["best_three_profitable_months_share"] is not None
            and concentration_result["best_three_profitable_months_share"]
            <= contract["rejection_gates"]["best_three_profitable_months_share_maximum"]
        ),
        "high_efficiency_expectancy_30bps": bool(
            high_primary and float(high_primary["mean_net_trade_return"]) > 0
        ),
        "high_efficiency_expectancy_80bps": bool(
            high_severe and float(high_severe["mean_net_trade_return"]) > 0
        ),
        "high_minus_low_efficiency_ci95": bool(
            bootstrap["ci95"]
            and bootstrap["valid_replications"] >= 9500
            and float(bootstrap["difference"]) > 0
            and float(bootstrap["ci95"][0]) > 0
        ),
        "minimum_filled_breakout_entries": len(primary)
        >= contract["rejection_gates"]["minimum_filled_breakout_entries"],
        "minimum_positive_calendar_years": int(
            s1_report["scenarios"][primary_id]["positive_calendar_years"]
        )
        >= contract["rejection_gates"]["minimum_positive_calendar_years_at_30bps"],
        "random_7d_percentile": random_result["empirical_percentile"]
        >= contract["rejection_gates"]["random_7d_percentile_minimum"],
        "top_three_profitable_trades_concentration": (
            concentration_result["top_three_profitable_trades_share"] is not None
            and concentration_result["top_three_profitable_trades_share"]
            <= contract["rejection_gates"]["top_three_profitable_trades_share_maximum"]
        ),
    }
    mechanism_supported = all(gates.values())
    decision = (
        "development_mechanism_supported"
        if mechanism_supported
        else "development_mechanism_rejected"
    )
    artifacts: dict[str, dict[str, Any]] = {}
    artifacts["mechanism-features.jsonl.gz"] = write_jsonl_gzip(
        output / "mechanism-features.jsonl.gz", feature_rows
    )
    artifacts["breakout-trade-attribution.jsonl.gz"] = write_jsonl_gzip(
        output / "breakout-trade-attribution.jsonl.gz", enriched
    )
    artifacts["random-control-replications.jsonl.gz"] = write_jsonl_gzip(
        output / "random-control-replications.jsonl.gz", random_rows
    )
    report = {
        "actionable_arm_id": "no_trade",
        "arm_acceptance_allowed": False,
        "attribution": scenario_attribution,
        "concentration": concentration_result,
        "contract_sha256": sha256_file(amendment_path),
        "decision": decision,
        "evidence_classification": "consumed_development_only",
        "experiment_id": contract["experiment_id"],
        "gates": gates,
        "holdout_accessed": False,
        "market_beta_control": s1_report["attribution"],
        "mechanism_card": contract["mechanism_card"],
        "mechanism_feature_observations": len(feature_rows),
        "month_block_high_minus_low": bootstrap,
        "promotion_evidence": False,
        "random_seven_day_control": random_result,
        "schema_version": "btc-regime-routing-s5-breakout-mechanism-report-v1",
    }
    report_path = output / "s5-breakout-mechanism-report.json"
    report_path.write_text(canonical_json(report), encoding="utf-8")
    artifacts[report_path.name] = {
        "bytes": report_path.stat().st_size,
        "sha256": sha256_file(report_path),
    }
    manifest = {
        "actionable_arm_id": "no_trade",
        "arm_acceptance_allowed": False,
        "artifacts": dict(sorted(artifacts.items())),
        "decision": decision,
        "experiment_id": contract["experiment_id"],
        "holdout_accessed": False,
        "implementations": {
            "research_breakout_mechanism.py": sha256_file(
                REPO_ROOT / "src/trading_platform/research_breakout_mechanism.py"
            ),
            "runner": sha256_file(Path(__file__).resolve()),
        },
        "inputs": {
            str(BASE_CONTRACT.relative_to(REPO_ROOT)): sha256_file(BASE_CONTRACT),
            str(amendment_path.relative_to(REPO_ROOT)): sha256_file(amendment_path),
            **{
                str(path.relative_to(REPO_ROOT)): sha256_file(path)
                for path in inputs.values()
            },
        },
        "promotion_evidence": False,
        "schema_version": "btc-regime-routing-s5-breakout-mechanism-manifest-v1",
    }
    manifest_path = output / "manifest.json"
    manifest_path.write_text(canonical_json(manifest), encoding="utf-8")
    return report


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    value.add_argument(
        "--output-dir", type=Path, default=ARTIFACT_ROOT / "s5-breakout-mechanism-v1"
    )
    return value


if __name__ == "__main__":
    try:
        result = run(parser().parse_args())
    except (OSError, ValueError, KeyError, ResearchBreakoutMechanismError) as exc:
        raise SystemExit(str(exc)) from exc
    print(canonical_json(result), end="")
