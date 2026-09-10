#!/usr/bin/env python3
"""Acquire official direct daily bars for BTC spot/perpetual D0 v3."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "research/btc/contracts/btc-spot-perp-continuation-data-audit-v3.json"
DEFAULT_OUTPUT = ROOT / "artifacts/agent-level-experiment/btc-focused/spot-perp-continuation-d0-v3"
UTC = timezone.utc


def load_v1_module():
    path = ROOT / "scripts/acquire_btc_spot_perp_continuation_data.py"
    spec = importlib.util.spec_from_file_location("spot_perp_d0_v1_acquisition_for_v3", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


V1 = load_v1_module()
canonical_bytes = V1.canonical_bytes
sha256_path = V1.sha256_path
ensure_output_path = V1.ensure_output_path
fetch = V1.fetch
expected_sidecar_digest = V1.expected_sidecar_digest
iso_to_ms = V1.iso_to_ms


def month_sequence(start_year: int, start_month: int) -> list[tuple[int, int]]:
    values = []
    for year in range(start_year, 2026):
        first_month = start_month if year == start_year else 1
        values.extend((year, month) for month in range(first_month, 13))
    return values


def acquire_monthly_archive(task: tuple[str, int, int], output: Path, allowed_hosts: set[str]) -> dict:
    market, year, month = task
    filename = f"BTCUSDT-1d-{year:04d}-{month:02d}.zip"
    prefix = "spot" if market == "spot" else "futures/um"
    url = f"https://data.binance.vision/data/{prefix}/monthly/klines/BTCUSDT/1d/{filename}"
    try:
        sidecar = fetch(url + ".CHECKSUM", allowed_hosts)
        expected = expected_sidecar_digest(sidecar, filename)
        payload = fetch(url, allowed_hosts)
        actual = hashlib.sha256(payload).hexdigest()
        if actual != expected:
            raise ValueError(f"official {market} daily archive checksum mismatch: {filename}")
        directory = output / "raw" / f"{market}-monthly" / f"{year:04d}"
        directory.mkdir(parents=True, exist_ok=True)
        archive_path = directory / filename
        sidecar_path = directory / f"{filename}.CHECKSUM"
        archive_path.write_bytes(payload)
        sidecar_path.write_bytes(sidecar)
        return {
            "archive_path": str(archive_path.relative_to(ROOT)),
            "archive_sha256": actual,
            "bytes": len(payload),
            "filename": filename,
            "market": market,
            "month": f"{year:04d}-{month:02d}",
            "official_checksum": expected,
            "official_checksum_path": str(sidecar_path.relative_to(ROOT)),
            "source_url": url,
            "status": "downloaded_and_official_checksum_matched",
        }
    except Exception as exc:
        return {
            "error": f"{type(exc).__name__}: {exc}",
            "filename": filename,
            "market": market,
            "month": f"{year:04d}-{month:02d}",
            "source_url": url,
            "status": "failed",
        }


def acquire_rest_daily(contract: dict, output: Path, allowed_hosts: set[str]) -> dict:
    fallback = contract["pre_2020_rest_fallback"]
    start = iso_to_ms(fallback["start_inclusive"])
    end_exclusive = iso_to_ms(fallback["end_exclusive"])
    query = urllib.parse.urlencode({
        "symbol": "BTCUSDT",
        "interval": "1d",
        "startTime": start,
        "endTime": end_exclusive - 1,
        "limit": fallback["limit"],
    })
    url = f"https://fapi.binance.com/fapi/v1/klines?{query}"
    payload = fetch(url, allowed_hosts)
    rows = json.loads(payload)
    if not isinstance(rows, list) or not rows:
        raise ValueError("official daily REST fallback returned no rows")
    path = output / "raw/rest/BTCUSDT-1d-2019-warmup-with-2020-overlap.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return {
        "bytes": len(payload),
        "first_open_time_ms": rows[0][0],
        "last_open_time_ms": rows[-1][0],
        "path": str(path.relative_to(ROOT)),
        "retrieved_at": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
        "row_count": len(rows),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "source_url": url,
        "status": "downloaded",
    }


def acquire_futures_daily_overlap(output: Path, allowed_hosts: set[str]) -> dict:
    filename = "BTCUSDT-1d-2019-12-31.zip"
    url = f"https://data.binance.vision/data/futures/um/daily/klines/BTCUSDT/1d/{filename}"
    sidecar = fetch(url + ".CHECKSUM", allowed_hosts)
    expected = expected_sidecar_digest(sidecar, filename)
    payload = fetch(url, allowed_hosts)
    actual = hashlib.sha256(payload).hexdigest()
    if actual != expected:
        raise ValueError("official futures daily overlap checksum mismatch")
    directory = output / "raw/futures-daily-overlap"
    directory.mkdir(parents=True, exist_ok=True)
    archive_path = directory / filename
    sidecar_path = directory / f"{filename}.CHECKSUM"
    archive_path.write_bytes(payload)
    sidecar_path.write_bytes(sidecar)
    return {
        "archive_path": str(archive_path.relative_to(ROOT)),
        "archive_sha256": actual,
        "filename": filename,
        "official_checksum": expected,
        "official_checksum_path": str(sidecar_path.relative_to(ROOT)),
        "retrieved_at": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
        "source_url": url,
        "status": "downloaded_and_official_checksum_matched",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output = ensure_output_path(args.output)
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    if contract.get("status") != "frozen_before_d0_v3_acquisition":
        raise ValueError("D0 v3 contract is not frozen before acquisition")
    for item in contract["bound_inputs"]:
        if sha256_path(ROOT / item["path"]) != item["sha256"]:
            raise ValueError(f"bound input checksum mismatch: {item['path']}")
    output.mkdir(parents=True)
    allowed_hosts = set(contract["allowed_hosts"])
    tasks = [("spot", year, month) for year, month in month_sequence(2019, 9)]
    tasks.extend(("perpetual", year, month) for year, month in month_sequence(2020, 1))
    records = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(acquire_monthly_archive, task, output, allowed_hosts): task
            for task in tasks
        }
        for future in as_completed(futures):
            records.append(future.result())
    records.sort(key=lambda item: (item["market"], item["month"]))
    rest = acquire_rest_daily(contract, output, allowed_hosts)
    daily_overlap = acquire_futures_daily_overlap(output, allowed_hosts)
    manifest = {
        "acquisition_has_no_future_return_label_forecast_strategy_or_pnl": True,
        "archive_failures": sum(item["status"] == "failed" for item in records),
        "archive_records": records,
        "audit_id": contract["audit_id"],
        "contract": {"path": str(CONTRACT_PATH.relative_to(ROOT)), "sha256": sha256_path(CONTRACT_PATH)},
        "credentials_used": False,
        "futures_daily_overlap": daily_overlap,
        "rest_daily": rest,
    }
    manifest_path = output / "source-manifest.json"
    manifest_path.write_bytes(canonical_bytes(manifest))
    print(json.dumps({
        "archive_failures": manifest["archive_failures"],
        "archives": len(records),
        "output": str(output.relative_to(ROOT)),
        "rest_rows": rest["row_count"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
