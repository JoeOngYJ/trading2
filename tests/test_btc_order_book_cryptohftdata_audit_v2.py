import json
from pathlib import Path

import pyarrow as pa
import pytest

from scripts.audit_btc_order_book_cryptohftdata_v2 import (
    _common_time_checks_v2,
    verify_predecessor,
)
from trading_platform.research_program import canonical_json


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = (
    REPO_ROOT / "config/experiments/btc-order-book-cryptohftdata-hour-day-audit-v2.json"
)


def contract() -> dict:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def test_successor_contract_is_canonical_and_preserves_v1_rejection():
    raw = CONTRACT_PATH.read_text(encoding="utf-8")
    payload = json.loads(raw)
    assert raw == canonical_json(payload)
    assert payload["replacement_of"] == "btc-order-book-cryptohftdata-hour-day-audit-v1"
    assert payload["decision_rule"]["partition_clock"] == "received_time"
    assert payload["decision_rule"]["maximum_received_minus_exchange_time_ms"] == 5000
    assert "rewrite_or_relabel_the_v1_rejection" in payload["prohibited_actions"]
    assert payload["boundaries"]["sealed_2026_access_allowed"] is False


def test_inherited_pilot_bytes_and_predecessor_manifests_are_immutable():
    objects = verify_predecessor(contract())
    assert [item["data_type"] for item in objects] == ["orderbook", "trades"]
    assert all(item["hour_utc"] == 20 for item in objects)


def test_received_time_owns_partition_and_causal_preboundary_event_is_allowed():
    start = 1_754_078_400_000_000_000
    table = pa.table(
        {
            "received_time": [start + 36_000_000, start + 100_000_000],
            "event_time": [start - 86_000_000, start + 10_000_000],
        }
    )
    _received, _event, summary = _common_time_checks_v2(table, "2025-08-01", 20)
    assert summary["min_event_time_ns"] == start - 86_000_000
    assert summary["max_received_minus_event_ns"] == 122_000_000


def test_noncausal_or_over_five_second_arrival_lag_fails_closed():
    start = 1_754_078_400_000_000_000
    noncausal = pa.table(
        {"received_time": [start + 1], "event_time": [start + 2]}
    )
    with pytest.raises(ValueError, match="precedes"):
        _common_time_checks_v2(noncausal, "2025-08-01", 20)
    stale = pa.table(
        {
            "received_time": [start + 6_000_000_000],
            "event_time": [start],
        }
    )
    with pytest.raises(ValueError, match="five-second"):
        _common_time_checks_v2(stale, "2025-08-01", 20)
