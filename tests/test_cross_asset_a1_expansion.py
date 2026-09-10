from __future__ import annotations

import copy
from pathlib import Path

import pytest

from trading_platform.cross_asset_a1_expansion import (
    A1ExpansionError,
    EffectiveCostSchedule,
    FuturesContractObservation,
    FuturesRollDecision,
    ParentMicroBridge,
    QualifiedInstrument,
    build_lse_request_specs,
    choose_source,
    load_contract,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/experiments/cross-asset-a1-lse-futures-expansion-v1.json"


def passing_source(source_id: str, tco: str) -> dict:
    return {
        "gates": {
            "authorized_distribution": True,
            "contract_definitions": True,
            "exact_boundary_coverage": True,
            "final_settlements": True,
            "private_research_retention": True,
            "publication_timestamps": True,
            "reproducible_retrieval": True,
        },
        "source_id": source_id,
        "twelve_month_tco_usd": tco,
    }


def test_expansion_contract_freezes_four_lse_and_five_futures_without_strategy():
    contract = load_contract(CONTRACT, ROOT)
    assert [item["symbol"] for item in contract["listed_funds"]] == [
        "SWDA",
        "VAGS",
        "SGLN",
        "COMM",
    ]
    assert [item["micro_root"] for item in contract["listed_futures"]] == [
        "MES",
        "MGC",
        "MCL",
        "M6E",
        "MTN",
    ]
    assert all(value is False for value in contract["prohibitions"].values())
    assert contract["futures_source_comparison"]["automatic_purchase_allowed"] is False
    requests = build_lse_request_specs(contract)
    assert len(requests) == 12
    assert sum(item.weight for item in requests) == 164
    assert all("apikey" not in key.casefold() for item in requests for key in item.parameters)


def test_source_choice_prefers_direct_within_ten_percent_and_cheaper_vendor_beyond_it():
    assert choose_source([passing_source("cme_datamine", "100"), passing_source("databento", "91")]) == "cme_datamine"
    assert choose_source([passing_source("cme_datamine", "100"), passing_source("databento", "89")]) == "databento"
    failed = passing_source("databento", "1")
    failed["gates"]["private_research_retention"] = False
    assert choose_source([failed]) is None


def test_timestamp_and_sealed_boundary_fail_closed():
    base = {
        "available_at": "2025-02-04T22:05:00Z",
        "contract_id": "MESH5",
        "expiry": "2025-03-21",
        "observed_at": "2025-02-04T22:00:00Z",
        "open_interest": "100",
        "root": "MES",
        "settlement": "6000.25",
        "source_digest": "a" * 64,
        "venue": "XCME",
        "volume": "1000",
    }
    FuturesContractObservation(**base)
    with pytest.raises(A1ExpansionError, match="availability precedes"):
        FuturesContractObservation(**{**base, "available_at": "2025-02-04T21:59:00Z"})
    with pytest.raises(A1ExpansionError, match="sealed 2026"):
        FuturesContractObservation(
            **{
                **base,
                "observed_at": "2026-01-02T22:00:00Z",
                "available_at": "2026-01-02T22:05:00Z",
                "expiry": "2026-03-20",
            }
        )


def test_roll_is_forward_only_and_preserves_delivery_buffer():
    base = {
        "decision_at": "2025-03-10T22:05:00Z",
        "effective_at": "2025-03-11T22:00:00Z",
        "lineage_digest": "b" * 64,
        "new_contract_id": "MESM5",
        "old_contract_id": "MESH5",
        "reason": "prior_session_volume_crossover",
        "root": "MES",
        "sessions_before_delivery_risk": 8,
    }
    FuturesRollDecision(**base)
    with pytest.raises(A1ExpansionError, match="five-session"):
        FuturesRollDecision(**{**base, "sessions_before_delivery_risk": 4})
    with pytest.raises(A1ExpansionError, match="effective after"):
        FuturesRollDecision(**{**base, "effective_at": base["decision_at"]})


def test_parent_bridge_and_cost_records_are_strict():
    ParentMicroBridge("MTN", "TN", 400, "1", "accepted", "c" * 64)
    with pytest.raises(A1ExpansionError, match="mapping changed"):
        ParentMicroBridge("MTN", "ZN", 400, "1", "accepted", "c" * 64)
    EffectiveCostSchedule(
        instrument_id="MES",
        effective_from="2025-01-01",
        explicit_per_side={"broker_commission_usd": "0.25", "exchange_fee_usd": "0.50"},
        implicit_round_trip_bps=(10, 30, 80),
        cash_or_collateral_yield_policy="zero_percent_primary",
        source_digest="d" * 64,
    )


def test_qualified_instrument_requires_failure_reason_and_pre_2026_end():
    QualifiedInstrument("SWDA", "global_equity", "qualified", "2009-10-05", "2025-12-31", "GBP", "e" * 64)
    with pytest.raises(A1ExpansionError, match="requires a reason"):
        QualifiedInstrument("MES", "global_equity", "blocked", "2019-05-06", "2025-12-31", "USD", "e" * 64)
    with pytest.raises(A1ExpansionError, match="sealed 2026"):
        QualifiedInstrument("MES", "global_equity", "candidate", "2019-05-06", "2026-01-01", "USD", "e" * 64)
