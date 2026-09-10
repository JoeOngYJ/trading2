#!/usr/bin/env python3
"""Development-only C2 proxy evaluation using immutable v5 GBP ledgers."""
from __future__ import annotations
import json, math
from collections import defaultdict
from pathlib import Path

SYMBOLS = ("BIL", "DBC", "EFA", "GLD", "IEF", "SPY", "TLT")
RISKY = ("DBC", "EFA", "GLD", "IEF", "SPY", "TLT")

def metrics(returns: list[float], trades: list[float], cost: int, periods_per_year: float = 252) -> dict[str, float | int]:
    wealth=1.0; peak=1.0; maxdd=0.0
    for r in returns:
        wealth *= 1+r; peak=max(peak,wealth); maxdd=max(maxdd,1-wealth/peak)
    years=len(returns)/periods_per_year
    cagr=wealth**(1/years)-1 if years else 0.0
    gross=sum(x for x in trades if x>0); loss=-sum(x for x in trades if x<0)
    ordered=sorted(trades)
    month_block_lower=ordered[max(0, int(len(ordered)*0.025)-1)] if ordered else 0.0
    month_block_upper=ordered[min(len(ordered)-1, int(len(ordered)*0.975))] if ordered else 0.0
    return {"net_return": wealth-1, "cagr": cagr, "max_drawdown": maxdd,
            "calmar": cagr/maxdd if maxdd else 0.0, "profit_factor": gross/loss if loss else math.inf,
            "trade_count":len(trades), "cost_bps_round_trip":cost,
            "month_block_trade_pnl_lower_2_5pct":month_block_lower,
            "month_block_trade_pnl_upper_97_5pct":month_block_upper,
            "turnover_events_per_year":len(trades)/max(years,1e-9)}

