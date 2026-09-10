#!/usr/bin/env python3
"""Transactionally download the frozen Twelve Data A1 v3 recovery windows."""

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
from trading_platform.cross_asset_twelvedata_history import TwelveDataHistoryError
from trading_platform.cross_asset_twelvedata_recovery import MANIFEST_SCHEMA, build_request_specs, load_contract, phase_offsets


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "config/experiments/cross-asset-a1-twelvedata-recovery-v3.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def run(contract_path: Path, timeout_seconds: float = 60.0) -> Path:
    contract, _, _ = load_contract(contract_path, ROOT)
    token = os.environ.get("TWELVEDATA_API_KEY", "")
    if not token.strip():
        raise TwelveDataHistoryError("TWELVEDATA_API_KEY is required")
    specs = build_request_specs(contract); offsets = phase_offsets(contract)
    output = ROOT / contract["output"]["artifact_root"]
    if output.exists():
        raise TwelveDataHistoryError("write-once v3 artifact root already exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=".twelvedata-recovery-", dir=output.parent)); raw_root = temp / "raw"; raw_root.mkdir()
    responses: list[dict[str, object]] = []; started = _now(); clock = time.monotonic(); completed: set[int] = set()
    try:
        for index, spec in enumerate(specs):
            delay = offsets[spec.phase] - (time.monotonic() - clock)
            if delay > 0: time.sleep(delay)
            url = f"https://api.twelvedata.com{spec.path}?{urlencode(spec.parameters)}"
            request = Request(url, headers={"Accept": "application/json", "Authorization": f"apikey {token}", "User-Agent": "trading-research-a1-recovery/1.0"}, method="GET")
            try:
                with urlopen(request, timeout=timeout_seconds) as response:
                    status = int(response.status); raw = response.read()
            except HTTPError as exc:
                raise TwelveDataHistoryError(f"provider request failed for {spec.symbol} {spec.endpoint} {spec.window_id}: HTTP {exc.code}") from exc
            except (URLError, TimeoutError, OSError) as exc:
                safe = str(exc).replace(token, "<redacted>")
                raise TwelveDataHistoryError(f"provider request failed for {spec.symbol} {spec.endpoint} {spec.window_id}: {safe}") from exc
            if status != 200: raise TwelveDataHistoryError(f"unexpected provider status {status}")
            parse_response(raw, f"{spec.symbol} {spec.endpoint} {spec.window_id}")
            path = raw_root / spec.filename; path.write_bytes(raw)
            responses.append({"bytes": len(raw), "endpoint": spec.endpoint, "parameters": dict(spec.parameters), "path": (Path(contract["output"]["artifact_root"]) / "raw" / spec.filename).as_posix(), "phase": spec.phase, "retrieved_at": _now(), "sha256": sha256_bytes(raw), "status_code": status, "symbol": spec.symbol, "weight": spec.weight, "window_id": spec.window_id})
            if spec.phase not in completed and not any(item.phase == spec.phase for item in specs[index + 1:]):
                completed.add(spec.phase); print(f"phase {spec.phase}/13 committed to transaction buffer", flush=True)
        manifest = {"authentication": "authorization_header_redacted_not_serialized", "completed_at": _now(), "contract_sha256": sha256_file(contract_path), "experiment_id": contract["experiment_id"], "responses": responses, "schema_version": MANIFEST_SCHEMA, "started_at": started, "total_requests": len(responses), "total_weighted_credits": sum(int(item["weight"]) for item in responses)}
        (temp / "source-manifest.json").write_text(canonical_json(manifest), encoding="utf-8"); temp.rename(output)
        return output / "source-manifest.json"
    except BaseException:
        shutil.rmtree(temp, ignore_errors=True); raise
    finally:
        token = ""


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT); parser.add_argument("--timeout-seconds", type=float, default=60.0); args = parser.parse_args()
    try: manifest = run(args.contract, args.timeout_seconds)
    except TwelveDataHistoryError as exc: parser.error(str(exc))
    print(f"source manifest written: {manifest.relative_to(ROOT)}")


if __name__ == "__main__": main()
