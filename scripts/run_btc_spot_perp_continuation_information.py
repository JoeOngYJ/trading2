#!/usr/bin/env python3
"""Run the frozen BTC spot/perpetual continuation-information experiment offline."""

from __future__ import annotations

import os

# Freeze numerical threading before NumPy or the research module is imported.
for _thread_variable in (
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
):
    os.environ[_thread_variable] = "1"

import argparse
import json
import platform
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import numpy as np

from trading_platform.research_spot_perp_continuation import (
    HORIZON_MS,
    YEAR_2026_MS,
    SpotPerpContinuationError,
    build_feature_rows,
    build_label_rows,
    canonical_json,
    feature_gate_report,
    iso_ms,
    label_gate_report,
    load_daily_pairs,
    load_feature_rows,
    load_label_rows,
    load_needed_five_minute_opens,
    model_report,
    parse_utc_z_ms,
    resolve_effective_contract,
    sha256_file,
    validate_bound_inputs,
    walk_forward,
    write_jsonl_gzip,
)


DEFAULT_CONTRACT = ROOT / "research/btc/contracts/btc-spot-perp-continuation-information-d1-v2.json"
ALLOWED_OUTPUT_PARENT = ROOT / "artifacts/agent-level-experiment/btc-focused"


def _load_canonical(path: Path, label: str) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    value = json.loads(raw)
    if not isinstance(value, dict) or raw != canonical_json(value):
        raise SpotPerpContinuationError(f"non-canonical {label}: {path}")
    return value


def _relative(root: Path, path: Path) -> str:
    return str(path.resolve(strict=False).relative_to(root))


def _require_output_root(root: Path, path: Path) -> Path:
    root = root.resolve(strict=True)
    allowed = (root / ALLOWED_OUTPUT_PARENT.relative_to(ROOT)).resolve(strict=True)
    absolute = path if path.is_absolute() else root / path
    candidate = absolute.resolve(strict=False)
    try:
        candidate.relative_to(allowed)
    except ValueError as exc:
        raise SpotPerpContinuationError("D1 output must remain under the BTC-focused artifact root") from exc
    for component in (candidate, *candidate.parents):
        if component.is_symlink():
            raise SpotPerpContinuationError(f"symlinked output path is prohibited: {component}")
    if candidate.exists() and not candidate.is_dir():
        raise SpotPerpContinuationError("D1 output root exists and is not a directory")
    return candidate


def _phase_paths(output_root: Path, phase: str) -> dict[str, Path]:
    if phase == "features":
        directory = output_root / "features"
        return {
            "directory": directory,
            "ledger": directory / "features.jsonl.gz",
            "report": directory / "feature-gate-report.json",
            "manifest": directory / "evidence-manifest.json",
        }
    if phase == "labels":
        directory = output_root / "labels"
        return {
            "directory": directory,
            "ledger": directory / "labels.jsonl.gz",
            "report": directory / "label-gate-report.json",
            "manifest": directory / "evidence-manifest.json",
        }
    if phase == "model":
        directory = output_root / "model"
        return {
            "directory": directory,
            "forecast": directory / "forecasts.jsonl.gz",
            "snapshots": directory / "model-snapshots.jsonl.gz",
            "report": directory / "report.json",
            "manifest": directory / "evidence-manifest.json",
        }
    raise SpotPerpContinuationError("phase must be features, labels, or model")


def _write_json(path: Path, value: Mapping[str, Any]) -> str:
    if path.exists():
        raise SpotPerpContinuationError(f"refusing to overwrite evidence: {path}")
    path.write_text(canonical_json(value), encoding="utf-8")
    return sha256_file(path)


def _validate_environment(contract: Mapping[str, Any]) -> None:
    expected = contract["environment"]
    if platform.python_version() != expected["python"]:
        raise SpotPerpContinuationError("frozen CPython version mismatch")
    if np.__version__ != expected["numpy"]:
        raise SpotPerpContinuationError("frozen NumPy version mismatch")
    if expected["numeric_type"] != "float64" or expected["canonical_numeric_decimal_places"] != 12:
        raise SpotPerpContinuationError("unsupported frozen numeric contract")
    for key, value in expected["required_thread_environment"].items():
        if os.environ.get(key) != value:
            raise SpotPerpContinuationError(f"frozen thread environment mismatch: {key}")


