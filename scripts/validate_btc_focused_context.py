#!/usr/bin/env python3
"""Validate the additive BTC-focused offline research context."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = ROOT / "research/btc/INDEX.json"


class FocusedContextError(ValueError):
    pass


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def canonical_line(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def record_digest(record: dict) -> str:
    payload = {key: value for key, value in record.items() if key != "record_digest"}
    return hashlib.sha256(canonical_line(payload).encode()).hexdigest()


def load_canonical(path: Path) -> dict:
    try:
        raw = path.read_text(encoding="utf-8")
        value = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise FocusedContextError(f"cannot load {path.relative_to(ROOT)}") from exc
    accepted_forms = {canonical_json(value), canonical_line(value) + "\n"}
    if not isinstance(value, dict) or raw not in accepted_forms:
        raise FocusedContextError(f"non-canonical JSON: {path.relative_to(ROOT)}")
    return value


def validate_bound_input(item: dict, label: str) -> None:
    """Validate frozen inputs, including the append-only live catalogue lineage."""
    relative = item.get("path")
    expected = item.get("sha256")
    if not isinstance(relative, str) or not isinstance(expected, str):
        raise FocusedContextError(f"invalid {label} reference")
    path = ROOT / relative
    if path.is_file() and sha256_path(path) == expected:
        return

    # Two early contracts bound the live catalogue before it was extended. Preserve
    # those contracts and prove their exact historical view is still a projection of
    # the append-only catalogue instead of rewriting a frozen experiment.
    if relative == "research/btc/BTC_EVIDENCE_CATALOG.json":
        catalog = load_canonical(path)
        projected = json.loads(json.dumps(catalog))
        projected["data_families"] = [
            value
            for value in projected.get("data_families", [])
            if value.get("id") != "deribit_btc_dvol_public_pilot"
        ]
        projected["experiment_families"] = [
            value
            for value in projected.get("experiment_families", [])
            if value.get("family")
            not in {
                "HAR_RV_standalone_volatility_forecast",
                "multidimensional_risk_forecast_and_downward_only_fusion_infrastructure",
            }
        ]
        projected_digest = hashlib.sha256(canonical_json(projected).encode()).hexdigest()
        if projected_digest == expected:
            return

    raise FocusedContextError(f"missing or changed {label}: {relative}")


def validate_decision_log(path: Path) -> tuple[int, str]:
    raw = path.read_text(encoding="utf-8")
    if not raw or not raw.endswith("\n"):
        raise FocusedContextError("decision log must be non-empty and newline terminated")
    previous = None
    for sequence, line in enumerate(raw.splitlines(), start=1):
        record = json.loads(line)
        if line != canonical_line(record) or record.get("sequence") != sequence:
            raise FocusedContextError(f"invalid canonical decision line {sequence}")
        if record.get("previous_record_digest") != previous:
            raise FocusedContextError(f"broken decision chain at line {sequence}")
        if record.get("record_digest") != record_digest(record):
            raise FocusedContextError(f"decision digest mismatch at line {sequence}")
        previous = record["record_digest"]
    return sequence, previous


def validate() -> dict:
    index = load_canonical(INDEX_PATH)
    if index.get("schema_version") != "btc-focused-research-index-v1":
        raise FocusedContextError("unsupported focused index schema")
    if index.get("actionable_arm_id") != "no_trade" or index.get("status") != "offline_research_only":
        raise FocusedContextError("focused context is not fail-closed offline research")
    if index.get("active_experiment") is not None:
        raise FocusedContextError("focused index must have no active experiment after trend rejection")
    if (
        index.get("selected_strategy_candidate")
        != "none_multihorizon_perp_trend_v5_rejected"
        or index.get("selected_strategy_direction")
        != "materially_different_non_price_trend_BTC_alpha_required"
    ):
        raise FocusedContextError("focused index does not preserve the current strategy boundary")
    if (
        index.get("last_completed_experiment")
        != "btc-breakout-execution-source-audit-a0-v1_execution_findings_confirmed"
        or index.get("next_permitted_action")
        != "Freeze_execution_correction_specification_then_synthetic_qualification_before_historical_replay"
    ):
        raise FocusedContextError("focused index does not preserve the blocked E1 phase boundary")

    seen = set()
    for item in index.get("context_artifacts", []):
        relative = item.get("path")
        if not isinstance(relative, str) or relative in seen or relative.startswith("/") or ".." in Path(relative).parts:
            raise FocusedContextError(f"invalid or repeated context path: {relative}")
        path = ROOT / relative
        if not path.is_file() or sha256_path(path) != item.get("sha256"):
            raise FocusedContextError(f"missing or changed context artifact: {relative}")
        seen.add(relative)

    handoff_text = (ROOT / "research/btc/HANDOFF.md").read_text(encoding="utf-8")
    if (
        "Current status: R2-v2 accounting reconciled; A0 execution defects confirmed; correction specification required; no strategy accepted"
        not in handoff_text
        or handoff_text.count("## Next permitted action") != 1
        or not handoff_text.rstrip().endswith("every actionable route remains `no_trade`.")
        or "Freeze the execution correction specification and qualify it synthetically before historical execution replay."
        not in handoff_text
        or "Do not implement C0, C1-C6, E1-v15, E2, historical reconciliation or strategy evaluation"
        not in handoff_text
        or "No pass review exists and no C0 implementation is authorized."
        not in handoff_text
        or "src/trading_platform/btc_decimal_ledger_e1.py" in handoff_text
        or "research/btc/tests/test_btc_decimal_ledger_e1.py" in handoff_text
    ):
        raise FocusedContextError("handoff contradicts the blocked E1/no_trade boundary")

    archive = ROOT / "research/btc/invalid/unified-backtest-engine-e0-v12-final-review-failure"
    bundle_path = archive / "candidate/pre-review-bundle-manifest.json"
    if sha256_path(bundle_path) != "82abf80c66c49bb780bf764f17a9c1313bb611002ad6815c642386b2910c1516":
        raise FocusedContextError("E0-v12 frozen bundle changed")
    bundle = json.loads(bundle_path.read_text())
    for item in bundle["files"]:
        archived = archive / "snapshot" / item["path"]
        if not archived.is_file() or archived.stat().st_size != item["size_bytes"] or sha256_path(archived) != item["sha256"]:
            raise FocusedContextError("E0-v12 archive bytes changed")
        if (ROOT / item["path"]).exists():
            raise FocusedContextError("rejected E0-v12 file remains active")

    e0_contract = load_canonical(
        ROOT / "research/btc/contracts/btc-unified-backtest-engine-e0-v1.json"
    )
    if (
        e0_contract.get("qualification_id") != "btc-unified-backtest-engine-e0-v1"
        or e0_contract.get("status") != "frozen_before_E1_implementation"
        or e0_contract.get("action_boundary", {}).get("actionable_arm_id") != "no_trade"
        or e0_contract.get("action_boundary", {}).get(
            "historical_strategy_return_access_allowed_in_E0_E1_E2"
        )
        is not False
    ):
        raise FocusedContextError("unified engine E0 contract is not frozen and fail closed")
    for item in e0_contract.get("bound_authorities", []):
        validate_bound_input(item, "unified engine E0 authority")

    e0_output = ROOT / "artifacts/agent-level-experiment/btc-focused/unified-backtest-engine-e0-v1"
    e0_report = load_canonical(e0_output / "qualification-report.json")
    if (
        e0_report.get("decision") != "e0_specification_passed_e1_synthetic_only_permitted"
        or e0_report.get("historical_market_rows_accessed") != 0
        or e0_report.get("historical_strategy_return_accessed") is not False
        or e0_report.get("production_or_external_service_accessed") is not False
        or e0_report.get("sealed_2026_or_partial_OB0_accessed") is not False
        or e0_report.get("actionable_arm_id") != "no_trade"
        or not all(e0_report.get("gates", {}).values())
    ):
        raise FocusedContextError("unified engine E0 qualification is not a clean pass")
    e0_manifest = load_canonical(e0_output / "evidence-manifest.json")
    if (
        e0_manifest.get("decision") != "e0_specification_passed_e1_synthetic_only_permitted"
        or e0_manifest.get("actionable_arm_id") != "no_trade"
    ):
        raise FocusedContextError("unified engine E0 manifest changed")
    for item in e0_manifest.get("artifacts", []):
        validate_bound_input(item, "unified engine E0 evidence")

    e0_v2 = load_canonical(ROOT / "research/btc/contracts/btc-unified-backtest-engine-e0-v2.json")
    if (
        e0_v2.get("qualification_id") != "btc-unified-backtest-engine-e0-v2"
        or e0_v2.get("action_boundary", {}).get("actionable_arm_id") != "no_trade"
        or e0_v2.get("action_boundary", {}).get(
            "historical_market_rows_results_metrics_or_strategy_logic_allowed"
        )
        is not False
    ):
        raise FocusedContextError("unified engine E0-v2 contract changed")
    for item in e0_v2.get("invalid_E1_v1_draft_evidence", []):
        validate_bound_input(item, "E0-v2 invalid draft evidence")
    for path_key, digest_key in (("contract_path", "contract_sha256"), ("plan_path", "plan_sha256")):
        validate_bound_input(
            {"path": e0_v2["predecessor"][path_key], "sha256": e0_v2["predecessor"][digest_key]},
            "E0-v2 predecessor",
        )

    e0_v3 = load_canonical(
        ROOT / "research/btc/contracts/btc-unified-backtest-engine-e0-v3-pair-close.json"
    )
    if (
        e0_v3.get("qualification_id") != "btc-unified-backtest-engine-e0-v3-pair-close"
        or e0_v3.get("action_boundary", {}).get("actionable_arm_id") != "no_trade"
        or e0_v3.get("action_boundary", {}).get(
            "historical_market_rows_results_metrics_strategy_or_oracle_allowed"
        )
        is not False
    ):
        raise FocusedContextError("unified engine E0-v3 contract changed")
    for group in ("inheritance", "machine_authorities", "paused_E1_clean_room_draft"):
        for item in e0_v3.get(group, {}).values() if isinstance(e0_v3.get(group), dict) else []:
            if isinstance(item, dict) and "path" in item and "sha256" in item:
                validate_bound_input(item, f"E0-v3 {group}")

    e0_v4_path = ROOT / "research/btc/contracts/btc-unified-backtest-engine-e0-v4-lineage-recovery.json"
    e0_v4 = load_canonical(e0_v4_path)
    if (
        e0_v4.get("experiment_id") != "btc-unified-backtest-engine-e0-v4-lineage-recovery"
        or e0_v4.get("status") != "frozen_pending_independent_review"
        or e0_v4.get("actionable_arm_id") != "no_trade"
    ):
        raise FocusedContextError("unified engine E0-v4 lineage recovery contract changed")

    tombstone = load_canonical(
        ROOT / "research/btc/incidents/unified-engine-v3-missing-paused-draft-tombstone.json"
    )
    if (
        tombstone.get("incident_id") != "unified-engine-v3-missing-paused-draft-lineage-v1"
        or tombstone.get("actionable_arm_id") != "no_trade"
        or tombstone.get("current_candidate_disposition")
        != "qualification_revoked_archived_unqualified_do_not_import_copy_repair_or_use_downstream"
    ):
        raise FocusedContextError("unified engine v3 lineage tombstone changed")

    v14_archive = (
        ROOT
        / "research/btc/invalid/unified-backtest-engine-e1-v14-accounting-authority-failure"
    )
    v14_identity = load_canonical(
        v14_archive / "identity/btc-unified-backtest-engine-e1-v14-identity.json"
    )
    v14_manifest = load_canonical(v14_archive / "snapshot/candidate/candidate-manifest.json")
    if (
        v14_identity.get("experiment_id") != "btc-unified-backtest-engine-e1-v14"
        or v14_identity.get("actionable_arm_id") != "no_trade"
        or v14_manifest.get("experiment_id") != "btc-unified-backtest-engine-e1-v14"
        or v14_manifest.get("status") != "frozen_before_independent_oracle_review"
        or v14_manifest.get("actionable_arm_id") != "no_trade"
    ):
        raise FocusedContextError("rejected E1-v14 identity or manifest changed")
    candidate_prefix = "research/btc/candidates/unified-backtest-engine-e1-v14/"
    if len(v14_manifest.get("artifacts", [])) != 17:
        raise FocusedContextError("rejected E1-v14 snapshot artifact count changed")
    for item in v14_manifest["artifacts"]:
        relative = item.get("path")
        active_relative = item.get("active_path")
        if not isinstance(relative, str) or not relative.startswith(candidate_prefix):
            raise FocusedContextError("invalid rejected E1-v14 snapshot path")
        archived = v14_archive / "snapshot/candidate" / relative[len(candidate_prefix):]
        if not archived.is_file() or sha256_path(archived) != item.get("sha256"):
            raise FocusedContextError(f"missing or changed rejected E1-v14 artifact: {archived}")
        if isinstance(active_relative, str) and (ROOT / active_relative).exists():
            raise FocusedContextError(f"rejected E1-v14 artifact remains active: {active_relative}")
    for forbidden in (
        ROOT / "research/btc/contracts/btc-unified-backtest-engine-e1-v14-identity.json",
        ROOT / "research/btc/reports/BTC_UNIFIED_BACKTEST_ENGINE_E1_V14_MODULAR_PLAN.md",
        ROOT / "research/btc/candidates/unified-backtest-engine-e1-v14",
    ):
        if forbidden.exists():
            raise FocusedContextError(f"rejected E1-v14 path remains active: {forbidden}")

    trend_contract = load_canonical(
        ROOT / "research/btc/contracts/btc-multihorizon-perp-trend-v5.json"
    )
    if (
        trend_contract.get("experiment_id") != "btc-multihorizon-perp-trend-v5"
        or trend_contract.get("status") != "frozen_before_single_historical_run"
        or trend_contract.get("action_boundary", {}).get("actionable_arm_id") != "no_trade"
    ):
        raise FocusedContextError("active trend contract is not frozen and fail closed")
    for item in trend_contract.get("bound_inputs", []):
        validate_bound_input(item, "active trend contract input")

    directional_mandate = load_canonical(
        ROOT / "config/mandates/retail-btc-directional-perpetual-research-v1.json"
    )
    authority = directional_mandate.get("authority", {})
    if (
        directional_mandate.get("status") != "frozen_offline_zero_capital_research_only"
        or directional_mandate.get("actionable_arm_id") != "no_trade"
        or authority.get("live_allocation_usdt") != 0
        or any(value is not False for key, value in authority.items() if key != "live_allocation_usdt")
    ):
        raise FocusedContextError("directional perpetual mandate is not zero-capital and fail closed")

    preliminary_t0 = load_canonical(
        ROOT / "artifacts/agent-level-experiment/btc-focused/multihorizon-perp-trend-v1/t0/report.json"
    )
    corrected_t0 = load_canonical(
        ROOT / "artifacts/agent-level-experiment/btc-focused/multihorizon-perp-trend-v1/t0-v2/report.json"
    )
    if (
        preliminary_t0.get("decision") != "t0_rejected_fail_closed"
        or preliminary_t0.get("strategy_return_accessed") is not False
        or corrected_t0.get("decision") != "t0_passed_implementation_permitted"
        or corrected_t0.get("t1_permitted") is not True
        or corrected_t0.get("strategy_return_accessed") is not False
        or corrected_t0.get("actionable_arm_id") != "no_trade"
        or not all(corrected_t0.get("gates", {}).values())
    ):
        raise FocusedContextError("trend T0 evidence does not preserve the audited fail-closed sequence")

    trend_t1 = load_canonical(
        ROOT / "artifacts/agent-level-experiment/btc-focused/multihorizon-perp-trend-v2/t1/audit-report.json"
    )
    if (
        trend_t1.get("decision") != "t1_synthetic_implementation_passed"
        or trend_t1.get("historical_market_rows_accessed") != 0
        or trend_t1.get("historical_strategy_return_accessed") is not False
        or trend_t1.get("t2_historical_run_permitted") is not True
        or trend_t1.get("actionable_arm_id") != "no_trade"
        or not all(trend_t1.get("checks", {}).values())
    ):
        raise FocusedContextError("trend T1 evidence is not synthetic-only and passed")

    trend_result = load_canonical(
        ROOT / "artifacts/agent-level-experiment/btc-focused/multihorizon-perp-trend-v5/report.json"
    )
    trend_audit = load_canonical(
        ROOT / "artifacts/agent-level-experiment/btc-focused/multihorizon-perp-trend-v5/audit/audit-report.json"
    )
    if (
        trend_result.get("decision") != "rejected_frozen_gates"
        or trend_result.get("accepted_strategy_arms") != []
        or trend_result.get("actionable_arm_id") != "no_trade"
        or trend_result.get("year_2026_accessed") is not False
        or trend_audit.get("decision") != "audit_passed_rejection_confirmed"
        or not all(trend_audit.get("checks", {}).values())
    ):
        raise FocusedContextError("trend v5 rejection or independent audit changed")

    program = load_canonical(ROOT / "research/btc/contracts/btc-only-program-v1.json")
    catalog = load_canonical(ROOT / "research/btc/BTC_EVIDENCE_CATALOG.json")
    if program.get("status") != "frozen" or program.get("active_market") != "BTC":
        raise FocusedContextError("BTC-only program is not frozen")
    if program.get("actionable_arm_id") != "no_trade" or program.get("accepted_strategy_arms"):
        raise FocusedContextError("BTC-only program does not preserve zero accepted arms")
    if program.get("maximum_active_strategy_hypotheses") != 1:
        raise FocusedContextError("BTC-only program does not enforce one active hypothesis")
    if catalog.get("actionable_arm_id") != "no_trade" or catalog.get("accepted_strategy_arms"):
        raise FocusedContextError("BTC evidence catalogue does not preserve no_trade")

    mandate_path = ROOT / "config/mandates/retail-btc-delta-neutral-research-v1.json"
    mandate = json.loads(mandate_path.read_text(encoding="utf-8"))
    authority = mandate.get("authority", {})
    if mandate.get("status") != "frozen_offline_research_only":
        raise FocusedContextError("derivatives research mandate is not frozen offline")
    if authority.get("live_allocation_usdt") != 0 or any(
        authority.get(key) is not False
        for key in (
            "account_connection_allowed",
            "credentials_allowed",
            "live_trading_allowed",
            "order_submission_allowed",
            "paper_orders_sent_to_exchange_allowed",
            "transfers_allowed",
        )
    ):
        raise FocusedContextError("derivatives mandate crosses zero-capital authority boundary")

    contract_path = ROOT / "research/btc/contracts/btc-carry-data-qualification-v1.json"
    contract = load_canonical(contract_path)
    if contract.get("status") != "frozen_before_any_new_acquisition":
        raise FocusedContextError("latest contract is not frozen")
    if contract.get("no_credentials") is not True or "return_or_PnL_calculation" not in contract.get("prohibited", []):
        raise FocusedContextError("carry audit contract crossed the data-only boundary")
    for item in contract.get("bound_existing_inputs", []):
        validate_bound_input(item, "bound input")

    output = ROOT / "artifacts/agent-level-experiment/btc-focused/carry-data-qualification-v1"
    source = load_canonical(output / "source-manifest.json")
    if source.get("archive_failures") != 0 or len(source.get("archive_records", [])) != 360:
        raise FocusedContextError("official carry archive acquisition is incomplete")
    if source.get("credentials_used") is not False or source.get("return_pnl_or_strategy_calculated") is not False:
        raise FocusedContextError("source acquisition crossed the data-only boundary")
    for record in source["archive_records"]:
        archive_path = ROOT / record["archive_path"]
        sidecar_path = ROOT / record["official_checksum_path"]
        if not archive_path.is_file() or sha256_path(archive_path) != record.get("archive_sha256"):
            raise FocusedContextError(f"missing or changed carry archive: {record['archive_path']}")
        if record.get("archive_sha256") != record.get("official_checksum"):
            raise FocusedContextError(f"official carry checksum mismatch: {record['archive_path']}")
        if not sidecar_path.is_file() or sidecar_path.read_text(encoding="utf-8").split()[0].lower() != record["official_checksum"]:
            raise FocusedContextError(f"missing or changed official sidecar: {record['official_checksum_path']}")
    for record in source.get("public_evidence_records", []):
        if record.get("status") == "downloaded":
            path = ROOT / record["path"]
            if not path.is_file() or sha256_path(path) != record.get("sha256"):
                raise FocusedContextError(f"missing or changed public evidence: {record['path']}")

    report = load_canonical(output / "audit-report.json")
    if report.get("decision") != "data_qualification_rejected" or report.get("actionable_arm_id") != "no_trade":
        raise FocusedContextError("latest report disposition is not preserved")
    if report.get("data_gate_passed") is not False or report.get("strategy_readiness_gate_passed") is not False:
        raise FocusedContextError("rejected carry gates were not preserved")
    if report.get("no_strategy_return_pnl_position_or_order_computed") is not True:
        raise FocusedContextError("latest report crossed the data-qualification boundary")
    expected_missing = {
        "klines": 0,
        "markPriceKlines": 192,
        "indexPriceKlines": 288,
        "premiumIndexKlines": 169,
    }
    actual_missing = {key: value.get("missing_hours") for key, value in report.get("price_series", {}).items()}
    if actual_missing != expected_missing:
        raise FocusedContextError("carry gap evidence changed")
    funding = report.get("funding", {})
    if any(funding.get(key) != 0 for key in ("duplicate_times", "invalid_rows", "irregular_intervals", "missing_scheduled_events")):
        raise FocusedContextError("funding continuity no longer passes")
    if funding.get("row_count") != 6576 or funding.get("maximum_schedule_offset_ms") != 47:
        raise FocusedContextError("funding schedule evidence changed")
    evidence_manifest = load_canonical(output / "evidence-manifest.json")
    for item in evidence_manifest.get("files", []):
        path = ROOT / item["path"]
        if not path.is_file() or sha256_path(path) != item.get("sha256"):
            raise FocusedContextError(f"missing or changed B2 evidence artifact: {item['path']}")

    b3_contract_path = ROOT / "research/btc/contracts/btc-backtest-core-qualification-v1.json"
    b3_contract = load_canonical(b3_contract_path)
    if b3_contract.get("status") != "frozen_before_core_implementation_and_qualification":
        raise FocusedContextError("B3 core contract is not frozen")
    boundary = b3_contract.get("action_boundary", {})
    if boundary.get("actionable_arm_id") != "no_trade" or boundary.get("accepted_strategy_arms"):
        raise FocusedContextError("B3 core contract does not preserve zero accepted arms")
    if boundary.get("new_strategy_outcome_allowed") is not False or boundary.get("regime_model_allowed") is not False:
        raise FocusedContextError("B3 core contract crosses its engineering-only boundary")
    for item in b3_contract.get("bound_inputs", []):
        validate_bound_input(item, "B3 bound input")

    b3_output = ROOT / "artifacts/agent-level-experiment/btc-focused/backtest-core-qualification-v1"
    b3_report = load_canonical(b3_output / "qualification-report.json")
    if b3_report.get("decision") != "b3_passed_engineering_only":
        raise FocusedContextError("B3 engineering disposition changed")
    if b3_report.get("actionable_arm_id") != "no_trade" or b3_report.get("accepted_strategy_arms"):
        raise FocusedContextError("B3 report does not preserve no_trade")
    if b3_report.get("new_strategy_outcome_evaluated") is not False or b3_report.get("regime_model_fitted") is not False:
        raise FocusedContextError("B3 report crossed its engineering-only boundary")
    if not all(b3_report.get("gates", {}).values()):
        raise FocusedContextError("a B3 engineering gate no longer passes")
    for key in ("core_implementation", "synthetic_result", "test_contract"):
        item = b3_report[key]
        path = ROOT / item["path"]
        if not path.is_file() or sha256_path(path) != item["sha256"]:
            raise FocusedContextError(f"missing or changed B3 implementation artifact: {item['path']}")
    b3_manifest = load_canonical(b3_output / "evidence-manifest.json")
    for item in b3_manifest.get("files", []):
        path = ROOT / item["path"]
        if not path.is_file() or sha256_path(path) != item["sha256"]:
            raise FocusedContextError(f"missing or changed B3 evidence artifact: {item['path']}")

    recovery_contract_path = ROOT / "research/btc/contracts/btc-carry-gap-recovery-v1.json"
    try:
        recovery_contract = json.loads(recovery_contract_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FocusedContextError("cannot load frozen carry gap-recovery contract") from exc
    if recovery_contract.get("status") != "frozen_before_any_recovery_request":
        raise FocusedContextError("carry gap-recovery contract is not frozen")
    if recovery_contract.get("http", {}).get("credentials") != "forbidden":
        raise FocusedContextError("carry gap recovery permits credentials")
    if recovery_contract.get("allowed_host") != "fapi.binance.com" or len(recovery_contract.get("frozen_requests", [])) != 18:
        raise FocusedContextError("carry gap-recovery request boundary changed")
    for required in ("strategy_signal", "return_or_PnL_calculation", "regime_model", "interpolation", "protected_service_access"):
        if required not in recovery_contract.get("prohibited", []):
            raise FocusedContextError(f"carry gap-recovery prohibition missing: {required}")
    for item in recovery_contract.get("bound_inputs", []):
        validate_bound_input(item, "gap-recovery bound input")

    recovery_output = ROOT / "artifacts/agent-level-experiment/btc-focused/carry-gap-recovery-v1"
    recovery_source = load_canonical(recovery_output / "source-manifest.json")
    if recovery_source.get("credentials_used") is not False:
        raise FocusedContextError("carry gap recovery used credentials")
    if recovery_source.get("return_pnl_position_order_or_regime_calculated") is not False:
        raise FocusedContextError("carry gap recovery crossed its data-only boundary")
    recovery_requests = recovery_source.get("requests", [])
    if len(recovery_requests) != 18 or sum(item.get("status") == "valid_exact_response" for item in recovery_requests) != 17:
        raise FocusedContextError("carry gap-recovery response disposition changed")
    failed = [item for item in recovery_requests if item.get("status") != "valid_exact_response"]
    if len(failed) != 1 or failed[0].get("request_id") != "premium-20201201-23":
        raise FocusedContextError("unexpected carry gap-recovery failure")
    if failed[0].get("http_status") != 200 or failed[0].get("raw_sha256") != "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945":
        raise FocusedContextError("missing premium response evidence changed")
    for item in recovery_requests:
        path = ROOT / item["raw_path"]
        if not path.is_file() or sha256_path(path) != item["raw_sha256"]:
            raise FocusedContextError(f"missing or changed gap-recovery raw response: {item['raw_path']}")

    recovery_report = load_canonical(recovery_output / "audit-report.json")
    if recovery_report.get("decision") != "official_rest_gap_recovery_rejected":
        raise FocusedContextError("carry gap-recovery decision changed")
    if recovery_report.get("recovery_passed") is not False or recovery_report.get("strategy_readiness_gate_passed") is not False:
        raise FocusedContextError("rejected carry recovery gates were not preserved")
    if recovery_report.get("actionable_arm_id") != "no_trade" or recovery_report.get("no_interpolation_substitution_strategy_or_pnl") is not True:
        raise FocusedContextError("carry gap recovery no longer fails closed")
    expected_recovery = {
        "markPriceKlines": (192, 52608, 0),
        "indexPriceKlines": (288, 52608, 0),
        "premiumIndexKlines": (168, 52607, 1),
    }
    actual_recovery = {
        series: (values.get("recovered_exact_rows"), values.get("combined_row_count"), values.get("combined_missing_hours"))
        for series, values in recovery_report.get("price_series", {}).items()
    }
    if actual_recovery != expected_recovery:
        raise FocusedContextError("carry gap-recovery counts changed")
    recovery_manifest = load_canonical(recovery_output / "evidence-manifest.json")
    for item in recovery_manifest.get("items", []):
        path = ROOT / item["path"]
        if not path.is_file() or sha256_path(path) != item["sha256"]:
            raise FocusedContextError(f"missing or changed gap-recovery evidence: {item['path']}")

    try:
        carry_mandate = json.loads(
            (ROOT / "config/mandates/retail-btc-delta-neutral-development-v2.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise FocusedContextError("cannot load frozen carry development mandate") from exc
    if carry_mandate.get("status") != "frozen_offline_development_backtest_only":
        raise FocusedContextError("carry development mandate is not frozen offline-only")
    if carry_mandate.get("actionable_arm_id") != "no_trade" or carry_mandate.get("authority", {}).get("live_allocation_usdt") != 0:
        raise FocusedContextError("carry development mandate crosses the zero-capital boundary")
    if carry_mandate.get("data_exception", {}).get("value_imputation_allowed") is not False:
        raise FocusedContextError("carry development mandate permits premium imputation")

    carry_contract_path = ROOT / "research/btc/contracts/btc-positive-funding-carry-v1.json"
    try:
        carry_contract = json.loads(carry_contract_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FocusedContextError("cannot load frozen positive-funding carry contract") from exc
    if carry_contract.get("status") != "frozen_before_any_strategy_outcome":
        raise FocusedContextError("positive-funding carry contract is not frozen")
    if carry_contract.get("actionable_arm_id") != "no_trade" or carry_contract.get("accepted_strategy_arms_before_test"):
        raise FocusedContextError("positive-funding carry contract does not preserve no_trade")
    if carry_contract.get("data", {}).get("premium_index_consumed") is not False:
        raise FocusedContextError("positive-funding carry contract unexpectedly consumes premium index")
    for item in carry_contract.get("bound_inputs", []):
        validate_bound_input(item, "carry strategy bound input")

    carry_output = ROOT / "artifacts/agent-level-experiment/btc-focused/positive-funding-carry-v1"
    carry_report = load_canonical(carry_output / "report.json")
    if carry_report.get("decision") != "development_strategy_rejected":
        raise FocusedContextError("positive-funding carry negative decision changed")
    if carry_report.get("strategy_passed_frozen_development_gates") is not False:
        raise FocusedContextError("rejected positive-funding carry was promoted")
    if carry_report.get("actionable_arm_id") != "no_trade" or carry_report.get("accepted_strategy_arms"):
        raise FocusedContextError("positive-funding carry no longer preserves no_trade")
    data_audit = carry_report.get("data_audit", {})
    if data_audit.get("premium_index_consumed") is not False or data_audit.get("year_2026_accessed") is not False:
        raise FocusedContextError("positive-funding carry crossed its data boundary")
    if data_audit.get("funding_events") != 6576 or data_audit.get("futures_hours") != 52608 or data_audit.get("mark_hours") != 52608:
        raise FocusedContextError("positive-funding carry qualified input counts changed")
    expected_failed_gates = {"no_margin_breach", "return_per_exposed_day_beats_always_on"}
    actual_failed_gates = {key for key, value in carry_report.get("gates", {}).items() if value is not True}
    if actual_failed_gates != expected_failed_gates:
        raise FocusedContextError("positive-funding carry gate disposition changed")
    primary_metrics = carry_report.get("results", {}).get("validation", {}).get("candle-primary-30bps-rt-v1", {}).get("metrics", {})
    severe_metrics = carry_report.get("results", {}).get("validation", {}).get("candle-severe-80bps-rt-v1", {}).get("metrics", {})
    if primary_metrics.get("net_return") != 0.05828262824755079 or severe_metrics.get("net_return") != 0.02611250940174785:
        raise FocusedContextError("positive-funding carry frozen result changed")
    carry_manifest = load_canonical(carry_output / "evidence-manifest.json")
    for item in carry_manifest.get("files", []):
        path = ROOT / item["path"]
        if not path.is_file() or sha256_path(path) != item["sha256"]:
            raise FocusedContextError(f"missing or changed carry strategy evidence: {item['path']}")

    safe_carry_contract_path = (
        ROOT / "research/btc/contracts/btc-safe-delta-neutral-funding-carry-v2.json"
    )
    safe_carry_contract = load_canonical(safe_carry_contract_path)
    safe_boundary = safe_carry_contract.get("action_boundary", {})
    if (
        safe_carry_contract.get("status") != "frozen_before_any_v2_return_calculation"
        or safe_carry_contract.get("experiment_id")
        != "btc-safe-delta-neutral-funding-carry-v2"
        or safe_boundary.get("actionable_arm_id") != "no_trade"
        or any(value is not False for key, value in safe_boundary.items() if key != "actionable_arm_id")
        or safe_carry_contract.get("parameters", {}).get(
            "maximum_notional_fraction_per_leg"
        )
        != 0.25
        or safe_carry_contract.get("risk_model", {}).get(
            "minimum_shocked_margin_equity_to_maintenance_ratio"
        )
        != 2.0
    ):
        raise FocusedContextError("safe carry v2 contract or safety boundary changed")
    for item in safe_carry_contract.get("bound_inputs", []):
        validate_bound_input(item, "safe carry v2 bound input")

    safe_carry_output = (
        ROOT
        / "artifacts/agent-level-experiment/btc-focused/safe-delta-neutral-funding-carry-v2"
    )
    safe_carry_report = load_canonical(safe_carry_output / "report.json")
    safe_primary = safe_carry_report.get("results", {}).get("evaluation", {}).get(
        "candle-primary-30bps-rt-v1", {}
    )
    safe_severe = safe_carry_report.get("results", {}).get("evaluation", {}).get(
        "candle-severe-80bps-rt-v1", {}
    )
    safe_always = safe_carry_report.get("controls", {}).get(
        "always_on_matched_carry_same_25pct_primary", {}
    )
    if (
        safe_carry_report.get("decision")
        != "risk_implementation_passed_timing_alpha_rejected"
        or safe_carry_report.get("risk_implementation_passed") is not True
        or safe_carry_report.get("timing_alpha_passed") is not False
        or safe_carry_report.get("strategy_passed_frozen_development_gates") is not False
        or safe_carry_report.get("actionable_arm_id") != "no_trade"
        or safe_carry_report.get("accepted_strategy_arms")
        or not all(safe_carry_report.get("risk_gates", {}).values())
        or any(safe_carry_report.get("timing_gates", {}).values())
        or safe_primary.get("metrics", {}).get("net_return") != 0.029472894033875447
        or safe_severe.get("metrics", {}).get("net_return") != 0.013325523382885519
        or safe_primary.get("counts", {}).get("margin_breaches") != 0
        or safe_primary.get("counts", {}).get("shock_margin_breaches") != 0
        or safe_primary.get("margin_diagnostics", {}).get(
            "minimum_shocked_margin_equity_to_maintenance_ratio"
        )
        != 9.511693198218383
        or safe_always.get("metrics", {}).get("net_return") != 0.07754022084544906
        or safe_always.get("margin_diagnostics", {}).get(
            "minimum_shocked_margin_equity_to_maintenance_ratio"
        )
        != 2.0719050228513662
        or safe_carry_report.get("data_audit", {}).get("year_2026_accessed") is not False
    ):
        raise FocusedContextError("safe carry v2 result or disposition changed")

    safe_manifest = load_canonical(safe_carry_output / "evidence-manifest.json")
    if (
        safe_manifest.get("experiment_id") != "btc-safe-delta-neutral-funding-carry-v2"
        or safe_manifest.get("actionable_arm_id") != "no_trade"
        or safe_manifest.get("no_strategy_arm_accepted_or_actionable") is not True
    ):
        raise FocusedContextError("safe carry v2 evidence manifest changed")
    for item in safe_manifest.get("artifacts", []) + safe_manifest.get("implementation", []):
        validate_bound_input(item, "safe carry v2 evidence")
    validate_bound_input(safe_manifest.get("bound_contract", {}), "safe carry v2 contract")

    safe_audit = load_canonical(safe_carry_output / "audit/audit-report.json")
    if (
        safe_audit.get("decision")
        != "safe_carry_v2_risk_pass_timing_rejection_independently_reproduced"
        or safe_audit.get("actionable_arm_id") != "no_trade"
        or safe_audit.get("strategy_arm_accepted") is not False
        or not all(safe_audit.get("checks", {}).values())
    ):
        raise FocusedContextError("safe carry v2 audit changed")
    safe_audit_manifest = load_canonical(safe_carry_output / "audit/evidence-manifest.json")
    if (
        safe_audit_manifest.get("decision")
        != "risk_implementation_passed_timing_alpha_rejected_and_closed"
        or safe_audit_manifest.get("actionable_arm_id") != "no_trade"
        or safe_audit_manifest.get("no_strategy_arm_accepted_or_actionable") is not True
    ):
        raise FocusedContextError("safe carry v2 audit manifest changed")
    for item in safe_audit_manifest.get("artifacts", []):
        validate_bound_input(item, "safe carry v2 replay or audit evidence")

    scorecard_contract_path = ROOT / "research/btc/contracts/btc-backtest-scorecard-v1.json"
    scorecard_contract = load_canonical(scorecard_contract_path)
    if scorecard_contract.get("status") != "frozen_before_supplemental_recalculation":
        raise FocusedContextError("BTC scorecard contract is not frozen")
    if scorecard_contract.get("actionable_arm_id") != "no_trade" or scorecard_contract.get("accepted_strategy_arms"):
        raise FocusedContextError("BTC scorecard contract does not preserve no_trade")
    for item in scorecard_contract.get("bound_inputs", []):
        validate_bound_input(item, "scorecard bound input")

    trial_path = ROOT / "research/btc/STRATEGY_TRIALS.jsonl"
    trial_raw = trial_path.read_text(encoding="utf-8")
    if not trial_raw or not trial_raw.endswith("\n"):
        raise FocusedContextError("BTC strategy trial registry is empty or unterminated")
    trial_families: set[str] = set()
    trial_ids: set[str] = set()
    for sequence, line in enumerate(trial_raw.splitlines(), start=1):
        row = json.loads(line)
        if line != canonical_line(row) or row.get("sequence") != sequence:
            raise FocusedContextError(f"invalid canonical strategy trial line {sequence}")
        if row.get("experiment_id") in trial_ids or row.get("family_history_complete") is not False:
            raise FocusedContextError("retrospective trial registry is duplicate or falsely complete")
        trial_ids.add(row["experiment_id"])
        trial_families.add(row["strategy_family"])
    if len(trial_ids) != 10:
        raise FocusedContextError("unexpected retrospective BTC strategy trial count")

    scorecard_output = ROOT / "artifacts/agent-level-experiment/btc-focused/backtest-scorecard-v1"
    scorecard_report = load_canonical(scorecard_output / "report.json")
    if scorecard_report.get("decision") != "scorecard_infrastructure_passed_no_strategy_accepted":
        raise FocusedContextError("BTC scorecard infrastructure decision changed")
    if scorecard_report.get("historical_dispositions_changed") is not False:
        raise FocusedContextError("BTC scorecard claims a historical disposition change")
    if scorecard_report.get("actionable_arm_id") != "no_trade" or scorecard_report.get("accepted_strategy_arms"):
        raise FocusedContextError("BTC scorecard report does not preserve no_trade")
    expected_scorecards = {
        "btc-fixed-20d-10d-breakout-legacy-control",
        "btc-positive-funding-carry-v1",
        "btc-regime-routing-s2-ewma-v2",
    }
    if set(scorecard_report.get("scorecard_dispositions", {})) != expected_scorecards or set(
        scorecard_report.get("scorecard_dispositions", {}).values()
    ) != {"supplemental_evidence_insufficient"}:
        raise FocusedContextError("BTC supplemental scorecard dispositions changed")
    if scorecard_report.get("lineage", {}).get("year_2026_accessed") is not False:
        raise FocusedContextError("BTC scorecard crossed the 2025 evidence boundary")

    scorecard_manifest = load_canonical(scorecard_output / "manifest.json")
    if any(
        scorecard_manifest.get(key) is not False
        for key in (
            "network_or_protected_service_accessed",
            "partial_ob0_accessed",
            "promotion_evidence",
            "year_2026_accessed",
        )
    ):
        raise FocusedContextError("BTC scorecard manifest crossed its isolation boundary")
    for item in scorecard_manifest.get("files", []):
        path = scorecard_output / item["name"]
        if not path.is_file() or sha256_path(path) != item["sha256"]:
            raise FocusedContextError(f"missing or changed scorecard evidence: {item['name']}")
    scorecards = {
        name: load_canonical(scorecard_output / f"{name}-scorecard.json")
        for name in expected_scorecards
    }
    if any(
        value.get("actionable_arm_id") != "no_trade"
        or value.get("accepted_strategy_arms")
        or value.get("promotion_evidence") is not False
        for value in scorecards.values()
    ):
        raise FocusedContextError("a supplemental BTC scorecard no longer fails closed")
    scored_carry = scorecards["btc-positive-funding-carry-v1"]
    if scored_carry.get("trades", {}).get("independent_trade_cohorts") != 6:
        raise FocusedContextError("carry scorecard independent trade evidence changed")
    if scored_carry.get("gates", {}).get("universal", {}).get("independent_blocks", {}).get("status") != "insufficient":
        raise FocusedContextError("carry scorecard block insufficiency changed")
    if scored_carry.get("gates", {}).get("role", {}).get("paired_control_separation", {}).get("status") != "fail":
        raise FocusedContextError("carry scorecard matched-control failure changed")

    risk_contract_path = ROOT / "research/btc/contracts/btc-multidimensional-risk-foundation-v1.json"
    risk_contract = load_canonical(risk_contract_path)
    if risk_contract.get("status") != "frozen_before_implementation":
        raise FocusedContextError("multidimensional risk foundation is not frozen")
    risk_boundary = risk_contract.get("action_boundary", {})
    if risk_boundary.get("actionable_arm_id") != "no_trade" or risk_boundary.get("accepted_strategy_arms"):
        raise FocusedContextError("multidimensional risk foundation does not preserve no_trade")
    if any(
        risk_boundary.get(key) is not False
        for key in (
            "order_intent_creation_allowed",
            "production_signal_creation_allowed",
            "strategy_or_pnl_evaluation_allowed",
        )
    ):
        raise FocusedContextError("multidimensional risk foundation crosses its research-only boundary")
    if risk_contract.get("clocks") != {
        "fast_shock_monitor": "4h_completed_observations_only",
        "slow_risk_budget": "daily_completed_observations_only",
    }:
        raise FocusedContextError("multidimensional risk dual-clock design changed")
    fusion_policy = risk_contract.get("fusion_policy", {})
    if fusion_policy.get("automatic_releveraging_allowed") is not False:
        raise FocusedContextError("multidimensional risk foundation permits automatic re-leveraging")
    if fusion_policy.get("existing_position_rule") != "minimum_of_current_allocation_and_all_usable_required_risk_caps":
        raise FocusedContextError("intratrade downward-only rule changed")
    expected_axes = {"volatility", "downside_tail", "jump_change", "implied_risk", "liquidity_execution"}
    if {item.get("axis") for item in risk_contract.get("research_axes", [])} != expected_axes:
        raise FocusedContextError("multidimensional risk axes changed")
    if risk_contract.get("isolation", {}).get("network_access_allowed") is not False:
        raise FocusedContextError("risk foundation implementation permits network access")

    dvol_contract_path = ROOT / "research/btc/contracts/btc-deribit-dvol-source-pilot-v2.json"
    dvol_contract = load_canonical(dvol_contract_path)
    if dvol_contract.get("status") != "frozen_before_any_request":
        raise FocusedContextError("DVOL source pilot contract is not frozen")
    if dvol_contract.get("endpoint", {}).get("credentials") != "forbidden":
        raise FocusedContextError("DVOL source pilot permits credentials")
    dvol_boundary = dvol_contract.get("action_boundary", {})
    if dvol_boundary.get("actionable_arm_id") != "no_trade" or dvol_boundary.get("accepted_strategy_arms"):
        raise FocusedContextError("DVOL source pilot does not preserve no_trade")
    if dvol_boundary.get("risk_model_input_approval_allowed") is not False:
        raise FocusedContextError("bounded DVOL pilot permits historical model-input approval")
    if len(dvol_contract.get("data_requests", [])) != 3 or any(
        request.get("currency") != "BTC"
        or request.get("resolution") != "1D"
        or request.get("start_timestamp", 0) >= request.get("end_timestamp", 0)
        or request.get("end_timestamp", 0) >= 1767225600000
        for request in dvol_contract.get("data_requests", [])
    ):
        raise FocusedContextError("DVOL bounded request windows changed or cross into 2026")

    dvol_output = ROOT / "artifacts/agent-level-experiment/btc-focused/deribit-dvol-source-pilot-v2"
    dvol_source = load_canonical(dvol_output / "source-manifest.json")
    if dvol_source.get("credentials_used") is not False or len(dvol_source.get("requests", [])) != 3:
        raise FocusedContextError("DVOL source manifest crossed its public bounded-pilot boundary")
    if any(
        item.get("http_status") != 200
        or item.get("jsonrpc_error") is not None
        or item.get("parse_error") is not None
        or item.get("audit", {}).get("rows") != 15
        or item.get("audit", {}).get("duplicate_timestamps") != 0
        or item.get("audit", {}).get("non_daily_gap_count") != 0
        or item.get("audit", {}).get("out_of_bounds_rows") != 0
        or item.get("audit", {}).get("failures")
        for item in dvol_source.get("requests", [])
    ):
        raise FocusedContextError("DVOL bounded request evidence changed")
    if any(
        item.get("http_status") != 200 or item.get("missing_required_phrases")
        for item in dvol_source.get("documentation", [])
    ):
        raise FocusedContextError("DVOL official documentation evidence changed")

    dvol_report = load_canonical(dvol_output / "audit-report.json")
    if dvol_report.get("decision") != "technical_pilot_passed_historical_use_blocked":
        raise FocusedContextError("DVOL technical-only disposition changed")
    if dvol_report.get("full_historical_risk_model_input_approved") is not False:
        raise FocusedContextError("DVOL bounded pilot was promoted to historical model input")
    if dvol_report.get("actionable_arm_id") != "no_trade":
        raise FocusedContextError("DVOL bounded pilot no longer preserves no_trade")
    if dvol_report.get("no_strategy_feature_label_return_pnl_regime_or_risk_model_computed") is not True:
        raise FocusedContextError("DVOL bounded pilot crossed its source-only boundary")
    expected_dvol_blockers = {
        "complete_history_not_tested",
        "effective_dated_methodology_archive_not_established",
        "historical_publication_and_revision_semantics_not_established",
        "private_research_retention_rights_not_established",
    }
    if set(dvol_report.get("historical_use_blockers", [])) != expected_dvol_blockers:
        raise FocusedContextError("DVOL historical-use blockers changed")
    dvol_manifest = load_canonical(dvol_output / "evidence-manifest.json")
    for item in dvol_manifest.get("files", []):
        path = ROOT / item["path"]
        if not path.is_file() or sha256_path(path) != item["sha256"]:
            raise FocusedContextError(f"missing or changed DVOL evidence: {item['path']}")

    har_contract_path = ROOT / "research/btc/contracts/btc-har-rv-risk-forecast-v1.json"
    har_contract = load_canonical(har_contract_path)
    if har_contract.get("status") != "frozen_before_implementation_and_results":
        raise FocusedContextError("HAR-RV contract is not frozen")
    har_boundary = har_contract.get("action_boundary", {})
    if har_boundary.get("actionable_arm_id") != "no_trade" or har_boundary.get("accepted_strategy_arms"):
        raise FocusedContextError("HAR-RV contract does not preserve no_trade")
    if har_boundary.get("allocation_or_risk_cap_mapping_allowed") is not False:
        raise FocusedContextError("HAR-RV contract permits action mapping")
    if har_contract.get("data", {}).get("sealed_2026_access_allowed") is not False:
        raise FocusedContextError("HAR-RV contract permits sealed data")
    for item in har_contract.get("bound_inputs", []):
        validate_bound_input(item, "HAR-RV bound input")

    har_output = ROOT / "artifacts/agent-level-experiment/btc-focused/har-rv-risk-forecast-v1"
    har_report = load_canonical(har_output / "report.json")
    if har_report.get("decision") != "development_forecast_challenger_rejected":
        raise FocusedContextError("HAR-RV coverage rejection changed")
    if har_report.get("development_forecast_gates_passed") is not False:
        raise FocusedContextError("rejected HAR-RV experiment was promoted")
    if har_report.get("actionable_arm_id") != "no_trade" or har_report.get("accepted_strategy_arms"):
        raise FocusedContextError("HAR-RV report does not preserve no_trade")
    if har_report.get("risk_cap_eligible") is not False or har_report.get("promotion_evidence") is not False:
        raise FocusedContextError("HAR-RV report was made operational or promotional")
    if har_report.get("no_strategy_return_pnl_allocation_or_execution_computed") is not True:
        raise FocusedContextError("HAR-RV report crossed its forecast-only boundary")
    failed_har_gates = {key for key, value in har_report.get("gates", {}).items() if value is not True}
    if failed_har_gates != {"common_row_coverage"}:
        raise FocusedContextError("HAR-RV frozen gate disposition changed")
    one_day = har_report.get("horizons", {}).get("1d", {})
    seven_day = har_report.get("horizons", {}).get("7d", {})
    if one_day.get("scores", {}).get("observations") != 2011 or seven_day.get("scores", {}).get("observations") != 1921:
        raise FocusedContextError("HAR-RV common forecast counts changed")
    if one_day.get("coverage", {}).get("annual", {}).get("2021", {}).get("coverage") != 0.4958904109589041:
        raise FocusedContextError("HAR-RV one-day coverage evidence changed")
    if seven_day.get("coverage", {}).get("annual", {}).get("2021", {}).get("coverage") != 0.4136986301369863:
        raise FocusedContextError("HAR-RV seven-day coverage evidence changed")
    if one_day.get("scores", {}).get("har", {}).get("mean_qlike") != -6.173004608204588:
        raise FocusedContextError("HAR-RV one-day forecast score changed")
    har_manifest = load_canonical(har_output / "evidence-manifest.json")
    for name, metadata in har_manifest.get("artifacts", {}).items():
        path = har_output / name
        if not path.is_file() or sha256_path(path) != metadata.get("sha256"):
            raise FocusedContextError(f"missing or changed HAR-RV artifact: {name}")
    for item in har_manifest.get("source_files", []):
        path = ROOT / item["path"]
        if not path.is_file() or sha256_path(path) != item["sha256"]:
            raise FocusedContextError(f"missing or changed HAR-RV source: {item['path']}")
    replay = ROOT / "artifacts/agent-level-experiment/btc-focused/replays/har-rv-risk-forecast-v1-replay-20260831T0230"
    for name in har_manifest.get("artifacts", {}):
        if not (replay / name).is_file() or sha256_path(replay / name) != sha256_path(har_output / name):
            raise FocusedContextError(f"HAR-RV replay differs: {name}")

    combination_contract_path = (
        ROOT / "research/btc/contracts/btc-score-combination-foundation-v1.json"
    )
    combination_contract = load_canonical(combination_contract_path)
    if combination_contract.get("status") != "frozen_before_implementation":
        raise FocusedContextError("score-combination foundation contract is not frozen")
    combination_boundary = combination_contract.get("action_boundary", {})
    if (
        combination_boundary.get("actionable_arm_id") != "no_trade"
        or combination_boundary.get("accepted_strategy_arms")
    ):
        raise FocusedContextError("score-combination foundation crossed its action boundary")
    for key in (
        "order_intent_creation_allowed",
        "production_signal_creation_allowed",
        "real_market_score_combination_allowed",
        "strategy_direction_or_pnl_evaluation_allowed",
    ):
        if combination_boundary.get(key) is not False:
            raise FocusedContextError(f"score-combination foundation permits {key}")
    for item in combination_contract.get("bound_inputs", []):
        validate_bound_input(item, "score-combination bound input")

    combination_output = (
        ROOT / "artifacts/agent-level-experiment/btc-focused/score-combination-foundation-v1"
    )
    combination_report = load_canonical(combination_output / "synthetic-qualification-report.json")
    if combination_report.get("decision") != "passed_synthetic_score_combination_infrastructure_only":
        raise FocusedContextError("score-combination infrastructure disposition changed")
    if (
        combination_report.get("actionable_arm_id") != "no_trade"
        or combination_report.get("accepted_strategy_arms")
    ):
        raise FocusedContextError("score-combination report created actionable authority")
    invariants = combination_report.get("invariants", {})
    required_false = {
        "current_rejected_scores_combined",
        "fitted_or_dynamic_weights_used",
        "master_market_score_created",
        "mcs4_activated",
        "order_position_signal_or_strategy_action_created",
        "partial_ob0_accessed",
        "protected_services_accessed",
        "risk_cap_fusion_reimplemented",
        "sealed_or_ineligible_2026_accessed",
        "strategy_or_pnl_evaluated",
    }
    if any(invariants.get(key) is not False for key in required_false):
        raise FocusedContextError("score-combination synthetic boundary changed")
    if invariants.get("market_data_or_outcomes_opened") != 0:
        raise FocusedContextError("score-combination report accessed market outcomes")
    ensemble = combination_report.get("synthetic_results", {}).get("ensemble_score", {})
    if (
        ensemble.get("evidence_status") != "development"
        or ensemble.get("actionable_arm_id") != "no_trade"
        or ensemble.get("strategy_action_created") is not False
    ):
        raise FocusedContextError("synthetic ensemble received action or acceptance status")
    combination_manifest = load_canonical(combination_output / "evidence-manifest.json")
    if combination_manifest.get("market_values_used") is not False:
        raise FocusedContextError("score-combination manifest claims market values")
    for item in combination_manifest.get("files", []):
        path = ROOT / item["path"]
        if not path.is_file() or sha256_path(path) != item["sha256"]:
            raise FocusedContextError(f"missing or changed score-combination evidence: {item['path']}")
    combination_replay = (
        ROOT
        / "artifacts/agent-level-experiment/btc-focused/replays/score-combination-foundation-v1-20260831T1800"
    )
    for name in ("synthetic-qualification-report.json", "evidence-manifest.json"):
        if (
            not (combination_replay / name).is_file()
            or sha256_path(combination_replay / name) != sha256_path(combination_output / name)
        ):
            raise FocusedContextError(f"score-combination replay differs: {name}")

    direction_tracker = load_canonical(
        ROOT / "research/btc/BTC_STRATEGY_DIRECTION_TRACKER.json"
    )
    if direction_tracker.get("schema_version") != "btc-strategy-direction-tracker-v1":
        raise FocusedContextError("unsupported BTC strategy-direction tracker")
    if direction_tracker.get("status") != "TNE1_A_v2_rejected_insufficient_frozen_trigger_sample":
        raise FocusedContextError("BTC strategy direction does not preserve the TNE1-A rejection")
    if direction_tracker.get("active_experiment") is not None:
        raise FocusedContextError("strategy-direction tracker did not close the rejected experiment")
    if (
        direction_tracker.get("accepted_strategy_arms")
        or direction_tracker.get("action_boundary", {}).get("actionable_arm_id") != "no_trade"
    ):
        raise FocusedContextError("strategy-direction tracker claims accepted or actionable alpha")
    direction_boundary = direction_tracker.get("action_boundary", {})
    for key in (
        "historical_non_pnl_event_outcome_access_allowed",
        "order_intent_creation_allowed",
        "production_signal_creation_allowed",
        "strategy_backtest_allowed_before_contract_freeze",
        "strategy_market_return_or_pnl_access_allowed",
    ):
        if direction_boundary.get(key) is not False:
            raise FocusedContextError(f"strategy-direction tracker permits {key}")
    directions = direction_tracker.get("direction_universe", [])
    if not isinstance(directions, list) or len(directions) != 9:
        raise FocusedContextError("strategy-direction tracker must preserve nine directional legs")
    selected = [
        row
        for row in directions
        if row.get("direction_id") == "distributed_cusum_trend_onset_upside_long"
    ]
    if (
        len(selected) != 1
        or selected[0].get("status")
        != "rejected_TNE1_A_v2_insufficient_frozen_trigger_sample"
    ):
        raise FocusedContextError("strategy-direction tracker lost the frozen TNE1-A rejection")
    if direction_tracker.get("active_direction_id") != "distributed_cusum_trend_onset_upside_long":
        raise FocusedContextError("strategy-direction tracker drifted from CUSUM trend onset")
    candidate = direction_tracker.get("candidate", {})
    if (
        candidate.get("candidate_id") != "btc-cusum-trend-onset-v1"
        or candidate.get("hypothesis_state")
        != "TNE1_A_v2_rejected_frozen_trigger_sample_gates_labels_and_models_not_opened"
        or candidate.get("routing_family") != "btc_directional_trend"
    ):
        raise FocusedContextError("CUSUM trend-onset candidate identity or state changed")
    if len(candidate.get("parameters_deferred_to_later_strategy_backtest_id", [])) < 5:
        raise FocusedContextError("upside-breakout strategy parameters are not explicitly deferred")
    if "using_sealed_or_ineligible_2026_as_clean_holdout" not in candidate.get(
        "prohibited", []
    ):
        raise FocusedContextError("upside-breakout tracker does not preserve the 2026 boundary")
    for item in direction_tracker.get("context_lineage", []):
        validate_bound_input(item, "strategy-direction context lineage")

    tne1_contract = load_canonical(
        ROOT / "research/btc/contracts/btc-cusum-trend-onset-v2.json"
    )
    if (
        tne1_contract.get("status") != "frozen_before_historical_trigger_access"
        or tne1_contract.get("experiment_id") != "btc-cusum-trend-onset-tne1-v2"
        or tne1_contract.get("action_boundary", {}).get("actionable_arm_id") != "no_trade"
    ):
        raise FocusedContextError("TNE1-v2 contract identity or safety boundary changed")
    for item in tne1_contract.get("bound_inputs", []):
        validate_bound_input(item, "TNE1-v2 bound input")

    tne1_output = (
        ROOT
        / "artifacts/agent-level-experiment/btc-focused/cusum-trend-onset-v1/tne1-v2"
    )
    trigger_output = tne1_output / "trigger"
    trigger_report = load_canonical(trigger_output / "trigger-gate-report.json")
    trigger_gate = trigger_report.get("trigger_count_gate_report", {})
    expected_year_counts = {
        "2017": 9,
        "2018": 13,
        "2019": 23,
        "2020": 30,
        "2021": 29,
        "2022": 27,
        "2023": 32,
        "2024": 34,
        "2025": 32,
    }
    expected_evaluation_counts = {
        "2021": 29,
        "2022": 27,
        "2023": 32,
        "2024": 34,
        "2025": 32,
    }
    if (
        trigger_report.get("experiment_id") != "btc-cusum-trend-onset-tne1-v2"
        or trigger_report.get("phase") != "trigger"
        or trigger_report.get("actionable_arm_id") != "no_trade"
        or trigger_report.get("aggregate_rows_1h") != 73234
        or trigger_report.get("source_rows") != 878985
        or trigger_report.get("total_trigger_count") != 229
        or trigger_report.get("model_ready_trigger_count") != 229
        or trigger_report.get("label_phase_allowed") is not False
        or trigger_report.get("catalogue_digest")
        != "0c5972dccb5fd9e6605a71690b76056e52e00bafa6663e9d5c2b4c63bdc3b5e8"
    ):
        raise FocusedContextError("TNE1-v2 frozen trigger summary changed")
    if (
        trigger_gate.get("passed") is not False
        or trigger_gate.get("pre_2021_model_ready_count") != 75
        or trigger_gate.get("distinct_model_ready_month_count") != 93
        or trigger_gate.get("model_ready_year_counts") != expected_year_counts
        or trigger_gate.get("evaluation_year_model_ready_counts")
        != expected_evaluation_counts
    ):
        raise FocusedContextError("TNE1-v2 frozen rejection gates changed")
    expected_checks = {
        "distinct_months_minimum": True,
        "maximum_year_share": True,
        "model_ready_minimum": False,
        "per_evaluation_year_minimum": False,
        "pre_2021_minimum": False,
        "top_three_month_share": True,
    }
    if trigger_gate.get("checks") != expected_checks:
        raise FocusedContextError("TNE1-v2 gate disposition changed")
    trigger_manifest = load_canonical(trigger_output / "evidence-manifest.json")
    for item in trigger_manifest.get("bound_inputs", []) + trigger_manifest.get("artifacts", []):
        validate_bound_input(item, "TNE1-v2 trigger evidence")
    for forbidden_phase in ("label", "labels", "model", "models"):
        if (tne1_output / forbidden_phase).exists():
            raise FocusedContextError(f"TNE1-v2 prohibited {forbidden_phase} output exists")

    bex1_contract = load_canonical(
        ROOT / "research/btc/contracts/btc-breakout-event-catalogue-v5.json"
    )
    if (
        bex1_contract.get("status") != "frozen_before_historical_event_outcomes"
        or bex1_contract.get("experiment_id")
        != "btc-upside-compression-breakout-v1-bex1-v5"
    ):
        raise FocusedContextError("BEX1-v5 contract identity or frozen status changed")
    if bex1_contract.get("action_boundary", {}).get("actionable_arm_id") != "no_trade":
        raise FocusedContextError("BEX1-v5 contract crossed no_trade boundary")
    for item in bex1_contract.get("bound_inputs", []):
        validate_bound_input(item, "BEX1-v5 bound input")
    bex1_output = (
        ROOT
        / "artifacts/agent-level-experiment/btc-focused/upside-compression-breakout-v1/bex1-v5"
    )
    bex1_report = load_canonical(bex1_output / "event-preflight-report.json")
    expected_counts = {
        "episode_count": 92,
        "confirmed_episode_count": 36,
        "model_ready_episode_count": 36,
        "continuation_count": 12,
        "range_reentry_count": 24,
        "right_censored_count": 0,
    }
    if any(bex1_report.get(key) != value for key, value in expected_counts.items()):
        raise FocusedContextError("BEX1-v5 frozen count evidence changed")
    if (
        bex1_report.get("actionable_arm_id") != "no_trade"
        or bex1_report.get("source_last_close_before_2026") is not True
        or bex1_report.get("research_disposition") != "development_event_catalogue_only"
    ):
        raise FocusedContextError("BEX1-v5 safety disposition changed")
    bex1_manifest = load_canonical(bex1_output / "evidence-manifest.json")
    for item in bex1_manifest.get("bound_inputs", []) + bex1_manifest.get("artifacts", []):
        validate_bound_input(item, "BEX1-v5 evidence")

    continuation_mandate = load_canonical(
        ROOT / "config/mandates/retail-btc-spot-cross-market-input-research-v1.json"
    )
    continuation_authority = continuation_mandate.get("authority", {})
    if continuation_mandate.get("status") != "frozen_offline_information_research_only":
        raise FocusedContextError("spot/perpetual input mandate is not frozen offline-only")
    if continuation_authority.get("live_allocation_usdt") != 0 or any(
        continuation_authority.get(key) is not False
        for key in (
            "account_connection_allowed",
            "credentials_allowed",
            "live_trading_allowed",
            "order_submission_allowed",
            "paper_orders_sent_to_exchange_allowed",
            "transfers_allowed",
        )
    ) or continuation_mandate.get("candidate_output", {}).get("perpetual_position_allowed") is not False:
        raise FocusedContextError("spot/perpetual input mandate crosses its zero-capital boundary")

    continuation_tracker = load_canonical(
        ROOT / "research/btc/BTC_SPOT_PERP_CONTINUATION_TRACKER.json"
    )
    if (
        continuation_tracker.get("status")
        != "D1_v3_rejected_and_closed_after_information_gate"
        or continuation_tracker.get("active_experiment") is not None
        or continuation_tracker.get("accepted_strategy_arms")
        or continuation_tracker.get("candidate", {}).get("strategy_status")
        != "information_model_rejected_strategy_not_tested_not_accepted"
        or continuation_tracker.get("d1_evidence", {}).get("model_fitted") is not True
        or continuation_tracker.get("d1_evidence", {}).get("label_gate_passed") is not True
        or continuation_tracker.get("d1_evidence", {}).get("information_gate_passed")
        is not False
    ):
        raise FocusedContextError("spot/perpetual continuation tracker overstates D1 evidence")
    continuation_boundary = continuation_tracker.get("action_boundary", {})
    if continuation_boundary.get("actionable_arm_id") != "no_trade" or any(
        continuation_boundary.get(key) is not False
        for key in (
            "future_return_label_allowed",
            "model_fit_allowed",
            "order_intent_creation_allowed",
            "position_creation_allowed",
            "strategy_return_or_pnl_allowed",
        )
    ):
        raise FocusedContextError("spot/perpetual continuation tracker opens model or action")

    continuation_catalog = load_canonical(
        ROOT / "research/btc/BTC_SPOT_PERP_CONTINUATION_EVIDENCE_CATALOG.json"
    )
    expected_continuation_dispositions = [
        "rejected_feature_readiness_after_hourly_gap_resets",
        "preflight_invalid_no_audit_report",
        "passed_label_blind_data_qualification_only",
        "preflight_invalid_before_any_D1_historical_row",
        "rejected_at_frozen_2021_label_coverage_gate_before_model",
        "rejected_and_closed_after_endpoint_validated_information_gate",
    ]
    if (
        continuation_catalog.get("actionable_arm_id") != "no_trade"
        or continuation_catalog.get("strategy_or_model_accepted") is not False
        or [entry.get("disposition") for entry in continuation_catalog.get("entries", [])]
        != expected_continuation_dispositions
    ):
        raise FocusedContextError("spot/perpetual continuation evidence lineage changed")

    d0_v1_contract = load_canonical(
        ROOT / "research/btc/contracts/btc-spot-perp-continuation-data-audit-v1.json"
    )
    d0_v1_output = (
        ROOT / "artifacts/agent-level-experiment/btc-focused/spot-perp-continuation-d0-v1"
    )
    d0_v1_report = load_canonical(d0_v1_output / "audit-report.json")
    if (
        d0_v1_contract.get("status") != "frozen_before_d0_acquisition"
        or d0_v1_report.get("decision") != "d0_rejected_label_blind_data_qualification"
        or d0_v1_report.get("d0_passed") is not False
        or d0_v1_report.get("actionable_arm_id") != "no_trade"
        or d0_v1_report.get("common_hourly", {}).get("segment_count") != 19
        or d0_v1_report.get("feature_availability", {}).get("pre_2021_count") != 65
    ):
        raise FocusedContextError("D0 v1 negative data evidence changed")
    d0_v1_manifest = load_canonical(d0_v1_output / "evidence-manifest.json")
    for item in d0_v1_manifest.get("files", []):
        validate_bound_input(item, "D0 v1 evidence")

    d0_v2_contract = load_canonical(
        ROOT / "research/btc/contracts/btc-spot-perp-continuation-data-audit-v2.json"
    )
    d0_v2_output = (
        ROOT / "artifacts/agent-level-experiment/btc-focused/spot-perp-continuation-d0-v2"
    )
    d0_v2_source = load_canonical(d0_v2_output / "source-manifest.json")
    if (
        d0_v2_contract.get("status") != "frozen_before_d0_v2_acquisition"
        or d0_v2_source.get("archive_failures") != 0
        or len(d0_v2_source.get("spot_archive_records", [])) != 76
        or d0_v2_source.get("credentials_used") is not False
        or d0_v2_source.get("acquisition_has_no_future_return_label_forecast_strategy_or_pnl")
        is not True
        or (d0_v2_output / "audit-report.json").exists()
    ):
        raise FocusedContextError("D0 v2 preserved parser-preflight evidence changed")
    for item in d0_v2_source.get("spot_archive_records", []):
        validate_bound_input(
            {"path": item.get("archive_path"), "sha256": item.get("archive_sha256")},
            "D0 v2 spot archive",
        )
        sidecar = ROOT / item["official_checksum_path"]
        if (
            not sidecar.is_file()
            or item.get("archive_sha256") != item.get("official_checksum")
            or sidecar.read_text(encoding="utf-8").split()[0].lower()
            != item.get("official_checksum")
        ):
            raise FocusedContextError("D0 v2 official sidecar evidence changed")

    d0_v3_contract = load_canonical(
        ROOT / "research/btc/contracts/btc-spot-perp-continuation-data-audit-v3.json"
    )
    if d0_v3_contract.get("status") != "frozen_before_d0_v3_acquisition":
        raise FocusedContextError("D0 v3 contract is not frozen")
    for item in d0_v3_contract.get("bound_inputs", []):
        validate_bound_input(item, "D0 v3 bound input")
    d0_v3_output = (
        ROOT / "artifacts/agent-level-experiment/btc-focused/spot-perp-continuation-d0-v3"
    )
    d0_v3_source = load_canonical(d0_v3_output / "source-manifest.json")
    if (
        d0_v3_source.get("archive_failures") != 0
        or len(d0_v3_source.get("archive_records", [])) != 148
        or d0_v3_source.get("credentials_used") is not False
        or d0_v3_source.get("acquisition_has_no_future_return_label_forecast_strategy_or_pnl")
        is not True
    ):
        raise FocusedContextError("D0 v3 source qualification changed")
    d0_v3_report = load_canonical(d0_v3_output / "audit-report.json")
    if (
        d0_v3_report.get("decision") != "d0_v3_passed_label_blind_data_qualification"
        or d0_v3_report.get("d0_passed") is not True
        or d0_v3_report.get("actionable_arm_id") != "no_trade"
        or not all(d0_v3_report.get("gate_results", {}).values())
        or d0_v3_report.get("common_daily", {}).get("coverage_2020_2025") != 1.0
        or d0_v3_report.get("common_daily", {}).get("segment_count") != 1
        or d0_v3_report.get("feature_availability", {}).get("pre_2021_count") != 391
        or d0_v3_report.get("feature_availability", {}).get("by_year")
        != {
            "2019": 25,
            "2020": 366,
            "2021": 365,
            "2022": 365,
            "2023": 365,
            "2024": 366,
            "2025": 365,
        }
        or d0_v3_report.get(
            "no_future_return_label_forecast_strategy_pnl_position_or_order_computed"
        )
        is not True
    ):
        raise FocusedContextError("D0 v3 passed data evidence changed")
    d0_v3_manifest = load_canonical(d0_v3_output / "evidence-manifest.json")
    for item in d0_v3_manifest.get("files", []):
        validate_bound_input(item, "D0 v3 evidence")

    continuation_tracker = load_canonical(
        ROOT / "research/btc/BTC_SPOT_PERP_CONTINUATION_TRACKER.json"
    )
    continuation_catalog = load_canonical(
        ROOT / "research/btc/BTC_SPOT_PERP_CONTINUATION_EVIDENCE_CATALOG.json"
    )
    if (
        continuation_tracker.get("status")
        != "D1_v3_rejected_and_closed_after_information_gate"
        or continuation_tracker.get("active_experiment") is not None
        or continuation_tracker.get("accepted_strategy_arms")
        or continuation_tracker.get("d1_evidence", {}).get("model_fitted") is not True
        or continuation_tracker.get("d1_evidence", {}).get("information_gate_passed")
        is not False
        or continuation_tracker.get("d1_evidence", {}).get("actual_2021_coverage")
        != 1.0
        or continuation_catalog.get("strategy_or_model_accepted") is not False
        or continuation_catalog.get("actionable_arm_id") != "no_trade"
    ):
        raise FocusedContextError("D1 continuation tracker or catalogue changed")

    d1_v1_path = (
        ROOT / "research/btc/contracts/btc-spot-perp-continuation-information-d1-v1.json"
    )
    d1_v2_path = (
        ROOT / "research/btc/contracts/btc-spot-perp-continuation-information-d1-v2.json"
    )
    d1_v1 = load_canonical(d1_v1_path)
    d1_v2 = load_canonical(d1_v2_path)
    if (
        d1_v1.get("status") != "frozen_before_any_D1_label_or_model_materialization"
        or d1_v2.get("status")
        != "frozen_before_any_D1_v2_historical_feature_label_or_model_access"
        or d1_v2.get("base_contract", {}).get("sha256") != sha256_path(d1_v1_path)
        or d1_v2.get("action_boundary", {}).get("actionable_arm_id") != "no_trade"
        or any(
            d1_v2.get("action_boundary", {}).get(key) is not False
            for key in (
                "cost_or_execution_model_allowed",
                "order_intent_creation_allowed",
                "partial_ob0_access_allowed",
                "perpetual_position_allowed",
                "position_or_pnl_calculation_allowed",
                "production_signal_creation_allowed",
                "sealed_or_ineligible_2026_access_allowed",
                "strategy_backtest_allowed",
            )
        )
    ):
        raise FocusedContextError("D1 frozen contract lineage or safety boundary changed")

    d1_output = (
        ROOT / "artifacts/agent-level-experiment/btc-focused/spot-perp-continuation-d1-v2"
    )
    d1_feature_report = load_canonical(d1_output / "features/feature-gate-report.json")
    d1_label_report = load_canonical(d1_output / "labels/label-gate-report.json")
    if (
        d1_feature_report.get("feature_gate_passed") is not True
        or d1_feature_report.get("feature_count") != 2209
        or d1_feature_report.get("pre_2021_feature_count") != 383
        or d1_feature_report.get("evaluation_coverage") != 1.0
        or d1_label_report.get("label_gate_passed") is not False
        or d1_label_report.get("decision") != "D1_labels_rejected_stop_before_model"
        or d1_label_report.get("evaluation_label_count") != 1799
        or d1_label_report.get("coverage_by_year", {}).get("2021") != 344 / 365
        or d1_label_report.get("diagnostics", {}).get("excluded_cross_segment_candidates")
        != 48
        or d1_label_report.get("diagnostics", {}).get(
            "excluded_missing_exact_open_candidates"
        )
        != 0
        or d1_label_report.get("diagnostics", {}).get("serialized_invalid_labels") != 0
        or [
            key
            for key, passed in d1_label_report.get("gate_results", {}).items()
            if not passed
        ]
        != ["per_year_label_coverage_minimum"]
        or (d1_output / "model").exists()
    ):
        raise FocusedContextError("D1 feature/label gate evidence changed")
    for phase in ("features", "labels"):
        manifest = load_canonical(d1_output / phase / "evidence-manifest.json")
        if (
            manifest.get("experiment_id")
            != "btc-spot-perp-continuation-information-d1-v2"
            or manifest.get("phase") != phase
            or manifest.get("actionable_arm_id") != "no_trade"
        ):
            raise FocusedContextError(f"D1 {phase} manifest identity changed")
        for item in manifest.get("artifacts", []):
            validate_bound_input(item, f"D1 {phase} evidence")

    d1_audit = load_canonical(d1_output / "audit/audit-report.json")
    if (
        d1_audit.get("decision") != "D1_v2_rejection_independently_reproduced_and_closed"
        or d1_audit.get("model_fitted") is not False
        or d1_audit.get("actionable_arm_id") != "no_trade"
        or not all(d1_audit.get("checks", {}).values())
        or d1_audit.get("label_gate_failure", {}).get("shortfall_labels") != 3
    ):
        raise FocusedContextError("D1 independent rejection audit changed")
    d1_manifest = load_canonical(d1_output / "evidence-manifest.json")
    if (
        d1_manifest.get("decision")
        != "rejected_before_model_at_frozen_label_coverage_gate"
        or d1_manifest.get("model_fitted") is not False
        or d1_manifest.get("actionable_arm_id") != "no_trade"
        or d1_manifest.get("no_strategy_pnl_cost_position_order_2026_or_actionable_route")
        is not True
    ):
        raise FocusedContextError("D1 rejection manifest changed")
    for item in d1_manifest.get("artifacts", []):
        validate_bound_input(item, "D1 rejection evidence")

    d1_v3_path = (
        ROOT / "research/btc/contracts/btc-spot-perp-continuation-information-d1-v3.json"
    )
    d1_v3 = load_canonical(d1_v3_path)
    if (
        d1_v3.get("status")
        != "frozen_before_any_D1_v3_endpoint_label_or_model_materialization"
        or d1_v3.get("base_contract", {}).get("sha256") != sha256_path(d1_v2_path)
        or d1_v3.get("action_boundary", {}).get("actionable_arm_id") != "no_trade"
        or any(
            d1_v3.get("action_boundary", {}).get(key) is not False
            for key in (
                "cost_or_execution_model_allowed",
                "order_intent_creation_allowed",
                "partial_ob0_access_allowed",
                "perpetual_position_allowed",
                "position_or_pnl_calculation_allowed",
                "production_signal_creation_allowed",
                "sealed_or_ineligible_2026_access_allowed",
                "strategy_backtest_allowed",
            )
        )
    ):
        raise FocusedContextError("D1-v3 frozen contract lineage or safety boundary changed")
    for item in d1_v3.get("bound_inputs", []):
        validate_bound_input(item, "D1-v3 bound input")

    d1_v3_output = (
        ROOT / "artifacts/agent-level-experiment/btc-focused/spot-perp-continuation-d1-v3"
    )
    d1_v3_endpoint = load_canonical(d1_v3_output / "endpoints/endpoint-gate-report.json")
    d1_v3_labels = load_canonical(d1_v3_output / "labels/label-gate-report.json")
    d1_v3_model = load_canonical(d1_v3_output / "model/report.json")
    if (
        d1_v3_endpoint.get("endpoint_gate_passed") is not True
        or d1_v3_endpoint.get("archive_count") != 73
        or d1_v3_endpoint.get("endpoint_count") != 2209
        or d1_v3_endpoint.get("missing_endpoint_count") != 0
        or not all(d1_v3_endpoint.get("gate_results", {}).values())
        or d1_v3_labels.get("label_gate_passed") is not True
        or d1_v3_labels.get("evaluation_label_count") != 1823
        or d1_v3_labels.get("evaluation_coverage") != 1.0
        or set(d1_v3_labels.get("coverage_by_year", {}).values()) != {1.0}
        or d1_v3_labels.get("interior_gap_diagnostics", {}).get(
            "candidates_crossing_interior_gaps"
        )
        != 48
        or d1_v3_labels.get("diagnostics", {}).get(
            "excluded_missing_exact_endpoint_candidates"
        )
        != 0
        or d1_v3_model.get("information_gate_passed") is not False
        or d1_v3_model.get("decision") != "D1_information_rejected"
        or d1_v3_model.get("forecast_count") != 1823
        or d1_v3_model.get("snapshot_count") != 60
        or d1_v3_model.get("model_metrics", {}).get("B0_MSE") != 0.00276009876
        or d1_v3_model.get("model_metrics", {}).get("M0_MSE") != 0.002778148523
        or d1_v3_model.get("model_metrics", {}).get("M1_MSE") != 0.002792931256
        or d1_v3_model.get("no_strategy_cost_PnL_position_order_or_2026_created")
        is not True
    ):
        raise FocusedContextError("D1-v3 endpoint, label or model evidence changed")
    for phase in ("endpoints", "labels", "model"):
        manifest = load_canonical(d1_v3_output / phase / "evidence-manifest.json")
        if (
            manifest.get("experiment_id")
            != "btc-spot-perp-continuation-information-d1-v3"
            or manifest.get("phase") != phase
            or manifest.get("actionable_arm_id") != "no_trade"
        ):
            raise FocusedContextError(f"D1-v3 {phase} manifest identity changed")
        for item in manifest.get("artifacts", []):
            validate_bound_input(item, f"D1-v3 {phase} evidence")

    d1_v3_top = load_canonical(d1_v3_output / "evidence-manifest.json")
    if (
        d1_v3_top.get("actionable_arm_id") != "no_trade"
        or d1_v3_top.get("no_strategy_cost_pnl_position_order_or_2026_created") is not True
    ):
        raise FocusedContextError("D1-v3 top evidence manifest changed")
    for item in d1_v3_top.get("artifacts", []) + d1_v3_top.get("phase_manifests", []):
        validate_bound_input(item, "D1-v3 top evidence")

    d1_v3_audit = load_canonical(d1_v3_output / "audit/audit-report.json")
    if (
        d1_v3_audit.get("decision")
        != "D1_v3_rejection_independently_reproduced_and_closed"
        or d1_v3_audit.get("actionable_arm_id") != "no_trade"
        or not all(d1_v3_audit.get("checks", {}).values())
        or d1_v3_audit.get("model_result", {}).get(
            "M1_relative_MSE_improvement_over_M0"
        )
        != -0.005321073826
        or d1_v3_audit.get("strategy_model_pnl_cost_position_order_or_2026_created")
        is not False
    ):
        raise FocusedContextError("D1-v3 independent rejection audit changed")
    d1_v3_audit_manifest = load_canonical(d1_v3_output / "audit/evidence-manifest.json")
    if (
        d1_v3_audit_manifest.get("decision")
        != "rejected_and_closed_after_deterministic_replay"
        or d1_v3_audit_manifest.get("actionable_arm_id") != "no_trade"
        or d1_v3_audit_manifest.get(
            "no_strategy_pnl_cost_position_order_2026_or_actionable_route"
        )
        is not True
    ):
        raise FocusedContextError("D1-v3 audit manifest changed")
    for item in d1_v3_audit_manifest.get("artifacts", []):
        validate_bound_input(item, "D1-v3 audit evidence")
    replay_top_item = next(
        (
            item
            for item in d1_v3_audit_manifest.get("artifacts", [])
            if item.get("path", "").endswith(
                "spot-perp-continuation-d1-v3-replay/evidence-manifest.json"
            )
        ),
        None,
    )
    if replay_top_item is None:
        raise FocusedContextError("D1-v3 audit omits replay top manifest")
    replay_top = load_canonical(ROOT / replay_top_item["path"])
    if (
        replay_top.get("experiment_id")
        != "btc-spot-perp-continuation-information-d1-v3"
        or replay_top.get("actionable_arm_id") != "no_trade"
        or replay_top.get("no_strategy_cost_pnl_position_order_or_2026_created") is not True
    ):
        raise FocusedContextError("D1-v3 replay top manifest changed")
    for item in replay_top.get("artifacts", []) + replay_top.get("phase_manifests", []):
        validate_bound_input(item, "D1-v3 replay evidence")
    for item in replay_top.get("phase_manifests", []):
        replay_phase = load_canonical(ROOT / item["path"])
        if (
            replay_phase.get("experiment_id")
            != "btc-spot-perp-continuation-information-d1-v3"
            or replay_phase.get("actionable_arm_id") != "no_trade"
        ):
            raise FocusedContextError("D1-v3 replay phase manifest changed")
        for artifact in replay_phase.get("artifacts", []):
            validate_bound_input(artifact, "D1-v3 replay phase artifact")

    decision_count, latest_digest = validate_decision_log(ROOT / "research/btc/DECISIONS.jsonl")
    if latest_digest != index.get("latest_decision_digest"):
        raise FocusedContextError("index latest decision digest is stale")
    return {
        "actionable_arm_id": "no_trade",
        "active_experiment": None,
        "context_artifact_count": len(seen),
        "decision_count": decision_count,
        "latest_decision_digest": latest_digest,
        "status": "context_valid",
    }


def main() -> None:
    print(canonical_line(validate()))


if __name__ == "__main__":
    main()
