import json
from pathlib import Path

import pytest

from scripts.validate_btc_order_book_tardis_pilot_contract import (
    TardisPilotContractError,
    validate_contract,
)
from trading_platform.research_program import canonical_json


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = REPO_ROOT / "config/experiments/btc-order-book-tardis-raw-pilot-v1.json"


def contract() -> dict:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def write_contract(path: Path, payload: dict) -> None:
    path.write_text(canonical_json(payload), encoding="utf-8")


def test_repository_contract_is_canonical_frozen_and_blocked():
    result = validate_contract()
    assert result["decision"] == "contract_valid_execution_blocked"
    assert result["exact_partition_dates"] == ["2019-12-01", "2022-12-01", "2025-12-01"]
    assert result["purchase_authorized"] is False
    assert result["sealed_2026_access_allowed"] is False


def test_contract_allows_only_native_raw_channels():
    payload = contract()
    assert payload["inputs"]["format"] == "exchange_native_ndjson_with_local_timestamp"
    assert payload["inputs"]["channels"] == ["aggTrade", "depth", "depthSnapshot"]
    assert payload["decision_rule"]["normalized_csv_can_satisfy_raw_contract"] is False


def test_future_or_2026_partition_fails_closed(tmp_path):
    payload = contract()
    payload["boundaries"]["exact_partition_dates"][-1] = "2026-01-01"
    path = tmp_path / "contract.json"
    write_contract(path, payload)
    with pytest.raises(TardisPilotContractError, match="pilot dates changed"):
        validate_contract(path)


def test_execution_or_purchase_authorization_fails_closed(tmp_path):
    payload = contract()
    payload["access_and_budget"]["purchase_authorized"] = True
    path = tmp_path / "purchase.json"
    write_contract(path, payload)
    with pytest.raises(TardisPilotContractError, match="cannot authorize a purchase"):
        validate_contract(path)

    payload = contract()
    payload["execution_prerequisites"]["state"] = "ready"
    path = tmp_path / "execute.json"
    write_contract(path, payload)
    with pytest.raises(TardisPilotContractError, match="must remain blocked"):
        validate_contract(path)


def test_official_reference_host_is_allowlisted(tmp_path):
    payload = contract()
    payload["inputs"]["provider_documentation"][0] = "https://example.com/fake"
    path = tmp_path / "host.json"
    write_contract(path, payload)
    with pytest.raises(TardisPilotContractError, match="official host"):
        validate_contract(path)
