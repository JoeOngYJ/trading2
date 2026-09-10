#!/usr/bin/env python3
"""Audit and normalize the frozen Twelve Data A1 v3 recovery snapshot."""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from trading_platform.cross_asset_twelvedata_audit import canonical_json, sha256_file
from trading_platform.cross_asset_twelvedata_history import ETF_SYMBOLS, SYMBOLS, TwelveDataHistoryError
from trading_platform.cross_asset_twelvedata_recovery import EVIDENCE_SCHEMA, load_contract, merge_dividend_windows, merge_price_windows, inherited_split_lines, validate_source_manifest


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "config/experiments/cross-asset-a1-twelvedata-recovery-v3.json"
DEFAULT_MANIFEST = ROOT / "artifacts/agent-level-experiment/cross-asset/a1-twelvedata-recovery-v3/source-manifest.json"


def _now() -> str: return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
def _artifact(path: Path) -> dict[str, object]: return {"bytes": path.stat().st_size, "path": path.resolve(strict=True).relative_to(ROOT.resolve(strict=True)).as_posix(), "sha256": sha256_file(path)}


def run(contract_path: Path, manifest_path: Path) -> tuple[Path, Path]:
    contract, pilot, calendar = load_contract(contract_path, ROOT)
    indexed, manifest = validate_source_manifest(ROOT, manifest_path, contract_path, contract)
    output = manifest_path.parent; report_path = output / "audit-report.json"; evidence_path = output / "evidence-manifest.json"; normalized = output / "normalized"
    if report_path.exists() or evidence_path.exists() or normalized.exists(): raise TwelveDataHistoryError("write-once v3 audit artifacts already exist")
    temp = Path(tempfile.mkdtemp(prefix=".normalized-", dir=output)); instruments = {item["symbol"]: dict(item) for item in pilot["instruments"]}
    results: dict[str, dict[str, object]] = {}; accepted: set[str] = set(); normalized_files: list[Path] = []
    try:
        for symbol in SYMBOLS:
            instrument = instruments[symbol]; result: dict[str, object] = {"symbol": symbol}; price_lines: tuple[str, ...] = (); dividend_lines: tuple[str, ...] = (); split_lines: tuple[str, ...] = ()
            try:
                price_paths = [indexed[(symbol, "time_series", window["window_id"])] for window in contract["time_series_windows"]]
                fx = symbol == "GBP/USD"; expected = calendar["fx_sessions"] if fx else calendar["us_sessions"]
                eligible_start = contract["per_instrument_policy"]["dbc_eligible_start_without_independent_2008_verification"] if symbol == "DBC" else contract["boundaries"]["development_start_inclusive"]
                daily, price_lines = merge_price_windows(price_paths, instrument, expected, fx=fx, maximum_missing_fraction=Decimal(contract["fx_policy"]["maximum_missing_fraction"]), maximum_gap=int(contract["fx_policy"]["maximum_consecutive_missing_reference_sessions"]), eligible_start=eligible_start)
                result["daily"] = daily
            except (TwelveDataHistoryError, ValueError) as exc: result["daily_error"] = str(exc)
            if symbol in ETF_SYMBOLS:
                try:
                    dividend_paths = [indexed[(symbol, "dividends", window["window_id"])] for window in contract["dividend_windows"]]
                    minimum = contract["per_instrument_policy"]["passing_dividend_minimums"].get(symbol)
                    dividends, dividend_lines = merge_dividend_windows(dividend_paths, instrument, int(contract["per_instrument_policy"]["dividend_response_record_limit"]), None if minimum is None else int(minimum))
                    result["dividends"] = dividends
                except (TwelveDataHistoryError, ValueError) as exc: result["dividend_error"] = str(exc)
                try:
                    splits, split_lines = inherited_split_lines(ROOT, contract, instrument); result["splits"] = splits
                except (TwelveDataHistoryError, ValueError) as exc: result["split_error"] = str(exc)
            instrument_accepted = "daily" in result and (symbol == "GBP/USD" or ("dividends" in result and "splits" in result))
            result["source_quality_decision"] = "accepted_for_A1_subset_review" if instrument_accepted else "rejected"
            result["eligibility"] = {"corporate_actions": instrument_accepted and symbol in ETF_SYMBOLS, "daily_close": instrument_accepted, "fx_conversion": instrument_accepted and symbol == "GBP/USD", "full_ohlc": instrument_accepted, "volume": instrument_accepted and symbol != "GBP/USD"}
            if instrument_accepted:
                accepted.add(symbol)
                for suffix, lines in (("daily", price_lines), ("dividends", dividend_lines), ("splits", split_lines)):
                    if suffix != "daily" and symbol == "GBP/USD": continue
                    path = temp / f"{symbol.casefold().replace('/', '-')}-{suffix}.jsonl"; path.write_text("" if not lines else "\n".join(lines) + "\n", encoding="utf-8"); normalized_files.append(path)
            results[symbol] = result
        roles = contract["decision_rule"]["essential_roles"]
        role_results = {role: {"accepted_symbols": sorted(set(symbols) & accepted), "passed": bool(set(symbols) & accepted)} for role, symbols in roles.items()}
        essential_pass = all(item["passed"] for item in role_results.values())
        temp.rename(normalized)
        decision = "recovery_accepted_for_A1_subset_review" if essential_pass else "recovery_rejected_missing_essential_role"
        report = {"a1_stage_passed": False, "accepted_instruments": sorted(accepted), "audited_at": _now(), "decision": decision, "economic_metrics_computed": False, "experiment_id": contract["experiment_id"], "feature_observations_generated": False, "instrument_results": [results[symbol] for symbol in SYMBOLS], "next_action": contract["decision_rule"]["next_if_essential_roles_pass"] if essential_pass else contract["decision_rule"]["next_if_role_missing"], "pnl_computed": False, "returns_computed": False, "role_results": role_results, "sealed_2026_partition_accessed": False, "source_snapshot_completed_at": manifest["completed_at"], "strategy_signals_generated": False, "unresolved_for_A1": ["issuer_corporate_action_reconciliation", "broker_executable_instrument_mapping", "account_specific_costs_and_permissions", "archival_use_after_subscription_termination"]}
        report_path.write_text(canonical_json(report), encoding="utf-8")
        artifacts = [manifest_path, report_path, *sorted((output / "raw").glob("*.json")), *sorted(normalized.glob("*.jsonl"))]
        evidence = {"artifacts": [_artifact(path) for path in artifacts], "calendar_sha256": contract["boundaries"]["calendar"]["sha256"], "contract_sha256": sha256_file(contract_path), "decision": decision, "experiment_id": contract["experiment_id"], "schema_version": EVIDENCE_SCHEMA}
        evidence_path.write_text(canonical_json(evidence), encoding="utf-8"); return report_path, evidence_path
    except BaseException:
        shutil.rmtree(temp, ignore_errors=True); raise


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT); parser.add_argument("--source-manifest", type=Path, default=DEFAULT_MANIFEST); args = parser.parse_args()
    try: report, evidence = run(args.contract, args.source_manifest)
    except TwelveDataHistoryError as exc: parser.error(str(exc))
    print(f"audit report written: {report.relative_to(ROOT)}"); print(f"evidence manifest written: {evidence.relative_to(ROOT)}")


if __name__ == "__main__": main()
