#!/usr/bin/env python3
"""Run the target-aware score-combination foundation on synthetic fixtures only."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from trading_platform.research_condition_scores import MarketConditionScore
from trading_platform.research_score_ensembles import (
    CalibrationSample,
    ConvexEnsembleSpec,
    ScoreCatalogue,
    ScoreCatalogueEntry,
    calibrate_empirical_percentile,
    combine_same_target,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "research/btc/contracts/btc-score-combination-foundation-v1.json"
DEFAULT_OUTPUT = ROOT / "artifacts/agent-level-experiment/btc-focused/score-combination-foundation-v1"
UTC = timezone.utc
NOW = datetime(2000, 2, 1, 12, tzinfo=UTC)
DIGEST_A = "a" * 64
DIGEST_B = "b" * 64


class ScoreCombinationQualificationError(ValueError):
    pass


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True) + "\n"


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_contract(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    value = json.loads(raw)
    if not isinstance(value, dict) or raw != canonical_json(value):
        raise ScoreCombinationQualificationError("contract must be canonical key-sorted JSON")
    if value.get("schema_version") != "btc-score-combination-foundation-contract-v1":
        raise ScoreCombinationQualificationError("unsupported contract schema")
    if value.get("status") != "frozen_before_implementation":
        raise ScoreCombinationQualificationError("contract was not frozen before implementation")
    boundary = value.get("action_boundary", {})
    if boundary.get("actionable_arm_id") != "no_trade" or boundary.get("accepted_strategy_arms"):
        raise ScoreCombinationQualificationError("contract action boundary is not fail-closed")
    for key in (
        "order_intent_creation_allowed",
        "production_signal_creation_allowed",
        "real_market_score_combination_allowed",
        "strategy_direction_or_pnl_evaluation_allowed",
    ):
        if boundary.get(key) is not False:
            raise ScoreCombinationQualificationError(f"contract permits {key}")
    return value


def validate_bound_inputs(contract: dict[str, Any]) -> list[dict[str, str]]:
    verified: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in contract.get("bound_inputs", []):
        relative = item.get("path")
        expected = item.get("sha256")
        if not isinstance(relative, str) or relative in seen or ".." in Path(relative).parts:
            raise ScoreCombinationQualificationError(f"invalid or duplicate bound path: {relative}")
        path = ROOT / relative
        if not path.is_file() or sha256_path(path) != expected:
            raise ScoreCombinationQualificationError(f"missing or changed bound input: {relative}")
        verified.append({"path": relative, "sha256": expected})
        seen.add(relative)
    if not verified:
        raise ScoreCombinationQualificationError("contract has no bound inputs")
    return sorted(verified, key=lambda item: item["path"])


def catalogue_entry(score_id: str, status: str) -> ScoreCatalogueEntry:
    uses = ("diagnostic", "same_target_ensemble") if status != "rejected" else ("diagnostic",)
    return ScoreCatalogueEntry(
        score_id=score_id,
        score_version="v1",
        axis="volatility",
        target_id="synthetic_realized_variance_1d",
        horizon_seconds=86400,
        score_kind="continuous",
        units="variance_fraction",
        evidence_status=status,
        permitted_uses=uses,
        evidence_digest=DIGEST_A,
    )


def synthetic_score(score_id: str, status: str, point: float) -> MarketConditionScore:
    return MarketConditionScore(
        score_id=score_id,
        score_version="v1",
        instrument="SYNTHETIC",
        venue="OFFLINE_FIXTURE",
        axis="volatility",
        score_kind="continuous",
        horizon_seconds=86400,
        fit_cutoff=NOW - timedelta(days=10),
        observed_at=NOW - timedelta(hours=1),
        available_at=NOW - timedelta(hours=1),
        expires_at=NOW + timedelta(hours=23),
        units="variance_fraction",
        point_estimate=point,
        lower_bound=point - 0.1,
        upper_bound=point + 0.1,
        confidence=0.8,
        evidence_status=status,
        lineage_digests={"fixture": DIGEST_B},
    )


def run(contract_path: Path, output: Path) -> None:
    if output.exists() and any(output.iterdir()):
        raise ScoreCombinationQualificationError(f"output must be absent or empty: {output}")
    contract = load_contract(contract_path)
    verified = validate_bound_inputs(contract)

    ewma_entry = catalogue_entry("synthetic-ewma", "benchmark")
    challenger_entry = catalogue_entry("synthetic-challenger", "accepted")
    rejected_entry = catalogue_entry("synthetic-rejected-control", "rejected")
    catalogue = ScoreCatalogue(
        catalogue_id="synthetic-score-catalogue",
        catalogue_version="v1",
        entries=(rejected_entry, challenger_entry, ewma_entry),
    )
    ewma_score = synthetic_score("synthetic-ewma", "benchmark", 0.4)
    challenger_score = synthetic_score("synthetic-challenger", "accepted", 0.6)
    history = tuple(
        CalibrationSample(
            observed_at=NOW - timedelta(days=20 - index),
            available_at=NOW - timedelta(days=19 - index),
            value=value,
            catalogue_entry_digest=ewma_entry.digest,
            lineage_digest=chr(99 + index) * 64,
        )
        for index, value in enumerate((0.1, 0.4, 0.4, 0.8))
    )
    calibrated = calibrate_empirical_percentile(
        score=ewma_score,
        catalogue_entry=ewma_entry,
        samples=history,
        decision_at=NOW,
        minimum_history=4,
    )
    ensemble_spec = ConvexEnsembleSpec(
        ensemble_id="synthetic-rv-equal-weight",
        ensemble_version="v1",
        axis="volatility",
        target_id="synthetic_realized_variance_1d",
        horizon_seconds=86400,
        score_kind="continuous",
        units="variance_fraction",
        weights={"synthetic-challenger@v1": 0.5, "synthetic-ewma@v1": 0.5},
    )
    ensemble = combine_same_target(
        spec=ensemble_spec,
        members=((ewma_entry, ewma_score), (challenger_entry, challenger_score)),
        decision_at=NOW,
    )

    report = {
        "accepted_strategy_arms": [],
        "actionable_arm_id": "no_trade",
        "bound_inputs_verified": verified,
        "decision": "passed_synthetic_score_combination_infrastructure_only",
        "experiment_id": contract["experiment_id"],
        "invariants": {
            "current_rejected_scores_combined": False,
            "fitted_or_dynamic_weights_used": False,
            "market_data_or_outcomes_opened": 0,
            "master_market_score_created": False,
            "mcs4_activated": False,
            "order_position_signal_or_strategy_action_created": False,
            "partial_ob0_accessed": False,
            "protected_services_accessed": False,
            "risk_cap_fusion_reimplemented": False,
            "sealed_or_ineligible_2026_accessed": False,
            "strategy_or_pnl_evaluated": False,
        },
        "next_permitted_action": "user_selects_one_new_strategy_hypothesis_before_strategy_adapter",
        "schema_version": "btc-score-combination-foundation-report-v1",
        "synthetic_results": {
            "calibrated_score": calibrated.as_dict(),
            "catalogue": catalogue.as_dict(),
            "catalogue_entries": [item.as_dict() for item in catalogue.entries],
            "ensemble_score": ensemble.as_dict(),
            "ensemble_spec": ensemble_spec.as_dict(),
        },
    }

    output.mkdir(parents=True, exist_ok=True)
    report_path = output / "synthetic-qualification-report.json"
    report_path.write_text(canonical_json(report), encoding="utf-8")
    contract_relative = contract_path.relative_to(ROOT).as_posix()
    logical_output = (
        "artifacts/agent-level-experiment/btc-focused/score-combination-foundation-v1/"
        "synthetic-qualification-report.json"
    )
    files = (
        contract_relative,
        "src/trading_platform/research_score_ensembles.py",
        "scripts/qualify_btc_score_combination_foundation.py",
        "tests/test_research_score_ensembles.py",
    )
    manifest = {
        "actionable_arm_id": "no_trade",
        "experiment_id": contract["experiment_id"],
        "files": [
            *({"path": relative, "sha256": sha256_path(ROOT / relative)} for relative in files),
            {"path": logical_output, "sha256": sha256_path(report_path)},
        ],
        "market_values_used": False,
        "schema_version": "btc-score-combination-foundation-evidence-manifest-v1",
        "synthetic_only": True,
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
