#!/usr/bin/env python3
"""Run development and validation only for the frozen A2 session breakout."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from trading_platform.cross_asset_oanda_hourly import canonical_json, sha256_file
from trading_platform.cross_asset_session_breakout import (
    INSTRUMENTS,
    all_session_long_outcomes,
    attribution,
    load_contract,
    load_conversion,
    load_sessions,
    matched_control_outcomes,
    month_block_interval,
    partition_outcomes,
    random_direction_percentile,
    resolve_inputs,
    simulate_shared_account,
    strategy_outcomes,
    _utc,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "config/experiments/cross-asset-a2-session-breakout-continuation-v1.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    args = parser.parse_args()
    contract = load_contract(args.contract, ROOT)
    artifact_root = ROOT / contract["output"]["artifact_root"]
    if artifact_root.exists():
        raise ValueError("refusing to rerun immutable A2 result")
    normalized, masks, conversion_path = resolve_inputs(contract, ROOT)
    final_start = _utc(contract["partitions"]["final_sealed"]["start_inclusive"], "final start")
    profiles = {
        "london": contract["session_logic"]["london"],
        "new_york": contract["session_logic"]["new_york"],
    }
    sessions = []
    for instrument in INSTRUMENTS:
        sessions.extend(
            load_sessions(
                instrument,
                normalized[instrument],
                masks[instrument],
                profiles["new_york" if instrument not in {"DE30_EUR", "UK100_GBP"} else "london"],
                final_start,
            )
        )
    session_index = {(item.instrument_id, item.local_date.isoformat()): item for item in sessions}
    conversion = load_conversion(conversion_path, final_start)
    eurusd = load_conversion(normalized["EUR_USD"], final_start)
    all_cost_outcomes = {
        str(cost): strategy_outcomes(sessions, profiles, cost, conversion, eurusd)
        for cost in contract["costs"]["additional_round_trip_slippage_bps"]
    }
    partitions = {
        name: (_utc(value["start_inclusive"], f"{name} start"), _utc(value["end_exclusive"], f"{name} end"))
        for name, value in contract["partitions"].items()
        if name in {"development", "validation"}
    }
    report = {
        "accepted_strategy_arms": [],
        "actionable_arm_id": "no_trade",
        "decision": None,
        "experiment_id": contract["experiment_id"],
        "final_partition_accessed": False,
        "partitions": {},
        "schema_version": "cross-asset-a2-session-breakout-result-v1",
    }
    primary_cost = str(contract["costs"]["primary_round_trip_slippage_bps"])
    for name, (start, end) in partitions.items():
        partition_report = {"cost_scenarios": {}}
        for cost, outcomes in all_cost_outcomes.items():
            selected = partition_outcomes(outcomes, start, end)
            simulation = simulate_shared_account(selected, contract)
            trade_rows = simulation.pop("trade_rows")
            partition_report["cost_scenarios"][cost] = {
                **simulation,
                "attribution": attribution(selected, trade_rows),
                "mean_unit_return_bps": (
                    sum(item.unit_return for item in selected) / len(selected) * 10000 if selected else None
                ),
            }
            if cost == primary_cost:
                partition_report["primary_trade_rows"] = trade_rows
                partition_report["primary_outcomes"] = selected
        report["partitions"][name] = partition_report
    validation = report["partitions"]["validation"]
    validation_outcomes = validation.pop("primary_outcomes")
    development_outcomes = report["partitions"]["development"].pop("primary_outcomes")
    validation_trades = validation.pop("primary_trade_rows")
    development_trades = report["partitions"]["development"].pop("primary_trade_rows")
    long_control = matched_control_outcomes(
        validation_outcomes, session_index, profiles, int(primary_cost), conversion, eurusd, "long"
    )
    short_control = matched_control_outcomes(
        validation_outcomes, session_index, profiles, int(primary_cost), conversion, eurusd, "short"
    )
    sign_control = matched_control_outcomes(
        validation_outcomes, session_index, profiles, int(primary_cost), conversion, eurusd, "sign"
    )
    all_long = partition_outcomes(
        all_session_long_outcomes(sessions, profiles, int(primary_cost), conversion, eurusd),
        partitions["validation"][0],
        partitions["validation"][1],
    )
    control_means = {
        "confirmation_sign_mean_bps": sum(x.unit_return for x in sign_control) / len(sign_control) * 10000,
        "timestamp_long_mean_bps": sum(x.unit_return for x in long_control) / len(long_control) * 10000,
        "timestamp_short_mean_bps": sum(x.unit_return for x in short_control) / len(short_control) * 10000,
    }
    control_accounts = {
        "flat_no_trade": {
            "filled_trades": 0,
            "maximum_drawdown_fraction": 0.0,
            "net_return_fraction": 0.0,
        },
        "intraday_always_long_same_session_window": {
            key: value
            for key, value in simulate_shared_account(all_long, contract).items()
            if key != "trade_rows"
        },
        "simple_confirmation_return_sign_same_timestamps": {
            key: value
            for key, value in simulate_shared_account(sign_control, contract).items()
            if key != "trade_rows"
        },
        "timestamp_matched_always_long": {
            key: value
            for key, value in simulate_shared_account(long_control, contract).items()
            if key != "trade_rows"
        },
        "timestamp_matched_always_short": {
            key: value
            for key, value in simulate_shared_account(short_control, contract).items()
            if key != "trade_rows"
        },
    }
    random_result = random_direction_percentile(
        validation_outcomes,
        long_control,
        short_control,
        contract["controls"]["random_direction_seed"],
        contract["controls"]["random_direction_replications"],
    )
    interval = month_block_interval(
        validation_outcomes,
        contract["statistics"]["month_block_bootstrap_seed"],
        contract["statistics"]["month_block_bootstrap_replications"],
    )
    validation["controls"] = control_means
    validation["control_accounts"] = control_accounts
    validation["buy_and_hold_disposition"] = contract["controls"]["buy_and_hold_disposition"]
    validation["month_block_mean_trade_ci95_bps"] = None if interval is None else [x * 10000 for x in interval]
    validation["random_direction_control"] = random_result
    primary = validation["cost_scenarios"][primary_cost]
    stress = validation["cost_scenarios"]["15"]
    development_primary = report["partitions"]["development"]["cost_scenarios"][primary_cost]
    gates = contract["acceptance_gates"]
    best_timestamp_control = max(control_means["timestamp_long_mean_bps"], control_means["timestamp_short_mean_bps"])
    gate_results = {
        "best_three_month_concentration": primary["attribution"]["best_three_positive_month_profit_share"] <= float(gates["best_three_positive_month_profit_share_maximum"]),
        "development_validation_positive": development_primary["net_return_fraction"] > 0 and primary["net_return_fraction"] > 0,
        "maximum_drawdown": primary["maximum_drawdown_fraction"] <= float(gates["maximum_drawdown_fraction_maximum"]),
        "minimum_positive_instruments": primary["attribution"]["instruments_with_positive_pnl"] >= gates["minimum_instruments_with_positive_primary_validation_return"],
        "month_block_ci": validation["month_block_mean_trade_ci95_bps"] is not None and validation["month_block_mean_trade_ci95_bps"][0] > float(gates["primary_month_block_mean_trade_ci95_lower_bps_minimum"]),
        "primary_net_return": primary["net_return_fraction"] > float(gates["primary_net_return_minimum"]),
        "primary_profit_factor": primary["profit_factor"] is not None and primary["profit_factor"] >= float(gates["primary_profit_factor_minimum"]),
        "primary_sharpe": primary["sharpe"] is not None and primary["sharpe"] >= float(gates["primary_sharpe_minimum"]),
        "random_direction": random_result["empirical_percentile"] >= float(gates["random_direction_empirical_percentile_minimum"]),
        "stress_net_return": stress["net_return_fraction"] > float(gates["stress_net_return_minimum"]),
        "timestamp_control_outperformance": random_result["observed_mean_bps"] - best_timestamp_control > float(gates["timestamp_matched_long_and_short_control_outperformance_bps_minimum"]),
        "us_equity_concentration": primary["attribution"]["us_equity_pair_positive_profit_share"] <= float(gates["us_equity_pair_positive_profit_share_maximum"]),
        "validation_trade_count": primary["filled_trades"] >= gates["validation_filled_trades_minimum"],
    }
    report["gate_results"] = gate_results
    passed = all(gate_results.values())
    report["decision"] = "a2_validation_pass_final_remains_sealed" if passed else "a2_rejected_final_remains_sealed"
    artifact_root.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".a2-session-breakout-", dir=artifact_root.parent) as temporary:
        temp = Path(temporary)
        (temp / "development-trades.jsonl").write_text(
            "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in development_trades),
            encoding="utf-8",
        )
        (temp / "validation-trades.jsonl").write_text(
            "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in validation_trades),
            encoding="utf-8",
        )
        report_path = temp / "result.json"
        report_path.write_text(canonical_json(report), encoding="utf-8")
        manifest = {
            "accepted_strategy_arms": [],
            "actionable_arm_id": "no_trade",
            "artifacts": [
                {"path": str(args.contract.relative_to(ROOT)), "sha256": sha256_file(args.contract)},
                {"path": str((artifact_root / "result.json").relative_to(ROOT)), "sha256": sha256_file(report_path)},
                {"path": str((artifact_root / "development-trades.jsonl").relative_to(ROOT)), "sha256": sha256_file(temp / "development-trades.jsonl")},
                {"path": str((artifact_root / "validation-trades.jsonl").relative_to(ROOT)), "sha256": sha256_file(temp / "validation-trades.jsonl")},
            ],
            "decision": report["decision"],
            "experiment_id": contract["experiment_id"],
            "final_partition_accessed": False,
            "schema_version": "cross-asset-a2-session-breakout-evidence-v1",
        }
        (temp / "evidence-manifest.json").write_text(canonical_json(manifest), encoding="utf-8")
        temp.replace(artifact_root)
    print(canonical_json({"decision": report["decision"], "gate_results": gate_results}), end="")


if __name__ == "__main__":
    main()
