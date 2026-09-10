#!/usr/bin/env python3
"""Contract-bound offline TNE2 runner; publication never creates an actionable arm."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Mapping

from trading_platform.btc_cusum_trend_models import (
    EMBARGO,
    LABEL_HORIZON,
    M1_FEATURES,
    M2_ADDITIONAL_FEATURES,
    OUTER_YEARS,
    RIDGE_ALPHAS,
    TOTAL_BOUNDARY_SEPARATION,
    CusumTrendModelError,
    FoldRequirements,
    canonical_digest,
    continuous_outcomes_from_cusum_records,
    evaluate_continuous_models,
    evaluate_tne2_gates,
)
from trading_platform.research_ledger import sha256_file


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_BOUND_ROLES = {
    "source",
    "source_manifest",
    "design",
    "research_standard",
    "mandate",
    "cost_model",
    "event_module",
    "event_runner",
    "event_tests",
    "calibration_script",
    "model_module",
    "model_runner",
    "model_tests",
    "predecessor_result",
}


def _inside_root(root: Path, relative: str, *, must_exist: bool) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise CusumTrendModelError("contract path must be repository-relative")
    resolved_root = root.resolve(strict=True)
    resolved = (resolved_root / candidate).resolve(strict=must_exist)
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise CusumTrendModelError("contract path leaves repository root")
    return resolved


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CusumTrendModelError(f"cannot read {label}") from exc
    if not isinstance(value, dict):
        raise CusumTrendModelError(f"{label} must be a JSON object")
    return value


def _load_contract(path: Path, experiment_id: str, root: Path) -> dict[str, Any]:
    resolved = path.resolve(strict=True)
    resolved_root = root.resolve(strict=True)
    if resolved_root not in resolved.parents:
        raise CusumTrendModelError("contract must be inside repository root")
    contract = _read_json(resolved, "TNE contract")
    if contract.get("experiment_id") != experiment_id:
        raise CusumTrendModelError("exact TNE experiment ID is required")
    if contract.get("status") != "frozen_before_historical_trigger_access":
        raise CusumTrendModelError("TNE contract is not frozen")
    if contract.get("action_boundary", {}).get("actionable_arm_id") != "no_trade":
        raise CusumTrendModelError("TNE contract does not fail closed")
    return contract


def _validate_model_contract(contract: Mapping[str, Any]) -> FoldRequirements:
    rules = contract.get("model_rules")
    if not isinstance(rules, dict):
        raise CusumTrendModelError("model_rules are required")
    expected = {
        "outer_evaluation_years": list(OUTER_YEARS),
        "ridge_alphas": list(RIDGE_ALPHAS),
        "label_horizon_hours": int(LABEL_HORIZON.total_seconds() // 3600),
        "embargo_hours": int(EMBARGO.total_seconds() // 3600),
        "total_boundary_separation_hours": int(
            TOTAL_BOUNDARY_SEPARATION.total_seconds() // 3600
        ),
        "m1_features": list(M1_FEATURES),
        "m2_additional_features": list(M2_ADDITIONAL_FEATURES),
        "bootstrap_repetitions": 10_000,
        "bootstrap_seed": 20260901,
        "bootstrap_method": "circular_moving_block_complete_utc_calendar",
        "bootstrap_block_months": 3,
        "continuation_bootstrap_seed": 20260903,
        "standardization": "training_only",
        "inner_folds": "expanding_chronological",
        "primary_metric": "pooled_oof_mse_normalized_72h_log_return",
    }
    for key, value in expected.items():
        if rules.get(key) != value:
            raise CusumTrendModelError(f"contract/code model rule mismatch: {key}")
    if set(rules) != set(expected) | {"fold_requirements"}:
        raise CusumTrendModelError("model_rules must use the exact frozen schema")
    raw_requirements = rules.get("fold_requirements")
    if not isinstance(raw_requirements, dict):
        raise CusumTrendModelError("fold_requirements are required")
    try:
        requirements = FoldRequirements(**raw_requirements)
    except TypeError as exc:
        raise CusumTrendModelError("fold_requirements schema mismatch") from exc
    if set(raw_requirements) != {
        "min_outer_train",
        "min_outer_evaluation",
        "min_inner_train",
        "min_inner_evaluation",
        "min_inner_folds",
    }:
        raise CusumTrendModelError("fold_requirements must use the exact frozen schema")
    gates = contract.get("model_gates")
    expected_gates = {
        "m1_mse_better_than_m0": True,
        "m2_mse_better_than_m0": True,
        "m2_mse_better_than_m1": True,
        "m2_relative_mse_improvement_minimum": 0.02,
        "m2_month_block_bootstrap_lower_strictly_positive": True,
        "m2_mae_improvement_minimum": 0.0,
        "m2_annual_wins_minimum": 4,
        "m2_best_three_month_exclusion_strictly_positive": True,
        "m2_top_year_positive_improvement_fraction_maximum": 0.5,
        "standalone_pooled_actual_mean_strictly_positive": True,
        "standalone_month_block_bootstrap_lower_strictly_positive": True,
        "standalone_positive_annual_means_minimum": 4,
        "standalone_best_three_event_month_exclusion_strictly_positive": True,
    }
    if gates != expected_gates:
        raise CusumTrendModelError("model_gates do not match the pre-registered evaluator")
    return requirements


def _validate_bound_inputs(contract: Mapping[str, Any], root: Path) -> list[dict[str, str]]:
    values = contract.get("bound_inputs")
    if not isinstance(values, list):
        raise CusumTrendModelError("bound_inputs are required")
    checked: list[dict[str, str]] = []
    roles: set[str] = set()
    paths: set[str] = set()
    for value in values:
        if not isinstance(value, dict):
            raise CusumTrendModelError("invalid bound input")
        relative, role, expected = value.get("path"), value.get("role"), value.get("sha256")
        if not all(isinstance(item, str) for item in (relative, role, expected)):
            raise CusumTrendModelError("bound path, role and checksum are required")
        if relative in paths or role in roles:
            raise CusumTrendModelError("bound paths and roles must be unique")
        path = _inside_root(root, relative, must_exist=True)
        actual = sha256_file(path)
        if actual != expected:
            raise CusumTrendModelError(f"bound input checksum mismatch: {relative}")
        paths.add(relative)
        roles.add(role)
        checked.append({"path": relative, "role": role, "sha256": actual})
    if not REQUIRED_BOUND_ROLES.issubset(roles):
        raise CusumTrendModelError("full TNE1/TNE2 implementation bindings are required")
    return checked


def _output_paths(contract: Mapping[str, Any], root: Path) -> tuple[dict[str, str], dict[str, Path]]:
    outputs = contract.get("outputs", {}).get("model")
    required = ("catalogue", "report", "manifest")
    if not isinstance(outputs, dict) or any(not isinstance(outputs.get(key), str) for key in required):
        raise CusumTrendModelError("model catalogue/report/manifest outputs are required")
    relative = {key: outputs[key] for key in required}
    paths = {key: _inside_root(root, value, must_exist=False) for key, value in relative.items()}
    if len(set(paths.values())) != 3:
        raise CusumTrendModelError("model output paths must be distinct")
    parents = {path.parent for path in paths.values()}
    if len(parents) != 1:
        raise CusumTrendModelError("model outputs must share one atomic publication directory")
    publication_directory = next(iter(parents))
    if publication_directory.exists() or any(path.exists() for path in paths.values()):
        raise CusumTrendModelError("refusing to overwrite existing model artifact")
    return relative, paths


def _phase_paths(contract: Mapping[str, Any], phase: str, root: Path) -> dict[str, Path]:
    configured = contract.get("outputs", {}).get(phase)
    if not isinstance(configured, dict):
        raise CusumTrendModelError(f"{phase} prerequisite paths are required")
    result: dict[str, Path] = {}
    for key in ("catalogue", "report", "manifest"):
        if not isinstance(configured.get(key), str):
            raise CusumTrendModelError(f"{phase} {key} path is required")
        result[key] = _inside_root(root, configured[key], must_exist=True)
    return result


def _validate_phase_manifest(
    contract: Mapping[str, Any], phase: str, root: Path, contract_sha: str
) -> tuple[dict[str, Path], dict[str, Any], dict[str, Any]]:
    paths = _phase_paths(contract, phase, root)
    report = _read_json(paths["report"], f"TNE1 {phase} report")
    manifest = _read_json(paths["manifest"], f"TNE1 {phase} manifest")
    experiment_id = contract["experiment_id"]
    if manifest.get("experiment_id") != experiment_id or manifest.get("phase") != phase:
        raise CusumTrendModelError(f"TNE1 {phase} manifest identity mismatch")
    if manifest.get("contract_sha256") != contract_sha:
        raise CusumTrendModelError(f"TNE1 {phase} manifest contract mismatch")
    artifacts = {
        item.get("path"): item.get("sha256")
        for item in manifest.get("artifacts", [])
        if isinstance(item, dict)
    }
    configured = contract["outputs"][phase]
    for key in ("catalogue", "report"):
        relative = configured[key]
        if artifacts.get(relative) != sha256_file(paths[key]):
            raise CusumTrendModelError(f"TNE1 {phase} artifact checksum mismatch")
    if report.get("experiment_id") != experiment_id or report.get("contract_sha256") != contract_sha:
        raise CusumTrendModelError(f"TNE1 {phase} report lineage mismatch")
    return paths, report, manifest


def _read_jsonl_gzip(path: Path, label: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise CusumTrendModelError(f"{label} line {line_number} is not an object")
                rows.append(value)
    except (OSError, json.JSONDecodeError) as exc:
        raise CusumTrendModelError(f"cannot read {label}") from exc
    return rows


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, allow_nan=False, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _prediction_bytes(records: list[dict[str, Any]]) -> bytes:
    raw = b"".join(
        (json.dumps(row, allow_nan=False, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        for row in records
    )
    return gzip.compress(raw, compresslevel=9, mtime=0)


def _publish_atomic(payloads: Mapping[Path, bytes]) -> None:
    parents = {path.parent for path in payloads}
    if len(parents) != 1:
        raise CusumTrendModelError("atomic payloads must share one directory")
    destination_directory = next(iter(parents))
    destination_directory.parent.mkdir(parents=True, exist_ok=True)
    staged_directory = Path(
        tempfile.mkdtemp(
            prefix=f".{destination_directory.name}.",
            suffix=".tmp",
            dir=destination_directory.parent,
        )
    )
    try:
        for destination, content in payloads.items():
            staged = staged_directory / destination.name
            with staged.open("xb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
        directory_descriptor = os.open(staged_directory, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
        if destination_directory.exists():
            raise CusumTrendModelError("model output appeared during atomic publication")
        os.rename(staged_directory, destination_directory)
    finally:
        if staged_directory.exists():
            shutil.rmtree(staged_directory)


def run(contract_path: Path, experiment_id: str, root: Path) -> dict[str, Any]:
    root = root.resolve(strict=True)
    contract_path = contract_path.resolve(strict=True)
    contract = _load_contract(contract_path, experiment_id, root)
    requirements = _validate_model_contract(contract)
    relative, outputs = _output_paths(contract, root)
    bound_inputs = _validate_bound_inputs(contract, root)
    contract_sha = sha256_file(contract_path)

    trigger_paths, trigger_report, trigger_manifest = _validate_phase_manifest(
        contract, "trigger", root, contract_sha
    )
    label_paths, label_report, label_manifest = _validate_phase_manifest(
        contract, "label", root, contract_sha
    )
    # This is the last check before any target value is deserialized.
    if label_report.get("model_phase_allowed") is not True:
        raise CusumTrendModelError("TNE1 label gates do not permit model phase")
    if label_report.get("trigger_report_sha256") != sha256_file(trigger_paths["report"]):
        raise CusumTrendModelError("label report does not bind the trigger report")

    trigger_records = _read_jsonl_gzip(trigger_paths["catalogue"], "trigger catalogue")
    label_records = _read_jsonl_gzip(label_paths["catalogue"], "label catalogue")
    if any(record.get("experiment_id") != experiment_id for record in trigger_records):
        raise CusumTrendModelError("trigger record experiment ID differs from contract")
    if any(record.get("experiment_id") != experiment_id for record in label_records):
        raise CusumTrendModelError("label record experiment ID differs from contract")
    observations = continuous_outcomes_from_cusum_records(trigger_records, label_records)
    evaluation = evaluate_continuous_models(
        observations,
        requirements=requirements,
        bootstrap_repetitions=10_000,
        bootstrap_seed=20260901,
    )
    gates = evaluate_tne2_gates(evaluation)
    observations_by_id = {row.event_id: row for row in observations}
    trigger_digests = {str(row["trigger_id"]): str(row["record_digest"]) for row in trigger_records}
    label_digests = {str(row["trigger_id"]): str(row["record_digest"]) for row in label_records}
    prediction_records: list[dict[str, Any]] = []
    for prediction in evaluation.predictions:
        observation = observations_by_id[prediction.event_id]
        payload = {
            "actionable_arm_id": "no_trade",
            **prediction.as_dict(),
            "experiment_id": experiment_id,
            "feature_digest": observation.feature_digest,
            "label_record_digest": label_digests[prediction.event_id],
            "observation_record_digest": observation.as_dict()["record_digest"],
            "source_digest": observation.source_digest,
            "trigger_record_digest": trigger_digests[prediction.event_id],
        }
        prediction_records.append({**payload, "record_digest": canonical_digest(payload)})
    prediction_content = _prediction_bytes(prediction_records)
    prediction_sha = hashlib.sha256(prediction_content).hexdigest()
    contract_relative = str(contract_path.relative_to(root))
    report = {
        "actionable_arm_id": "no_trade",
        "contract_path": contract_relative,
        "contract_sha256": contract_sha,
        "effective_contract_digest": canonical_digest(contract),
        "evaluation": evaluation.as_dict(),
        "experiment_id": experiment_id,
        "gate_decision": gates.as_dict(),
        "model_phase": "tne2_continuous_outcome",
        "observation_count": len(observations),
        "output": relative["catalogue"],
        "output_sha256": prediction_sha,
        "prediction_count": len(prediction_records),
        "strategy_or_pnl_evaluated": False,
        "trigger_manifest_sha256": sha256_file(trigger_paths["manifest"]),
        "label_manifest_sha256": sha256_file(label_paths["manifest"]),
    }
    report_content = _json_bytes(report)
    report_sha = hashlib.sha256(report_content).hexdigest()
    manifest = {
        "actionable_arm_id": "no_trade",
        "artifacts": [
            {"path": relative["catalogue"], "sha256": prediction_sha},
            {"path": relative["report"], "sha256": report_sha},
        ],
        "bound_inputs": bound_inputs,
        "contract_path": contract_relative,
        "contract_sha256": contract_sha,
        "experiment_id": experiment_id,
        "phase": "model",
        "prerequisites": [
            {"path": contract["outputs"]["trigger"]["manifest"], "sha256": sha256_file(trigger_paths["manifest"])},
            {"path": contract["outputs"]["label"]["manifest"], "sha256": sha256_file(label_paths["manifest"])},
        ],
    }
    manifest_content = _json_bytes(manifest)
    _publish_atomic(
        {
            outputs["catalogue"]: prediction_content,
            outputs["report"]: report_content,
            outputs["manifest"]: manifest_content,
        }
    )
    return {
        **report,
        "manifest": relative["manifest"],
        "manifest_sha256": hashlib.sha256(manifest_content).hexdigest(),
        "report": relative["report"],
        "report_sha256": report_sha,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    result = run(args.contract, args.experiment_id, args.root)
    print(json.dumps(result, allow_nan=False, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
