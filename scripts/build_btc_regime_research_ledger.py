#!/usr/bin/env python3
"""Build S1 causal ledgers and reproduce the fixed BTC breakout on development only."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from trading_platform.research_breakout import (
    breakout_forecasts,
    exit_execution_rows,
    segmented_buy_hold,
    signal_indices,
    simulate,
)
from trading_platform.research_evidence import load_research_partition_registry
from trading_platform.research_ledger import (
    DAY_MS,
    FOUR_HOURS_MS,
    aggregate_candles,
    feature_observations,
    load_source_candles,
    sha256_file,
    write_jsonl_gzip,
)
from trading_platform.research_program import canonical_json


REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = REPO_ROOT / "artifacts/agent-level-experiment/btc-regime-routing"
DEFAULT_CONTRACT = REPO_ROOT / "config/experiments/btc-regime-routing-s1-ledger-v1.json"
DEFAULT_SCENARIOS = REPO_ROOT / "config/execution_scenarios.json"
DEFAULT_BOUNDARIES = REPO_ROOT / "config/research/btc-directional-trend-evidence-boundaries-v1.json"


def parse_ms(value: str) -> int:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
        raise ValueError(f"timestamp is not explicit UTC: {value}")
    return int(parsed.timestamp() * 1000)


def require_exact_path(path: Path, expected: Path, label: str) -> Path:
    actual = path.resolve(strict=True)
    frozen = expected.resolve(strict=True)
    if actual != frozen:
        raise ValueError(f"{label} differs from frozen path: {actual}")
    if path.is_symlink():
        raise ValueError(f"symlinked {label} is prohibited")
    return actual


def require_output(path: Path) -> Path:
    root = ARTIFACT_ROOT.resolve(strict=False)
    output = path.resolve(strict=False)
    try:
        output.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"output escapes isolated S1 artifact root: {output}") from exc
    if output.exists() and any(output.iterdir()):
        raise ValueError(f"refusing to overwrite non-empty output directory: {output}")
    return output


def scenario_costs(path: Path, selected_ids: list[str]) -> dict[str, dict[str, float]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    scenarios = {item["scenario_id"]: item for item in payload["scenarios"]}
    if len(scenarios) != len(payload["scenarios"]):
        raise ValueError("execution scenario IDs are not unique")
    result: dict[str, dict[str, float]] = {}
    for scenario_id in selected_ids:
        item = scenarios.get(scenario_id)
        if item is None or item.get("mode") != "candle_taker":
            raise ValueError(f"missing frozen candle-taker scenario: {scenario_id}")
        side = (
            float(item["taker_fee_bps"])
            + float(item["implicit_cost_bps_per_side"])
            + float(item["residual_impact_bps"])
        )
        result[scenario_id] = {
            "price_protection_bps": float(item["price_protection_bps"]),
            "side_cost_bps": side,
        }
    return result


def core_metrics(result: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "busy_signal_count",
        "cagr",
        "calmar",
        "expired_entry_count",
        "exposure_fraction",
        "frequency_blocked_count",
        "maximum_drawdown_fraction",
        "mean_net_trade_bps",
        "net_return",
        "positive_calendar_years",
        "profit_factor",
        "trade_count",
    )
    return {key: result[key] for key in keys}


def require_exact_mapping(actual: dict[str, Any], expected: dict[str, Any], label: str) -> None:
    if actual != expected:
        differences = {
            key: {"actual": actual.get(key), "expected": expected.get(key)}
            for key in sorted(set(actual) | set(expected))
            if actual.get(key) != expected.get(key)
        }
        raise ValueError(f"{label} parity mismatch: {differences}")


def run(args: argparse.Namespace) -> dict[str, Any]:
    contract_path = require_exact_path(args.contract, DEFAULT_CONTRACT, "S1 contract")
    scenario_path = require_exact_path(args.scenario_config, DEFAULT_SCENARIOS, "scenario config")
    boundary_path = require_exact_path(args.boundaries, DEFAULT_BOUNDARIES, "evidence boundaries")
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if (
        contract.get("experiment_id") != "btc-regime-routing-s1-ledger-v1"
        or contract.get("stage_id") != "S1"
        or contract.get("status") != "frozen"
    ):
        raise ValueError("exact frozen S1 contract is required")
    isolation = contract["isolation"]
    if any(
        isolation.get(key) is not False
        for key in (
            "active_order_book_partial_access_allowed",
            "active_soak_access_allowed",
            "database_access_allowed",
            "exchange_access_allowed",
            "freqtrade_access_allowed",
            "holdout_access_allowed",
            "message_bus_access_allowed",
            "model_fitting_allowed",
            "network_access_allowed",
            "order_intent_creation_allowed",
            "position_creation_allowed",
            "production_signal_creation_allowed",
        )
    ):
        raise ValueError("S1 isolation boundary is not fail-closed")

    data_spec = contract["data"]
    data_path = require_exact_path(
        args.data, REPO_ROOT / data_spec["allowed_dataset_path"], "development dataset"
    )
    manifest_path = require_exact_path(
        args.manifest, REPO_ROOT / data_spec["development_manifest_path"], "development manifest"
    )
    if sha256_file(manifest_path) != data_spec["development_manifest_sha256"]:
        raise ValueError("development manifest checksum mismatch")
    source_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        source_manifest.get("accepted") is not True
        or source_manifest.get("partition") != "development-2017-2025"
        or source_manifest.get("dataset_sha256") != data_spec["development_dataset_sha256"]
    ):
        raise ValueError("accepted development-only source manifest required")

    legacy = contract["legacy_parity"]
    legacy_report_path = require_exact_path(
        REPO_ROOT / legacy["legacy_report_path"],
        REPO_ROOT / legacy["legacy_report_path"],
        "legacy report",
    )
    if sha256_file(legacy_report_path) != legacy["legacy_report_sha256"]:
        raise ValueError("legacy report checksum mismatch")
    if sha256_file(REPO_ROOT / legacy["legacy_contract_path"]) != legacy["legacy_contract_sha256"]:
        raise ValueError("legacy contract checksum mismatch")
    if sha256_file(REPO_ROOT / legacy["legacy_runner_path"]) != legacy["legacy_runner_sha256"]:
        raise ValueError("legacy runner checksum mismatch")
    legacy_report = json.loads(legacy_report_path.read_text(encoding="utf-8"))
    if legacy_report.get("holdout_accessed") is not False:
        raise ValueError("legacy reproduction source does not preserve the sealed holdout")

    if sha256_file(scenario_path) != "a020cb07780e88b60fffd4c6e1b205922f0b815f033a4676dd422a7038538f36":
        raise ValueError("execution scenario checksum mismatch")
    registry = load_research_partition_registry(boundary_path)
    if registry.strategy_family != "btc-directional-trend":
        raise ValueError("BTC directional-trend evidence registry required")
    registry.require_access(
        "btc-development-2017-2025-consumed",
        "reproduction",
        datetime.fromisoformat(contract["frozen_at"].replace("Z", "+00:00")),
    )
    if registry.clean_unseen_partition_ids():
        raise ValueError("S1 must not declare a clean unseen BTC trend partition")

    rows, source_digest = load_source_candles(data_path, data_spec["development_dataset_sha256"])
    if len(rows) != data_spec["expected_rows_5m"]:
        raise ValueError("five-minute row count differs from frozen contract")
    if len({row.segment for row in rows}) != data_spec["expected_source_segments"]:
        raise ValueError("source segment count differs from frozen contract")
    bars_4h, discarded_4h = aggregate_candles(rows, FOUR_HOURS_MS, "4h")
    bars_daily, discarded_daily = aggregate_candles(rows, DAY_MS, "1d")
    aggregation = {
        "bars_4h": len(bars_4h),
        "bars_daily": len(bars_daily),
        "discarded_rows_4h": discarded_4h,
        "discarded_rows_daily": discarded_daily,
    }
    require_exact_mapping(aggregation, legacy["expected_aggregation"], "aggregation")

    features_4h = feature_observations(bars_4h, source_digest)
    features_daily = feature_observations(bars_daily, source_digest)
    evaluation_start_ms = parse_ms(data_spec["evaluation_start"])
    evaluation_end_ms = parse_ms(data_spec["evaluation_end_exclusive"])
    forecasts = breakout_forecasts(
        bars_4h,
        lookback=contract["parameters"]["entry_channel_bars"],
        evaluation_start_ms=evaluation_start_ms,
        evidence_digest=legacy["legacy_report_sha256"],
    )
    signals = signal_indices(forecasts)
    if len(signals) != legacy["expected_breakout_conditions"]:
        raise ValueError(
            f"breakout condition parity mismatch: {len(signals)} != {legacy['expected_breakout_conditions']}"
        )
    planned_exits = exit_execution_rows(
        rows, bars_4h, contract["parameters"]["exit_channel_bars"]
    )
    costs = scenario_costs(scenario_path, contract["parameters"]["execution_scenario_ids"])
    results: dict[str, dict[str, Any]] = {}
    for scenario_id, cost in costs.items():
        result = simulate(
            rows,
            bars_4h,
            signals,
            planned_exits,
            side_cost_bps=cost["side_cost_bps"],
            price_protection_bps=cost["price_protection_bps"],
            evaluation_start_ms=evaluation_start_ms,
            evaluation_end_ms=evaluation_end_ms,
            stop_fraction=contract["parameters"]["protective_stop_fraction"],
            maximum_holding_days=contract["parameters"]["maximum_holding_days"],
            allocation=contract["parameters"]["account_fraction_per_entry"],
        )
        observed = core_metrics(result)
        require_exact_mapping(observed, legacy["expected_scenarios"][scenario_id], scenario_id)
        require_exact_mapping(
            observed,
            core_metrics(legacy_report["breakout_control_execution_scenarios"][scenario_id]),
            f"{scenario_id} legacy report",
        )
        results[scenario_id] = result

    primary_id = contract["parameters"]["execution_scenario_ids"][0]
    control = segmented_buy_hold(
        rows,
        side_cost_bps=costs[primary_id]["side_cost_bps"],
        evaluation_start_ms=evaluation_start_ms,
        evaluation_end_ms=evaluation_end_ms,
        allocation=contract["parameters"]["account_fraction_per_entry"],
    )
    control_core = {
        "segmented_buy_hold_allocation_fraction": control["allocation_fraction"],
        "segmented_buy_hold_cagr": control["cagr"],
        "segmented_buy_hold_maximum_drawdown_fraction": control[
            "maximum_drawdown_fraction"
        ],
        "segmented_buy_hold_net_return": control["net_return"],
        "segmented_buy_hold_segments": control["segments"],
        "flat_maximum_drawdown_fraction": 0.0,
        "flat_net_return": 0.0,
    }
    require_exact_mapping(control_core, legacy["expected_controls"], "controls")

    output = require_output(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, dict[str, Any]] = {}
    artifacts["candles-5m.jsonl.gz"] = write_jsonl_gzip(
        output / "candles-5m.jsonl.gz", (row.as_dict() for row in rows)
    )
    artifacts["candles-4h.jsonl.gz"] = write_jsonl_gzip(
        output / "candles-4h.jsonl.gz", (bar.as_dict() for bar in bars_4h)
    )
    artifacts["candles-1d.jsonl.gz"] = write_jsonl_gzip(
        output / "candles-1d.jsonl.gz", (bar.as_dict() for bar in bars_daily)
    )
    artifacts["features-4h.jsonl.gz"] = write_jsonl_gzip(
        output / "features-4h.jsonl.gz", (item.as_dict() for item in features_4h)
    )
    artifacts["features-1d.jsonl.gz"] = write_jsonl_gzip(
        output / "features-1d.jsonl.gz", (item.as_dict() for item in features_daily)
    )
    artifacts["breakout-forecasts.jsonl.gz"] = write_jsonl_gzip(
        output / "breakout-forecasts.jsonl.gz", (item.as_dict() for item in forecasts)
    )
    artifacts["breakout-trades.jsonl.gz"] = write_jsonl_gzip(
        output / "breakout-trades.jsonl.gz",
        (
            {"scenario_id": scenario_id, **trade}
            for scenario_id in contract["parameters"]["execution_scenario_ids"]
            for trade in results[scenario_id]["trades"]
        ),
    )
    scenario_report = {
        scenario_id: {key: value for key, value in result.items() if key != "trades"}
        for scenario_id, result in results.items()
    }
    report = {
        "aggregation": aggregation,
        "attribution": {
            "asset_selection": "not_applicable_single_asset",
            "costs": "reported_at_all_frozen_30_40_80_bps_scenarios",
            "flat": {"maximum_drawdown_fraction": 0.0, "net_return": 0.0},
            "market_beta_warning": "Breakout return remains unresolved timing of BTC directional participation, not proven independent alpha.",
            "segmented_btc_buy_hold_primary_cost": {
                key: value for key, value in control.items() if key != "segment_returns"
            },
            "sizing": "fixed_10_percent_reproduced_not_compared_or_optimized",
            "timestamp_matched_validation": "not_evaluated_in_s1",
        },
        "breakout_conditions": len(signals),
        "decision": "s1_passed_reproduction_only",
        "evidence_boundary": registry.summary(),
        "experiment_id": contract["experiment_id"],
        "feature_observations": {
            "daily": len(features_daily),
            "four_hour": len(features_4h),
        },
        "holdout_accessed": False,
        "model_fitted": False,
        "promotion_evidence": False,
        "result_classification": "development_reproduction_only",
        "schema_version": "btc-regime-routing-s1-reproduction-report-v1",
        "scenarios": scenario_report,
        "source": {
            "dataset_sha256": source_digest,
            "rows_5m": len(rows),
            "segments": len({row.segment for row in rows}),
        },
    }
    boundary_report = {
        "decision": "no_clean_unseen_partition_fail_closed",
        "holdout_accessed": False,
        "schema_version": "btc-trend-evidence-boundary-audit-v1",
        **registry.summary(),
    }
    report_path = output / "breakout-reproduction-report.json"
    boundary_report_path = output / "evidence-boundary-audit.json"
    report_path.write_text(canonical_json(report), encoding="utf-8")
    boundary_report_path.write_text(canonical_json(boundary_report), encoding="utf-8")
    artifacts[report_path.name] = {
        "bytes": report_path.stat().st_size,
        "sha256": sha256_file(report_path),
    }
    artifacts[boundary_report_path.name] = {
        "bytes": boundary_report_path.stat().st_size,
        "sha256": sha256_file(boundary_report_path),
    }
    manifest = {
        "artifacts": dict(sorted(artifacts.items())),
        "decision": "s1_passed_reproduction_only",
        "experiment_id": contract["experiment_id"],
        "holdout_accessed": False,
        "inputs": {
            str(boundary_path.relative_to(REPO_ROOT)): sha256_file(boundary_path),
            str(contract_path.relative_to(REPO_ROOT)): sha256_file(contract_path),
            str(data_path.relative_to(REPO_ROOT)): source_digest,
            str(manifest_path.relative_to(REPO_ROOT)): sha256_file(manifest_path),
            str(scenario_path.relative_to(REPO_ROOT)): sha256_file(scenario_path),
            legacy["legacy_report_path"]: sha256_file(legacy_report_path),
        },
        "implementations": {
            "research_breakout.py": sha256_file(
                REPO_ROOT / "src/trading_platform/research_breakout.py"
            ),
            "research_ledger.py": sha256_file(REPO_ROOT / "src/trading_platform/research_ledger.py"),
            "runner": sha256_file(Path(__file__)),
        },
        "model_fitted": False,
        "promotion_evidence": False,
        "schema_version": "btc-regime-routing-s1-manifest-v1",
    }
    manifest_path_out = output / "manifest.json"
    manifest_path_out.write_text(canonical_json(manifest), encoding="utf-8")
    return {
        "artifact_count": len(artifacts) + 1,
        "breakout_conditions": len(signals),
        "decision": manifest["decision"],
        "holdout_accessed": False,
        "output_dir": str(output),
        "primary": core_metrics(results[primary_id]),
    }


def main() -> None:
    contract = json.loads(DEFAULT_CONTRACT.read_text(encoding="utf-8"))
    data = contract["data"]
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--data", type=Path, default=REPO_ROOT / data["allowed_dataset_path"])
    parser.add_argument("--manifest", type=Path, default=REPO_ROOT / data["development_manifest_path"])
    parser.add_argument("--scenario-config", type=Path, default=DEFAULT_SCENARIOS)
    parser.add_argument("--boundaries", type=Path, default=DEFAULT_BOUNDARIES)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
