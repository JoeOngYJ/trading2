#!/usr/bin/env python3
"""Run the frozen metadata-only BTC MCS3-C readiness audit."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_platform.research_carry_readiness import (  # noqa: E402
    CarryReadinessError,
    evaluate_mcs3_c_readiness,
)


DEFAULT_CONTRACT = ROOT / "research/btc/contracts/btc-market-condition-scores-mcs3-c-readiness-v1.json"
DEFAULT_OUTPUT = ROOT / "artifacts/agent-level-experiment/btc-focused/market-condition-scores-mcs3-c-readiness-v1"
CONTRACT_SHA256 = "9ca6fd35d7e10d90eced628e367641ad63653c993a5719537a8fdef309b72c24"
OUTPUT_ROOT = (ROOT / "artifacts/agent-level-experiment/btc-focused").resolve(strict=True)
MODULE_PATH = ROOT / "src/trading_platform/research_carry_readiness.py"
RUNNER_PATH = Path(__file__).resolve()
TEST_PATH = ROOT / "tests/test_research_carry_readiness.py"


def canonical_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_canonical(path: Path, label: str) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CarryReadinessError(f"invalid {label} JSON") from exc
    accepted = {canonical_json(value), json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"}
    if not isinstance(value, dict) or raw not in accepted:
        raise CarryReadinessError(f"non-canonical {label}")
    return value


def load_bound_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CarryReadinessError(f"invalid {label} JSON") from exc
    if not isinstance(value, dict):
        raise CarryReadinessError(f"non-object {label}")
    return value


def require_file(relative: str, expected_sha256: str) -> Path:
    path = ROOT / relative
    absolute = path.absolute()
    for component in (absolute, *absolute.parents):
        if component.is_symlink():
            raise CarryReadinessError(f"symlinked input prohibited: {relative}")
    resolved = path.resolve(strict=True)
    try:
        resolved.relative_to(ROOT)
    except ValueError as exc:
        raise CarryReadinessError(f"input escapes repository: {relative}") from exc
    lowered = relative.lower()
    if "ob0" in lowered or "holdout" in lowered or "2026-01-07" in lowered:
        raise CarryReadinessError(f"prohibited input path: {relative}")
    if sha256_file(resolved) != expected_sha256:
        raise CarryReadinessError(f"input checksum mismatch: {relative}")
    return resolved


def require_output(path: Path) -> Path:
    absolute = path.absolute()
    for component in (absolute, *absolute.parents):
        if component.exists() and component.is_symlink():
            raise CarryReadinessError("symlinked output path prohibited")
    resolved = path.resolve(strict=False)
    try:
        resolved.relative_to(OUTPUT_ROOT)
    except ValueError as exc:
        raise CarryReadinessError("output escapes BTC-focused artifact root") from exc
    if resolved.exists() and (not resolved.is_dir() or any(resolved.iterdir())):
        raise CarryReadinessError("output must be absent or an empty directory")
    return resolved


def run(contract_path: Path = DEFAULT_CONTRACT, output_path: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    contract_path = contract_path.resolve(strict=True)
    if contract_path != DEFAULT_CONTRACT.resolve(strict=True):
        raise CarryReadinessError("only the repository readiness contract may run")
    if sha256_file(contract_path) != CONTRACT_SHA256:
        raise CarryReadinessError("frozen readiness contract checksum changed")
    contract = load_canonical(contract_path, "readiness contract")
    if (
        contract.get("schema_version")
        != "btc-market-condition-scores-mcs3-c-readiness-contract-v1"
        or contract.get("status") != "frozen_before_automated_metadata_readiness_audit"
    ):
        raise CarryReadinessError("wrong or unfrozen readiness contract")
    boundary = contract.get("action_boundary", {})
    if boundary.get("actionable_arm_id") != "no_trade" or boundary.get("accepted_strategy_arms"):
        raise CarryReadinessError("readiness contract does not preserve no_trade")
    if boundary.get("live_allocation_usdt") != 0 or any(
        value is not False
        for key, value in boundary.items()
        if key.endswith("_allowed")
    ):
        raise CarryReadinessError("readiness contract crosses authority boundary")

    resolved: dict[str, Path] = {}
    verified: list[dict[str, str]] = []
    for item in contract["bound_inputs"]:
        relative = item["path"]
        if relative in resolved:
            raise CarryReadinessError(f"duplicate bound input: {relative}")
        resolved[relative] = require_file(relative, item["sha256"])
        verified.append({"path": relative, "sha256": item["sha256"]})

    def load(relative: str) -> dict[str, Any]:
        return load_bound_json(resolved[relative], relative)

    readiness = evaluate_mcs3_c_readiness(
        contract=contract,
        mcs1_report=load("artifacts/agent-level-experiment/btc-focused/market-condition-scores-mcs1-v1/availability-report.json"),
        qualification_report=load("artifacts/agent-level-experiment/btc-focused/carry-data-qualification-v1/audit-report.json"),
        recovery_report=load("artifacts/agent-level-experiment/btc-focused/carry-gap-recovery-v1/audit-report.json"),
        carry_contract=load("research/btc/contracts/btc-positive-funding-carry-v1.json"),
        carry_report=load("artifacts/agent-level-experiment/btc-focused/positive-funding-carry-v1/report.json"),
        research_mandate=load("config/mandates/retail-btc-delta-neutral-research-v1.json"),
        development_mandate=load("config/mandates/retail-btc-delta-neutral-development-v2.json"),
    )
    passed = readiness["mcs3_c_contract_freeze_permitted"]
    report = {
        "accepted_market_condition_scores": [],
        "accepted_strategy_arms": [],
        "actionable_arm_id": "no_trade",
        "audit_id": contract["audit_id"],
        "bound_inputs": verified,
        "contract_sha256": sha256_file(contract_path),
        "decision": "mcs3_c_ready_for_separate_contract" if passed else "mcs3_c_blocked_not_activated",
        "market_data_values_deserialized": False,
        "mcs3_c_score_or_model_fitted": False,
        "partial_ob0_or_2026_accessed": False,
        "readiness": readiness,
        "schema_version": "btc-market-condition-scores-mcs3-c-readiness-report-v1",
        "strategy_position_pnl_order_or_risk_cap_evaluated": False,
        "supplementary_constraints": [
            "historical_price_rows_do_not_emit_explicit_per_row_available_at",
            "funding_runner_must_use_actual_calc_time_or_a_frozen_conservative_delay_not_only_scheduled_time",
            "spot_segments_must_propagate_unknown_and_reset_without_interpolation",
            "all_2020_2025_carry_history_is_consumed_development_evidence",
        ],
    }
    destination = require_output(output_path)
    destination.mkdir(parents=True, exist_ok=True)
    report_path = destination / "readiness-report.json"
    report_path.write_text(canonical_json(report), encoding="utf-8")
    manifest = {
        "artifacts": {
            "readiness-report.json": {
                "bytes": report_path.stat().st_size,
                "sha256": sha256_file(report_path),
            }
        },
        "audit_id": contract["audit_id"],
        "bound_inputs": verified,
        "contract_sha256": sha256_file(contract_path),
        "decision": report["decision"],
        "market_data_values_deserialized": False,
        "mcs3_c_score_or_model_fitted": False,
        "no_external_or_protected_service_access": True,
        "partial_ob0_or_2026_accessed": False,
        "schema_version": "btc-market-condition-scores-mcs3-c-readiness-evidence-manifest-v1",
        "source_files": [
            {"path": str(MODULE_PATH.relative_to(ROOT)), "sha256": sha256_file(MODULE_PATH)},
            {"path": str(RUNNER_PATH.relative_to(ROOT)), "sha256": sha256_file(RUNNER_PATH)},
            {"path": str(TEST_PATH.relative_to(ROOT)), "sha256": sha256_file(TEST_PATH)},
        ],
        "strategy_position_pnl_order_or_risk_cap_evaluated": False,
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
    print(canonical_json({"audit_id": report["audit_id"], "decision": report["decision"]}), end="")


if __name__ == "__main__":
    main()
