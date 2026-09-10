#!/usr/bin/env python3
"""Audit and normalize the frozen Twelve Data 2008-2025 history snapshot."""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from trading_platform.cross_asset_twelvedata_audit import canonical_json, parse_response, sha256_file
from trading_platform.cross_asset_twelvedata_history import (
    EVIDENCE_SCHEMA,
    ETF_SYMBOLS,
    SYMBOLS,
    TwelveDataHistoryError,
    load_contract,
    normalized_action_lines,
    normalized_price_lines,
    validate_source_manifest,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = REPO_ROOT / "config/experiments/cross-asset-a1-twelvedata-full-history-v2.json"
DEFAULT_MANIFEST = (
    REPO_ROOT
    / "artifacts/agent-level-experiment/cross-asset/a1-twelvedata-full-history-v2/source-manifest.json"
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _artifact(path: Path) -> dict[str, object]:
    return {
        "bytes": path.stat().st_size,
        "path": path.resolve(strict=True).relative_to(REPO_ROOT.resolve(strict=True)).as_posix(),
        "sha256": sha256_file(path),
    }


def run(contract_path: Path, manifest_path: Path) -> tuple[Path, Path]:
    contract, pilot, calendars = load_contract(contract_path, REPO_ROOT)
    indexed, manifest = validate_source_manifest(
        REPO_ROOT, manifest_path, contract_path, contract
    )
    output_root = manifest_path.parent
    report_path = output_root / "audit-report.json"
    evidence_path = output_root / "evidence-manifest.json"
    normalized_root = output_root / "normalized"
    if report_path.exists() or evidence_path.exists() or normalized_root.exists():
        raise TwelveDataHistoryError("write-once history audit artifacts already exist")
    temp_normalized = Path(tempfile.mkdtemp(prefix=".normalized-", dir=output_root))
    instruments = {item["symbol"]: dict(item) for item in pilot["instruments"]}
    failures: list[dict[str, str]] = []
    results: dict[str, dict[str, object]] = {symbol: {"symbol": symbol} for symbol in SYMBOLS}
    try:
        for symbol in SYMBOLS:
            instrument = instruments[symbol]
            expected = (
                calendars["fx"]["sessions"]
                if symbol == "GBP/USD"
                else calendars["us_exchange"]["sessions"]
            )
            raw_path = indexed[(symbol, "time_series")]
            try:
                payload = parse_response(raw_path.read_bytes(), f"{symbol} full time series")
                lines = normalized_price_lines(payload, instrument, expected, sha256_file(raw_path))
                normalized_path = temp_normalized / f"{symbol.casefold().replace('/', '-')}-daily.jsonl"
                normalized_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
                results[symbol]["daily"] = {
                    "first_session": expected[0],
                    "last_session": expected[-1],
                    "normalized_rows": len(lines),
                    "source_sha256": sha256_file(raw_path),
                }
            except (TwelveDataHistoryError, ValueError) as exc:
                failures.append({"error": str(exc), "gate": "daily_history", "symbol": symbol})
                results[symbol]["daily_error"] = str(exc)
        minimums = contract["cash_flow_and_split_policy"][
            "distribution_plausibility_minimum_records"
        ]
        for symbol in ETF_SYMBOLS:
            instrument = instruments[symbol]
            instrument["corporate_action_identity_via_time_series"] = True
            for endpoint in ("dividends", "splits"):
                raw_path = indexed[(symbol, endpoint)]
                try:
                    payload = parse_response(raw_path.read_bytes(), f"{symbol} {endpoint}")
                    lines = normalized_action_lines(
                        payload,
                        instrument,
                        endpoint,
                        sha256_file(raw_path),
                        contract["boundaries"]["development_start_inclusive"],
                        contract["boundaries"]["development_end_inclusive"],
                    )
                    if endpoint == "dividends" and symbol in minimums and len(lines) < int(minimums[symbol]):
                        raise TwelveDataHistoryError(
                            f"{symbol} dividend count {len(lines)} is below frozen minimum {minimums[symbol]}"
                        )
                    normalized_path = temp_normalized / f"{symbol.casefold()}-{endpoint}.jsonl"
                    normalized_path.write_text(
                        "" if not lines else "\n".join(lines) + "\n", encoding="utf-8"
                    )
                    results[symbol].setdefault("corporate_actions", {})[endpoint] = {
                        "normalized_rows": len(lines),
                        "source_sha256": sha256_file(raw_path),
                    }
                except (TwelveDataHistoryError, ValueError) as exc:
                    failures.append({"error": str(exc), "gate": endpoint, "symbol": symbol})
                    results[symbol].setdefault("corporate_action_errors", {})[endpoint] = str(exc)
        history_accepted = not failures
        if history_accepted:
            temp_normalized.rename(normalized_root)
        else:
            shutil.rmtree(temp_normalized, ignore_errors=True)
        decision = (
            "full_history_accepted_for_A1_review"
            if history_accepted
            else "full_history_rejected"
        )
        report = {
            "a1_stage_passed": False,
            "audited_at": _utc_now(),
            "decision": decision,
            "economic_metrics_computed": False,
            "experiment_id": contract["experiment_id"],
            "feature_observations_generated": False,
            "gate_failures": failures,
            "history_accepted": history_accepted,
            "instrument_results": [results[symbol] for symbol in SYMBOLS],
            "next_action": (
                "review_A1_research_proxy_boundary_before_any_A2_contract"
                if history_accepted
                else "preserve_rejection_and_freeze_any_corrected_history_contract_under_a_new_experiment_id"
            ),
            "pnl_computed": False,
            "returns_computed": False,
            "sealed_2026_partition_accessed": False,
            "source_snapshot_completed_at": manifest["completed_at"],
            "strategy_signals_generated": False,
            "unresolved_for_execution": [
                "broker_executable_instrument_mapping",
                "account_specific_costs_and_permissions",
                "archival_use_after_subscription_termination"
            ],
        }
        report_path.write_text(canonical_json(report), encoding="utf-8")
        artifact_paths = [
            manifest_path,
            report_path,
            *sorted((output_root / "raw").glob("*.json")),
        ]
        if history_accepted:
            artifact_paths.extend(sorted(normalized_root.glob("*.jsonl")))
        evidence = {
            "artifacts": [_artifact(path) for path in artifact_paths],
            "calendar_sha256": contract["boundaries"]["expected_calendar"]["sha256"],
            "contract_sha256": sha256_file(contract_path),
            "decision": decision,
            "experiment_id": contract["experiment_id"],
            "schema_version": EVIDENCE_SCHEMA,
        }
        evidence_path.write_text(canonical_json(evidence), encoding="utf-8")
        return report_path, evidence_path
    except BaseException:
        shutil.rmtree(temp_normalized, ignore_errors=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit the frozen Twelve Data full history.")
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--source-manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    try:
        report, evidence = run(args.contract, args.source_manifest)
    except TwelveDataHistoryError as exc:
        parser.error(str(exc))
    print(f"audit report written: {report.relative_to(REPO_ROOT)}")
    print(f"evidence manifest written: {evidence.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
