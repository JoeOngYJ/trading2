#!/usr/bin/env python3
"""BTC-centered causal feature and BTC/ETH relationship report.

Uses only completed bars. Lag k means the feature is shifted k bars before the
future BTC return target; no future values are used. This is an exploratory
research tool, not a trading signal publisher.
"""
from __future__ import annotations
import argparse, gzip, json
from pathlib import Path
import numpy as np
import pandas as pd

def load(path: Path, prefix: str) -> pd.DataFrame:
    with gzip.open(path, "rt") as fh:
        df = pd.read_csv(fh)
    df["time"] = pd.to_datetime(df.open_time_ms, unit="ms", utc=True)
    df = df.set_index("time").sort_index()
    keep = ["open", "high", "low", "close", "volume", "trades"]
    return df[keep].rename(columns={c: f"{prefix}_{c}" for c in keep})

def corr(a: pd.Series, b: pd.Series) -> float | None:
    x = pd.concat([a, b], axis=1).dropna()
    return None if len(x) < 20 else float(x.iloc[:, 0].corr(x.iloc[:, 1]))

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--btc", type=Path, required=True)
    ap.add_argument("--eth", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    btc, eth = load(args.btc, "btc"), load(args.eth, "eth")
    df = btc.join(eth, how="inner")
    for p in ("btc", "eth"):
        df[f"{p}_ret"] = np.log(df[f"{p}_close"]).diff()
        df[f"{p}_range"] = (df[f"{p}_high"] - df[f"{p}_low"]) / df[f"{p}_close"]
        df[f"{p}_vol20"] = df[f"{p}_ret"].rolling(20).std()
        df[f"{p}_vol_surprise"] = df[f"{p}_volume"] / df[f"{p}_volume"].rolling(20).median() - 1
    df["btc_eth_beta_100"] = df["btc_ret"].rolling(100).cov(df["eth_ret"]) / df["eth_ret"].rolling(100).var()
    df["btc_residual"] = df["btc_ret"] - df["btc_eth_beta_100"] * df["eth_ret"]
    horizons = {"1h": 1, "4h": 4}
    result = {"rows": int(len(df)), "start": str(df.index.min()), "end": str(df.index.max()), "horizons": {}}
    for name, h in horizons.items():
        target = df["btc_ret"].shift(-h)
        out = {"contemporaneous": corr(df["btc_ret"], df["eth_ret"]), "lead_lag": {}}
        for lag in range(1, 13):
            out["lead_lag"][str(lag)] = corr(df["eth_ret"].shift(lag), target)
        out["feature_corr_to_target"] = {
            k: corr(df[k].shift(1), target) for k in ["btc_ret","eth_ret","btc_vol20","eth_vol20","btc_vol_surprise","eth_vol_surprise","btc_residual"]
        }
        result["horizons"][name] = out
    result["rolling_corr"] = {str(w): float(df["btc_ret"].rolling(w).corr(df["eth_ret"]).mean()) for w in (24, 96, 240)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")

if __name__ == "__main__":
    main()
