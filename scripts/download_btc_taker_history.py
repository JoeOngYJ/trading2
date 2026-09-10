#!/usr/bin/env python3
"""Download and inventory official Binance BTCUSDT monthly 5m klines."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import tarfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

BASE = "https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/5m"
ALLOWED_HOST = "data.binance.vision"


def months(start: str, end: str) -> list[str]:
    sy, sm = map(int, start.split("-")); ey, em = map(int, end.split("-"))
    result = []
    while (sy, sm) <= (ey, em):
        result.append(f"{sy:04d}-{sm:02d}")
        sm += 1
        if sm == 13: sy, sm = sy + 1, 1
    return result


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch(url: str, retries: int = 4) -> bytes:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != ALLOWED_HOST or not parsed.path.startswith("/data/spot/monthly/klines/BTCUSDT/5m/"):
        raise ValueError(f"URL outside allowlist: {url}")
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "btc-taker-flow-research/1"})
            with urllib.request.urlopen(request, timeout=60) as response:
                final = urllib.parse.urlparse(response.geturl())
                if final.hostname != ALLOWED_HOST:
                    raise ValueError("download redirected outside allowlist")
                return response.read()
        except (urllib.error.URLError, TimeoutError):
            if attempt + 1 == retries: raise
            time.sleep(2 ** attempt)
    raise RuntimeError("unreachable")


def official_checksum(filename: str) -> str:
    text = fetch(f"{BASE}/{filename}.CHECKSUM").decode("ascii").strip()
    fields = text.split()
    if len(fields) < 1 or len(fields[0]) != 64:
        raise ValueError(f"invalid checksum sidecar for {filename}")
    return fields[0].lower()


def existing_payloads(tar_path: Path | None) -> dict[str, bytes]:
    if tar_path is None: return {}
    payloads = {}
    with tarfile.open(tar_path, "r:gz") as archive:
        for member in archive.getmembers():
            name = Path(member.name).name
            if member.isfile() and name.startswith("BTCUSDT-5m-") and name.endswith(".zip"):
                handle = archive.extractfile(member)
                if handle is not None: payloads[name] = handle.read()
    return payloads


def inspect_zip(payload: bytes, filename: str) -> dict:
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        members = [m for m in archive.infolist() if not m.is_dir()]
        expected = filename.removesuffix(".zip") + ".csv"
        if len(members) != 1 or members[0].filename != expected:
            raise ValueError(f"unexpected ZIP contents: {filename}")
        with archive.open(members[0]) as binary:
            reader = csv.reader(io.TextIOWrapper(binary, encoding="utf-8", newline=""))
            count = 0; first = last = None; unit = None
            for row in reader:
                if len(row) != 12: raise ValueError(f"invalid row width in {filename}")
                current_unit = "microseconds" if len(row[0]) == 16 else "milliseconds" if len(row[0]) == 13 else "unknown"
                if unit is None: unit = current_unit
                if current_unit != unit or unit == "unknown": raise ValueError(f"mixed timestamp units in {filename}")
                value = int(row[0]) // (1000 if unit == "microseconds" else 1)
                first = value if first is None else first; last = value; count += 1
    return {"rows": count, "first_ms": first, "last_ms": last, "timestamp_unit": unit}


def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("--start",default="2017-08"); parser.add_argument("--end",default="2026-07"); parser.add_argument("--output-dir",type=Path,required=True); parser.add_argument("--reuse-tar",type=Path)
    args=parser.parse_args(); args.output_dir.mkdir(parents=True,exist_ok=True)
    reused=existing_payloads(args.reuse_tar); records=[]
    for period in months(args.start,args.end):
        filename=f"BTCUSDT-5m-{period}.zip"; expected=official_checksum(filename)
        destination=args.output_dir/filename
        if destination.exists() and sha(destination.read_bytes()) == expected:
            payload=destination.read_bytes(); origin="existing_file"
        elif filename in reused and sha(reused[filename]) == expected:
            payload=reused[filename]; origin="reused_verified_archive"
        else:
            payload=fetch(f"{BASE}/{filename}"); origin="downloaded"
        actual=sha(payload)
        if actual != expected: raise ValueError(f"official checksum mismatch: {filename}")
        if not destination.exists() or sha(destination.read_bytes()) != actual:
            temporary=destination.with_suffix(".zip.part"); temporary.write_bytes(payload); os.replace(temporary,destination)
        info=inspect_zip(payload,filename)
        records.append({"file":filename,"source_url":f"{BASE}/{filename}","checksum_url":f"{BASE}/{filename}.CHECKSUM","official_sha256":expected,"bytes":len(payload),"origin":origin,**info})
        print(f"{period} {origin} {info['rows']} rows",flush=True)
    manifest={"accepted":True,"dataset":"binance-spot-klines","symbol":"BTCUSDT","interval":"5m","start_period":args.start,"end_period":args.end,"files":records}
    content=(json.dumps(manifest,indent=2,sort_keys=True)+"\n").encode(); temporary=args.output_dir/"btc-history-source-manifest.json.part"; temporary.write_bytes(content); os.replace(temporary,args.output_dir/"btc-history-source-manifest.json")


if __name__ == "__main__": main()
