"""Reusable, offline-only helpers for causal strategy attribution.

This module contains no database, message-bus, exchange, HTTP, or credential code.  It
operates on already validated archived observations and deterministic experiment inputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from trading_platform.execution_model import ExecutionScenario


@dataclass(frozen=True)
class AttributionSignal:
    """A completed-information decision and its precomputed eligible rankings."""

    signal_time: pd.Timestamp
    decision_time: pd.Timestamp
    entry_time: pd.Timestamp
    ranked_pairs: tuple[str, ...]
    top4_pairs: tuple[str, ...]


def require_child_path(path: Path, parent: Path, label: str) -> Path:
    """Resolve a path and fail unless it remains within a frozen offline boundary."""

    resolved = path.resolve(strict=True)
    boundary = parent.resolve(strict=True)
    try:
        resolved.relative_to(boundary)
    except ValueError as exc:
        raise ValueError(f"{label} escapes frozen boundary {boundary}: {resolved}") from exc
    return resolved


def require_output_path(path: Path, parent: Path) -> Path:
    """Resolve an output target without requiring that the leaf already exists."""

    boundary = parent.resolve(strict=True)
    resolved = path.resolve(strict=False)
    try:
        resolved.relative_to(boundary)
    except ValueError as exc:
        raise ValueError(f"output directory escapes frozen boundary {boundary}: {resolved}") from exc
    return resolved


def reject_symlink_tree(path: Path) -> None:
    """Reject symlinked input components so a frozen path cannot redirect elsewhere."""

    candidate = path.absolute()
    for component in (candidate, *candidate.parents):
        if component.is_symlink():
            raise ValueError(f"symlinked frozen input is not allowed: {component}")


def validate_attribution_signals(
    signals: Sequence[AttributionSignal],
    universe: Sequence[str],
    development_end: pd.Timestamp,
) -> None:
    if not signals:
        raise ValueError("attribution signal ledger is empty")
    allowed = set(universe)
    seen: set[pd.Timestamp] = set()
    for signal in signals:
        times = (signal.signal_time, signal.decision_time, signal.entry_time)
        if any(timestamp.tzinfo is None for timestamp in times):
            raise ValueError("signal timestamps must be timezone aware")
        if signal.signal_time in seen:
            raise ValueError(f"duplicate signal timestamp: {signal.signal_time}")
        seen.add(signal.signal_time)
        if signal.signal_time.minute != 0 or signal.signal_time.hour != 0:
            raise ValueError(f"R0 accepts midnight-UTC signals only: {signal.signal_time}")
        if signal.decision_time != signal.signal_time + pd.Timedelta(minutes=15):
            raise ValueError("decision must follow the completed signal candle by 15 minutes")
        if signal.entry_time < signal.decision_time:
            raise ValueError("entry precedes the causal decision time")
        if signal.entry_time + pd.Timedelta(hours=48) >= development_end:
            raise ValueError("signal exit crosses the frozen development boundary")
        if len(signal.ranked_pairs) != 2 or len(set(signal.ranked_pairs)) != 2:
            raise ValueError("ranked top-two selection must contain two unique pairs")
        if len(signal.top4_pairs) != 4 or len(set(signal.top4_pairs)) != 4:
            raise ValueError("gate-qualified top-four must contain four unique pairs")
        if not set(signal.ranked_pairs).issubset(set(signal.top4_pairs)):
            raise ValueError("ranked top two are not contained in the frozen top four")
        if not set(signal.top4_pairs).issubset(allowed):
            raise ValueError("signal contains a pair outside the frozen universe")


def selected_pairs(
    signal: AttributionSignal,
    control: str,
    universe: Sequence[str],
) -> tuple[str, ...]:
    if control == "ranked_top2":
        return signal.ranked_pairs
    if control == "gate_qualified_top4_equal_weight":
        return signal.top4_pairs
    if control == "eligible_universe7_equal_weight":
        return tuple(universe)
    if control == "btc_only":
        return ("BTC/USDT",)
    if control == "eth_only":
        return ("ETH/USDT",)
    if control == "eligible_remainder_equal_weight":
        selected = set(signal.ranked_pairs)
        return tuple(pair for pair in universe if pair not in selected)
    raise ValueError(f"unknown attribution control: {control}")


def friction_adjusted_return(
    entry_price: float,
    exit_price: float,
    scenario: ExecutionScenario,
) -> float:
    """Net long return for deterministic next-open attribution diagnostics.

    Shared-capital results use the full execution simulator.  This paired diagnostic
    intentionally removes order-protection expiry and allocation effects so every asset is
    compared at the same timestamps using the scenario's fees and implicit costs.
    """

    if not np.isfinite(entry_price) or not np.isfinite(exit_price) or entry_price <= 0 or exit_price <= 0:
        raise ValueError("entry and exit prices must be finite and positive")
    fee = float(scenario.taker_fee_bps) / 10_000.0
    implicit = float(scenario.implicit_cost_bps_per_side) / 10_000.0
    entry_cash = entry_price * (1.0 + implicit) * (1.0 + fee)
    exit_cash = exit_price * (1.0 - implicit) * (1.0 - fee)
    return exit_cash / entry_cash - 1.0


def basket_return(
    event_returns: Mapping[str, float],
    pairs: Sequence[str],
) -> float:
    if not pairs:
        raise ValueError("basket cannot be empty")
    values = np.asarray([event_returns[pair] for pair in pairs], dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("basket contains a non-finite return")
    return float(values.mean())


def random_top2_distribution(
    matrix: np.ndarray,
    simulations: int,
    seed: int,
) -> np.ndarray:
    """Sample two distinct assets per event and return the simulation mean returns."""

    values = np.asarray(matrix, dtype=float)
    if values.ndim != 2 or values.shape[0] == 0 or values.shape[1] < 2:
        raise ValueError("random-selection matrix must have events by at least two assets")
    if not np.isfinite(values).all() or simulations <= 0:
        raise ValueError("random-selection inputs must be finite and simulations positive")
    rng = np.random.default_rng(seed)
    output = np.empty(simulations, dtype=float)
    asset_count = values.shape[1]
    event_index = np.arange(values.shape[0])
    for simulation in range(simulations):
        first = rng.integers(0, asset_count, size=values.shape[0])
        second_raw = rng.integers(0, asset_count - 1, size=values.shape[0])
        second = second_raw + (second_raw >= first)
        output[simulation] = float(
            ((values[event_index, first] + values[event_index, second]) / 2.0).mean()
        )
    return output


def matched_gate_distribution(
    matched_month_returns: Sequence[np.ndarray],
    simulations: int,
    seed: int,
) -> np.ndarray:
    """Draw one non-signal matched date per signal-month and average its return."""

    if not matched_month_returns or simulations <= 0:
        raise ValueError("matched gate pools and positive simulations are required")
    pools = [np.asarray(pool, dtype=float) for pool in matched_month_returns]
    if any(pool.ndim != 1 or len(pool) == 0 or not np.isfinite(pool).all() for pool in pools):
        raise ValueError("every matched gate pool must contain finite returns")
    rng = np.random.default_rng(seed)
    output = np.empty(simulations, dtype=float)
    for simulation in range(simulations):
        output[simulation] = float(np.mean([pool[rng.integers(0, len(pool))] for pool in pools]))
    return output


def one_sided_randomization_p(observed: float, distribution: np.ndarray) -> float:
    values = np.asarray(distribution, dtype=float)
    if values.ndim != 1 or len(values) == 0 or not np.isfinite(values).all():
        raise ValueError("randomization distribution must be a non-empty finite vector")
    return float((1 + np.count_nonzero(values >= observed)) / (len(values) + 1))


def randomization_percentile(observed: float, distribution: np.ndarray) -> float:
    values = np.asarray(distribution, dtype=float)
    if values.ndim != 1 or len(values) == 0 or not np.isfinite(values).all():
        raise ValueError("randomization distribution must be a non-empty finite vector")
    return float(np.count_nonzero(values < observed) / len(values))


def _group_indices(blocks: Sequence[str]) -> list[np.ndarray]:
    if not blocks:
        raise ValueError("bootstrap blocks are empty")
    labels = np.asarray(blocks, dtype=object)
    ordered = list(dict.fromkeys(labels.tolist()))
    return [np.flatnonzero(labels == label) for label in ordered]


def block_bootstrap_mean_interval(
    values: Sequence[float],
    blocks: Sequence[str],
    replications: int,
    seed: int,
    confidence: float,
) -> dict[str, float]:
    observations = np.asarray(values, dtype=float)
    groups = _group_indices(blocks)
    if len(observations) != len(blocks) or not np.isfinite(observations).all():
        raise ValueError("bootstrap observations and blocks must align and be finite")
    if replications <= 0 or not 0 < confidence < 1:
        raise ValueError("invalid bootstrap configuration")
    rng = np.random.default_rng(seed)
    sampled = np.empty(replications, dtype=float)
    for replication in range(replications):
        chosen = rng.integers(0, len(groups), size=len(groups))
        indices = np.concatenate([groups[index] for index in chosen])
        sampled[replication] = float(observations[indices].mean())
    tail = (1.0 - confidence) / 2.0
    return {
        "estimate": float(observations.mean()),
        "lower": float(np.quantile(sampled, tail)),
        "upper": float(np.quantile(sampled, 1.0 - tail)),
        "standard_error": float(sampled.std(ddof=1)),
    }


def ols_alpha_beta(y: Sequence[float], x: Sequence[float]) -> dict[str, float]:
    dependent = np.asarray(y, dtype=float)
    market = np.asarray(x, dtype=float)
    if dependent.ndim != 1 or market.ndim != 1 or len(dependent) != len(market) or len(dependent) < 3:
        raise ValueError("OLS inputs must be aligned vectors with at least three observations")
    if not np.isfinite(dependent).all() or not np.isfinite(market).all():
        raise ValueError("OLS inputs must be finite")
    design = np.column_stack([np.ones(len(market)), market])
    coefficients, _, _, _ = np.linalg.lstsq(design, dependent, rcond=None)
    fitted = design @ coefficients
    residual = dependent - fitted
    total = float(np.sum((dependent - dependent.mean()) ** 2))
    residual_sum = float(np.sum(residual**2))
    return {
        "alpha_per_event": float(coefficients[0]),
        "beta": float(coefficients[1]),
        "r_squared": float(1.0 - residual_sum / total) if total > 0 else 0.0,
        "residual_standard_deviation": float(residual.std(ddof=2)),
        "observations": int(len(dependent)),
    }


def block_bootstrap_ols_alpha_interval(
    y: Sequence[float],
    x: Sequence[float],
    blocks: Sequence[str],
    replications: int,
    seed: int,
    confidence: float,
) -> dict[str, float]:
    dependent = np.asarray(y, dtype=float)
    market = np.asarray(x, dtype=float)
    groups = _group_indices(blocks)
    if len(dependent) != len(market) or len(dependent) != len(blocks):
        raise ValueError("OLS bootstrap inputs must align")
    rng = np.random.default_rng(seed)
    alphas = np.empty(replications, dtype=float)
    for replication in range(replications):
        chosen = rng.integers(0, len(groups), size=len(groups))
        indices = np.concatenate([groups[index] for index in chosen])
        alphas[replication] = ols_alpha_beta(dependent[indices], market[indices])["alpha_per_event"]
    tail = (1.0 - confidence) / 2.0
    return {
        "lower": float(np.quantile(alphas, tail)),
        "upper": float(np.quantile(alphas, 1.0 - tail)),
        "standard_error": float(alphas.std(ddof=1)),
    }


def profitable_period_concentration(
    rows: Iterable[Mapping[str, Any]],
    top_n: int = 3,
) -> dict[str, Any]:
    frame = pd.DataFrame(rows)
    if frame.empty:
        return {"top_n": top_n, "share": None, "profitable_periods": 0, "period_pnl": {}}
    frame["period"] = pd.to_datetime(frame["entry_time"], utc=True).dt.strftime("%Y-%m")
    period = frame.groupby("period", sort=True)["pnl"].sum()
    positive = period[period > 0].sort_values(ascending=False)
    share = float(positive.head(top_n).sum() / positive.sum()) if positive.sum() > 0 else None
    return {
        "top_n": top_n,
        "share": share,
        "profitable_periods": int(len(positive)),
        "period_pnl": {str(key): float(value) for key, value in period.items()},
    }
