#!/usr/bin/env python3
"""Run the frozen MCS3-D BTC downside/tail information experiment offline."""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_platform.research_downside import (  # noqa: E402
    DownsideResearchError,
    build_daily_downside_observations,
    build_downside_samples,
    build_forecasts,
    build_horizon_tail_losses,
    calendar_coverage,
    canonical_json,
    parse_utc_ms,
    score_forecasts,
    sha256_file,
    write_jsonl_gzip,
)
from trading_platform.research_volatility import load_candles  # noqa: E402


DEFAULT_CONTRACT = (
    ROOT / "research/btc/contracts/btc-market-condition-scores-mcs3-d-v1.json"
)
DEFAULT_OUTPUT = (
    ROOT
    / "artifacts/agent-level-experiment/btc-focused/market-condition-scores-mcs3-d-v1"
)
CONTRACT_SHA256 = "1206acf6e80f985bd491e60f1a67aa7135c84f4ea541be5835bd7050cbed1024"
MODULE_PATH = ROOT / "src/trading_platform/research_downside.py"
RUNNER_PATH = Path(__file__).resolve()
FOCUSED_ARTIFACT_ROOT = (
    ROOT / "artifacts/agent-level-experiment/btc-focused"
).resolve(strict=True)
S1_MANIFEST = "artifacts/agent-level-experiment/btc-regime-routing/s1-ledger-v1/manifest.json"
S1_CANDLES = "artifacts/agent-level-experiment/btc-regime-routing/s1-ledger-v1/candles-5m.jsonl.gz"
FORBIDDEN_IMPORTS = frozenset(
    {"ccxt", "freqtrade", "httpx", "nats", "psycopg", "requests", "sqlalchemy"}
)


def _load_canonical(path: Path, label: str) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DownsideResearchError(f"invalid {label} JSON") from exc
    if not isinstance(value, dict) or raw != canonical_json(value):
        raise DownsideResearchError(f"non-canonical {label}")
    return value


def _require_file(path: Path, expected_sha256: str, label: str) -> Path:
    absolute = path.absolute()
    for component in (absolute, *absolute.parents):
        if component.is_symlink():
            raise DownsideResearchError(f"symlinked {label} is prohibited")
    resolved = path.resolve(strict=True)
    try:
        resolved.relative_to(ROOT)
    except ValueError as exc:
        raise DownsideResearchError(f"{label} escapes the repository") from exc
    lowered = str(resolved.relative_to(ROOT)).lower()
    if "holdout" in lowered or "2026-01-07" in lowered:
        raise DownsideResearchError(f"sealed input path is prohibited: {label}")
    actual = sha256_file(resolved)
    if actual != expected_sha256:
        raise DownsideResearchError(
            f"{label} checksum mismatch: expected {expected_sha256}, got {actual}"
        )
    return resolved


def _require_output(path: Path) -> Path:
    if path.is_symlink():
        raise DownsideResearchError("symlinked output is prohibited")
    resolved = path.resolve(strict=False)
    try:
        resolved.relative_to(FOCUSED_ARTIFACT_ROOT)
    except ValueError as exc:
        raise DownsideResearchError("output escapes BTC-focused artifact boundary") from exc
    for component in resolved.parents:
        if component == FOCUSED_ARTIFACT_ROOT.parent:
            break
        if component.exists() and component.is_symlink():
            raise DownsideResearchError("symlinked output parent is prohibited")
    if resolved.exists() and (not resolved.is_dir() or any(resolved.iterdir())):
        raise DownsideResearchError("MCS3-D output must be absent or an empty directory")
    return resolved


def _audit_imports(paths: Iterable[Path]) -> dict[str, Any]:
    imports: set[str] = set()
    audited: list[str] = []
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        audited.append(str(path.relative_to(ROOT)))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
    violations = sorted(imports & FORBIDDEN_IMPORTS)
    return {
        "audited": audited,
        "imports": sorted(imports),
        "passed": not violations,
        "violations": violations,
    }


