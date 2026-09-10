#!/usr/bin/env python3
"""Offline R0 attribution audit for the frozen multi-asset top-two experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from scripts.backtest_multi_asset_top2 import (
    BAR,
    PAIR_TO_STEM,
    Signal,
    canonical_json,
    run_backtest,
    sha256_file,
    validate_frame,
)
from trading_platform.execution_model import ExecutionScenario, load_scenarios
from trading_platform.research_attribution import (
    AttributionSignal,
    basket_return,
    block_bootstrap_mean_interval,
    block_bootstrap_ols_alpha_interval,
    friction_adjusted_return,
    matched_gate_distribution,
    ols_alpha_beta,
    one_sided_randomization_p,
    profitable_period_concentration,
    random_top2_distribution,
    randomization_percentile,
    reject_symlink_tree,
    require_child_path,
    require_output_path,
    selected_pairs,
    validate_attribution_signals,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_spec(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("experiment_id") != "multi-asset-top2-alpha-decomposition-r0-v1":
        raise ValueError("wrong attribution experiment_id")
    if payload.get("status") != "development_frozen":
        raise ValueError("attribution experiment must be frozen before execution")
    if payload.get("research_only") is not True or payload.get("live_trading_authorized") is not False:
        raise ValueError("R0 must remain research-only with live trading disabled")
    isolation = payload.get("isolation", {})
    prohibited = (
        "network_access_allowed",
        "database_access_allowed",
        "message_bus_access_allowed",
        "active_soak_access_allowed",
    )
    if any(isolation.get(name) is not False for name in prohibited):
        raise ValueError("R0 isolation contract permits an external connection")
    return payload


def validate_isolation(
    spec: Mapping[str, Any],
    data_dir: Path,
    signal_ledger: Path,
    output_dir: Path,
) -> tuple[Path, Path, Path]:
    isolation = spec["isolation"]
    allowed_data = (REPO_ROOT / isolation["allowed_data_directory"]).resolve(strict=True)
    allowed_signal = (REPO_ROOT / isolation["allowed_signal_ledger"]).resolve(strict=True)
    allowed_output_root = (REPO_ROOT / isolation["allowed_output_root"]).resolve(strict=True)
    checked_data = require_child_path(data_dir, allowed_data, "data directory")
    checked_signal = require_child_path(signal_ledger, allowed_signal.parent, "signal ledger")
    checked_output = require_output_path(output_dir, allowed_output_root)
    if checked_data != allowed_data:
        raise ValueError(f"data directory must exactly match frozen directory: {allowed_data}")
    if checked_signal != allowed_signal:
        raise ValueError(f"signal ledger must exactly match frozen ledger: {allowed_signal}")
    if isolation.get("refuse_symlink_inputs", False):
        reject_symlink_tree(data_dir)
        reject_symlink_tree(signal_ledger)
    return checked_data, checked_signal, checked_output


def load_price_frames(
    data_dir: Path,
    spec: Mapping[str, Any],
) -> tuple[dict[str, pd.DataFrame], list[dict[str, Any]]]:
    frames: dict[str, pd.DataFrame] = {}
    quality: list[dict[str, Any]] = []
    expected_hashes = spec["frozen_input_sha256"]
    for pair, stem in PAIR_TO_STEM.items():
        path = data_dir / f"{stem}-15m.feather"
        reject_symlink_tree(path)
        digest = sha256_file(path)
        if digest != expected_hashes[pair]:
            raise ValueError(f"frozen input checksum mismatch for {pair}: {digest}")
        raw = pd.read_feather(path)
        frame = validate_frame(raw, pair, path)
        frames[pair] = frame
        quality.append(
            {
                "pair": pair,
                "path": str(path.relative_to(REPO_ROOT)),
                "sha256": digest,
                "rows": int(len(frame)),
                "start": frame["date"].min().isoformat(),
                "end": frame["date"].max().isoformat(),
                "rows_at_or_after_development_end": int(
                    (frame["date"] >= pd.Timestamp(spec["development_period"]["end_exclusive"])).sum()
                ),
            }
        )
    return frames, quality


def load_frozen_daily_signals(path: Path, spec: Mapping[str, Any]) -> list[AttributionSignal]:
    digest = sha256_file(path)
    if digest != spec["frozen_signal_ledger_sha256"]:
        raise ValueError(f"frozen signal ledger checksum mismatch: {digest}")
    ledger = pd.read_csv(path)
    required = {"signal_time", "decision_time", "entry_time", "pairs", "top4_pairs"}
    missing = sorted(required - set(ledger.columns))
    if missing:
        raise ValueError(f"signal ledger missing columns: {missing}")
    for column in ("signal_time", "decision_time", "entry_time"):
        ledger[column] = pd.to_datetime(ledger[column], utc=True)
    ledger = ledger[ledger["signal_time"].dt.hour.eq(0)].copy()
    signals = [
        AttributionSignal(
            signal_time=row.signal_time,
            decision_time=row.decision_time,
            entry_time=row.entry_time,
            ranked_pairs=tuple(str(row.pairs).split(",")),
            top4_pairs=tuple(str(row.top4_pairs).split(",")),
        )
        for row in ledger.itertuples(index=False)
    ]
    development_end = pd.Timestamp(spec["development_period"]["end_exclusive"])
    validate_attribution_signals(signals, spec["universe"], development_end)
    return signals


def simulation_signals(
    signals: Sequence[AttributionSignal],
    control: str,
    universe: Sequence[str],
) -> list[Signal]:
    return [
        Signal(
            signal_time=signal.signal_time,
            decision_time=signal.decision_time,
            entry_time=signal.entry_time,
            pairs=selected_pairs(signal, control, universe),
            top4_pairs=signal.top4_pairs,
            scores=(0.0, 0.0),
        )
        for signal in signals
    ]


def run_shared_capital_controls(
    frames: dict[str, pd.DataFrame],
    signals: Sequence[AttributionSignal],
    controls: Sequence[str],
    scenarios: Sequence[ExecutionScenario],
    universe: Sequence[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    results: list[dict[str, Any]] = []
    cohorts: list[dict[str, Any]] = []
    for scenario in scenarios:
        for control in controls:
            result, rows = run_backtest(
                frames,
                simulation_signals(signals, control, universe),
                scenario,
                cadence="daily",
                derisk=False,
            )
            result["control"] = control
            result["variant"] = "daily_hold48"
            results.append(result)
            for row in rows:
                cohorts.append(
                    {
                        "control": control,
                        "scenario_id": scenario.scenario_id,
                        **row,
                    }
                )
    return results, cohorts


def indexed_prices(frames: Mapping[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    return {pair: frame.set_index("date", drop=False).sort_index() for pair, frame in frames.items()}


def event_asset_returns(
    prices: Mapping[str, pd.DataFrame],
    signal_time: pd.Timestamp,
    scenario: ExecutionScenario,
    universe: Sequence[str],
) -> dict[str, float]:
    entry_time = signal_time + BAR
    exit_time = entry_time + pd.Timedelta(hours=48)
    return {
        pair: friction_adjusted_return(
            float(prices[pair].at[entry_time, "open"]),
            float(prices[pair].at[exit_time, "open"]),
            scenario,
        )
        for pair in universe
    }


def build_event_attribution(
    frames: Mapping[str, pd.DataFrame],
    signals: Sequence[AttributionSignal],
    scenarios: Sequence[ExecutionScenario],
    universe: Sequence[str],
) -> tuple[list[dict[str, Any]], dict[str, np.ndarray]]:
    prices = indexed_prices(frames)
    rows: list[dict[str, Any]] = []
    primary_matrix: dict[str, np.ndarray] = {}
    for scenario in scenarios:
        matrix: list[list[float]] = []
        for signal in signals:
            by_pair = event_asset_returns(prices, signal.signal_time, scenario, universe)
            matrix.append([by_pair[pair] for pair in universe])
            ranked = basket_return(by_pair, signal.ranked_pairs)
            top4 = basket_return(by_pair, signal.top4_pairs)
            eligible = basket_return(by_pair, universe)
            remainder_pairs = tuple(pair for pair in universe if pair not in set(signal.ranked_pairs))
            remainder = basket_return(by_pair, remainder_pairs)
            rows.append(
                {
                    "scenario_id": scenario.scenario_id,
                    "signal_time": signal.signal_time.isoformat(),
                    "entry_time": signal.entry_time.isoformat(),
                    "exit_time": (signal.entry_time + pd.Timedelta(hours=48)).isoformat(),
                    "ranked_pairs": ",".join(signal.ranked_pairs),
                    "top4_pairs": ",".join(signal.top4_pairs),
                    "ranked_top2_return": ranked,
                    "top4_equal_weight_return": top4,
                    "universe7_equal_weight_return": eligible,
                    "btc_return": by_pair["BTC/USDT"],
                    "eth_return": by_pair["ETH/USDT"],
                    "eligible_remainder_return": remainder,
                    "ranked_minus_top4": ranked - top4,
                    "ranked_minus_universe": ranked - eligible,
                    "selected_minus_remainder": ranked - remainder,
                }
            )
        primary_matrix[scenario.scenario_id] = np.asarray(matrix, dtype=float)
    return rows, primary_matrix


def build_gate_match_pools(
    frames: Mapping[str, pd.DataFrame],
    signals: Sequence[AttributionSignal],
    scenario: ExecutionScenario,
    universe: Sequence[str],
) -> tuple[list[np.ndarray], dict[str, int]]:
    prices = indexed_prices(frames)
    common = set.intersection(*(set(frame.index) for frame in prices.values()))
    signal_times = {signal.signal_time for signal in signals}
    development_start = min(signal.signal_time for signal in signals).normalize().replace(month=1, day=1)
    development_end = pd.Timestamp("2026-01-01T00:00:00Z")
    candidate_by_month: dict[str, list[pd.Timestamp]] = {}
    for timestamp in sorted(common):
        if timestamp < development_start or timestamp >= development_end:
            continue
        if timestamp.minute != 0 or timestamp.hour != 0 or timestamp in signal_times:
            continue
        if timestamp + BAR not in common or timestamp + BAR + pd.Timedelta(hours=48) not in common:
            continue
        candidate_by_month.setdefault(timestamp.strftime("%Y-%m"), []).append(timestamp)
    return_cache: dict[pd.Timestamp, float] = {}
    pools: list[np.ndarray] = []
    pool_sizes: dict[str, int] = {}
    for signal in signals:
        month = signal.signal_time.strftime("%Y-%m")
        candidates = candidate_by_month.get(month, [])
        if not candidates:
            raise ValueError(f"no non-signal midnight gate match is available for {month}")
        values: list[float] = []
        for timestamp in candidates:
            if timestamp not in return_cache:
                returns = event_asset_returns(prices, timestamp, scenario, universe)
                return_cache[timestamp] = basket_return(returns, universe)
            values.append(return_cache[timestamp])
        pools.append(np.asarray(values, dtype=float))
        pool_sizes[signal.signal_time.isoformat()] = len(values)
    return pools, pool_sizes


def buy_hold_baselines(
    frames: Mapping[str, pd.DataFrame],
    scenarios: Sequence[ExecutionScenario],
) -> list[dict[str, Any]]:
    btc = frames["BTC/USDT"].set_index("date").sort_index()
    start = btc.index[btc.index >= pd.Timestamp("2021-01-01T00:00:00Z")][0]
    end = btc.index[btc.index < pd.Timestamp("2026-01-01T00:00:00Z")][-1]
    rows: list[dict[str, Any]] = []
    for scenario in scenarios:
        allocated_return = friction_adjusted_return(
            float(btc.at[start, "open"]), float(btc.at[end, "close"]), scenario
        )
        rows.append(
            {
                "baseline": "btc_buy_hold_25pct_initial_equity",
                "scenario_id": scenario.scenario_id,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "return_on_allocated": allocated_return,
                "account_net_return": 0.25 * allocated_return,
            }
        )
    return rows


def result_for(
    results: Sequence[Mapping[str, Any]],
    control: str,
    scenario_id: str,
) -> Mapping[str, Any]:
    return next(
        row for row in results if row["control"] == control and row["scenario_id"] == scenario_id
    )


def build_statistics(
    spec: Mapping[str, Any],
    event_rows: Sequence[Mapping[str, Any]],
    matrices: Mapping[str, np.ndarray],
    frames: Mapping[str, pd.DataFrame],
    signals: Sequence[AttributionSignal],
    scenarios_by_id: Mapping[str, ExecutionScenario],
    cohorts: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    primary_id = "candle-primary-30bps-rt-v1"
    primary_rows = [row for row in event_rows if row["scenario_id"] == primary_id]
    blocks = [pd.Timestamp(row["signal_time"]).strftime("%Y-%m") for row in primary_rows]
    ranked = np.asarray([row["ranked_top2_return"] for row in primary_rows], dtype=float)
    universe = np.asarray([row["universe7_equal_weight_return"] for row in primary_rows], dtype=float)
    top4 = np.asarray([row["top4_equal_weight_return"] for row in primary_rows], dtype=float)
    remainder = np.asarray([row["eligible_remainder_return"] for row in primary_rows], dtype=float)
    selection_delta = ranked - universe

    random_spec = spec["diagnostics"]["random_top2"]
    random_distribution = random_top2_distribution(
        matrices[primary_id], random_spec["simulations"], random_spec["seed"]
    )
    confidence = spec["diagnostics"]["confidence"]
    delta_interval = block_bootstrap_mean_interval(
        selection_delta,
        blocks,
        confidence["replications"],
        confidence["seed"],
        confidence["interval"],
    )
    beta = ols_alpha_beta(ranked, universe)
    beta["alpha_interval"] = block_bootstrap_ols_alpha_interval(
        ranked,
        universe,
        blocks,
        confidence["replications"],
        confidence["seed"] + 1,
        confidence["interval"],
    )

    gate_spec = spec["diagnostics"]["regime_gate_timing"]
    gate_pools, gate_pool_sizes = build_gate_match_pools(
        frames, signals, scenarios_by_id[primary_id], spec["universe"]
    )
    gate_distribution = matched_gate_distribution(
        gate_pools, gate_spec["simulations"], gate_spec["seed"]
    )
    gated_universe_mean = float(universe.mean())

    yearly: dict[str, dict[str, float | int]] = {}
    for year in sorted({pd.Timestamp(row["signal_time"]).year for row in primary_rows}):
        indices = np.asarray(
            [pd.Timestamp(row["signal_time"]).year == year for row in primary_rows], dtype=bool
        )
        yearly[str(year)] = {
            "events": int(indices.sum()),
            "ranked_top2_mean_return": float(ranked[indices].mean()),
            "universe_mean_return": float(universe[indices].mean()),
            "selection_delta": float(selection_delta[indices].mean()),
        }

    primary_ranked_cohorts = [
        row
        for row in cohorts
        if row["control"] == "ranked_top2" and row["scenario_id"] == primary_id
    ]
    concentration = profitable_period_concentration(primary_ranked_cohorts, top_n=3)
    distribution_rows = [
        {"distribution": "random_top2", "simulation": index, "mean_return": float(value)}
        for index, value in enumerate(random_distribution)
    ]
    distribution_rows.extend(
        {
            "distribution": "matched_non_gate_universe7",
            "simulation": index,
            "mean_return": float(value),
        }
        for index, value in enumerate(gate_distribution)
    )
    statistics = {
        "event_return_convention": (
            "paired next-open to 48-hour next-open returns with scenario fees and implicit costs; "
            "price-protection expiry and shared-capital sizing are excluded from statistical diagnostics"
        ),
        "events": len(primary_rows),
        "mean_returns": {
            "ranked_top2": float(ranked.mean()),
            "gate_qualified_top4": float(top4.mean()),
            "eligible_universe7": float(universe.mean()),
            "eligible_remainder": float(remainder.mean()),
            "ranked_minus_top4": float((ranked - top4).mean()),
            "ranked_minus_universe": float(selection_delta.mean()),
            "selected_minus_remainder": float((ranked - remainder).mean()),
        },
        "selection_delta_month_block_bootstrap": delta_interval,
        "random_top2": {
            "simulations": len(random_distribution),
            "seed": random_spec["seed"],
            "observed_ranked_mean": float(ranked.mean()),
            "distribution_mean": float(random_distribution.mean()),
            "distribution_median": float(np.median(random_distribution)),
            "percentile": randomization_percentile(float(ranked.mean()), random_distribution),
            "one_sided_p": one_sided_randomization_p(float(ranked.mean()), random_distribution),
        },
        "regime_gate_timing": {
            "simulations": len(gate_distribution),
            "seed": gate_spec["seed"],
            "gated_universe_mean": gated_universe_mean,
            "matched_non_gate_distribution_mean": float(gate_distribution.mean()),
            "matched_non_gate_distribution_median": float(np.median(gate_distribution)),
            "percentile": randomization_percentile(gated_universe_mean, gate_distribution),
            "one_sided_p": one_sided_randomization_p(gated_universe_mean, gate_distribution),
            "matched_pool_sizes_by_signal": gate_pool_sizes,
        },
        "market_beta_model": beta,
        "calendar_year_selection": yearly,
        "positive_selection_delta_calendar_years": int(
            sum(row["selection_delta"] > 0 for row in yearly.values())
        ),
        "primary_ranked_month_concentration": concentration,
    }
    return statistics, distribution_rows


def build_gates(
    spec: Mapping[str, Any],
    results: Sequence[Mapping[str, Any]],
    statistics: Mapping[str, Any],
) -> dict[str, bool]:
    expected = spec["acceptance_gates"]
    primary = result_for(results, "ranked_top2", "candle-primary-30bps-rt-v1")
    severe = result_for(results, "ranked_top2", "candle-severe-80bps-rt-v1")
    means = statistics["mean_returns"]
    concentration = statistics["primary_ranked_month_concentration"]["share"]
    return {
        "minimum_filled_ranked_cohorts": primary["cohorts"] >= expected["minimum_filled_ranked_cohorts"],
        "ranked_top2_primary_net_return_positive": primary["net_return"] > 0,
        "ranked_top2_severe_net_return_positive": severe["net_return"] > 0,
        "ranked_minus_universe_mean_return_bps": (
            means["ranked_minus_universe"] * 10_000
            > expected["ranked_minus_universe_mean_return_bps_strictly_above"]
        ),
        "ranked_minus_top4_mean_return_bps": (
            means["ranked_minus_top4"] * 10_000
            > expected["ranked_minus_top4_mean_return_bps_strictly_above"]
        ),
        "selection_delta_bootstrap_lower_95_bps": (
            statistics["selection_delta_month_block_bootstrap"]["lower"] * 10_000
            > expected["selection_delta_bootstrap_lower_95_bps_strictly_above"]
        ),
        "random_selection_one_sided_p": (
            statistics["random_top2"]["one_sided_p"]
            <= expected["random_selection_one_sided_p_maximum"]
        ),
        "regime_gate_one_sided_p": (
            statistics["regime_gate_timing"]["one_sided_p"]
            <= expected["regime_gate_one_sided_p_maximum"]
        ),
        "positive_selection_delta_calendar_years": (
            statistics["positive_selection_delta_calendar_years"]
            >= expected["positive_selection_delta_calendar_years_minimum"]
        ),
        "top_three_profitable_months_share": bool(
            concentration is not None
            and concentration <= expected["top_three_profitable_months_share_maximum"]
        ),
        "maximum_entry_gross_exposure_fraction": (
            primary["maximum_entry_gross_exposure_fraction"]
            <= expected["maximum_entry_gross_exposure_fraction"] + 1e-12
        ),
        "point_in_time_universe_membership": False,
        "no_post_signal_information": True,
        "sealed_2026_not_read": True,
    }


def write_csv_gz(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    pd.DataFrame(rows).to_csv(
        path,
        index=False,
        compression={"method": "gzip", "compresslevel": 9, "mtime": 0},
    )


def build_manifest(
    spec_path: Path,
    scenario_path: Path,
    signal_path: Path,
    quality: Sequence[Mapping[str, Any]],
    output_dir: Path,
) -> dict[str, Any]:
    output_names = (
        "report.json",
        "cohorts.csv.gz",
        "event_attribution.csv.gz",
        "random_distributions.csv.gz",
    )
    return {
        "schema_version": "multi-asset-alpha-attribution-manifest-v1",
        "experiment_sha256": sha256_file(spec_path),
        "scenario_config_sha256": sha256_file(scenario_path),
        "frozen_signal_ledger_sha256": sha256_file(signal_path),
        "runner_sha256": sha256_file(Path(__file__)),
        "research_attribution_module_sha256": sha256_file(
            REPO_ROOT / "src/trading_platform/research_attribution.py"
        ),
        "shared_capital_runner_sha256": sha256_file(
            REPO_ROOT / "scripts/backtest_multi_asset_top2.py"
        ),
        "inputs": {row["pair"]: row["sha256"] for row in quality},
        "outputs": {name: sha256_file(output_dir / name) for name in output_names},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--spec",
        type=Path,
        default=Path("config/experiments/multi-asset-top2-alpha-decomposition-r0-v1.json"),
    )
    parser.add_argument(
        "--scenario-config", type=Path, default=Path("config/execution_scenarios.json")
    )
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--signal-ledger", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    spec_path = args.spec.resolve(strict=True)
    scenario_path = args.scenario_config.resolve(strict=True)
    spec = load_spec(spec_path)
    data_dir, signal_path, output_dir = validate_isolation(
        spec, args.data_dir, args.signal_ledger, args.output_dir
    )
    if output_dir.exists() and any(output_dir.iterdir()):
        parser.error(f"refusing to overwrite non-empty output directory: {output_dir}")

    frames, quality = load_price_frames(data_dir, spec)
    signals = load_frozen_daily_signals(signal_path, spec)
    scenario_map = load_scenarios(scenario_path)
    scenarios = [scenario_map[scenario_id] for scenario_id in spec["execution_scenarios"]]

    results, cohorts = run_shared_capital_controls(
        frames,
        signals,
        spec["shared_capital_controls"],
        scenarios,
        spec["universe"],
    )
    event_rows, matrices = build_event_attribution(frames, signals, scenarios, spec["universe"])
    statistics, distribution_rows = build_statistics(
        spec, event_rows, matrices, frames, signals, scenario_map, cohorts
    )
    gates = build_gates(spec, results, statistics)
    decision = "selection_alpha_pass" if all(gates.values()) else "selection_alpha_reject"

    primary = result_for(results, "ranked_top2", "candle-primary-30bps-rt-v1")
    severe = result_for(results, "ranked_top2", "candle-severe-80bps-rt-v1")
    report = {
        "schema_version": "multi-asset-alpha-attribution-report-v1",
        "experiment_id": spec["experiment_id"],
        "source_experiment_id": spec["source_experiment_id"],
        "decision": decision,
        "research_only": True,
        "live_trading_authorized": False,
        "isolation_verified": {
            "archived_files_only": True,
            "network_used": False,
            "database_used": False,
            "message_bus_used": False,
            "active_soak_accessed": False,
        },
        "development_end_exclusive": spec["development_period"]["end_exclusive"],
        "sealed_2026_read": False,
        "signal_count": len(signals),
        "shared_capital_model": (
            "single 1000 USDT cash account per control and scenario; 25% cohort and aggregate "
            "gross cap; equal-notional atomic basket; next-open entry; 48-hour next-open exit"
        ),
        "shared_capital_results": results,
        "flat_baseline_account_net_return": 0.0,
        "buy_hold_baselines": buy_hold_baselines(frames, scenarios),
        "attribution": statistics,
        "sizing_attribution": {
            "ranked_primary_mean_return_on_allocated_event_capital": statistics["mean_returns"][
                "ranked_top2"
            ],
            "ranked_primary_shared_account_net_return_at_25pct_cap": primary["net_return"],
            "maximum_allocation_fraction": 0.25,
            "interpretation": "Sizing changes account-level return and loss, not the paired selection statistic.",
        },
        "cost_attribution": {
            "ranked_primary_account_net_return": primary["net_return"],
            "ranked_severe_account_net_return": severe["net_return"],
            "severe_minus_primary_account_net_return": severe["net_return"] - primary["net_return"],
            "ranked_primary_execution_cost_quote": primary["execution_cost_quote"],
            "ranked_severe_execution_cost_quote": severe["execution_cost_quote"],
        },
        "acceptance_gates": gates,
        "acceptance_gate_values": spec["acceptance_gates"],
        "failed_gates": sorted(name for name, passed in gates.items() if not passed),
        "data_quality": quality,
        "limitations": spec["known_pre_execution_limitations"],
        "interpretation_policy": (
            "If ranked top two do not beat the matched eligible universe and random controls with "
            "adequate uncertainty, positive returns are described as regime timing or crypto beta, "
            "not selection alpha. This development audit cannot create promotion evidence."
        ),
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv_gz(output_dir / "cohorts.csv.gz", cohorts)
    write_csv_gz(output_dir / "event_attribution.csv.gz", event_rows)
    write_csv_gz(output_dir / "random_distributions.csv.gz", distribution_rows)
    (output_dir / "report.json").write_text(canonical_json(report), encoding="utf-8")
    manifest = build_manifest(spec_path, scenario_path, signal_path, quality, output_dir)
    (output_dir / "manifest.json").write_text(canonical_json(manifest), encoding="utf-8")
    print(
        canonical_json(
            {
                "output_dir": str(output_dir),
                "decision": decision,
                "failed_gates": report["failed_gates"],
                "ranked_primary_net_return": primary["net_return"],
                "selection_delta_mean_bps": statistics["mean_returns"][
                    "ranked_minus_universe"
                ]
                * 10_000,
                "random_selection_p": statistics["random_top2"]["one_sided_p"],
                "regime_gate_p": statistics["regime_gate_timing"]["one_sided_p"],
            }
        )
    )


if __name__ == "__main__":
    main()
