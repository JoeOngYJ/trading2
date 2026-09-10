#!/usr/bin/env python3
"""Transactionally acquire four frozen LSE boundary-clarification responses."""

from __future__ import annotations

import argparse
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from trading_platform.cross_asset_twelvedata_audit import (
    TwelveDataAuditError,
    canonical_json,
    parse_response,
    sha256_bytes,
    sha256_file,
)
from trading_platform.cross_asset_twelvedata_lse_clarification import (
    MANIFEST_SCHEMA,
    build_request_specs,
    load_contract,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = REPO_ROOT / "config/experiments/cross-asset-a1-executable-universe-feasibility-v2.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def run(contract_path: Path, timeout_seconds: float) -> Path:
    contract = load_contract(contract_path)
    api_key = os.environ.get("TWELVEDATA_API_KEY", "")
    if not api_key.strip():
        raise TwelveDataAuditError("TWELVEDATA_API_KEY is required")
    specs = build_request_specs(contract)
    output_root = REPO_ROOT / contract["output"]["artifact_root"]
    if output_root.exists():
        raise TwelveDataAuditError("write-once LSE clarification artifact root already exists")
    output_root.parent.mkdir(parents=True, exist_ok=True)
    temp_root = Path(tempfile.mkdtemp(prefix=".twelvedata-lse-v2-", dir=output_root.parent))
    raw_root = temp_root / "raw"
    raw_root.mkdir()
    responses: list[dict[str, object]] = []
    try:
        for spec in specs:
            url = f"{contract['source_access']['api_base_url']}{spec.path}?{urlencode(spec.parameters)}"
            request = Request(
                url,
                headers={
                    "Accept": "application/json",
                    "Authorization": f"apikey {api_key}",
                    "User-Agent": "trading-research-exact-lse-boundary-clarification/1.0",
                },
                method="GET",
            )
            try:
                with urlopen(request, timeout=timeout_seconds) as response:
                    status = int(response.status)
                    raw = response.read()
            except HTTPError as exc:
                raise TwelveDataAuditError(
                    f"provider request failed for {spec.symbol} time_series: HTTP {exc.code}"
                ) from exc
            except (URLError, TimeoutError, OSError) as exc:
                message = str(exc).replace(api_key, "<redacted>")
                raise TwelveDataAuditError(
                    f"provider request failed for {spec.symbol} time_series: {message}"
                ) from exc
            if status != 200:
                raise TwelveDataAuditError(
                    f"provider request failed for {spec.symbol} time_series: HTTP {status}"
                )
            parse_response(raw, f"{spec.symbol} clarification time_series")
            raw_path = raw_root / spec.filename
            raw_path.write_bytes(raw)
            relative = Path(contract["output"]["artifact_root"]) / "raw" / spec.filename
            responses.append(
                {
                    "bytes": len(raw),
                    "endpoint": "time_series",
                    "parameters": dict(spec.parameters),
                    "path": relative.as_posix(),
                    "provider_symbol": spec.provider_symbol,
                    "sha256": sha256_bytes(raw),
                    "status_code": status,
                    "symbol": spec.symbol,
                    "weight": 1,
                }
            )
            print(f"completed {spec.symbol} time_series", flush=True)
        manifest = {
            "authentication": "authorization_header_redacted_not_serialized",
            "contract_sha256": sha256_file(contract_path),
            "responses": responses,
            "retrieved_at": _utc_now(),
            "review_id": contract["review_id"],
            "schema_version": MANIFEST_SCHEMA,
            "total_requests": len(responses),
            "total_weighted_credits": len(responses),
        }
        manifest_path = temp_root / "source-manifest.json"
        manifest_path.write_text(canonical_json(manifest), encoding="utf-8")
        temp_root.rename(output_root)
        return output_root / "source-manifest.json"
    except BaseException:
        shutil.rmtree(temp_root, ignore_errors=True)
        raise
    finally:
        api_key = ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the frozen LSE boundary clarification.")
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    args = parser.parse_args()
    try:
        manifest = run(args.contract, args.timeout_seconds)
    except TwelveDataAuditError as exc:
        parser.error(str(exc))
    print(f"source manifest written: {manifest.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
