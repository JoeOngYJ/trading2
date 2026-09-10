#!/usr/bin/env python3
"""Run the frozen A3 development and historical validation exactly once."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from decimal import Decimal
from pathlib import Path

from trading_platform.cross_asset_gap_reversion import (
    INSTRUMENTS,
    augmented_account,
    generate_candidates,
    load_contract,
    load_conversion_partition,
    load_session_partition,
    month_block_interval,
    outcomes_for_candidates,
    partition_outcomes,
    random_direction_percentile,
    resolve_prepartitions,
    validation_year_pnl,
    attribution,
    _utc,
)
from trading_platform.cross_asset_oanda_hourly import canonical_json, sha256_file


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "config/experiments/cross-asset-a3-overnight-gap-reversion-v2.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    args = parser.parse_args()
    contract = load_contract(args.contract, ROOT)
    artifact_root = ROOT / contract["output"]["artifact_root"]
    if artifact_root.exists():
        raise ValueError("refusing to rerun immutable A3 result")
    sources = resolve_prepartitions(contract, ROOT)
    profiles = {"london": contract["session_logic"]["london"], "new_york": contract["session_logic"]["new_york"]}
    sessions_by_instrument = {}
    for instrument in INSTRUMENTS:
        sessions = []
        for partition in ("development", "validation"):
            sessions.extend(
                load_session_partition(
                    instrument,
                    sources[(partition, instrument, "market")],
                    sources[(partition, instrument, "availability")],
                    profiles["new_york" if instrument not in {"DE30_EUR", "UK100_GBP"} else "london"],
                )
            )
        sessions_by_instrument[instrument] = sorted(sessions, key=lambda item: item.local_date)
    conversion = {}
    eurusd = {}
    for partition in ("development", "validation"):
        conversion.update(load_conversion_partition(sources[(partition, "GBP_USD", "conversion")]))
        eurusd.update(load_conversion_partition(sources[(partition, "EUR_USD", "market")]))
    robustness = contract["robustness"]
    candidates = generate_candidates(
        sessions_by_instrument,
        profiles,
        int(robustness["primary_lookback_complete_sessions"]),
        Decimal(robustness["primary_gap_threshold_multiplier"]),
    )
    bounds = {
        name: (_utc(value["start_inclusive"], f"{name} start"), _utc(value["end_exclusive"], f"{name} end"))
        for name, value in contract["partitions"].items()
        if name in {"development", "validation"}
    }
    report = {
        "accepted_strategy_arms": [],
        "actionable_arm_id": "no_trade",
        "decision": None,
        "experiment_id": contract["experiment_id"],
        "partitions": {},
        "prospective_partition_accessed": False,
        "schema_version": "cross-asset-a3-overnight-gap-reversion-result-v2",
    }
    outcomes_by_cost = {
        str(cost): outcomes_for_candidates(candidates, profiles, cost, conversion, eurusd)
        for cost in contract["costs"]["additional_round_trip_slippage_bps"]
    }
    primary_key = str(contract["costs"]["primary_round_trip_slippage_bps"])
    primary_rows = {}
    primary_partition_outcomes = {}
    for name, (start, end) in bounds.items():
        partition_report = {"cost_scenarios": {}}
        for cost, outcomes in outcomes_by_cost.items():
            selected = partition_outcomes(outcomes, start, end)
            account = augmented_account(selected, contract)
            trade_rows = account.pop("trade_rows")
            partition_report["cost_scenarios"][cost] = {
                **account,
                "attribution": attribution(selected, trade_rows),
                "mean_unit_return_bps": sum(item.unit_return for item in selected) / len(selected) * 10000 if selected else None,
            }
            if cost == primary_key:
                primary_rows[name] = trade_rows
                primary_partition_outcomes[name] = selected
        report["partitions"][name] = partition_report
    validation = report["partitions"]["validation"]
    validation_outcomes = primary_partition_outcomes["validation"]
    validation_rows = primary_rows["validation"]
    validation_candidates = [
        item for item in candidates
        if bounds["validation"][0] <= item.session.bars[profiles[item.session.profile_id]["entry_local_hour"]].observed_at < bounds["validation"][1]
    ]
    controls = {}
    control_outcomes = {}
    for mode in ("long", "short", "continuation"):
        observed = outcomes_for_candidates(validation_candidates, profiles, int(primary_key), conversion, eurusd, mode)
        control_outcomes[mode] = observed
        controls[f"timestamp_matched_{mode}_mean_bps"] = sum(item.unit_return for item in observed) / len(observed) * 10000 if observed else None
    threshold_only = generate_candidates(
        sessions_by_instrument,
        profiles,
        int(robustness["primary_lookback_complete_sessions"]),
        Decimal(robustness["primary_gap_threshold_multiplier"]),
        require_confirmation=False,
    )
    threshold_validation = [
        item for item in threshold_only
        if bounds["validation"][0] <= item.session.bars[profiles[item.session.profile_id]["entry_local_hour"]].observed_at < bounds["validation"][1]
    ]
    threshold_outcomes = outcomes_for_candidates(threshold_validation, profiles, int(primary_key), conversion, eurusd)
    threshold_mean = sum(item.unit_return for item in threshold_outcomes) / len(threshold_outcomes) * 10000 if threshold_outcomes else None
    controls["threshold_only_gap_fade_mean_bps"] = threshold_mean
    controls["flat_no_trade"] = {"filled_trades": 0, "net_return_fraction": 0.0}
    validation["controls"] = controls
    validation["random_direction_control"] = random_direction_percentile(
        validation_outcomes,
        control_outcomes["long"],
        control_outcomes["short"],
        contract["controls"]["random_direction_seed"],
        contract["controls"]["random_direction_replications"],
    )
    interval = month_block_interval(
        validation_outcomes,
        contract["statistics"]["month_block_bootstrap_seed"],
        contract["statistics"]["month_block_bootstrap_replications"],
    )
    validation["month_block_mean_trade_ci95_bps"] = [value * 10000 for value in interval] if interval else None
    validation["year_pnl_gbp"] = validation_year_pnl(validation_rows)
    validation["leave_one_instrument_out"] = {
        instrument: augmented_account([item for item in validation_outcomes if item.instrument_id != instrument], contract)["net_return_fraction"]
        for instrument in INSTRUMENTS
    }
    variants = {}
    for label, lookback, threshold in [
        ("lookback_15", 15, Decimal("0.75")),
        ("lookback_30", 30, Decimal("0.75")),
        ("threshold_0_50", 20, Decimal("0.50")),
        ("threshold_1_00", 20, Decimal("1.00")),
    ]:
        variant_candidates = generate_candidates(sessions_by_instrument, profiles, lookback, threshold)
        variant_outcomes = outcomes_for_candidates(variant_candidates, profiles, int(primary_key), conversion, eurusd)
        selected = partition_outcomes(variant_outcomes, *bounds["validation"])
        variants[label] = {
            key: value for key, value in augmented_account(selected, contract).items() if key != "trade_rows"
        }
    validation["robustness_variants"] = variants
    primary = validation["cost_scenarios"][primary_key]
    development_primary = report["partitions"]["development"]["cost_scenarios"][primary_key]
    stress = validation["cost_scenarios"]["15"]
    gates = contract["acceptance_gates"]
    strategy_mean = primary["mean_unit_return_bps"]
    timestamp_best = max(controls[f"timestamp_matched_{mode}_mean_bps"] for mode in ("long", "short", "continuation"))
    gate_results = {
        "best_three_month_concentration": primary["attribution"]["best_three_positive_month_profit_share"] <= float(gates["best_three_positive_month_profit_share_maximum"]),
        "development_validation_positive": development_primary["net_return_fraction"] > 0 and primary["net_return_fraction"] > 0,
        "leave_one_instrument_out": sum(value > 0 for value in validation["leave_one_instrument_out"].values()) >= gates["leave_one_instrument_out_positive_count_minimum"],
        "maximum_drawdown": primary["maximum_drawdown_fraction"] <= float(gates["maximum_drawdown_fraction_maximum"]),
        "minimum_positive_instruments": primary["attribution"]["instruments_with_positive_pnl"] >= gates["minimum_instruments_with_positive_primary_validation_return"],
        "month_block_ci": validation["month_block_mean_trade_ci95_bps"] is not None and validation["month_block_mean_trade_ci95_bps"][0] > float(gates["primary_month_block_mean_trade_ci95_lower_bps_minimum"]),
        "positive_validation_years": sum(value > 0 for value in validation["year_pnl_gbp"].values()) >= gates["positive_validation_years_minimum"],
        "primary_net_return": primary["net_return_fraction"] > float(gates["primary_net_return_minimum"]),
        "primary_profit_factor": primary["profit_factor"] is not None and primary["profit_factor"] >= float(gates["primary_profit_factor_minimum"]),
        "primary_sharpe": primary["sharpe"] is not None and primary["sharpe"] >= float(gates["primary_sharpe_minimum"]),
        "random_direction": validation["random_direction_control"]["empirical_percentile"] >= float(gates["random_direction_empirical_percentile_minimum"]),
        "robustness": sum(value["net_return_fraction"] > 0 for value in variants.values()) >= gates["robustness_variants_with_positive_primary_return_minimum"],
        "simpler_gap_fade": threshold_mean is not None and strategy_mean - threshold_mean > float(gates["simpler_gap_fade_mean_outperformance_bps_minimum"]),
        "stress_net_return": stress["net_return_fraction"] > float(gates["stress_net_return_minimum"]),
        "timestamp_controls": strategy_mean - timestamp_best > float(gates["timestamp_matched_long_short_and_continuation_outperformance_bps_minimum"]),
        "us_equity_concentration": primary["attribution"]["us_equity_pair_positive_profit_share"] <= float(gates["us_equity_pair_positive_profit_share_maximum"]),
        "validation_trade_count": primary["filled_trades"] >= gates["validation_filled_trades_minimum"],
    }
    report["gate_results"] = gate_results
    report["decision"] = (
        "a3_historical_candidate_pending_prospective_evidence"
        if all(gate_results.values())
        else "a3_rejected_do_not_tune"
    )
    temp_root = Path(tempfile.mkdtemp(prefix=f".{artifact_root.name}-", dir=artifact_root.parent))
    try:
        for name in ("development", "validation"):
            (temp_root / f"{name}-trades.jsonl").write_text(
                "".join(json.dumps(row, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n" for row in primary_rows[name]),
                encoding="utf-8",
            )
        (temp_root / "result.json").write_text(canonical_json(report), encoding="utf-8")
        target_root = Path(contract["output"]["artifact_root"])
        artifacts = [
            {"path": str(args.contract.resolve(strict=True).relative_to(ROOT)), "sha256": sha256_file(args.contract)},
            {"path": str(target_root / "result.json"), "sha256": sha256_file(temp_root / "result.json")},
            {"path": str(target_root / "development-trades.jsonl"), "sha256": sha256_file(temp_root / "development-trades.jsonl")},
            {"path": str(target_root / "validation-trades.jsonl"), "sha256": sha256_file(temp_root / "validation-trades.jsonl")},
        ]
        evidence = {
            "accepted_strategy_arms": [],
            "actionable_arm_id": "no_trade",
            "artifacts": artifacts,
            "decision": report["decision"],
            "experiment_id": contract["experiment_id"],
            "prospective_partition_accessed": False,
            "schema_version": "cross-asset-a3-overnight-gap-reversion-evidence-v2",
        }
        (temp_root / "evidence-manifest.json").write_text(canonical_json(evidence), encoding="utf-8")
        os.replace(temp_root, artifact_root)
    except Exception:
        import shutil
        shutil.rmtree(temp_root, ignore_errors=True)
        raise
    print(canonical_json({"decision": report["decision"], "artifact": str(artifact_root / "evidence-manifest.json")}), end="")


if __name__ == "__main__":
    main()
