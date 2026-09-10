#!/usr/bin/env python3
"""Develop one predeclared BTC taker-flow exhaustion/reversal hypothesis."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import random
import statistics
from collections import defaultdict, deque
from pathlib import Path

DAY_BARS = 288
HORIZON = 12
DISCOVERY_END_MS = 1_672_531_200_000  # 2023-01-01


def quantile(values: list[float], probability: float) -> float:
    ordered=sorted(values); position=(len(ordered)-1)*probability; lo=math.floor(position); hi=math.ceil(position)
    return ordered[lo] if lo==hi else ordered[lo]*(hi-position)+ordered[hi]*(position-lo)


def bootstrap_days(events: list[tuple[int,float]], seed: int=20260825, replicates: int=4000) -> list[float]:
    grouped=defaultdict(list)
    for timestamp,value in events: grouped[timestamp//86_400_000].append(value)
    days=list(grouped.values()); rng=random.Random(seed); estimates=[]
    for _ in range(replicates):
        sample=[days[rng.randrange(len(days))] for _ in days]; flat=[value for day in sample for value in day]
        estimates.append(statistics.fmean(flat))
    return estimates


def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("--data",type=Path,required=True); parser.add_argument("--manifest",type=Path,required=True); parser.add_argument("--holdout-manifest",type=Path,required=True); parser.add_argument("--output",type=Path,required=True); parser.add_argument("--hypothesis-output",type=Path,required=True)
    args=parser.parse_args(); manifest=json.loads(args.manifest.read_text()); holdout=json.loads(args.holdout_manifest.read_text()); digest=hashlib.sha256(args.data.read_bytes()).hexdigest()
    if manifest.get("partition")!="development-2017-2025" or manifest.get("dataset_sha256")!=digest: parser.error("accepted development dataset required")
    if not str(holdout.get("partition","")).startswith("holdout") or not holdout.get("accepted"): parser.error("accepted sealed holdout manifest required")
    rows=[]
    with gzip.open(args.data,"rt",newline="",encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            rows.append({"segment":int(row["segment_id"]),"time":int(row["open_time_ms"]),"open":float(row["open"]),"high":float(row["high"]),"low":float(row["low"]),"close":float(row["close"]),"quote":float(row["quote_volume"]),"imbalance":float(row["base_trade_flow_imbalance"]) if row["base_trade_flow_imbalance"] else None})
    quote_window=deque(); range_window=deque(); quote_sum=range_sum=0.0; previous_segment=None; features=[]
    for row in rows:
        if row["segment"]!=previous_segment:
            quote_window.clear(); range_window.clear(); quote_sum=range_sum=0.0; previous_segment=row["segment"]
        range_fraction=(row["high"]-row["low"])/row["open"]
        volume_shock=row["quote"]/(quote_sum/DAY_BARS) if len(quote_window)==DAY_BARS and quote_sum>0 else None
        range_shock=range_fraction/(range_sum/DAY_BARS) if len(range_window)==DAY_BARS and range_sum>0 else None
        features.append((volume_shock,range_shock,math.log(row["close"]/row["open"])))
        quote_window.append(row["quote"]); range_window.append(range_fraction); quote_sum+=row["quote"]; range_sum+=range_fraction
        if len(quote_window)>DAY_BARS: quote_sum-=quote_window.popleft(); range_sum-=range_window.popleft()
    discovery=[i for i,row in enumerate(rows) if row["time"]<DISCOVERY_END_MS and features[i][0] is not None and row["imbalance"] is not None]
    imbalance_threshold=quantile([rows[i]["imbalance"] for i in discovery],.95)
    volume_threshold=quantile([features[i][0] for i in discovery],.90)
    range_threshold=quantile([features[i][1] for i in discovery],.90)
    events=[]
    for i,row in enumerate(rows):
        volume_shock,range_shock,bar_return=features[i]
        if row["time"]<DISCOVERY_END_MS or volume_shock is None or row["imbalance"] is None or i+HORIZON>=len(rows): continue
        if rows[i+HORIZON]["segment"]!=row["segment"]: continue
        if row["imbalance"]>=imbalance_threshold and volume_shock>=volume_threshold and range_shock>=range_threshold and bar_return>0:
            events.append((row["time"],math.log(rows[i+HORIZON]["close"]/row["close"])))
    annual={}
    for year in (2023,2024,2025):
        start=int(__import__('datetime').datetime(year,1,1,tzinfo=__import__('datetime').timezone.utc).timestamp()*1000); end=int(__import__('datetime').datetime(year+1,1,1,tzinfo=__import__('datetime').timezone.utc).timestamp()*1000)
        values=[value for timestamp,value in events if start<=timestamp<end]
        annual[str(year)]={"events":len(values),"mean_forward_log_return":statistics.fmean(values) if values else None,"median_forward_log_return":statistics.median(values) if values else None,"reversal_hit_rate":sum(v<0 for v in values)/len(values) if values else None}
    estimates=bootstrap_days(events); estimates.sort(); pooled=statistics.fmean(value for _,value in events)
    ci=[quantile(estimates,.025),quantile(estimates,.975)]
    gates={"at_least_100_events_each_year":all(annual[str(y)]["events"]>=100 for y in (2023,2024,2025)),"negative_mean_each_year":all(annual[str(y)]["mean_forward_log_return"]<0 for y in (2023,2024,2025)),"pooled_ci_upper_below_zero":ci[1]<0,"mean_reversal_at_least_12bps":pooled<=-0.0012}
    accepted=all(gates.values())
    report={"study":"btc-positive-taker-exhaustion-v1","development_dataset_sha256":digest,"discovery_period":"2017-08 through 2022-12","evaluation_period":"2023-01 through 2025-12","event":{"imbalance":"base imbalance >= discovery q95","volume":"quote volume / prior-288-bar mean >= discovery q90","range":"(high-low)/open / prior-288-bar mean >= discovery q90","bar_direction":"close > open","horizon_bars":HORIZON},"thresholds":{"imbalance_q95":imbalance_threshold,"volume_shock_q90":volume_threshold,"range_shock_q90":range_threshold},"annual":annual,"pooled":{"events":len(events),"mean_forward_log_return":pooled,"bootstrap_ci95":ci},"gates":gates,"accepted_for_holdout":accepted}
    args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    hypothesis={"status":"frozen" if accepted else "rejected","pattern_id":"btc-positive-taker-exhaustion-v1","holdout_dataset_sha256":holdout["dataset_sha256"],"development_report_sha256":hashlib.sha256(args.output.read_bytes()).hexdigest(),"definition":report["event"],"thresholds":report["thresholds"],"success_criteria":gates,"holdout_permitted":accepted}
    args.hypothesis_output.write_text(json.dumps(hypothesis,indent=2,sort_keys=True)+"\n"); print(json.dumps(report,indent=2,sort_keys=True))


if __name__=="__main__": main()
