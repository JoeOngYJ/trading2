#!/usr/bin/env python3
"""Download the bounded conversion-only GBP/USD H1 source transactionally."""

from __future__ import annotations

import argparse
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from scripts.download_cross_asset_a1_oanda_hourly import credentials, get_bytes, request_url
from trading_platform.cross_asset_gbp_conversion import (
    SOURCE_SCHEMA,
    build_request_specs,
    load_contract,
)
from trading_platform.cross_asset_oanda_hourly import OandaHourlyError, canonical_json, sha256_bytes


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "config/experiments/cross-asset-a2-gbp-conversion-source-v1.json"
DEFAULT_MANDATE = ROOT / "config/mandates/retail-cross-asset-research-v7.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--mandate", type=Path, default=DEFAULT_MANDATE)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env.local")
    args = parser.parse_args()
    contract = load_contract(args.contract, args.mandate, ROOT)
    api_url, _account_id, token = credentials(contract, args.env_file)
    specs = build_request_specs(contract, ROOT)
    artifact_root = ROOT / contract["output"]["artifact_root"]
    if artifact_root.exists():
        raise OandaHourlyError("refusing to replace immutable conversion source root")
    artifact_root.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".gbp-conversion-", dir=artifact_root.parent) as temporary:
        temp = Path(temporary)
        raw_root = temp / "raw"
        raw_root.mkdir()
        sources = []
        for index, spec in enumerate(specs, start=1):
            status, raw = get_bytes(
                request_url(api_url, spec["path_template"], "GBP_USD", spec["parameters"]),
                token,
                int(contract["request_plan"]["request_timeout_seconds"]),
            )
            if not isinstance(json.loads(raw), dict):
                raise OandaHourlyError("conversion response is not a JSON object")
            (raw_root / spec["filename"]).write_bytes(raw)
            sources.append(
                {
                    "bytes": len(raw),
                    "endpoint_template": spec["path_template"],
                    "http_method": "GET",
                    "http_status": status,
                    "instrument_id": "GBP_USD",
                    "parameters": spec["parameters"],
                    "path": f"raw/{spec['filename']}",
                    "sha256": sha256_bytes(raw),
                }
            )
            if index % 8 == 0:
                print(f"downloaded {index}/32 conversion responses", flush=True)
        manifest = {
            "account_id_sha256": contract["source_access"]["account_id_sha256"],
            "api_base_url": contract["source_access"]["api_base_url"],
            "experiment_id": contract["experiment_id"],
            "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "schema_version": SOURCE_SCHEMA,
            "sources": sources,
        }
        (temp / "source-manifest.json").write_text(canonical_json(manifest), encoding="utf-8")
        temp.replace(artifact_root)


if __name__ == "__main__":
    main()
