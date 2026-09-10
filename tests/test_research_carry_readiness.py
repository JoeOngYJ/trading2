from __future__ import annotations

import ast
from copy import deepcopy
from pathlib import Path

import pytest

from trading_platform.research_carry_readiness import (
    CarryReadinessError,
    evaluate_mcs3_c_readiness,
)


ROOT = Path(__file__).resolve().parents[1]
GATE_NAMES = {
    "causal_matched_carry_metadata_available",
    "collateral_and_financing_policy_frozen",
    "effective_dated_historical_fee_schedule_archived",
    "effective_dated_historical_margin_brackets_archived",
    "funding_history_complete",
    "historical_contract_funding_liquidation_and_adl_rules_archived",
    "index_history_complete_after_exact_recovery",
    "mark_history_complete_after_exact_recovery",
    "perpetual_execution_history_complete",
    "rejected_carry_v1_identity_preserved",
    "spot_execution_history_available_with_explicit_segments",
}


def inputs() -> dict:
    return {
        "contract": {"stage_id": "MCS3-C-READINESS", "gates": {key: True for key in GATE_NAMES}},
        "mcs1_report": {
            "decision": "mcs1_passed_metadata_only",
            "availability_matrix": {
                "records": [
                    {
                        "coverage_end_exclusive": "2026-01-01T00:00:00Z",
                        "coverage_start": "2020-01-01T00:00:00Z",
                        "dataset_id": "btc_matched_carry_inputs",
                        "point_in_time_ready": True,
                        "status": "conditional_research",
                        "supported_axes": ["carry"],
                    }
                ]
            },
        },
        "qualification_report": {
            "decision": "data_qualification_rejected",
            "funding": {
                "duplicate_times": 0,
                "invalid_rows": 0,
                "irregular_intervals": 0,
                "missing_scheduled_events": 0,
                "row_count": 6576,
            },
            "price_series": {
                "klines": {
                    "duplicate_open_times": 0,
                    "invalid_rows": 0,
                    "missing_hours": 0,
                    "row_count": 52608,
                }
            },
            "strategy_readiness_results": {
                "effective_dated_historical_fee_evidence": True,
                "effective_dated_historical_margin_brackets": True,
                "exact_account_fee": True,
                "official_margin_documentation_archived": True,
                "official_market_data_documentation_archived": True,
            },
        },
        "recovery_report": {
            "decision": "official_rest_gap_recovery_rejected",
            "price_series": {
                "indexPriceKlines": {
                    "combined_duplicate_open_times": 0,
                    "combined_invalid_rows": 0,
                    "combined_missing_hours": 0,
                    "combined_row_count": 52608,
                },
                "markPriceKlines": {
                    "combined_duplicate_open_times": 0,
                    "combined_invalid_rows": 0,
                    "combined_missing_hours": 0,
                    "combined_row_count": 52608,
                },
                "premiumIndexKlines": {"combined_missing_hours": 1},
            },
        },
        "carry_contract": {
            "attribution": ["collateral_opportunity_cost"],
            "experiment_id": "btc-positive-funding-carry-v1",
            "parameters": {
                "entry_threshold_cumulative_funding_bps": 60,
                "exit_threshold_cumulative_funding_bps": 30,
            },
        },
        "carry_report": {
            "accepted_strategy_arms": [],
            "actionable_arm_id": "no_trade",
            "data_audit": {
                "spot": {
                    "complete_hours": 52561,
                    "partial_or_missing_observed_hours": 15,
                }
            },
            "decision": "development_strategy_rejected",
            "strategy_passed_frozen_development_gates": False,
        },
        "research_mandate": {
            "margin_policy": {},
            "status": "frozen_offline_research_only",
        },
        "development_mandate": {
            "development_margin_model": {"historical_bracket_claim_allowed": False},
            "required_attribution": ["collateral_opportunity_cost"],
            "status": "frozen_offline_development_backtest_only",
        },
    }


def test_all_synthetic_research_readiness_gates_can_pass():
    result = evaluate_mcs3_c_readiness(**inputs())
    assert all(result["gates"].values())
    assert result["mcs3_c_contract_freeze_permitted"] is True
    assert result["score_panel_branch_disposition"] == "continue_to_separate_mcs3_c_contract"
    assert result["mcs4_permitted"] is False


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (("strategy_readiness_results", "effective_dated_historical_fee_evidence"), "effective_dated_historical_fee_schedule_archived"),
        (("strategy_readiness_results", "effective_dated_historical_margin_brackets"), "effective_dated_historical_margin_brackets_archived"),
        (("strategy_readiness_results", "official_margin_documentation_archived"), "historical_contract_funding_liquidation_and_adl_rules_archived"),
    ],
)
def test_missing_historical_economics_fail_closed(path, expected):
    values = inputs()
    values["qualification_report"][path[0]][path[1]] = False
    result = evaluate_mcs3_c_readiness(**values)
    assert result["mcs3_c_contract_freeze_permitted"] is False
    assert expected in result["blockers"]
    assert result["score_panel_branch_disposition"] == "stop_current_score_panel_branch"


def test_planning_margin_cannot_claim_historical_evidence():
    values = inputs()
    values["development_mandate"]["development_margin_model"][
        "historical_bracket_claim_allowed"
    ] = False
    result = evaluate_mcs3_c_readiness(**values)
    assert result["promotion_only_diagnostics"]["development_margin_is_historical_evidence"] is False


def test_premium_gap_is_recorded_but_not_a_basic_score_gate():
    result = evaluate_mcs3_c_readiness(**inputs())
    assert result["premium_index"]["combined_missing_hours"] == 1
    assert result["premium_index"]["basic_score_requires_premium"] is False
    assert result["premium_index"]["if_used"] == "fail_flat_and_reset_across_gap"


def test_duplicate_or_missing_carry_record_fails_closed():
    values = inputs()
    duplicate = deepcopy(values["mcs1_report"]["availability_matrix"]["records"][0])
    values["mcs1_report"]["availability_matrix"]["records"].append(duplicate)
    with pytest.raises(CarryReadinessError, match="exactly one"):
        evaluate_mcs3_c_readiness(**values)


def test_rejected_carry_identity_must_remain_rejected():
    values = inputs()
    values["carry_report"]["decision"] = "accepted"
    with pytest.raises(CarryReadinessError, match="disposition changed"):
        evaluate_mcs3_c_readiness(**values)


def test_forbidden_clients_are_not_imported():
    forbidden = {"ccxt", "freqtrade", "httpx", "nats", "psycopg", "requests", "sqlalchemy"}
    imported: set[str] = set()
    for relative in (
        "src/trading_platform/research_carry_readiness.py",
        "scripts/audit_btc_mcs3_c_readiness.py",
    ):
        tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
    assert not (imported & forbidden)
