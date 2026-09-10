#!/usr/bin/env python3
"""Acquire only the exact public files allowed by the frozen cross-asset A1 pilot."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trading_platform.cross_asset_data_audit import load_frozen_contract
from trading_platform.cross_asset_program import canonical_json, sha256_file


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = REPO_ROOT / "config/experiments/cross-asset-a1-lse-source-pilot-v1.json"
ALLOWED_HOSTS = frozenset(
    {
        "docs.londonstockexchange.com",
        "stooq.com",
        "www.ishares.com",
        "www.vanguard.co.uk",
    }
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def exact_stooq_url(endpoint: str, symbol: str, parameters: dict[str, str]) -> str:
    query = urllib.parse.urlencode({"s": symbol, **parameters})
    return f"{endpoint}?{query}"


def fetch(url: str) -> tuple[bytes, str, str | None]:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise ValueError(f"URL outside frozen A1 host allowlist: {url}")
    request = urllib.request.Request(url, headers={"User-Agent": "cross-asset-a1-audit/1"})
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            final_url = response.geturl()
            final = urllib.parse.urlparse(final_url)
            if final.scheme != "https" or final.hostname not in ALLOWED_HOSTS:
                raise ValueError("A1 download redirected outside the frozen host allowlist")
            return response.read(), final_url, None
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        return b"", url, f"{type(exc).__name__}: {exc}"


def atomic_write(path: Path, payload: bytes) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_bytes(payload)
    os.replace(temporary, path)


def store_one(raw_dir: Path, filename: str, role: str, url: str) -> dict[str, Any]:
    payload, final_url, error = fetch(url)
    relative = raw_dir.relative_to(REPO_ROOT) / filename
    record: dict[str, Any] = {
        "bytes": len(payload),
        "error": error,
        "final_url": final_url,
        "path": relative.as_posix(),
        "requested_url": url,
        "role": role,
        "sha256": hashlib.sha256(payload).hexdigest(),
    }
    destination = raw_dir / filename
    if destination.exists():
        if destination.read_bytes() != payload:
            raise ValueError(f"refusing to replace different A1 raw bytes: {destination}")
    else:
        atomic_write(destination, payload)
    return record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    args = parser.parse_args()
    if args.contract.resolve(strict=True) != DEFAULT_CONTRACT.resolve(strict=True):
        raise ValueError("exact frozen A1 pilot contract is required")
    contract = load_frozen_contract(args.contract)
    artifact_root = (REPO_ROOT / contract["output"]["artifact_root"]).resolve(strict=False)
    artifact_root.relative_to(REPO_ROOT.resolve(strict=True))
    if artifact_root.is_symlink():
        raise ValueError("symlinked A1 artifact root is prohibited")
    raw_dir = artifact_root / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    calendar = contract["sources"]["calendar"]
    records.append(store_one(raw_dir, "lse-calendar-2025.pdf", "calendar", calendar["url"]))
    stooq = contract["sources"]["stooq_daily_csv"]
    for instrument in contract["instruments"]:
        ticker = instrument["ticker"].lower()
        records.append(
            store_one(
                raw_dir,
                f"{ticker}-issuer.html",
                f"issuer_identity:{instrument['ticker']}",
                instrument["issuer_product_url"],
            )
        )
        records.append(
            store_one(
                raw_dir,
                f"{ticker}-2025-01-stooq.csv",
                f"stooq_daily_csv:{instrument['ticker']}",
                exact_stooq_url(
                    stooq["endpoint"], instrument["stooq_symbol"], stooq["exact_query_parameters"]
                ),
            )
        )
    manifest = {
        "contract_sha256": sha256_file(DEFAULT_CONTRACT),
        "files": records,
        "pilot_id": contract["pilot_id"],
        "request_count": len(records),
        "retrieved_at": utc_now(),
        "schema_version": "cross-asset-a1-source-manifest-v1",
        "strategy_data_evaluated": False,
    }
    manifest_path = artifact_root / "source-manifest.json"
    payload = canonical_json(manifest).encode("utf-8")
    if manifest_path.exists():
        raise ValueError(f"refusing to overwrite A1 source manifest: {manifest_path}")
    atomic_write(manifest_path, payload)
    print(
        canonical_json(
            {
                "decision": "a1_exact_pilot_files_acquired",
                "failed_requests": sum(record["error"] is not None for record in records),
                "files": len(records),
                "manifest_sha256": sha256_file(manifest_path),
            }
        ),
        end="",
    )


if __name__ == "__main__":
    main()