def _verify_contract(contract: dict[str, Any]) -> None:
    if (
        contract.get("schema_version")
        != "btc-market-condition-scores-mcs3-d-contract-v1"
        or contract.get("experiment_id") != "btc-market-condition-scores-mcs3-d-v1"
        or contract.get("stage_id") != "MCS3-D"
        or contract.get("status") != "frozen_before_any_downside_or_tail_outcome_read"
    ):
        raise DownsideResearchError("wrong or unfrozen MCS3-D contract")
    boundary = contract.get("action_boundary", {})
    if boundary.get("actionable_arm_id") != "no_trade" or boundary.get(
        "accepted_strategy_arms"
    ):
        raise DownsideResearchError("MCS3-D contract does not preserve no_trade")
    forbidden_true = [
        key
        for key, value in boundary.items()
        if key.endswith("_allowed") and value is not False
    ]
    if forbidden_true or boundary.get("live_allocation_usdt") != 0:
        raise DownsideResearchError("MCS3-D action boundary permits prohibited activity")
    chronology = contract.get("chronology", {})
    if chronology.get("evaluation_end_exclusive") != "2026-01-01T00:00:00Z":
        raise DownsideResearchError("MCS3-D evaluation boundary changed")
    if contract.get("historical_quantile", {}).get("exceedance_rule") != (
        "loss_greater_than_or_equal_to_VaR"
    ):
        raise DownsideResearchError("MCS3-D exceedance convention changed")
    targets = contract.get("targets")
    if targets != [
        {"days": 1, "horizon": "1d", "role": "primary"},
        {"days": 7, "horizon": "7d", "role": "secondary_diagnostic_cannot_rescue_primary"},
    ]:
        raise DownsideResearchError("MCS3-D target horizons changed")


def _verify_inputs(
    contract: dict[str, Any], contract_path: Path
) -> tuple[dict[str, Path], list[dict[str, str]]]:
    if contract_path != DEFAULT_CONTRACT.resolve(strict=True):
        raise DownsideResearchError("only the repository MCS3-D contract may run")
    if sha256_file(contract_path) != CONTRACT_SHA256:
        raise DownsideResearchError("frozen MCS3-D contract checksum changed")
    resolved: dict[str, Path] = {}
    verified: list[dict[str, str]] = []
    for item in contract["bound_inputs"]:
        relative = item["path"]
        path = _require_file(ROOT / relative, item["sha256"], relative)
        resolved[relative] = path
        verified.append({"path": relative, "sha256": item["sha256"]})
    if S1_MANIFEST not in resolved or S1_CANDLES not in resolved:
        raise DownsideResearchError("MCS3-D contract omits required S1 lineage")
    s1 = _load_canonical(resolved[S1_MANIFEST], "S1 manifest")
    if s1.get("experiment_id") != "btc-regime-routing-s1-ledger-v1":
        raise DownsideResearchError("wrong S1 lineage experiment")
    if s1.get("holdout_accessed") is not False:
        raise DownsideResearchError("S1 lineage accessed the holdout")
    candle_record = s1.get("artifacts", {}).get("candles-5m.jsonl.gz", {})
    bound_candle = next(
        item for item in contract["bound_inputs"] if item["path"] == S1_CANDLES
    )
    if (
        candle_record.get("sha256") != bound_candle["sha256"]
        or candle_record.get("rows") != contract["input_contract"]["expected_rows"]
    ):
        raise DownsideResearchError("S1 manifest does not bind the frozen 5m ledger")
    return resolved, verified


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    method = getattr(value, "as_dict", None)
    if not callable(method):
        raise DownsideResearchError("ledger row does not support canonical serialization")
    result = method()
    if not isinstance(result, dict):
        raise DownsideResearchError("ledger row serialization is not an object")
    return result


def _row_value(value: Any, name: str) -> Any:
    if isinstance(value, dict):
        return value[name]
    return getattr(value, name)


