"""Causal BTC/ETH relative-return features for offline research."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np
import pandas as pd


BAR_15M = pd.Timedelta(minutes=15)
BAR_4H = pd.Timedelta(hours=4)


@dataclass(frozen=True)
class RelativeSignal:
    variant: str
    bar_start: pd.Timestamp
    decision_time: pd.Timestamp
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    btc_return_4h: float
    eth_return_4h: float
    btc_return_24h: float
    eth_return_24h: float
    alpha: float
    beta: float
    residual: float
    residual_threshold: float


def complete_four_hour_bars(frame: pd.DataFrame) -> pd.DataFrame:
    """Aggregate only UTC 4h bars containing all sixteen consecutive 15m rows."""

    required = {"date", "open", "high", "low", "close", "volume"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"15-minute frame missing columns: {missing}")
    work = frame[list(required)].copy().sort_values("date")
    work["date"] = pd.to_datetime(work["date"], utc=True)
    work["source_segment"] = work["date"].diff().ne(BAR_15M).cumsum()
    work["bar_start"] = work["date"].dt.floor("4h")
    rows: list[dict[str, object]] = []
    for (_, bar_start), group in work.groupby(["source_segment", "bar_start"], sort=True):
        ordered = group.sort_values("date")
        expected_end = bar_start + BAR_4H - BAR_15M
        if (
            len(ordered) != 16
            or ordered["date"].iloc[0] != bar_start
            or ordered["date"].iloc[-1] != expected_end
            or not ordered["date"].diff().dropna().eq(BAR_15M).all()
        ):
            continue
        rows.append(
            {
                "bar_start": bar_start,
                "open": float(ordered["open"].iloc[0]),
                "high": float(ordered["high"].max()),
                "low": float(ordered["low"].min()),
                "close": float(ordered["close"].iloc[-1]),
                "volume": float(ordered["volume"].sum()),
            }
        )
    result = pd.DataFrame(rows)
    if result.empty:
        raise ValueError("no complete four-hour bars")
    result = result.sort_values("bar_start").reset_index(drop=True)
    result["segment"] = result["bar_start"].diff().ne(BAR_4H).cumsum()
    return result


def _segment_features(group: pd.DataFrame, window: int, quantile: float) -> pd.DataFrame:
    out = group.copy()
    out["btc_return_4h"] = np.log(out["btc_close"]).diff()
    out["eth_return_4h"] = np.log(out["eth_close"]).diff()
    prior_btc = out["btc_return_4h"].shift(1)
    prior_eth = out["eth_return_4h"].shift(1)
    mean_btc = prior_btc.rolling(window, min_periods=window).mean()
    mean_eth = prior_eth.rolling(window, min_periods=window).mean()
    covariance = prior_btc.rolling(window, min_periods=window).cov(prior_eth)
    variance = prior_eth.rolling(window, min_periods=window).var()
    out["beta"] = covariance / variance.replace(0.0, np.nan)
    out["alpha"] = mean_btc - out["beta"] * mean_eth
    out["residual"] = out["btc_return_4h"] - (
        out["alpha"] + out["beta"] * out["eth_return_4h"]
    )
    out["residual_threshold"] = (
        out["residual"].shift(1).rolling(window, min_periods=window).quantile(quantile)
    )
    out["btc_return_threshold"] = (
        out["btc_return_4h"].shift(1).rolling(window, min_periods=window).quantile(quantile)
    )
    out["btc_return_24h"] = out["btc_close"].pct_change(6)
    out["eth_return_24h"] = out["eth_close"].pct_change(6)
    out["joint_return_24h"] = (out["btc_return_24h"] + out["eth_return_24h"]) / 2.0
    return out


def relative_feature_frame(
    btc: pd.DataFrame,
    eth: pd.DataFrame,
    window: int,
    quantile: float,
) -> pd.DataFrame:
    if window < 20 or not 0 < quantile < 0.5:
        raise ValueError("invalid rolling relative-model configuration")
    btc4 = complete_four_hour_bars(btc).rename(
        columns={column: f"btc_{column}" for column in ("open", "high", "low", "close", "volume")}
    )
    eth4 = complete_four_hour_bars(eth).rename(
        columns={column: f"eth_{column}" for column in ("open", "high", "low", "close", "volume")}
    )
    merged = btc4.drop(columns="segment").merge(
        eth4.drop(columns="segment"), on="bar_start", how="inner", validate="one_to_one"
    )
    merged = merged.sort_values("bar_start").reset_index(drop=True)
    merged["segment"] = merged["bar_start"].diff().ne(BAR_4H).cumsum()
    featured = (
        merged.groupby("segment", group_keys=False)
        .apply(lambda group: _segment_features(group, window, quantile), include_groups=False)
        .reset_index(drop=True)
    )
    return featured.sort_values("bar_start").reset_index(drop=True)


def make_relative_signals(
    features: pd.DataFrame,
    variant: str,
    holding_hours: int,
    development_start: pd.Timestamp,
    development_end: pd.Timestamp,
) -> list[RelativeSignal]:
    if holding_hours <= 0:
        raise ValueError("holding period must be positive")
    required = {
        "bar_start",
        "btc_return_4h",
        "eth_return_4h",
        "btc_return_24h",
        "eth_return_24h",
        "joint_return_24h",
        "alpha",
        "beta",
        "residual",
        "residual_threshold",
    }
    if required - set(features.columns):
        raise ValueError("relative feature frame is incomplete")
    valid = features[list(required - {"bar_start"})].notna().all(axis=1)
    selected = features[
        valid
        & features["eth_return_4h"].gt(0)
        & features["joint_return_24h"].gt(0)
        & features["residual"].le(features["residual_threshold"])
    ]
    signals: list[RelativeSignal] = []
    for row in selected.itertuples(index=False):
        decision = row.bar_start + BAR_4H
        exit_time = decision + pd.Timedelta(hours=holding_hours)
        if decision < development_start or exit_time >= development_end:
            continue
        signals.append(
            RelativeSignal(
                variant=variant,
                bar_start=row.bar_start,
                decision_time=decision,
                entry_time=decision,
                exit_time=exit_time,
                btc_return_4h=float(row.btc_return_4h),
                eth_return_4h=float(row.eth_return_4h),
                btc_return_24h=float(row.btc_return_24h),
                eth_return_24h=float(row.eth_return_24h),
                alpha=float(row.alpha),
                beta=float(row.beta),
                residual=float(row.residual),
                residual_threshold=float(row.residual_threshold),
            )
        )
    return signals


def make_btc_self_reversal_signals(
    features: pd.DataFrame,
    holding_hours: int,
    development_start: pd.Timestamp,
    development_end: pd.Timestamp,
) -> list[RelativeSignal]:
    valid = features[
        [
            "btc_return_4h",
            "eth_return_4h",
            "btc_return_24h",
            "eth_return_24h",
            "alpha",
            "beta",
            "residual",
            "residual_threshold",
            "btc_return_threshold",
        ]
    ].notna().all(axis=1)
    selected = features[
        valid
        & features["btc_return_24h"].gt(0)
        & features["btc_return_4h"].le(features["btc_return_threshold"])
    ]
    output: list[RelativeSignal] = []
    for row in selected.itertuples(index=False):
        decision = row.bar_start + BAR_4H
        exit_time = decision + pd.Timedelta(hours=holding_hours)
        if decision < development_start or exit_time >= development_end:
            continue
        output.append(
            RelativeSignal(
                variant="btc_self_reversal",
                bar_start=row.bar_start,
                decision_time=decision,
                entry_time=decision,
                exit_time=exit_time,
                btc_return_4h=float(row.btc_return_4h),
                eth_return_4h=float(row.eth_return_4h),
                btc_return_24h=float(row.btc_return_24h),
                eth_return_24h=float(row.eth_return_24h),
                alpha=float(row.alpha),
                beta=float(row.beta),
                residual=float(row.residual),
                residual_threshold=float(row.residual_threshold),
            )
        )
    return output


def make_joint_risk_on_signals(
    features: pd.DataFrame,
    holding_hours: int,
    development_start: pd.Timestamp,
    development_end: pd.Timestamp,
) -> list[RelativeSignal]:
    valid = features[
        [
            "btc_return_4h",
            "eth_return_4h",
            "btc_return_24h",
            "eth_return_24h",
            "joint_return_24h",
            "alpha",
            "beta",
            "residual",
            "residual_threshold",
        ]
    ].notna().all(axis=1)
    selected = features[valid & features["joint_return_24h"].gt(0)]
    output: list[RelativeSignal] = []
    for row in selected.itertuples(index=False):
        decision = row.bar_start + BAR_4H
        exit_time = decision + pd.Timedelta(hours=holding_hours)
        if decision < development_start or exit_time >= development_end:
            continue
        output.append(
            RelativeSignal(
                variant="joint_risk_on_every_24h",
                bar_start=row.bar_start,
                decision_time=decision,
                entry_time=decision,
                exit_time=exit_time,
                btc_return_4h=float(row.btc_return_4h),
                eth_return_4h=float(row.eth_return_4h),
                btc_return_24h=float(row.btc_return_24h),
                eth_return_24h=float(row.eth_return_24h),
                alpha=float(row.alpha),
                beta=float(row.beta),
                residual=float(row.residual),
                residual_threshold=float(row.residual_threshold),
            )
        )
    return output
