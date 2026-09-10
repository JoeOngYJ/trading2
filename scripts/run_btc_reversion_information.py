#!/usr/bin/env python3
"""Run frozen MCS3-R completed-displacement unwind information experiment offline."""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_platform.research_persistence import (  # noqa: E402
    PersistenceResearchError,
    canonical_json,
    load_candles,
    parse_utc_z,
    sha256_file,
    write_jsonl_gzip,
)
from trading_platform.research_reversion import (  # noqa: E402
    build_displacement_rows,
    evaluate_matched_events,
    feature_coverage,
    match_completed_controls,
    matched_event_as_dict,
    select_nonoverlapping_events,
)


DEFAULT_CONTRACT = ROOT / "research/btc/contracts/btc-market-condition-scores-mcs3-r-v1.json"
DEFAULT_OUTPUT = ROOT / "artifacts/agent-level-experiment/btc-focused/market-condition-scores-mcs3-r-v1"
MODULE_PATH = ROOT / "src/trading_platform/research_reversion.py"
RUNNER_PATH = Path(__file__).resolve()


def _load_contract(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    contract = json.loads(raw)
    if raw != canonical_json(contract):
        raise PersistenceResearchError("MCS3-R contract is not canonical JSON")
    if (
        contract.get("experiment_id") != "btc-market-condition-scores-mcs3-r-v1"
        or contract.get("status") != "frozen_before_any_reversion_outcome_read"
        or contract.get("statistics", {}).get("same_exact_seed_for_every_bootstrap") is not True
    ):
        raise PersistenceResearchError("wrong or unfrozen MCS3-R contract")
    return contract


def _prepare_output(path: Path) -> Path:
    resolved = path.resolve(strict=False)
    boundary = (ROOT / "artifacts/agent-level-experiment/btc-focused").resolve(strict=True)
    try:
        resolved.relative_to(boundary)
    except ValueError as exc:
        raise PersistenceResearchError("output escapes BTC-focused artifact boundary") from exc
    if resolved.exists() and any(resolved.iterdir()):
        raise PersistenceResearchError("output directory must be absent or empty")
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _verify_inputs(contract: dict[str, Any], contract_path: Path) -> list[dict[str, str]]:
    verified = []
    for item in contract["bound_inputs"]:
        actual = sha256_file(ROOT / item["path"])
        if actual != item["sha256"]:
            raise PersistenceResearchError(f"changed bound input: {item['path']}")
        verified.append({"path": item["path"], "sha256": actual})
    if sha256_file(contract_path) != sha256_file(DEFAULT_CONTRACT):
        raise PersistenceResearchError("only the frozen repository MCS3-R contract may run")
    return verified


def _import_audit() -> dict[str, Any]:
    imports: set[str] = set()
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    forbidden = {"ccxt", "freqtrade", "httpx", "nats", "psycopg", "requests", "sqlalchemy"}
    violations = sorted(imports & forbidden)
    return {"imports": sorted(imports), "passed": not violations, "violations": violations}


def run(contract_path: Path = DEFAULT_CONTRACT, output: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    contract_path = contract_path.resolve(strict=True)
    contract = _load_contract(contract_path)
    verified = _verify_inputs(contract, contract_path)
    destination = _prepare_output(output)
    candle_input = next(
        item for item in contract["bound_inputs"] if item["path"].endswith("candles-4h.jsonl.gz")
    )
    candles = load_candles(
        ROOT / candle_input["path"], candle_input["sha256"], contract["input_contract"]["expected_rows"]
    )
    chronology = contract["chronology"]
    evaluation_start = parse_utc_z(chronology["evaluation_start"], "evaluation_start")
    evaluation_end = parse_utc_z(chronology["evaluation_end_exclusive"], "evaluation_end")
    horizons = {item["horizon"]: int(item["bars"]) for item in contract["targets"]}
    rows = build_displacement_rows(
        candles,
        horizons,
        displacement_bars=chronology["source_displacement_bars"],
        reference_observations=chronology["reference_displacement_observations"],
    )
    coverage = feature_coverage(
        candles,
        rows["4h"],
        evaluation_start=evaluation_start,
        evaluation_end=evaluation_end,
    )
    matching = contract["control_matching"]
    statistics: dict[str, Any] = {}
    ledger: list[dict[str, Any]] = []
    matched_by_horizon = {}
    for target in contract["targets"]:
        horizon = target["horizon"]
        events = select_nonoverlapping_events(
            rows[horizon],
            threshold=contract["candidate"]["absolute_event_threshold"],
            evaluation_start=evaluation_start,
            evaluation_end=evaluation_end,
        )
        matched = match_completed_controls(
            events,
            rows[horizon],
            quiet_absolute_z_maximum=contract["benchmark"]["quiet_absolute_z_maximum"],
            maximum_lookback_days=matching["maximum_lookback_days"],
            maximum_variance_ratio=matching["maximum_past_realized_variance_ratio"],
        )
        matched_by_horizon[horizon] = matched
        statistics[horizon] = evaluate_matched_events(
            matched,
            replications=contract["statistics"]["month_block_bootstrap_replications"],
            seed=contract["statistics"]["month_block_bootstrap_seed"],
        )
        ledger.extend(matched_event_as_dict(item) for item in matched)
    horizon_order = {target["horizon"]: index for index, target in enumerate(contract["targets"])}
    ledger.sort(key=lambda row: (row["observed_at"], horizon_order[row["horizon"]]))
    ledger_spec = write_jsonl_gzip(destination / "events.jsonl.gz", ledger)

    gates_spec = contract["gates"]
    required_years = [str(year) for year in gates_spec["required_evaluation_years"]]
    primary = statistics["1d"]
    event_interval = primary["event_month_block_mean_reversal"]
    delta_interval = primary["matched_event_minus_control_month_block"]
    sides = primary["side_statistics"]
    gates = {
        "all_feature_coverage": coverage["overall"] >= gates_spec["all_feature_coverage_overall_minimum"]
        and all(
            year in coverage["per_year"]
            and coverage["per_year"][year]["fraction"]
            >= gates_spec["all_feature_coverage_per_year_minimum"]
            for year in required_years
        ),
        "all_input_causality_nonoverlap_and_matching_checks": True,
        "primary_1d_both_direction_event_fractions": all(
            item["fraction"] >= gates_spec["primary_1d_both_direction_event_fractions_minimum"]
            for item in sides.values()
        ),
        "primary_1d_both_direction_mean_reversal_positive": all(
            item["mean_reversal"] is not None and item["mean_reversal"] > 0
            for item in sides.values()
        ),
        "primary_1d_event_count": primary["event_count"] >= gates_spec["primary_1d_event_count_minimum"],
        "primary_1d_event_mean_reversal_above_80bps": primary["event_mean_reversal"] * 10000
        > gates_spec["primary_1d_event_mean_reversal_bps_strictly_above"],
        "primary_1d_event_month_block_lower_above_30bps": event_interval["ci95"][0] * 10000
        > gates_spec["primary_1d_event_mean_reversal_month_block_lower_95_bps_strictly_above"],
        "primary_1d_excluding_best_three_months_positive": primary[
            "event_months_excluding_best_three_mean_reversal"
        ]
        is not None
        and primary["event_months_excluding_best_three_mean_reversal"] > 0,
        "primary_1d_matched_control_coverage": primary["matched_control_coverage"]
        >= gates_spec["primary_1d_matched_control_coverage_overall_minimum"]
        and all(
            year in primary["matched_control_coverage_by_year"]
            and primary["matched_control_coverage_by_year"][year]
            >= gates_spec["primary_1d_matched_control_coverage_per_year_minimum"]
            for year in required_years
        ),
        "primary_1d_matched_delta_month_block_lower_positive": delta_interval is not None
        and delta_interval["ci95"][0] * 10000
        > gates_spec["primary_1d_matched_event_minus_control_month_block_lower_95_bps_strictly_above"],
        "primary_1d_positive_annual_event_years": sum(
            primary["annual_event_mean_reversal"].get(year, 0.0) > 0 for year in required_years
        )
        >= gates_spec["primary_1d_positive_annual_event_mean_years_minimum"],
        "primary_1d_positive_annual_matched_delta_years": sum(
            primary["annual_matched_event_minus_control"].get(year, 0.0) > 0
            for year in required_years
        )
        >= gates_spec["primary_1d_positive_annual_matched_delta_years_minimum"],
        "primary_1d_yearly_event_count": all(
            primary["event_count_by_year"].get(year, 0)
            >= gates_spec["primary_1d_yearly_event_count_minimum"]
            for year in required_years
        ),
        "required_years_present": set(primary["event_count_by_year"]) == set(required_years),
        "valid_bootstrap_replications": event_interval["valid_replications"]
        >= gates_spec["valid_bootstrap_replications_minimum"]
        and delta_interval is not None
        and delta_interval["valid_replications"] >= gates_spec["valid_bootstrap_replications_minimum"],
    }
    import_audit = _import_audit()
    if not import_audit["passed"]:
        raise PersistenceResearchError("reversion module import isolation failed")
    passed = all(gates.values())
    report = {
        "accepted_strategy_arms": [],
        "actionable_arm_id": "no_trade",
        "bound_inputs": verified,
        "candidate": contract["candidate"],
        "decision": "reversion_information_accepted_for_offline_conditioning_research"
        if passed
        else "reversion_information_rejected",
        "event_ledger": ledger_spec,
        "experiment_id": contract["experiment_id"],
        "feature_coverage": coverage,
        "gates": gates,
        "import_audit": import_audit,
        "information_gate_passed": passed,
        "market_values_used": True,
        "no_strategy_pnl_position_cost_or_execution_evaluated": True,
        "partial_ob0_or_2026_accessed": False,
        "promotion_or_live_evidence": False,
        "schema_version": "btc-market-condition-scores-mcs3-r-report-v1",
        "statistics": statistics,
    }
    report_path = destination / "report.json"
    report_path.write_text(canonical_json(report), encoding="utf-8")
    manifest = {
        "experiment_id": contract["experiment_id"],
        "files": [
            {"path": str(contract_path.relative_to(ROOT)), "sha256": sha256_file(contract_path)},
            {"path": str(MODULE_PATH.relative_to(ROOT)), "sha256": sha256_file(MODULE_PATH)},
            {"path": str(RUNNER_PATH.relative_to(ROOT)), "sha256": sha256_file(RUNNER_PATH)},
            {
                "path": str((destination / "events.jsonl.gz").relative_to(ROOT)),
                "sha256": ledger_spec["sha256"],
            },
            {"path": str(report_path.relative_to(ROOT)), "sha256": sha256_file(report_path)},
        ],
        "information_gate_passed": passed,
        "market_values_used": True,
        "no_strategy_or_pnl": True,
        "schema_version": "btc-market-condition-scores-mcs3-r-evidence-manifest-v1",
    }
    (destination / "evidence-manifest.json").write_text(canonical_json(manifest), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = run(args.contract, args.output)
    print(canonical_json({"decision": report["decision"], "gates": report["gates"]}), end="")


if __name__ == "__main__":
    main()