def _causality_and_domain_checks(rows: Iterable[Any]) -> bool:
    seen: set[tuple[int, int]] = set()
    for row in rows:
        decision = int(_row_value(row, "decision_ms"))
        target_end = int(_row_value(row, "target_end_ms"))
        horizon = int(_row_value(row, "horizon_days"))
        cutoff = int(_row_value(row, "model_cutoff_ms"))
        identity = (decision, horizon)
        if identity in seen or target_end != decision + horizon * 86_400_000:
            return False
        if cutoff > decision or target_end <= decision:
            return False
        positive = (
            "candidate_negative_semivariance",
            "benchmark_negative_semivariance",
            "candidate_var_95",
            "candidate_es_95",
            "benchmark_var_95",
            "benchmark_es_95",
        )
        try:
            values = {name: float(_row_value(row, name)) for name in positive}
        except (AttributeError, KeyError, TypeError, ValueError):
            return False
        if any(value <= 0 for value in values.values()):
            return False
        if values["candidate_es_95"] < values["candidate_var_95"] or values[
            "benchmark_es_95"
        ] < values["benchmark_var_95"]:
            return False
        seen.add(identity)
    return bool(seen)


def _score_gates(
    contract: dict[str, Any],
    horizon_results: dict[str, dict[str, Any]],
    causal_domain_passed: bool,
) -> dict[str, bool]:
    frozen = contract["gates"]
    primary = horizon_results["1d"]
    scores = primary["scores"]
    candidate = scores["candidate"]
    benchmark = scores["benchmark"]
    coverage = primary["coverage"]
    required_years = [str(value) for value in frozen["required_evaluation_years"]]
    annual = scores["annual"]
    leave_one_out = scores["leave_one_year_out"]
    quartiles = scores["calibration_quartiles"]
    quartile_means = [
        quartiles[str(index)]["mean_realized_negative_semivariance"]
        for index in range(1, 5)
    ]
    qlike_bootstrap = scores["month_block_qlike_improvement"]
    fz0_bootstrap = scores["month_block_fz0_improvement"]
    es_calibration = scores["es_calibration_month_block"]
    exclusion = scores["excluding_best_three_months"]
    calibration = scores["var_exceedance"]
    refits = int(primary["forecast_build"]["monthly_refits"])
    valid_bootstraps = (qlike_bootstrap, fz0_bootstrap, es_calibration)
    return {
        "all_input_causality_common_row_score_domain_and_replay_checks": causal_domain_passed,
        "primary_1d_candidate_fz0_strictly_below_benchmark": candidate["mean_fz0"]
        < benchmark["mean_fz0"],
        "primary_1d_candidate_mse_ratio_to_benchmark_maximum": candidate[
            "mse_ratio_to_benchmark"
        ]
        <= frozen["primary_1d_candidate_mse_ratio_to_benchmark_maximum"],
        "primary_1d_candidate_nsv_qlike_strictly_below_benchmark": candidate[
            "mean_qlike"
        ]
        < benchmark["mean_qlike"],
        "primary_1d_candidate_pinball_strictly_below_benchmark": candidate[
            "mean_pinball"
        ]
        < benchmark["mean_pinball"],
        "primary_1d_es_calibration_month_block_interval_contains_zero": es_calibration[
            "ci95"
        ][0]
        <= 0
        <= es_calibration["ci95"][1],
        "primary_1d_excluding_best_three_months_fz0_and_qlike_improvements_positive": exclusion[
            "fz0_improvement"
        ]
        > 0
        and exclusion["qlike_improvement"] > 0,
        "primary_1d_forecast_count_minimum": scores["observations"]
        >= frozen["primary_1d_forecast_count_minimum"],
        "primary_1d_fz0_improvement_month_block_lower_95_strictly_above": fz0_bootstrap[
            "ci95"
        ][0]
        > frozen["primary_1d_fz0_improvement_month_block_lower_95_strictly_above"],
        "primary_1d_leave_one_year_out_fz0_and_qlike_positive_years_minimum": sum(
            value["fz0_improvement"] > 0 and value["qlike_improvement"] > 0
            for year, value in leave_one_out.items()
            if year in required_years
        )
        >= frozen["primary_1d_leave_one_year_out_fz0_and_qlike_positive_years_minimum"],
        "primary_1d_monthly_refits_minimum": refits
        >= frozen["primary_1d_monthly_refits_minimum"],
        "primary_1d_nsv_qlike_improvement_month_block_lower_95_strictly_above": qlike_bootstrap[
            "ci95"
        ][0]
        > frozen["primary_1d_nsv_qlike_improvement_month_block_lower_95_strictly_above"],
        "primary_1d_overall_coverage_minimum": coverage["overall"]
        >= frozen["primary_1d_overall_coverage_minimum"],
        "primary_1d_per_year_coverage_minimum": all(
            year in coverage["per_year"]
            and coverage["per_year"][year]["fraction"]
            >= frozen["primary_1d_per_year_coverage_minimum"]
            for year in required_years
        ),
        "primary_1d_positive_annual_fz0_and_qlike_improvement_years_minimum": sum(
            value["fz0_improvement"] > 0 and value["qlike_improvement"] > 0
            for year, value in annual.items()
            if year in required_years
        )
        >= frozen["primary_1d_positive_annual_fz0_and_qlike_improvement_years_minimum"],
        "primary_1d_risk_quartile_realized_nsv_means_non_decreasing": all(
            right >= left for left, right in zip(quartile_means, quartile_means[1:])
        ),
        "primary_1d_var_exceedance_fraction_maximum": calibration["fraction"]
        <= frozen["primary_1d_var_exceedance_fraction_maximum"],
        "primary_1d_var_exceedance_fraction_minimum": calibration["fraction"]
        >= frozen["primary_1d_var_exceedance_fraction_minimum"],
        "primary_1d_var_exceedance_wilson_interval_contains_expected": calibration[
            "wilson_95"
        ][0]
        <= contract["historical_quantile"]["tail_probability"]
        <= calibration["wilson_95"][1],
        "required_evaluation_years_present": set(coverage["per_year"])
        == set(required_years)
        and set(annual) == set(required_years)
        and set(leave_one_out) == set(required_years),
        "valid_bootstrap_replications_minimum": all(
            value["valid_replications"] >= frozen["valid_bootstrap_replications_minimum"]
            for value in valid_bootstraps
        ),
    }


