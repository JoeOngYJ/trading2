from __future__ import annotations

import ast
import copy
import json
from pathlib import Path

import pytest

from trading_platform.cross_asset_gbp_conversion import build_request_specs, load_contract
from trading_platform.cross_asset_oanda_hourly import OandaHourlyError, canonical_json


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/experiments/cross-asset-a2-gbp-conversion-source-v1.json"
MANDATE = ROOT / "config/mandates/retail-cross-asset-research-v7.json"


def test_conversion_source_is_exact_bounded_and_never_a_strategy_instrument():
    contract = load_contract(CONTRACT, MANDATE, ROOT)
    assert len(build_request_specs(contract, ROOT)) == 32
    assert contract["instrument"]["instrument_id"] == "GBP_USD"
    assert contract["instrument"]["eligible_as_strategy_instrument"] is False
    assert contract["acceptance_rules"]["strategy_evaluation_authorized_by_this_source_experiment"] is False
    assert contract["evidence_boundary"]["sealed_2026_price_access_allowed"] is False


def test_conversion_contract_rejects_strategy_eligibility_drift(tmp_path: Path):
    value = json.loads(CONTRACT.read_text())
    value["instrument"]["eligible_as_strategy_instrument"] = True
    unsafe = tmp_path / "unsafe.json"
    unsafe.write_text(canonical_json(value))
    with pytest.raises(OandaHourlyError, match="purpose changed"):
        load_contract(unsafe, MANDATE, ROOT)


def test_conversion_module_is_offline():
    source = (ROOT / "src/trading_platform/cross_asset_gbp_conversion.py").read_text()
    tree = ast.parse(source)
    imports = {
        alias.name
        for node in ast.walk(tree)
        for alias in (node.names if isinstance(node, ast.Import) else ())
    }
    imports.update(
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module
    )
    assert not any(name.startswith(("urllib", "requests", "psycopg", "nats", "freqtrade")) for name in imports)
