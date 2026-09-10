#!/usr/bin/env python3
"""Acquire checksummed official BTCUSDT daily archives for the S2 data-only audit."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from trading_platform.research_program import canonical_json, sha256_file


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = REPO_ROOT / "config/experiments/btc-regime-routing-s2-daily-data-audit-v1.json"


def periods(start: str, end: str) -> list[str]:
    year, month = map(int, start.split("-"))
    end_year, end_month = map(int, end.split("-"))
    result: list[str] = []
    while (year, month) <= (end_year, end_month):
        result.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return result


def load_contract(path: Path) -> dict[str, Any]:
    if path.resolve(strict=True) != DEFAULT_CONTRACT.resolve(strict=True):
        raise ValueError("exact frozen daily-data audit contract is required")
    raw = path.read_text(encoding="utf-8")
    payload = json.loads(raw)
    if raw != canonical_json(payload):
        raise ValueError("daily-data audit contract is not canonical JSON")
    if (
        payload.get("schema_version")
        != "btc-regime-routing-s2-daily-data-audit-contract-v1"
        or payload.get("status") != "frozen"
    ):
        raise ValueError("unsupported or unfrozen daily-data audit contract")
    return payload


def fetch(url: str, *, allowed_host: str, allowed_prefix: str) -> bytes:
    parsed = urllib.parse.urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != allowed_host
        or not parsed.path.startswith(allowed_prefix)
    ):
        raise ValueError(f"URL outside frozen allowlist: {url}")
    request = urllib.request.Request(url, headers={"User-Agent": "btc-regime-daily-audit/1"})
    last_error: Exception | None = None
    for _ in range(4):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                final = urllib.parse.urlparse(response.geturl())
                if final.scheme != "https" or final.hostname != allowed_host:
                    raise ValueError("archive download redirected outside frozen allowlist")
                return response.read()
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
    assert last_error is not None
    raise last_error


def parse_official_checksum(payload: bytes, filename: str) -> str:
    fields = payload.decode("ascii").strip().split()
    if len(fields) < 1 or len(fields[0]) != 64:
        raise ValueError(f"invalid official checksum sidecar: {filename}")
    digest = fields[0].lower()
    int(digest, 16)
    return digest


def timestamp_ms(raw: str, filename: str) -> tuple[int, str]:
    if len(raw) == 13:
        return int(raw), "milliseconds"
    if len(raw) == 16 and int(raw) % 1000 == 0:
        return int(raw) // 1000, "microseconds"
    raise ValueError(f"unsupported timestamp in {filename}: {raw}")


def inspect_zip(payload: bytes, filename: str) -> dict[str, Any]:
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        members = [member for member in archive.infolist() if not member.is_dir()]
        expected_member = filename.removesuffix(".zip") + ".csv"
        if len(members) != 1 or members[0].filename != expected_member:
            raise ValueError(f"unexpected ZIP contents: {filename}")
        row_count = 0
        first_ms: int | None = None
        last_ms: int | None = None
        unit: str | None = None
        with archive.open(members[0]) as binary:
            reader = csv.reader(io.TextIOWrapper(binary, encoding="utf-8", newline=""))
            for row in reader:
                if len(row) != 12:
                    raise ValueError(f"invalid daily row width in {filename}")
                value, current_unit = timestamp_ms(row[0], filename)
                if unit is None:
                    unit = current_unit
                elif current_unit != unit:
                    raise ValueError(f"mixed timestamp units in {filename}")
                if last_ms is not None and value <= last_ms:
                    raise ValueError(f"daily rows are not ordered in {filename}")
                first_ms = value if first_ms is None else first_ms
                last_ms = value
                row_count += 1
    if row_count == 0 or first_ms is None or last_ms is None or unit is None:
        raise ValueError(f"empty daily archive: {filename}")
    return {
        "first_open_ms": first_ms,
        "last_open_ms": last_ms,
        "rows": row_count,
        "timestamp_unit": unit,
    }


def atomic_write(path: Path, payload: bytes) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_bytes(payload)
    os.replace(temporary, path)


def acquire_one(
    period: str, *, base_url: str, allowed_host: str, raw_dir: Path
) -> dict[str, Any]:
    filename = f"BTCUSDT-1d-{period}.zip"
    url = f"{base_url}/{filename}"
    checksum_url = f"{url}.CHECKSUM"
    allowed_prefix = urllib.parse.urlparse(base_url).path.rstrip("/") + "/"
    checksum_payload = fetch(
        checksum_url, allowed_host=allowed_host, allowed_prefix=allowed_prefix
    )
    official_sha256 = parse_official_checksum(checksum_payload, filename)
    destination = raw_dir / filename
    if destination.exists() and sha256_file(destination) == official_sha256:
        payload = destination.read_bytes()
    else:
        payload = fetch(url, allowed_host=allowed_host, allowed_prefix=allowed_prefix)
        observed = hashlib.sha256(payload).hexdigest()
        if observed != official_sha256:
            raise ValueError(f"official checksum mismatch for {filename}")
        atomic_write(destination, payload)
    observed = hashlib.sha256(payload).hexdigest()
    if observed != official_sha256:
        raise ValueError(f"stored checksum mismatch for {filename}")
    return {
        "bytes": len(payload),
        "checksum_url": checksum_url,
        "file": filename,
        "official_sha256": official_sha256,
        "source_url": url,
        **inspect_zip(payload, filename),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    if not 1 <= args.workers <= 16:
        raise ValueError("workers must be within [1, 16]")
    contract = load_contract(args.contract)
    boundaries = contract["boundaries"]
    expected_periods = periods(
        boundaries["archive_start_period"], boundaries["archive_end_period"]
    )
    if len(expected_periods) != boundaries["expected_monthly_archives"]:
        raise ValueError("frozen archive count does not match frozen period boundary")
    output_root = (REPO_ROOT / contract["output"]["artifact_root"]).resolve(strict=False)
    repo_root = REPO_ROOT.resolve(strict=True)
    output_root.relative_to(repo_root)
    if output_root.is_symlink():
        raise ValueError("symlinked output root is prohibited")
    raw_dir = output_root / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    base_url = contract["inputs"]["monthly_base_url"]
    allowed_hosts = contract["inputs"]["official_host_allowlist"]
    if allowed_hosts != ["data.binance.vision"]:
        raise ValueError("unexpected official host allowlist")
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        records = list(
            pool.map(
                lambda period: acquire_one(
                    period,
                    base_url=base_url,
                    allowed_host=allowed_hosts[0],
                    raw_dir=raw_dir,
                ),
                expected_periods,
            )
        )
    manifest = {
        "archives": records,
        "audit_id": contract["audit_id"],
        "contract_sha256": sha256_file(DEFAULT_CONTRACT),
        "interval": "1d",
        "schema_version": "btc-regime-routing-daily-source-manifest-v1",
        "symbol": contract["inputs"]["symbol"],
    }
    manifest_path = output_root / "source-manifest.json"
    if manifest_path.exists():
        existing = manifest_path.read_text(encoding="utf-8")
        if existing != canonical_json(manifest):
            raise ValueError("refusing to replace a different source manifest")
    else:
        atomic_write(manifest_path, canonical_json(manifest).encode("utf-8"))
    print(
        canonical_json(
            {
                "archives": len(records),
                "decision": "official_daily_archives_acquired",
                "manifest_sha256": sha256_file(manifest_path),
                "rows": sum(record["rows"] for record in records),
            }
        ),
        end="",
    )


if __name__ == "__main__":
    main()
