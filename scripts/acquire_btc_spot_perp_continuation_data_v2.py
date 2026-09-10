#!/usr/bin/env python3
"""Acquire official direct spot-hourly archives for BTC spot/perp D0 v2."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "research/btc/contracts/btc-spot-perp-continuation-data-audit-v2.json"
DEFAULT_OUTPUT = ROOT / "artifacts/agent-level-experiment/btc-focused/spot-perp-continuation-d0-v2"
UTC = timezone.utc


def load_v1_module():
    path = ROOT / "scripts/acquire_btc_spot_perp_continuation_data.py"
    spec = importlib.util.spec_from_file_location("spot_perp_d0_v1_acquisition", path)
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


def month_sequence() -> list[tuple[int, int]]:
    values = []
    for year in range(2019, 2026):
        first_month = 9 if year == 2019 else 1
        values.extend((year, month) for month in range(first_month, 13))
    return values


def acquire_spot_archive(task: tuple[int, int], output: Path, allowed_hosts: set[str]) -> dict:
    year, month = task
    filename = f"BTCUSDT-1h-{year:04d}-{month:02d}.zip"
    url = f"https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1h/{filename}"
    try:
        sidecar = fetch(url + ".CHECKSUM", allowed_hosts)
        expected = expected_sidecar_digest(sidecar, filename)
        payload = fetch(url, allowed_hosts)
        actual = hashlib.sha256(payload).hexdigest()
        if actual != expected:
            raise ValueError(f"official spot archive checksum mismatch: {filename}")
        directory = output / "raw/spot-monthly" / f"{year:04d}"
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
            "month": f"{year:04d}-{month:02d}",
            "source_url": url,
            "status": "failed",
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output = ensure_output_path(args.output)
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    if contract.get("status") != "frozen_before_d0_v2_acquisition":
        raise ValueError("D0 v2 contract is not frozen before acquisition")
    for item in contract["bound_inputs"]:
        if sha256_path(ROOT / item["path"]) != item["sha256"]:
            raise ValueError(f"bound input checksum mismatch: {item['path']}")
    output.mkdir(parents=True)
    allowed_hosts = set(contract["allowed_hosts"])
    records = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(acquire_spot_archive, task, output, allowed_hosts): task
            for task in month_sequence()
        }
        for future in as_completed(futures):
            records.append(future.result())
    records.sort(key=lambda item: item["month"])
    manifest = {
        "acquisition_has_no_future_return_label_forecast_strategy_or_pnl": True,
        "archive_failures": sum(item["status"] == "failed" for item in records),
        "audit_id": contract["audit_id"],
        "contract": {"path": str(CONTRACT_PATH.relative_to(ROOT)), "sha256": sha256_path(CONTRACT_PATH)},
        "credentials_used": False,
        "parent_d0_v1_source": contract["bound_inputs_by_role"]["parent_d0_v1_source_manifest"],
        "retrieval_completed_at": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
        "spot_archive_records": records,
    }
    manifest_path = output / "source-manifest.json"
    manifest_path.write_bytes(canonical_bytes(manifest))
    print(json.dumps({
        "archive_failures": manifest["archive_failures"],
        "archives": len(records),
        "output": str(output.relative_to(ROOT)),
        "source_manifest": str(manifest_path.relative_to(ROOT)),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
