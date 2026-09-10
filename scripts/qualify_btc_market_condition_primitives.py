#!/usr/bin/env python3
"""Run the MCS2 fixed synthetic qualification without market-data access."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from trading_platform.research_condition_scores import (
    MarketConditionScore,
    MarketConditionScorePanel,
    annualized_completed_funding,
    completed_field_values,
    completed_short_perpetual_funding,
    corwin_schultz_high_low_spread_proxy,
    directional_efficiency,
    lag_one_autocovariance,
    mean_amihud_price_impact_proxy,
    overlapping_variance_ratio,
    perpetual_basis_fraction,
    realized_variation_components,
    standardized_displacement,
    volatility_scaled_return,
)
from trading_platform.research_market_conditions import MarketConditionObservation


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "research/btc/contracts/btc-market-condition-scores-mcs2-v1.json"
DEFAULT_OUTPUT = (
    ROOT / "artifacts/agent-level-experiment/btc-focused/market-condition-scores-mcs2-v1"
)
UTC = timezone.utc
FIXTURE_NOW = datetime(2000, 1, 2, 12, tzinfo=UTC)
FIXTURE_DIGEST = "a" * 64


class MCS2QualificationError(ValueError):
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
        raise MCS2QualificationError("MCS2 contract must be canonical key-sorted JSON")
    if value.get("schema_version") != "btc-market-condition-scores-mcs2-contract-v1":
        raise MCS2QualificationError("unsupported MCS2 contract schema")
    if value.get("stage_id") != "MCS2" or value.get("status") != "frozen_before_implementation":
        raise MCS2QualificationError("MCS2 contract is not frozen")
    boundary = value.get("action_boundary", {})
    if boundary.get("actionable_arm_id") != "no_trade" or boundary.get("accepted_strategy_arms"):
        raise MCS2QualificationError("MCS2 action boundary is not fail-closed")
    for key in (
        "market_data_or_feature_value_deserialization_allowed",
        "model_or_score_fit_allowed",
        "order_intent_creation_allowed",
        "production_signal_creation_allowed",
        "strategy_or_pnl_evaluation_allowed",
        "threshold_selection_allowed",
    ):
        if boundary.get(key) is not False:
            raise MCS2QualificationError(f"MCS2 action boundary permits {key}")
    if len(value.get("primitive_definitions", [])) != 12:
        raise MCS2QualificationError("MCS2 primitive registry changed")
    return value


def validate_bound_inputs(contract: dict[str, Any]) -> list[dict[str, str]]:
    verified: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in contract.get("bound_inputs", []):
        relative = item.get("path")
        expected = item.get("sha256")
        if not isinstance(relative, str) or relative in seen or ".." in Path(relative).parts:
            raise MCS2QualificationError(f"invalid or duplicate bound path: {relative}")
        path = ROOT / relative
        if not path.is_file() or sha256_path(path) != expected:
            raise MCS2QualificationError(f"missing or changed bound input: {relative}")
        verified.append({"path": relative, "sha256": expected})
        seen.add(relative)
    if not verified:
        raise MCS2QualificationError("MCS2 contract has no bound inputs")
    return sorted(verified, key=lambda item: item["path"])


def synthetic_observations() -> tuple[MarketConditionObservation, ...]:
    rows: list[MarketConditionObservation] = []
    for index, value in enumerate((0.01, 0.02, -0.01)):
        observed = FIXTURE_NOW - timedelta(hours=3 - index)
        rows.append(
            MarketConditionObservation(
                instrument="SYNTHETIC",
                venue="OFFLINE_FIXTURE",
                axis="persistence",
                interval="1h",
                segment="synthetic-segment",
                window_started_at=observed - timedelta(hours=1),
                observed_at=observed,
                available_at=observed,
                field_values={"return": value},
                lineage_digests={"fixture": FIXTURE_DIGEST},
            )
        )
    return tuple(rows)


def synthetic_score() -> MarketConditionScore:
    return MarketConditionScore(
        score_id="synthetic-persistence",
        score_version="v1",
        instrument="SYNTHETIC",
        venue="OFFLINE_FIXTURE",
        axis="persistence",
        score_kind="continuous",
        horizon_seconds=14400,
        fit_cutoff=FIXTURE_NOW - timedelta(days=30),
        observed_at=FIXTURE_NOW - timedelta(hours=1),
        available_at=FIXTURE_NOW - timedelta(hours=1),
        expires_at=FIXTURE_NOW + timedelta(hours=3),
        units="dimensionless",
        point_estimate=0.2,
        lower_bound=-0.1,
        upper_bound=0.5,
        confidence=0.6,
        evidence_status="development",
        lineage_digests={"fixture": FIXTURE_DIGEST},
    )


def run(contract_path: Path, output: Path) -> None:
    if output.exists() and any(output.iterdir()):
        raise MCS2QualificationError(f"output directory must be absent or empty: {output}")
    contract = load_contract(contract_path)
    verified = validate_bound_inputs(contract)

    causal_returns = completed_field_values(
        synthetic_observations(), field_name="return", decision_at=FIXTURE_NOW, minimum=3
    )
    variation = realized_variation_components((0.001, 0.001, 0.1))
    score = synthetic_score()
    panel = MarketConditionScorePanel(decision_at=FIXTURE_NOW, scores=(score,))
    results = {
        "carry_transforms": {
            "annualized_completed_funding": annualized_completed_funding(
                (0.0001, 0.0002, -0.0001)
            ),
            "completed_short_perpetual_funding": completed_short_perpetual_funding(
                (0.0001, 0.0002, -0.0001)
            ),
            "perpetual_basis_fraction": perpetual_basis_fraction(
                spot_price=100, perpetual_price=101
            ),
        },
        "causal_completed_returns": list(causal_returns),
        "liquidity_proxies": {
            "corwin_schultz_high_low_spread_proxy": corwin_schultz_high_low_spread_proxy(
                110, 100, 110, 100
            ),
            "mean_amihud_price_impact_proxy": mean_amihud_price_impact_proxy(
                (0.01, -0.02), (1000, 2000)
            ),
            "protected_fill_cost_claimed": False,
        },
        "persistence_reversion_diagnostics": {
            "directional_efficiency": directional_efficiency(causal_returns),
            "lag_one_autocovariance": lag_one_autocovariance((1, 2, 4)),
            "overlapping_variance_ratio": overlapping_variance_ratio(
                (1, -1, 1, -1, 1, -1), 2
            ),
            "standardized_displacement": standardized_displacement((1, 2, 3), 4),
            "volatility_scaled_return": volatility_scaled_return(causal_returns),
        },
        "realized_variation": variation.as_dict(),
        "score_contract": score.as_dict(),
        "score_panel": panel.as_dict(),
    }

    contract_relative = contract_path.relative_to(ROOT).as_posix()
    implementation_relative = "src/trading_platform/research_condition_scores.py"
    runner_relative = "scripts/qualify_btc_market_condition_primitives.py"
    implementation_sha256 = sha256_path(ROOT / implementation_relative)
    runner_sha256 = sha256_path(ROOT / runner_relative)
    report = {
        "accepted_strategy_arms": [],
        "actionable_arm_id": "no_trade",
        "bound_inputs_verified": verified,
        "decision": "mcs2_passed_synthetic_infrastructure_only",
        "experiment_id": contract["experiment_id"],
        "implementation": {
            "path": implementation_relative,
            "sha256": implementation_sha256,
        },
        "invariants": {
            "composite_or_universal_score_created": False,
            "market_data_feature_label_or_pnl_files_opened": 0,
            "market_values_deserialized": False,
            "models_or_scores_fitted": False,
            "order_intents_or_production_signals_created": False,
            "partial_ob0_accessed": False,
            "protected_services_accessed": False,
            "sealed_or_ineligible_2026_accessed": False,
            "strategy_or_pnl_evaluated": False,
            "thresholds_selected": False,
        },
        "next_permitted_stage": "MCS3-P",
        "schema_version": "btc-market-condition-scores-mcs2-report-v1",
        "stage_id": "MCS2",
        "synthetic_results": results,
    }

    output.mkdir(parents=True, exist_ok=True)
    report_path = output / "synthetic-qualification-report.json"
    report_path.write_text(canonical_json(report), encoding="utf-8")
    logical_report_path = (
        "artifacts/agent-level-experiment/btc-focused/market-condition-scores-mcs2-v1/"
        "synthetic-qualification-report.json"
    )
    manifest = {
        "experiment_id": contract["experiment_id"],
        "files": [
            {"path": contract_relative, "sha256": sha256_path(contract_path)},
            {"path": implementation_relative, "sha256": implementation_sha256},
            {"path": runner_relative, "sha256": runner_sha256},
            {"path": logical_report_path, "sha256": sha256_path(report_path)},
        ],
        "market_values_used": False,
        "schema_version": "btc-market-condition-scores-mcs2-evidence-manifest-v1",
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
