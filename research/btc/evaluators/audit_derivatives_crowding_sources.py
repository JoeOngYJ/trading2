#!/usr/bin/env python3
"""Public, data-only availability audit for the frozen BTC derivatives contract."""
from __future__ import annotations
import hashlib, json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

START=1577836800000; END=1704067199999
ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/"artifacts/agent-level-experiment/btc-focused/derivatives-crowding-data-audit-v1"

def get(url: str) -> bytes:
    req=Request(url,headers={"User-Agent":"offline-research-audit/1"})
    with urlopen(req,timeout=30) as r: return r.read(10_000_001)

def main() -> None:
    if OUT.exists(): raise FileExistsError(OUT)
    OUT.mkdir(parents=True)
    funding=[]; cursor=START; responses=[]
    while cursor<=END:
        url="https://fapi.binance.com/fapi/v1/fundingRate?"+urlencode({"symbol":"BTCUSDT","startTime":cursor,"endTime":END,"limit":1000})
        raw=get(url); rows=json.loads(raw); responses.append(hashlib.sha256(raw).hexdigest())
        if not rows: break
        funding.extend(rows); cursor=int(rows[-1]["fundingTime"])+1
        if len(rows)<1000: break
    checks={}
    for name,url in {
        "open_interest":"https://fapi.binance.com/futures/data/openInterestHist?"+urlencode({"symbol":"BTCUSDT","period":"1d","startTime":START,"endTime":END,"limit":500}),
        "basis":"https://fapi.binance.com/futures/data/basis?"+urlencode({"pair":"BTCUSDT","contractType":"PERPETUAL","period":"1d","startTime":START,"endTime":END,"limit":500}),
    }.items():
        try:
            raw=get(url); payload=json.loads(raw)
            checks[name]={"response_sha256":hashlib.sha256(raw).hexdigest(),"row_count":len(payload) if isinstance(payload,list) else 0,"response_type":type(payload).__name__}
        except Exception as exc:
            checks[name]={"error_type":type(exc).__name__,"row_count":0}
    report={"audit_id":"btc-derivatives-crowding-data-audit-v1","funding":{"row_count":len(funding),"first_time":funding[0]["fundingTime"] if funding else None,"last_time":funding[-1]["fundingTime"] if funding else None,"response_sha256s":responses},"historical_checks":checks,"strategy_evaluation_run":False,"prices_or_forward_labels_read":False,"actionable_arm_id":"no_trade","decision":"source_gate_passed" if funding and any(v.get("row_count",0)>0 for v in checks.values()) else "source_gate_blocked"}
    (OUT/"report.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    (OUT/"funding.json").write_text(json.dumps(funding,separators=(",",":"))+"\n")
    print(json.dumps(report,indent=2,sort_keys=True))
if __name__=="__main__": main()
