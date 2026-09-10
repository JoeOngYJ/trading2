#!/usr/bin/env python3
from __future__ import annotations
import csv, hashlib, io, json, zipfile
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
START=1577836800000; END=1704067199999; DAY=86400000
ROOT=Path(__file__).resolve().parents[3]; OUT=ROOT/"artifacts/agent-level-experiment/btc-focused/derivatives-crowding-data-audit-v2"
def get(url):
    with urlopen(Request(url,headers={"User-Agent":"offline-research-audit/2"}),timeout=30) as r:return r.read()
def main():
    if OUT.exists(): raise FileExistsError(OUT)
    OUT.mkdir(parents=True)
    basis=[]; cursor=START; basis_digests=[]
    while cursor<=END:
        url="https://fapi.binance.com/futures/data/basis?"+urlencode({"pair":"BTCUSDT","contractType":"PERPETUAL","period":"1d","startTime":cursor,"endTime":END,"limit":500})
        raw=get(url); rows=json.loads(raw); basis_digests.append(hashlib.sha256(raw).hexdigest())
        if not rows: break
        basis.extend(rows); cursor=int(rows[-1]["timestamp"])+DAY
        if len(rows)<500: break
    cot=[]; cot_sources=[]
    for year in range(2020,2024):
        url=f"https://www.cftc.gov/files/dea/history/fut_fin_txt_{year}.zip"; raw=get(url)
        cot_sources.append({"year":year,"sha256":hashlib.sha256(raw).hexdigest()})
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            text=z.read(z.namelist()[0]).decode("utf-8-sig")
        for row in csv.DictReader(io.StringIO(text)):
            if row["CFTC_Contract_Market_Code"].strip()=="133741": cot.append(row)
    report={"audit_id":"btc-derivatives-crowding-data-audit-v2","basis_rows":len(basis),"basis_first":basis[0]["timestamp"] if basis else None,"basis_last":basis[-1]["timestamp"] if basis else None,"basis_response_sha256s":basis_digests,"cftc_bitcoin_rows":len(cot),"cftc_sources":cot_sources,"decision":"source_gate_passed" if len(basis)>=1400 and len(cot)>=180 else "source_gate_blocked","strategy_evaluation_run":False,"actionable_arm_id":"no_trade"}
    (OUT/"basis.json").write_text(json.dumps(basis,separators=(",",":"))+"\n")
    (OUT/"cftc-bitcoin-tff.json").write_text(json.dumps(cot,separators=(",",":"))+"\n")
    (OUT/"report.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print(json.dumps(report,indent=2,sort_keys=True))
if __name__=="__main__":main()
