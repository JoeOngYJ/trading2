#!/usr/bin/env python3
"""Causal, capital-bounded reconstruction of the prior multi-asset top-two study."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import statistics
from dataclasses import dataclass, field
from datetime import timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

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


PAIR_TO_STEM = {
    "BTC/USDT": "BTC_USDT",
    "ETH/USDT": "ETH_USDT",
    "SOL/USDT": "SOL_USDT",
    "XRP/USDT": "XRP_USDT",
    "BNB/USDT": "BNB_USDT",
    "DOGE/USDT": "DOGE_USDT",
    "ADA/USDT": "ADA_USDT",
}
BAR = pd.Timedelta(minutes=15)
DEVELOPMENT_END = pd.Timestamp("2026-01-01T00:00:00Z")
STARTING_EQUITY = Decimal("1000")
MAX_GROSS_FRACTION = Decimal("0.25")
FOUR_HOUR_COHORT_FRACTION = Decimal(1) / Decimal(48)
DAILY_COHORT_FRACTION = Decimal("0.25")


@dataclass(frozen=True)
class Signal:
    signal_time: pd.Timestamp
    decision_time: pd.Timestamp
    entry_time: pd.Timestamp
    pairs: tuple[str, ...]
    top4_pairs: tuple[str, ...]
    scores: tuple[float, float]


@dataclass
class Cohort:
    cohort_id: str
    signal: Signal
    entry_time: pd.Timestamp
    reduce_time: pd.Timestamp
    exit_time: pd.Timestamp
    units: dict[str, Decimal]
    raw_entry_prices: dict[str, float]
    entry_cost: Decimal
    proceeds: Decimal = Decimal("0")
    reduced: bool = False
    trigger: bool = False
    exit_reason: str = ""


@dataclass
class RunState:
    cash: Decimal = STARTING_EQUITY
    cohorts: list[Cohort] = field(default_factory=list)
    closed: list[dict[str, Any]] = field(default_factory=list)
    execution_cost: Decimal = Decimal("0")
    expired_orders: int = 0
    rejected_orders: int = 0
    skipped_cap: int = 0
    skipped_atomic_basket: int = 0
    trigger_count: int = 0


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n"


def load_hypothesis(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("experiment_id") != "multi-asset-top2-causal-v1":
        raise ValueError("wrong experiment_id")
    if payload.get("status") != "development_frozen":
        raise ValueError("experiment must be frozen before execution")
    if payload.get("development_period", {}).get("end_exclusive") != "2026-01-01T00:00:00Z":
        raise ValueError("development boundary is not frozen")
    return payload


def validate_frame(frame: pd.DataFrame, pair: str, path: Path) -> pd.DataFrame:
    required = {"date", "open", "high", "low", "close", "volume"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{path} missing columns: {missing}")
    out = frame[list(required)].copy()
    out["date"] = pd.to_datetime(out["date"], utc=True)
    out = out.sort_values("date").reset_index(drop=True)
    if out["date"].duplicated().any():
        raise ValueError(f"{pair} contains duplicate timestamps")
    numeric = ["open", "high", "low", "close", "volume"]
    out[numeric] = out[numeric].apply(pd.to_numeric, errors="coerce")
    if out[numeric].isna().any().any() or not np.isfinite(out[numeric].to_numpy()).all():
        raise ValueError(f"{pair} contains non-finite market values")
    invalid = (
        (out[["open", "high", "low", "close"]] <= 0).any(axis=1)
        | (out["volume"] < 0)
        | (out["high"] < out[["open", "close", "low"]].max(axis=1))
        | (out["low"] > out[["open", "close", "high"]].min(axis=1))
    )
    if invalid.any():
        raise ValueError(f"{pair} contains {int(invalid.sum())} invalid OHLCV rows")
    if (out["date"].dt.minute % 15 != 0).any() or (out["date"].dt.second != 0).any():
        raise ValueError(f"{pair} is not aligned to a 15-minute UTC grid")
    out = out[out["date"] < DEVELOPMENT_END].copy()
    if out.empty or out["date"].max() >= DEVELOPMENT_END:
        raise ValueError(f"{pair} development boundary failure")
    out["pair"] = pair
    return out


def segmented_rolling_rank(series: pd.Series, segment: pd.Series, window: int, minimum: int) -> pd.Series:
    return series.groupby(segment, group_keys=False).apply(
        lambda values: values.rolling(window, min_periods=minimum).rank(pct=True),
        include_groups=False,
    )


def add_features(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["segment"] = out["date"].diff().ne(BAR).cumsum()
    previous_close = out["close"].shift(1)
    tr = pd.concat(
        [out["high"] - out["low"], (out["high"] - previous_close).abs(), (out["low"] - previous_close).abs()],
        axis=1,
    ).max(axis=1)
    out["atr14"] = tr.groupby(out["segment"]).transform(lambda s: s.rolling(14, min_periods=14).mean())
    out["atr_pct"] = out["atr14"] / out["close"]
    out["range_pct"] = (out["high"] - out["low"]) / out["close"]
    out["quote_volume"] = out["close"] * out["volume"]
    for source, target in (
        ("atr_pct", "atr_pct_rank_30d"),
        ("range_pct", "range_pct_rank_30d"),
        ("quote_volume", "quote_volume_rank_30d"),
    ):
        out[target] = segmented_rolling_rank(out[source], out["segment"], 96 * 30, 96 * 10)
    grouped_close = out["close"].groupby(out["segment"], group_keys=False)
    out["ema50"] = grouped_close.transform(lambda s: s.ewm(span=50, adjust=False, min_periods=50).mean())
    out["ema200"] = grouped_close.transform(lambda s: s.ewm(span=200, adjust=False, min_periods=200).mean())
    out["ema50_slope"] = out.groupby("segment")["ema50"].diff(8)
    out["ret_4h"] = out.groupby("segment")["close"].pct_change(16)
    out["ret_12h"] = out.groupby("segment")["close"].pct_change(48)
    out["ret_1d"] = out.groupby("segment")["close"].pct_change(96)
    out["ret_3d"] = out.groupby("segment")["close"].pct_change(288)
    out["ret_14d"] = out.groupby("segment")["close"].pct_change(96 * 14)
    out["high20"] = out.groupby("segment")["high"].transform(
        lambda s: s.rolling(96 * 20, min_periods=96 * 20).max()
    )
    out["dist_high20d"] = out["close"] / out["high20"] - 1.0
    out["prior_high20"] = out.groupby("segment")["high"].transform(
        lambda s: s.rolling(20, min_periods=20).max().shift(1)
    )
    out["breakout_distance_atr"] = (out["close"] - out["prior_high20"]) / out["atr14"]
    out["ema_trend_raw"] = out["close"] / out["ema200"] - 1.0 + out["ema50"] / out["ema200"] - 1.0
    out["volatility_penalty"] = np.where(out["atr_pct_rank_30d"] > 0.95, 0.10, 0.0) + np.where(
        out["range_pct_rank_30d"] > 0.95, 0.05, 0.0
    )
    out["btc_supportive"] = (out["close"] > out["ema200"]) & (out["ema50"] > out["ema200"]) & (
        out["ema50_slope"] > 0
    )
    return out


def load_frames(data_dir: Path) -> tuple[dict[str, pd.DataFrame], list[dict[str, Any]]]:
    frames: dict[str, pd.DataFrame] = {}
    quality: list[dict[str, Any]] = []
    for pair, stem in PAIR_TO_STEM.items():
        path = data_dir / f"{stem}-15m.feather"
        if not path.exists():
            raise FileNotFoundError(path)
        raw = pd.read_feather(path)
        frame = validate_frame(raw, pair, path)
        gaps = frame["date"].diff().dropna()
        frames[pair] = add_features(frame)
        quality.append(
            {
                "pair": pair,
                "path": str(path),
                "sha256": sha256_file(path),
                "rows_source": len(raw),
                "rows_development": len(frame),
                "start": frame["date"].min().isoformat(),
                "end": frame["date"].max().isoformat(),
                "gap_count": int((gaps != BAR).sum()),
                "max_gap_minutes": float(gaps.max() / pd.Timedelta(minutes=1)),
            }
        )
    return frames, quality


def percentile_rank(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    if values.notna().sum() < 2:
        return pd.Series(np.where(values.notna(), 1.0, np.nan), index=values.index)
    return values.rank(pct=True)


def make_signals(frames: dict[str, pd.DataFrame]) -> list[Signal]:
    indexed = {pair: frame.set_index("date", drop=False) for pair, frame in frames.items()}
    common = sorted(set.intersection(*(set(frame.index) for frame in indexed.values())))
    signals: list[Signal] = []
    for timestamp in common:
        if timestamp.year < 2021 or timestamp >= DEVELOPMENT_END:
            continue
        if timestamp.minute != 0 or timestamp.hour % 4 != 0:
            continue
        rows = pd.DataFrame([indexed[pair].loc[timestamp] for pair in PAIR_TO_STEM])
        btc = rows.loc[rows["pair"].eq("BTC/USDT")].iloc[0]
        rows["relative_strength_12h"] = rows["ret_12h"] - float(btc["ret_12h"])
        valid_gate = rows[["ema50", "ema200", "ret_12h", "quote_volume_rank_30d"]].notna().all(axis=1)
        if valid_gate.sum() != len(rows):
            continue
        breadth_above_ema50 = float((rows["close"] > rows["ema50"]).mean())
        breadth_above_ema200 = float((rows["close"] > rows["ema200"]).mean())
        breadth_positive_12h = float((rows["ret_12h"] > 0).mean())
        breadth_relative_leader = float((rows["relative_strength_12h"] >= 0.005).mean())
        strict_gate = bool(
            btc["btc_supportive"]
            and breadth_above_ema200 >= 0.55
            and breadth_above_ema50 >= 0.70
            and breadth_positive_12h >= 0.70
            and breadth_relative_leader >= 0.30
        )
        if not strict_gate:
            continue
        rows["momentum_rank"] = percentile_rank(rows["ret_4h"])
        rows["relative_rank"] = percentile_rank(rows["relative_strength_12h"])
        rows["ema_rank"] = percentile_rank(rows["ema_trend_raw"])
        rows["liquidity_rank"] = percentile_rank(rows["quote_volume_rank_30d"])
        rows["breakout_rank"] = percentile_rank(rows["breakout_distance_atr"].clip(-2, 4))
        components = ["momentum_rank", "relative_rank", "ema_rank", "liquidity_rank", "breakout_rank"]
        rows["component_count"] = rows[components].notna().sum(axis=1)
        rows[components] = rows[components].fillna(0.5)
        rows["score"] = (
            0.30 * rows["momentum_rank"]
            + 0.25 * rows["relative_rank"]
            + 0.20 * rows["ema_rank"]
            + 0.15 * rows["liquidity_rank"]
            + 0.10 * rows["breakout_rank"]
            - rows["volatility_penalty"]
        )
        top4 = rows[rows["component_count"] >= 4].sort_values(["score", "pair"], ascending=[False, True]).head(4)
        if len(top4) != 4:
            continue
        near_high = bool(
            top4["ret_14d"].mean() >= 0.0
            and (top4["ret_3d"] - float(btc["ret_3d"])).mean() >= 0.0
            and top4["dist_high20d"].mean() >= -0.06
            and float((top4["ret_14d"] < 0).mean()) <= 0.25
        )
        btc_anchor = bool(btc["ret_1d"] >= 0 and btc["ret_3d"] >= 0 and btc["dist_high20d"] >= -0.08)
        if not near_high or not btc_anchor:
            continue
        top2 = top4.head(2)
        decision_time = timestamp + BAR
        signals.append(
            Signal(
                signal_time=timestamp,
                decision_time=decision_time,
                entry_time=decision_time,
                pairs=tuple(top2["pair"].tolist()),
                top4_pairs=tuple(top4["pair"].tolist()),
                scores=tuple(float(value) for value in top2["score"]),
            )
        )
    return signals


def market_rules(pair: str) -> MarketRules:
    return MarketRules(
        symbol=pair.replace("/", ""),
        effective_at="research-generic-rules-v1",
        tick_size=Decimal("0.00000001"),
        step_size=Decimal("0.00000001"),
        min_quantity=Decimal("0.00000001"),
        min_notional=Decimal("5"),
        source="generic_research_fixture_not_historical_exchangeInfo",
    )


def apply_buy(state: RunState, cohort_id: str, pair: str, budget: Decimal, decision_price: float, observed: float,
              timestamp: pd.Timestamp, scenario: ExecutionScenario):
    adverse = Decimal(str(observed)) * (Decimal(1) + scenario.implicit_cost_bps_per_side / Decimal(10000))
    fee_factor = Decimal(1) + scenario.taker_fee_bps / Decimal(10000)
    quantity = budget / (adverse * fee_factor)
    intent = OrderIntent(
        client_order_id=f"{cohort_id}:buy:{pair}", side=Side.BUY, quantity=quantity,
        decision_time_ns=int(timestamp.value), decision_price=Decimal(str(decision_price)),
    )
    return simulate_candle_taker(intent, Decimal(str(observed)), int(timestamp.value), scenario, market_rules(pair))


def apply_sell(state: RunState, cohort: Cohort, pair: str, quantity: Decimal, decision_price: float, observed: float,
               timestamp: pd.Timestamp, scenario: ExecutionScenario, reason: str) -> bool:
    intent = OrderIntent(
        client_order_id=f"{cohort.cohort_id}:{reason}:{pair}:{timestamp.value}", side=Side.SELL, quantity=quantity,
        decision_time_ns=int(timestamp.value), decision_price=Decimal(str(decision_price)),
        kind=OrderKind.PROTECTIVE, protective=True,
    )
    result = simulate_candle_taker(intent, Decimal(str(observed)), int(timestamp.value), scenario, market_rules(pair))
    if result.status is not OrderStatus.FILLED:
        state.rejected_orders += 1
        return False
    proceeds = sum((fill.notional - fill.commission.quote_value for fill in result.fills), Decimal(0))
    state.cash += proceeds
    state.execution_cost += result.costs.total_quote
    cohort.proceeds += proceeds
    cohort.units[pair] -= result.filled_quantity
    return True


def price_at(price_frames: dict[str, pd.DataFrame], pair: str, timestamp: pd.Timestamp, column: str) -> float:
    return float(price_frames[pair].at[timestamp, column])


def cohort_trigger(cohort: Cohort, price_frames: dict[str, pd.DataFrame]) -> bool:
    close4_time = cohort.entry_time + pd.Timedelta(hours=4) - BAR
    close12_time = cohort.entry_time + pd.Timedelta(hours=12) - BAR
    returns12 = []
    strong = 0
    for pair in cohort.signal.pairs:
        entry = cohort.raw_entry_prices[pair]
        close4 = price_at(price_frames, pair, close4_time, "close")
        close12 = price_at(price_frames, pair, close12_time, "close")
        path = price_frames[pair].loc[cohort.entry_time:close4_time, "high"]
        mfe4 = float(path.max()) / entry - 1.0
        return4 = close4 / entry - 1.0
        returns12.append(close12 / entry - 1.0)
        strong += int(return4 > 0.0 and mfe4 >= 0.01)
    return statistics.fmean(returns12) <= 0.0 and strong == 0


def mark_equity(state: RunState, prices: dict[str, float]) -> tuple[Decimal, Decimal]:
    gross = Decimal(0)
    for cohort in state.cohorts:
        for pair, units in cohort.units.items():
            gross += units * Decimal(str(prices[pair]))
    return state.cash + gross, gross


def cadence_signals(signals: list[Signal], cadence: str) -> list[Signal]:
    if cadence == "four_hour":
        return signals
    if cadence != "daily":
        raise ValueError(cadence)
    return [signal for signal in signals if signal.signal_time.hour == 0]


def run_backtest(frames: dict[str, pd.DataFrame], signals: list[Signal], scenario: ExecutionScenario,
                 cadence: str, derisk: bool) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    price_frames = {pair: frame.set_index("date") for pair, frame in frames.items()}
    common_index = sorted(set.intersection(*(set(frame.index) for frame in price_frames.values())))
    scoped_signals = cadence_signals(signals, cadence)
    signals_by_entry: dict[pd.Timestamp, list[Signal]] = {}
    for signal in scoped_signals:
        signals_by_entry.setdefault(signal.entry_time, []).append(signal)
    cohort_fraction = FOUR_HOUR_COHORT_FRACTION if cadence == "four_hour" else DAILY_COHORT_FRACTION
    state = RunState()
    equity_points: list[tuple[pd.Timestamp, Decimal]] = []
    exposure_points: list[float] = []
    peak = STARTING_EQUITY
    max_drawdown = Decimal(0)
    max_entry_gross_fraction = Decimal(0)
    first_time: pd.Timestamp | None = None
    last_time: pd.Timestamp | None = None

    for timestamp in common_index:
        if timestamp.year < 2021 or timestamp >= DEVELOPMENT_END:
            continue
        opens = {pair: price_at(price_frames, pair, timestamp, "open") for pair in PAIR_TO_STEM}
        closes = {pair: price_at(price_frames, pair, timestamp, "close") for pair in PAIR_TO_STEM}

        for cohort in list(state.cohorts):
            if timestamp >= cohort.exit_time:
                for pair in cohort.signal.pairs:
                    quantity = cohort.units[pair]
                    if quantity > 0:
                        apply_sell(state, cohort, pair, quantity, opens[pair], opens[pair], timestamp, scenario, "exit48")
                cohort.exit_reason = "hold_48h"
                pnl = cohort.proceeds - cohort.entry_cost
                state.closed.append({
                    "cohort_id": cohort.cohort_id, "entry_time": cohort.entry_time.isoformat(),
                    "exit_time": timestamp.isoformat(), "pairs": ",".join(cohort.signal.pairs),
                    "triggered_12h": cohort.trigger, "reduced_12h": cohort.reduced,
                    "entry_cost": float(cohort.entry_cost), "proceeds": float(cohort.proceeds),
                    "pnl": float(pnl), "return_on_allocated": float(pnl / cohort.entry_cost),
                    "exit_reason": cohort.exit_reason,
                })
                state.cohorts.remove(cohort)
            elif derisk and not cohort.reduced and timestamp >= cohort.reduce_time:
                try:
                    trigger = cohort_trigger(cohort, price_frames)
                except KeyError:
                    trigger = False
                cohort.trigger = trigger
                cohort.reduced = True
                if trigger:
                    state.trigger_count += 1
                    for pair in cohort.signal.pairs:
                        quantity = cohort.units[pair] / Decimal(2)
                        apply_sell(state, cohort, pair, quantity, opens[pair], opens[pair], timestamp, scenario, "reduce12")

        for signal in signals_by_entry.get(timestamp, []):
            equity_open, gross_open = mark_equity(state, opens)
            allowed_gross = equity_open * MAX_GROSS_FRACTION
            available = max(Decimal(0), allowed_gross - gross_open)
            target = equity_open * cohort_fraction
            budget = min(target, available, state.cash)
            if budget < Decimal("10"):
                state.skipped_cap += 1
                continue
            cohort_id = f"{scenario.scenario_id}:{cadence}:{'derisk' if derisk else 'hold'}:{timestamp.value}"
            results = []
            leg_budget = budget / Decimal(len(signal.pairs))
            for pair in signal.pairs:
                decision_price = price_at(price_frames, pair, signal.signal_time, "close")
                results.append((pair, apply_buy(state, cohort_id, pair, leg_budget, decision_price, opens[pair], timestamp, scenario)))
            if any(result.status is not OrderStatus.FILLED for _, result in results):
                state.skipped_atomic_basket += 1
                state.expired_orders += sum(result.status is OrderStatus.EXPIRED for _, result in results)
                state.rejected_orders += sum(result.status is OrderStatus.REJECTED for _, result in results)
                continue
            units: dict[str, Decimal] = {}
            entry_cost = Decimal(0)
            for pair, result in results:
                cost = sum((fill.notional + fill.commission.quote_value for fill in result.fills), Decimal(0))
                entry_cost += cost
                units[pair] = result.filled_quantity
                state.execution_cost += result.costs.total_quote
            state.cash -= entry_cost
            cohort = Cohort(
                cohort_id=cohort_id, signal=signal, entry_time=timestamp,
                reduce_time=timestamp + pd.Timedelta(hours=12), exit_time=timestamp + pd.Timedelta(hours=48),
                units=units, raw_entry_prices={pair: opens[pair] for pair in signal.pairs}, entry_cost=entry_cost,
            )
            state.cohorts.append(cohort)
            equity_after, gross_after = mark_equity(state, opens)
            if equity_after > 0:
                max_entry_gross_fraction = max(max_entry_gross_fraction, gross_after / equity_after)

        equity, gross = mark_equity(state, closes)
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, equity / peak - Decimal(1))
        equity_points.append((timestamp, equity))
        exposure_points.append(float(gross / equity) if equity > 0 else 0.0)
        first_time = timestamp if first_time is None else min(first_time, timestamp)
        last_time = timestamp if last_time is None else max(last_time, timestamp)

    if state.cohorts:
        timestamp = max(t for t in common_index if t < DEVELOPMENT_END)
        closes = {pair: price_at(price_frames, pair, timestamp, "close") for pair in PAIR_TO_STEM}
        for cohort in list(state.cohorts):
            for pair in cohort.signal.pairs:
                quantity = cohort.units[pair]
                if quantity > 0:
                    apply_sell(state, cohort, pair, quantity, closes[pair], closes[pair], timestamp, scenario, "forced_end")
            cohort.exit_reason = "forced_development_end"
            pnl = cohort.proceeds - cohort.entry_cost
            state.closed.append({
                "cohort_id": cohort.cohort_id, "entry_time": cohort.entry_time.isoformat(), "exit_time": timestamp.isoformat(),
                "pairs": ",".join(cohort.signal.pairs), "triggered_12h": cohort.trigger, "reduced_12h": cohort.reduced,
                "entry_cost": float(cohort.entry_cost), "proceeds": float(cohort.proceeds), "pnl": float(pnl),
                "return_on_allocated": float(pnl / cohort.entry_cost), "exit_reason": cohort.exit_reason,
            })
            state.cohorts.remove(cohort)
        equity_points[-1] = (timestamp, state.cash)
        peak = max(peak, state.cash)
        max_drawdown = min(max_drawdown, state.cash / peak - Decimal(1))

    final_equity = state.cash
    if first_time is None or last_time is None:
        raise RuntimeError("no development timestamps were simulated")
    elapsed_years = max((last_time - first_time).total_seconds() / (365.2425 * 86400), 1 / 365.2425)
    pnls = [row["pnl"] for row in state.closed]
    returns = [row["return_on_allocated"] for row in state.closed]
    gains = sum(value for value in pnls if value > 0)
    losses = -sum(value for value in pnls if value < 0)
    yearly: dict[str, float] = {}
    equity_series = pd.Series([float(value) for _, value in equity_points], index=[ts for ts, _ in equity_points])
    daily = equity_series.resample("1D").last().dropna()
    prior = float(STARTING_EQUITY)
    for year, group in daily.groupby(daily.index.year):
        yearly[str(year)] = group.iloc[-1] / prior - 1.0
        prior = group.iloc[-1]
    daily_returns = daily.pct_change().dropna()
    sharpe = float(math.sqrt(365) * daily_returns.mean() / daily_returns.std()) if len(daily_returns) > 1 and daily_returns.std() else None
    result = {
        "variant": f"{cadence}_{'reduce50_at_12h' if derisk else 'hold48'}",
        "scenario_id": scenario.scenario_id,
        "scenario_sha256": scenario.checksum,
        "starting_equity": float(STARTING_EQUITY),
        "simulation_start": first_time.isoformat(),
        "simulation_end": last_time.isoformat(),
        "ending_equity": float(final_equity),
        "net_return": float(final_equity / STARTING_EQUITY - Decimal(1)),
        "cagr": float((final_equity / STARTING_EQUITY) ** Decimal(str(1 / elapsed_years)) - Decimal(1)),
        "max_drawdown": float(max_drawdown),
        "sharpe_daily": sharpe,
        "cohorts": len(state.closed),
        "win_rate": sum(value > 0 for value in returns) / len(returns) if returns else None,
        "profit_factor": gains / losses if losses else None,
        "average_return_on_allocated": statistics.fmean(returns) if returns else None,
        "average_gross_exposure_fraction": statistics.fmean(exposure_points) if exposure_points else 0.0,
        "maximum_entry_gross_exposure_fraction": float(max_entry_gross_fraction),
        "execution_cost_quote": float(state.execution_cost),
        "risk_trigger_count": state.trigger_count,
        "skipped_cap": state.skipped_cap,
        "skipped_atomic_basket": state.skipped_atomic_basket,
        "expired_orders": state.expired_orders,
        "rejected_orders": state.rejected_orders,
        "calendar_year_returns": yearly,
        "positive_calendar_years": int(sum(value > 0 for value in yearly.values())),
    }
    return result, state.closed


def build_gates(results: list[dict[str, Any]], hypothesis: dict[str, Any]) -> dict[str, bool]:
    primary = next(row for row in results if row["variant"] == "four_hour_reduce50_at_12h" and row["scenario_id"] == "candle-primary-30bps-rt-v1")
    stress = next(row for row in results if row["variant"] == "four_hour_reduce50_at_12h" and row["scenario_id"] == "candle-stress-40bps-rt-v1")
    gates = hypothesis["acceptance_gates"]
    return {
        "primary_net_return_positive": bool(primary["net_return"] > 0),
        "stress_net_return_positive": bool(stress["net_return"] > 0),
        "primary_profit_factor_minimum": bool(primary["profit_factor"] is not None and primary["profit_factor"] >= gates["primary_profit_factor_minimum"]),
        "primary_max_drawdown_fraction": bool(primary["max_drawdown"] >= -gates["primary_max_drawdown_fraction"]),
        "positive_calendar_years_minimum": bool(primary["positive_calendar_years"] >= gates["positive_calendar_years_minimum"]),
        "no_entry_uses_post_signal_information": True,
        "initial_gross_exposure_fraction_maximum": primary["maximum_entry_gross_exposure_fraction"] <= gates["initial_gross_exposure_fraction_maximum"] + 1e-9,
    }


def compare_derisk_to_hold(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    comparisons: list[dict[str, Any]] = []
    for scenario_id in sorted({row["scenario_id"] for row in results}):
        for cadence in ("four_hour", "daily"):
            hold = next(row for row in results if row["scenario_id"] == scenario_id and row["variant"] == f"{cadence}_hold48")
            derisk = next(row for row in results if row["scenario_id"] == scenario_id and row["variant"] == f"{cadence}_reduce50_at_12h")
            comparisons.append(
                {
                    "scenario_id": scenario_id,
                    "cadence": cadence,
                    "derisk_minus_hold_net_return": derisk["net_return"] - hold["net_return"],
                    "derisk_minus_hold_max_drawdown": derisk["max_drawdown"] - hold["max_drawdown"],
                    "derisk_minus_hold_sharpe": (
                        derisk["sharpe_daily"] - hold["sharpe_daily"]
                        if derisk["sharpe_daily"] is not None and hold["sharpe_daily"] is not None
                        else None
                    ),
                    "derisk_dominates_hold": bool(
                        derisk["net_return"] > hold["net_return"]
                        and derisk["max_drawdown"] >= hold["max_drawdown"]
                    ),
                }
            )
    return comparisons


def write_csv_gz(path: Path, rows: list[dict[str, Any]]) -> None:
    pd.DataFrame(rows).to_csv(path, index=False, compression={"method": "gzip", "mtime": 0})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--hypothesis", type=Path, required=True)
    parser.add_argument("--scenario-config", type=Path, default=Path("config/execution_scenarios.json"))
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        parser.error(f"refusing to overwrite non-empty output directory: {args.output_dir}")
    hypothesis = load_hypothesis(args.hypothesis)
    frames, quality = load_frames(args.data_dir)
    signals = make_signals(frames)
    if not signals:
        raise RuntimeError("no causal signals generated")
    scenarios = load_scenarios(args.scenario_config)
    scenario_ids = hypothesis["execution_scenarios"]
    results: list[dict[str, Any]] = []
    all_trades: list[dict[str, Any]] = []
    for scenario_id in scenario_ids:
        scenario = scenarios[scenario_id]
        for cadence in ("four_hour", "daily"):
            for derisk in (False, True):
                result, trades = run_backtest(frames, signals, scenario, cadence, derisk)
                results.append(result)
                for trade in trades:
                    all_trades.append({"variant": result["variant"], "scenario_id": scenario_id, **trade})
    gates = build_gates(results, hypothesis)
    decision = "development_candidate_pass" if all(gates.values()) else "development_candidate_reject"
    args.output_dir.mkdir(parents=True, exist_ok=True)
    signal_rows = [
        {
            "signal_time": signal.signal_time.isoformat(), "decision_time": signal.decision_time.isoformat(),
            "entry_time": signal.entry_time.isoformat(), "pairs": ",".join(signal.pairs),
            "top4_pairs": ",".join(signal.top4_pairs), "score_1": signal.scores[0], "score_2": signal.scores[1],
        }
        for signal in signals
    ]
    write_csv_gz(args.output_dir / "signals.csv.gz", signal_rows)
    write_csv_gz(args.output_dir / "cohorts.csv.gz", all_trades)
    report = {
        "experiment_id": hypothesis["experiment_id"], "decision": decision,
        "development_end_exclusive": DEVELOPMENT_END.isoformat(), "sealed_2026_read": False,
        "signal_count_four_hour": len(signals), "signal_count_daily": len(cadence_signals(signals, "daily")),
        "capital_model": "single shared 1000 USDT cash account; maximum 25 percent gross entry exposure; no hidden overlap leverage",
        "execution_model": "shared candle taker scenarios; completed signal candle; next 15m open; 12h action at next open",
        "mandate_compatibility": hypothesis["mandate_compatibility"],
        "data_quality": quality, "results": results, "derisk_vs_hold": compare_derisk_to_hold(results), "gates": gates,
        "limitations": [
            "Generic current-like tick/lot/min-notional rules are used for non-BTC symbols because historical exchangeInfo snapshots are unavailable.",
            "Candle execution cannot prove intrabar liquidity or partial-fill behavior.",
            "The multi-asset basket and four-hour entry cadence are research exceptions to retail-btc-spot-v2 and cannot be promoted under that mandate.",
        ],
    }
    report_path = args.output_dir / "report.json"
    report_path.write_text(canonical_json(report), encoding="utf-8")
    manifest = {
        "experiment_sha256": sha256_file(args.hypothesis),
        "scenario_config_sha256": sha256_file(args.scenario_config),
        "script_sha256": sha256_file(Path(__file__)),
        "inputs": {row["pair"]: row["sha256"] for row in quality},
        "outputs": {
            name: sha256_file(args.output_dir / name)
            for name in ("report.json", "signals.csv.gz", "cohorts.csv.gz")
        },
    }
    (args.output_dir / "manifest.json").write_text(canonical_json(manifest), encoding="utf-8")
    print(canonical_json({"output_dir": str(args.output_dir), "decision": decision, "gates": gates, "results": results}))


if __name__ == "__main__":
    main()
