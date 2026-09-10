#!/usr/bin/env python3
"""Write-once downloader for the frozen free Marketstack A1 source pilot."""

from __future__ import annotations

import argparse
import os
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from trading_platform.cross_asset_marketstack_audit import (
    MarketstackAuditError,
    build_request_specs,
    canonical_json,
    load_contract,
    parse_json_response,
    redact_secret,
    sha256_file,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = (
    REPO_ROOT / "config/experiments/cross-asset-a1-marketstack-free-source-pilot-v3.json"
)


def _download(url: str, api_key: str) -> tuple[bytes, int, str]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "TradingResearch-Marketstack-A1/1.0",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - frozen host
            raw = response.read()
            status = int(response.status)
            content_type = response.headers.get_content_type()
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
        safe = redact_secret(str(exc), api_key)
        raise MarketstackAuditError(f"Marketstack request failed: {safe}") from exc
    if not 200 <= status < 300:
        raise MarketstackAuditError(f"Marketstack returned HTTP {status}")
    parse_json_response(raw, "Marketstack response")
    return raw, status, content_type


def run(contract_path: Path) -> Path:
    contract_path = contract_path.resolve(strict=True)
    contract = load_contract(contract_path, REPO_ROOT)
    if contract_path != DEFAULT_CONTRACT.resolve(strict=True):
        raise MarketstackAuditError("only the canonical frozen Marketstack pilot is allowed")
    api_key = os.environ.get("MARKETSTACK_API_KEY", "")
    specs = build_request_specs(contract, api_key)
    output_root = REPO_ROOT / contract["output"]["artifact_root"]
    if output_root.exists():
        raise MarketstackAuditError(f"write-once artifact root already exists: {output_root}")
    output_root.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".a1-marketstack-", dir=output_root.parent) as temp_name:
        temp_root = Path(temp_name)
        raw_root = temp_root / "raw"
        raw_root.mkdir()
        records: list[dict[str, object]] = []
        retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        for spec in specs:
            raw, status, content_type = _download(spec.url, api_key)
            filename = f"{spec.ticker.lower()}-{spec.endpoint}.json"
            temporary_path = raw_root / filename
            temporary_path.write_bytes(raw)
            final_relative = Path(contract["output"]["artifact_root"]) / "raw" / filename
            records.append(
                {
                    "bytes": len(raw),
                    "content_type": content_type,
                    "credential_serialized": False,
                    "endpoint": spec.endpoint,
                    "error": None,
                    "http_status": status,
                    "path": final_relative.as_posix(),
                    "request_parameters": dict(spec.persisted_parameters),
                    "sha256": sha256_file(temporary_path),
                    "ticker": spec.ticker,
                }
            )
        manifest = {
            "api_token_serialized": False,
            "contract_sha256": sha256_file(contract_path),
            "files": records,
            "pilot_id": contract["pilot_id"],
            "request_count": len(records),
            "retrieved_at": retrieved_at,
            "schema_version": "cross-asset-a1-marketstack-source-manifest-v1",
            "strategy_data_evaluated": False,
        }
        (temp_root / "source-manifest.json").write_text(canonical_json(manifest), encoding="utf-8")
        temp_root.rename(output_root)
    return output_root / "source-manifest.json"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download the frozen free Marketstack A1 source-qualification pilot."
    )
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    args = parser.parse_args()
    try:
        manifest = run(args.contract)
    except MarketstackAuditError as exc:
        parser.error(str(exc))
    print(f"source manifest written: {manifest.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
