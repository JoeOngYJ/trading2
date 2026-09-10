#!/usr/bin/env python3
"""Acquire only the official/public inputs frozen by btc-carry-data-qualification-v1."""

from __future__ import annotations

import hashlib
import json
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "research/btc/contracts/btc-carry-data-qualification-v1.json"
OUTPUT = ROOT / "artifacts/agent-level-experiment/btc-focused/carry-data-qualification-v1"
BASE = "https://data.binance.vision/data/futures/um/monthly"
UTC = timezone.utc


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def allowed_url(url: str, allowed_hosts: set[str]) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in allowed_hosts or parsed.username or parsed.password:
        raise ValueError(f"URL is outside frozen allowlist: {url}")


def fetch(url: str, allowed_hosts: set[str], attempts: int = 3) -> bytes:
    allowed_url(url, allowed_hosts)
    error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "btc-carry-data-audit-v1/1.0"})
            with urllib.request.urlopen(request, timeout=45) as response:
                if not 200 <= response.status < 300:
                    raise RuntimeError(f"HTTP {response.status}: {url}")
                return response.read()
        except Exception as exc:  # acquisition records exact terminal failure
            error = exc
            if attempt + 1 < attempts:
                time.sleep(0.5 * (attempt + 1))
    assert error is not None
    raise error


def expected_sidecar_digest(payload: bytes, filename: str) -> str:
    text = payload.decode("utf-8").strip()
    parts = text.split()
    if len(parts) < 2 or parts[1].lstrip("*") != filename:
        raise ValueError(f"invalid official checksum sidecar for {filename}")
    digest = parts[0].lower()
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ValueError(f"invalid official SHA-256 for {filename}")
    return digest


def archive_url(series: str, year: int, month: int) -> tuple[str, str]:
    filename = f"BTCUSDT-1h-{year:04d}-{month:02d}.zip"
    if series == "fundingRate":
        filename = f"BTCUSDT-fundingRate-{year:04d}-{month:02d}.zip"
        url = f"{BASE}/{series}/BTCUSDT/{filename}"
    else:
        url = f"{BASE}/{series}/BTCUSDT/1h/{filename}"
    return url, filename


def acquire_archive(task: tuple[str, int, int], allowed_hosts: set[str]) -> dict:
    series, year, month = task
    url, filename = archive_url(series, year, month)
    relative_dir = Path("raw") / series / f"{year:04d}"
    destination_dir = OUTPUT / relative_dir
    destination_dir.mkdir(parents=True, exist_ok=True)
    zip_path = destination_dir / filename
    sidecar_path = destination_dir / f"{filename}.CHECKSUM"
    try:
        if zip_path.is_file() and sidecar_path.is_file():
            sidecar = sidecar_path.read_bytes()
            expected = expected_sidecar_digest(sidecar, filename)
            actual = sha256_path(zip_path)
            if actual == expected:
                return {
                    "archive_path": str(zip_path.relative_to(ROOT)),
                    "archive_sha256": actual,
                    "bytes": zip_path.stat().st_size,
                    "filename": filename,
                    "month": f"{year:04d}-{month:02d}",
                    "official_checksum": expected,
                    "official_checksum_path": str(sidecar_path.relative_to(ROOT)),
                    "series": series,
                    "source_url": url,
                    "status": "existing_and_official_checksum_matched",
                }
        sidecar = fetch(url + ".CHECKSUM", allowed_hosts)
        expected = expected_sidecar_digest(sidecar, filename)
        payload = fetch(url, allowed_hosts)
        actual = hashlib.sha256(payload).hexdigest()
        if actual != expected:
            raise ValueError(f"official checksum mismatch: {filename}")
        zip_path.write_bytes(payload)
        sidecar_path.write_bytes(sidecar)
        return {
            "archive_path": str(zip_path.relative_to(ROOT)),
            "archive_sha256": actual,
            "bytes": len(payload),
            "filename": filename,
            "month": f"{year:04d}-{month:02d}",
            "official_checksum": expected,
            "official_checksum_path": str(sidecar_path.relative_to(ROOT)),
            "series": series,
            "source_url": url,
            "status": "downloaded_and_official_checksum_matched",
        }
    except Exception as exc:
        return {
            "filename": filename,
            "month": f"{year:04d}-{month:02d}",
            "series": series,
            "source_url": url,
            "status": "failed",
            "error": f"{type(exc).__name__}: {exc}",
        }


