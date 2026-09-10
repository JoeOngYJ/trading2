#!/usr/bin/env python3
"""Run the frozen causal S3 Student-t HMM risk evaluation offline."""

from __future__ import annotations

import argparse
import copy
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping

from scripts.run_btc_regime_routing_s2_ewma import (
    compact_summary,
    economic_scenario_gates,
    load_canonical,
    require_exact_path,
    require_output,
)
from trading_platform.research_evidence import load_research_partition_registry
from trading_platform.research_hmm import (
    ResearchHMMError,
    build_feature_rows,
    forward_labels,
    hmm_allocations,
    load_daily_ohlc,
    month_block_state_difference,
    state_path_statistics,
    walk_forward_states,
)
from trading_platform.research_ledger import iter_jsonl_gzip, sha256_file, write_jsonl_gzip
from trading_platform.research_program import canonical_json
from trading_platform.research_volatility import (
    EWMAConfig,
    allocations_for_opportunities,
    build_ewma_observations,
    check_planned_risk,
    leave_one_year_out,
    load_candles,
    load_direct_close_features,
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
BASE_CONTRACT = REPO_ROOT / "config/experiments/btc-regime-routing-s3-student-t-hmm-v1.json"
DEFAULT_CONTRACT = REPO_ROOT / "config/experiments/btc-regime-routing-s3-student-t-hmm-v2.json"


def resolved_contract(path: Path) -> tuple[dict[str, Any], dict[str, Any], Path]:
    amendment_path = require_exact_path(path, DEFAULT_CONTRACT, "S3 successor contract")
    amendment = load_canonical(amendment_path, "S3 successor contract")
    if (
        amendment.get("schema_version")
        != "regime-routing-s3-student-t-hmm-contract-amendment-v1"
        or amendment.get("experiment_id") != "btc-regime-routing-s3-student-t-hmm-v2"
        or amendment.get("status") != "frozen"
        or amendment.get("base_contract_sha256") != sha256_file(BASE_CONTRACT)
    ):
        raise ResearchHMMError("exact frozen S3 successor contract is required")
    base = load_canonical(BASE_CONTRACT, "S3 base contract")
    if (
        base.get("schema_version") != "regime-routing-s3-student-t-hmm-contract-v1"
        or base.get("experiment_id") != "btc-regime-routing-s3-student-t-hmm-v1"
        or base.get("status") != "frozen"
    ):
        raise ResearchHMMError("S3 base contract identity changed")
    contract = copy.deepcopy(base)
    contract["experiment_id"] = amendment["experiment_id"]
    contract["frozen_at"] = amendment["frozen_at"]
    contract["clarifications"] = amendment["clarifications"]
    contract["resolved_contract_digests"] = {
        "amendment": sha256_file(amendment_path),
        "base": sha256_file(BASE_CONTRACT),
    }
    return contract, amendment, amendment_path


def required_input(path: str, digest: str, label: str) -> Path:
    value = require_exact_path(REPO_ROOT / path, REPO_ROOT / path, label)
    if sha256_file(value) != digest:
        raise ResearchHMMError(f"{label} checksum mismatch")
    lowered = str(value).lower()
    if "holdout" in lowered or "2026-01-07" in lowered:
        raise ResearchHMMError(f"sealed input prohibited: {label}")
    return value


def load_primary_s2_allocations(path: Path, opportunities: list[Any], primary_id: str) -> list[float]:
    selected = [row for row in iter_jsonl_gzip(path) if row.get("variant_id") == primary_id]
    if len(selected) != len(opportunities):
        raise ResearchHMMError("S2 primary allocation count mismatch")
    output: list[float] = []
    for opportunity, row in zip(opportunities, selected, strict=True):
        if row.get("opportunity_id") != opportunity.opportunity_id:
            raise ResearchHMMError("S2 allocation opportunity lineage mismatch")
        value = float(row["allocation_fraction"])
        if not 0 <= value <= 0.1:
            raise ResearchHMMError("S2 allocation is outside frozen bounds")
        output.append(value)
    return output


def coverage(opportunities: list[Any], allocations: list[Mapping[str, Any]]) -> dict[str, Any]:
    annual: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "usable": 0})
    reasons: dict[str, int] = defaultdict(int)
    for opportunity, row in zip(opportunities, allocations, strict=True):
        year = str(__import__("datetime").datetime.fromtimestamp(
            opportunity.signal_ms / 1000, tz=__import__("datetime").timezone.utc
        ).year)
        annual[year]["total"] += 1
        if row["unknown_reason"] is None:
            annual[year]["usable"] += 1
        else:
            reasons[str(row["unknown_reason"])] += 1
    usable = sum(item["usable"] for item in annual.values())
    return {
        "annual": {
            year: {**value, "coverage": value["usable"] / value["total"]}
            for year, value in sorted(annual.items())
        },
        "overall": usable / len(opportunities),
        "reasons": dict(sorted(reasons.items())),
        "total": len(opportunities),
        "usable": usable,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    contract, amendment, amendment_path = resolved_contract(args.contract)
    if any(
        value is not False
        for key, value in contract["isolation"].items()
        if key.endswith("_allowed")
    ):
        raise ResearchHMMError("S3 isolation boundary enables prohibited access")
    if contract["action_mapping"]["actionable_arm_id"] != "no_trade":
        raise ResearchHMMError("S3 actionable route is not locked to no_trade")
    data = contract["data"]
    boundary_path = required_input(
        data["evidence_boundary_path"], data["evidence_boundary_sha256"], "S3 boundary"
    )
    registry = load_research_partition_registry(boundary_path)
    registry.require_access(
        "btc-development-2017-2025-consumed",
        "risk_benchmark_development",
        __import__("datetime").datetime.fromisoformat(
            contract["frozen_at"].replace("Z", "+00:00")
        ),
    )
    if registry.clean_unseen_partition_ids() or data["sealed_2026_path_allowed"]:
        raise ResearchHMMError("S3 evidence boundary is unsafe")

    input_specs = {
        "daily": (
            data["daily_risk_source"]["dataset_path"],
            data["daily_risk_source"]["dataset_sha256"],
        ),
        "daily_audit": (
            data["daily_risk_source"]["audit_report_path"],
            data["daily_risk_source"]["audit_report_sha256"],
        ),
        "candles": (data["s1_candles_path"], data["s1_candles_sha256"]),
        "opportunities": (
            data["s1_opportunities_path"],
            data["s1_opportunities_sha256"],
        ),
        "s1_report": (data["s1_report_path"], data["s1_report_sha256"]),
        "s2_allocations": (data["s2_allocations_path"], data["s2_allocations_sha256"]),
        "s2_contract": (data["s2_contract_path"], data["s2_contract_sha256"]),
        "s2_manifest": (data["s2_manifest_path"], data["s2_manifest_sha256"]),
        "s2_report": (data["s2_report_path"], data["s2_report_sha256"]),
    }
    inputs = {
        name: required_input(path, digest, f"S3 {name}")
        for name, (path, digest) in input_specs.items()
    }
    audit = load_canonical(inputs["daily_audit"], "daily audit")
    mismatches = audit.get("reconciliation", {}).get("ohlc_mismatches", [])
    if any(set(item.get("fields", [])) - {"open"} for item in mismatches):
        raise ResearchHMMError("S3 high, low, or close fails source reconciliation")
    if contract["data"]["daily_risk_source"]["feature_fields"] != ["close", "high", "low"]:
        raise ResearchHMMError("S3 source fields changed")

    daily_rows = load_daily_ohlc(
        inputs["daily"], data["daily_risk_source"]["expected_rows"]
    )
    features = build_feature_rows(daily_rows, data["daily_risk_source"]["dataset_sha256"])
    evaluation_start_ms = parse_utc_ms(data["evaluation_start"])
    evaluation_end_ms = parse_utc_ms(data["evaluation_end_exclusive"])
    states, snapshots = walk_forward_states(
        features,
        evaluation_start_ms=evaluation_start_ms,
        evaluation_end_ms=evaluation_end_ms,
        contract=contract,
    )
    candles = load_candles(
        inputs["candles"], data["s1_candles_sha256"], data["s1_candles_rows"]
    )
    s2_contract = load_canonical(inputs["s2_contract"], "S2 contract")
    scenario_ids = s2_contract["parameters"]["execution_scenario_ids"]
    opportunities, inferred_costs = load_opportunities(
        inputs["opportunities"],
        data["s1_opportunities_sha256"],
        data["s1_opportunities_rows"],
        scenario_ids,
        67,
        candles,
    )
    s1_report = load_canonical(inputs["s1_report"], "S1 report")
    side_costs = {
        scenario_id: float(s1_report["scenarios"][scenario_id]["side_cost_bps"])
        for scenario_id in scenario_ids
    }
    if any(
        not math.isclose(inferred_costs[key], side_costs[key], rel_tol=0, abs_tol=1e-9)
        for key in scenario_ids
    ):
        raise ResearchHMMError("S1 cost lineage changed")
    ewma_allocations = load_primary_s2_allocations(
        inputs["s2_allocations"], opportunities, s2_contract["robustness"]["primary_variant_id"]
    )
    state_allocations = hmm_allocations(
        opportunities,
        ewma_allocations,
        states,
        max_age_ms=contract["operational_state"]["maximum_age_hours_exclusive"] * 3_600_000,
    )
    state_coverage = coverage(opportunities, state_allocations)
    path = state_path_statistics(states)
    labels = forward_labels(
        states,
        candles,
        horizon_days=contract["standalone_gates"]["forward_label_horizon_days"],
        evaluation_end_ms=evaluation_end_ms,
    )
    bootstrap = {
        metric: month_block_state_difference(
            labels,
            metric,
            seed=contract["standalone_gates"]["month_block_bootstrap_seed"],
            replications=contract["standalone_gates"]["month_block_bootstrap_replications"],
        )
        for metric in ("realized_variance", "downside_loss")
    }
    gates = contract["standalone_gates"]
    convergence = bool(snapshots) and all(item.fit.converged for item in snapshots)
    label_stability = bool(snapshots) and all(
        sum(item.fit.locations[0]) < sum(item.fit.locations[1]) for item in snapshots
    )
    occupancy_gate = all(
        value >= gates["minimum_hard_state_occupancy_fraction"]
        for value in path["occupancy"].values()
    )
    dwell_gate = all(
        value >= gates["minimum_median_dwell_observations_each_state"]
        for value in path["median_dwell"].values()
    )
    separation = {
        metric: bootstrap[metric]["observed_difference"] > 0
        and bootstrap[metric]["ci95"][0] > 0
        and bootstrap[metric]["valid_replications"] >= 9500
        for metric in bootstrap
    }
    standalone = {
        "convergence": convergence,
        "downside_loss_separation": separation["downside_loss"],
        "label_stability": label_stability,
        "median_dwell": dwell_gate,
        "minimum_forward_labels": len(labels) >= gates["minimum_valid_forward_labels"],
        "one_day_flicker": path["one_day_run_fraction"]
        <= gates["one_day_run_fraction_maximum"],
        "opportunity_coverage_annual": all(
            item["coverage"] >= 0.9 for item in state_coverage["annual"].values()
        ),
        "opportunity_coverage_overall": state_coverage["overall"] >= 0.95,
        "occupancy": occupancy_gate,
        "realized_variance_separation": separation["realized_variance"],
        "transitions": path["transitions"] >= gates["minimum_out_of_sample_transitions"],
    }

    output = require_output(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, dict[str, Any]] = {}
    artifacts["feature-observations.jsonl.gz"] = write_jsonl_gzip(
        output / "feature-observations.jsonl.gz", (item.as_dict() for item in features)
    )
    artifacts["model-snapshots.jsonl.gz"] = write_jsonl_gzip(
        output / "model-snapshots.jsonl.gz",
        ({**item.as_dict(), "snapshot_digest": item.digest} for item in snapshots),
    )
    artifacts["regime-states.jsonl.gz"] = write_jsonl_gzip(
        output / "regime-states.jsonl.gz", (item.as_dict() for item in states)
    )
    artifacts["forward-labels.jsonl.gz"] = write_jsonl_gzip(
        output / "forward-labels.jsonl.gz", labels
    )
    artifacts["opportunity-allocations.jsonl.gz"] = write_jsonl_gzip(
        output / "opportunity-allocations.jsonl.gz", state_allocations
    )
    report: dict[str, Any] = {
        "actionable_arm_id": "no_trade",
        "contract_sha256": sha256_file(amendment_path),
        "development_overlay_gate_met": False,
        "evidence_classification": "consumed_development_only",
        "experiment_id": contract["experiment_id"],
        "feature_observations": len(features),
        "forward_label_bootstrap": bootstrap,
        "forward_labels": len(labels),
        "holdout_accessed": False,
        "model_fitted": True,
        "promotion_evidence": False,
        "refit_snapshots": len(snapshots),
        "schema_version": "btc-regime-routing-s3-report-v1",
        "standalone_gates": standalone,
        "state_path": path,
        "state_opportunity_coverage": state_coverage,
    }
    trade_rows: list[dict[str, Any]] = []
    if not all(standalone.values()):
        risk_separation_passed = separation["realized_variance"] and separation["downside_loss"]
        unstable = not all(
            standalone[name] for name in ("median_dwell", "one_day_flicker", "transitions")
        )
        if not risk_separation_passed:
            report["decision"] = "s3_rejected_stop_latent_branch"
            report["s4_disposition"] = "skipped_forward_risk_separation_failed"
        elif unstable:
            report["decision"] = "s3_rejected_s4_jump_model_eligible"
            report["s4_disposition"] = "eligible_only_under_frozen_conditional_branch"
        else:
            report["decision"] = "s3_rejected_s4_skipped"
            report["s4_disposition"] = "skipped_failure_not_transition_or_dwell_related"
        report["simulations"] = None
    else:
        primary_daily_features = load_direct_close_features(
            inputs["daily"],
            data["daily_risk_source"]["dataset_sha256"],
            data["daily_risk_source"]["expected_rows"],
            source_segment=data["daily_risk_source"]["source_segment_id"],
        )
        ewma_config = EWMAConfig(
            variant_id=s2_contract["robustness"]["primary_variant_id"],
            decay_lambda=s2_contract["parameters"]["daily_decay_lambda"],
            target_annualized_volatility=s2_contract["parameters"]["target_annualized_volatility"],
            annualization_days=s2_contract["parameters"]["annualization_days"],
            initialization_returns=s2_contract["initialization"]["minimum_returns"],
        )
        ewma_observations = build_ewma_observations(primary_daily_features, ewma_config)
        participation = segmented_participation_opportunities(
            candles, evaluation_start_ms, evaluation_end_ms
        )
        participation_ewma_rows = allocations_for_opportunities(
            participation,
            ewma_observations,
            base_allocation=s2_contract["parameters"]["base_allocation_fraction"],
            max_age_ms=s2_contract["parameters"]["forecast_maximum_age_hours_exclusive"]
            * 3_600_000,
            independent_risk_source=True,
        )
        participation_ewma = [float(item["allocation_fraction"]) for item in participation_ewma_rows]
        participation_hmm_rows = hmm_allocations(
            participation,
            participation_ewma,
            states,
            max_age_ms=contract["operational_state"]["maximum_age_hours_exclusive"]
            * 3_600_000,
        )
        hmm_values = [float(item["allocation_fraction"]) for item in state_allocations]
        participation_hmm = [float(item["allocation_fraction"]) for item in participation_hmm_rows]
        exposure_match = matched_allocation(opportunities, state_allocations)
        controls = {
            "flat_no_trade": (opportunities, [0.0] * len(opportunities)),
            "fixed_10_percent_breakout": (opportunities, [0.1] * len(opportunities)),
            "primary_ewma_scaled_breakout": (opportunities, ewma_allocations),
            "student_t_hmm_on_ewma_breakout": (opportunities, hmm_values),
            "constant_capital_time_matched_hmm_breakout": (
                opportunities,
                [exposure_match] * len(opportunities),
            ),
            "fixed_10_percent_segmented_btc_participation": (
                participation,
                [0.1] * len(participation),
            ),
            "primary_ewma_scaled_segmented_btc_participation": (
                participation,
                participation_ewma,
            ),
            "student_t_hmm_on_ewma_segmented_btc_participation": (
                participation,
                participation_hmm,
            ),
        }
        full: dict[str, dict[str, dict[str, Any]]] = {}
        summaries: dict[str, dict[str, Any]] = {}
        for scenario_id in scenario_ids:
            full[scenario_id] = {}
            summaries[scenario_id] = {}
            for control_id, (cohorts, values) in controls.items():
                result = simulate_locked_cohorts(
                    candles,
                    cohorts,
                    values,
                    side_cost_bps=side_costs[scenario_id],
                    evaluation_start_ms=evaluation_start_ms,
                    evaluation_end_ms=evaluation_end_ms,
                )
                full[scenario_id][control_id] = result
                summaries[scenario_id][control_id] = compact_summary(result)
                trade_rows.extend(
                    {"control_id": control_id, "scenario_id": scenario_id, **trade}
                    for trade in result["trades"]
                )
        s2_report = load_canonical(inputs["s2_report"], "S2 report")
        for scenario_id in scenario_ids:
            expected = s2_report["simulations"][scenario_id]["primary_ewma_scaled_breakout"]
            actual = summaries[scenario_id]["primary_ewma_scaled_breakout"]
            if any(
                isinstance(value, (int, float))
                and not math.isclose(float(actual[key]), float(value), rel_tol=0, abs_tol=1e-12)
                for key, value in expected.items()
                if value is not None
            ):
                raise ResearchHMMError("frozen S2 EWMA control parity mismatch")
        scorecard = contract["overlay_gates"]
        scenario_gates: dict[str, dict[str, bool]] = {}
        neutralized: dict[str, Any] = {}
        paired_ci: dict[str, Any] = {}
        for scenario_id in scorecard["required_cost_scenarios"]:
            ewma = full[scenario_id]["primary_ewma_scaled_breakout"]
            hmm = full[scenario_id]["student_t_hmm_on_ewma_breakout"]
            item = neutralize_best_relative_months(hmm["daily_returns"], ewma["daily_returns"])
            neutralized[scenario_id] = item
            translated = {
                "maximum_drawdown_or_worst_rolling_90_day_loss_improvement_fraction_minimum": scorecard[
                    "maximum_drawdown_or_worst_rolling_90_day_loss_improvement_fraction_minimum"
                ],
                "minimum_calmar_improvement_fraction": scorecard[
                    "minimum_ewma_calmar_improvement_fraction"
                ],
                "minimum_fixed_cagr_retention_fraction": scorecard[
                    "minimum_ewma_cagr_retention_fraction"
                ],
            }
            scenario_gates[scenario_id] = economic_scenario_gates(hmm, ewma, item, translated)
            paired_ci[scenario_id] = paired_month_bootstrap(
                hmm["monthly_returns"],
                ewma["monthly_returns"],
                seed=contract["standalone_gates"]["month_block_bootstrap_seed"],
                replications=contract["standalone_gates"]["month_block_bootstrap_replications"],
            )
        report["simulations"] = summaries
        report["constant_capital_time_matched_allocation_fraction"] = exposure_match
        report["economic_gates"] = scenario_gates
        report["best_relative_month_neutralization"] = neutralized
        report["paired_monthly_return_difference_ci95"] = paired_ci
        report["leave_one_year_out"] = {
            scenario_id: {
                "ewma": leave_one_year_out(
                    full[scenario_id]["primary_ewma_scaled_breakout"]["daily_returns"]
                ),
                "hmm": leave_one_year_out(
                    full[scenario_id]["student_t_hmm_on_ewma_breakout"]["daily_returns"]
                ),
            }
            for scenario_id in scorecard["required_cost_scenarios"]
        }
        report["planned_risk_fraction_at_maximum_allocation"] = {
            scenario_id: check_planned_risk(
                0.1,
                s2_contract["parameters"]["protective_stop_fraction"],
                side_costs[scenario_id] * 2,
                s2_contract["parameters"]["maximum_planned_risk_fraction"],
            )
            for scenario_id in scenario_ids
        }
        report["development_overlay_gate_met"] = all(
            all(item.values()) for item in scenario_gates.values()
        )
        if report["development_overlay_gate_met"]:
            report["decision"] = "s3_passed_all_gates_s4_skipped"
            report["s4_disposition"] = "skipped_hmm_passed"
        else:
            report["decision"] = "s3_rejected_overlay_gates_s4_skipped"
            report["s4_disposition"] = "skipped_hmm_transition_and_dwell_stable"
        artifacts["simulation-trades.jsonl.gz"] = write_jsonl_gzip(
            output / "simulation-trades.jsonl.gz", trade_rows
        )

    report_path = output / "s3-hmm-report.json"
    report_path.write_text(canonical_json(report), encoding="utf-8")
    artifacts["s3-hmm-report.json"] = {
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
            "research_hmm.py": sha256_file(REPO_ROOT / "src/trading_platform/research_hmm.py"),
            "runner": sha256_file(Path(__file__).resolve()),
        },
        "inputs": {
            str(BASE_CONTRACT.relative_to(REPO_ROOT)): sha256_file(BASE_CONTRACT),
            str(amendment_path.relative_to(REPO_ROOT)): sha256_file(amendment_path),
            str(boundary_path.relative_to(REPO_ROOT)): sha256_file(boundary_path),
            **{
                str(path.relative_to(REPO_ROOT)): sha256_file(path)
                for path in inputs.values()
            },
        },
        "model_fitted": True,
        "promotion_evidence": False,
        "schema_version": "btc-regime-routing-s3-manifest-v1",
    }
    manifest_path = output / "manifest.json"
    manifest_path.write_text(canonical_json(manifest), encoding="utf-8")
    return report


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    value.add_argument(
        "--output-dir", type=Path, default=ARTIFACT_ROOT / "s3-student-t-hmm-v1"
    )
    return value


if __name__ == "__main__":
    try:
        result = run(parser().parse_args())
    except (OSError, ValueError, KeyError, ResearchHMMError) as exc:
        raise SystemExit(str(exc)) from exc
    print(canonical_json(result), end="")
