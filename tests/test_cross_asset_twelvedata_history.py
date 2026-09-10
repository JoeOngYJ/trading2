from __future__ import annotations

import json
from pathlib import Path

import pytest

from trading_platform.cross_asset_twelvedata_history import (
    ETF_SYMBOLS,
    SYMBOLS,
    TwelveDataHistoryError,
    available_at,
    build_request_specs,
    load_contract,
    normalized_action_lines,
    normalized_price_lines,
    phase_offsets,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "config/experiments/cross-asset-a1-twelvedata-full-history-v1.json"
SUCCESSOR_PATH = ROOT / "config/experiments/cross-asset-a1-twelvedata-full-history-v2.json"


def loaded():
    return load_contract(CONTRACT_PATH, ROOT)


def test_contract_freezes_exact_universe_calendars_and_no_strategy_outputs():
    contract, pilot, calendars = loaded()
    assert tuple(contract["instruments"]) == SYMBOLS
    assert tuple(item["symbol"] for item in pilot["instruments"]) == SYMBOLS
    assert calendars["us_exchange"]["session_count"] == 4529
    assert calendars["fx"]["session_count"] == 4671
    assert contract["prohibitions"]["return_calculation_allowed"] is False
    assert contract["prohibitions"]["strategy_signals_allowed"] is False


def test_request_plan_is_25_calls_329_credits_and_token_free():
    contract, _, _ = loaded()
    specs = build_request_specs(contract)
    assert len(specs) == 25
    assert sum(item.weight for item in specs) == 329
    assert {(item.symbol, item.endpoint) for item in specs if item.endpoint != "time_series"} == {
        (symbol, endpoint) for symbol in ETF_SYMBOLS for endpoint in ("dividends", "splits")
    }
    assert phase_offsets(contract)[9] == 488
    assert all("apikey" not in key.casefold() for item in specs for key in item.parameters)
    dividend = next(item for item in specs if item.symbol == "SPY" and item.endpoint == "dividends")
    assert dividend.parameters["adjust"] == "false"


def test_interrupted_v1_is_preserved_and_v2_changes_only_artifact_root():
    contract, _, _ = load_contract(SUCCESSOR_PATH, ROOT)
    assert contract["experiment_id"] == "cross-asset-a1-twelvedata-full-history-v2"
    assert contract["output"]["artifact_root"].endswith("full-history-v2")
    assert len(build_request_specs(contract)) == 25


def test_availability_is_conservative_next_calendar_day_0500_utc():
    assert available_at("2025-12-31") == "2026-01-01T05:00:00Z"
    with pytest.raises(TwelveDataHistoryError, match="invalid session"):
        available_at("not-a-date")


def test_price_normalization_emits_point_in_time_rows_without_returns():
    _, pilot, _ = loaded()
    instrument = next(item for item in pilot["instruments"] if item["symbol"] == "SPY")
    sessions = ["2025-02-03", "2025-02-04"]
    payload = {
        "meta": {
            "currency": "USD",
            "exchange": "NYSE",
            "interval": "1day",
            "mic_code": "ARCX",
            "symbol": "SPY",
            "type": "ETF",
        },
        "values": [
            {
                "close": "101.00",
                "datetime": session,
                "high": "102",
                "low": "99",
                "open": "100",
                "volume": "1000",
            }
            for session in sessions
        ],
    }
    lines = normalized_price_lines(payload, instrument, sessions, "a" * 64)
    row = json.loads(lines[0])
    assert row["available_at"] == "2025-02-04T05:00:00Z"
    assert row["close"] == "101"
    assert "return" not in row and "signal" not in row


def test_action_normalization_accepts_official_numeric_split_schema_and_sorts():
    _, pilot, _ = loaded()
    instrument = dict(next(item for item in pilot["instruments"] if item["symbol"] == "SPY"))
    payload = {
        "meta": {"currency": "USD", "mic_code": "ARCX", "symbol": "SPY"},
        "splits": [
            {
                "date": "2020-08-31",
                "description": "4-for-1 split",
                "from_factor": 1,
                "ratio": 4,
                "to_factor": 4,
            }
        ],
    }
    lines = normalized_action_lines(
        payload, instrument, "splits", "b" * 64, "2008-01-02", "2025-12-31"
    )
    assert json.loads(lines[0])["ratio"] == "4"
    bad = dict(payload)
    bad["splits"] = [{**payload["splits"][0], "to_factor": 3}]
    with pytest.raises(TwelveDataHistoryError, match="conflicts"):
        normalized_action_lines(
            bad, instrument, "splits", "b" * 64, "2008-01-02", "2025-12-31"
        )
