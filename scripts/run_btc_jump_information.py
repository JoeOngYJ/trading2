#!/usr/bin/env python3
"""Run the frozen MCS3-J jump/change information experiment offline."""

from __future__ import annotations

import argparse
import ast
import json
import math
import sys
from pathlib import Path
from typing import Any, Iterable, Sequence


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_platform.research_jump import (  # noqa: E402
    JumpResearchError,
    build_four_hour_jump_observations,
    build_jump_forecasts,
    calendar_coverage,
    canonical_json,
    parse_utc_ms,
    score_jump_forecasts,
    sha256_file,
    write_jsonl_gzip,
)
from trading_platform.research_volatility import CandlePoint, load_candles  # noqa: E402


DEFAULT_CONTRACT = ROOT / "research/btc/contracts/btc-market-condition-scores-mcs3-j-v1.json"
DEFAULT_OUTPUT = (
    ROOT
    / "artifacts/agent-level-experiment/btc-focused/market-condition-scores-mcs3-j-v1"
)
CONTRACT_SHA256 = "0b96d3a5624d9a91f59e0c5a484b5515bb9ae06b00ff1ef72e3da384d6976fd2"
MODULE_PATH = ROOT / "src/trading_platform/research_jump.py"
RUNNER_PATH = Path(__file__).resolve()
FOCUSED_ROOT = (
    ROOT / "artifacts/agent-level-experiment/btc-focused"
).resolve(strict=True)
S1_MANIFEST = "artifacts/agent-level-experiment/btc-regime-routing/s1-ledger-v1/manifest.json"
S1_CANDLES = "artifacts/agent-level-experiment/btc-regime-routing/s1-ledger-v1/candles-5m.jsonl.gz"
FOUR_HOURS_MS = 4 * 60 * 60 * 1000
FORBIDDEN_IMPORTS = frozenset(
    {"ccxt", "freqtrade", "httpx", "nats", "psycopg", "requests", "sqlalchemy"}
)


def _load_canonical(path: Path, label: str) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise JumpResearchError(f"invalid {label} JSON") from exc
    if not isinstance(value, dict) or raw != canonical_json(value):
        raise JumpResearchError(f"non-canonical {label}")
    return value


def _require_file(path: Path, expected_sha256: str, label: str) -> Path:
    absolute = path.absolute()
    for component in (absolute, *absolute.parents):
        if component.is_symlink():
            raise JumpResearchError(f"symlinked {label} is prohibited")
    resolved = path.resolve(strict=True)
    try:
        resolved.relative_to(ROOT)
    except ValueError as exc:
        raise JumpResearchError(f"{label} escapes repository boundary") from exc
    lowered = str(resolved.relative_to(ROOT)).lower()
    if "holdout" in lowered or "2026-01-07" in lowered:
        raise JumpResearchError(f"sealed input path is prohibited: {label}")
    actual = sha256_file(resolved)
    if actual != expected_sha256:
        raise JumpResearchError(
            f"{label} checksum mismatch: expected {expected_sha256}, got {actual}"
        )
    return resolved


def _require_output(path: Path) -> Path:
    absolute = path.absolute()
    for component in (absolute, *absolute.parents):
        if component.exists() and component.is_symlink():
            raise JumpResearchError("symlinked output path is prohibited")
    resolved = path.resolve(strict=False)
    try:
        resolved.relative_to(FOCUSED_ROOT)
    except ValueError as exc:
        raise JumpResearchError("output escapes BTC-focused artifact boundary") from exc
    if resolved.exists() and (not resolved.is_dir() or any(resolved.iterdir())):
        raise JumpResearchError("MCS3-J output must be absent or an empty directory")
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
        contract.get("schema_version") != "btc-market-condition-scores-mcs3-j-contract-v1"
        or contract.get("experiment_id") != "btc-market-condition-scores-mcs3-j-v1"
        or contract.get("stage_id") != "MCS3-J"
        or contract.get("status") != "frozen_before_any_future_jump_or_intensity_outcome_read"
    ):
        raise JumpResearchError("wrong or unfrozen MCS3-J contract")
    boundary = contract.get("action_boundary", {})
    if boundary.get("actionable_arm_id") != "no_trade" or boundary.get(
        "accepted_strategy_arms"
    ):
        raise JumpResearchError("MCS3-J contract does not preserve no_trade")
    if boundary.get("live_allocation_usdt") != 0 or any(
        value is not False
        for key, value in boundary.items()
        if key.endswith("_allowed")
    ):
        raise JumpResearchError("MCS3-J action boundary permits prohibited activity")
    if contract.get("chronology", {}).get("evaluation_end_exclusive") != (
        "2026-01-01T00:00:00Z"
    ):
        raise JumpResearchError("MCS3-J evaluation boundary changed")
    if contract.get("event_definition", {}).get("event_threshold") != 0.5:
        raise JumpResearchError("MCS3-J event threshold changed")
    candidate = contract.get("candidate", {})
    if candidate.get("lambda") != 0.94 or candidate.get("probability_log_loss_clip") != [
        1e-6,
        0.999999,
    ]:
        raise JumpResearchError("MCS3-J candidate parameters changed")
    targets = contract.get("targets")
    if not isinstance(targets, list) or [item.get("horizon") for item in targets] != [
        "4h",
        "1d",
    ] or [item.get("target_blocks") for item in targets] != [1, 6]:
        raise JumpResearchError("MCS3-J target horizons changed")
    if contract.get("statistics", {}).get("same_exact_seed_for_every_bootstrap") is not True:
        raise JumpResearchError("MCS3-J exact bootstrap-seed rule changed")


