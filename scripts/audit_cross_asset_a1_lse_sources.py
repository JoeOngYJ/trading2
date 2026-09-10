#!/usr/bin/env python3
"""Audit the frozen A1 LSE source pilot without signals, returns, or PnL."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from trading_platform.cross_asset_data_audit import (
    CrossAssetDataAuditError,
    load_frozen_contract,
    parse_stooq_daily_csv,
    verify_manifest_file,
)
from trading_platform.cross_asset_program import canonical_json, sha256_file


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = REPO_ROOT / "config/experiments/cross-asset-a1-lse-source-pilot-v1.json"


def load_canonical(path: Path, label: str) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    payload = json.loads(raw)
    if not isinstance(payload, dict) or raw != canonical_json(payload):
        raise CrossAssetDataAuditError(f"{label} is not canonical JSON")
    return payload


def atomic_write(path: Path, payload: bytes) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_bytes(payload)
    os.replace(temporary, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    args = parser.parse_args()
    if args.contract.resolve(strict=True) != DEFAULT_CONTRACT.resolve(strict=True):
        raise ValueError("exact frozen A1 pilot contract is required")
    contract = load_frozen_contract(args.contract)
    artifact_root = (REPO_ROOT / contract["output"]["artifact_root"]).resolve(strict=True)
    artifact_root.relative_to(REPO_ROOT.resolve(strict=True))
    source_manifest_path = artifact_root / "source-manifest.json"
    manifest = load_canonical(source_manifest_path, "A1 source manifest")
    if (
        manifest.get("schema_version") != "cross-asset-a1-source-manifest-v1"
        or manifest.get("pilot_id") != contract["pilot_id"]
        or manifest.get("contract_sha256") != sha256_file(DEFAULT_CONTRACT)
        or manifest.get("strategy_data_evaluated") is not False
    ):
        raise CrossAssetDataAuditError("A1 source manifest does not match the frozen pilot")
    records = manifest.get("files")
    if not isinstance(records, list) or len(records) != 9:
        raise CrossAssetDataAuditError("A1 source manifest must contain exactly nine files")
    by_role = {record["role"]: record for record in records}
    identity_results: list[dict[str, Any]] = []
    price_results: list[dict[str, Any]] = []
    expected_sessions = contract["boundaries"]["expected_lse_sessions"]
    for instrument in contract["instruments"]:
        ticker = instrument["ticker"]
        identity_record = by_role.get(f"issuer_identity:{ticker}")
        if identity_record is None:
            raise CrossAssetDataAuditError(f"missing issuer identity record for {ticker}")
        identity_path = verify_manifest_file(REPO_ROOT, identity_record)
        identity_text = identity_path.read_text(encoding="utf-8", errors="replace")
        required_tokens = [
            ticker,
            instrument["isin"],
            instrument["sedol"],
            instrument["ric"],
        ]
        missing_tokens = [token for token in required_tokens if token not in identity_text]
        identity_results.append(
            {
                "error": identity_record.get("error"),
                "identity_verified": identity_record.get("error") is None and not missing_tokens,
                "missing_tokens": missing_tokens,
                "raw_sha256": identity_record["sha256"],
                "ticker": ticker,
            }
        )
        price_record = by_role.get(f"stooq_daily_csv:{ticker}")
        if price_record is None:
            raise CrossAssetDataAuditError(f"missing Stooq record for {ticker}")
        price_path = verify_manifest_file(REPO_ROOT, price_record)
        try:
            parsed = parse_stooq_daily_csv(
                price_path.read_bytes(), ticker=ticker, expected_sessions=expected_sessions
            )
        except CrossAssetDataAuditError as exc:
            price_results.append(
                {
                    "error": price_record.get("error") or str(exc),
                    "technical_csv_valid": False,
                    "ticker": ticker,
                }
            )
        else:
            price_results.append(
                {
                    **parsed.as_dict(),
                    "error": price_record.get("error"),
                    "technical_csv_valid": price_record.get("error") is None,
                }
            )
    calendar_record = by_role.get("calendar")
    if calendar_record is None:
        raise CrossAssetDataAuditError("missing LSE calendar record")
    calendar_path = verify_manifest_file(REPO_ROOT, calendar_record)
    calendar_retrieved = calendar_record.get("error") is None and calendar_path.stat().st_size > 0
    source = contract["sources"]["stooq_daily_csv"]
    unresolved_semantics = sorted(
        key
        for key in (
            "adjustment_policy_documented",
            "availability_time_documented",
            "corporate_action_policy_documented",
            "research_reuse_terms_documented",
        )
        if source.get(key) is not True
    )
    identities_pass = all(item["identity_verified"] for item in identity_results)
    technical_prices_pass = all(item["technical_csv_valid"] for item in price_results)
    source_accepted = identities_pass and technical_prices_pass and not unresolved_semantics
    report = {
        "a1_stage_passed": False,
        "bulk_download_authorized": False,
        "calendar_retrieved": calendar_retrieved,
        "contract_sha256": sha256_file(DEFAULT_CONTRACT),
        "decision": (
            "candidate_source_accepted_for_full_history_contract"
            if source_accepted
            else "candidate_source_rejected_for_full_history_contract"
        ),
        "economic_metrics_computed": False,
        "identity_results": identity_results,
        "identity_verification_passed": identities_pass,
        "pilot_id": contract["pilot_id"],
        "pnl_computed": False,
        "price_results": price_results,
        "schema_version": "cross-asset-a1-source-audit-v1",
        "sealed_partition_accessed": False,
        "source_accepted": source_accepted,
        "strategy_signals_generated": False,
        "technical_price_validation_passed": technical_prices_pass,
        "unresolved_source_semantics": unresolved_semantics,
    }
    report_path = artifact_root / "audit-report.json"
    if report_path.exists():
        raise ValueError(f"refusing to overwrite A1 audit report: {report_path}")
    atomic_write(report_path, canonical_json(report).encode("utf-8"))
    evidence_manifest = {
        "artifacts": [
            {"path": source_manifest_path.relative_to(REPO_ROOT).as_posix(), "sha256": sha256_file(source_manifest_path)},
            {"path": report_path.relative_to(REPO_ROOT).as_posix(), "sha256": sha256_file(report_path)},
            *[
                {"path": record["path"], "sha256": record["sha256"]}
                for record in records
            ],
        ],
        "contract_sha256": sha256_file(DEFAULT_CONTRACT),
        "decision": report["decision"],
        "pilot_id": contract["pilot_id"],
        "schema_version": "cross-asset-a1-evidence-manifest-v1",
    }
    evidence_path = artifact_root / "evidence-manifest.json"
    if evidence_path.exists():
        raise ValueError(f"refusing to overwrite A1 evidence manifest: {evidence_path}")
    atomic_write(evidence_path, canonical_json(evidence_manifest).encode("utf-8"))
    print(
        canonical_json(
            {
                "decision": report["decision"],
                "evidence_manifest_sha256": sha256_file(evidence_path),
                "identity_verification_passed": identities_pass,
                "source_accepted": source_accepted,
                "technical_price_validation_passed": technical_prices_pass,
                "unresolved_source_semantics": unresolved_semantics,
            }
        ),
        end="",
    )


if __name__ == "__main__":
    main()
