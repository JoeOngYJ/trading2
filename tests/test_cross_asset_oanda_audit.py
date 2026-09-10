from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from trading_platform.cross_asset_oanda_audit import (
    CHUNK_BOUNDARIES,
    INSTRUMENT_IDS,
    OandaAuditError,
    audit_candle_payload,
    audit_instrument_history,
    build_successor_report,
    build_request_specs,
    catalogue_names,
    load_contract,
    load_successor_contract,
    validate_runtime_identity,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "config/experiments/cross-asset-a1-oanda-source-pilot-v1.json"
MANDATE_PATH = ROOT / "config/mandates/retail-cross-asset-research-v5.json"
SUCCESSOR_PATH = ROOT / "config/experiments/cross-asset-a1-oanda-source-pilot-v2.json"


def contract():
    return load_contract(CONTRACT_PATH, MANDATE_PATH)


def candle_payload(instrument: str = "EUR_USD") -> dict:
    return {
        "candles": [
            {
                "ask": {"c": "1.1012", "h": "1.1022", "l": "1.0992", "o": "1.1002"},
                "bid": {"c": "1.1010", "h": "1.1020", "l": "1.0990", "o": "1.1000"},
                "complete": True,
                "time": "2022-01-03T22:00:00.000000000Z",
                "volume": 123,
            },
            {
                "ask": {"c": "1.1022", "h": "1.1032", "l": "1.1002", "o": "1.1012"},
                "bid": {"c": "1.1020", "h": "1.1030", "l": "1.1000", "o": "1.1010"},
                "complete": True,
                "time": "2022-01-04T22:00:00.000000000Z",
                "volume": 124,
            },
        ],
        "granularity": "D",
        "instrument": instrument,
    }


def test_oanda_contract_is_frozen_get_only_and_non_economic():
    frozen = contract()
    assert [item["instrument_id"] for item in frozen["candidate_instruments"]] == list(
        INSTRUMENT_IDS
    )
    assert frozen["request_plan"]["allowed_http_method"] == "GET"
    assert frozen["acceptance_rules"]["a1_stage_passed_by_this_pilot"] is False
    assert frozen["prohibitions"]["return_calculation_allowed"] is False
    assert frozen["prohibitions"]["order_or_order_preview_allowed"] is False


def test_oanda_request_plan_is_bounded_and_contains_no_credentials():
    specs = build_request_specs(contract())
    assert len(specs) == 26
    assert specs[0].path_template == "/v3/accounts/{accountID}/instruments"
    assert tuple(item.parameters["from"] for item in specs[1:6]) == CHUNK_BOUNDARIES[:-1]
    serialized = json.dumps([item.parameters for item in specs])
    assert "Authorization" not in serialized
    assert "token" not in serialized.casefold()


def test_runtime_identity_fails_closed_on_host_or_account_change():
    frozen = contract()
    synthetic_account = "synthetic-account"
    frozen["source_access"]["account_id_sha256"] = hashlib.sha256(
        synthetic_account.encode("utf-8")
    ).hexdigest()
    validate_runtime_identity(
        frozen,
        "https://api-fxtrade.oanda.com",
        synthetic_account,
    )
    with pytest.raises(OandaAuditError, match="host"):
        validate_runtime_identity(frozen, "https://api-fxpractice.oanda.com", synthetic_account)
    with pytest.raises(OandaAuditError, match="account"):
        validate_runtime_identity(frozen, "https://api-fxtrade.oanda.com", "different")


def test_catalogue_rejects_duplicate_instrument_identity():
    row = {"displayName": "EUR/USD", "name": "EUR_USD", "type": "CURRENCY"}
    with pytest.raises(OandaAuditError, match="repeats"):
        catalogue_names({"instruments": [row, copy.deepcopy(row)]})


def test_bid_ask_daily_candles_require_causal_unique_uncrossed_rows():
    payload = candle_payload()
    timestamps = audit_candle_payload(
        payload,
        "EUR_USD",
        "2022-01-01T00:00:00Z",
        "2026-01-01T00:00:00Z",
    )
    assert len(timestamps) == 2

    crossed = copy.deepcopy(payload)
    crossed["candles"][0]["ask"]["c"] = "1.1000"
    with pytest.raises(OandaAuditError, match="crossed"):
        audit_candle_payload(
            crossed,
            "EUR_USD",
            "2022-01-01T00:00:00Z",
            "2026-01-01T00:00:00Z",
        )


def test_identical_aligned_boundary_overlap_is_counted_without_rewriting_rows():
    first = candle_payload()
    first["candles"] = [first["candles"][-1]]
    first["candles"][0]["time"] = "2009-12-31T22:00:00.000000000Z"
    second = copy.deepcopy(first)
    candidate = {
        "instrument_id": "EUR_USD",
        "minimum_complete_daily_candles": 1,
        "minimum_usable_start_on_or_before": "2010-01-04",
    }
    result = audit_instrument_history(
        [first, second],
        candidate,
        (
            "2005-01-01T00:00:00Z",
            "2010-01-01T00:00:00Z",
            "2014-01-01T00:00:00Z",
        ),
    )
    assert result["complete_daily_candles"] == 1
    assert result["identical_boundary_overlap_count"] == 1

    conflict = copy.deepcopy(second)
    conflict["candles"][0]["volume"] += 1
    with pytest.raises(OandaAuditError, match="conflicting duplicate"):
        audit_instrument_history(
            [first, conflict],
            candidate,
            (
                "2005-01-01T00:00:00Z",
                "2010-01-01T00:00:00Z",
                "2014-01-01T00:00:00Z",
            ),
        )

    duplicate = candle_payload()
    duplicate["candles"][1]["time"] = duplicate["candles"][0]["time"]
    with pytest.raises(OandaAuditError, match="non-increasing"):
        audit_candle_payload(
            duplicate,
            "EUR_USD",
            "2022-01-01T00:00:00Z",
            "2026-01-01T00:00:00Z",
        )


def test_mandate_rejects_private_state_or_order_permission(tmp_path: Path):
    frozen = json.loads(MANDATE_PATH.read_text(encoding="utf-8"))
    frozen["data_provider_token_policy"]["order_or_order_preview_access_allowed"] = True
    bad_path = tmp_path / "bad-mandate.json"
    bad_path.write_text(
        json.dumps(frozen, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True, separators=(",", ": "))
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(OandaAuditError, match="order_or_order_preview"):
        load_contract(CONTRACT_PATH, bad_path)


def test_oanda_successor_changes_only_the_frozen_oil_segment():
    successor = load_successor_contract(SUCCESSOR_PATH, ROOT)
    assert successor["changes_from_predecessor"]["new_provider_requests_allowed"] is False
    report = build_successor_report(successor, ROOT)
    assert report["source_pilot_passed"] is True
    assert report["qualified_for_strategy_evaluation"] is False
    oil = next(item for item in report["instrument_results"] if item["instrument_id"] == "WTICO_USD")
    assert oil["decision"] == "candidate_pass_segmented"
    assert oil["first_candle_at"] == "2005-11-27T22:00:00Z"
    assert oil["gap_count"] == 0
