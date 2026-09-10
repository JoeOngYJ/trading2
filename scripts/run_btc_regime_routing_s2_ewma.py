#!/usr/bin/env python3
"""Run the frozen S2 EWMA benchmark on immutable S1 development artifacts only."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Mapping

from trading_platform.research_evidence import load_research_partition_registry
from trading_platform.research_ledger import DAY_MS, sha256_file, write_jsonl_gzip
from trading_platform.research_program import canonical_json
from trading_platform.research_volatility import (
    EWMAConfig,
    ResearchVolatilityError,
    allocations_for_opportunities,
    build_ewma_observations,
    check_planned_risk,
    coverage_report,
    forecast_diagnostics,
    leave_one_year_out,
    load_candles,
    load_daily_features,
    load_opportunities,
    matched_allocation,
    neutralize_best_relative_months,
    paired_month_bootstrap,
    parse_utc_ms,
    segmented_participation_opportunities,
    simulate_locked_cohorts,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = REPO_ROOT / "artifacts/agent-level-experiment/btc-regime-routing"
DEFAULT_CONTRACT = REPO_ROOT / "config/experiments/btc-regime-routing-s2-ewma-v1.json"


def require_exact_path(path: Path, expected: Path, label: str) -> Path:
    actual = path.resolve(strict=True)
    frozen = expected.resolve(strict=True)
    if actual != frozen:
        raise ValueError(f"{label} differs from frozen path: {actual}")
    if path.is_symlink():
        raise ValueError(f"symlinked {label} is prohibited")
    return actual


def require_output(path: Path) -> Path:
    root = ARTIFACT_ROOT.resolve(strict=False)
    output = path.resolve(strict=False)
    try:
        output.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"output escapes isolated routing artifact root: {output}") from exc
    if output.exists() and any(output.iterdir()):
        raise ValueError(f"refusing to overwrite non-empty output directory: {output}")
    return output


def load_canonical(path: Path, label: str) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    payload = json.loads(raw)
    if raw != canonical_json(payload):
        raise ValueError(f"{label} is not canonical JSON")
    return payload


def exact_fixed_parity(actual: Mapping[str, Any], expected: Mapping[str, Any], label: str) -> None:
    mapping = {
        "cagr": "cagr",
        "calmar": "calmar",
        "active_position_time_fraction": "exposure_fraction",
        "maximum_drawdown_fraction": "maximum_drawdown_fraction",
        "mean_net_trade_bps": "mean_net_trade_bps",
        "net_return": "net_return",
        "profit_factor": "profit_factor",
        "trade_count": "trade_count",
    }
    differences: dict[str, dict[str, Any]] = {}
    for actual_key, expected_key in mapping.items():
        left = actual[actual_key]
        right = expected[expected_key]
        equal = left == right
        if isinstance(left, float) and isinstance(right, (float, int)):
            equal = math.isclose(left, float(right), rel_tol=0, abs_tol=1e-12)
        if not equal:
            differences[actual_key] = {"actual": left, "expected": right}
    if differences:
        raise ResearchVolatilityError(f"{label} S1 parity mismatch: {differences}")


def compact_summary(result: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in result.items() if key not in {"daily_returns", "trades"}}


def tail_gate(primary: Mapping[str, Any], fixed: Mapping[str, Any], fraction: float) -> bool:
    drawdown = primary["maximum_drawdown_fraction"] <= (1 - fraction) * fixed[
        "maximum_drawdown_fraction"
    ]
    primary_rolling = primary["worst_rolling_90_day_return"]
    fixed_rolling = fixed["worst_rolling_90_day_return"]
    rolling = (
        primary_rolling is not None
        and fixed_rolling is not None
        and fixed_rolling < 0
        and primary_rolling >= (1 - fraction) * fixed_rolling
    )
    return drawdown or rolling


def economic_scenario_gates(
    primary: Mapping[str, Any],
    fixed: Mapping[str, Any],
    neutralized: Mapping[str, Any],
    scorecard: Mapping[str, Any],
) -> dict[str, bool]:
    retention = scorecard["minimum_fixed_cagr_retention_fraction"]
    calmar_improvement = scorecard["minimum_calmar_improvement_fraction"]
    tail_improvement = scorecard[
        "maximum_drawdown_or_worst_rolling_90_day_loss_improvement_fraction_minimum"
    ]
    fixed_cagr = fixed["cagr"]
    fixed_calmar = fixed["calmar"]
    primary_calmar = primary["calmar"]
    neutral_fixed = neutralized["fixed"]
    neutral_primary = neutralized["primary"]
    return {
        "cagr_retention": fixed_cagr > 0 and primary["cagr"] / fixed_cagr >= retention,
        "calmar_improvement": fixed_calmar is not None
        and primary_calmar is not None
        and primary_calmar >= (1 + calmar_improvement) * fixed_calmar,
        "net_return_positive": primary["net_return"] > 0,
        "neutralized_cagr_retention": neutral_fixed["cagr"] > 0
        and neutral_primary["cagr"] / neutral_fixed["cagr"] >= retention,
        "neutralized_calmar_improvement": neutral_fixed["calmar"] is not None
        and neutral_primary["calmar"] is not None
        and neutral_primary["calmar"] >= (1 + calmar_improvement) * neutral_fixed["calmar"],
        "neutralized_net_return_positive": neutral_primary["net_return"] > 0,
        "neutralized_tail_improvement": neutral_primary["maximum_drawdown_fraction"]
        <= (1 - tail_improvement) * neutral_fixed["maximum_drawdown_fraction"],
        "tail_improvement": tail_gate(primary, fixed, tail_improvement),
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    contract_path = require_exact_path(args.contract, DEFAULT_CONTRACT, "S2 contract")
    contract = load_canonical(contract_path, "S2 contract")
    if (
        contract.get("schema_version") != "regime-routing-s2-ewma-contract-v1"
        or contract.get("experiment_id") != "btc-regime-routing-s2-ewma-v1"
        or contract.get("stage_id") != "S2"
        or contract.get("status") != "frozen"
    ):
        raise ValueError("exact frozen S2 contract is required")
    isolation = contract["isolation"]
    if any(value is not False for key, value in isolation.items() if key.endswith("_allowed")):
        raise ValueError("S2 isolation boundary enables prohibited access")
    if contract["action_mapping"]["actionable_arm_id"] != "no_trade":
        raise ValueError("S2 actionable route is not locked to no_trade")

    data = contract["data"]
    boundary_path = require_exact_path(
        REPO_ROOT / data["evidence_boundary_path"],
        REPO_ROOT / data["evidence_boundary_path"],
        "S2 evidence boundary",
    )
    if sha256_file(boundary_path) != data["evidence_boundary_sha256"]:
        raise ValueError("S2 evidence-boundary checksum mismatch")
    registry = load_research_partition_registry(boundary_path)
    registry.require_access(
        "btc-development-2017-2025-consumed",
        "risk_benchmark_development",
        __import__("datetime").datetime.fromisoformat(
            contract["frozen_at"].replace("Z", "+00:00")
        ),
    )
    if registry.clean_unseen_partition_ids():
        raise ValueError("S2 must not declare a clean unseen partition")

    source_root = (REPO_ROOT / data["s1_source_root"]).resolve(strict=True)
    source_specs = data["s1_source_artifacts"]
    resolved_inputs: dict[str, Path] = {}
    for name, metadata in source_specs.items():
        path = source_root / name
        resolved_inputs[name] = require_exact_path(path, path, f"S1 artifact {name}")
        if sha256_file(path) != metadata["sha256"]:
            raise ValueError(f"S1 artifact checksum mismatch: {name}")
    s1_manifest = load_canonical(resolved_inputs["manifest.json"], "S1 manifest")
    if s1_manifest.get("holdout_accessed") is not False:
        raise ValueError("S1 lineage does not preserve the holdout")
    for name, metadata in source_specs.items():
        if name in {"manifest.json", "breakout-reproduction-report.json"}:
            continue
        recorded = s1_manifest["artifacts"].get(name)
        if recorded is None or recorded["sha256"] != metadata["sha256"]:
            raise ValueError(f"S1 manifest lineage mismatch: {name}")

    features_spec = source_specs["features-1d.jsonl.gz"]
    candle_spec = source_specs["candles-5m.jsonl.gz"]
    trade_spec = source_specs["breakout-trades.jsonl.gz"]
    features = load_daily_features(
        resolved_inputs["features-1d.jsonl.gz"],
        features_spec["sha256"],
        features_spec["expected_rows"],
    )
    candles = load_candles(
        resolved_inputs["candles-5m.jsonl.gz"],
        candle_spec["sha256"],
        candle_spec["expected_rows"],
    )
    scenario_ids = contract["parameters"]["execution_scenario_ids"]
    opportunities, inferred_costs = load_opportunities(
        resolved_inputs["breakout-trades.jsonl.gz"],
        trade_spec["sha256"],
        trade_spec["expected_rows"],
        scenario_ids,
        contract["validity_gates"]["s1_expected_filled_opportunities_per_cost_scenario"],
        candles,
    )
    s1_report = load_canonical(
        resolved_inputs["breakout-reproduction-report.json"], "S1 reproduction report"
    )
    side_costs = {
        scenario_id: float(s1_report["scenarios"][scenario_id]["side_cost_bps"])
        for scenario_id in scenario_ids
    }
    for scenario_id in scenario_ids:
        if not math.isclose(
            inferred_costs[scenario_id], side_costs[scenario_id], rel_tol=0, abs_tol=1e-9
        ):
            raise ValueError(f"S1 cost lineage mismatch: {scenario_id}")

    parameters = contract["parameters"]
    configs = [
        EWMAConfig(
            variant_id=contract["robustness"]["primary_variant_id"],
            decay_lambda=parameters["daily_decay_lambda"],
            target_annualized_volatility=parameters["target_annualized_volatility"],
            annualization_days=parameters["annualization_days"],
            initialization_returns=contract["initialization"]["minimum_returns"],
        )
    ]
    configs.extend(
        EWMAConfig(
            variant_id=item["variant_id"],
            decay_lambda=item["daily_decay_lambda"],
            target_annualized_volatility=item["target_annualized_volatility"],
            annualization_days=parameters["annualization_days"],
            initialization_returns=contract["initialization"]["minimum_returns"],
        )
        for item in contract["robustness"]["non_selectable_one_at_a_time_diagnostics"]
    )
    observations = {config.variant_id: build_ewma_observations(features, config) for config in configs}
    max_age_ms = parameters["forecast_maximum_age_hours_exclusive"] * 60 * 60 * 1000
    allocations = {
        config.variant_id: allocations_for_opportunities(
            opportunities,
            observations[config.variant_id],
            base_allocation=parameters["base_allocation_fraction"],
            max_age_ms=max_age_ms,
        )
        for config in configs
    }
    primary_id = contract["robustness"]["primary_variant_id"]
    coverage = coverage_report(opportunities, allocations[primary_id])
    coverage_gates = {
        "annual": all(
            item["coverage"]
            >= contract["validity_gates"]["minimum_opportunity_coverage_each_calendar_year"]
            for item in coverage["annual"].values()
        ),
        "overall": coverage["overall"]
        >= contract["validity_gates"]["minimum_opportunity_coverage_overall"],
    }
    output = require_output(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, dict[str, Any]] = {}
    artifacts["ewma-observations.jsonl.gz"] = write_jsonl_gzip(
        output / "ewma-observations.jsonl.gz",
        (
            item.as_dict()
            for config in configs
            for item in observations[config.variant_id]
        ),
    )
    artifacts["opportunity-allocations.jsonl.gz"] = write_jsonl_gzip(
        output / "opportunity-allocations.jsonl.gz",
        (
            item
            for config in configs
            for item in allocations[config.variant_id]
        ),
    )

    evaluation_start_ms = parse_utc_ms(data["evaluation_start"])
    evaluation_end_ms = parse_utc_ms(data["evaluation_end_exclusive"])
    report: dict[str, Any] = {
        "actionable_arm_id": "no_trade",
        "contract_sha256": sha256_file(contract_path),
        "coverage": coverage,
        "coverage_gates": coverage_gates,
        "development_overlay_gate_met": False,
        "evidence_classification": "consumed_development_only",
        "experiment_id": contract["experiment_id"],
        "holdout_accessed": False,
        "hmm_or_jump_model_fitted": False,
        "promotion_evidence": False,
        "schema_version": "btc-regime-routing-s2-report-v1",
    }
    trade_rows: list[dict[str, Any]] = []
    if not all(coverage_gates.values()):
        report["decision"] = "s2_rejected_insufficient_risk_coverage"
        report["forecast_diagnostics"] = None
        report["simulations"] = None
    else:
        diagnostics = forecast_diagnostics(
            observations[primary_id],
            candles,
            evaluation_start_ms=evaluation_start_ms,
            evaluation_end_ms=evaluation_end_ms,
            horizons_days=contract["forecast_evaluation"]["horizons_days"],
        )
        report["forecast_diagnostics"] = diagnostics
        primary_allocations = [float(item["allocation_fraction"]) for item in allocations[primary_id]]
        exposure_match = matched_allocation(opportunities, allocations[primary_id])
        planned_risk = {
            scenario_id: check_planned_risk(
                parameters["maximum_allocation_fraction"]
                if "maximum_allocation_fraction" in parameters
                else contract["validity_gates"]["maximum_allocation_fraction"],
                parameters["protective_stop_fraction"],
                side_costs[scenario_id] * 2,
                parameters["maximum_planned_risk_fraction"],
            )
            for scenario_id in scenario_ids
        }
        simulations: dict[str, dict[str, Any]] = {}
        full_results: dict[str, dict[str, dict[str, Any]]] = {}
        participation = segmented_participation_opportunities(
            candles, evaluation_start_ms, evaluation_end_ms
        )
        participation_allocations = allocations_for_opportunities(
            participation,
            observations[primary_id],
            base_allocation=parameters["base_allocation_fraction"],
            max_age_ms=max_age_ms,
        )
        for scenario_id in scenario_ids:
            cost = side_costs[scenario_id]
            controls: dict[str, tuple[list[Any], list[float]]] = {
                "fixed_10_percent_breakout": (
                    opportunities,
                    [parameters["base_allocation_fraction"]] * len(opportunities),
                ),
                "primary_ewma_scaled_breakout": (opportunities, primary_allocations),
                "constant_capital_time_matched_breakout": (
                    opportunities,
                    [exposure_match] * len(opportunities),
                ),
                "fixed_10_percent_segmented_btc_participation": (
                    participation,
                    [parameters["base_allocation_fraction"]] * len(participation),
                ),
                "primary_ewma_scaled_segmented_btc_participation": (
                    participation,
                    [float(item["allocation_fraction"]) for item in participation_allocations],
                ),
            }
            for config in configs[1:]:
                controls[f"diagnostic_{config.variant_id}"] = (
                    opportunities,
                    [
                        float(item["allocation_fraction"])
                        for item in allocations[config.variant_id]
                    ],
                )
            scenario_results: dict[str, dict[str, Any]] = {}
            full_results[scenario_id] = {}
            for control_id, (cohorts, cohort_allocations) in controls.items():
                result = simulate_locked_cohorts(
                    candles,
                    cohorts,
                    cohort_allocations,
                    side_cost_bps=cost,
                    evaluation_start_ms=evaluation_start_ms,
                    evaluation_end_ms=evaluation_end_ms,
                )
                full_results[scenario_id][control_id] = result
                scenario_results[control_id] = compact_summary(result)
                trade_rows.extend(
                    {"control_id": control_id, "scenario_id": scenario_id, **trade}
                    for trade in result["trades"]
                )
            fixed = full_results[scenario_id]["fixed_10_percent_breakout"]
            exact_fixed_parity(fixed, s1_report["scenarios"][scenario_id], scenario_id)
            if scenario_id == scenario_ids[0]:
                buy_hold = full_results[scenario_id][
                    "fixed_10_percent_segmented_btc_participation"
                ]
                expected_buy_hold = s1_report["attribution"][
                    "segmented_btc_buy_hold_primary_cost"
                ]
                for actual_key, expected_key in (
                    ("cagr", "cagr"),
                    ("maximum_drawdown_fraction", "maximum_drawdown_fraction"),
                    ("net_return", "net_return"),
                ):
                    if not math.isclose(
                        buy_hold[actual_key], expected_buy_hold[expected_key], rel_tol=0, abs_tol=1e-12
                    ):
                        raise ResearchVolatilityError("segmented BTC control parity mismatch")
            simulations[scenario_id] = scenario_results

        report["planned_risk_fraction_at_maximum_allocation"] = planned_risk
        report["constant_capital_time_matched_allocation_fraction"] = exposure_match
        report["simulations"] = simulations
        scorecard = contract["economic_scorecard"]
        scenario_gates: dict[str, Any] = {}
        neutralized_outputs: dict[str, Any] = {}
        bootstrap_outputs: dict[str, Any] = {}
        for scenario_id in scorecard["required_cost_scenarios"]:
            fixed = full_results[scenario_id]["fixed_10_percent_breakout"]
            primary = full_results[scenario_id]["primary_ewma_scaled_breakout"]
            neutralized = neutralize_best_relative_months(
                primary["daily_returns"], fixed["daily_returns"]
            )
            neutralized_outputs[scenario_id] = neutralized
            scenario_gates[scenario_id] = economic_scenario_gates(
                primary, fixed, neutralized, scorecard
            )
            bootstrap_outputs[scenario_id] = paired_month_bootstrap(
                primary["monthly_returns"],
                fixed["monthly_returns"],
                seed=contract["statistics"]["bootstrap_seed"],
                replications=contract["statistics"]["bootstrap_replications"],
            )
        forecast_gate = (
            diagnostics["1d"]["primary_mean_qlike"]
            < diagnostics["1d"]["expanding_mean_qlike"]
        )
        report["economic_gates"] = {
            "forecast_gate": forecast_gate,
            "scenarios": scenario_gates,
        }
        report["development_overlay_gate_met"] = forecast_gate and all(
            all(values.values()) for values in scenario_gates.values()
        )
        report["best_relative_month_neutralization"] = neutralized_outputs
        report["paired_monthly_return_difference_ci95"] = bootstrap_outputs
        report["leave_one_year_out"] = {
            scenario_id: {
                "fixed": leave_one_year_out(
                    full_results[scenario_id]["fixed_10_percent_breakout"]["daily_returns"]
                ),
                "primary": leave_one_year_out(
                    full_results[scenario_id]["primary_ewma_scaled_breakout"]["daily_returns"]
                ),
            }
            for scenario_id in scorecard["required_cost_scenarios"]
        }
        report["robustness_disposition"] = {
            "parameter_replacement_allowed": False,
            "variants": [config.variant_id for config in configs[1:]],
        }
        report["decision"] = "s2_passed_benchmark_frozen"
        artifacts["simulation-trades.jsonl.gz"] = write_jsonl_gzip(
            output / "simulation-trades.jsonl.gz", trade_rows
        )

    report_path = output / "s2-ewma-report.json"
    report_path.write_text(canonical_json(report), encoding="utf-8")
    artifacts["s2-ewma-report.json"] = {
        "bytes": report_path.stat().st_size,
        "sha256": sha256_file(report_path),
    }
    manifest = {
        "actionable_arm_id": "no_trade",
        "artifacts": dict(sorted(artifacts.items())),
        "decision": report["decision"],
        "experiment_id": contract["experiment_id"],
        "holdout_accessed": False,
        "implementations": {
            "research_evidence.py": sha256_file(
                REPO_ROOT / "src/trading_platform/research_evidence.py"
            ),
            "research_volatility.py": sha256_file(
                REPO_ROOT / "src/trading_platform/research_volatility.py"
            ),
            "runner": sha256_file(Path(__file__).resolve()),
        },
        "inputs": {
            str(contract_path.relative_to(REPO_ROOT)): sha256_file(contract_path),
            str(boundary_path.relative_to(REPO_ROOT)): sha256_file(boundary_path),
            **{
                str(path.relative_to(REPO_ROOT)): sha256_file(path)
                for path in resolved_inputs.values()
            },
        },
        "model_fitted": False,
        "promotion_evidence": False,
        "schema_version": "btc-regime-routing-s2-manifest-v1",
    }
    manifest_path = output / "manifest.json"
    manifest_path.write_text(canonical_json(manifest), encoding="utf-8")
    return report


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    value.add_argument(
        "--output-dir",
        type=Path,
        default=ARTIFACT_ROOT / "s2-ewma-v1",
    )
    return value


if __name__ == "__main__":
    try:
        result = run(parser().parse_args())
    except (OSError, ValueError, KeyError, ResearchVolatilityError) as exc:
        raise SystemExit(str(exc)) from exc
    print(canonical_json(result), end="")
