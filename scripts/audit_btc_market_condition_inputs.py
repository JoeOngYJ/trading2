#!/usr/bin/env python3
"""Build the MCS1 metadata-only BTC market-condition input matrix."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from trading_platform.research_market_conditions import (
    InputAvailabilityMatrix,
    InputAvailabilityRecord,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "research/btc/contracts/btc-market-condition-scores-mcs1-v1.json"
DEFAULT_OUTPUT = (
    ROOT / "artifacts/agent-level-experiment/btc-focused/market-condition-scores-mcs1-v1"
)


class MCS1AuditError(ValueError):
    pass


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True) + "\n"


def load_contract(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    value = json.loads(raw)
    if not isinstance(value, dict) or raw != canonical_json(value):
        raise MCS1AuditError("MCS1 contract must be canonical key-sorted JSON")
    if value.get("schema_version") != "btc-market-condition-scores-mcs1-contract-v1":
        raise MCS1AuditError("unsupported MCS1 contract schema")
    if value.get("stage_id") != "MCS1" or value.get("status") != "frozen_before_implementation":
        raise MCS1AuditError("MCS1 contract is not frozen")
    boundary = value.get("action_boundary", {})
    if boundary.get("actionable_arm_id") != "no_trade" or boundary.get("accepted_strategy_arms"):
        raise MCS1AuditError("MCS1 action boundary is not fail-closed")
    for key in (
        "market_data_or_feature_value_deserialization_allowed",
        "model_or_score_fit_allowed",
        "order_intent_creation_allowed",
        "production_signal_creation_allowed",
        "strategy_or_pnl_evaluation_allowed",
    ):
        if boundary.get(key) is not False:
            raise MCS1AuditError(f"MCS1 action boundary permits {key}")
    return value


def parse_utc(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise MCS1AuditError("coverage timestamp is not UTC")
    return parsed


def build_record(raw: dict[str, Any]) -> InputAvailabilityRecord:
    return InputAvailabilityRecord(
        dataset_id=raw["dataset_id"],
        instrument=raw["instrument"],
        status=raw["status"],
        intervals=raw["intervals"],
        supported_axes=raw["supported_axes"],
        candidate_axes=raw["candidate_axes"],
        coverage_start=parse_utc(raw["coverage_start"]),
        coverage_end_exclusive=parse_utc(raw["coverage_end_exclusive"]),
        manifest_path=raw["manifest_path"],
        manifest_sha256=raw["manifest_sha256"],
        point_in_time_ready=raw["point_in_time_ready"],
        segment_policy=raw["segment_policy"],
        blockers=raw["blockers"],
    )


def validate_bound_metadata(contract: dict[str, Any]) -> list[dict[str, str]]:
    verified: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in contract.get("bound_metadata_inputs", []):
        relative = item.get("path")
        expected = item.get("sha256")
        if not isinstance(relative, str) or relative in seen or ".." in Path(relative).parts:
            raise MCS1AuditError(f"invalid or duplicate bound metadata path: {relative}")
        path = ROOT / relative
        if not path.is_file():
            raise MCS1AuditError(f"missing bound metadata input: {relative}")
        actual = sha256_path(path)
        if actual != expected:
            raise MCS1AuditError(f"changed bound metadata input: {relative}")
        verified.append({"path": relative, "sha256": actual})
        seen.add(relative)
    if not verified:
        raise MCS1AuditError("MCS1 contract has no bound metadata inputs")

    record_references = {
        (item["manifest_path"], item["manifest_sha256"])
        for item in contract.get("availability_records", [])
    }
    verified_references = {(item["path"], item["sha256"]) for item in verified}
    if not record_references <= verified_references:
        raise MCS1AuditError("availability record references an unbound metadata input")
    return sorted(verified, key=lambda item: item["path"])


def assert_frozen_axis_dispositions(matrix: InputAvailabilityMatrix) -> None:
    summary = matrix.axis_summary()
    expected_ready = {
        "carry": ["btc_matched_carry_inputs"],
        "downside_tail": ["btc_causal_segmented_candles"],
        "implied_risk": [],
        "jump_change": ["btc_causal_segmented_candles"],
        "liquidity_cost": [],
        "onchain_flow": [],
        "persistence": ["btc_causal_segmented_candles"],
        "reversion": ["btc_causal_segmented_candles"],
        "volatility": ["btc_causal_segmented_candles", "btc_official_daily_close"],
    }
    actual_ready = {axis: values["research_ready"] for axis, values in summary.items()}
    if actual_ready != expected_ready:
        raise MCS1AuditError("MCS1 research-ready axis disposition changed")
    if summary["liquidity_cost"]["proxy_only"] != ["btc_low_frequency_liquidity_proxies"]:
        raise MCS1AuditError("liquidity proxy disposition changed")
    if summary["liquidity_cost"]["blocked_or_absent"] != ["btc_spot_l2_ob0_ob1"]:
        raise MCS1AuditError("L2 blocked disposition changed")
    if summary["implied_risk"]["blocked_or_absent"] != ["btc_deribit_dvol_pilot"]:
        raise MCS1AuditError("DVOL blocked disposition changed")
    if summary["onchain_flow"]["blocked_or_absent"] != ["btc_onchain_flow_sources"]:
        raise MCS1AuditError("on-chain absent disposition changed")


def run(contract_path: Path, output: Path) -> None:
    if output.exists() and any(output.iterdir()):
        raise MCS1AuditError(f"output directory must be absent or empty: {output}")
    contract = load_contract(contract_path)
    verified = validate_bound_metadata(contract)
    matrix = InputAvailabilityMatrix(
        tuple(build_record(item) for item in contract.get("availability_records", []))
    )
    assert_frozen_axis_dispositions(matrix)

    contract_relative = contract_path.relative_to(ROOT).as_posix()
    contract_sha256 = sha256_path(contract_path)
    implementation_relative = "src/trading_platform/research_market_conditions.py"
    runner_relative = "scripts/audit_btc_market_condition_inputs.py"
    implementation_sha256 = sha256_path(ROOT / implementation_relative)
    runner_sha256 = sha256_path(ROOT / runner_relative)

    report = {
        "accepted_strategy_arms": [],
        "actionable_arm_id": "no_trade",
        "availability_matrix": matrix.as_dict(),
        "bound_metadata_inputs_verified": verified,
        "decision": "mcs1_passed_metadata_only",
        "experiment_id": contract["experiment_id"],
        "implementation": {
            "market_condition_contract_path": implementation_relative,
            "market_condition_contract_sha256": implementation_sha256,
        },
        "invariants": {
            "market_data_feature_label_or_pnl_files_opened": 0,
            "market_values_deserialized": False,
            "models_or_scores_fitted": False,
            "order_intents_or_production_signals_created": False,
            "partial_ob0_accessed": False,
            "protected_services_accessed": False,
            "sealed_or_ineligible_2026_accessed": False,
            "strategy_or_pnl_evaluated": False,
        },
        "next_permitted_stage": "MCS2",
        "schema_version": "btc-market-condition-scores-mcs1-report-v1",
        "stage_id": "MCS1",
    }

    output.mkdir(parents=True, exist_ok=True)
    report_path = output / "availability-report.json"
    report_path.write_text(canonical_json(report), encoding="utf-8")
    logical_report_path = contract["output_paths"][0]
    if not isinstance(logical_report_path, str) or not logical_report_path.endswith(
        "/availability-report.json"
    ):
        raise MCS1AuditError("contract does not define the canonical availability report path")
    manifest = {
        "experiment_id": contract["experiment_id"],
        "files": [
            {"path": contract_relative, "sha256": contract_sha256},
            {"path": implementation_relative, "sha256": implementation_sha256},
            {"path": runner_relative, "sha256": runner_sha256},
            {
                "path": logical_report_path,
                "sha256": sha256_path(report_path),
            },
        ],
        "metadata_only": True,
        "schema_version": "btc-market-condition-scores-mcs1-evidence-manifest-v1",
    }
    (output / "evidence-manifest.json").write_text(canonical_json(manifest), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    run(args.contract.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
