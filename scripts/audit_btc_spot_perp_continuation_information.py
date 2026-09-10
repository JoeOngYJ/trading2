#!/usr/bin/env python3
"""Independently close and checksum the rejected BTC D1-v2 information experiment."""

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
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for _entry in (str(ROOT), str(SRC)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from scripts.run_btc_spot_perp_continuation_information import _validate_phase
from trading_platform.research_spot_perp_continuation import (
    SpotPerpContinuationError,
    canonical_json,
    load_feature_rows,
    load_label_rows,
    resolve_effective_contract,
    sha256_file,
    validate_bound_inputs,
)


DEFAULT_CONTRACT = ROOT / "research/btc/contracts/btc-spot-perp-continuation-information-d1-v2.json"
DEFAULT_PRIMARY = ROOT / "artifacts/agent-level-experiment/btc-focused/spot-perp-continuation-d1-v2"
DEFAULT_REPLAY = ROOT / "artifacts/agent-level-experiment/btc-focused/spot-perp-continuation-d1-v2-replay"


def _relative(path: Path) -> str:
    return str(path.resolve(strict=False).relative_to(ROOT))


def _write_json(path: Path, value: dict[str, Any]) -> str:
    if path.exists():
        raise SpotPerpContinuationError(f"refusing to overwrite audit evidence: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value), encoding="utf-8")
    return sha256_file(path)


def _semantic_report(path: Path, phase: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    value.pop("artifacts", None)
    if phase == "labels":
        value.pop("feature_ledger_path", None)
    return value


def audit(contract_path: Path, primary: Path, replay: Path) -> dict[str, Any]:
    contract_path = contract_path.resolve(strict=True)
    primary = primary.resolve(strict=True)
    replay = replay.resolve(strict=True)
    contract = resolve_effective_contract(ROOT, contract_path)
    validate_bound_inputs(ROOT, contract)
    experiment_id = contract["experiment_id"]
    if experiment_id != "btc-spot-perp-continuation-information-d1-v2":
        raise SpotPerpContinuationError("unexpected D1 experiment identity")

    phase_data: dict[str, dict[str, Any]] = {}
    checks: dict[str, bool] = {}
    for phase in ("features", "labels"):
        primary_paths, primary_report, _ = _validate_phase(
            ROOT, primary, phase, experiment_id
        )
        replay_paths, replay_report, _ = _validate_phase(
            ROOT, replay, phase, experiment_id
        )
        ledger_name = "ledger"
        primary_digest = sha256_file(primary_paths[ledger_name])
        replay_digest = sha256_file(replay_paths[ledger_name])
        checks[f"{phase}_ledger_byte_identical"] = primary_digest == replay_digest
        checks[f"{phase}_semantic_report_identical"] = _semantic_report(
            primary_paths["report"], phase
        ) == _semantic_report(replay_paths["report"], phase)
        phase_data[phase] = {
            "primary_ledger": _relative(primary_paths[ledger_name]),
            "primary_ledger_sha256": primary_digest,
            "primary_manifest": _relative(primary_paths["manifest"]),
            "primary_manifest_sha256": sha256_file(primary_paths["manifest"]),
            "primary_report": _relative(primary_paths["report"]),
            "primary_report_sha256": sha256_file(primary_paths["report"]),
            "replay_ledger": _relative(replay_paths[ledger_name]),
            "replay_ledger_sha256": replay_digest,
            "replay_manifest": _relative(replay_paths["manifest"]),
            "replay_manifest_sha256": sha256_file(replay_paths["manifest"]),
            "replay_report": _relative(replay_paths["report"]),
            "replay_report_sha256": sha256_file(replay_paths["report"]),
        }
        if phase == "features":
            checks["feature_gate_passed"] = primary_report.get("feature_gate_passed") is True
            checks["feature_count_exact"] = primary_report.get("feature_count") == 2209
            features = load_feature_rows(
                primary_paths["ledger"], primary_digest, experiment_id
            )
        else:
            checks["label_gate_rejected"] = primary_report.get("label_gate_passed") is False
            checks["only_failing_gate_is_per_year_coverage"] = [
                key for key, passed in primary_report.get("gate_results", {}).items() if not passed
            ] == ["per_year_label_coverage_minimum"]
            checks["2021_coverage_exact"] = (
                primary_report.get("label_counts_by_year", {}).get("2021") == 344
                and primary_report.get("coverage_by_year", {}).get("2021")
                == 344 / 365
            )
            checks["cross_segment_exclusions_exact"] = (
                primary_report.get("diagnostics", {}).get("excluded_cross_segment_candidates")
                == 48
            )
            checks["no_missing_exact_opens"] = (
                primary_report.get("diagnostics", {}).get(
                    "excluded_missing_exact_open_candidates"
                )
                == 0
            )
            checks["zero_invalid_serialized_labels"] = (
                primary_report.get("diagnostics", {}).get("serialized_invalid_labels") == 0
            )
            labels = load_label_rows(primary_paths["ledger"], primary_digest, experiment_id)

    feature_digests = {row["feature_digest"] for row in features}
    checks["all_labels_join_exact_features"] = all(
        row["feature_digest"] in feature_digests for row in labels
    )
    checks["label_count_exact"] = len(labels) == 2158
    checks["model_directory_absent"] = not (primary / "model").exists()
    checks["no_top_manifest_before_audit_close"] = not (primary / "evidence-manifest.json").exists()
    if not all(checks.values()):
        failed = [key for key, passed in checks.items() if not passed]
        raise SpotPerpContinuationError(f"D1 independent audit failed: {failed}")

    audit_directory = primary / "audit"
    audit_report_path = audit_directory / "audit-report.json"
    top_manifest_path = primary / "evidence-manifest.json"
    report = {
        "actionable_arm_id": "no_trade",
        "checks": checks,
        "decision": "D1_v2_rejection_independently_reproduced_and_closed",
        "experiment_id": experiment_id,
        "label_gate_failure": {
            "actual_2021_coverage": 344 / 365,
            "actual_2021_labels": 344,
            "minimum_coverage": 0.95,
            "minimum_labels_needed": 347,
            "shortfall_labels": 3,
        },
        "model_fitted": False,
        "phase_evidence": phase_data,
        "strategy_pnl_cost_position_order_or_2026_created": False,
    }
    audit_report_sha = _write_json(audit_report_path, report)
    artifacts = []
    for phase in phase_data.values():
        for key, value in phase.items():
            if key.endswith("_sha256"):
                continue
            artifacts.append({"path": value, "sha256": phase[f"{key}_sha256"]})
    artifacts.append({"path": _relative(audit_report_path), "sha256": audit_report_sha})
    implementation = [
        ROOT / "src/trading_platform/research_spot_perp_continuation.py",
        ROOT / "scripts/run_btc_spot_perp_continuation_information.py",
        ROOT / "scripts/audit_btc_spot_perp_continuation_information.py",
        ROOT / "research/btc/tests/test_spot_perp_continuation_information.py",
    ]
    manifest = {
        "actionable_arm_id": "no_trade",
        "artifacts": artifacts,
        "contract_lineage": [
            {"path": _relative(contract_path), "sha256": sha256_file(contract_path)},
            {
                "path": "research/btc/contracts/btc-spot-perp-continuation-information-d1-v1.json",
                "sha256": sha256_file(
                    ROOT
                    / "research/btc/contracts/btc-spot-perp-continuation-information-d1-v1.json"
                ),
            },
        ],
        "decision": "rejected_before_model_at_frozen_label_coverage_gate",
        "experiment_id": experiment_id,
        "implementation": [
            {"path": _relative(path), "sha256": sha256_file(path)} for path in implementation
        ],
        "model_fitted": False,
        "no_strategy_pnl_cost_position_order_2026_or_actionable_route": True,
        "schema_version": "btc-spot-perp-continuation-d1-rejection-manifest-v1",
    }
    manifest_sha = _write_json(top_manifest_path, manifest)
    return {
        **report,
        "audit_report": _relative(audit_report_path),
        "audit_report_sha256": audit_report_sha,
        "evidence_manifest": _relative(top_manifest_path),
        "evidence_manifest_sha256": manifest_sha,
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
