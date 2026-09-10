#!/usr/bin/env python3
"""Independently audit and close the rejected endpoint-valid BTC D1-v3 experiment."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for _entry in (str(ROOT), str(SRC)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from scripts.run_btc_spot_perp_continuation_information_v3 import _validate_phase
from trading_platform.research_spot_perp_continuation import (
    SpotPerpContinuationError,
    canonical_json,
    load_label_rows,
    sha256_file,
    validate_bound_inputs,
)
from trading_platform.research_spot_perp_continuation_v3 import (
    load_endpoint_rows,
    resolve_v3_contract,
    validate_v3_bound_inputs,
)


DEFAULT_CONTRACT = ROOT / "research/btc/contracts/btc-spot-perp-continuation-information-d1-v3.json"
DEFAULT_PRIMARY = ROOT / "artifacts/agent-level-experiment/btc-focused/spot-perp-continuation-d1-v3"
DEFAULT_REPLAY = ROOT / "artifacts/agent-level-experiment/btc-focused/spot-perp-continuation-d1-v3-replay"


def _relative(path: Path) -> str:
    return str(path.resolve(strict=False).relative_to(ROOT))


def _write_json(path: Path, value: dict[str, Any]) -> str:
    if path.exists():
        raise SpotPerpContinuationError(f"refusing to overwrite D1-v3 audit evidence: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value), encoding="utf-8")
    return sha256_file(path)


def _normalized(value: Any, output_root: Path) -> Any:
    prefix = _relative(output_root)
    if isinstance(value, str):
        return "$OUTPUT" + value[len(prefix) :] if value.startswith(prefix) else value
    if isinstance(value, list):
        return [_normalized(item, output_root) for item in value]
    if isinstance(value, dict):
        return {key: _normalized(item, output_root) for key, item in value.items()}
    return value


def _interval_crosses_zero(interval: Any) -> bool:
    return (
        isinstance(interval, list)
        and len(interval) == 2
        and float(interval[0]) <= 0.0 <= float(interval[1])
    )


def _normalized_top_manifest(value: dict[str, Any], output_root: Path) -> dict[str, Any]:
    """Normalize output paths and hashes of JSON that embeds those paths."""
    normalized = _normalized(value, output_root)
    for item in normalized.get("artifacts", []):
        if str(item.get("path", "")).endswith(".json"):
            item["sha256"] = "$OUTPUT_PATH_DEPENDENT_JSON"
    for item in normalized.get("phase_manifests", []):
        item["sha256"] = "$OUTPUT_PATH_DEPENDENT_JSON"
    return normalized


def audit(contract_path: Path, primary: Path, replay: Path) -> dict[str, Any]:
    contract_path = contract_path.resolve(strict=True)
    primary = primary.resolve(strict=True)
    replay = replay.resolve(strict=True)
    contract = resolve_v3_contract(ROOT, contract_path)
    validate_bound_inputs(ROOT, contract)
    validate_v3_bound_inputs(ROOT, contract)
    experiment_id = contract["experiment_id"]
    if experiment_id != "btc-spot-perp-continuation-information-d1-v3":
        raise SpotPerpContinuationError("unexpected D1-v3 experiment identity")

    checks: dict[str, bool] = {}
    phase_evidence: dict[str, dict[str, Any]] = {}
    reports: dict[str, dict[str, Any]] = {}
    for phase in ("endpoints", "labels", "model"):
        primary_paths, primary_report, _ = _validate_phase(
            ROOT, primary, phase, experiment_id
        )
        replay_paths, replay_report, _ = _validate_phase(
            ROOT, replay, phase, experiment_id
        )
        reports[phase] = primary_report
        checks[f"{phase}_semantic_report_identical"] = _normalized(
            primary_report, primary
        ) == _normalized(replay_report, replay)
        names = ("forecast", "snapshots") if phase == "model" else ("ledger",)
        artifacts: dict[str, Any] = {}
        for name in names:
            primary_sha = sha256_file(primary_paths[name])
            replay_sha = sha256_file(replay_paths[name])
            checks[f"{phase}_{name}_byte_identical"] = primary_sha == replay_sha
            artifacts[f"primary_{name}"] = _relative(primary_paths[name])
            artifacts[f"primary_{name}_sha256"] = primary_sha
            artifacts[f"replay_{name}"] = _relative(replay_paths[name])
            artifacts[f"replay_{name}_sha256"] = replay_sha
        for side, paths in (("primary", primary_paths), ("replay", replay_paths)):
            for name in ("manifest", "report"):
                artifacts[f"{side}_{name}"] = _relative(paths[name])
                artifacts[f"{side}_{name}_sha256"] = sha256_file(paths[name])
        phase_evidence[phase] = artifacts

    endpoint_report = reports["endpoints"]
    endpoint_path = primary / "endpoints/endpoints.jsonl.gz"
    endpoint_sha = sha256_file(endpoint_path)
    endpoints = load_endpoint_rows(endpoint_path, endpoint_sha, experiment_id)
    checks.update(
        {
            "endpoint_gate_passed": endpoint_report.get("endpoint_gate_passed") is True,
            "endpoint_count_exact": len(endpoints) == 2209,
            "endpoint_missing_count_zero": endpoint_report.get("missing_endpoint_count") == 0,
            "official_archive_count_exact": endpoint_report.get("archive_count") == 73,
        }
    )

    label_report = reports["labels"]
    label_path = primary / "labels/labels.jsonl.gz"
    label_sha = sha256_file(label_path)
    labels = load_label_rows(label_path, label_sha, experiment_id)
    checks.update(
        {
            "label_gate_passed": label_report.get("label_gate_passed") is True,
            "label_count_exact": len(labels) == 2206,
            "evaluation_label_count_exact": label_report.get("evaluation_label_count") == 1823,
            "all_evaluation_years_have_full_coverage": all(
                value == 1.0 for value in label_report.get("coverage_by_year", {}).values()
            )
            and set(label_report.get("coverage_by_year", {}))
            == {"2021", "2022", "2023", "2024", "2025"},
            "interior_gap_diagnostic_exact": label_report.get(
                "interior_gap_diagnostics", {}
            ).get("candidates_crossing_interior_gaps")
            == 48,
            "no_missing_label_endpoints": label_report.get("diagnostics", {}).get(
                "excluded_missing_exact_endpoint_candidates"
            )
            == 0,
        }
    )

    model_report = reports["model"]
    metrics = model_report.get("model_metrics", {})
    bootstrap = model_report.get("bootstrap", {})
    coefficient = model_report.get("coefficient_stability", {})
    annual = model_report.get("annual_results", {})
    checks.update(
        {
            "information_gate_rejected": model_report.get("information_gate_passed") is False
            and model_report.get("decision") == "D1_information_rejected",
            "forecast_count_exact": model_report.get("forecast_count") == 1823,
            "snapshot_count_exact": model_report.get("snapshot_count") == 60,
            "M1_worse_than_M0": float(metrics.get("M1_MSE", 0.0))
            > float(metrics.get("M0_MSE", 0.0)),
            "M1_worse_than_B0": float(metrics.get("M1_MSE", 0.0))
            > float(metrics.get("B0_MSE", 0.0)),
            "exactly_two_positive_evaluation_years": sum(
                float(value["relative_improvement"]) > 0.0 for value in annual.values()
            )
            == 2,
            "squared_error_interval_crosses_zero": _interval_crosses_zero(
                bootstrap.get("squared_error_improvement", {}).get("ci95")
            ),
            "incremental_rank_ic_interval_crosses_zero": _interval_crosses_zero(
                bootstrap.get("incremental_rank_ic", {}).get("ci95")
            ),
            "residual_spread_interval_crosses_zero": _interval_crosses_zero(
                bootstrap.get("top_minus_bottom_residual", {}).get("ci95")
            ),
            "frozen_continuation_coefficients_have_negative_medians": all(
                float(coefficient.get(name, {}).get("median", 0.0)) < 0.0
                for name in ("basis_impulse_z", "spot_minus_perpetual_turnover_z")
            ),
            "best_months_excluded_result_negative": float(
                model_report.get("best_three_months_excluded_mean_squared_error_improvement", 0.0)
            )
            < 0.0,
            "no_strategy_or_execution_artifact": model_report.get(
                "no_strategy_cost_PnL_position_order_or_2026_created"
            )
            is True,
        }
    )

    primary_top = primary / "evidence-manifest.json"
    replay_top = replay / "evidence-manifest.json"
    primary_top_value = json.loads(primary_top.read_text(encoding="utf-8"))
    replay_top_value = json.loads(replay_top.read_text(encoding="utf-8"))
    checks["top_manifest_semantic_replay_identical"] = _normalized_top_manifest(
        primary_top_value, primary
    ) == _normalized_top_manifest(replay_top_value, replay)
    checks["top_manifest_rejects_and_is_fail_closed"] = (
        primary_top_value.get("schema_version")
        == "btc-spot-perp-continuation-d1-v3-evidence-manifest-v1"
        and primary_top_value.get("actionable_arm_id") == "no_trade"
        and primary_top_value.get("no_strategy_cost_pnl_position_order_or_2026_created")
        is True
    )

    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise SpotPerpContinuationError(f"D1-v3 independent audit failed: {failed}")

    report = {
        "actionable_arm_id": "no_trade",
        "checks": checks,
        "decision": "D1_v3_rejection_independently_reproduced_and_closed",
        "experiment_id": experiment_id,
        "model_result": {
            "B0_MSE": metrics["B0_MSE"],
            "M0_MSE": metrics["M0_MSE"],
            "M1_MSE": metrics["M1_MSE"],
            "M1_relative_MSE_improvement_over_M0": metrics[
                "M1_relative_MSE_improvement_over_M0"
            ],
            "positive_evaluation_years": [
                year
                for year, value in annual.items()
                if float(value["relative_improvement"]) > 0.0
            ],
        },
        "phase_evidence": phase_evidence,
        "root_cause_conclusion": (
            "endpoint evidence repairs the D1-v2 label-rule defect, but the frozen "
            "spot/perpetual continuation variables do not add stable forward information"
        ),
        "strategy_model_pnl_cost_position_order_or_2026_created": False,
    }
    audit_directory = primary / "audit"
    report_path = audit_directory / "audit-report.json"
    report_sha = _write_json(report_path, report)
    manifest = {
        "actionable_arm_id": "no_trade",
        "artifacts": [
            {"path": _relative(primary_top), "sha256": sha256_file(primary_top)},
            {"path": _relative(replay_top), "sha256": sha256_file(replay_top)},
            {"path": _relative(report_path), "sha256": report_sha},
        ],
        "audit_implementation": {
            "path": _relative(Path(__file__)),
            "sha256": sha256_file(Path(__file__)),
        },
        "decision": "rejected_and_closed_after_deterministic_replay",
        "experiment_id": experiment_id,
        "no_strategy_pnl_cost_position_order_2026_or_actionable_route": True,
        "schema_version": "btc-spot-perp-continuation-d1-v3-audit-manifest-v1",
    }
    manifest_path = audit_directory / "evidence-manifest.json"
    manifest_sha = _write_json(manifest_path, manifest)
    return {
        **report,
        "audit_report": _relative(report_path),
        "audit_report_sha256": report_sha,
        "audit_manifest": _relative(manifest_path),
        "audit_manifest_sha256": manifest_sha,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--primary", type=Path, default=DEFAULT_PRIMARY)
    parser.add_argument("--replay", type=Path, default=DEFAULT_REPLAY)
    args = parser.parse_args()
    result = audit(args.contract, args.primary, args.replay)
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))


if __name__ == "__main__":
    main()
