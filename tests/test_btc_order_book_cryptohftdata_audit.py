import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from scripts.audit_btc_order_book_cryptohftdata import (
    inspect_orderbook,
    object_key,
    request_url,
    timestamp_ns,
    validate_redirect_url,
    validate_request_url,
)
from trading_platform.research_program import canonical_json


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = (
    REPO_ROOT / "config/experiments/btc-order-book-cryptohftdata-hour-day-audit-v1.json"
)


def contract() -> dict:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def test_contract_is_canonical_bounded_staged_and_non_predictive():
    raw = CONTRACT_PATH.read_text(encoding="utf-8")
    payload = json.loads(raw)
    assert raw == canonical_json(payload)
    assert payload["boundaries"]["exact_partition_date"] == "2025-08-01"
    assert payload["boundaries"]["full_day_hours_utc"] == list(range(24))
    assert payload["boundaries"]["day_extension_requires_hour_pass"] is True
    assert payload["boundaries"]["sealed_2026_access_allowed"] is False
    assert payload["isolation"]["economic_or_predictive_analysis_allowed"] is False
    assert payload["output"]["feature_generation_allowed"] is False


def test_request_and_redirect_allowlists_reject_wrong_scope():
    payload = contract()
    key = object_key(payload, 20, "orderbook")
    url = request_url(payload, key)
    validate_request_url(payload, url)
    with pytest.raises(ValueError, match="allowlist"):
        validate_request_url(
            payload,
            "https://example.com/v1/download?file=binance_spot%2F2025-08-01%2F20%2FBTCUSDT_orderbook.parquet",
        )
    with pytest.raises(ValueError):
        object_key(payload, 20, "liquidations")
    valid_redirect = (
        "https://bucket.r2.cloudflarestorage.com/cryptohftdata-processed/"
        f"{key}.zst?X-Amz-Signature=test"
    )
    validate_redirect_url(payload, valid_redirect, key)
    with pytest.raises(ValueError, match="allowlist"):
        validate_redirect_url(
            payload,
            f"https://example.com/cryptohftdata-processed/{key}.zst?sig=test",
            key,
        )


def _write_orderbook(path: Path, *, gap: bool = False, crossed: bool = False) -> None:
    base = 1_754_078_400_000_000_000
    update_id = 102 if gap else 101
    table = pa.table(
        {
            "received_time": pa.array(
                [base + 1_000_000] * 4 + [base + 101_000_000],
                type=pa.timestamp("ns", tz="UTC"),
            ),
            "event_time": [base] * 4 + [base + 100_000_000],
            "transaction_time": [None] * 5,
            "symbol": ["BTCUSDT"] * 5,
            "event_type": ["snapshot"] * 4 + ["update"],
            "first_update_id": [None] * 4 + [update_id],
            "final_update_id": [None] * 4 + [update_id],
            "prev_final_update_id": [None] * 4 + [100],
            "last_update_id": [100] * 4 + [None],
            "side": ["bid", "bid", "ask", "ask", "bid"],
            "price": [100.0, 99.0, 101.0, 102.0, 101.0 if crossed else 100.5],
            "quantity": [1.0, 2.0, 1.5, 2.5, 3.0],
            "order_count": [None] * 5,
        }
    )
    pq.write_table(table, path)


def test_timestamp_unit_normalization():
    milliseconds = pa.array([1_754_078_400_000], type=pa.int64())
    nanoseconds = timestamp_ns(milliseconds)
    assert nanoseconds.tolist() == [1_754_078_400_000_000_000]


def test_snapshot_plus_contiguous_update_replays_uncrossed(tmp_path):
    path = tmp_path / "book.parquet"
    _write_orderbook(path)
    result = inspect_orderbook(path, contract(), 20)
    assert result["snapshot_groups"] == 1
    assert result["update_groups"] == 1
    assert result["final_update_id"] == 101
    assert result["replay_uncrossed"] is True


def test_gap_or_crossed_replay_fails_closed(tmp_path):
    gap = tmp_path / "gap.parquet"
    _write_orderbook(gap, gap=True)
    with pytest.raises(ValueError, match="update-ID gap"):
        inspect_orderbook(gap, contract(), 20)
    crossed = tmp_path / "crossed.parquet"
    _write_orderbook(crossed, crossed=True)
    with pytest.raises(ValueError, match="crossed"):
        inspect_orderbook(crossed, contract(), 20)
