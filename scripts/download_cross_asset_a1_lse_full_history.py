#!/usr/bin/env python3
"""Transactionally download the frozen exact XLON history and action inventory."""

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

from trading_platform.cross_asset_a1_expansion import (
    A1ExpansionError,
    build_lse_request_specs,
    canonical_json,
    load_contract,
    sha256_file,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = REPO_ROOT / "config/experiments/cross-asset-a1-lse-futures-expansion-v1.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _safe_message(exc: BaseException, secret: str) -> str:
    return str(exc).replace(secret, "<redacted>").replace("Authorization", "<auth-header>")


def _parse(raw: bytes, label: str) -> None:
    import json

    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise A1ExpansionError(f"{label} response is not JSON") from exc
    if not isinstance(payload, dict):
        raise A1ExpansionError(f"{label} response must be an object")
    if payload.get("status") == "error" or "code" in payload and "message" in payload:
        raise A1ExpansionError(f"{label} provider returned an error payload")


def run(contract_path: Path, timeout_seconds: float) -> Path:
    contract = load_contract(contract_path, REPO_ROOT)
    acquisition = contract["lse_acquisition"]
    variable = acquisition["api_token_environment_variable"]
    api_key = os.environ.get(variable, "")
    if not api_key.strip():
        raise A1ExpansionError(f"{variable} is required")
    specs = build_lse_request_specs(contract)
    output_root = REPO_ROOT / acquisition["output_artifact_root"]
    if output_root.exists():
        raise A1ExpansionError("write-once LSE full-history artifact root already exists")
    output_root.parent.mkdir(parents=True, exist_ok=True)
    temp_root = Path(tempfile.mkdtemp(prefix=".lse-full-history-", dir=output_root.parent))
    raw_root = temp_root / "raw"
    raw_root.mkdir()
    offsets = {index + 1: value for index, value in enumerate(acquisition["phase_offsets_seconds"])}
    responses: list[dict[str, object]] = []
    started_at = _utc_now()
    started_clock = time.monotonic()
    try:
        for spec in specs:
            remaining = float(offsets[spec.phase]) - (time.monotonic() - started_clock)
            if remaining > 0:
                time.sleep(remaining)
            url = f"{acquisition['api_base_url']}{spec.path}?{urlencode(spec.parameters)}"
            request = Request(
                url,
                headers={
                    "Accept": "application/json",
                    "Authorization": f"apikey {api_key}",
                    "User-Agent": "trading-research-exact-xlon-history/1.0",
                },
                method="GET",
            )
            try:
                with urlopen(request, timeout=timeout_seconds) as response:
                    status = int(response.status)
                    raw = response.read()
            except HTTPError as exc:
                raise A1ExpansionError(
                    f"provider request failed for {spec.symbol} {spec.endpoint}: HTTP {exc.code}"
                ) from exc
            except (URLError, TimeoutError, OSError) as exc:
                raise A1ExpansionError(
                    f"provider request failed for {spec.symbol} {spec.endpoint}: "
                    f"{_safe_message(exc, api_key)}"
                ) from exc
            if status != 200:
                raise A1ExpansionError(
                    f"provider request failed for {spec.symbol} {spec.endpoint}: HTTP {status}"
                )
            _parse(raw, f"{spec.symbol} {spec.endpoint}")
            raw_path = raw_root / spec.filename
            raw_path.write_bytes(raw)
            responses.append(
                {
                    "bytes": len(raw),
                    "endpoint": spec.endpoint,
                    "parameters": dict(spec.parameters),
                    "path": (
                        Path(acquisition["output_artifact_root"]) / "raw" / spec.filename
                    ).as_posix(),
                    "phase": spec.phase,
                    "retrieved_at": _utc_now(),
                    "sha256": sha256_file(raw_path),
                    "status_code": status,
                    "symbol": spec.symbol,
                    "weight": spec.weight,
                }
            )
            print(f"completed {spec.symbol} {spec.endpoint}", flush=True)
        manifest = {
            "authentication": "authorization_header_redacted_not_serialized",
            "completed_at": _utc_now(),
            "contract_sha256": sha256_file(contract_path),
            "experiment_id": contract["experiment_id"],
            "responses": responses,
            "schema_version": "cross-asset-a1-exact-xlon-history-source-manifest-v1",
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    args = parser.parse_args()
    try:
        manifest = run(args.contract, args.timeout_seconds)
    except A1ExpansionError as exc:
        parser.error(str(exc))
    print(f"source manifest written: {manifest.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
