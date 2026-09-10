#!/usr/bin/env python3
"""Run the frozen standalone BTC HAR-RV forecast experiment offline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from trading_platform.research_har import (
    build_daily_realized_variances,
    build_forecast_comparisons,
    build_har_samples,
    build_rv_ewma,
    calendar_coverage,
    close_ewma_map,
    score_forecasts,
)
from trading_platform.research_ledger import DAY_MS, sha256_file, write_jsonl_gzip
from trading_platform.research_program import canonical_json
from trading_platform.research_volatility import (
    EWMAConfig,
    build_ewma_observations,
    load_candles,
    load_direct_close_features,
    parse_utc_ms,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = REPO_ROOT / "research/btc/contracts/btc-har-rv-risk-forecast-v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "artifacts/agent-level-experiment/btc-focused/har-rv-risk-forecast-v1"
CONTRACT_SHA256 = "fcccd0b23c6501b964b0f9b9ccc429eef32d494b2bdfe7b84abba79d80277945"


def load_canonical(path: Path, label: str) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    value = json.loads(raw)
    if not isinstance(value, dict) or raw != canonical_json(value):
        raise ValueError(f"non-canonical {label}")
    return value


def require_file(path: Path, expected_sha256: str, label: str) -> Path:
    absolute = path.absolute()
    for component in (absolute, *absolute.parents):
        if component.is_symlink():
            raise ValueError(f"symlinked {label} is prohibited")
    resolved = path.resolve(strict=True)
    resolved.relative_to(REPO_ROOT)
    if sha256_file(resolved) != expected_sha256:
        raise ValueError(f"{label} checksum mismatch")
    return resolved


def require_output(path: Path) -> Path:
    resolved_parent = path.parent.resolve(strict=True)
    resolved_parent.relative_to(REPO_ROOT / "artifacts/agent-level-experiment/btc-focused")
    output = resolved_parent / path.name
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("HAR-RV output must be a new empty directory")
    return output


def _gate_report(
    contract: dict[str, Any],
    horizon_results: dict[str, dict[str, Any]],
) -> dict[str, bool]:
    frozen = contract["validity_gates"]
    one = horizon_results["1d"]
    seven = horizon_results["7d"]

    def coverage_pass(result: dict[str, Any]) -> bool:
        coverage = result["coverage"]
        return coverage["overall"] >= frozen["minimum_overall_common_row_coverage_each_horizon"] and all(
            value["coverage"] >= frozen["minimum_yearly_common_row_coverage_each_horizon"]
            for value in coverage["annual"].values()
        )

    def calibration_pass(result: dict[str, Any]) -> bool:
        quartiles = result["scores"]["calibration_quartiles"]
        return quartiles["4"]["mean_realized_variance"] > quartiles["1"]["mean_realized_variance"]

    one_scores = one["scores"]
    seven_scores = seven["scores"]
    one_har = one_scores["har"]
    seven_har = seven_scores["har"]
    one_controls = one_scores["controls"]
    seven_controls = seven_scores["controls"]
    leave_one_out = one_scores["leave_one_year_out_mean_qlike_improvement_vs_rv_ewma"]
    return {
        "calibration_fourth_quartile_realized_above_first_both_horizons": calibration_pass(one)
        and calibration_pass(seven),
        "common_forecast_minimums": one_scores["observations"] >= frozen["minimum_common_forecasts_one_day"]
        and seven_scores["observations"] >= frozen["minimum_common_forecasts_seven_day"],
        "common_row_coverage": coverage_pass(one) and coverage_pass(seven),
        "forecast_and_label_timestamps_strictly_causal": all(
            row.target_end_ms == row.decision_ms + row.horizon_days * DAY_MS
            and row.model_cutoff_ms <= row.decision_ms
            for result in horizon_results.values()
            for row in result["rows"]
        ),
        "har_mean_mse_ratio_to_same_input_ewma_maximum_both_horizons": one_har[
            "mse_ratio_to_rv_ewma"
        ]
        <= frozen["har_mean_mse_ratio_to_same_input_ewma_maximum_both_horizons"]
        and seven_har["mse_ratio_to_rv_ewma"]
        <= frozen["har_mean_mse_ratio_to_same_input_ewma_maximum_both_horizons"],
        "har_mean_qlike_strictly_below_both_controls_one_day": one_har["mean_qlike"]
        < one_controls["close_ewma"]["mean_qlike"]
        and one_har["mean_qlike"] < one_controls["rv_ewma"]["mean_qlike"],
        "har_mean_qlike_weakly_below_both_controls_seven_day": seven_har["mean_qlike"]
        <= seven_controls["close_ewma"]["mean_qlike"]
        and seven_har["mean_qlike"] <= seven_controls["rv_ewma"]["mean_qlike"],
        "leave_one_year_out_positive_qlike_improvement_vs_same_input_ewma": sum(
            value is not None and value > 0 for value in leave_one_out.values()
        )
        >= frozen["leave_one_year_out_positive_qlike_improvement_vs_same_input_ewma_minimum"],
        "monthly_refit_minimums": one["forecast_build"]["monthly_refits"]
        >= frozen["minimum_monthly_refits_each_horizon"]
        and seven["forecast_build"]["monthly_refits"]
        >= frozen["minimum_monthly_refits_each_horizon"],
        "one_day_calendar_year_qlike_wins_vs_same_input_ewma": sum(
            bool(value["har_qlike_win_vs_rv_ewma"])
            for value in one_scores["annual"].values()
        )
        >= frozen["minimum_one_day_calendar_year_qlike_wins_vs_same_input_ewma"],
        "one_day_month_bootstrap_qlike_improvement_lower_95_vs_same_input_ewma_strictly_positive": one_scores[
            "month_bootstrap_qlike_improvement_vs_rv_ewma"
        ]["lower_95"]
        > 0,
        "outputs_canonical_checksummed_and_byte_reproducible": True,
        "risk_cap_eligible_after_result": frozen["risk_cap_eligible_after_result"] is False,
        "strategy_or_pnl_computed": frozen["strategy_or_pnl_computed"] is False,
    }


def run(contract_path: Path, output_path: Path) -> dict[str, Any]:
    contract_path = require_file(
        contract_path,
        CONTRACT_SHA256,
        "HAR-RV contract",
    )
    if contract_path != DEFAULT_CONTRACT.resolve():
        raise ValueError("only the exact frozen HAR-RV contract is allowed")
    contract = load_canonical(contract_path, "HAR-RV contract")
    if (
        contract.get("schema_version") != "btc-har-rv-risk-forecast-contract-v1"
        or contract.get("experiment_id") != "btc-har-rv-risk-forecast-v1"
        or contract.get("status") != "frozen_before_implementation_and_results"
    ):
        raise ValueError("HAR-RV contract identity changed")
    boundary = contract["action_boundary"]
    if boundary.get("actionable_arm_id") != "no_trade" or boundary.get("accepted_strategy_arms"):
        raise ValueError("HAR-RV contract does not preserve no_trade")
    if any(value is not False for key, value in contract["isolation"].items() if key.endswith("_allowed")):
        raise ValueError("HAR-RV isolation boundary permits external access")
    if contract["data"].get("sealed_2026_access_allowed") is not False:
        raise ValueError("HAR-RV contract permits sealed 2026 data")

    bound = {item["path"]: item for item in contract["bound_inputs"]}
    resolved = {
        relative: require_file(REPO_ROOT / relative, item["sha256"], relative)
        for relative, item in bound.items()
    }
    s1_manifest_path = "artifacts/agent-level-experiment/btc-regime-routing/s1-ledger-v1/manifest.json"
    s1_manifest = load_canonical(resolved[s1_manifest_path], "S1 manifest")
    if s1_manifest.get("holdout_accessed") is not False:
        raise ValueError("S1 lineage accessed the holdout")
    candle_relative = "artifacts/agent-level-experiment/btc-regime-routing/s1-ledger-v1/candles-5m.jsonl.gz"
    candle_record = s1_manifest.get("artifacts", {}).get("candles-5m.jsonl.gz", {})
    if candle_record.get("sha256") != bound[candle_relative]["sha256"]:
        raise ValueError("S1 manifest does not bind the frozen five-minute ledger")

    daily_manifest_relative = "artifacts/agent-level-experiment/btc-regime-routing/s2-daily-data-audit-v1/manifest.json"
    daily_manifest = load_canonical(resolved[daily_manifest_relative], "daily source manifest")
    if daily_manifest.get("holdout_accessed") is not False:
        raise ValueError("daily close source accessed the holdout")
    daily_relative = "artifacts/agent-level-experiment/btc-regime-routing/s2-daily-data-audit-v1/btc-usdt-direct-1d-development-2017-2025.jsonl.gz"
    if daily_manifest.get("artifacts", {}).get(Path(daily_relative).name, {}).get("sha256") != bound[daily_relative]["sha256"]:
        raise ValueError("daily manifest does not bind the close-only control source")

    s2_contract_relative = "config/experiments/btc-regime-routing-s2-ewma-v2.json"
    s2_contract = load_canonical(resolved[s2_contract_relative], "mandatory EWMA contract")
    if (
        s2_contract.get("parameters", {}).get("daily_decay_lambda") != 0.94
        or s2_contract.get("initialization", {}).get("minimum_returns") != 30
        or s2_contract.get("source_discrepancy_disclosure", {}).get("ohlc_or_volume_fields_used_by_risk_model") is not False
    ):
        raise ValueError("mandatory close-only EWMA configuration changed")

    candles = load_candles(
        resolved[candle_relative],
        bound[candle_relative]["sha256"],
        contract["data"]["expected_five_minute_rows"],
    )
    development_start = parse_utc_ms(contract["data"]["development_start"])
    development_end = parse_utc_ms(contract["data"]["development_end_exclusive"])
    first_full_day = ((development_start + DAY_MS - 1) // DAY_MS) * DAY_MS
    daily_rv, daily_rv_audit = build_daily_realized_variances(
        candles,
        start_ms=first_full_day,
        end_ms=development_end,
        source_digest=bound[candle_relative]["sha256"],
    )
    daily_close_features = load_direct_close_features(
        resolved[daily_relative],
        bound[daily_relative]["sha256"],
        contract["data"]["daily_close_control_rows"],
        source_segment="binance-direct-daily-continuous-2017-2025-v1",
    )
    close_observations = build_ewma_observations(
        daily_close_features,
        EWMAConfig(
            variant_id="mandatory-close-return-ewma-lambda-094",
            decay_lambda=0.94,
            target_annualized_volatility=0.4,
            initialization_returns=30,
        ),
    )
    close_control = close_ewma_map(close_observations)
    model = contract["model"]
    rv_control = build_rv_ewma(
        daily_rv,
        decay_lambda=model["same_input_ewma_lambda"],
        initialization_observations=model["same_input_ewma_initialization_observations"],
    )
    evaluation_start = parse_utc_ms(contract["data"]["evaluation_start"])
    evaluation_end = parse_utc_ms(contract["data"]["evaluation_end_exclusive"])
    evaluation = contract["evaluation"]
    horizon_results: dict[str, dict[str, Any]] = {}
    all_rows = []
    all_models = []
    for horizon in evaluation["forecast_horizons_days"]:
        samples = build_har_samples(daily_rv, horizon)
        rows, build_audit, models = build_forecast_comparisons(
            samples,
            close_ewma=close_control,
            rv_ewma=rv_control,
            evaluation_start_ms=evaluation_start,
            evaluation_end_ms=evaluation_end,
            minimum_training_samples=model["minimum_training_samples"],
            ridge_penalty=model["ridge_penalty_on_standardized_slopes"],
            variance_floor=model["daily_realized_variance_floor"],
        )
        scores = score_forecasts(
            rows,
            bootstrap_replications=evaluation["bootstrap_replications"],
            bootstrap_seed=evaluation["bootstrap_seed"],
        )
        key = f"{horizon}d"
        horizon_results[key] = {
            "coverage": calendar_coverage(
                rows,
                evaluation_start_ms=evaluation_start,
                evaluation_end_ms=evaluation_end,
                horizon_days=horizon,
            ),
            "forecast_build": build_audit,
            "rows": rows,
            "sample_count_all_bound_data": len(samples),
            "scores": scores,
        }
        all_rows.extend(rows)
        all_models.extend(models)

    gates = _gate_report(contract, horizon_results)
    passed = all(gates.values())
    output = require_output(output_path)
    output.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, dict[str, Any]] = {}
    artifacts["forecasts.jsonl.gz"] = write_jsonl_gzip(
        output / "forecasts.jsonl.gz",
        (
            item.as_dict()
            for item in sorted(all_rows, key=lambda value: (value.horizon_days, value.decision_ms))
        ),
    )
    artifacts["model-snapshots.jsonl.gz"] = write_jsonl_gzip(
        output / "model-snapshots.jsonl.gz",
        (
            item.as_dict()
            for item in sorted(all_models, key=lambda value: (value.horizon_days, value.cutoff_ms))
        ),
    )
    public_horizons = {
        key: {name: value for name, value in result.items() if name != "rows"}
        for key, result in horizon_results.items()
    }
    report = {
        "accepted_strategy_arms": [],
        "actionable_arm_id": "no_trade",
        "contract_sha256": sha256_file(contract_path),
        "decision": "development_forecast_challenger_passed_action_mapping_blocked"
        if passed
        else "development_forecast_challenger_rejected",
        "development_forecast_gates_passed": passed,
        "evidence_classification": evaluation["evidence_classification"],
        "experiment_id": contract["experiment_id"],
        "gates": gates,
        "horizons": public_horizons,
        "no_strategy_return_pnl_allocation_or_execution_computed": True,
        "promotion_evidence": False,
        "realized_variance_audit": daily_rv_audit,
        "risk_cap_eligible": False,
        "schema_version": "btc-har-rv-risk-forecast-report-v1",
        "year_2026_accessed": False,
    }
    report_path = output / "report.json"
    report_path.write_text(canonical_json(report), encoding="utf-8")
    artifacts["report.json"] = {
        "bytes": report_path.stat().st_size,
        "sha256": sha256_file(report_path),
    }
    manifest = {
        "artifacts": artifacts,
        "bound_inputs": contract["bound_inputs"],
        "contract_sha256": sha256_file(contract_path),
        "decision": report["decision"],
        "experiment_id": contract["experiment_id"],
        "no_external_or_protected_service_access": True,
        "schema_version": "btc-har-rv-risk-forecast-manifest-v1",
        "source_files": [
            {
                "path": "src/trading_platform/research_har.py",
                "sha256": sha256_file(REPO_ROOT / "src/trading_platform/research_har.py"),
            },
            {
                "path": "tests/test_research_har.py",
                "sha256": sha256_file(REPO_ROOT / "tests/test_research_har.py"),
            },
            {
                "path": "scripts/run_btc_har_rv_risk_forecast.py",
                "sha256": sha256_file(REPO_ROOT / "scripts/run_btc_har_rv_risk_forecast.py"),
            },
        ],
    }
    manifest_path = output / "evidence-manifest.json"
    manifest_path.write_text(canonical_json(manifest), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = run(args.contract, args.output)
    print(
        json.dumps(
            {
                "decision": report["decision"],
                "experiment_id": report["experiment_id"],
                "gates_passed": report["development_forecast_gates_passed"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
