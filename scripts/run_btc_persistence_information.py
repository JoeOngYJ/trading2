#!/usr/bin/env python3
"""Run frozen MCS3-P BTC persistence information experiment offline."""

from __future__ import annotations

import argparse
import ast
import json
import shutil
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_platform.research_persistence import (  # noqa: E402
    PersistenceResearchError,
    build_rows,
    canonical_json,
    coverage_report,
    evaluate_forecasts,
    load_candles,
    parse_utc_z,
    sha256_file,
    walk_forward_forecasts,
    write_jsonl_gzip,
)


DEFAULT_CONTRACT = ROOT / "research/btc/contracts/btc-market-condition-scores-mcs3-p-v1.json"
DEFAULT_OUTPUT = (
    ROOT
    / "artifacts/agent-level-experiment/btc-focused/market-condition-scores-mcs3-p-v1"
)
MODULE_PATH = ROOT / "src/trading_platform/research_persistence.py"
RUNNER_PATH = Path(__file__).resolve()


def _load_contract(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    contract = json.loads(raw)
    if raw != canonical_json(contract):
        raise PersistenceResearchError("MCS3-P contract is not canonical JSON")
    if (
        contract.get("experiment_id") != "btc-market-condition-scores-mcs3-p-v1"
        or contract.get("status") != "frozen_before_any_BTC_value_read"
    ):
        raise PersistenceResearchError("wrong or unfrozen MCS3-P contract")
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


def _verify_bound_inputs(contract: dict[str, Any], contract_path: Path) -> list[dict[str, Any]]:
    verified = []
    for item in contract["bound_inputs"]:
        path = ROOT / item["path"]
        actual = sha256_file(path)
        if actual != item["sha256"]:
            raise PersistenceResearchError(f"changed bound input: {item['path']}")
        verified.append({"path": item["path"], "sha256": actual})
    if sha256_file(contract_path) != sha256_file(DEFAULT_CONTRACT):
        raise PersistenceResearchError("only the frozen repository MCS3-P contract may run")
    return verified


def _import_audit() -> dict[str, Any]:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    forbidden = {
        "ccxt",
        "freqtrade",
        "httpx",
        "nats",
        "psycopg",
        "requests",
        "sqlalchemy",
    }
    violations = sorted(imports & forbidden)
    return {"imports": sorted(imports), "passed": not violations, "violations": violations}


def _all_non_decreasing(values: list[float]) -> bool:
    return all(right >= left for left, right in zip(values, values[1:], strict=False))


def run(contract_path: Path = DEFAULT_CONTRACT, output: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    contract_path = contract_path.resolve(strict=True)
    contract = _load_contract(contract_path)
    verified_inputs = _verify_bound_inputs(contract, contract_path)
    destination = _prepare_output(output)
    try:
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
        raw_rows = build_rows(candles, horizons, trailing_returns=chronology["warmup_returns"])
        forecasts: list[dict[str, Any]] = []
        coverage: dict[str, Any] = {}
        statistics: dict[str, Any] = {}
        for target in contract["targets"]:
            horizon = target["horizon"]
            coverage[horizon] = coverage_report(
                candles,
                raw_rows[horizon],
                horizon_bars=int(target["bars"]),
                evaluation_start=evaluation_start,
                evaluation_end=evaluation_end,
            )
            horizon_forecasts = walk_forward_forecasts(
                raw_rows[horizon],
                evaluation_start=evaluation_start,
                evaluation_end=evaluation_end,
                minimum_training_rows=chronology["minimum_training_rows"],
            )
            forecasts.extend(horizon_forecasts)
            statistics[horizon] = evaluate_forecasts(
                horizon_forecasts,
                replications=contract["statistics"]["month_block_bootstrap_replications"],
                seed=contract["statistics"]["month_block_bootstrap_seed"],
            )
        horizon_order = {target["horizon"]: index for index, target in enumerate(contract["targets"])}
        forecasts.sort(key=lambda row: (row["observed_at"], horizon_order[row["horizon"]]))
        forecast_spec = write_jsonl_gzip(destination / "forecasts.jsonl.gz", forecasts)

        required_years = [str(year) for year in contract["gates"]["required_evaluation_years"]]
        coverage_gate = all(
            item["overall"] >= contract["gates"]["all_horizon_coverage_overall_minimum"]
            and all(
                year in item["per_year"]
                and item["per_year"][year]["fraction"]
                >= contract["gates"]["all_horizon_per_year_coverage_minimum"]
                for year in required_years
            )
            for item in coverage.values()
        )
        primary = statistics["7d"]
        primary_coverage = coverage["7d"]
        annual = primary["annual_incremental_candidate_coefficients"]
        loo = primary["leave_one_year_out_incremental_candidate_coefficients"]
        bucket_means = [primary["quintile_forward_return_means"][str(index)] for index in range(1, 6)]
        bootstrap_objects = (
            primary["month_block_rank_ic"],
            primary["month_block_error_improvement"],
            primary["month_block_top_minus_bottom"],
        )
        gates = {
            "all_horizon_coverage": coverage_gate,
            "all_input_and_causality_checks": True,
            "primary_7d_candidate_hac_incremental_coefficient_lower_95_positive": primary[
                "expanded_regression_hac"
            ]["ci95"][2][0]
            > 0,
            "primary_7d_candidate_mse_below_benchmark": primary["candidate_mse"]
            < primary["benchmark_mse"],
            "primary_7d_candidate_rank_ic_month_block_lower_95_positive": primary[
                "month_block_rank_ic"
            ]["ci95"][0]
            > 0,
            "primary_7d_error_improvement_month_block_lower_95_positive": primary[
                "month_block_error_improvement"
            ]["ci95"][0]
            > 0,
            "primary_7d_leave_one_year_out_incremental_coefficients_all_positive": set(loo)
            == set(required_years)
            and all(value > 0 for value in loo.values()),
            "primary_7d_positive_incremental_coefficient_years_minimum": sum(
                annual.get(year, 0.0) > 0 for year in required_years
            )
            >= contract["gates"]["primary_7d_positive_incremental_coefficient_years_minimum"],
            "primary_7d_quintile_means_non_decreasing": _all_non_decreasing(bucket_means),
            "primary_7d_top_minus_bottom_month_block_lower_95_positive": primary[
                "month_block_top_minus_bottom"
            ]["ci95"][0]
            > 0,
            "required_years_present": set(annual) == set(required_years)
            and set(primary_coverage["per_year"]) == set(required_years),
            "valid_bootstrap_replications": all(
                item["valid_replications"]
                >= contract["gates"]["valid_bootstrap_replications_minimum"]
                for item in bootstrap_objects
            ),
        }
        passed = all(gates.values())
        import_audit = _import_audit()
        if not import_audit["passed"]:
            raise PersistenceResearchError("research module import isolation failed")
        report = {
            "accepted_strategy_arms": [],
            "actionable_arm_id": "no_trade",
            "bound_inputs": verified_inputs,
            "candidate": contract["candidate"],
            "coverage": coverage,
            "decision": "persistence_information_accepted_for_offline_conditioning_research"
            if passed
            else "persistence_information_rejected",
            "experiment_id": contract["experiment_id"],
            "forecast_ledger": forecast_spec,
            "gates": gates,
            "import_audit": import_audit,
            "information_gate_passed": passed,
            "market_values_used": True,
            "no_strategy_pnl_position_cost_or_execution_evaluated": True,
            "partial_ob0_or_2026_accessed": False,
            "promotion_or_live_evidence": False,
            "schema_version": "btc-market-condition-scores-mcs3-p-report-v1",
            "statistics": statistics,
        }
        report_path = destination / "report.json"
        report_path.write_text(canonical_json(report), encoding="utf-8")
        manifest = {
            "experiment_id": contract["experiment_id"],
            "files": [
                {
                    "path": str(contract_path.relative_to(ROOT)),
                    "sha256": sha256_file(contract_path),
                },
                {
                    "path": str(MODULE_PATH.relative_to(ROOT)),
                    "sha256": sha256_file(MODULE_PATH),
                },
                {
                    "path": str(RUNNER_PATH.relative_to(ROOT)),
                    "sha256": sha256_file(RUNNER_PATH),
                },
                {
                    "path": str((destination / "forecasts.jsonl.gz").relative_to(ROOT)),
                    "sha256": forecast_spec["sha256"],
                },
                {
                    "path": str(report_path.relative_to(ROOT)),
                    "sha256": sha256_file(report_path),
                },
            ],
            "information_gate_passed": passed,
            "market_values_used": True,
            "no_strategy_or_pnl": True,
            "schema_version": "btc-market-condition-scores-mcs3-p-evidence-manifest-v1",
        }
        manifest_path = destination / "evidence-manifest.json"
        manifest_path.write_text(canonical_json(manifest), encoding="utf-8")
        return report
    except Exception:
        if destination.exists() and not any(destination.iterdir()):
            shutil.rmtree(destination)
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = run(args.contract, args.output)
    print(canonical_json({"decision": report["decision"], "gates": report["gates"]}), end="")


if __name__ == "__main__":
    main()