def acquire_named(name: str, url: str, allowed_hosts: set[str], suffix: str) -> dict:
    path = OUTPUT / "public-evidence" / f"{name}{suffix}"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        payload = fetch(url, allowed_hosts)
        path.write_bytes(payload)
        return {
            "bytes": len(payload),
            "name": name,
            "path": str(path.relative_to(ROOT)),
            "retrieved_at": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "source_url": url,
            "status": "downloaded",
        }
    except Exception as exc:
        return {"name": name, "source_url": url, "status": "failed", "error": f"{type(exc).__name__}: {exc}"}


def main() -> None:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    if contract["status"] != "frozen_before_any_new_acquisition" or contract["no_credentials"] is not True:
        raise ValueError("B2 contract is not frozen and credential-free")
    for item in contract["bound_existing_inputs"]:
        if sha256_path(ROOT / item["path"]) != item["sha256"]:
            raise ValueError(f"bound input checksum mismatch: {item['path']}")
    allowed_hosts = set(contract["allowed_hosts"])
    OUTPUT.mkdir(parents=True, exist_ok=True)

    tasks = [
        (series, year, month)
        for series in contract["acquisition"]["archive_series"]
        for year in range(2020, 2026)
        for month in range(1, 13)
    ]
    archive_records = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(acquire_archive, task, allowed_hosts): task for task in tasks}
        for future in as_completed(futures):
            archive_records.append(future.result())
    archive_records.sort(key=lambda item: (item["series"], item["month"]))

    public_sources = [
        ("spot-exchange-info-BTCUSDT", "https://data-api.binance.vision/api/v3/exchangeInfo?symbol=BTCUSDT", ".json"),
        ("usd-m-exchange-info", "https://fapi.binance.com/fapi/v1/exchangeInfo", ".json"),
        ("usd-m-funding-info", "https://fapi.binance.com/fapi/v1/fundingInfo", ".json"),
        ("usd-m-mark-index-BTCUSDT", "https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT", ".json"),
        ("binance-public-data-README", "https://raw.githubusercontent.com/binance/binance-public-data/master/README.md", ".md"),
        ("binance-fee-schedule", "https://www.binance.com/en/fee/trading", ".html"),
        ("usd-m-account-margin-documentation", "https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/account", ".html"),
        ("usd-m-market-data-documentation", "https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data", ".html"),
    ]
    public_records = [acquire_named(name, url, allowed_hosts, suffix) for name, url, suffix in public_sources]
    manifest = {
        "archive_failures": sum(item["status"] == "failed" for item in archive_records),
        "archive_records": archive_records,
        "audit_id": contract["audit_id"],
        "contract": {"path": str(CONTRACT_PATH.relative_to(ROOT)), "sha256": sha256_path(CONTRACT_PATH)},
        "credentials_used": False,
        "public_evidence_failures": sum(item["status"] == "failed" for item in public_records),
        "public_evidence_records": public_records,
        "return_pnl_or_strategy_calculated": False,
    }
    (OUTPUT / "source-manifest.json").write_bytes(canonical_bytes(manifest))
    print(json.dumps({
        "archive_failures": manifest["archive_failures"],
        "archives_downloaded": len(archive_records) - manifest["archive_failures"],
        "public_evidence_failures": manifest["public_evidence_failures"],
        "source_manifest": str((OUTPUT / "source-manifest.json").relative_to(ROOT)),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
