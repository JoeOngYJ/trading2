from __future__ import annotations

import copy
import ast
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from trading_platform.cross_asset_oanda_hourly import (
    INSTRUMENT_IDS,
    OandaHourlyError,
    _session_result,
    build_request_specs,
    canonical_json,
    load_contract,
    parse_candle_row,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/experiments/cross-asset-a1-oanda-hourly-history-v1.json"
MANDATE = ROOT / "config/mandates/retail-cross-asset-research-v6.json"


def load() -> dict:
    return load_contract(CONTRACT, MANDATE, ROOT)


def candle(time: str = "2025-01-02T10:00:00Z") -> dict:
    return {
        "ask": {"c": "101.2", "h": "102", "l": "100", "o": "101"},
        "bid": {"c": "101.0", "h": "101.8", "l": "99.8", "o": "100.8"},
        "complete": True,
        "time": time,
        "volume": 12,
    }


def test_frozen_hourly_contract_is_canonical_bounded_and_price_only():
    contract = load()
    assert CONTRACT.read_text() == canonical_json(json.loads(CONTRACT.read_text()))
    assert tuple(item["instrument_id"] for item in contract["candidate_instruments"]) == INSTRUMENT_IDS
    specs = build_request_specs(contract)
    assert len(specs) == 224
    assert all(spec.parameters["granularity"] == "H1" for spec in specs)
    assert all(spec.parameters["price"] == "BA" for spec in specs)
    assert max(spec.parameters["to"] for spec in specs) == "2026-01-01T00:00:00Z"
    assert contract["acceptance_rules"]["missing_required_window_bar_disposition"] == "no_trade"
    assert contract["acceptance_rules"]["strategy_evaluation_authorized_by_this_experiment"] is False
    assert contract["prohibitions"]["market_returns_or_pnl_allowed"] is False


def test_hourly_contract_rejects_universe_and_request_budget_drift(tmp_path: Path):
    payload = json.loads(CONTRACT.read_text())
    payload["candidate_instruments"][0]["instrument_id"] = "SUBSTITUTED"
    unsafe = tmp_path / "unsafe.json"
    unsafe.write_text(canonical_json(payload))
    with pytest.raises(OandaHourlyError, match="universe changed"):
        load_contract(unsafe, MANDATE, ROOT)

    payload = json.loads(CONTRACT.read_text())
    payload["request_plan"]["maximum_requests"] = 225
    unsafe.write_text(canonical_json(payload))
    with pytest.raises(OandaHourlyError, match="request plan changed"):
        load_contract(unsafe, MANDATE, ROOT)


def test_hourly_row_rejects_naive_future_crossed_and_reversed_prices():
    lower = datetime(2025, 1, 1, tzinfo=timezone.utc)
    upper = datetime(2025, 7, 1, tzinfo=timezone.utc)
    with pytest.raises(OandaHourlyError, match="UTC Z"):
        parse_candle_row(candle("2025-01-02T10:00:00"), "EUR_USD", lower, upper)
    with pytest.raises(OandaHourlyError, match="outside frozen chunk"):
        parse_candle_row(candle("2026-01-02T10:00:00Z"), "EUR_USD", lower, upper)
    crossed = candle()
    crossed["ask"]["c"] = "100.9"
    with pytest.raises(OandaHourlyError, match="crossed"):
        parse_candle_row(crossed, "EUR_USD", lower, upper)
    reversed_ohlc = candle()
    reversed_ohlc["bid"]["l"] = "101.2"
    with pytest.raises(OandaHourlyError, match="invalid bid OHLC"):
        parse_candle_row(reversed_ohlc, "EUR_USD", lower, upper)


def test_session_windows_follow_local_dst_and_missing_bar_fails_closed():
    contract = load()
    candidate = next(item for item in contract["candidate_instruments"] if item["instrument_id"] == "EUR_USD")
    # 09:00--12:00 and 16:00 New York: UTC shifts after US DST.
    complete = [
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        for value in (
            "2025-01-02T14:00:00Z",
            "2025-01-02T15:00:00Z",
            "2025-01-02T16:00:00Z",
            "2025-01-02T17:00:00Z",
            "2025-01-02T21:00:00Z",
            "2025-07-02T13:00:00Z",
            "2025-07-02T14:00:00Z",
            "2025-07-02T15:00:00Z",
            "2025-07-02T16:00:00Z",
            "2025-07-02T20:00:00Z",
        )
    ]
    result = _session_result(complete, candidate, contract)
    assert result["complete_session_days"] == 2
    assert result["incomplete_observed_session_days"] == 0
    missing = _session_result(complete[:-1], candidate, contract)
    assert missing["complete_session_days"] == 1
    assert missing["incomplete_observed_session_days"] == 1


def test_offline_hourly_module_has_no_network_or_platform_integrations():
    source = (ROOT / "src/trading_platform/cross_asset_oanda_hourly.py").read_text()
    tree = ast.parse(source)
    imports = {
        alias.name
        for node in ast.walk(tree)
        for alias in (node.names if isinstance(node, ast.Import) else ())
    }
    imports.update(
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module
    )
    for forbidden in ("urllib", "requests", "psycopg", "nats", "freqtrade"):
        assert not any(name == forbidden or name.startswith(f"{forbidden}.") for name in imports)
    assert "OrderIntent" not in source
    assert "SignalPayload" not in source