def _verify_inputs(
    contract: dict[str, Any], contract_path: Path
) -> tuple[dict[str, Path], list[dict[str, str]]]:
    if contract_path != DEFAULT_CONTRACT.resolve(strict=True):
        raise JumpResearchError("only the repository MCS3-J contract may run")
    if sha256_file(contract_path) != CONTRACT_SHA256:
        raise JumpResearchError("frozen MCS3-J contract checksum changed")
    resolved: dict[str, Path] = {}
    verified: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in contract["bound_inputs"]:
        relative = item["path"]
        if relative in seen:
            raise JumpResearchError(f"duplicate bound input: {relative}")
        seen.add(relative)
        resolved[relative] = _require_file(ROOT / relative, item["sha256"], relative)
        verified.append({"path": relative, "sha256": item["sha256"]})
    if S1_MANIFEST not in resolved or S1_CANDLES not in resolved:
        raise JumpResearchError("MCS3-J contract omits required S1 lineage")
    s1 = _load_canonical(resolved[S1_MANIFEST], "S1 manifest")
    if s1.get("experiment_id") != "btc-regime-routing-s1-ledger-v1":
        raise JumpResearchError("wrong S1 lineage experiment")
    if s1.get("holdout_accessed") is not False:
        raise JumpResearchError("S1 lineage accessed the holdout")
    candle_record = s1.get("artifacts", {}).get("candles-5m.jsonl.gz", {})
    candle_contract = next(
        item for item in contract["bound_inputs"] if item["path"] == S1_CANDLES
    )
    if (
        candle_record.get("sha256") != candle_contract["sha256"]
        or candle_record.get("rows") != contract["input_contract"]["expected_rows"]
    ):
        raise JumpResearchError("S1 manifest does not bind the frozen 5m ledger")
    return resolved, verified


def _validate_candle_contract(
    candles: Sequence[CandlePoint], *, development_end_ms: int
) -> None:
    closed_segments: set[str] = set()
    active_segment: str | None = None
    for candle in candles:
        if candle.open_ms >= development_end_ms:
            raise JumpResearchError("candle source contains an ineligible 2026 row")
        if candle.segment != active_segment:
            if active_segment is not None:
                closed_segments.add(active_segment)
            if candle.segment in closed_segments:
                raise JumpResearchError("closed candle segment reappeared")
            active_segment = candle.segment


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    method = getattr(value, "as_dict", None)
    if not callable(method):
        raise JumpResearchError("ledger row does not support canonical serialization")
    result = method()
    if not isinstance(result, dict):
        raise JumpResearchError("ledger row serialization is not an object")
    return result


def _value(row: Any, name: str) -> Any:
    if isinstance(row, dict):
        return row[name]
    return getattr(row, name)


def _measurement_checks(measurements: Sequence[Any], *, event_threshold: float) -> bool:
    seen: set[int] = set()
    previous = -1
    for row in measurements:
        observed = int(_value(row, "observed_ms"))
        rv = float(_value(row, "realized_variance"))
        bpv = float(_value(row, "bipower_variation"))
        jump = float(_value(row, "nonnegative_jump_variation"))
        share = float(_value(row, "jump_share"))
        event = int(_value(row, "event_indicator"))
        if observed in seen or observed <= previous or observed % FOUR_HOURS_MS:
            return False
        if not all(math.isfinite(value) for value in (rv, bpv, jump, share)):
            return False
        if rv < 0 or bpv < 0 or jump < 0 or not 0 <= share <= 1 or event not in (0, 1):
            return False
        expected_jump = max(rv - bpv, 0.0)
        expected_share = expected_jump / rv if rv > 0 else 0.0
        if not math.isclose(jump, expected_jump, rel_tol=1e-12, abs_tol=1e-18):
            return False
        if not math.isclose(share, expected_share, rel_tol=1e-12, abs_tol=1e-15):
            return False
        if event != int(share >= event_threshold):
            return False
        seen.add(observed)
        previous = observed
    return bool(seen)


