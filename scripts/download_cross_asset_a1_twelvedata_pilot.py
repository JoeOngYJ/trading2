#!/usr/bin/env python3
"""Transactionally acquire the frozen, bounded Twelve Data A1 source pilot."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from trading_platform.cross_asset_twelvedata_audit import (
    MANIFEST_SCHEMA,
    TwelveDataAuditError,
    build_request_specs,
    canonical_json,
    load_contract,
    parse_response,
    sha256_bytes,
    sha256_file,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = (
    REPO_ROOT / "config/experiments/cross-asset-a1-twelvedata-economic-proxy-pilot-v2.json"
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _safe_error(exc: BaseException, secret: str) -> str:
    message = str(exc).replace(secret, "<redacted>") if secret else str(exc)
    return message.replace("Authorization", "<auth-header>")


def run(contract_path: Path, timeout_seconds: float) -> Path:
    contract = load_contract(contract_path)
    api_key = os.environ.get("TWELVEDATA_API_KEY", "")
    if not api_key.strip():
        raise TwelveDataAuditError("TWELVEDATA_API_KEY is required")
    specs = build_request_specs(contract)
    output_root = REPO_ROOT / contract["output"]["artifact_root"]
    if output_root.exists():
        raise TwelveDataAuditError("write-once Twelve Data pilot artifact root already exists")
    output_root.parent.mkdir(parents=True, exist_ok=True)
    temp_root = Path(tempfile.mkdtemp(prefix=".twelvedata-pilot-", dir=output_root.parent))
    raw_root = temp_root / "raw"
    raw_root.mkdir()
    responses: list[dict[str, object]] = []
    phase_1_started = time.monotonic()
    try:
        for spec in specs:
            if spec.phase == 2:
                minimum = contract["sources"]["twelvedata_grow"]["rate_limit_schedule"][1][
                    "minimum_seconds_after_phase_1_start"
                ]
                remaining = float(minimum) - (time.monotonic() - phase_1_started)
                if remaining > 0:
                    time.sleep(remaining)
            url = f"https://api.twelvedata.com{spec.path}?{urlencode(spec.persisted_parameters)}"
            request = Request(
                url,
                headers={
                    "Accept": "application/json",
                    "Authorization": f"apikey {api_key}",
                    "User-Agent": "trading-research-source-qualification/1.0",
                },
                method="GET",
            )
            try:
                with urlopen(request, timeout=timeout_seconds) as response:
                    status = int(response.status)
                    raw = response.read()
            except HTTPError as exc:
                raise TwelveDataAuditError(
                    f"provider request failed for {spec.symbol} {spec.endpoint}: HTTP {exc.code}"
                ) from exc
            except (URLError, TimeoutError, OSError) as exc:
                raise TwelveDataAuditError(
                    f"provider request failed for {spec.symbol} {spec.endpoint}: {_safe_error(exc, api_key)}"
                ) from exc
            if status != 200:
                raise TwelveDataAuditError(
                    f"provider request failed for {spec.symbol} {spec.endpoint}: HTTP {status}"
                )
            parse_response(raw, f"{spec.symbol} {spec.endpoint}")
            raw_path = raw_root / spec.filename
            raw_path.write_bytes(raw)
            relative = Path(contract["output"]["artifact_root"]) / "raw" / spec.filename
            responses.append(
                {
                    "bytes": len(raw),
                    "endpoint": spec.endpoint,
                    "parameters": dict(spec.persisted_parameters),
                    "path": relative.as_posix(),
                    "phase": spec.phase,
                    "sha256": sha256_bytes(raw),
                    "status_code": status,
                    "symbol": spec.symbol,
                    "weight": spec.weight,
                }
            )
        manifest = {
            "authentication": "authorization_header_redacted_not_serialized",
            "contract_sha256": sha256_file(contract_path),
            "pilot_id": contract["pilot_id"],
            "responses": responses,
            "retrieved_at": _utc_now(),
            "schema_version": MANIFEST_SCHEMA,
            "total_requests": len(responses),
            "total_weighted_credits": sum(int(item["weight"]) for item in responses),
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
    parser = argparse.ArgumentParser(description="Run the frozen Twelve Data A1 source pilot.")
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
