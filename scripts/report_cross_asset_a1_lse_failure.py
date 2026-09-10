#!/usr/bin/env python3
"""Write the immutable comprehensive quality inventory for the rejected XLON run."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from trading_platform.cross_asset_a1_expansion import (
    canonical_json,
    canonical_json_line,
    load_contract,
    sha256_file,
)
from trading_platform.cross_asset_lse_history import load_source_manifest
from trading_platform.cross_asset_xlon_calendar import load_calendar


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = REPO_ROOT / "config/experiments/cross-asset-a1-lse-futures-expansion-v1.json"


def row_digest(row: dict) -> str:
    return hashlib.sha256(canonical_json_line(row).encode("utf-8")).hexdigest()


def main() -> None:
    contract = load_contract(CONTRACT_PATH, REPO_ROOT)
    output_root = REPO_ROOT / contract["lse_acquisition"]["output_artifact_root"]
    failure_path = output_root / "failure-report.json"
    inventory_path = output_root / "quality-inventory.json"
    evidence_path = output_root / "failure-evidence-manifest.json"
    if any(path.exists() for path in (failure_path, inventory_path, evidence_path)):
        raise SystemExit("write-once XLON failure evidence already exists")
    source_path = output_root / "source-manifest.json"
    source = load_source_manifest(source_path, CONTRACT_PATH, contract, REPO_ROOT)
    calendar = load_calendar(
        REPO_ROOT / contract["xlon_calendar"]["path"],
        REPO_ROOT / "config/research/xlon-calendar-evidence-v1.json",
        REPO_ROOT,
    )
    response_by_key = {(item["symbol"], item["endpoint"]): item for item in source["responses"]}
    reports: list[dict] = []
    for instrument in contract["listed_funds"]:
        symbol = instrument["symbol"]
        response = response_by_key[(symbol, "time_series")]
        payload = json.loads((REPO_ROOT / response["path"]).read_text(encoding="utf-8"))
        values = payload.get("values", [])
        rows_by_date: dict[str, list[dict]] = defaultdict(list)
        for row in values:
            rows_by_date[str(row.get("datetime"))].append(row)
        expected_sessions = {
            item.session_date: item
            for item in calendar["sessions"]
            if instrument["usable_start"] <= item.session_date <= instrument["usable_end"]
        }
        duplicates = []
        for session, rows in sorted(rows_by_date.items()):
            if len(rows) > 1:
                digests = sorted(row_digest(row) for row in rows)
                duplicates.append(
                    {
                        "count": len(rows),
                        "identical_rows": len(set(digests)) == 1,
                        "row_sha256": digests,
                        "session": session,
                    }
                )
        actual = set(rows_by_date)
        missing = sorted(set(expected_sessions) - actual)
        actions = {}
        for endpoint in ("dividends", "splits"):
            action_response = response_by_key[(symbol, endpoint)]
            action_payload = json.loads(
                (REPO_ROOT / action_response["path"]).read_text(encoding="utf-8")
            )
            key = "ex_date" if endpoint == "dividends" else "date"
            dates = [str(row.get(key)) for row in action_payload.get(endpoint, [])]
            actions[endpoint] = {
                "duplicate_dates": sorted(day for day, count in Counter(dates).items() if count > 1),
                "rows": len(dates),
            }
        reports.append(
            {
                "action_inventory": actions,
                "duplicate_dates": duplicates,
                "duplicate_session_count": len(duplicates),
                "expected_sessions": len(expected_sessions),
                "missing_half_days": [day for day in missing if expected_sessions[day].half_day],
                "missing_sessions": missing,
                "off_calendar_sessions": sorted(actual - set(expected_sessions)),
                "raw_rows": len(values),
                "symbol": symbol,
                "unique_sessions": len(actual),
            }
        )
    inventory = {
        "calendar_id": calendar["calendar_id"],
        "contract_sha256": sha256_file(CONTRACT_PATH),
        "decision": "exact_lse_full_history_rejected",
        "experiment_id": contract["experiment_id"],
        "instruments": reports,
        "schema_version": "cross-asset-a1-exact-xlon-history-quality-inventory-v1",
        "source_manifest_sha256": sha256_file(source_path),
    }
    inventory_path.write_text(canonical_json(inventory), encoding="utf-8")
    failure = {
        "a1_stage_passed": False,
        "accepted_strategy_arms": [],
        "actionable_arm_id": "no_trade",
        "approved_execution_instruments": [],
        "decision": "exact_lse_full_history_rejected",
        "experiment_id": contract["experiment_id"],
        "failed_gates": [
            "duplicate_session_rows",
            "complete_expected_session_coverage",
            "issuer_action_reconciliation",
            "effective_dated_costs",
            "futures_source_and_history"
        ],
        "first_fail_closed_error": "SWDA contains duplicate session 2014-12-19",
        "quality_inventory_path": str(inventory_path.relative_to(REPO_ROOT)),
        "quality_inventory_sha256": sha256_file(inventory_path),
        "replacement_experiment_id": None,
        "safety": {
            "economic_metrics_computed": False,
            "partial_ob0_accessed": False,
            "pnl_computed": False,
            "protected_services_accessed": False,
            "returns_computed": False,
            "sealed_2026_accessed": False,
            "strategy_signals_generated": False
        },
        "schema_version": "cross-asset-a1-exact-xlon-history-failure-v1"
    }
    failure_path.write_text(canonical_json(failure), encoding="utf-8")
    evidence = {
        "artifacts": [
            {"path": str(failure_path.relative_to(REPO_ROOT)), "sha256": sha256_file(failure_path)},
            {"path": str(inventory_path.relative_to(REPO_ROOT)), "sha256": sha256_file(inventory_path)},
            {"path": str(source_path.relative_to(REPO_ROOT)), "sha256": sha256_file(source_path)}
        ],
        "contract_sha256": sha256_file(CONTRACT_PATH),
        "decision": "exact_lse_full_history_rejected",
        "experiment_id": contract["experiment_id"],
        "schema_version": "cross-asset-a1-exact-xlon-history-failure-evidence-v1"
    }
    evidence_path.write_text(canonical_json(evidence), encoding="utf-8")
    print(f"failure evidence written: {evidence_path.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
