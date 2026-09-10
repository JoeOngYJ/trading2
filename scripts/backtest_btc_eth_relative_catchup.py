#!/usr/bin/env python3
"""Run the frozen, offline BTC/ETH relative catch-up R2 experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd

from trading_platform.execution_model import (
    ExecutionScenario,
    MarketRules,
    OrderIntent,
    OrderKind,
    OrderStatus,
    Side,
    load_scenarios,
    simulate_candle_taker,
)
from trading_platform.research_attribution import (
    block_bootstrap_mean_interval,
    friction_adjusted_return,
    matched_gate_distribution,
    one_sided_randomization_p,
    profitable_period_concentration,
    randomization_percentile,
    reject_symlink_tree,
    require_child_path,
    require_output_path,
)
from trading_platform.research_relative import (
    BAR_15M,
    RelativeSignal,
    make_btc_self_reversal_signals,
    make_joint_risk_on_signals,
    make_relative_signals,
    relative_feature_frame,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
STARTING_EQUITY = Decimal("1000")
BTC_PAIR = "BTC/USDT"
ETH_PAIR = "ETH/USDT"
PAIR_STEMS = {BTC_PAIR: "BTC_USDT", ETH_PAIR: "ETH_USDT"}


@dataclass
class Position:
    signal: RelativeSignal
    quantity: Decimal
    entry_cost: Decimal
    entry_observed_price: float
    entry_fill_price: Decimal


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n"


def load_spec(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("experiment_id") != "btc-eth-relative-catchup-r2-v1":
        raise ValueError("wrong experiment_id")
    if payload.get("status") != "development_frozen":
        raise ValueError("R2 specification must be frozen before execution")
    if payload.get("data", {}).get("development_end_exclusive") != "2026-01-01T00:00:00Z":
        raise ValueError("R2 development boundary is not frozen")
    if payload.get("mandate", {}).get("traded_pair") != BTC_PAIR:
        raise ValueError("R2 runner accepts only the BTC spot mandate")
    if payload.get("mandate", {}).get("context_only_pair") != ETH_PAIR:
        raise ValueError("R2 ETH role must remain context only")
    return payload


def validate_frame(
    frame: pd.DataFrame,
    pair: str,
    path: Path,
    development_start: pd.Timestamp,
    development_end: pd.Timestamp,
) -> pd.DataFrame:
    required = ["date", "open", "high", "low", "close", "volume"]
    missing = sorted(set(required) - set(frame.columns))
    if missing:
        raise ValueError(f"{path} missing columns: {missing}")
    out = frame[required].copy()
    out["date"] = pd.to_datetime(out["date"], utc=True)
    out = out.sort_values("date").reset_index(drop=True)
    if out["date"].duplicated().any():
        raise ValueError(f"{pair} contains duplicate timestamps")
    out[required[1:]] = out[required[1:]].apply(pd.to_numeric, errors="coerce")
    values = out[required[1:]].to_numpy(dtype=float)
    if np.isnan(values).any() or not np.isfinite(values).all():
        raise ValueError(f"{pair} contains non-finite market values")
    invalid = (
        out[["open", "high", "low", "close"]].le(0).any(axis=1)
        | out["volume"].lt(0)
        | out["high"].lt(out[["open", "close", "low"]].max(axis=1))
        | out["low"].gt(out[["open", "close", "high"]].min(axis=1))
    )
    if invalid.any():
        raise ValueError(f"{pair} contains {int(invalid.sum())} invalid OHLCV rows")
    if (
        out["date"].dt.second.ne(0).any()
        or out["date"].dt.microsecond.ne(0).any()
        or out["date"].dt.minute.mod(15).ne(0).any()
    ):
        raise ValueError(f"{pair} is not aligned to a 15-minute UTC grid")
    if out["date"].ge(development_end).any():
        raise ValueError(f"{pair} archive contains sealed rows at or after {development_end.isoformat()}")
    out = out[out["date"].ge(development_start) & out["date"].lt(development_end)].copy()
    if out.empty:
        raise ValueError(f"{pair} has no rows in the frozen development interval")
    out["pair"] = pair
    return out.reset_index(drop=True)


def load_inputs(
    spec: dict[str, Any], data_dir: Path
) -> tuple[dict[str, pd.DataFrame], list[dict[str, Any]]]:
    allowed = REPO_ROOT / spec["isolation"]["allowed_data_directory"]
    resolved_dir = require_child_path(data_dir, allowed, "R2 data directory")
    if resolved_dir != allowed.resolve(strict=True):
        raise ValueError("R2 requires the exact frozen data directory, not a child directory")
    reject_symlink_tree(resolved_dir)
    start = pd.Timestamp(spec["data"]["development_start"])
    end = pd.Timestamp(spec["data"]["development_end_exclusive"])
    frames: dict[str, pd.DataFrame] = {}
    quality: list[dict[str, Any]] = []
    for pair, stem in PAIR_STEMS.items():
        path = resolved_dir / f"{stem}-15m.feather"
        reject_symlink_tree(path)
        if not path.is_file():
            raise FileNotFoundError(path)
        observed_hash = sha256_file(path)
        expected_hash = spec["data"][f"{pair}_sha256"]
        if observed_hash != expected_hash:
            raise ValueError(f"{pair} checksum mismatch: {observed_hash}")
        raw = pd.read_feather(path)
        frame = validate_frame(raw, pair, path, start, end)
        differences = frame["date"].diff().dropna()
        frames[pair] = frame
        quality.append(
            {
                "pair": pair,
                "path": str(path.relative_to(REPO_ROOT)),
                "sha256": observed_hash,
                "rows_source": int(len(raw)),
                "rows_development": int(len(frame)),
                "start": frame["date"].min().isoformat(),
                "end": frame["date"].max().isoformat(),
                "gap_count": int(differences.ne(BAR_15M).sum()),
                "max_gap_minutes": float(differences.max() / pd.Timedelta(minutes=1)),
                "sealed_rows_read": 0,
            }
        )
    return frames, quality


def market_rules() -> MarketRules:
    return MarketRules(
        symbol="BTCUSDT",
        effective_at="research-generic-rules-v1",
        tick_size=Decimal("0.00000001"),
        step_size=Decimal("0.00000001"),
        min_quantity=Decimal("0.00000001"),
        min_notional=Decimal("5"),
        source="generic_research_fixture_not_historical_exchangeInfo",
    )


def _price_frame(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.set_index("date", drop=False).sort_index()


def signal_has_complete_path(signal: RelativeSignal, prices: pd.DataFrame) -> bool:
    if signal.entry_time not in prices.index or signal.exit_time not in prices.index:
        return False
    path = prices.loc[signal.entry_time : signal.exit_time]
    expected_rows = int((signal.exit_time - signal.entry_time) / BAR_15M) + 1
    return bool(
        len(path) == expected_rows
        and path.index[0] == signal.entry_time
        and path.index[-1] == signal.exit_time
        and path.index.to_series().diff().dropna().eq(BAR_15M).all()
    )


def filter_executable_signals(
    signals: Sequence[RelativeSignal], prices: pd.DataFrame
) -> tuple[list[RelativeSignal], int]:
    valid = [signal for signal in signals if signal_has_complete_path(signal, prices)]
    return valid, len(signals) - len(valid)


def _order(
    signal: RelativeSignal,
    quantity: Decimal,
    side: Side,
    decision_price: float,
    observed_price: float,
    timestamp: pd.Timestamp,
    scenario: ExecutionScenario,
    suffix: str,
) -> Any:
    intent = OrderIntent(
        client_order_id=f"{scenario.scenario_id}:{signal.variant}:{signal.entry_time.value}:{suffix}",
        side=side,
        quantity=quantity,
        decision_time_ns=int(timestamp.value),
        decision_price=Decimal(str(decision_price)),
        kind=OrderKind.PROTECTIVE if side is Side.SELL else OrderKind.MARKETABLE_LIMIT,
        protective=side is Side.SELL,
    )
    return simulate_candle_taker(
        intent,
        Decimal(str(observed_price)),
        int(timestamp.value),
        scenario,
        market_rules(),
    )


def run_backtest(
    frame: pd.DataFrame,
    signals: Sequence[RelativeSignal],
    scenario: ExecutionScenario,
    maximum_fraction: float = 0.25,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Simulate one BTC position with exits processed before same-time entries."""

    if not 0 < maximum_fraction <= 1:
        raise ValueError("maximum account fraction must be in (0, 1]")
    prices = _price_frame(frame)
    ordered = sorted(signals, key=lambda item: (item.entry_time, item.variant))
    signal_by_entry: dict[pd.Timestamp, list[RelativeSignal]] = {}
    for signal in ordered:
        if not signal_has_complete_path(signal, prices):
            raise ValueError(f"signal crosses a missing BTC execution path: {signal.entry_time}")
        signal_by_entry.setdefault(signal.entry_time, []).append(signal)

    cash = STARTING_EQUITY
    position: Position | None = None
    trades: list[dict[str, Any]] = []
    execution_cost = Decimal(0)
    expired_orders = 0
    rejected_orders = 0
    skipped_overlap = 0
    equity_points: list[tuple[pd.Timestamp, Decimal]] = []
    exposure_points: list[float] = []
    peak = STARTING_EQUITY
    max_drawdown = Decimal(0)
    max_entry_exposure = Decimal(0)
    start = min(prices.index)
    end = max(prices.index)

    for timestamp, row in prices.iterrows():
        observed_open = float(row["open"])
        if position is not None and timestamp >= position.signal.exit_time:
            result = _order(
                position.signal,
                position.quantity,
                Side.SELL,
                observed_open,
                observed_open,
                timestamp,
                scenario,
                "exit",
            )
            if result.status is not OrderStatus.FILLED:
                raise RuntimeError(f"protective research exit failed: {result.reason}")
            proceeds = sum(
                (fill.notional - fill.commission.quote_value for fill in result.fills), Decimal(0)
            )
            cash += proceeds
            execution_cost += result.costs.total_quote
            pnl = proceeds - position.entry_cost
            trades.append(
                {
                    "variant": position.signal.variant,
                    "scenario_id": scenario.scenario_id,
                    "entry_time": position.signal.entry_time.isoformat(),
                    "exit_time": timestamp.isoformat(),
                    "entry_observed_price": position.entry_observed_price,
                    "entry_fill_price": float(position.entry_fill_price),
                    "exit_observed_price": observed_open,
                    "exit_fill_price": float(result.average_fill_price),
                    "quantity": float(position.quantity),
                    "entry_cost": float(position.entry_cost),
                    "proceeds": float(proceeds),
                    "pnl": float(pnl),
                    "return_on_allocated": float(pnl / position.entry_cost),
                    "holding_hours": float(
                        (timestamp - position.signal.entry_time) / pd.Timedelta(hours=1)
                    ),
                }
            )
            position = None

        for signal in signal_by_entry.get(timestamp, []):
            if position is not None:
                skipped_overlap += 1
                continue
            decision_close_time = signal.decision_time - BAR_15M
            if decision_close_time not in prices.index:
                raise ValueError(f"missing completed decision close: {decision_close_time}")
            decision_price = float(prices.at[decision_close_time, "close"])
            equity_open = cash
            budget = min(cash, equity_open * Decimal(str(maximum_fraction)))
            adverse = Decimal(str(observed_open)) * (
                Decimal(1) + scenario.implicit_cost_bps_per_side / Decimal(10_000)
            )
            fee_factor = Decimal(1) + scenario.taker_fee_bps / Decimal(10_000)
            quantity = budget / (adverse * fee_factor)
            result = _order(
                signal,
                quantity,
                Side.BUY,
                decision_price,
                observed_open,
                timestamp,
                scenario,
                "entry",
            )
            if result.status is not OrderStatus.FILLED:
                expired_orders += int(result.status is OrderStatus.EXPIRED)
                rejected_orders += int(result.status is OrderStatus.REJECTED)
                continue
            entry_cost = sum(
                (fill.notional + fill.commission.quote_value for fill in result.fills), Decimal(0)
            )
            cash -= entry_cost
            execution_cost += result.costs.total_quote
            position = Position(
                signal=signal,
                quantity=result.filled_quantity,
                entry_cost=entry_cost,
                entry_observed_price=observed_open,
                entry_fill_price=result.average_fill_price,
            )
            equity_after = cash + result.filled_quantity * Decimal(str(observed_open))
            gross = result.filled_quantity * Decimal(str(observed_open))
            if equity_after > 0:
                max_entry_exposure = max(max_entry_exposure, gross / equity_after)

        close = Decimal(str(row["close"]))
        gross_close = position.quantity * close if position is not None else Decimal(0)
        equity = cash + gross_close
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, equity / peak - Decimal(1))
        equity_points.append((timestamp, equity))
        exposure_points.append(float(gross_close / equity) if equity > 0 else 0.0)

    if position is not None:
        raise RuntimeError("a frozen signal remained open beyond the development archive")
    equity_series = pd.Series(
        [float(value) for _, value in equity_points],
        index=pd.DatetimeIndex([timestamp for timestamp, _ in equity_points]),
    )
    daily = equity_series.resample("1D").last().dropna()
    daily_returns = daily.pct_change().dropna()
    elapsed_years = max((end - start).total_seconds() / (365.2425 * 86_400), 1 / 365.2425)
    yearly: dict[str, float] = {}
    prior = float(STARTING_EQUITY)
    for year, group in daily.groupby(daily.index.year):
        yearly[str(year)] = float(group.iloc[-1] / prior - 1.0)
        prior = float(group.iloc[-1])
    pnls = [float(row["pnl"]) for row in trades]
    allocated_returns = [float(row["return_on_allocated"]) for row in trades]
    gains = sum(value for value in pnls if value > 0)
    losses = -sum(value for value in pnls if value < 0)
    downside = daily_returns[daily_returns < 0]
    result = {
        "variant": ordered[0].variant if ordered else "no_signals",
        "scenario_id": scenario.scenario_id,
        "scenario_sha256": scenario.checksum,
        "starting_equity": float(STARTING_EQUITY),
        "simulation_start": start.isoformat(),
        "simulation_end": end.isoformat(),
        "ending_equity": float(cash),
        "net_return": float(cash / STARTING_EQUITY - Decimal(1)),
        "cagr": float((cash / STARTING_EQUITY) ** Decimal(str(1 / elapsed_years)) - Decimal(1)),
        "max_drawdown": float(max_drawdown),
        "sharpe_daily": (
            float(math.sqrt(365) * daily_returns.mean() / daily_returns.std())
            if len(daily_returns) > 1 and daily_returns.std() > 0
            else None
        ),
        "sortino_daily": (
            float(math.sqrt(365) * daily_returns.mean() / downside.std())
            if len(downside) > 1 and downside.std() > 0
            else None
        ),
        "signal_count": len(ordered),
        "filled_trades": len(trades),
        "win_rate": sum(value > 0 for value in pnls) / len(pnls) if pnls else None,
        "profit_factor": gains / losses if losses else None,
        "average_return_on_allocated": (
            statistics.fmean(allocated_returns) if allocated_returns else None
        ),
        "average_gross_exposure_fraction": (
            statistics.fmean(exposure_points) if exposure_points else 0.0
        ),
        "maximum_entry_gross_exposure_fraction": float(max_entry_exposure),
        "execution_cost_quote": float(execution_cost),
        "skipped_overlap": skipped_overlap,
        "expired_orders": expired_orders,
        "rejected_orders": rejected_orders,
        "calendar_year_returns": yearly,
        "positive_calendar_years": int(sum(value > 0 for value in yearly.values())),
    }
    return result, trades


