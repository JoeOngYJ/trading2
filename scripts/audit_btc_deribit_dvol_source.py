#!/usr/bin/env python3
"""Run the bounded, unauthenticated Deribit DVOL source pilot."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urlparse
from urllib.error import HTTPError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "research/btc/contracts/btc-deribit-dvol-source-pilot-v2.json"
DAY_MS = 86_400_000


class DvolPilotError(ValueError):
    pass


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def load_contract(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    value = json.loads(raw)
    if raw != canonical_json(value):
        raise DvolPilotError("contract is not canonical indented sorted JSON")
    if value.get("status") != "frozen_before_any_request":
        raise DvolPilotError("DVOL contract is not frozen")
    if value.get("action_boundary", {}).get("risk_model_input_approval_allowed") is not False:
        raise DvolPilotError("pilot can approve a risk-model input")
    return value


def fetch(url: str, allowed_hosts: set[str]) -> tuple[int, bytes]:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in allowed_hosts:
        raise DvolPilotError(f"request outside frozen host boundary: {url}")
    request = Request(url, headers={"User-Agent": "btc-dvol-offline-source-pilot/1"})
    try:
        with urlopen(request, timeout=60) as response:
            return int(response.status), response.read()
    except HTTPError as exc:
        return int(exc.code), exc.read()


def audit_rows(rows: object, request_spec: dict) -> dict:
    failures: list[str] = []
    if not isinstance(rows, list):
        return {"failures": ["result_data_not_a_list"], "rows": 0}
    parsed: list[tuple[int, float, float, float, float]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, list) or len(row) != 5:
            failures.append(f"row_{index}_shape")
            continue
        try:
            timestamp = int(row[0])
            open_value, high, low, close = (float(value) for value in row[1:])
        except (TypeError, ValueError):
            failures.append(f"row_{index}_type")
            continue
        values = (open_value, high, low, close)
        if any(not math.isfinite(value) or value <= 0 for value in values):
            failures.append(f"row_{index}_nonpositive_or_nonfinite")
        if low > min(open_value, close) or high < max(open_value, close) or low > high:
            failures.append(f"row_{index}_ohlc_order")
        parsed.append((timestamp, open_value, high, low, close))

    timestamps = [row[0] for row in parsed]
    duplicate_count = len(timestamps) - len(set(timestamps))
    nonincreasing = sum(later <= earlier for earlier, later in zip(timestamps, timestamps[1:]))
    gaps = [later - earlier for earlier, later in zip(timestamps, timestamps[1:])]
    non_daily_gaps = [gap for gap in gaps if gap != DAY_MS]
    start = int(request_spec["start_timestamp"])
    end = int(request_spec["end_timestamp"])
    out_of_bounds = sum(timestamp < start or timestamp > end for timestamp in timestamps)
    if len(parsed) != 15:
        failures.append("row_count_not_15")
    if duplicate_count:
        failures.append("duplicate_timestamps")
    if nonincreasing:
        failures.append("timestamps_not_strictly_increasing")
    if non_daily_gaps:
        failures.append("non_daily_timestamp_gap")
    if out_of_bounds:
        failures.append("timestamp_outside_request")
    if timestamps and (timestamps[0] - start >= DAY_MS or end - timestamps[-1] >= DAY_MS):
        failures.append("request_edge_not_covered")
    return {
        "duplicate_timestamps": duplicate_count,
        "failures": sorted(set(failures)),
        "first_timestamp": timestamps[0] if timestamps else None,
        "last_timestamp": timestamps[-1] if timestamps else None,
        "non_daily_gap_count": len(non_daily_gaps),
        "out_of_bounds_rows": out_of_bounds,
        "rows": len(parsed),
    }


def run(contract_path: Path, output: Path) -> dict:
    contract = load_contract(contract_path)
    if output.exists():
        raise FileExistsError(output)
    output.mkdir(parents=True)
    raw_dir = output / "raw"
    raw_dir.mkdir()
    allowed_hosts = set(contract["allowed_hosts"])
    retrieved_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    documentation_records: list[dict] = []
    for evidence in contract["documentation_evidence"]:
        status, raw = fetch(evidence["url"], allowed_hosts)
        path = raw_dir / f"{evidence['evidence_id']}.html"
        path.write_bytes(raw)
        lowered = raw.decode("utf-8", errors="ignore").lower()
        missing = [phrase for phrase in evidence["required_phrases"] if phrase.lower() not in lowered]
        documentation_records.append(
            {
                "evidence_id": evidence["evidence_id"],
                "http_status": status,
                "missing_required_phrases": missing,
                "path": str(path.relative_to(ROOT)),
                "sha256": sha256_bytes(raw),
                "url": evidence["url"],
            }
        )

    request_records: list[dict] = []
    endpoint = "https://www.deribit.com" + contract["endpoint"]["path"]
    for spec in contract["data_requests"]:
        query = urlencode(
            {
                "currency": spec["currency"],
                "start_timestamp": spec["start_timestamp"],
                "end_timestamp": spec["end_timestamp"],
                "resolution": spec["resolution"],
            }
        )
        url = endpoint + "?" + query
        status, raw = fetch(url, allowed_hosts)
        path = raw_dir / f"{spec['request_id']}.json"
        path.write_bytes(raw)
        parse_error = None
        jsonrpc_error = None
        audit = {"failures": ["response_not_parsed"], "rows": 0}
        try:
            payload = json.loads(raw)
            jsonrpc_error = payload.get("error") if isinstance(payload, dict) else "non_object_response"
            result = payload.get("result", {}) if isinstance(payload, dict) else {}
            audit = audit_rows(result.get("data"), spec) if isinstance(result, dict) else audit
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            parse_error = type(exc).__name__
        request_records.append(
            {
                "audit": audit,
                "http_status": status,
                "jsonrpc_error": jsonrpc_error,
                "parse_error": parse_error,
                "path": str(path.relative_to(ROOT)),
                "request_id": spec["request_id"],
                "sha256": sha256_bytes(raw),
                "url": url,
            }
        )

    documentation_gate = all(
        item["http_status"] == 200 and not item["missing_required_phrases"]
        for item in documentation_records
    )
    response_gate = all(
        item["http_status"] == 200
        and item["parse_error"] is None
        and item["jsonrpc_error"] is None
        and not item["audit"]["failures"]
        for item in request_records
    )
    technical_gate = documentation_gate and response_gate
    report = {
        "actionable_arm_id": "no_trade",
        "credentials_used": False,
        "decision": (
            "technical_pilot_passed_historical_use_blocked"
            if technical_gate
            else "source_pilot_rejected"
        ),
        "documentation_gate_passed": documentation_gate,
        "experiment_id": contract["experiment_id"],
        "full_historical_risk_model_input_approved": False,
        "historical_use_blockers": [
            "complete_history_not_tested",
            "effective_dated_methodology_archive_not_established",
            "historical_publication_and_revision_semantics_not_established",
            "private_research_retention_rights_not_established",
        ],
        "no_strategy_feature_label_return_pnl_regime_or_risk_model_computed": True,
        "request_gate_passed": response_gate,
        "technical_pilot_gate_passed": technical_gate,
    }
    source_manifest = {
        "contract_path": str(contract_path.relative_to(ROOT)),
        "contract_sha256": sha256_path(contract_path),
        "credentials_used": False,
        "documentation": documentation_records,
        "experiment_id": contract["experiment_id"],
        "requests": request_records,
        "retrieved_at": retrieved_at,
        "schema_version": "btc-deribit-dvol-source-manifest-v1",
    }
    report_path = output / "audit-report.json"
    source_path = output / "source-manifest.json"
    report_path.write_text(canonical_json(report), encoding="utf-8")
    source_path.write_text(canonical_json(source_manifest), encoding="utf-8")
    files = [*sorted(raw_dir.iterdir()), report_path, source_path]
    evidence = {
        "experiment_id": contract["experiment_id"],
        "files": [
            {
                "bytes": path.stat().st_size,
                "path": str(path.relative_to(ROOT)),
                "sha256": sha256_path(path),
            }
            for path in files
        ],
        "schema_version": "btc-deribit-dvol-evidence-manifest-v1",
    }
    evidence_path = output / "evidence-manifest.json"
    evidence_path.write_text(canonical_json(evidence), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "artifacts/agent-level-experiment/btc-focused/deribit-dvol-source-pilot-v2",
    )
    args = parser.parse_args()
    try:
        report = run(args.contract.resolve(), args.output.resolve())
    except Exception as exc:
        print(f"DVOL pilot failed closed: {exc}", file=sys.stderr)
        return 1
    print(canonical_json(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