def _base_lineage(root: Path, contract_path: Path, contract: Mapping[str, Any]) -> list[dict[str, str]]:
    candidates = [
        {"path": _relative(root, contract_path), "sha256": sha256_file(contract_path)},
        {
            "path": "research/btc/contracts/btc-spot-perp-continuation-information-d1-v1.json",
            "sha256": sha256_file(root / "research/btc/contracts/btc-spot-perp-continuation-information-d1-v1.json"),
        },
    ]
    unique: dict[str, dict[str, str]] = {}
    for item in candidates:
        unique[item["path"]] = item
    return list(unique.values())


def _bound_input_lineage(root: Path, contract: Mapping[str, Any]) -> list[dict[str, str]]:
    return [
        {"path": item["path"], "sha256": sha256_file(root / item["path"])}
        for item in contract["bound_inputs"]
    ]


def _write_phase(
    root: Path,
    paths: Mapping[str, Path],
    artifacts: Mapping[str, Any],
    report: dict[str, Any],
    manifest_base: dict[str, Any],
) -> dict[str, Any]:
    directory = paths["directory"]
    if directory.exists():
        raise SpotPerpContinuationError(f"refusing to overwrite phase directory: {directory}")
    directory.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{directory.name}-", dir=directory.parent))
    temporary_paths = {key: temporary / value.name for key, value in paths.items() if key != "directory"}
    try:
        artifact_refs: list[dict[str, str]] = []
        for key, rows in artifacts.items():
            write_jsonl_gzip(temporary_paths[key], rows)
            artifact_refs.append(
                {"path": _relative(root, paths[key]), "sha256": sha256_file(temporary_paths[key])}
            )
        report["artifacts"] = list(artifact_refs)
        report_sha = _write_json(temporary_paths["report"], report)
        artifact_refs.append({"path": _relative(root, paths["report"]), "sha256": report_sha})
        manifest = {**manifest_base, "artifacts": artifact_refs}
        manifest_sha = _write_json(temporary_paths["manifest"], manifest)
        os.replace(temporary, directory)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return {
        **report,
        "manifest": _relative(root, paths["manifest"]),
        "manifest_sha256": manifest_sha,
        "report": _relative(root, paths["report"]),
        "report_sha256": report_sha,
    }


def _validate_phase(
    root: Path, output_root: Path, phase: str, experiment_id: str
) -> tuple[dict[str, Path], dict[str, Any], dict[str, Any]]:
    paths = _phase_paths(output_root, phase)
    report = _load_canonical(paths["report"], f"D1 {phase} report")
    manifest = _load_canonical(paths["manifest"], f"D1 {phase} manifest")
    if report.get("experiment_id") != experiment_id or manifest.get("experiment_id") != experiment_id:
        raise SpotPerpContinuationError(f"D1 {phase} experiment identity mismatch")
    if report.get("phase") != phase or manifest.get("phase") != phase:
        raise SpotPerpContinuationError(f"D1 {phase} phase identity mismatch")
    expected = {_relative(root, path): path for key, path in paths.items() if key not in {"directory", "manifest"}}
    references = manifest.get("artifacts")
    if not isinstance(references, list) or {item.get("path") for item in references} != set(expected):
        raise SpotPerpContinuationError(f"D1 {phase} artifact manifest changed")
    for item in references:
        path = expected[item["path"]]
        if not path.is_file() or sha256_file(path) != item.get("sha256"):
            raise SpotPerpContinuationError(f"D1 {phase} artifact checksum mismatch: {path}")
    return paths, report, manifest


def _source_item(contract: Mapping[str, Any], suffix: str) -> Mapping[str, Any]:
    matches = [item for item in contract["bound_inputs"] if item["path"].endswith(suffix)]
    if len(matches) != 1:
        raise SpotPerpContinuationError(f"expected exactly one bound source ending in {suffix}")
    return matches[0]


