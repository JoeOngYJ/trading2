#!/usr/bin/env python3
"""Audit and normalize exact XLON history without calculating returns or PnL."""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path

from trading_platform.cross_asset_a1_expansion import (
    A1ExpansionError,
    canonical_json,
    load_contract,
    sha256_file,
)
from trading_platform.cross_asset_lse_history import (
    LseHistoryError,
    load_source_manifest,
    normalize_actions,
    normalize_prices,
)
from trading_platform.cross_asset_xlon_calendar import load_calendar


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = REPO_ROOT / "config/experiments/cross-asset-a1-lse-futures-expansion-v1.json"


def run(contract_path: Path) -> Path:
    contract = load_contract(contract_path, REPO_ROOT)
    output_root = REPO_ROOT / contract["lse_acquisition"]["output_artifact_root"]
    manifest_path = output_root / "source-manifest.json"
    manifest = load_source_manifest(manifest_path, contract_path, contract, REPO_ROOT)
    if (output_root / "audit-report.json").exists():
        raise LseHistoryError("write-once LSE audit already exists")
    calendar_record = contract["xlon_calendar"]
    calendar = load_calendar(
        REPO_ROOT / calendar_record["path"],
        REPO_ROOT / "config/research/xlon-calendar-evidence-v1.json",
        REPO_ROOT,
    )
    response_by_key = {(item["symbol"], item["endpoint"]): item for item in manifest["responses"]}
    temp_root = Path(tempfile.mkdtemp(prefix=".lse-audit-", dir=output_root))
    normalized_root = temp_root / "normalized"
    normalized_root.mkdir()
    artifacts: list[dict[str, str]] = []
    instrument_reports: list[dict[str, object]] = []
    try:
        for instrument in contract["listed_funds"]:
            symbol = instrument["symbol"]
            expected_sessions = tuple(
                item
                for item in calendar["sessions"]
                if instrument["usable_start"] <= item.session_date <= instrument["usable_end"]
            )
            price_record = response_by_key[(symbol, "time_series")]
            price_path = REPO_ROOT / price_record["path"]
            price_payload = json.loads(price_path.read_text(encoding="utf-8"))
            price_lines = normalize_prices(
                price_payload, instrument, expected_sessions, price_record["sha256"]
            )
            price_output = normalized_root / f"{symbol.casefold()}-daily.jsonl"
            price_output.write_text("\n".join(price_lines) + "\n", encoding="utf-8")
            action_counts: dict[str, int] = {}
            for endpoint in ("dividends", "splits"):
                action_record = response_by_key[(symbol, endpoint)]
                action_path = REPO_ROOT / action_record["path"]
                action_payload = json.loads(action_path.read_text(encoding="utf-8"))
                lines = normalize_actions(
                    action_payload, instrument, endpoint, action_record["sha256"]
                )
                action_output = normalized_root / f"{symbol.casefold()}-{endpoint}.jsonl"
                action_output.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
                action_counts[endpoint] = len(lines)
            instrument_reports.append(
                {
                    "action_counts": action_counts,
                    "expected_sessions": len(expected_sessions),
                    "history_source_passed": True,
                    "issuer_action_reconciliation_passed": False,
                    "normalized_price_rows": len(price_lines),
                    "symbol": symbol,
                    "usable_end": instrument["usable_end"],
                    "usable_start": instrument["usable_start"],
                }
            )
        for path in sorted(normalized_root.iterdir()):
            artifacts.append(
                {
                    "path": str((Path(contract["lse_acquisition"]["output_artifact_root"]) / "normalized" / path.name)),
                    "sha256": sha256_file(path),
                }
            )
        report = {
            "a1_stage_passed": False,
            "accepted_strategy_arms": [],
            "approved_execution_instruments": [],
            "decision": "exact_lse_history_source_passed_pending_issuer_actions_and_costs",
            "economic_metrics_computed": False,
            "experiment_id": contract["experiment_id"],
            "instruments": instrument_reports,
            "next_gate": "complete issuer-action reconciliation and effective-dated costs",
            "pnl_computed": False,
            "returns_computed": False,
            "sealed_2026_accessed": False,
            "strategy_signals_generated": False,
        }
        report_path = temp_root / "audit-report.json"
        report_path.write_text(canonical_json(report), encoding="utf-8")
        artifacts.append(
            {
                "path": str(Path(contract["lse_acquisition"]["output_artifact_root"]) / "audit-report.json"),
                "sha256": sha256_file(report_path),
            }
        )
        evidence = {
            "artifacts": artifacts,
            "contract_sha256": sha256_file(contract_path),
            "decision": report["decision"],
            "experiment_id": contract["experiment_id"],
            "schema_version": "cross-asset-a1-exact-xlon-history-evidence-manifest-v1",
            "source_manifest_sha256": sha256_file(manifest_path),
        }
        evidence_path = temp_root / "evidence-manifest.json"
        evidence_path.write_text(canonical_json(evidence), encoding="utf-8")
        for item in temp_root.iterdir():
            item.rename(output_root / item.name)
        temp_root.rmdir()
        return output_root / "evidence-manifest.json"
    except BaseException:
        shutil.rmtree(temp_root, ignore_errors=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    args = parser.parse_args()
    try:
        evidence = run(args.contract)
    except (A1ExpansionError, LseHistoryError) as exc:
        parser.error(str(exc))
    print(f"evidence manifest written: {evidence.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
