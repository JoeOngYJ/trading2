from __future__ import annotations

import copy
from pathlib import Path

import pytest

from trading_platform.cross_asset_twelvedata_audit import (
    EXPECTED_SYMBOLS,
    TwelveDataAuditError,
    audit_corporate_actions,
    audit_earliest,
    audit_identity,
    audit_time_series,
    build_request_specs,
    load_contract,
    parse_response,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = (
    ROOT / "config/experiments/cross-asset-a1-twelvedata-economic-proxy-pilot-v1.json"
)


def contract() -> dict:
    return load_contract(CONTRACT_PATH)


def instrument(symbol: str = "SPY") -> dict:
    return next(item for item in contract()["instruments"] if item["symbol"] == symbol)


def meta(symbol: str = "SPY") -> dict:
    if symbol == "GBP/USD":
        return {
            "currency_base": "British Pound",
            "currency_quote": "US Dollar",
            "interval": "1day",
            "symbol": symbol,
            "type": "Physical Currency",
        }
    return {
        "currency": "USD",
        "exchange": "NYSE",
        "interval": "1day",
        "mic_code": "ARCX",
        "symbol": symbol,
        "type": "ETF",
    }


def series_payload(symbol: str = "SPY") -> dict:
    sessions = (
        contract()["boundaries"]["expected_fx_sessions"]
        if symbol == "GBP/USD"
        else contract()["boundaries"]["expected_us_etf_sessions"]
    )
    values = [
        {
            "close": "101",
            "datetime": session,
            "high": "102",
            "low": "99",
            "open": "100",
            **({} if symbol == "GBP/USD" else {"volume": "1000"}),
        }
        for session in sessions
    ]
    return {"meta": meta(symbol), "status": "ok", "values": values}


def test_contract_is_canonical_bounded_and_source_only():
    frozen = contract()
    assert tuple(item["symbol"] for item in frozen["instruments"]) == EXPECTED_SYMBOLS
    assert frozen["strategy_evaluation_authorized"] is False
    assert frozen["prohibitions"]["pnl_allowed"] is False
    assert frozen["decision_rule"]["a1_stage_passed_by_pilot"] is False
    assert frozen["sources"]["twelvedata_grow"]["adjustment_mode"] == "none"


def test_request_plan_is_exact_weighted_and_contains_no_token_parameter():
    specs = build_request_specs(contract())
    assert len(specs) == 20
    assert sum(item.weight for item in specs) == 58
    assert sum(item.weight for item in specs if item.phase == 1) == 18
    assert sum(item.weight for item in specs if item.phase == 2) == 40
    assert all("apikey" not in key.casefold() for item in specs for key in item.persisted_parameters)
    assert {(item.symbol, item.endpoint) for item in specs if item.phase == 2} == {
        ("SPY", "dividends"),
        ("SPY", "splits"),
    }


def test_identity_requires_exact_etf_and_fx_metadata():
    assert audit_identity(meta(), instrument())["mic_code"] == "ARCX"
    assert audit_identity(meta("GBP/USD"), instrument("GBP/USD"))["currency_quote"] == "US Dollar"
    wrong = meta()
    wrong["mic_code"] = "XNAS"
    with pytest.raises(TwelveDataAuditError, match="MIC"):
        audit_identity(wrong, instrument())
    wrong_fx = meta("GBP/USD")
    wrong_fx["currency_base"] = "Euro"
    with pytest.raises(TwelveDataAuditError, match="base or quote"):
        audit_identity(wrong_fx, instrument("GBP/USD"))


def test_earliest_history_must_meet_frozen_threshold():
    result = audit_earliest({"datetime": "1993-01-29"}, instrument())
    assert result["earliest_date"] == "1993-01-29"
    with pytest.raises(TwelveDataAuditError, match="after the frozen threshold"):
        audit_earliest({"datetime": "2010-01-01"}, instrument())


def test_time_series_requires_exact_ordered_coverage_and_valid_ohlcv():
    frozen = contract()
    sessions = frozen["boundaries"]["expected_us_etf_sessions"]
    result = audit_time_series(series_payload(), instrument(), sessions)
    assert result["rows"] == 19
    missing = series_payload()
    missing["values"].pop()
    with pytest.raises(TwelveDataAuditError, match="coverage"):
        audit_time_series(missing, instrument(), sessions)
    reversed_rows = series_payload()
    reversed_rows["values"].reverse()
    with pytest.raises(TwelveDataAuditError, match="sequence"):
        audit_time_series(reversed_rows, instrument(), sessions)


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("datetime", "2025-02-03T00:00:00", "date-only"),
        ("high", "98", "OHLC"),
        ("volume", "-1", "volume"),
        ("open", "NaN", "numeric"),
    ],
)
def test_time_series_rejects_invalid_labels_and_values(field: str, value: str, error: str):
    payload = series_payload()
    payload["values"][0][field] = value
    with pytest.raises(TwelveDataAuditError, match=error):
        audit_time_series(
            payload, instrument(), contract()["boundaries"]["expected_us_etf_sessions"]
        )


def test_fx_allows_missing_volume_but_not_a_gap():
    payload = series_payload("GBP/USD")
    sessions = contract()["boundaries"]["expected_fx_sessions"]
    assert audit_time_series(payload, instrument("GBP/USD"), sessions)["rows"] == 20
    payload["values"].pop(10)
    with pytest.raises(TwelveDataAuditError, match="coverage"):
        audit_time_series(payload, instrument("GBP/USD"), sessions)


def test_successor_allows_only_ordered_rows_outside_the_frozen_boundary():
    payload = series_payload()
    payload["values"] = [
        {**payload["values"][0], "datetime": "2025-01-31"},
        *payload["values"],
        {**payload["values"][-1], "datetime": "2025-03-03"},
    ]
    sessions = contract()["boundaries"]["expected_us_etf_sessions"]
    result = audit_time_series(payload, instrument(), sessions, allow_boundary_buffer=True)
    assert result["buffer_rows"] == 2
    holiday = copy.deepcopy(payload)
    holiday["values"].insert(11, {**payload["values"][10], "datetime": "2025-02-17"})
    with pytest.raises(TwelveDataAuditError, match="coverage"):
        audit_time_series(holiday, instrument(), sessions, allow_boundary_buffer=True)


def test_corporate_action_schema_is_attributable_and_boundary_limited():
    empty = {"dividends": [], "meta": meta(), "status": "ok"}
    assert audit_corporate_actions(empty, instrument(), "dividends", "2025-02-03", "2025-02-28")[
        "records"
    ] == 0
    split = {
        "meta": meta(),
        "splits": [{"date": "2025-02-10", "ratio": "2:1"}],
        "status": "ok",
    }
    assert audit_corporate_actions(split, instrument(), "splits", "2025-02-03", "2025-02-28")[
        "records"
    ] == 1
    outside = copy.deepcopy(split)
    outside["splits"][0]["date"] = "2025-03-01"
    with pytest.raises(TwelveDataAuditError, match="boundary"):
        audit_corporate_actions(outside, instrument(), "splits", "2025-02-03", "2025-02-28")


def test_provider_errors_non_json_and_non_finite_json_fail_closed():
    with pytest.raises(TwelveDataAuditError, match="provider error"):
        parse_response(b'{"code":401,"message":"bad key","status":"error"}', "fixture")
    with pytest.raises(TwelveDataAuditError, match="strict UTF-8 JSON"):
        parse_response(b"<html>challenge</html>", "fixture")
    with pytest.raises(TwelveDataAuditError, match="strict UTF-8 JSON"):
        parse_response(b'{"values":[NaN]}', "fixture")
