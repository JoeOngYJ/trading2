#!/usr/bin/env python3
"""Transactionally download the frozen GET-only OANDA A1 hourly history."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from trading_platform.cross_asset_oanda_hourly import (
    OandaHourlyError,
    SOURCE_SCHEMA,
    build_request_specs,
    canonical_json,
    load_contract,
    sha256_bytes,
    validate_runtime_identity,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = REPO_ROOT / "config/experiments/cross-asset-a1-oanda-hourly-history-v1.json"
DEFAULT_MANDATE = REPO_ROOT / "config/mandates/retail-cross-asset-research-v6.json"
DEFAULT_ENV = REPO_ROOT / ".env.local"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def read_env_file(path: Path, allowed: set[str]) -> dict[str, str]:
    if not path.is_file() or path.stat().st_mode & 0o077:
        raise OandaHourlyError("credential file is missing or is not mode 600")
    result = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() in allowed:
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
                value = value[1:-1]
            result[key.strip()] = value
    return result


def credentials(contract: Mapping[str, object], env_path: Path) -> tuple[str, str, str]:
    access = contract["source_access"]
    assert isinstance(access, Mapping)
    names = {
        str(access["account_id_environment_variable"]),
        str(access["api_token_environment_variable"]),
        str(access["api_url_environment_variable"]),
    }
    file_values = read_env_file(env_path, names)
    values = {name: os.environ.get(name) or file_values.get(name, "") for name in names}
    account = values[str(access["account_id_environment_variable"])]
    token = values[str(access["api_token_environment_variable"])]
    url = values[str(access["api_url_environment_variable"])]
    validate_runtime_identity(contract, url, account)
    if not token:
        raise OandaHourlyError("OANDA API token is missing")
    return url, account, token


def request_url(base: str, path_template: str, instrument: str, parameters: Mapping[str, str]) -> str:
    path = path_template.format(instrument=instrument)
    return f"{base}{path}?{urllib.parse.urlencode(parameters, safe=':/')}"


def get_bytes(url: str, token: str, timeout: int) -> tuple[int, bytes]:
    request = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Accept": "application/json",
            "Accept-Datetime-Format": "RFC3339",
            "Authorization": f"Bearer {token}",
            "User-Agent": "cross-asset-oanda-a1-hourly-source-audit/1",
        },
    )
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
                status = int(response.status)
                raw = response.read(64 * 1024 * 1024 + 1)
            if status != 200:
                raise OandaHourlyError(f"OANDA GET returned HTTP {status}")
            if len(raw) > 64 * 1024 * 1024:
                raise OandaHourlyError("OANDA response exceeded the frozen size ceiling")
            return status, raw
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code != 429 and not 500 <= exc.code < 600:
                raise OandaHourlyError(f"OANDA GET failed with HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            last_error = exc
        if attempt < 2:
            time.sleep(2**attempt)
    raise OandaHourlyError("OANDA GET failed after bounded retries") from last_error


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--mandate", type=Path, default=DEFAULT_MANDATE)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV)
    args = parser.parse_args()
    contract = load_contract(args.contract, args.mandate, REPO_ROOT)
    api_url, _account_id, token = credentials(contract, args.env_file)
    specs = build_request_specs(contract)
    artifact_root = REPO_ROOT / contract["output"]["artifact_root"]
    if artifact_root.exists():
        raise OandaHourlyError("refusing to replace immutable hourly artifact root")
    artifact_root.parent.mkdir(parents=True, exist_ok=True)
    timeout = int(contract["request_plan"]["request_timeout_seconds"])
    with tempfile.TemporaryDirectory(prefix=".oanda-hourly-a1-", dir=artifact_root.parent) as temporary:
        temporary_root = Path(temporary)
        raw_root = temporary_root / "raw"
        raw_root.mkdir()
        sources = []
        for index, spec in enumerate(specs, start=1):
            status, raw = get_bytes(
                request_url(api_url, spec.path_template, spec.instrument_id, spec.parameters),
                token,
                timeout,
            )
            try:
                payload = json.loads(raw)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise OandaHourlyError(f"invalid OANDA JSON for {spec.filename}") from exc
            if not isinstance(payload, dict):
                raise OandaHourlyError(f"non-object OANDA JSON for {spec.filename}")
            (raw_root / spec.filename).write_bytes(raw)
            sources.append(
                {
                    "bytes": len(raw),
                    "endpoint_template": spec.path_template,
                    "http_method": "GET",
                    "http_status": status,
                    "instrument_id": spec.instrument_id,
                    "parameters": dict(spec.parameters),
                    "path": f"raw/{spec.filename}",
                    "sha256": sha256_bytes(raw),
                }
            )
            if index % 16 == 0 or index == len(specs):
                print(f"downloaded {index}/{len(specs)} frozen hourly responses", flush=True)
        manifest = {
            "account_id_sha256": contract["source_access"]["account_id_sha256"],
            "api_base_url": contract["source_access"]["api_base_url"],
            "experiment_id": contract["experiment_id"],
            "retrieved_at": utc_now(),
            "schema_version": SOURCE_SCHEMA,
            "sources": sources,
        }
        (temporary_root / "source-manifest.json").write_text(canonical_json(manifest), encoding="utf-8")
        temporary_root.replace(artifact_root)
    print(f"committed {len(specs)} immutable GET responses")


if __name__ == "__main__":
    main()
