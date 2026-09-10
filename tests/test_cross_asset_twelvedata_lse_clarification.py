from __future__ import annotations

import json
from pathlib import Path

from trading_platform.cross_asset_twelvedata_lse_clarification import (
    _audit_direction_agnostic_actions,
    _compatible_instrument,
    build_request_specs,
    load_contract,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/experiments/cross-asset-a1-executable-universe-feasibility-v2.json"
VAGS_DIVIDENDS = ROOT / "artifacts/agent-level-experiment/cross-asset/a1-executable-universe-feasibility-v1/raw/vags-dividends.json"


def test_clarification_freezes_four_corrected_requests_only():
    contract = load_contract(CONTRACT)
    specs = build_request_specs(contract)
    assert len(specs) == 4
    assert all(item.parameters["end_date"] == "2025-03-01" for item in specs)
    assert all(item.parameters["order"] == "ASC" for item in specs)
    assert {item.provider_symbol for item in specs} == {
        "SWDA:LSE",
        "VAGS:LSE",
        "SGLN:LSE",
        "COMM:LSE",
    }


def test_v1_descending_dividends_are_unique_monotonic_and_valid():
    contract = load_contract(CONTRACT)
    instrument = _compatible_instrument(contract["expected_instruments"][1])
    payload = json.loads(VAGS_DIVIDENDS.read_text(encoding="utf-8"))
    result = _audit_direction_agnostic_actions(
        payload,
        instrument,
        "dividends",
        "2024-01-01",
        "2025-02-28",
    )
    assert result == {"endpoint": "dividends", "provider_order": "descending", "records": 14}
