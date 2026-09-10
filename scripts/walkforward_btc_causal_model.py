#!/usr/bin/env python3
"""Walk-forward ridge model for causal BTC return features.

Features are shifted one completed bar before the forward target. This intentionally
does not use MA/RSI/MACD/ADX. It is a research diagnostic, not an order publisher.
"""
from __future__ import annotations
import argparse, gzip, json
from pathlib import Path
import numpy as np
import pandas as pd

def load(path: Path, prefix: str) -> pd.DataFrame:
    with gzip.open(path, "rt") as fh: d = pd.read_csv(fh)
    d["time"] = pd.to_datetime(d.open_time_ms, unit="ms", utc=True)
    d = d.set_index("time").sort_index()
    keep=("open","high","low","close","volume")
    return d[list(keep)].rename(columns={c:f"{prefix}_{c}" for c in keep})

def ridge_fit(x: np.ndarray, y: np.ndarray, alpha: float) -> np.ndarray:
    mu, sd = x.mean(0), x.std(0); sd[sd == 0] = 1
    z = (x-mu)/sd
    return np.linalg.solve(z.T@z + alpha*np.eye(z.shape[1]), z.T@y), mu, sd

def main() -> None:
    ap=argparse.ArgumentParser(); ap.add_argument("--btc",type=Path,required=True); ap.add_argument("--eth",type=Path,required=True); ap.add_argument("--horizon",type=int,choices=(1,4),default=1); ap.add_argument("--output",type=Path,required=True); ap.add_argument("--train-bars",type=int,default=3000); ap.add_argument("--cost-bps",type=float,default=24)
    a=ap.parse_args(); d=load(a.btc,"btc").join(load(a.eth,"eth"),how="inner")
    for p in ("btc","eth"):
        d[f"{p}_ret"] = np.log(d[f"{p}_close"]).diff()
        d[f"{p}_range"] = (d[f"{p}_high"]-d[f"{p}_low"])/d[f"{p}_close"]
        d[f"{p}_vol"] = d[f"{p}_ret"].rolling(24).std()
        d[f"{p}_volume_surprise"] = d[f"{p}_volume"]/d[f"{p}_volume"].rolling(24).median()-1
    cols=["btc_ret","eth_ret","btc_range","eth_range","btc_vol","eth_vol","btc_volume_surprise","eth_volume_surprise"]
    x=d[cols].shift(1); y=d["btc_ret"].shift(-a.horizon); valid=x.notna().all(1)&y.notna(); x=x[valid].to_numpy(); y=y[valid].to_numpy()
    preds=np.full(len(y),np.nan); start=max(a.train_bars, 100)
    for i in range(start,len(y)):
        coef,mu,sd=ridge_fit(x[i-a.train_bars:i],y[i-a.train_bars:i],1.0); preds[i]=((x[i]-mu)/sd)@coef
    ok=~np.isnan(preds); p,t=preds[ok],y[ok]; threshold=a.cost_bps/10000
    traded=np.abs(p)>threshold; strat=np.where(traded,np.sign(p)*t,0.0)-np.where(traded,1,0)*threshold
    result={"horizon_bars":a.horizon,"features":cols,"train_bars":a.train_bars,"cost_bps_round_trip":a.cost_bps,"observations":int(len(t)),"traded_observations":int(traded.sum()),"prediction_corr":float(np.corrcoef(p,t)[0,1]) if len(t)>1 else None,"directional_accuracy":float((np.sign(p)==np.sign(t)).mean()),"cost_threshold_accuracy":float((np.sign(p[traded])==np.sign(t[traded])).mean()) if traded.any() else None,"mean_target":float(t.mean()),"mean_strategy_return":float(strat.mean()),"cumulative_strategy_return":float((1+strat).prod()-1),"baseline_buy_hold_return":float((1+t).prod()-1)}
    a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(result,indent=2)+"\n"); print(json.dumps(result,indent=2))

if __name__ == "__main__": main()