def run(
    contract_path: Path = DEFAULT_CONTRACT, output_path: Path = DEFAULT_OUTPUT
) -> dict[str, Any]:
    contract_path = contract_path.resolve(strict=True)
    contract = _load_canonical(contract_path, "MCS3-D contract")
    _verify_contract(contract)
    resolved_inputs, verified_inputs = _verify_inputs(contract, contract_path)
    import_audit = _audit_imports((MODULE_PATH, RUNNER_PATH))
    if not import_audit["passed"]:
        raise DownsideResearchError("MCS3-D import isolation failed")
    destination = _require_output(output_path)

    candles = load_candles(
        resolved_inputs[S1_CANDLES],
        next(item["sha256"] for item in contract["bound_inputs"] if item["path"] == S1_CANDLES),
        contract["input_contract"]["expected_rows"],
    )
    chronology = contract["chronology"]
    development_start = parse_utc_ms(chronology["development_start"])
    development_end = parse_utc_ms(chronology["development_end_exclusive"])
    evaluation_start = parse_utc_ms(chronology["evaluation_start"])
    evaluation_end = parse_utc_ms(chronology["evaluation_end_exclusive"])
    observations, observation_audit = build_daily_downside_observations(
        candles,
        start_ms=development_start,
        end_ms=development_end,
        source_digest=next(
            item["sha256"] for item in contract["bound_inputs"] if item["path"] == S1_CANDLES
        ),
    )

    model = contract["model_parameters"]
    statistics = contract["statistics"]
    quantile = contract["historical_quantile"]
    horizon_results: dict[str, dict[str, Any]] = {}
    all_forecasts: list[Any] = []
    all_models: list[Any] = []
    for target in contract["targets"]:
        horizon = target["horizon"]
        days = int(target["days"])
        samples = build_downside_samples(
            observations,
            horizon_days=days,
        )
        historical_losses = build_horizon_tail_losses(observations, horizon_days=days)
        forecasts, forecast_audit, models = build_forecasts(
            samples,
            historical_losses=historical_losses,
            evaluation_start_ms=evaluation_start,
            evaluation_end_ms=evaluation_end,
            minimum_training_samples=model["minimum_training_labels"],
            ridge_penalty=model["ridge_penalty"],
            log_floor=model["log_floor"],
            tail_history_observations=contract["benchmark"]["tail_history_observations"],
        )
        scores = score_forecasts(
            forecasts,
            bootstrap_replications=statistics["month_block_bootstrap_replications"],
            bootstrap_seed=statistics["month_block_bootstrap_seed"],
            wilson_z=statistics["wilson_z"],
        )
        coverage = calendar_coverage(
            forecasts,
            evaluation_start_ms=evaluation_start,
            evaluation_end_ms=evaluation_end,
            horizon_days=days,
        )
        horizon_results[horizon] = {
            "coverage": coverage,
            "forecast_build": forecast_audit,
            "sample_count_all_bound_data": len(samples),
            "scores": scores,
        }
        all_forecasts.extend(forecasts)
        all_models.extend(models)

    causal_domain_passed = _causality_and_domain_checks(all_forecasts)
    gates = _score_gates(contract, horizon_results, causal_domain_passed)
    passed = all(gates.values())

    destination.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, dict[str, Any]] = {}
    artifacts["forecasts.jsonl.gz"] = write_jsonl_gzip(
        destination / "forecasts.jsonl.gz",
        (
            _as_dict(item)
            for item in sorted(
                all_forecasts,
                key=lambda value: (
                    int(_row_value(value, "horizon_days")),
                    int(_row_value(value, "decision_ms")),
                ),
            )
        ),
    )
    artifacts["models.jsonl.gz"] = write_jsonl_gzip(
        destination / "models.jsonl.gz",
        (
            _as_dict(item)
            for item in sorted(
                all_models,
                key=lambda value: (
                    int(_row_value(value, "horizon_days")),
                    int(_row_value(value, "cutoff_ms")),
                ),
            )
        ),
    )
    report = {
        "accepted_strategy_arms": [],
        "actionable_arm_id": "no_trade",
        "bound_inputs": verified_inputs,
        "candidate": contract["candidate"],
        "contract_sha256": sha256_file(contract_path),
        "decision": "downside_tail_information_accepted_for_future_offline_risk_research"
        if passed
        else "downside_tail_information_rejected",
        "experiment_id": contract["experiment_id"],
        "gates": gates,
        "horizons": horizon_results,
        "import_audit": import_audit,
        "information_gate_passed": passed,
        "market_values_used": True,
        "no_strategy_pnl_position_cost_execution_or_risk_cap_evaluated": True,
        "observation_audit": observation_audit,
        "partial_ob0_or_2026_accessed": False,
        "promotion_or_live_evidence": False,
        "schema_version": "btc-market-condition-scores-mcs3-d-report-v1",
    }
    report_path = destination / "report.json"
    report_path.write_text(canonical_json(report), encoding="utf-8")
    artifacts["report.json"] = {
        "bytes": report_path.stat().st_size,
        "sha256": sha256_file(report_path),
    }
    manifest = {
        "artifacts": artifacts,
        "bound_inputs": verified_inputs,
        "contract_sha256": sha256_file(contract_path),
        "decision": report["decision"],
        "experiment_id": contract["experiment_id"],
        "information_gate_passed": passed,
        "market_values_used": True,
        "no_external_or_protected_service_access": True,
        "no_strategy_pnl_position_cost_execution_or_risk_cap": True,
        "partial_ob0_or_2026_accessed": False,
        "schema_version": "btc-market-condition-scores-mcs3-d-evidence-manifest-v1",
        "source_files": [
            {
                "path": str(MODULE_PATH.relative_to(ROOT)),
                "sha256": sha256_file(MODULE_PATH),
            },
            {
                "path": str(RUNNER_PATH.relative_to(ROOT)),
                "sha256": sha256_file(RUNNER_PATH),
            },
            {
                "path": "tests/test_research_downside.py",
                "sha256": sha256_file(ROOT / "tests/test_research_downside.py"),
            },
        ],
    }
    manifest_path = destination / "evidence-manifest.json"
    manifest_path.write_text(canonical_json(manifest), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = run(args.contract, args.output)
    print(
        canonical_json(
            {
                "decision": report["decision"],
                "experiment_id": report["experiment_id"],
                "gates_passed": report["information_gate_passed"],
            }
        ),
        end="",
    )


if __name__ == "__main__":
    main()
