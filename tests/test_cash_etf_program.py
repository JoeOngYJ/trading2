from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from trading_platform.cash_etf_program import (
    CashEtfContextError,
    _validate_boundaries,
    _validate_program,
    _validate_registry,
    _validate_strategy_contract,
    canonical_json,
    validate_context,
)


ROOT = Path(__file__).parents[1]


def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_cash_etf_context_is_valid_and_locked_to_no_trade():
    result = validate_context(ROOT)
    assert result["decision"] == "context_valid"
    assert result["accepted_strategy_arms"] == 0
    assert result["approved_execution_instruments"] == 0


def test_program_rejects_direct_futures_permission():
    payload = load("config/research/cash-etf-program-v1.json")
    payload["safety_boundaries"]["direct_futures_data_allowed"] = True
    with pytest.raises(CashEtfContextError, match="direct_futures"):
        _validate_program(payload)


def test_registry_rejects_proxy_execution_promotion():
    payload = load("config/research/cash-etf-proxy-registry-v1.json")
    payload["proxy_instruments"][0]["execution_eligible"] = True
    with pytest.raises(CashEtfContextError, match="execution eligible"):
        _validate_registry(payload)


def test_boundaries_reject_open_confirmation():
    payload = load("config/research/cash-etf-evidence-boundaries-v1.json")
    payload["partitions"][2]["state"] = "open"
    with pytest.raises(CashEtfContextError, match="boundaries changed"):
        _validate_boundaries(payload)


def test_strategy_contract_rejects_parameter_tuning():
    payload = load("config/experiments/cash-etf-slow-trend-proxy-v1.json")
    payload["rule"]["lookback_sessions"] = 251
    with pytest.raises(CashEtfContextError, match="slow-trend rule changed"):
        _validate_strategy_contract(payload, "cash-etf-slow-trend-proxy-v1")


def test_canonical_json_rejects_nan():
    with pytest.raises(ValueError):
        canonical_json({"bad": float("nan")})