def run_features(
    root: Path, contract_path: Path, contract: Mapping[str, Any], output_root: Path
) -> dict[str, Any]:
    paths = _phase_paths(output_root, "features")
    if paths["directory"].exists():
        raise SpotPerpContinuationError("D1 features already exist")
    source = _source_item(contract, "spot-perp-continuation-d0-v3/source-manifest.json")
    pairs = load_daily_pairs(root, contract)
    rows, diagnostics = build_feature_rows(pairs, contract, source["sha256"])
    report = feature_gate_report(rows, diagnostics, contract)
    report.update(
        {
            "contract_path": _relative(root, contract_path),
            "contract_sha256": sha256_file(contract_path),
            "daily_input_count": len(pairs),
            "phase": "features",
            "source_manifest_path": source["path"],
            "source_manifest_sha256": source["sha256"],
        }
    )
    return _write_phase(
        root,
        paths,
        {"ledger": rows},
        report,
        {
            "actionable_arm_id": "no_trade",
            "bound_inputs": _bound_input_lineage(root, contract),
            "contract_lineage": _base_lineage(root, contract_path, contract),
            "experiment_id": contract["experiment_id"],
            "phase": "features",
            "schema_version": "btc-spot-perp-continuation-d1-phase-manifest-v1",
        },
    )


def run_labels(
    root: Path, contract_path: Path, contract: Mapping[str, Any], output_root: Path
) -> dict[str, Any]:
    feature_paths, feature_report, _ = _validate_phase(
        root, output_root, "features", contract["experiment_id"]
    )
    if feature_report.get("feature_gate_passed") is not True:
        raise SpotPerpContinuationError("feature gate did not permit target-source access")
    feature_sha = sha256_file(feature_paths["ledger"])
    features = load_feature_rows(feature_paths["ledger"], feature_sha, contract["experiment_id"])
    needed: set[int] = set()
    for feature in features:
        decision = parse_utc_z_ms(feature["decision_at"], "decision_at")
        if decision + HORIZON_MS < YEAR_2026_MS:
            needed.update((decision, decision + HORIZON_MS))
    source = _source_item(contract, "s1-ledger-v1/candles-5m.jsonl.gz")
    source_manifest_item = _source_item(contract, "s1-ledger-v1/manifest.json")
    source_manifest = _load_canonical(root / source_manifest_item["path"], "S1 source manifest")
    source_artifact = source_manifest.get("artifacts", {}).get("candles-5m.jsonl.gz", {})
    if source_artifact.get("sha256") != source["sha256"]:
        raise SpotPerpContinuationError("S1 manifest and bound five-minute source disagree")
    expected_rows = source_artifact.get("rows")
    if not isinstance(expected_rows, int):
        raise SpotPerpContinuationError("S1 source manifest lacks a frozen row count")
    opens = load_needed_five_minute_opens(
        root / source["path"], source["sha256"], expected_rows, needed
    )
    labels, diagnostics = build_label_rows(features, opens, contract)
    report = label_gate_report(features, labels, diagnostics, contract)
    report.update(
        {
            "contract_path": _relative(root, contract_path),
            "contract_sha256": sha256_file(contract_path),
            "feature_ledger_path": _relative(root, feature_paths["ledger"]),
            "feature_ledger_sha256": feature_sha,
            "five_minute_open_count_loaded": len(opens),
            "five_minute_open_count_requested": len(needed),
            "phase": "labels",
            "target_source_path": source["path"],
            "target_source_sha256": source["sha256"],
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
            "bound_inputs": _bound_input_lineage(root, contract),
            "contract_lineage": _base_lineage(root, contract_path, contract),
            "experiment_id": contract["experiment_id"],
            "feature_manifest": {
                "path": _relative(root, feature_paths["manifest"]),
                "sha256": sha256_file(feature_paths["manifest"]),
            },
            "phase": "labels",
            "schema_version": "btc-spot-perp-continuation-d1-phase-manifest-v1",
        },
    )


