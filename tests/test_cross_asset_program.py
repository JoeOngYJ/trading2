from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from trading_platform.cross_asset_program import (
    CrossAssetContextError,
    _validate_a1_contract,
    _validate_a1_evidence,
    _validate_a2_contract,
    _validate_a2_evidence,
    _validate_a2_integrity_evidence,
    _validate_a3_contract,
    _validate_a3_evidence,
    _validate_a3_hypothesis,
    _validate_a3_prepartition_evidence,
    _validate_access_matrix,
    _validate_data_contract,
    _validate_futures_source_comparison,
    _validate_futures_specs,
    _validate_mandate,
    _validate_program,
    _validate_status,
    canonical_json,
    validate_artifact_lineage,
    validate_cross_asset_context,
)


ROOT = Path(__file__).resolve().parents[1]


def load(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def test_superseded_a1_v2_context_fails_closed_after_append_only_progress():
    with pytest.raises(CrossAssetContextError, match="checksum mismatch"):
        validate_cross_asset_context(
            ROOT,
            ROOT / "config/research/cross-asset-program-v2.json",
            ROOT / "config/mandates/retail-cross-asset-research-v4.json",
            ROOT / "config/research/cross-asset-instrument-access-v2.json",
            ROOT / "config/research/cross-asset-data-contract-v2.json",
            ROOT / "config/research/cross-asset-status-v2.json",
        )


def test_a3_repository_context_records_rejection_and_fails_closed():
    result = validate_cross_asset_context(
        ROOT,
        ROOT / "config/research/cross-asset-program-v6.json",
        ROOT / "config/mandates/retail-cross-asset-research-v7.json",
        ROOT / "config/research/cross-asset-instrument-access-v4.json",
        ROOT / "config/research/cross-asset-data-contract-v6.json",
        ROOT / "config/research/cross-asset-status-v7.json",
    )
    assert result.current_stage == "A3"
    assert result.current_state == "rejected"
    assert result.active_stage is None
    assert result.accepted_strategy_arms == 0
    assert result.approved_execution_instruments == 0


def test_oanda_v5_mandate_and_v3_data_contract_block_execution_and_overnight_shortcuts():
    mandate = load("config/mandates/retail-cross-asset-research-v5.json")
    access = load("config/research/cross-asset-instrument-access-v3.json")
    data = load("config/research/cross-asset-data-contract-v3.json")
    _validate_mandate(mandate)
    _validate_access_matrix(access)
    _validate_data_contract(data)
    assert mandate["execution_scope"]["oanda_execution_authorized"] is False
    assert data["strategy_evaluation_authorized"] is False
    assert (
        data["intraday_successor_policy"][
            "commodity_and_bond_cfds_eligible_without_historical_financing"
        ]
        is False
    )
    unsafe = copy.deepcopy(data)
    unsafe["intraday_successor_policy"][
        "commodity_and_bond_cfds_eligible_without_historical_financing"
    ] = True
    with pytest.raises(CrossAssetContextError, match="financing"):
        _validate_data_contract(unsafe)


def test_oanda_v6_hourly_context_requires_masks_and_keeps_execution_blocked():
    mandate = load("config/mandates/retail-cross-asset-research-v6.json")
    access = load("config/research/cross-asset-instrument-access-v4.json")
    data = load("config/research/cross-asset-data-contract-v4.json")
    _validate_mandate(mandate)
    _validate_access_matrix(access)
    _validate_data_contract(data)
    assert mandate["execution_scope"]["approved_execution_instrument_ids"] == []
    assert access["approved_execution_instruments"] == []
    assert data["strategy_evaluation_authorized"] is False
    unsafe = copy.deepcopy(data)
    unsafe["gap_policy"]["incomplete_session_window"] = "forward_fill"
    with pytest.raises(CrossAssetContextError, match="no_trade"):
        _validate_data_contract(unsafe)


def test_a2_v7_mandate_and_v5_data_contract_keep_execution_blocked():
    mandate = load("config/mandates/retail-cross-asset-research-v7.json")
    data = load("config/research/cross-asset-data-contract-v5.json")
    _validate_mandate(mandate)
    _validate_data_contract(data)
    scope = mandate["execution_scope"]
    assert scope["conversion_only_oanda_instruments"] == ["GBP_USD"]
    assert scope["oanda_execution_authorized"] is False
    assert scope["shorting_authorized_for_execution"] is False
    assert scope["approved_execution_instrument_ids"] == []
    assert data["strategy_evaluation_authorized"] is False
    assert data["a2_result_policy"]["result"] == "rejected_do_not_tune_or_rerun"
    assert data["a3_prerequisites"]["matching_a2_partitions_allowed"] is False

    unsafe = copy.deepcopy(mandate)
    unsafe["execution_scope"]["shorting_authorized_for_execution"] = True
    with pytest.raises(CrossAssetContextError, match="cannot authorize execution"):
        _validate_mandate(unsafe)


def test_a2_rejection_and_integrity_evidence_are_bound_to_frozen_contracts():
    contract = load("config/experiments/cross-asset-a2-session-breakout-continuation-v1.json")
    evidence = load(
        "artifacts/agent-level-experiment/cross-asset/"
        "a2-session-breakout-continuation-v1/evidence-manifest.json"
    )
    integrity = load(
        "artifacts/agent-level-experiment/cross-asset/"
        "a2-session-breakout-integrity-review-v1/evidence-manifest.json"
    )
    hypothesis = load("config/experiments/cross-asset-a3-overnight-gap-reversion-v1.json")
    _validate_a2_contract(contract)
    _validate_a2_evidence(ROOT, evidence)
    _validate_a2_integrity_evidence(ROOT, integrity)
    _validate_a3_hypothesis(hypothesis)
    assert evidence["accepted_strategy_arms"] == []
    assert integrity["final_partition_clean_for_a2"] is False
    assert hypothesis["status"] == "frozen_hypothesis_only_unimplemented"

    unsafe = copy.deepcopy(evidence)
    unsafe["accepted_strategy_arms"] = ["session_breakout"]
    with pytest.raises(CrossAssetContextError, match="unexpected A2 rejection evidence"):
        _validate_a2_evidence(ROOT, unsafe)


def test_a3_prepartition_and_replacement_contract_preserve_zero_arm_boundary():
    evidence = load(
        "artifacts/agent-level-experiment/cross-asset/"
        "a3-timestamp-prepartition-v1/evidence-manifest.json"
    )
    contract = load("config/experiments/cross-asset-a3-overnight-gap-reversion-v2.json")
    _validate_a3_prepartition_evidence(ROOT, evidence)
    _validate_a3_contract(contract)
    assert evidence["price_fields_deserialized"] is False
    assert evidence["prospective_price_rows_present"] is False
    assert contract["historical_result_policy"]["historical_result_can_accept_strategy_arm"] is False

    unsafe = copy.deepcopy(contract)
    unsafe["historical_result_policy"]["historical_result_can_accept_strategy_arm"] = True
    with pytest.raises(CrossAssetContextError, match="cannot accept an arm"):
        _validate_a3_contract(unsafe)


def test_a3_rejection_evidence_and_v6_data_contract_block_later_stages():
    evidence = load(
        "artifacts/agent-level-experiment/cross-asset/"
        "a3-overnight-gap-reversion-v2/evidence-manifest.json"
    )
    data = load("config/research/cross-asset-data-contract-v6.json")
    _validate_a3_evidence(ROOT, evidence)
    _validate_data_contract(data)
    assert evidence["accepted_strategy_arms"] == []
    assert evidence["prospective_partition_accessed"] is False
    assert data["next_family_policy"]["a4_or_a5_activation_allowed"] is False

    unsafe = copy.deepcopy(data)
    unsafe["next_family_policy"]["a4_or_a5_activation_allowed"] = True
    with pytest.raises(CrossAssetContextError, match="post-A3"):
        _validate_data_contract(unsafe)


def test_hourly_successor_contract_and_evidence_are_no_download_and_pass_a1():
    contract = load("config/experiments/cross-asset-a1-oanda-hourly-history-v2.json")
    evidence = load(
        "artifacts/agent-level-experiment/cross-asset/a1-oanda-hourly-history-v2/evidence-manifest.json"
    )
    _validate_a1_contract(contract)
    _validate_a1_evidence(ROOT, evidence, "passed")
    assert contract["changes_from_predecessor"]["new_provider_requests_allowed"] is False
    assert evidence["new_provider_requests"] == 0
    assert evidence["returns_or_pnl_computed"] is False


def test_a1_account_instrument_verification_contract_is_frozen_and_read_only():
    contract = load(
        "config/experiments/cross-asset-a1-account-instrument-verification-v1.json"
    )
    _validate_a1_contract(contract)
    assert [item["symbol"] for item in contract["candidate_instruments"]] == [
        "SWDA",
        "VAGS",
        "SGLN",
        "COMM",
    ]
    assert contract["allowed_operations"]["read_only_account_metadata_allowed"] is True

    unsafe = copy.deepcopy(contract)
    unsafe["prohibitions"]["order_preview_allowed"] = True
    with pytest.raises(CrossAssetContextError, match="unsafe A1 account-verification permission"):
        _validate_a1_contract(unsafe)

    substituted = copy.deepcopy(contract)
    substituted["candidate_instruments"][0]["isin"] = "different-instrument"
    with pytest.raises(CrossAssetContextError, match="universe changed"):
        _validate_a1_contract(substituted)


def test_a1_account_verification_evidence_preserves_incomplete_mapping():
    evidence = load(
        "artifacts/agent-level-experiment/cross-asset/"
        "a1-account-instrument-verification-v1/evidence-manifest.json"
    )
    _validate_a1_evidence(ROOT, evidence, "blocked")

    with pytest.raises(CrossAssetContextError, match="cannot pass A1"):
        _validate_a1_evidence(ROOT, evidence, "passed")


def test_ibkr_contract_details_public_review_is_frozen_and_price_free():
    contract = load(
        "config/experiments/cross-asset-a1-ibkr-contract-details-public-review-v1.json"
    )
    _validate_a1_contract(contract)
    assert contract["source_policy"]["price_or_performance_fields_are_discarded"] is True
    assert contract["prohibitions"]["account_or_broker_login_allowed"] is False

    unsafe = copy.deepcopy(contract)
    unsafe["decision_rules"]["strategy_or_price_evidence_can_repair_identity_failure"] = True
    with pytest.raises(CrossAssetContextError, match="unsafe IBKR contract-details rule"):
        _validate_a1_contract(unsafe)


def test_ibkr_public_review_evidence_fails_closed_on_gbpence_inference():
    evidence = load(
        "artifacts/agent-level-experiment/cross-asset/"
        "a1-ibkr-contract-details-public-review-v1/evidence-manifest.json"
    )
    _validate_a1_evidence(ROOT, evidence, "blocked")

    with pytest.raises(CrossAssetContextError, match="cannot pass A1"):
        _validate_a1_evidence(ROOT, evidence, "passed")

    facts = load(
        "artifacts/agent-level-experiment/cross-asset/"
        "a1-ibkr-contract-details-public-review-v1/source-facts.json"
    )
    assert facts["currency_notation_review"]["exact_literal_mapping_supported"] is False
    assert [
        item["symbol"]
        for item in facts["instrument_results"]
        if item["exact_account_line_verified"]
    ] == ["VAGS"]


def test_executable_universe_feasibility_contract_is_source_only_and_bounded():
    contract = load(
        "config/experiments/cross-asset-a1-executable-universe-feasibility-v1.json"
    )
    _validate_a1_contract(contract)
    cash = contract["candidate_paths"]["exact_lse_cash"]
    assert [item["provider_symbol"] for item in cash["expected_instruments"]] == [
        "SWDA:LSE",
        "VAGS:LSE",
        "SGLN:LSE",
        "COMM:LSE",
    ]
    assert cash["request_plan"]["maximum_requests"] == 16
    assert contract["decision_rules"]["full_history_download_authorized_by_this_review"] is False
    assert contract["prohibitions"]["strategy_signals_allowed"] is False


def test_mandate_records_capital_floor_without_making_return_a_gate():
    mandate = load("config/mandates/retail-cross-asset-research-v2.json")
    _validate_mandate(mandate)
    assert mandate["capital"]["research_equity_gbp"] == 20_000
    assert mandate["capital"]["soft_equity_floor_gbp"] == 17_600
    assert mandate["capital"]["hard_equity_floor_gbp"] == 16_000
    assert mandate["objective"]["stretch_annualized_return_fraction"] == 0.50
    assert mandate["objective"]["stretch_return_is_acceptance_gate"] is False

    unsafe = copy.deepcopy(mandate)
    unsafe["objective"]["stretch_return_is_acceptance_gate"] = True
    with pytest.raises(CrossAssetContextError, match="cannot be an acceptance gate"):
        _validate_mandate(unsafe)

    unsafe_token = copy.deepcopy(mandate)
    unsafe_token["data_provider_token_policy"]["repository_storage_allowed"] = True
    with pytest.raises(CrossAssetContextError, match="repository_storage_allowed"):
        _validate_mandate(unsafe_token)


def test_access_matrix_has_no_approved_product_and_blocks_crypto_derivatives():
    matrix = load("config/research/cross-asset-instrument-access-v1.json")
    _validate_access_matrix(matrix)
    assert matrix["approved_execution_instruments"] == []

    unsafe = copy.deepcopy(matrix)
    uk = next(item for item in unsafe["jurisdictions"] if item["jurisdiction_id"] == "UK_retail")
    derivative = next(
        item for item in uk["product_access"] if item["product_family"] == "crypto_derivatives"
    )
    derivative["execution_state"] = "conditional_unapproved"
    with pytest.raises(CrossAssetContextError, match="crypto derivatives"):
        _validate_access_matrix(unsafe)


def test_data_contract_rejects_source_acceptance_and_survivor_universe():
    contract = load("config/research/cross-asset-data-contract-v1.json")
    _validate_data_contract(contract)

    accepted = copy.deepcopy(contract)
    accepted["accepted_sources"] = [{"source_id": "unfrozen"}]
    with pytest.raises(CrossAssetContextError, match="cannot accept"):
        _validate_data_contract(accepted)

    survivors = copy.deepcopy(contract)
    survivors["point_in_time_universe"]["current_survivors_as_history"] = "allow"
    with pytest.raises(CrossAssetContextError, match="current-survivor"):
        _validate_data_contract(survivors)


def test_status_rejects_skipped_prerequisite_and_multiple_active_stages():
    program = load("config/research/cross-asset-program-v1.json")
    program_id, graph = _validate_program(program)
    status = load("config/research/cross-asset-status-v1.json")

    invalid = copy.deepcopy(status)
    invalid["stages"][1]["state"] = "active"
    invalid["stages"][0]["state"] = "planned"
    invalid["current_stage"] = "A1"
    invalid["current_state"] = "active"
    with pytest.raises(CrossAssetContextError, match="unsatisfied prerequisites"):
        _validate_status(invalid, program_id, graph)

    multiple = copy.deepcopy(status)
    multiple["stages"][1]["state"] = "active"
    multiple["stages"][2]["state"] = "active"
    with pytest.raises(CrossAssetContextError, match="only one"):
        _validate_status(multiple, program_id, graph)


def test_canonical_serialization_and_artifact_checksum_are_deterministic(tmp_path: Path):
    payload = {"z": [2, 1], "a": {"safe": True}}
    assert canonical_json(payload) == canonical_json(json.loads(canonical_json(payload)))

    artifact = tmp_path / "artifact.json"
    artifact.write_text('{"state":"frozen"}\n', encoding="utf-8")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    validate_artifact_lineage(tmp_path, [{"path": "artifact.json", "sha256": digest}])
    artifact.write_text('{"state":"changed"}\n', encoding="utf-8")
    with pytest.raises(CrossAssetContextError, match="checksum mismatch"):
        validate_artifact_lineage(tmp_path, [{"path": "artifact.json", "sha256": digest}])


def test_program_safety_boundary_rejects_strategy_evaluation_in_a0():
    program = load("config/research/cross-asset-program-v1.json")
    _validate_program(program)
    unsafe = copy.deepcopy(program)
    unsafe["safety_boundaries"]["strategy_evaluation_allowed_in_a0"] = True
    with pytest.raises(CrossAssetContextError, match="strategy_evaluation_allowed_in_a0"):
        _validate_program(unsafe)


def test_v4_mandate_allows_only_offline_futures_data_research():
    mandate = load("config/mandates/retail-cross-asset-research-v4.json")
    _validate_mandate(mandate)
    assert mandate["execution_scope"]["candidate_futures"] == [
        "MES",
        "MGC",
        "MCL",
        "M6E",
        "MTN",
    ]
    assert mandate["execution_scope"]["derivatives_execution_authorized"] is False
    unsafe = copy.deepcopy(mandate)
    unsafe["execution_scope"]["derivatives_execution_authorized"] = True
    with pytest.raises(CrossAssetContextError, match="cannot authorize derivatives"):
        _validate_mandate(unsafe)


def test_v2_data_and_access_contracts_keep_every_future_unapproved():
    data = load("config/research/cross-asset-data-contract-v2.json")
    access = load("config/research/cross-asset-instrument-access-v2.json")
    _validate_data_contract(data)
    _validate_access_matrix(access)
    assert data["futures_policy"]["vendor_adjusted_continuous_series_allowed"] is False
    assert access["approved_execution_instruments"] == []
    unsafe = copy.deepcopy(access)
    unsafe["research_candidates"][0]["execution_state"] = "approved"
    with pytest.raises(CrossAssetContextError, match="cannot be execution-approved"):
        _validate_access_matrix(unsafe)


def test_futures_specs_and_source_comparison_fail_closed_before_quotes():
    specs = load("config/research/cross-asset-futures-specs-v1.json")
    comparison = load("config/research/cross-asset-futures-source-comparison-v1.json")
    _validate_futures_specs(specs)
    _validate_futures_source_comparison(comparison)
    assert [item["micro_root"] for item in specs["instruments"]] == [
        "MES",
        "MGC",
        "MCL",
        "M6E",
        "MTN",
    ]
    assert comparison["selected_provider_id"] is None

    unsafe_specs = copy.deepcopy(specs)
    unsafe_specs["instruments"][0]["execution_state"] = "approved"
    with pytest.raises(CrossAssetContextError, match="cannot approve"):
        _validate_futures_specs(unsafe_specs)

    unsafe_comparison = copy.deepcopy(comparison)
    unsafe_comparison["selected_provider_id"] = "databento"
    with pytest.raises(CrossAssetContextError, match="cannot be selected"):
        _validate_futures_source_comparison(unsafe_comparison)


def test_a1_expansion_contract_and_freeze_evidence_are_non_economic():
    contract = load("config/experiments/cross-asset-a1-lse-futures-expansion-v1.json")
    _validate_a1_contract(contract)
    evidence = load(
        "artifacts/agent-level-experiment/cross-asset/"
        "a1-lse-futures-expansion-v1/evidence-manifest.json"
    )
    _validate_a1_evidence(ROOT, evidence, "blocked")
    with pytest.raises(CrossAssetContextError, match="cannot pass A1"):
        _validate_a1_evidence(ROOT, evidence, "passed")

    failure = load(
        "artifacts/agent-level-experiment/cross-asset/a1-lse-futures-expansion-v1/"
        "lse-history/failure-evidence-manifest.json"
    )
    _validate_a1_evidence(ROOT, failure, "blocked")
    with pytest.raises(CrossAssetContextError, match="cannot pass A1"):
        _validate_a1_evidence(ROOT, failure, "passed")


def test_a1_contract_freezes_exact_gbp_lse_pilot_without_strategy_evaluation():
    contract = load("config/experiments/cross-asset-a1-lse-source-pilot-v1.json")
    _validate_a1_contract(contract)
    assert [item["ticker"] for item in contract["instruments"]] == [
        "SWDA",
        "VAGS",
        "SGLN",
        "COMM",
    ]
    assert contract["strategy_evaluation_authorized"] is False
    assert contract["decision_rule"]["technical_csv_success_is_source_acceptance"] is False

    unsafe = copy.deepcopy(contract)
    unsafe["prohibitions"]["pnl_allowed"] = True
    with pytest.raises(CrossAssetContextError, match="pnl_allowed"):
        _validate_a1_contract(unsafe)


def test_twelvedata_a1_contract_freezes_source_only_proxy_pilot():
    contract = json.loads(
        (ROOT / "config/experiments/cross-asset-a1-twelvedata-economic-proxy-pilot-v1.json").read_text()
    )
    _validate_a1_contract(contract)
    assert contract["decision_rule"]["a1_stage_passed_by_pilot"] is False
    assert contract["prohibitions"]["pnl_allowed"] is False


def test_twelvedata_a1_contract_rejects_strategy_or_request_budget_drift():
    contract = json.loads(
        (ROOT / "config/experiments/cross-asset-a1-twelvedata-economic-proxy-pilot-v1.json").read_text()
    )
    unsafe = copy.deepcopy(contract)
    unsafe["prohibitions"]["strategy_signals_allowed"] = True
    with pytest.raises(CrossAssetContextError, match="strategy_signals"):
        _validate_a1_contract(unsafe)
    unsafe = copy.deepcopy(contract)
    unsafe["sources"]["twelvedata_grow"]["maximum_weighted_credits"] = 59
    with pytest.raises(CrossAssetContextError, match="request budget"):
        _validate_a1_contract(unsafe)


def test_twelvedata_history_contract_is_source_only_and_calendar_bound():
    contract = load("config/experiments/cross-asset-a1-twelvedata-full-history-v1.json")
    _validate_a1_contract(contract)
    assert contract["prohibitions"]["return_calculation_allowed"] is False
    unsafe = copy.deepcopy(contract)
    unsafe["request_plan"]["maximum_weighted_credits"] = 330
    with pytest.raises(CrossAssetContextError, match="request budget"):
        _validate_a1_contract(unsafe)


def test_a1_completion_review_is_fail_closed_and_cannot_approve_by_similarity():
    contract = load("config/experiments/cross-asset-a1-completion-review-v1.json")
    _validate_a1_contract(contract)
    assert [item["symbol"] for item in contract["instruments"]] == [
        "SPY", "EFA", "IEF", "TLT", "GLD", "DBC", "BIL", "GBP/USD"
    ]
    assert contract["decision_rules"]["economically_similar_product_is_exact_mapping"] is False
    assert contract["prohibitions"]["return_calculation_allowed"] is False

    unsafe = copy.deepcopy(contract)
    unsafe["decision_rules"]["public_catalog_presence_is_execution_approval"] = True
    with pytest.raises(CrossAssetContextError, match="public catalog"):
        _validate_a1_contract(unsafe)

    unsafe = copy.deepcopy(contract)
    unsafe["prohibitions"]["economic_metrics_allowed"] = True
    with pytest.raises(CrossAssetContextError, match="economic_metrics_allowed"):
        _validate_a1_contract(unsafe)


def test_a1_blocked_evidence_preserves_rejection_and_no_strategy_outputs():
    evidence = load(
        "artifacts/agent-level-experiment/cross-asset/a1-lse-source-pilot-v1/evidence-manifest.json"
    )
    _validate_a1_evidence(ROOT, evidence, "blocked")
    report = load(
        "artifacts/agent-level-experiment/cross-asset/a1-lse-source-pilot-v1/audit-report.json"
    )
    assert report["source_accepted"] is False
    assert report["economic_metrics_computed"] is False
    assert report["pnl_computed"] is False
    assert report["strategy_signals_generated"] is False

    with pytest.raises(CrossAssetContextError, match="cannot pass"):
        _validate_a1_evidence(ROOT, evidence, "passed")


def test_a1_completion_evidence_is_blocked_and_cannot_pass():
    evidence = load(
        "artifacts/agent-level-experiment/cross-asset/a1-completion-review-v1/evidence-manifest.json"
    )
    _validate_a1_evidence(ROOT, evidence, "blocked")
    report = load(
        "artifacts/agent-level-experiment/cross-asset/a1-completion-review-v1/audit-report.json"
    )
    assert report["a1_stage_passed"] is False
    assert report["approved_execution_instruments"] == []
    assert not any(report["safety"].values())

    with pytest.raises(CrossAssetContextError, match="cannot pass"):
        _validate_a1_evidence(ROOT, evidence, "passed")
