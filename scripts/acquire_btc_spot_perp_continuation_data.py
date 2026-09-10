#!/usr/bin/env python3
"""Acquire only the public inputs frozen by the BTC spot/perp D0 audit."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "research/btc/contracts/btc-spot-perp-continuation-data-audit-v1.json"
DEFAULT_OUTPUT = ROOT / "artifacts/agent-level-experiment/btc-focused/spot-perp-continuation-d0-v1"
UTC = timezone.utc


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_output_path(path: Path) -> Path:
    resolved = path.resolve()
    root = ROOT.resolve()
    if resolved == root or root not in resolved.parents:
        raise ValueError("output must be a new directory below the repository root")
    if resolved.exists():
        raise FileExistsError(f"refusing to overwrite existing D0 output: {resolved}")
    return resolved


def allowed_url(url: str, allowed_hosts: set[str]) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in allowed_hosts or parsed.username or parsed.password:
        raise ValueError(f"URL is outside frozen allowlist: {url}")


def fetch(url: str, allowed_hosts: set[str], attempts: int = 3) -> bytes:
    allowed_url(url, allowed_hosts)
    error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "btc-spot-perp-d0-v1/1.0"})
            with urllib.request.urlopen(request, timeout=45) as response:
                if not 200 <= response.status < 300:
                    raise RuntimeError(f"HTTP {response.status}: {url}")
                return response.read()
        except Exception as exc:
            error = exc
            if attempt + 1 < attempts:
                time.sleep(0.5 * (attempt + 1))
    assert error is not None
    raise error


def expected_sidecar_digest(payload: bytes, filename: str) -> str:
    parts = payload.decode("utf-8").strip().split()
    if len(parts) < 2 or parts[1].lstrip("*") != filename:
        raise ValueError(f"invalid official checksum sidecar for {filename}")
    digest = parts[0].lower()
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ValueError(f"invalid official SHA-256 for {filename}")
    return digest


def iso_to_ms(value: str) -> int:
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)


def acquire_rest_pages(contract: dict, output: Path, allowed_hosts: set[str]) -> list[dict]:
    specification = contract["pre_2020_rest_fallback"]
    start = iso_to_ms(specification["start_inclusive"])
    end_exclusive = iso_to_ms(specification["end_exclusive"])
    limit = int(specification["limit"])
    maximum_pages = int(specification["maximum_pages"])
    records: list[dict] = []
    cursor = start
    raw_dir = output / "raw/rest"
    raw_dir.mkdir(parents=True, exist_ok=True)
    for page_number in range(1, maximum_pages + 1):
        query = urllib.parse.urlencode({
            "symbol": "BTCUSDT",
            "interval": "1h",
            "startTime": cursor,
            "endTime": end_exclusive - 1,
            "limit": limit,
        })
        url = f"https://fapi.binance.com/fapi/v1/klines?{query}"
        payload = fetch(url, allowed_hosts)
        rows = json.loads(payload)
        if not isinstance(rows, list):
            raise ValueError("official REST kline response is not an array")
        path = raw_dir / f"klines-page-{page_number:03d}.json"
        path.write_bytes(payload)
        record = {
            "bytes": len(payload),
            "first_open_time_ms": None if not rows else rows[0][0],
            "last_open_time_ms": None if not rows else rows[-1][0],
            "path": str(path.relative_to(ROOT)),
            "request_end_exclusive_ms": end_exclusive,
            "request_start_ms": cursor,
            "retrieved_at": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
            "row_count": len(rows),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "source_url": url,
            "status": "downloaded",
        }
        records.append(record)
        if not rows or int(rows[-1][0]) + 3_600_000 >= end_exclusive:
            break
        next_cursor = int(rows[-1][0]) + 3_600_000
        if next_cursor <= cursor:
            raise ValueError("REST pagination did not advance")
        cursor = next_cursor
    if not records or records[-1]["last_open_time_ms"] is None:
        raise ValueError("official REST fallback returned no rows")
    if int(records[-1]["last_open_time_ms"]) + 3_600_000 < end_exclusive:
        raise ValueError("official REST fallback exceeded frozen maximum page count")
    return records


def acquire_daily_overlap(output: Path, allowed_hosts: set[str]) -> dict:
    filename = "BTCUSDT-1h-2019-12-31.zip"
    url = f"https://data.binance.vision/data/futures/um/daily/klines/BTCUSDT/1h/{filename}"
    sidecar = fetch(url + ".CHECKSUM", allowed_hosts)
    expected = expected_sidecar_digest(sidecar, filename)
    payload = fetch(url, allowed_hosts)
    actual = hashlib.sha256(payload).hexdigest()
    if actual != expected:
        raise ValueError("official daily overlap archive checksum mismatch")
    raw_dir = output / "raw/daily-overlap"
    raw_dir.mkdir(parents=True, exist_ok=True)
    archive_path = raw_dir / filename
    sidecar_path = raw_dir / f"{filename}.CHECKSUM"
    archive_path.write_bytes(payload)
    sidecar_path.write_bytes(sidecar)
    return {
        "archive_path": str(archive_path.relative_to(ROOT)),
        "archive_sha256": actual,
        "bytes": len(payload),
        "filename": filename,
        "official_checksum": expected,
        "official_checksum_path": str(sidecar_path.relative_to(ROOT)),
        "retrieved_at": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
        "source_url": url,
        "status": "downloaded_and_official_checksum_matched",
    }


def recheck_monthly_sidecars(contract: dict, output: Path, allowed_hosts: set[str]) -> list[dict]:
    carry_manifest_path = ROOT / contract["bound_inputs_by_role"]["existing_perpetual_source_manifest"]["path"]
    carry_manifest = json.loads(carry_manifest_path.read_text(encoding="utf-8"))
    records = [
        item for item in carry_manifest["archive_records"]
        if item.get("series") == "klines" and item.get("status") != "failed"
    ]
    if len(records) != 72:
        raise ValueError("bound 2020-2025 perpetual archive set is not 72 months")
    raw_dir = output / "raw/current-sidecars"
    raw_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for item in sorted(records, key=lambda value: value["month"]):
        payload = fetch(item["source_url"] + ".CHECKSUM", allowed_hosts)
        current = expected_sidecar_digest(payload, item["filename"])
        path = raw_dir / f"{item['filename']}.CHECKSUM"
        path.write_bytes(payload)
        results.append({
            "bound_archive_path": item["archive_path"],
            "bound_archive_sha256": item["archive_sha256"],
            "current_official_checksum": current,
            "current_sidecar_path": str(path.relative_to(ROOT)),
            "month": item["month"],
            "revision_detected": current != item["archive_sha256"],
            "source_url": item["source_url"] + ".CHECKSUM",
        })
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output = ensure_output_path(args.output)
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    if contract.get("status") != "frozen_before_d0_acquisition":
        raise ValueError("D0 contract is not frozen before acquisition")
    for item in contract["bound_inputs"]:
        path = ROOT / item["path"]
        if sha256_path(path) != item["sha256"]:
            raise ValueError(f"bound input checksum mismatch: {item['path']}")
    output.mkdir(parents=True)
    allowed_hosts = set(contract["allowed_hosts"])
    rest_pages = acquire_rest_pages(contract, output, allowed_hosts)
    daily_overlap = acquire_daily_overlap(output, allowed_hosts)
    monthly_sidecars = recheck_monthly_sidecars(contract, output, allowed_hosts)
    manifest = {
        "acquisition_has_no_future_return_label_forecast_strategy_or_pnl": True,
        "audit_id": contract["audit_id"],
        "contract": {"path": str(CONTRACT_PATH.relative_to(ROOT)), "sha256": sha256_path(CONTRACT_PATH)},
        "credentials_used": False,
        "daily_overlap": daily_overlap,
        "monthly_sidecar_rechecks": monthly_sidecars,
        "rest_pages": rest_pages,
        "revision_count": sum(item["revision_detected"] for item in monthly_sidecars),
    }
    manifest_path = output / "source-manifest.json"
    manifest_path.write_bytes(canonical_bytes(manifest))
    print(json.dumps({
        "output": str(output.relative_to(ROOT)),
        "rest_pages": len(rest_pages),
        "revision_count": manifest["revision_count"],
        "source_manifest": str(manifest_path.relative_to(ROOT)),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