def _forecast_checks(forecasts: Sequence[Any]) -> bool:
    seen: set[tuple[int, int]] = set()
    for row in forecasts:
        decision = int(_value(row, "decision_ms"))
        target_end = int(_value(row, "target_end_ms"))
        blocks = int(_value(row, "horizon_blocks"))
        identity = (decision, blocks)
        if identity in seen or blocks not in (1, 6):
            return False
        if target_end != decision + blocks * FOUR_HOURS_MS:
            return False
        probabilities = (
            float(_value(row, "candidate_probability")),
            float(_value(row, "control_probability")),
        )
        intensities = (
            float(_value(row, "candidate_intensity")),
            float(_value(row, "control_intensity")),
            float(_value(row, "target_intensity")),
        )
        event = int(_value(row, "target_event"))
        if event not in (0, 1) or any(
            not math.isfinite(value) or not 0 <= value <= 1
            for value in (*probabilities, *intensities)
        ):
            return False
        seen.add(identity)
    return bool(seen)


def _primary_gates(
    contract: dict[str, Any],
    horizon_results: dict[str, dict[str, Any]],
    *,
    measurement_checks_passed: bool,
    forecast_checks_passed: bool,
) -> dict[str, bool]:
    frozen = contract["gates"]
    primary = horizon_results["4h"]
    scores = primary["scores"]
    candidate = scores["candidate"]
    control = scores["control"]
    coverage = primary["coverage"]
    required_years = [str(year) for year in frozen["required_evaluation_years"]]
    annual = scores["annual"]
    leave_one_out = scores["leave_one_year_out"]
    exclusion = scores["excluding_best_three_months"]
    intensity_quartiles = scores["intensity_quartiles"]
    quartile_means = [
        intensity_quartiles[str(index)]["mean_realized_intensity"]
        for index in range(1, 5)
    ]
    brier_bootstrap = scores["month_block_brier_improvement"]
    log_bootstrap = scores["month_block_log_loss_improvement"]
    intensity_bootstrap = scores["month_block_intensity_mse_improvement"]
    spread_bootstrap = scores[
        "month_block_top_minus_bottom_probability_quintile_event_rate"
    ]
    valid_bootstraps = (
        brier_bootstrap,
        log_bootstrap,
        intensity_bootstrap,
        spread_bootstrap,
    )
    return {
        "all_input_causality_common_row_score_domain_isolation_and_replay_checks": measurement_checks_passed
        and forecast_checks_passed,
        "primary_4h_average_precision_above_control": candidate["average_precision"]
        > control["average_precision"],
        "primary_4h_average_precision_ratio_to_prevalence_minimum": scores[
            "event_prevalence"
        ]
        > 0
        and candidate["average_precision"] / scores["event_prevalence"]
        >= frozen["primary_4h_average_precision_ratio_to_prevalence_minimum"],
        "primary_4h_brier_and_log_improvements_positive_after_excluding_each_metrics_best_three_months": exclusion[
            "brier_improvement"
        ]
        > 0
        and exclusion["log_loss_improvement"] > 0,
        "primary_4h_brier_skill_minimum": candidate["brier_skill"]
        >= frozen["primary_4h_brier_skill_minimum"],
        "primary_4h_candidate_brier_strictly_below_control": candidate["mean_brier"]
        < control["mean_brier"],
        "primary_4h_candidate_forecast_mean_inside_event_fraction_wilson_interval": scores[
            "event_fraction_wilson_95"
        ][0]
        <= candidate["forecast_mean"]
        <= scores["event_fraction_wilson_95"][1],
        "primary_4h_candidate_intensity_mae_strictly_below_control": candidate[
            "mean_intensity_mae"
        ]
        < control["mean_intensity_mae"],
        "primary_4h_candidate_intensity_mse_strictly_below_control": candidate[
            "mean_intensity_mse"
        ]
        < control["mean_intensity_mse"],
        "primary_4h_candidate_log_loss_strictly_below_control": candidate[
            "mean_log_loss"
        ]
        < control["mean_log_loss"],
        "primary_4h_effective_observations_minimum": scores["effective_observations"]
        >= frozen["primary_4h_effective_observations_minimum"],
        "primary_4h_event_count_minimum": scores["event_count"]
        >= frozen["primary_4h_event_count_minimum"],
        "primary_4h_event_count_per_year_minimum": all(
            scores["event_count_by_year"].get(year, 0)
            >= frozen["primary_4h_event_count_per_year_minimum"]
            for year in required_years
        ),
        "primary_4h_event_prevalence_maximum": scores["event_prevalence"]
        <= frozen["primary_4h_event_prevalence_maximum"],
        "primary_4h_event_prevalence_minimum": scores["event_prevalence"]
        >= frozen["primary_4h_event_prevalence_minimum"],
        "primary_4h_forecast_count_minimum": scores["observations"]
        >= frozen["primary_4h_forecast_count_minimum"],
        "primary_4h_intensity_improvement_positive_after_excluding_best_three_months": exclusion[
            "intensity_mse_improvement"
        ]
        > 0,
        "primary_4h_intensity_mse_improvement_month_block_lower_95_strictly_above": intensity_bootstrap[
            "ci95"
        ][0]
        > frozen["primary_4h_intensity_mse_improvement_month_block_lower_95_strictly_above"],
        "primary_4h_intensity_quartile_realized_means_non_decreasing": all(
            right >= left for left, right in zip(quartile_means, quartile_means[1:])
        ),
        "primary_4h_joint_annual_event_loss_and_intensity_improvement_years_minimum": sum(
            value["brier_improvement"] > 0
            and value["log_loss_improvement"] > 0
            and value["intensity_mse_improvement"] > 0
            for year, value in annual.items()
            if year in required_years
        )
        >= frozen[
            "primary_4h_joint_annual_event_loss_and_intensity_improvement_years_minimum"
        ],
        "primary_4h_joint_leave_one_year_out_positive_years_minimum": sum(
            value["brier_improvement"] > 0
            and value["log_loss_improvement"] > 0
            and value["intensity_mse_improvement"] > 0
            for year, value in leave_one_out.items()
            if year in required_years
        )
        >= frozen["primary_4h_joint_leave_one_year_out_positive_years_minimum"],
        "primary_4h_log_loss_improvement_month_block_lower_95_strictly_above": log_bootstrap[
            "ci95"
        ][0]
        > frozen["primary_4h_log_loss_improvement_month_block_lower_95_strictly_above"],
        "primary_4h_month_block_brier_improvement_lower_95_strictly_above": brier_bootstrap[
            "ci95"
        ][0]
        > frozen["primary_4h_month_block_brier_improvement_lower_95_strictly_above"],
        "primary_4h_overall_coverage_minimum": coverage["overall"]
        >= frozen["primary_4h_overall_coverage_minimum"],
        "primary_4h_per_year_coverage_minimum": all(
            year in coverage["per_year"]
            and coverage["per_year"][year]["fraction"]
            >= frozen["primary_4h_per_year_coverage_minimum"]
            for year in required_years
        ),
        "primary_4h_probability_calibration_ece_maximum": scores["calibration"]["ece"]
        <= frozen["primary_4h_probability_calibration_ece_maximum"],
        "primary_4h_top_minus_bottom_probability_quintile_event_rate_month_block_lower_95_strictly_above": spread_bootstrap[
            "ci95"
        ][0]
        > frozen[
            "primary_4h_top_minus_bottom_probability_quintile_event_rate_month_block_lower_95_strictly_above"
        ],
        "required_evaluation_years_present": set(coverage["per_year"])
        == set(required_years)
        and set(scores["event_count_by_year"]) == set(required_years)
        and set(annual) == set(required_years)
        and set(leave_one_out) == set(required_years),
        "valid_bootstrap_replications_minimum": all(
            item["valid_replications"] >= frozen["valid_bootstrap_replications_minimum"]
            for item in valid_bootstraps
        ),
    }


