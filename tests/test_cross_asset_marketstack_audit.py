from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from trading_platform.cross_asset_marketstack_audit import (
    EXPECTED_MULTIPLIERS,
    EXPECTED_QUOTE_UNITS,
    MarketstackAuditError,
    audit_corporate_actions,
    audit_eod,
    audit_eod_identity,
    audit_identity,
    build_request_specs,
    load_contract,
    parse_response,
    redact_secret,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "config/experiments/cross-asset-a1-marketstack-free-source-pilot-v3.json"


def contract() -> dict:
    return load_contract(CONTRACT_PATH, ROOT)


def instrument(ticker: str = "SWDA") -> dict:
    return next(item for item in contract()["instruments"] if item["ticker"] == ticker)


def eod_payload(ticker: str = "SWDA") -> dict:
    sessions = contract()["boundaries"]["expected_lse_sessions"]
    return {
        "data": [
            {
                "adj_close": 101,
                "adj_high": 102,
                "adj_low": 99,
                "adj_open": 100,
                "adj_volume": 1000,
                "close": 101,
                "date": f"{session}T00:00:00+00:00",
                "dividend": 0,
                "exchange": "XLON",
                "high": 102,
                "low": 99,
                "name": "iShares Core MSCI World UCITS ETF",
                "open": 100,
                "price_currency": "gbp",
                "split_factor": 1,
                "symbol": ticker,
                "volume": 1000,
            }
            for session in sessions
        ]
    }


def test_frozen_marketstack_contract_is_canonical_and_source_only():
    frozen = load_contract(CONTRACT_PATH, ROOT)
    assert frozen["pilot_id"] == "cross-asset-a1-marketstack-free-source-pilot-v3"
    assert frozen["strategy_evaluation_authorized"] is False
    assert frozen["source_access"]["paid_upgrade_authorized"] is False
    assert frozen["sources"]["marketstack_free"]["maximum_requests"] == 20
    assert frozen["sources"]["marketstack_free"]["adjusted_fields_eligible_for_research"] is False
    assert frozen["sources"]["marketstack_free"]["availability_fallback_frozen"] is True
    assert frozen["sources"]["marketstack_free"][
        "raw_plus_separate_corporate_actions_policy_frozen"
    ] is True


def test_request_plan_is_exact_and_never_persists_token():
    secret = "not-a-real-marketstack-key"
    specs = build_request_specs(contract(), secret)
    assert len(specs) == 12
    assert {(item.ticker, item.endpoint) for item in specs} == {
        (ticker, endpoint)
        for ticker in ("SWDA", "VAGS", "SGLN", "COMM")
        for endpoint in ("eod", "splits", "dividends")
    }
    assert all(secret in item.url for item in specs)
    assert all("access_key" not in item.persisted_parameters for item in specs)
    assert secret not in redact_secret(f"failed URL {specs[0].url}", secret)
    with pytest.raises(MarketstackAuditError, match="required"):
        build_request_specs(contract(), "")


def test_quote_units_and_gbp_multipliers_are_frozen_per_trading_line():
    frozen = load_contract(CONTRACT_PATH, ROOT)
    assert {item["ticker"]: item["expected_vendor_quote_unit"] for item in frozen["instruments"]} == EXPECTED_QUOTE_UNITS
    assert {
        item["ticker"]: item["price_to_gbp_multiplier"] for item in frozen["instruments"]
    } == {ticker: str(value) for ticker, value in EXPECTED_MULTIPLIERS.items()}


def test_identity_requires_one_exact_xlon_ticker_and_issuer_name():
    payload = {
        "data": [
            {
                "name": "iShares Core MSCI World UCITS ETF",
                "stock_exchange": {"mic": "XLON"},
                "symbol": "SWDA",
            }
        ]
    }
    result = audit_identity(payload, instrument())
    assert result["ticker"] == "SWDA"
    assert result["issuer_control_required"] is True

    duplicate = copy.deepcopy(payload)
    duplicate["data"].append(copy.deepcopy(duplicate["data"][0]))
    with pytest.raises(MarketstackAuditError, match="exactly one"):
        audit_identity(duplicate, instrument())

    wrong_exchange = copy.deepcopy(payload)
    wrong_exchange["data"][0]["stock_exchange"]["mic"] = "XNAS"
    with pytest.raises(MarketstackAuditError, match="exactly one"):
        audit_identity(wrong_exchange, instrument())


def test_eod_accepts_only_exact_ordered_session_coverage():
    frozen = contract()
    expected = frozen["boundaries"]["expected_lse_sessions"]
    result = audit_eod(eod_payload(), instrument(), expected)
    assert result["rows"] == 22
    assert result["first_session"] == "2025-09-01"
    assert result["last_session"] == "2025-09-30"
    assert audit_eod_identity(eod_payload(), instrument())["price_currency"] == "GBP"

    missing = eod_payload()
    missing["data"].pop()
    with pytest.raises(MarketstackAuditError, match="coverage"):
        audit_eod(missing, instrument(), expected)

    reversed_rows = eod_payload()
    reversed_rows["data"].reverse()
    with pytest.raises(MarketstackAuditError, match="sequence"):
        audit_eod(reversed_rows, instrument(), expected)


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("date", "2025-09-01T00:00:00", "explicit UTC"),
        ("date", "2025-09-01T00:00:00+01:00", "explicit UTC"),
        ("high", 98, "OHLC"),
        ("volume", -1, "volume"),
        ("open", "NaN", "numeric"),
        ("exchange", "XNAS", "identity"),
    ],
)
def test_eod_rejects_invalid_timestamp_identity_and_values(field: str, value: object, error: str):
    payload = eod_payload()
    payload["data"][0][field] = value
    with pytest.raises(MarketstackAuditError, match=error):
        audit_eod(payload, instrument(), contract()["boundaries"]["expected_lse_sessions"])


def test_provider_errors_non_json_and_non_finite_json_fail_closed():
    with pytest.raises(MarketstackAuditError, match="provider error"):
        parse_response(b'{"data":[],"error":{"code":"invalid_access_key"}}', "fixture")
    with pytest.raises(MarketstackAuditError, match="strict UTF-8 JSON"):
        parse_response(b"<html>challenge</html>", "fixture")
    with pytest.raises(MarketstackAuditError, match="strict UTF-8 JSON"):
        parse_response(b'{"data":[NaN]}', "fixture")


def test_corporate_actions_reject_boundary_crossing_and_wrong_symbol():
    valid = {"data": []}
    assert audit_corporate_actions(valid, instrument(), "splits", "2025-09-01", "2025-09-30")[
        "records"
    ] == 0
    wrong = {
        "data": [
            {
                "date": "2025-10-01T00:00:00+00:00",
                "split_factor": 2,
                "symbol": "SWDA",
            }
        ]
    }
    with pytest.raises(MarketstackAuditError, match="boundary"):
        audit_corporate_actions(wrong, instrument(), "splits", "2025-09-01", "2025-09-30")