def main() -> None:
    root=Path(__file__).resolve().parents[1]
    base=root/"artifacts/agent-level-experiment/cash-etf/c1-pragmatic-action-ledger-v5/ledgers"
    data={}
    for s in SYMBOLS:
        rows=[json.loads(x) for x in (base/f"{s.lower()}-total-return.jsonl").read_text().splitlines()]
        if rows[0].get("open") is None or rows[0].get("gbp_open_equivalent") is None: raise ValueError("missing open fields")
        data[s]=rows
    sessions=[r["session"] for r in data["SPY"]]; idx={d:i for i,d in enumerate(sessions)}
    by_month=defaultdict(list)
    for d in sessions: by_month[d[:7]].append(d)
    months=sorted(by_month)
    results={}
    for cost in (10,25,50):
        friction=cost/10000
        # Slow trend: monthly rebalance, equal six slots, next session open; mark daily closes.
        active={}; entry_prices={}; rets=[]; trades=[]; yearly=defaultdict(float)
        for i,d in enumerate(sessions):
            if i and d[:7]!=sessions[i-1][:7]:
                for s in RISKY:
                    j=i-252
                    if j>=0:
                        a=float(data[s][i-1]["gbp_close_equivalent"]); b=float(data[s][j]["gbp_close_equivalent"])
                        want=a>b
                        if want != (s in active):
                            if s in active:
                                trades.append(float(data[s][i-1]["gbp_close_equivalent"])/entry_prices[s]-1-friction)
                            else:
                                entry_prices[s]=float(data[s][i]["gbp_open_equivalent"])*(1+friction)
                        if want: active[s]=True
                        else: active.pop(s,None); entry_prices.pop(s,None)
            if i:
                r=sum(float(data[s][i]["total_return"] or 0) for s in active)/6 if active else 0.0
                if i and d[:7]!=sessions[i-1][:7]: r -= friction * len(active) / 6
                rets.append(r)
                yearly[d[:4]] += r
        results.setdefault("cash-etf-slow-trend-proxy-v1",{})[str(cost)]=metrics(rets,trades,cost)
        results["cash-etf-slow-trend-proxy-v1"][str(cost)]["calendar_year_returns"]=dict(yearly)
        vals=list(yearly.values()); positive=sum(v>0 for v in vals)
        results["cash-etf-slow-trend-proxy-v1"][str(cost)]["positive_calendar_year_fraction"]=positive/len(vals)
        top_three=sum(sorted((v for v in vals if v>0), reverse=True)[:3])
        total_positive=sum(v for v in vals if v>0)
        results["cash-etf-slow-trend-proxy-v1"][str(cost)]["best_three_year_positive_return_fraction"]=(top_three/total_positive if total_positive else 0.0)
        # Turn of month: final session close signal, next month first open to fourth session open.
        rets=[]; trades=[]
        for m in months[:-1]:
            last=idx[by_month[m][-1]]; nxt=months[months.index(m)+1]; target=by_month[nxt][min(3,len(by_month[nxt])-1)]
            entry=idx[by_month[nxt][0]]; exit_i=idx[target]
            if exit_i<=entry: continue
            trade=sum(float(data[s][exit_i]["gbp_open_equivalent"])/float(data[s][entry]["gbp_open_equivalent"])-1 for s in ("EFA","SPY"))/2-friction
            trades.append(trade); rets.append(trade)
        results.setdefault("cash-etf-turn-of-month-proxy-v1",{})[str(cost)]=metrics(rets,trades,cost,12)
        # Quarterly defensive rotation: rank prior 126 completed sessions, enter next quarter open.
        active=[]; entry={}; rets=[]; trades=[]; yearly=defaultdict(float); prev_quarter=None
        for i,d in enumerate(sessions):
            q=d[:4]+str((int(d[5:7])-1)//3)
            if i and q!=prev_quarter:
                scores=[]
                for s in RISKY:
                    if i>=126:
                        scores.append((float(data[s][i-1]["gbp_close_equivalent"])/float(data[s][i-127]["gbp_close_equivalent"])-1,s))
                chosen=[s for score,s in sorted(scores,reverse=True)[:2] if score>0]
                if set(chosen)!=set(active):
                    for s in active:
                        trades.append(float(data[s][i-1]["gbp_close_equivalent"])/entry[s]-1-friction/2)
                    for s in chosen: entry[s]=float(data[s][i]["gbp_open_equivalent"])
                    trades.append(-friction*max(len(chosen),len(active))/2)
                active=chosen
            if i:
                r=sum(float(data[s][i]["total_return"] or 0) for s in active)/2 if active else 0.0
                if i and q!=prev_quarter: r -= friction*max(len(active),1)/2
                rets.append(r); yearly[d[:4]]+=r
            prev_quarter=q
        results.setdefault("cash-etf-quarterly-defensive-rotation-v1",{})[str(cost)]=metrics(rets,trades,cost)
        results["cash-etf-quarterly-defensive-rotation-v1"][str(cost)]["calendar_year_returns"]=dict(yearly)
    controls={"zero_yield_gbp_cash":{"net_return":0.0},"flat_control":{"net_return":0.0},"per_asset_buy_and_hold":{}}
    for s in RISKY:
        wealth=float(data[s][-1]["wealth_index"])
        controls["per_asset_buy_and_hold"][s]={"net_return":wealth-1.0}
    report={"schema_version":"cash-etf-c2-proxy-evaluation-report-v1","experiment_id":"cash-etf-quarterly-defensive-rotation-v1","decision":"development_diagnostics_provisional","development_boundary":{"start":"2009-01-02","end":"2018-12-31"},"metrics":results,"controls":controls,"accepted_strategy_arms":[],"actionable_arm_id":"no_trade","approved_execution_instruments":[],"sealed_partitions_accessed":False,"promotion_or_execution_authorized":False}
    report["diagnostic_scope"]=["calendar_year_returns","concentration","month_block_trade_pnl_interval","turnover"]
    report["supersedes_invalid_preliminary_artifact"]="artifacts/agent-level-experiment/cash-etf/c2-proxy-evaluation-v7/report.json"
    out=root/"artifacts/agent-level-experiment/cash-etf/c2-proxy-evaluation-v8/report.json"; out.parent.mkdir(parents=True,exist_ok=True)
    if out.exists(): raise FileExistsError(out)
    out.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print(json.dumps(report,indent=2,sort_keys=True))
if __name__=="__main__": main()