def _write_top_manifest(
    root: Path, contract_path: Path, contract: Mapping[str, Any], output_root: Path
) -> tuple[str, str]:
    path = output_root / "evidence-manifest.json"
    if path.exists():
        raise SpotPerpContinuationError("refusing to overwrite D1 top-level evidence manifest")
    phase_refs = []
    artifacts = []
    for phase in ("features", "labels", "model"):
        paths, _, manifest = _validate_phase(root, output_root, phase, contract["experiment_id"])
        phase_refs.append({"path": _relative(root, paths["manifest"]), "sha256": sha256_file(paths["manifest"])})
        artifacts.extend(manifest["artifacts"])
    implementation_paths = [
        root / "src/trading_platform/research_spot_perp_continuation.py",
        root / "scripts/run_btc_spot_perp_continuation_information.py",
    ]
    manifest = {
        "actionable_arm_id": "no_trade",
        "artifacts": artifacts,
        "contract_lineage": _base_lineage(root, contract_path, contract),
        "experiment_id": contract["experiment_id"],
        "implementation": [
            {"path": _relative(root, item), "sha256": sha256_file(item)}
            for item in implementation_paths
        ],
        "no_strategy_cost_pnl_position_order_or_2026_created": True,
        "phase_manifests": phase_refs,
        "schema_version": "btc-spot-perp-continuation-d1-evidence-manifest-v1",
    }
    digest = _write_json(path, manifest)
    return _relative(root, path), digest


def run_model(
    root: Path, contract_path: Path, contract: Mapping[str, Any], output_root: Path
) -> dict[str, Any]:
    feature_paths, feature_report, _ = _validate_phase(root, output_root, "features", contract["experiment_id"])
    label_paths, label_report, _ = _validate_phase(root, output_root, "labels", contract["experiment_id"])
    if feature_report.get("feature_gate_passed") is not True or label_report.get("label_gate_passed") is not True:
        raise SpotPerpContinuationError("feature and label gates did not permit model fitting")
    feature_sha = sha256_file(feature_paths["ledger"])
    label_sha = sha256_file(label_paths["ledger"])
    features = load_feature_rows(feature_paths["ledger"], feature_sha, contract["experiment_id"])
    labels = load_label_rows(label_paths["ledger"], label_sha, contract["experiment_id"])
    forecasts, snapshots = walk_forward(features, labels, contract)
    report = model_report(forecasts, snapshots, contract)
    report.update(
        {
            "contract_path": _relative(root, contract_path),
            "contract_sha256": sha256_file(contract_path),
            "feature_ledger_path": _relative(root, feature_paths["ledger"]),
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
            "contract_lineage": _base_lineage(root, contract_path, contract),
            "experiment_id": contract["experiment_id"],
            "feature_manifest": {
                "path": _relative(root, feature_paths["manifest"]),
                "sha256": sha256_file(feature_paths["manifest"]),
            },
            "label_manifest": {
                "path": _relative(root, label_paths["manifest"]),
                "sha256": sha256_file(label_paths["manifest"]),
            },
            "phase": "model",
            "schema_version": "btc-spot-perp-continuation-d1-phase-manifest-v1",
        },
    )
    top_path, top_sha = _write_top_manifest(root, contract_path, contract, output_root)
    result["evidence_manifest"] = top_path
    result["evidence_manifest_sha256"] = top_sha
    return result


def run(contract_path: Path, output: Path | None, phase: str, root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve(strict=True)
    contract_path = contract_path.resolve(strict=True)
    contract_path.relative_to(root)
    contract = resolve_effective_contract(root, contract_path)
    if contract["experiment_id"] != "btc-spot-perp-continuation-information-d1-v2":
        raise SpotPerpContinuationError("only the frozen D1-v2 experiment may run")
    validate_bound_inputs(root, contract)
    _validate_environment(contract)
    default_root = root / "artifacts/agent-level-experiment/btc-focused/spot-perp-continuation-d1-v2"
    output_root = _require_output_root(root, default_root if output is None else output)
    if phase == "features":
        return run_features(root, contract_path, contract, output_root)
    if phase == "labels":
        return run_labels(root, contract_path, contract, output_root)
    if phase == "model":
        return run_model(root, contract_path, contract, output_root)
    raise SpotPerpContinuationError("invalid D1 phase")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--phase", choices=("features", "labels", "model"), required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    result = run(args.contract, args.output, args.phase, args.root)
    print(json.dumps(result, allow_nan=False, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
