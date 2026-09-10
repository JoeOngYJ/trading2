#!/usr/bin/env python3
"""Cost-aware BTC breakout comparison with optional lagging confirmation."""
from __future__ import annotations
import argparse, gzip, json
from pathlib import Path
import numpy as np
import pandas as pd

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--window", type=int, default=20)
    ap.add_argument("--fee-bps", type=float, default=10)
    ap.add_argument("--slippage-bps", type=float, default=2)
    ap.add_argument("--confirmation", choices=("none","ema","adx"), default="none")
    args = ap.parse_args()
    with gzip.open(args.data, "rt") as fh: df = pd.read_csv(fh)
    c, o, h, l = [df[x].astype(float) for x in ("close","open","high","low")]
    prior_high = h.shift(1).rolling(args.window).max()
    tr = pd.concat([h-l, (h-c.shift(1)).abs(), (l-c.shift(1)).abs()], axis=1).max(axis=1)
    vol = tr.shift(1).rolling(20).mean()
    ema20 = c.shift(1).ewm(span=20, adjust=False).mean()
    if args.confirmation == "ema": confirm = c.shift(1) > ema20
    elif args.confirmation == "adx":
        up, down = h.diff(), -l.diff(); plus = up.where((up > down) & (up > 0), 0).rolling(14).mean(); minus = down.where((down > up) & (down > 0), 0).rolling(14).mean(); confirm = ((plus-minus).abs()/(plus+minus).replace(0,np.nan)).rolling(14).mean() > .2
    else: confirm = pd.Series(True, index=df.index)
    # Signal is formed on the completed current bar; position is applied next bar.
    entry = (c > prior_high) & confirm
    prior_low = l.shift(1).rolling(args.window).min()
    pos = pd.Series(0, index=df.index, dtype=int)
    in_trade = False
    for i in range(len(df) - 1):
        # Signals are evaluated on the closed bar and applied to the next bar.
        if not in_trade and bool(entry.iloc[i]):
            in_trade = True
        elif in_trade and bool(c.iloc[i] < prior_low.iloc[i]):
            in_trade = False
        pos.iloc[i + 1] = int(in_trade)
    ret = c.pct_change().fillna(0) * pos.shift(1).fillna(0)
    turnover = pos.diff().abs().fillna(0)
    cost = turnover * (args.fee_bps + args.slippage_bps) / 10000
    net = ret - cost
    equity = (1 + net).cumprod(); dd = equity / equity.cummax() - 1
    wins, losses = net[net > 0].sum(), -net[net < 0].sum()
    out = {"window": args.window, "confirmation": args.confirmation, "fee_bps": args.fee_bps, "slippage_bps": args.slippage_bps, "rows": len(df), "trades": int(turnover.sum()), "net_return": float(equity.iloc[-1]-1), "max_drawdown": float(dd.min()), "profit_factor": float(wins/losses) if losses else None, "turnover": float(turnover.sum()), "cost_paid": float(cost.sum())}
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(out, indent=2)+"\n")

if __name__ == "__main__": main()
