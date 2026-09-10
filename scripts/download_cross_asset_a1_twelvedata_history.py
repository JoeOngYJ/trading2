#!/usr/bin/env python3
"""Transactionally download the frozen Twelve Data 2008-2025 history snapshot."""

from __future__ import annotations

import argparse
import os
import shutil
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from trading_platform.cross_asset_twelvedata_audit import canonical_json, parse_response, sha256_bytes, sha256_file
from trading_platform.cross_asset_twelvedata_history import (
    MANIFEST_SCHEMA,
    TwelveDataHistoryError,
    build_request_specs,
    load_contract,
    phase_offsets,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = REPO_ROOT / "config/experiments/cross-asset-a1-twelvedata-full-history-v2.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _safe_error(exc: BaseException, secret: str) -> str:
    return str(exc).replace(secret, "<redacted>").replace("Authorization", "<auth-header>")


def run(contract_path: Path, timeout_seconds: float) -> Path:
    contract, _, _ = load_contract(contract_path, REPO_ROOT)
    api_key = os.environ.get("TWELVEDATA_API_KEY", "")
    if not api_key.strip():
        raise TwelveDataHistoryError("TWELVEDATA_API_KEY is required")
    specs = build_request_specs(contract)
    offsets = phase_offsets(contract)
    output_root = REPO_ROOT / contract["output"]["artifact_root"]
    if output_root.exists():
        raise TwelveDataHistoryError("write-once full-history artifact root already exists")
    output_root.parent.mkdir(parents=True, exist_ok=True)
    temp_root = Path(tempfile.mkdtemp(prefix=".twelvedata-history-", dir=output_root.parent))
    raw_root = temp_root / "raw"
    raw_root.mkdir()
    responses: list[dict[str, object]] = []
    started_at = _utc_now()
    phase_1_started = time.monotonic()
    completed_phases: set[int] = set()
    try:
        for spec in specs:
            remaining = float(offsets[spec.phase]) - (time.monotonic() - phase_1_started)
            if remaining > 0:
                time.sleep(remaining)
            url = f"https://api.twelvedata.com{spec.path}?{urlencode(spec.parameters)}"
            request = Request(
                url,
                headers={
                    "Accept": "application/json",
                    "Authorization": f"apikey {api_key}",
                    "User-Agent": "trading-research-history-qualification/1.0",
                },
                method="GET",
            )
            try:
                with urlopen(request, timeout=timeout_seconds) as response:
                    status = int(response.status)
                    raw = response.read()
            except HTTPError as exc:
                raise TwelveDataHistoryError(
                    f"provider request failed for {spec.symbol} {spec.endpoint}: HTTP {exc.code}"
                ) from exc
            except (URLError, TimeoutError, OSError) as exc:
                raise TwelveDataHistoryError(
                    f"provider request failed for {spec.symbol} {spec.endpoint}: {_safe_error(exc, api_key)}"
                ) from exc
            if status != 200:
                raise TwelveDataHistoryError(
                    f"provider request failed for {spec.symbol} {spec.endpoint}: HTTP {status}"
                )
            try:
                parse_response(raw, f"{spec.symbol} {spec.endpoint}")
            except Exception as exc:
                raise TwelveDataHistoryError(str(exc)) from exc
            raw_path = raw_root / spec.filename
            raw_path.write_bytes(raw)
            relative = Path(contract["output"]["artifact_root"]) / "raw" / spec.filename
            responses.append(
                {
                    "bytes": len(raw),
                    "endpoint": spec.endpoint,
                    "parameters": dict(spec.parameters),
                    "path": relative.as_posix(),
                    "phase": spec.phase,
                    "retrieved_at": _utc_now(),
                    "sha256": sha256_bytes(raw),
                    "status_code": status,
                    "symbol": spec.symbol,
                    "weight": spec.weight,
                }
            )
            if spec.phase not in completed_phases and not any(
                later.phase == spec.phase for later in specs[len(responses):]
            ):
                completed_phases.add(spec.phase)
                print(f"phase {spec.phase}/9 committed to transaction buffer", flush=True)
        manifest = {
            "authentication": "authorization_header_redacted_not_serialized",
            "completed_at": _utc_now(),
            "contract_sha256": sha256_file(contract_path),
            "experiment_id": contract["experiment_id"],
            "responses": responses,
            "schema_version": MANIFEST_SCHEMA,
            "started_at": started_at,
            "total_requests": len(responses),
            "total_weighted_credits": sum(int(item["weight"]) for item in responses),
        }
        (temp_root / "source-manifest.json").write_text(canonical_json(manifest), encoding="utf-8")
        temp_root.rename(output_root)
        return output_root / "source-manifest.json"
    except BaseException:
        shutil.rmtree(temp_root, ignore_errors=True)
        raise
    finally:
        api_key = ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Download the frozen Twelve Data full history.")
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    args = parser.parse_args()
    try:
        manifest = run(args.contract, args.timeout_seconds)
    except TwelveDataHistoryError as exc:
        parser.error(str(exc))
    print(f"source manifest written: {manifest.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
