#!/usr/bin/env python3
"""Run the frozen endpoint-only BTC continuation D1-v3 experiment offline."""

from __future__ import annotations

import os

for _thread_variable in (
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
):
    os.environ[_thread_variable] = "1"

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for _entry in (str(ROOT), str(SRC)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from scripts.run_btc_spot_perp_continuation_information import (
    _load_canonical,
    _relative,
    _require_output_root,
    _validate_environment,
    _write_json,
    _write_phase,
)
from trading_platform.research_spot_perp_continuation import (
    SpotPerpContinuationError,
    label_gate_report,
    load_feature_rows,
    load_label_rows,
    load_needed_five_minute_opens,
    model_report,
    sha256_file,
    validate_bound_inputs,
    walk_forward,
)
from trading_platform.research_spot_perp_continuation_v3 import (
    V2_EXPERIMENT_ID,
    build_endpoint_label_rows,
    endpoint_gate_report,
    load_endpoint_rows,
    load_official_endpoints,
    relevant_gap_diagnostics,
    requested_endpoint_timestamps,
    resolve_v3_contract,
    validate_v3_bound_inputs,
)


DEFAULT_CONTRACT = ROOT / "research/btc/contracts/btc-spot-perp-continuation-information-d1-v3.json"
DEFAULT_OUTPUT = ROOT / "artifacts/agent-level-experiment/btc-focused/spot-perp-continuation-d1-v3"


def _phase_paths(output_root: Path, phase: str) -> dict[str, Path]:
    if phase == "endpoints":
        directory = output_root / "endpoints"
        return {
            "directory": directory,
            "ledger": directory / "endpoints.jsonl.gz",
            "manifest": directory / "evidence-manifest.json",
            "report": directory / "endpoint-gate-report.json",
        }
    if phase == "labels":
        directory = output_root / "labels"
        return {
            "directory": directory,
            "ledger": directory / "labels.jsonl.gz",
            "manifest": directory / "evidence-manifest.json",
            "report": directory / "label-gate-report.json",
        }
    if phase == "model":
        directory = output_root / "model"
        return {
            "directory": directory,
            "forecast": directory / "forecasts.jsonl.gz",
            "manifest": directory / "evidence-manifest.json",
            "report": directory / "report.json",
            "snapshots": directory / "model-snapshots.jsonl.gz",
        }
    raise SpotPerpContinuationError("D1-v3 phase must be endpoints, labels, or model")


def _contract_lineage(root: Path, contract_path: Path, contract: Mapping[str, Any]) -> list[dict[str, str]]:
    v2_path = root / contract["v3_spec"]["base_contract"]["path"]
    v1_path = root / "research/btc/contracts/btc-spot-perp-continuation-information-d1-v1.json"
    return [
        {"path": _relative(root, contract_path), "sha256": sha256_file(contract_path)},
        {"path": _relative(root, v2_path), "sha256": sha256_file(v2_path)},
        {"path": _relative(root, v1_path), "sha256": sha256_file(v1_path)},
    ]


def _v3_bound_lineage(root: Path, contract: Mapping[str, Any]) -> list[dict[str, str]]:
    return [
        {"path": item["path"], "sha256": sha256_file(root / item["path"])}
        for item in contract["v3_spec"]["bound_inputs"]
    ]


def _validate_phase(
    root: Path, output_root: Path, phase: str, experiment_id: str
) -> tuple[dict[str, Path], dict[str, Any], dict[str, Any]]:
    paths = _phase_paths(output_root, phase)
    report = _load_canonical(paths["report"], f"D1-v3 {phase} report")
    manifest = _load_canonical(paths["manifest"], f"D1-v3 {phase} manifest")
    if (
        report.get("experiment_id") != experiment_id
        or manifest.get("experiment_id") != experiment_id
        or report.get("phase") != phase
        or manifest.get("phase") != phase
        or manifest.get("actionable_arm_id") != "no_trade"
    ):
        raise SpotPerpContinuationError(f"D1-v3 {phase} identity changed")
    expected = {
        _relative(root, path): path
        for key, path in paths.items()
        if key not in {"directory", "manifest"}
    }
    references = manifest.get("artifacts")
    if not isinstance(references, list) or {item.get("path") for item in references} != set(expected):
        raise SpotPerpContinuationError(f"D1-v3 {phase} manifest artifact set changed")
    for item in references:
        path = expected[item["path"]]
        if not path.is_file() or sha256_file(path) != item.get("sha256"):
            raise SpotPerpContinuationError(f"D1-v3 {phase} artifact checksum mismatch")
    return paths, report, manifest


def _load_features(root: Path, contract: Mapping[str, Any]) -> tuple[list[dict[str, Any]], Path, str]:
    item = next(
        value
        for value in contract["v3_spec"]["bound_inputs"]
        if value["path"].endswith("d1-v2/features/features.jsonl.gz")
    )
    path = root / item["path"]
    rows = load_feature_rows(path, item["sha256"], V2_EXPERIMENT_ID)
    return rows, path, item["sha256"]


def _load_s1_opens(root: Path, contract: Mapping[str, Any], needed: set[int]):
    source = next(
        value
        for value in contract["v3_spec"]["bound_inputs"]
        if value["path"].endswith("s1-ledger-v1/candles-5m.jsonl.gz")
    )
    manifest_item = next(
        value
        for value in contract["v3_spec"]["bound_inputs"]
        if value["path"].endswith("s1-ledger-v1/manifest.json")
    )
    manifest = _load_canonical(root / manifest_item["path"], "S1 source manifest")
    artifact = manifest.get("artifacts", {}).get("candles-5m.jsonl.gz", {})
    if artifact.get("sha256") != source["sha256"] or not isinstance(artifact.get("rows"), int):
        raise SpotPerpContinuationError("D1-v3 S1 source manifest changed")
    return load_needed_five_minute_opens(
        root / source["path"], source["sha256"], artifact["rows"], needed
    )


def run_endpoints(
    root: Path, contract_path: Path, contract: Mapping[str, Any], output_root: Path
) -> dict[str, Any]:
    paths = _phase_paths(output_root, "endpoints")
    if paths["directory"].exists():
        raise SpotPerpContinuationError("D1-v3 endpoint phase already exists")
    features, feature_path, feature_sha = _load_features(root, contract)
    needed = requested_endpoint_timestamps(features)
    s1_opens = _load_s1_opens(root, contract, needed)
    rows, diagnostics = load_official_endpoints(root, contract, needed, s1_opens)
    report = endpoint_gate_report(diagnostics, contract)
    report.update(
        {
            "contract_path": _relative(root, contract_path),
            "contract_sha256": sha256_file(contract_path),
            "feature_ledger_path": _relative(root, feature_path),
            "feature_ledger_sha256": feature_sha,
            "phase": "endpoints",
        }
    )
    return _write_phase(
        root,
        paths,
        {"ledger": rows},
        report,
        {
            "actionable_arm_id": "no_trade",
            "bound_inputs": _v3_bound_lineage(root, contract),
            "contract_lineage": _contract_lineage(root, contract_path, contract),
            "experiment_id": contract["experiment_id"],
            "phase": "endpoints",
            "schema_version": "btc-spot-perp-continuation-d1-v3-phase-manifest-v1",
        },
    )


def run_labels(
    root: Path, contract_path: Path, contract: Mapping[str, Any], output_root: Path
) -> dict[str, Any]:
    endpoint_paths, endpoint_report, _ = _validate_phase(
        root, output_root, "endpoints", contract["experiment_id"]
    )
    if endpoint_report.get("endpoint_gate_passed") is not True:
        raise SpotPerpContinuationError("D1-v3 endpoint gate did not permit labels")
    endpoint_sha = sha256_file(endpoint_paths["ledger"])
    endpoints = load_endpoint_rows(endpoint_paths["ledger"], endpoint_sha, contract["experiment_id"])
    features, feature_path, feature_sha = _load_features(root, contract)
    manifest_item = next(
        value
        for value in contract["v3_spec"]["bound_inputs"]
        if value["path"].endswith("validated/development-2017-2025-manifest.json")
    )
    validated_manifest = _load_canonical(
        root / manifest_item["path"], "validated development source manifest"
    )
    gap_map, gap_diagnostics = relevant_gap_diagnostics(features, validated_manifest)
    labels, diagnostics = build_endpoint_label_rows(features, endpoints, gap_map, contract)
    report = label_gate_report(features, labels, diagnostics, contract)
    report.update(
        {
            "contract_path": _relative(root, contract_path),
            "contract_sha256": sha256_file(contract_path),
            "endpoint_ledger_path": _relative(root, endpoint_paths["ledger"]),
            "endpoint_ledger_sha256": endpoint_sha,
            "feature_ledger_path": _relative(root, feature_path),
            "feature_ledger_sha256": feature_sha,
            "interior_gap_diagnostics": gap_diagnostics,
            "phase": "labels",
        }
    )
    paths = _phase_paths(output_root, "labels")
    return _write_phase(
        root,
        paths,
        {"ledger": labels},
        report,
        {
            "actionable_arm_id": "no_trade",
            "contract_lineage": _contract_lineage(root, contract_path, contract),
            "endpoint_manifest": {
                "path": _relative(root, endpoint_paths["manifest"]),
                "sha256": sha256_file(endpoint_paths["manifest"]),
            },
            "experiment_id": contract["experiment_id"],
            "phase": "labels",
            "schema_version": "btc-spot-perp-continuation-d1-v3-phase-manifest-v1",
        },
    )


def _write_top_manifest(
    root: Path, contract_path: Path, contract: Mapping[str, Any], output_root: Path
) -> tuple[str, str]:
    path = output_root / "evidence-manifest.json"
    phase_refs = []
    artifacts = []
    for phase in ("endpoints", "labels", "model"):
        paths, _, manifest = _validate_phase(root, output_root, phase, contract["experiment_id"])
        phase_refs.append(
            {"path": _relative(root, paths["manifest"]), "sha256": sha256_file(paths["manifest"])}
        )
        artifacts.extend(manifest["artifacts"])
    implementations = [
        root / "src/trading_platform/research_spot_perp_continuation.py",
        root / "src/trading_platform/research_spot_perp_continuation_v3.py",
        root / "scripts/run_btc_spot_perp_continuation_information_v3.py",
    ]
    manifest = {
        "actionable_arm_id": "no_trade",
        "artifacts": artifacts,
        "contract_lineage": _contract_lineage(root, contract_path, contract),
        "experiment_id": contract["experiment_id"],
        "implementation": [
            {"path": _relative(root, item), "sha256": sha256_file(item)}
            for item in implementations
        ],
        "no_strategy_cost_pnl_position_order_or_2026_created": True,
        "phase_manifests": phase_refs,
        "schema_version": "btc-spot-perp-continuation-d1-v3-evidence-manifest-v1",
    }
    return _relative(root, path), _write_json(path, manifest)


def run_model(
    root: Path, contract_path: Path, contract: Mapping[str, Any], output_root: Path
) -> dict[str, Any]:
    label_paths, label_report, _ = _validate_phase(
        root, output_root, "labels", contract["experiment_id"]
    )
    if label_report.get("label_gate_passed") is not True:
        raise SpotPerpContinuationError("D1-v3 label gate did not permit model fitting")
    features, feature_path, feature_sha = _load_features(root, contract)
    label_sha = sha256_file(label_paths["ledger"])
    labels = load_label_rows(label_paths["ledger"], label_sha, contract["experiment_id"])
    forecasts, snapshots = walk_forward(features, labels, contract)
    report = model_report(forecasts, snapshots, contract)
    report.update(
        {
            "contract_path": _relative(root, contract_path),
            "contract_sha256": sha256_file(contract_path),
            "feature_ledger_path": _relative(root, feature_path),
            "feature_ledger_sha256": feature_sha,
            "label_ledger_path": _relative(root, label_paths["ledger"]),
            "label_ledger_sha256": label_sha,
            "phase": "model",
        }
    )
    paths = _phase_paths(output_root, "model")
    result = _write_phase(
        root,
        paths,
        {"forecast": forecasts, "snapshots": snapshots},
        report,
        {
            "actionable_arm_id": "no_trade",
            "contract_lineage": _contract_lineage(root, contract_path, contract),
            "experiment_id": contract["experiment_id"],
            "label_manifest": {
                "path": _relative(root, label_paths["manifest"]),
                "sha256": sha256_file(label_paths["manifest"]),
            },
            "phase": "model",
            "schema_version": "btc-spot-perp-continuation-d1-v3-phase-manifest-v1",
        },
    )
    top_path, top_sha = _write_top_manifest(root, contract_path, contract, output_root)
    result["evidence_manifest"] = top_path
    result["evidence_manifest_sha256"] = top_sha
    return result


def run(
    contract_path: Path, output: Path | None, phase: str, root: Path = ROOT
) -> dict[str, Any]:
    root = root.resolve(strict=True)
    contract_path = contract_path.resolve(strict=True)
    contract_path.relative_to(root)
    contract = resolve_v3_contract(root, contract_path)
    validate_bound_inputs(root, contract)
    validate_v3_bound_inputs(root, contract)
    _validate_environment(contract)
    output_root = _require_output_root(root, DEFAULT_OUTPUT if output is None else output)
    if phase == "endpoints":
        return run_endpoints(root, contract_path, contract, output_root)
    if phase == "labels":
        return run_labels(root, contract_path, contract, output_root)
    if phase == "model":
        return run_model(root, contract_path, contract, output_root)
    raise SpotPerpContinuationError("invalid D1-v3 phase")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--phase", choices=("endpoints", "labels", "model"), required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    result = run(args.contract, args.output, args.phase, args.root)
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))


if __name__ == "__main__":
    main()