def signal_rows(signals: Iterable[RelativeSignal]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for signal in signals:
        row = asdict(signal)
        for field in ("bar_start", "decision_time", "entry_time", "exit_time"):
            row[field] = row[field].isoformat()
        rows.append(row)
    return rows


def event_return_rows(
    signals: Sequence[RelativeSignal],
    prices: pd.DataFrame,
    scenarios: Sequence[ExecutionScenario],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for scenario in scenarios:
        for signal in signals:
            entry = float(prices.at[signal.entry_time, "open"])
            exit_price = float(prices.at[signal.exit_time, "open"])
            rows.append(
                {
                    "variant": signal.variant,
                    "scenario_id": scenario.scenario_id,
                    "entry_time": signal.entry_time.isoformat(),
                    "exit_time": signal.exit_time.isoformat(),
                    "entry_open": entry,
                    "exit_open": exit_price,
                    "net_return_on_allocated": friction_adjusted_return(
                        entry, exit_price, scenario
                    ),
                }
            )
    return rows


def buy_hold_baselines(
    frame: pd.DataFrame, scenarios: Sequence[ExecutionScenario]
) -> list[dict[str, Any]]:
    start = frame.iloc[0]
    end = frame.iloc[-1]
    rows = []
    for scenario in scenarios:
        allocated = friction_adjusted_return(
            float(start["open"]), float(end["close"]), scenario
        )
        rows.append(
            {
                "baseline": "btc_buy_hold_25pct_initial_equity",
                "scenario_id": scenario.scenario_id,
                "start": start["date"].isoformat(),
                "end": end["date"].isoformat(),
                "return_on_allocated": allocated,
                "account_net_return": 0.25 * allocated,
            }
        )
    return rows


def matched_random_statistics(
    primary_signals: Sequence[RelativeSignal],
    risk_on_signals: Sequence[RelativeSignal],
    prices: pd.DataFrame,
    primary_scenario: ExecutionScenario,
    simulations: int,
    seed: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    signal_times = {signal.entry_time for signal in primary_signals}
    candidate_by_month: dict[str, list[float]] = {}
    for signal in risk_on_signals:
        if signal.entry_time in signal_times:
            continue
        value = friction_adjusted_return(
            float(prices.at[signal.entry_time, "open"]),
            float(prices.at[signal.exit_time, "open"]),
            primary_scenario,
        )
        candidate_by_month.setdefault(signal.entry_time.strftime("%Y-%m"), []).append(value)
    pools: list[np.ndarray] = []
    pool_sizes: dict[str, int] = {}
    for signal in primary_signals:
        month = signal.entry_time.strftime("%Y-%m")
        pool = np.asarray(candidate_by_month.get(month, []), dtype=float)
        if len(pool) == 0:
            raise ValueError(f"no non-signal joint-risk-on match is available for {month}")
        pools.append(pool)
        pool_sizes[signal.entry_time.isoformat()] = int(len(pool))
    distribution = matched_gate_distribution(pools, simulations, seed)
    observed_values = [
        friction_adjusted_return(
            float(prices.at[signal.entry_time, "open"]),
            float(prices.at[signal.exit_time, "open"]),
            primary_scenario,
        )
        for signal in primary_signals
    ]
    observed = float(np.mean(observed_values))
    statistics_row = {
        "observed_mean_return": observed,
        "random_mean_return": float(distribution.mean()),
        "one_sided_p_value": one_sided_randomization_p(observed, distribution),
        "observed_percentile": randomization_percentile(observed, distribution),
        "simulations": simulations,
        "seed": seed,
        "minimum_month_pool_size": min(pool_sizes.values()),
        "maximum_month_pool_size": max(pool_sizes.values()),
    }
    rows = [
        {"simulation": index, "mean_return": float(value)}
        for index, value in enumerate(distribution)
    ]
    return statistics_row, rows


def build_gates(
    spec: dict[str, Any],
    primary: dict[str, Any],
    severe: dict[str, Any],
    primary_event_values: Sequence[float],
    interval: dict[str, float],
    random_stats: dict[str, Any],
    self_event_mean: float,
    concentration: dict[str, Any],
    sensitivity_results: Sequence[dict[str, Any]],
) -> dict[str, bool]:
    gates = spec["acceptance_gates"]
    mean_value = float(np.mean(primary_event_values))
    return {
        "minimum_filled_primary_trades": primary["filled_trades"]
        >= gates["minimum_filled_primary_trades"],
        "primary_30bps_net_return_positive": primary["net_return"] > 0,
        "severe_80bps_net_return_positive": severe["net_return"] > 0,
        "primary_profit_factor_minimum": primary["profit_factor"] is not None
        and primary["profit_factor"] >= gates["primary_profit_factor_minimum"],
        "primary_max_drawdown_fraction": primary["max_drawdown"]
        >= -gates["primary_max_drawdown_fraction"],
        "primary_event_mean_positive": mean_value
        > gates["primary_event_mean_bps_strictly_above"] / 10_000,
        "primary_event_bootstrap_lower_95_positive": interval["lower"]
        > gates["primary_event_bootstrap_lower_95_bps_strictly_above"] / 10_000,
        "calendar_matched_random_p_maximum": random_stats["one_sided_p_value"]
        <= gates["calendar_matched_random_one_sided_p_maximum"],
        "candidate_beats_btc_self_reversal_mean": mean_value - self_event_mean
        > gates["candidate_minus_btc_self_reversal_mean_bps_strictly_above"] / 10_000,
        "positive_calendar_years_minimum": primary["positive_calendar_years"]
        >= gates["positive_calendar_years_minimum"],
        "top_three_profitable_months_share_maximum": concentration["share"] is not None
        and concentration["share"] <= gates["top_three_profitable_months_share_maximum"],
        "positive_primary_cost_sensitivities_minimum": sum(
            result["net_return"] > 0 for result in sensitivity_results
        )
        >= gates["positive_primary_cost_sensitivities_minimum"],
        "maximum_entry_gross_exposure_fraction": primary[
            "maximum_entry_gross_exposure_fraction"
        ]
        <= gates["maximum_entry_gross_exposure_fraction"] + 1e-9,
        "no_post_decision_information": True,
        "sealed_2026_not_read": True,
    }


def write_csv_gz(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    pd.DataFrame(rows).to_csv(
        path,
        index=False,
        compression={"method": "gzip", "mtime": 0},
        float_format="%.12g",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--spec", type=Path, default=Path("config/experiments/btc-eth-relative-catchup-r2-v1.json")
    )
    parser.add_argument(
        "--scenario-config", type=Path, default=Path("config/execution_scenarios.json")
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("artifacts/agent-level-experiment/multi-asset-top2/development-input"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(
            "artifacts/agent-level-experiment/btc-eth-relative-catchup-r2/development-v1"
        ),
    )
    args = parser.parse_args()

    spec_path = (REPO_ROOT / args.spec).resolve() if not args.spec.is_absolute() else args.spec
    scenario_path = (
        (REPO_ROOT / args.scenario_config).resolve()
        if not args.scenario_config.is_absolute()
        else args.scenario_config
    )
    data_dir = (REPO_ROOT / args.data_dir).resolve() if not args.data_dir.is_absolute() else args.data_dir
    output_dir = REPO_ROOT / args.output_dir if not args.output_dir.is_absolute() else args.output_dir
    spec = load_spec(spec_path)
    output_root = REPO_ROOT / spec["isolation"]["allowed_output_root"]
    output_root.mkdir(parents=True, exist_ok=True)
    output_dir = require_output_path(output_dir, output_root)
    if output_dir.exists() and any(output_dir.iterdir()):
        parser.error(f"refusing to overwrite non-empty output directory: {output_dir}")

    frames, quality = load_inputs(spec, data_dir)
    btc = frames[BTC_PAIR]
    eth = frames[ETH_PAIR]
    prices = _price_frame(btc)
    start = pd.Timestamp(spec["data"]["development_start"])
    end = pd.Timestamp(spec["data"]["development_end_exclusive"])
    primary_model = spec["primary_model"]
    primary_features = relative_feature_frame(
        btc,
        eth,
        int(primary_model["beta_window_bars"]),
        float(primary_model["residual_quantile"]),
    )
    primary_raw = make_relative_signals(
        primary_features,
        "primary_relative_catchup",
        int(primary_model["holding_period_hours"]),
        start,
        end,
    )
    primary_signals, primary_invalid_paths = filter_executable_signals(primary_raw, prices)
    if not primary_signals:
        raise RuntimeError("frozen R2 hypothesis produced no executable signals")
    self_raw = make_btc_self_reversal_signals(
        primary_features, int(primary_model["holding_period_hours"]), start, end
    )
    self_signals, self_invalid_paths = filter_executable_signals(self_raw, prices)
    risk_on_raw = make_joint_risk_on_signals(
        primary_features, int(primary_model["holding_period_hours"]), start, end
    )
    risk_on_signals, risk_on_invalid_paths = filter_executable_signals(risk_on_raw, prices)

    scenario_map = load_scenarios(scenario_path)
    scenario_ids = spec["execution_scenarios"]
    scenarios = [scenario_map[scenario_id] for scenario_id in scenario_ids]
    primary_scenario = scenario_map["candle-primary-30bps-rt-v1"]
    results: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    for scenario in scenarios:
        result, rows = run_backtest(btc, primary_signals, scenario)
        results.append(result)
        trades.extend(rows)
    for variant, signals in (
        ("btc_self_reversal", self_signals),
        ("joint_risk_on_every_24h", risk_on_signals),
    ):
        result, rows = run_backtest(btc, signals, primary_scenario)
        result["variant"] = variant
        results.append(result)
        trades.extend(rows)

    sensitivity_results: list[dict[str, Any]] = []
    sensitivity_signals: list[RelativeSignal] = []
    sensitivity_invalid_paths: dict[str, int] = {}
    for frozen in spec["predeclared_sensitivities"]:
        features = relative_feature_frame(
            btc,
            eth,
            int(frozen["beta_window_bars"]),
            float(frozen["residual_quantile"]),
        )
        raw = make_relative_signals(
            features,
            frozen["variant"],
            int(frozen["holding_period_hours"]),
            start,
            end,
        )
        valid, invalid_count = filter_executable_signals(raw, prices)
        sensitivity_invalid_paths[frozen["variant"]] = invalid_count
        result, rows = run_backtest(btc, valid, primary_scenario)
        result["variant"] = frozen["variant"]
        sensitivity_results.append(result)
        sensitivity_signals.extend(valid)
        trades.extend(rows)

    event_rows = event_return_rows(
        [*primary_signals, *self_signals, *risk_on_signals, *sensitivity_signals],
        prices,
        scenarios,
    )
    primary_event = [
        row
        for row in event_rows
        if row["variant"] == "primary_relative_catchup"
        and row["scenario_id"] == primary_scenario.scenario_id
    ]
    primary_event_values = [row["net_return_on_allocated"] for row in primary_event]
    self_event_values = [
        row["net_return_on_allocated"]
        for row in event_rows
        if row["variant"] == "btc_self_reversal"
        and row["scenario_id"] == primary_scenario.scenario_id
    ]
    bootstrap = spec["statistics"]
    interval = block_bootstrap_mean_interval(
        primary_event_values,
        [pd.Timestamp(row["entry_time"]).strftime("%Y-%m") for row in primary_event],
        int(bootstrap["bootstrap_replications"]),
        int(bootstrap["bootstrap_seed"]),
        float(bootstrap["confidence_interval"]),
    )
    random_spec = spec["matched_controls"]["calendar_matched_random"]
    random_stats, random_rows = matched_random_statistics(
        primary_signals,
        risk_on_signals,
        prices,
        primary_scenario,
        int(random_spec["simulations"]),
        int(random_spec["seed"]),
    )
    primary_result = next(
        row
        for row in results
        if row["variant"] == "primary_relative_catchup"
        and row["scenario_id"] == primary_scenario.scenario_id
    )
    severe_result = next(
        row
        for row in results
        if row["variant"] == "primary_relative_catchup"
        and row["scenario_id"] == "candle-severe-80bps-rt-v1"
    )
    primary_trade_rows = [
        row
        for row in trades
        if row["variant"] == "primary_relative_catchup"
        and row["scenario_id"] == primary_scenario.scenario_id
    ]
    concentration = profitable_period_concentration(primary_trade_rows, top_n=3)
    self_event_mean = float(np.mean(self_event_values))
    gates = build_gates(
        spec,
        primary_result,
        severe_result,
        primary_event_values,
        interval,
        random_stats,
        self_event_mean,
        concentration,
        sensitivity_results,
    )
    decision = "development_mechanism_pass" if all(gates.values()) else "development_mechanism_reject"

    output_dir.mkdir(parents=True, exist_ok=False)
    write_csv_gz(
        output_dir / "signals.csv.gz",
        signal_rows([*primary_signals, *self_signals, *risk_on_signals, *sensitivity_signals]),
    )
    write_csv_gz(output_dir / "trades.csv.gz", trades)
    write_csv_gz(output_dir / "event_returns.csv.gz", event_rows)
    write_csv_gz(output_dir / "random_distribution.csv.gz", random_rows)
    report = {
        "experiment_id": spec["experiment_id"],
        "decision": decision,
        "promotion_eligible": False,
        "promotion_blockers": spec["promotion_blockers"],
        "development_end_exclusive": end.isoformat(),
        "sealed_2026_read": False,
        "traded_pair": BTC_PAIR,
        "context_only_pair": ETH_PAIR,
        "signal_counts": {
            "primary_raw": len(primary_raw),
            "primary_executable": len(primary_signals),
            "primary_invalid_path": primary_invalid_paths,
            "btc_self_executable": len(self_signals),
            "btc_self_invalid_path": self_invalid_paths,
            "joint_risk_on_executable": len(risk_on_signals),
            "joint_risk_on_invalid_path": risk_on_invalid_paths,
            "sensitivity_invalid_paths": sensitivity_invalid_paths,
        },
        "data_quality": quality,
        "capital_model": "single 1000 USDT account; BTC spot long/flat; one position; 25 percent current-equity allocation; no leverage",
        "execution_model": "completed UTC 4h information; first 15m open; shared candle taker scenarios; exact 24h/variant exit; protective exit",
        "results": results,
        "sensitivity_results": sensitivity_results,
        "buy_hold_baselines": buy_hold_baselines(btc, scenarios),
        "statistics": {
            "primary_event_mean_return": float(np.mean(primary_event_values)),
            "primary_event_mean_bps": float(np.mean(primary_event_values) * 10_000),
            "primary_event_month_block_bootstrap": interval,
            "btc_self_reversal_event_mean_return": self_event_mean,
            "candidate_minus_btc_self_event_mean_bps": float(
                (np.mean(primary_event_values) - self_event_mean) * 10_000
            ),
            "calendar_matched_random": random_stats,
            "primary_trade_month_concentration": concentration,
        },
        "gates": gates,
        "failed_gates": sorted(name for name, passed in gates.items() if not passed),
        "limitations": [
            "The development interval and related BTC/ETH features were inspected previously, so this run can reject but cannot independently promote the mechanism.",
            "Candle execution cannot prove intrabar liquidity or partial-fill behavior.",
            "Generic current-like BTC tick, lot, and minimum-notional rules are used because historical exchangeInfo snapshots are unavailable.",
            "ETH contributes context only; no ETH order, rotation, leverage, or short exposure is simulated.",
        ],
    }
    (output_dir / "report.json").write_text(canonical_json(report), encoding="utf-8")
    manifest = {
        "schema_version": "research-result-manifest-v1",
        "experiment_id": spec["experiment_id"],
        "experiment_sha256": sha256_file(spec_path),
        "scenario_config_sha256": sha256_file(scenario_path),
        "runner_sha256": sha256_file(Path(__file__)),
        "relative_feature_module_sha256": sha256_file(
            REPO_ROOT / "src/trading_platform/research_relative.py"
        ),
        "inputs": {row["pair"]: row["sha256"] for row in quality},
        "outputs": {
            name: sha256_file(output_dir / name)
            for name in (
                "report.json",
                "signals.csv.gz",
                "trades.csv.gz",
                "event_returns.csv.gz",
                "random_distribution.csv.gz",
            )
        },
    }
    (output_dir / "manifest.json").write_text(canonical_json(manifest), encoding="utf-8")
    print(
        canonical_json(
            {
                "output_dir": str(output_dir.relative_to(REPO_ROOT)),
                "decision": decision,
                "failed_gates": report["failed_gates"],
                "primary_result": primary_result,
                "statistics": report["statistics"],
            }
        )
    )


if __name__ == "__main__":
    main()
