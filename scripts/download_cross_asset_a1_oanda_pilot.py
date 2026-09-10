#!/usr/bin/env python3
"""Download the bounded, GET-only OANDA A1 source pilot transactionally."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from trading_platform.cross_asset_oanda_audit import (
    SOURCE_MANIFEST_SCHEMA,
    OandaAuditError,
    build_request_specs,
    canonical_json,
    catalogue_names,
    load_contract,
    parse_json_bytes,
    sha256_bytes,
    validate_runtime_identity,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = REPO_ROOT / "config/experiments/cross-asset-a1-oanda-source-pilot-v1.json"
DEFAULT_MANDATE = REPO_ROOT / "config/mandates/retail-cross-asset-research-v5.json"
DEFAULT_ENV = REPO_ROOT / ".env.local"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def read_env_file(path: Path, allowed_names: set[str]) -> dict[str, str]:
    if not path.is_file():
        raise OandaAuditError(f"credential file does not exist: {path}")
    if path.stat().st_mode & 0o077:
        raise OandaAuditError("credential file must not be group- or world-readable")
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key not in allowed_names:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key] = value
    return values


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
    account_id = values[str(access["account_id_environment_variable"])]
    token = values[str(access["api_token_environment_variable"])]
    api_url = values[str(access["api_url_environment_variable"])]
    validate_runtime_identity(contract, api_url, account_id)
    if not token:
        raise OandaAuditError("OANDA API token is missing")
    return api_url, account_id, token


def get_bytes(url: str, token: str, timeout: int) -> tuple[int, bytes]:
    request = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Accept": "application/json",
            "Accept-Datetime-Format": "RFC3339",
            "Authorization": f"Bearer {token}",
            "User-Agent": "cross-asset-oanda-a1-source-audit/1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - frozen HTTPS host
            status = int(response.status)
            raw = response.read(64 * 1024 * 1024 + 1)
    except urllib.error.HTTPError as exc:
        raise OandaAuditError(f"OANDA GET failed with HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise OandaAuditError("OANDA GET failed before a response was received") from exc
    if status != 200:
        raise OandaAuditError(f"OANDA GET returned HTTP {status}")
    if len(raw) > 64 * 1024 * 1024:
        raise OandaAuditError("OANDA response exceeded the frozen size ceiling")
    return status, raw


def request_url(
    base_url: str,
    account_id: str,
    path_template: str,
    instrument_id: str | None,
    parameters: Mapping[str, str],
) -> str:
    path = path_template.format(accountID=account_id, instrument=instrument_id or "")
    query = urllib.parse.urlencode(parameters, safe=":/")
    return f"{base_url}{path}" + (f"?{query}" if query else "")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--mandate", type=Path, default=DEFAULT_MANDATE)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV)
    args = parser.parse_args()

    contract = load_contract(args.contract, args.mandate)
    api_url, account_id, token = credentials(contract, args.env_file)
    specs = build_request_specs(contract)
    artifact_root = REPO_ROOT / contract["output"]["artifact_root"]
    if artifact_root.exists():
        raise OandaAuditError("refusing to replace the immutable OANDA artifact root")
    artifact_root.parent.mkdir(parents=True, exist_ok=True)
    timeout = int(contract["request_plan"]["request_timeout_seconds"])

    with tempfile.TemporaryDirectory(prefix=".oanda-a1-", dir=artifact_root.parent) as temporary:
        temporary_root = Path(temporary)
        raw_root = temporary_root / "raw"
        raw_root.mkdir()
        sources = []

        catalogue_spec = specs[0]
        status, raw = get_bytes(
            request_url(
                api_url,
                account_id,
                catalogue_spec.path_template,
                None,
                catalogue_spec.parameters,
            ),
            token,
            timeout,
        )
        catalogue_payload = parse_json_bytes(raw, catalogue_spec.filename)
        available = catalogue_names(catalogue_payload)
        catalogue_path = raw_root / catalogue_spec.filename
        catalogue_path.write_bytes(raw)
        sources.append(
            {
                "bytes": len(raw),
                "endpoint_template": catalogue_spec.path_template,
                "http_method": "GET",
                "http_status": status,
                "instrument_id": None,
                "kind": catalogue_spec.kind,
                "parameters": {},
                "path": f"raw/{catalogue_spec.filename}",
                "sha256": sha256_bytes(raw),
            }
        )

        for spec in specs[1:]:
            if spec.instrument_id not in available:
                continue
            status, raw = get_bytes(
                request_url(
                    api_url,
                    account_id,
                    spec.path_template,
                    spec.instrument_id,
                    spec.parameters,
                ),
                token,
                timeout,
            )
            parse_json_bytes(raw, spec.filename)
            destination = raw_root / spec.filename
            destination.write_bytes(raw)
            sources.append(
                {
                    "bytes": len(raw),
                    "endpoint_template": spec.path_template,
                    "http_method": "GET",
                    "http_status": status,
                    "instrument_id": spec.instrument_id,
                    "kind": spec.kind,
                    "parameters": dict(spec.parameters),
                    "path": f"raw/{spec.filename}",
                    "sha256": sha256_bytes(raw),
                }
            )

        retrieved_at = utc_now()
        manifest = {
            "account_id_sha256": contract["source_access"]["account_id_sha256"],
            "api_base_url": contract["source_access"]["api_base_url"],
            "experiment_id": contract["experiment_id"],
            "retrieved_at": retrieved_at,
            "schema_version": SOURCE_MANIFEST_SCHEMA,
            "sources": sources,
        }
        (temporary_root / "source-manifest.json").write_text(
            canonical_json(manifest), encoding="utf-8"
        )
        temporary_root.rename(artifact_root)

    present = [instrument_id for instrument_id in (item["instrument_id"] for item in contract["candidate_instruments"]) if instrument_id in available]
    print(
        json.dumps(
            {
                "candidate_instruments_present": present,
                "decision": "oanda_source_bytes_acquired",
                "requests_completed": len(sources),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
