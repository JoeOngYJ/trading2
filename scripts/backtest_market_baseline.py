#!/usr/bin/env python3
"""Small, deterministic long-only market baseline for verified Binance candles."""
from __future__ import annotations
import argparse, csv, gzip, json, math
from pathlib import Path

def load(path: Path):
    with gzip.open(path, "rt", newline="") as f:
        return list(csv.DictReader(f))

def run(rows, fast, slow, fee_bps=10.0, slippage_bps=2.0):
    closes=[float(r["close"]) for r in rows]; opens=[float(r["open"]) for r in rows]
    equity=1.0; peak=1.0; max_dd=0.0; position=False; entry=None; trades=[]
    for i in range(slow, len(rows)-1):
        fast_now=sum(closes[i-fast+1:i+1])/fast
        slow_now=sum(closes[i-slow+1:i+1])/slow
        fast_prev=sum(closes[i-fast:i])/fast
        slow_prev=sum(closes[i-slow:i])/slow
        signal = fast_prev <= slow_prev and fast_now > slow_now
        exit_signal = fast_prev >= slow_prev and fast_now < slow_now
        fill=opens[i+1]
        cost=(fee_bps+slippage_bps)/10000
        if position and exit_signal:
            net=fill*(1-cost)/entry-1
            equity*=1+net; trades.append(net); position=False; entry=None
        elif not position and signal:
            entry=fill*(1+cost); position=True
        peak=max(peak,equity); max_dd=min(max_dd,equity/peak-1)
    if position:
        fill=float(rows[-1]["close"]); net=fill*(1-cost)/entry-1
        equity*=1+net; trades.append(net)
    gains=sum(x for x in trades if x>0); losses=-sum(x for x in trades if x<0)
    return {"fast":fast,"slow":slow,"trades":len(trades),"return":equity-1,
            "max_drawdown":max_dd,"win_rate":sum(x>0 for x in trades)/len(trades) if trades else 0,
            "profit_factor":gains/losses if losses else math.inf}

def main():
    p=argparse.ArgumentParser(); p.add_argument("--data",type=Path,required=True)
    p.add_argument("--symbol",required=True); p.add_argument("--timeframe",required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--fee-bps",type=float,default=10.0)
    p.add_argument("--slippage-bps",type=float,default=2.0)
    a=p.parse_args(); rows=load(a.data)
    results=[run(rows,f,s,a.fee_bps,a.slippage_bps) for f,s in ((10,30),(20,50),(30,100))]
    report={"symbol":a.symbol,"timeframe":a.timeframe,"execution":"next_open",
            "fees_bps_per_side":a.fee_bps,"slippage_bps_per_side":a.slippage_bps,
            "rows":len(rows),"results":results}
    a.output.write_text(json.dumps(report,indent=2)+"\n"); print(json.dumps(report,indent=2))
if __name__=="__main__": main()