def run(
    contract_path: Path = DEFAULT_CONTRACT,
    output_path: Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    contract_path = contract_path.resolve(strict=True)
    contract = _load_canonical(contract_path, "MCS3-J contract")
    _verify_contract(contract)
    resolved_inputs, verified_inputs = _verify_inputs(contract, contract_path)
    import_audit = _audit_imports((MODULE_PATH, RUNNER_PATH))
    if not import_audit["passed"]:
        raise JumpResearchError("MCS3-J import isolation failed")
    destination = _require_output(output_path)

    candle_item = next(
        item for item in contract["bound_inputs"] if item["path"] == S1_CANDLES
    )
    candles = load_candles(
        resolved_inputs[S1_CANDLES],
        candle_item["sha256"],
        contract["input_contract"]["expected_rows"],
    )
    chronology = contract["chronology"]
    development_start = parse_utc_ms(chronology["development_start"])
    development_end = parse_utc_ms(chronology["development_end_exclusive"])
    evaluation_start = parse_utc_ms(chronology["evaluation_start"])
    evaluation_end = parse_utc_ms(chronology["evaluation_end_exclusive"])
    _validate_candle_contract(candles, development_end_ms=development_end)

    measurements, measurement_audit = build_four_hour_jump_observations(
        candles,
        start_ms=development_start,
        end_ms=development_end,
        source_digest=candle_item["sha256"],
        event_threshold=contract["event_definition"]["event_threshold"],
    )
    measurement_checks_passed = _measurement_checks(
        measurements,
        event_threshold=contract["event_definition"]["event_threshold"],
    )
    horizon_results: dict[str, dict[str, Any]] = {}
    all_forecasts: list[Any] = []
    benchmark = contract["benchmark"]
    candidate = contract["candidate"]
    statistics = contract["statistics"]
    for target in contract["targets"]:
        horizon = target["horizon"]
        blocks = int(target["target_blocks"])
        all_horizon_forecasts = build_jump_forecasts(
            measurements,
            blocks,
            lookback_blocks=benchmark["lookback_blocks"],
            decay_lambda=candidate["lambda"],
            threshold=contract["event_definition"]["event_threshold"],
            probability_alpha=benchmark["probability_smoothing_alpha"],
            probability_beta=benchmark["probability_smoothing_beta"],
        )
        forecasts = [
            item
            for item in all_horizon_forecasts
            if evaluation_start <= item.decision_ms < evaluation_end
            and item.target_end_ms < evaluation_end
        ]
        forecast_audit = {
            "all_bound_rows": len(all_horizon_forecasts),
            "evaluation_rows": len(forecasts),
            "excluded_outside_evaluation": len(all_horizon_forecasts) - len(forecasts),
        }
        scores = score_jump_forecasts(
            forecasts,
            bootstrap_replications=statistics["month_block_bootstrap_replications"],
            bootstrap_seed=statistics["month_block_bootstrap_seed"],
            wilson_z=statistics["wilson_z"],
        )
        coverage = calendar_coverage(
            forecasts,
            evaluation_start_ms=evaluation_start,
            evaluation_end_ms=evaluation_end,
            horizon_blocks=blocks,
        )
        horizon_results[horizon] = {
            "coverage": coverage,
            "forecast_build": forecast_audit,
            "scores": scores,
        }
        all_forecasts.extend(forecasts)

    forecast_checks_passed = _forecast_checks(all_forecasts)
    gates = _primary_gates(
        contract,
        horizon_results,
        measurement_checks_passed=measurement_checks_passed,
        forecast_checks_passed=forecast_checks_passed,
    )
    passed = all(gates.values())

    destination.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, dict[str, Any]] = {}
    artifacts["measurements.jsonl.gz"] = write_jsonl_gzip(
        destination / "measurements.jsonl.gz",
        (_as_dict(item) for item in measurements),
    )
    artifacts["forecasts.jsonl.gz"] = write_jsonl_gzip(
        destination / "forecasts.jsonl.gz",
        (
            _as_dict(item)
            for item in sorted(
                all_forecasts,
                key=lambda value: (
                    int(_value(value, "horizon_blocks")),
                    int(_value(value, "decision_ms")),
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
        "decision": "jump_information_accepted_for_future_offline_shock_risk_research"
        if passed
        else "jump_information_rejected",
        "event_definition": contract["event_definition"],
        "experiment_id": contract["experiment_id"],
        "gates": gates,
        "horizons": horizon_results,
        "import_audit": import_audit,
        "information_gate_passed": passed,
        "market_values_used": True,
        "measurement_audit": measurement_audit,
        "no_strategy_pnl_position_cost_execution_or_risk_cap_evaluated": True,
        "partial_ob0_or_2026_accessed": False,
        "promotion_or_live_evidence": False,
        "schema_version": "btc-market-condition-scores-mcs3-j-report-v1",
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
        "schema_version": "btc-market-condition-scores-mcs3-j-evidence-manifest-v1",
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
                "path": "tests/test_research_jump.py",
                "sha256": sha256_file(ROOT / "tests/test_research_jump.py"),
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
