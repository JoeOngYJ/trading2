"""Metadata-only readiness checks for the BTC MCS3-C carry-score lane."""

from __future__ import annotations

from typing import Any, Mapping


class CarryReadinessError(ValueError):
    """Raised when a readiness input is missing or inconsistent."""


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CarryReadinessError(f"{label} must be an object")
    return value


def _carry_record(mcs1_report: Mapping[str, Any]) -> Mapping[str, Any]:
    matrix = _mapping(mcs1_report.get("availability_matrix"), "availability matrix")
    records = matrix.get("records")
    if not isinstance(records, list):
        raise CarryReadinessError("availability records must be a list")
    selected = [
        _mapping(item, "availability record")
        for item in records
        if isinstance(item, Mapping) and item.get("dataset_id") == "btc_matched_carry_inputs"
    ]
    if len(selected) != 1:
        raise CarryReadinessError("exactly one matched-carry availability record is required")
    return selected[0]


def evaluate_mcs3_c_readiness(
    *,
    contract: Mapping[str, Any],
    mcs1_report: Mapping[str, Any],
    qualification_report: Mapping[str, Any],
    recovery_report: Mapping[str, Any],
    carry_contract: Mapping[str, Any],
    carry_report: Mapping[str, Any],
    research_mandate: Mapping[str, Any],
    development_mandate: Mapping[str, Any],
) -> dict[str, Any]:
    """Evaluate only frozen metadata; never open a market-value ledger."""

    if contract.get("stage_id") != "MCS3-C-READINESS":
        raise CarryReadinessError("wrong readiness contract")
    if mcs1_report.get("decision") != "mcs1_passed_metadata_only":
        raise CarryReadinessError("MCS1 metadata foundation is not preserved")
    if qualification_report.get("decision") != "data_qualification_rejected":
        raise CarryReadinessError("carry qualification disposition changed")
    if recovery_report.get("decision") != "official_rest_gap_recovery_rejected":
        raise CarryReadinessError("carry recovery disposition changed")
    if carry_contract.get("experiment_id") != "btc-positive-funding-carry-v1":
        raise CarryReadinessError("wrong carry-v1 contract")
    if carry_report.get("decision") != "development_strategy_rejected":
        raise CarryReadinessError("rejected carry-v1 disposition changed")
    if research_mandate.get("status") != "frozen_offline_research_only":
        raise CarryReadinessError("research mandate is not frozen offline")
    if development_mandate.get("status") != "frozen_offline_development_backtest_only":
        raise CarryReadinessError("development mandate is not frozen offline")

    carry = _carry_record(mcs1_report)
    qualification = _mapping(
        qualification_report.get("strategy_readiness_results"),
        "qualification readiness",
    )
    funding = _mapping(qualification_report.get("funding"), "funding audit")
    qualified_prices = _mapping(
        qualification_report.get("price_series"), "qualified price series"
    )
    recovered_prices = _mapping(
        recovery_report.get("price_series"), "recovered price series"
    )
    carry_data = _mapping(carry_report.get("data_audit"), "carry data audit")
    spot = _mapping(carry_data.get("spot"), "spot audit")
    margin_policy = _mapping(research_mandate.get("margin_policy"), "margin policy")
    development_margin = _mapping(
        development_mandate.get("development_margin_model"),
        "development margin model",
    )

    def complete_recovered_series(name: str) -> bool:
        series = _mapping(recovered_prices.get(name), name)
        return (
            series.get("combined_row_count") == 52608
            and series.get("combined_missing_hours") == 0
            and series.get("combined_duplicate_open_times") == 0
            and series.get("combined_invalid_rows") == 0
        )

    perpetual = _mapping(qualified_prices.get("klines"), "perpetual klines")
    carry_attribution = carry_contract.get("attribution", [])
    gates = {
        "causal_matched_carry_metadata_available": carry.get("point_in_time_ready") is True
        and carry.get("status") == "conditional_research"
        and "carry" in carry.get("supported_axes", []),
        "collateral_and_financing_policy_frozen": "collateral_opportunity_cost"
        in carry_attribution
        and "collateral_opportunity_cost"
        in development_mandate.get("required_attribution", []),
        "effective_dated_historical_fee_schedule_archived": qualification.get(
            "effective_dated_historical_fee_evidence"
        )
        is True,
        "effective_dated_historical_margin_brackets_archived": qualification.get(
            "effective_dated_historical_margin_brackets"
        )
        is True,
        "funding_history_complete": funding.get("row_count") == 6576
        and funding.get("missing_scheduled_events") == 0
        and funding.get("duplicate_times") == 0
        and funding.get("invalid_rows") == 0
        and funding.get("irregular_intervals") == 0,
        "historical_contract_funding_liquidation_and_adl_rules_archived": qualification.get(
            "official_market_data_documentation_archived"
        )
        is True
        and qualification.get("official_margin_documentation_archived") is True,
        "index_history_complete_after_exact_recovery": complete_recovered_series(
            "indexPriceKlines"
        ),
        "mark_history_complete_after_exact_recovery": complete_recovered_series(
            "markPriceKlines"
        ),
        "perpetual_execution_history_complete": perpetual.get("row_count") == 52608
        and perpetual.get("missing_hours") == 0
        and perpetual.get("duplicate_open_times") == 0
        and perpetual.get("invalid_rows") == 0,
        "rejected_carry_v1_identity_preserved": carry_report.get(
            "strategy_passed_frozen_development_gates"
        )
        is False
        and carry_report.get("accepted_strategy_arms") == []
        and carry_report.get("actionable_arm_id") == "no_trade"
        and carry_contract.get("parameters", {}).get(
            "entry_threshold_cumulative_funding_bps"
        )
        == 60
        and carry_contract.get("parameters", {}).get(
            "exit_threshold_cumulative_funding_bps"
        )
        == 30,
        "spot_execution_history_available_with_explicit_segments": spot.get(
            "complete_hours"
        )
        == 52561
        and spot.get("partial_or_missing_observed_hours") == 15
        and carry.get("coverage_start") == "2020-01-01T00:00:00Z"
        and carry.get("coverage_end_exclusive") == "2026-01-01T00:00:00Z",
    }
    if set(gates) != set(contract.get("gates", {})):
        raise CarryReadinessError("implemented readiness gates differ from frozen contract")

    promotion_only = {
        "exact_account_fee_available": qualification.get("exact_account_fee") is True,
        "development_margin_is_historical_evidence": development_margin.get(
            "historical_bracket_claim_allowed"
        )
        is True,
    }
    blockers = sorted(key for key, value in gates.items() if not value)
    passed = all(gates.values())
    return {
        "blockers": blockers,
        "coverage": {
            "end_exclusive": carry.get("coverage_end_exclusive"),
            "start": carry.get("coverage_start"),
        },
        "gates": gates,
        "mcs3_c_contract_freeze_permitted": passed,
        "mcs4_permitted": False,
        "premium_index": {
            "basic_score_requires_premium": False,
            "combined_missing_hours": _mapping(
                recovered_prices.get("premiumIndexKlines"), "premium index"
            ).get("combined_missing_hours"),
            "if_used": "fail_flat_and_reset_across_gap",
        },
        "promotion_only_diagnostics": promotion_only,
        "score_panel_branch_disposition": "continue_to_separate_mcs3_c_contract"
        if passed
        else "stop_current_score_panel_branch",
    }


__all__ = ["CarryReadinessError", "evaluate_mcs3_c_readiness"]
