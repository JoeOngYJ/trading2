#!/usr/bin/env python3
"""Validate official BTCUSDT history and publish development/holdout partitions."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import os
import tempfile
import zipfile
from pathlib import Path

from extract_btc_taker_flow import OUTPUT_COLUMNS, ValidationError, detect_timestamp_unit, parse_row, sha256_path

SPLIT_MS = 1_767_225_600_000  # 2026-01-01 UTC


def publish(rows_path: Path, output_dir: Path, label: str, metadata: dict) -> dict:
    raw_sha = sha256_path(rows_path)
    temporary = tempfile.NamedTemporaryFile("wb", dir=output_dir, delete=False)
    temporary_path = Path(temporary.name)
    try:
        with rows_path.open("rb") as source, temporary:
            with gzip.GzipFile(filename="", mode="wb", compresslevel=9, fileobj=temporary, mtime=0) as target:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    target.write(chunk)
        compressed_sha = sha256_path(temporary_path)
        filename = f"BTCUSDT-5m-taker-trade-flow-{label}-{compressed_sha}.csv.gz"
        destination = output_dir / filename
        if destination.exists():
            if sha256_path(destination) != compressed_sha:
                raise ValidationError("content-addressed output mismatch")
            temporary_path.unlink()
        else:
            os.replace(temporary_path, destination)
    finally:
        if temporary_path.exists(): temporary_path.unlink()
    manifest = {**metadata, "accepted": True, "partition": label, "dataset_file": filename,
                "dataset_sha256": compressed_sha, "uncompressed_csv_sha256": raw_sha,
                "schema_version": "btc-taker-trade-flow-segmented-v1"}
    content=(json.dumps(manifest,indent=2,sort_keys=True)+"\n").encode()
    target=output_dir/f"{label}-manifest.json"; temp=target.with_suffix(".json.part"); temp.write_bytes(content); os.replace(temp,target)
    return manifest


def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("--input-dir",type=Path,required=True); parser.add_argument("--source-manifest",type=Path,required=True); parser.add_argument("--output-dir",type=Path,required=True)
    args=parser.parse_args(); args.output_dir.mkdir(parents=True,exist_ok=True)
    source=json.loads(args.source_manifest.read_text()); files=source["files"]
    partitions={"development-2017-2025": {"path":None,"handle":None,"writer":None,"rows":0,"first_open_ms":None,"last_open_ms":None,"segment_id":0,"previous_open":None,"gaps":[],"files":[],"legacy_nonzero_ignore_count":0,"legacy_close_boundary_count":0,"incomplete_bar_excluded_count":0,"misaligned_bar_excluded_count":0},
                "holdout-2026-01-07": {"path":None,"handle":None,"writer":None,"rows":0,"first_open_ms":None,"last_open_ms":None,"segment_id":0,"previous_open":None,"gaps":[],"files":[],"legacy_nonzero_ignore_count":0,"legacy_close_boundary_count":0,"incomplete_bar_excluded_count":0,"misaligned_bar_excluded_count":0}}
    try:
        for state in partitions.values():
            handle=tempfile.NamedTemporaryFile("w",encoding="utf-8",newline="",dir=args.output_dir,delete=False); state["path"]=Path(handle.name); state["handle"]=handle; state["writer"]=csv.writer(handle,lineterminator="\n"); state["writer"].writerow(("segment_id",)+OUTPUT_COLUMNS)
        for record in files:
            path=args.input_dir/record["file"]; payload=path.read_bytes()
            if hashlib.sha256(payload).hexdigest()!=record["official_sha256"]: raise ValidationError(f"checksum mismatch: {path.name}")
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                members=[m for m in archive.infolist() if not m.is_dir()]
                if len(members)!=1: raise ValidationError(f"unexpected ZIP contents: {path.name}")
                month_rows=0; month_first=month_last=None; month_partitions=set()
                with archive.open(members[0]) as binary:
                    reader=csv.reader(io.TextIOWrapper(binary,encoding="utf-8",newline="")); unit=None
                    for fields in reader:
                        if unit is None: unit=detect_timestamp_unit(fields[0])
                        divisor=1000 if unit=="microseconds" else 1
                        raw_open=int(fields[0])//divisor; raw_close=int(fields[6])//divisor
                        label="development-2017-2025" if raw_open<SPLIT_MS else "holdout-2026-01-07"; state=partitions[label]
                        month_first=raw_open if month_first is None else month_first; month_last=raw_open; month_rows+=1; month_partitions.add(label)
                        if raw_open % 300_000:
                            state["misaligned_bar_excluded_count"] += 1
                            continue
                        if raw_close-raw_open not in (299_999,300_000):
                            state["incomplete_bar_excluded_count"] += 1
                            continue
                        parsed=parse_row(fields,unit,allow_nonzero_ignore=True,allow_legacy_close_boundary=True)
                        if fields[11] != "0": state["legacy_nonzero_ignore_count"] += 1
                        if raw_close == raw_open + 300_000: state["legacy_close_boundary_count"] += 1
                        previous=state["previous_open"]
                        if previous is not None and parsed.open_ms!=previous+300_000:
                            missing=(parsed.open_ms-previous)//300_000-1
                            if missing<0: raise ValidationError("duplicate or non-monotonic timestamp")
                            state["segment_id"]+=1; state["gaps"].append({"after_open_ms":previous,"before_open_ms":parsed.open_ms,"missing_bars":missing})
                        state["writer"].writerow((state["segment_id"],)+parsed.values); state["previous_open"]=parsed.open_ms; state["rows"]+=1
                        state["first_open_ms"]=parsed.open_ms if state["first_open_ms"] is None else state["first_open_ms"]; state["last_open_ms"]=parsed.open_ms
                if month_rows!=record["rows"] or month_first!=record["first_ms"] or month_last!=record["last_ms"]: raise ValidationError(f"source inventory mismatch: {path.name}")
                if len(month_partitions)!=1: raise ValidationError("monthly archive crosses partition boundary")
                partitions[next(iter(month_partitions))]["files"].append(record["file"])
        results={}
        for label,state in partitions.items():
            state["handle"].close(); metadata={"symbol":"BTCUSDT","interval":"5m","rows":state["rows"],"first_open_ms":state["first_open_ms"],"last_open_ms":state["last_open_ms"],"segment_count":state["segment_id"]+1,"gap_count":len(state["gaps"]),"gaps":state["gaps"],"source_files":state["files"],"source_manifest_sha256":sha256_path(args.source_manifest),"legacy_nonzero_ignore_count":state["legacy_nonzero_ignore_count"],"legacy_close_boundary_count":state["legacy_close_boundary_count"],"incomplete_bar_excluded_count":state["incomplete_bar_excluded_count"],"misaligned_bar_excluded_count":state["misaligned_bar_excluded_count"],"holdout_access":"sealed; feature/pattern analysis prohibited without frozen hypothesis" if label.startswith("holdout") else "research development"}
            results[label]=publish(state["path"],args.output_dir,label,metadata)
        print(json.dumps(results,indent=2,sort_keys=True))
    finally:
        for state in partitions.values():
            handle=state.get("handle")
            if handle and not handle.closed: handle.close()
            path=state.get("path")
            if path and path.exists(): path.unlink()


if __name__=="__main__": main()
