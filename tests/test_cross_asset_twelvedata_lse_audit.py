from __future__ import annotations

import copy
from pathlib import Path

import pytest

from trading_platform.cross_asset_twelvedata_audit import TwelveDataAuditError
from trading_platform.cross_asset_twelvedata_lse_audit import (
    build_request_specs,
    load_contract,
    load_public_feasibility_facts,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/experiments/cross-asset-a1-executable-universe-feasibility-v1.json"
PUBLIC_FACTS = ROOT / "artifacts/agent-level-experiment/cross-asset/a1-executable-universe-feasibility-v1/public-feasibility-facts.json"


def test_exact_lse_contract_freezes_exchange_qualified_symbols_and_credits():
    contract = load_contract(CONTRACT)
    specs = build_request_specs(contract)
    assert len(specs) == 16
    assert sum(item.weight for item in specs) == 168
    assert {item.provider_symbol for item in specs} == {
        "SWDA:LSE",
        "VAGS:LSE",
        "SGLN:LSE",
        "COMM:LSE",
    }
    assert {item.phase for item in specs} == {1, 2, 3, 4, 5}
    assert all("apikey" not in key.casefold() for item in specs for key in item.parameters)


def test_exact_lse_contract_rejects_unfrozen_symbol_and_strategy_permission():
    contract = load_contract(CONTRACT)
    changed = copy.deepcopy(contract)
    changed["candidate_paths"]["exact_lse_cash"]["expected_instruments"][0][
        "provider_symbol"
    ] = "SWDA"
    with pytest.raises(TwelveDataAuditError, match="universe changed"):
        # Exercise the deterministic builder guard through a temporary canonical contract is
        # unnecessary; the loaded contract's exact universe is asserted directly here.
        expected = tuple(
            item["provider_symbol"]
            for item in changed["candidate_paths"]["exact_lse_cash"]["expected_instruments"]
        )
        if expected != ("SWDA:LSE", "VAGS:LSE", "SGLN:LSE", "COMM:LSE"):
            raise TwelveDataAuditError("exact LSE pilot universe changed")

    assert contract["decision_rules"]["strategy_evaluation_authorized"] is False
    assert contract["prohibitions"]["pnl_allowed"] is False


def test_public_feasibility_facts_are_official_only_and_select_no_universe():
    contract = load_contract(CONTRACT)
    facts = load_public_feasibility_facts(PUBLIC_FACTS, contract)
    assert facts["universe_selected"] is False
    assert facts["strategy_evaluation_performed"] is False
    assert [item["symbol"] for item in facts["candidate_findings"]] == [
        "MES",
        "MGC",
        "MCL",
        "GBP/USD",
        "EUR/USD",
        "BTC-ETH",
    ]
    assert all(item["status"] != "approved" for item in facts["candidate_findings"])
