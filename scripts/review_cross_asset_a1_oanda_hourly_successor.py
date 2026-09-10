#!/usr/bin/env python3
"""Build the no-download OANDA hourly v2 availability-mask successor."""

from __future__ import annotations

import argparse
import json
import tempfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from trading_platform.cross_asset_oanda_hourly import (
    INSTRUMENT_IDS,
    OandaHourlyError,
    canonical_json,
    canonical_json_line,
    sha256_file,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = REPO_ROOT / "config/experiments/cross-asset-a1-oanda-hourly-history-v2.json"
BASE_ROOT = REPO_ROOT / "artifacts/agent-level-experiment/cross-asset/a1-oanda-hourly-history-v1"
SUCCESSOR_SCHEMA = "cross-asset-a1-oanda-hourly-history-amendment-v1"
SUCCESSOR_ID = "cross-asset-a1-oanda-hourly-history-v2"


def load_canonical(path: Path, label: str) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
        value = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OandaHourlyError(f"cannot read {label}") from exc
    if not isinstance(value, dict) or raw != canonical_json(value):
        raise OandaHourlyError(f"{label} must be canonical JSON")
    return value


def repo_file(raw: Any) -> Path:
    if not isinstance(raw, str) or Path(raw).is_absolute():
        raise OandaHourlyError("successor evidence path must be repository-relative")
    root = REPO_ROOT.resolve(strict=True)
    try:
        path = (root / raw).resolve(strict=True)
        path.relative_to(root)
    except (OSError, ValueError) as exc:
        raise OandaHourlyError("invalid successor evidence path") from exc
    if not path.is_file():
        raise OandaHourlyError("successor evidence path is not a file")
    return path


def validate_contract(path: Path) -> dict[str, Any]:
    value = load_canonical(path, "hourly successor contract")
    if (value.get("schema_version"), value.get("experiment_id"), value.get("status")) != (
        SUCCESSOR_SCHEMA,
        SUCCESSOR_ID,
        "frozen",
    ):
        raise OandaHourlyError("unexpected hourly successor")
    if value.get("supersedes") != "cross-asset-a1-oanda-hourly-history-v1":
        raise OandaHourlyError("hourly successor lineage changed")
    expected_changes = {
        "candidate_pass_requires_complete_session_days_at_least": 3000,
        "candidate_pass_requires_history_edges_and_no_gap_over_hours": 168,
        "every_incomplete_session_date_disposition": "no_trade",
        "incomplete_session_fraction_is_reported_not_a_source_rejection_gate": True,
        "new_provider_requests_allowed": False,
        "output_artifact_root": "artifacts/agent-level-experiment/cross-asset/a1-oanda-hourly-history-v2",
        "price_rows_may_be_changed_or_filled": False,
        "raw_and_normalized_predecessor_reuse_required": True,
    }
    if value.get("changes_from_predecessor") != expected_changes:
        raise OandaHourlyError("hourly successor changes are not the frozen no-download correction")
    records = {"base_contract": value["base_contract"], **value["frozen_predecessor_evidence"]}
    for label, record in records.items():
        evidence_path = repo_file(record.get("path"))
        if sha256_file(evidence_path) != record.get("sha256"):
            raise OandaHourlyError(f"hourly successor {label} checksum changed")
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    args = parser.parse_args()
    successor = validate_contract(args.contract)
    base_contract = load_canonical(repo_file(successor["base_contract"]["path"]), "base contract")
    predecessor = load_canonical(
        repo_file(successor["frozen_predecessor_evidence"]["audit_report"]["path"]),
        "predecessor audit",
    )
    evidence = load_canonical(
        repo_file(successor["frozen_predecessor_evidence"]["evidence_manifest"]["path"]),
        "predecessor evidence",
    )
    if predecessor.get("decision") != "a1_hourly_source_qualification_rejected" or predecessor.get(
        "passed_candidate_count"
    ) != 2:
        raise OandaHourlyError("hourly predecessor is not the frozen two-pass rejection")
    if evidence.get("returns_or_pnl_computed") is not False or evidence.get("sealed_2026_price_accessed") is not False:
        raise OandaHourlyError("hourly predecessor violated the source-only boundary")
    normalized_records = {
        Path(record["path"]).name: record
        for record in evidence.get("artifacts", ())
        if "/normalized/" in str(record.get("path", ""))
    }
    if len(normalized_records) != len(INSTRUMENT_IDS):
        raise OandaHourlyError("hourly predecessor normalized lineage is incomplete")

    artifact_root = REPO_ROOT / successor["changes_from_predecessor"]["output_artifact_root"]
    if artifact_root.exists():
        raise OandaHourlyError("refusing to replace immutable hourly successor root")
    artifact_root.parent.mkdir(parents=True, exist_ok=True)
    candidate_map = {item["instrument_id"]: item for item in base_contract["candidate_instruments"]}
    predecessor_map = {item["instrument_id"]: item for item in predecessor["instrument_results"]}
    successor_results = []
    with tempfile.TemporaryDirectory(prefix=".oanda-hourly-v2-", dir=artifact_root.parent) as temporary:
        temporary_root = Path(temporary)
        masks_root = temporary_root / "availability"
        masks_root.mkdir()
        mask_records = []
        for instrument in INSTRUMENT_IDS:
            candidate = candidate_map[instrument]
            profile = base_contract["session_profiles"][candidate["session_profile"]]
            required = set(profile["local_candle_start_hours"])
            zone = ZoneInfo(profile["timezone"])
            base_path = BASE_ROOT / "normalized" / f"{instrument.casefold()}-h1.jsonl"
            record = normalized_records[base_path.name]
            if sha256_file(base_path) != record.get("sha256"):
                raise OandaHourlyError(f"normalized predecessor checksum changed: {instrument}")
            dates: dict[str, set[int]] = defaultdict(set)
            with base_path.open(encoding="utf-8") as rows:
                for line in rows:
                    row = json.loads(line)
                    observed = datetime.fromisoformat(row["observed_at"].replace("Z", "+00:00")).astimezone(zone)
                    if observed.hour in required:
                        dates[observed.date().isoformat()].add(observed.hour)
            mask_path = masks_root / f"{instrument.casefold()}-availability.jsonl"
            complete = incomplete = 0
            with mask_path.open("w", encoding="utf-8", newline="\n") as output:
                for local_date, present in sorted(dates.items()):
                    is_complete = present == required
                    complete += int(is_complete)
                    incomplete += int(not is_complete)
                    output.write(
                        canonical_json_line(
                            {
                                "disposition": "eligible" if is_complete else "no_trade",
                                "instrument_id": instrument,
                                "local_date": local_date,
                                "missing_local_candle_start_hours": sorted(required - present),
                                "session_profile": candidate["session_profile"],
                            }
                        )
                        + "\n"
                    )
            prior = predecessor_map[instrument]
            if (complete, incomplete) != (
                prior["complete_session_days"],
                prior["incomplete_observed_session_days"],
            ):
                raise OandaHourlyError(f"availability mask count differs from predecessor: {instrument}")
            allowed_failure = ["incomplete_observed_session_fraction_exceeds_gate"]
            if prior["failures"] not in ([], allowed_failure):
                raise OandaHourlyError(f"predecessor has a non-correctable failure: {instrument}")
            if complete < 3000 or prior["outage_gaps"] or int(prior["maximum_observed_gap_hours"]) > 168:
                raise OandaHourlyError(f"successor quality gates fail: {instrument}")
            updated = dict(prior)
            final_mask_path = artifact_root / "availability" / mask_path.name
            updated.update(
                {
                    "availability_mask_path": str(final_mask_path.relative_to(REPO_ROOT)),
                    "decision": "candidate_pass_with_incomplete_sessions_no_trade",
                    "failures": [],
                    "predecessor_decision": prior["decision"],
                    "predecessor_failures": prior["failures"],
                }
            )
            successor_results.append(updated)
            mask_records.append(
                {
                    "bytes": mask_path.stat().st_size,
                    "path": str(final_mask_path.relative_to(REPO_ROOT)),
                    "sha256": sha256_file(mask_path),
                }
            )
        report = {
            "a1_stage_passed": True,
            "accepted_strategy_arms": [],
            "actionable_arm_id": "no_trade",
            "approved_execution_instruments": [],
            "decision": "a1_hourly_source_qualification_passed_with_no_trade_masks",
            "experiment_id": SUCCESSOR_ID,
            "instrument_results": successor_results,
            "new_provider_requests": 0,
            "passed_candidate_count": len(successor_results),
            "price_rows_changed_or_filled": False,
            "qualified_for_strategy_evaluation": True,
            "returns_or_pnl_computed": False,
            "schema_version": "cross-asset-a1-oanda-hourly-successor-audit-v1",
            "sealed_2026_price_accessed": False,
        }
        report_path = temporary_root / "audit-report.json"
        report_path.write_text(canonical_json(report), encoding="utf-8")
        artifact_records = [
            {"path": str(args.contract.relative_to(REPO_ROOT)), "sha256": sha256_file(args.contract)},
            {"path": str((artifact_root / "audit-report.json").relative_to(REPO_ROOT)), "sha256": sha256_file(report_path)},
            *mask_records,
        ]
        for record in successor["frozen_predecessor_evidence"].values():
            artifact_records.append(dict(record))
        successor_evidence = {
            "a1_stage_passed": True,
            "accepted_strategy_arms": [],
            "actionable_arm_id": "no_trade",
            "approved_execution_instruments": [],
            "artifacts": artifact_records,
            "decision": report["decision"],
            "experiment_id": SUCCESSOR_ID,
            "new_provider_requests": 0,
            "price_rows_changed_or_filled": False,
            "qualified_for_strategy_evaluation": True,
            "returns_or_pnl_computed": False,
            "schema_version": "cross-asset-a1-oanda-hourly-successor-evidence-v1",
            "sealed_2026_price_accessed": False,
        }
        (temporary_root / "evidence-manifest.json").write_text(
            canonical_json(successor_evidence), encoding="utf-8"
        )
        temporary_root.replace(artifact_root)
    print(canonical_json({"decision": report["decision"], "passed_candidate_count": 7}), end="")


if __name__ == "__main__":
    main()
