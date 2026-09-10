import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from scripts.audit_btc_order_book_cryptolake_sample import (
    inspect_parquet,
    raw_replay_missing,
    validate_url,
)
from trading_platform.research_program import canonical_json


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = (
    REPO_ROOT / "config/experiments/btc-order-book-cryptolake-sample-audit-v1.json"
)


def contract() -> dict:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def timestamp(values: list[int]) -> pa.Array:
    return pa.array(values, type=pa.timestamp("ns", tz="UTC"))


def book_spec() -> dict:
    return contract()["inputs"]["objects"][0]


def write_book(path: Path, *, crossed: bool = False, out_of_partition: bool = False) -> None:
    base = 1_664_582_400_000_000_000
    if out_of_partition:
        base += 86_400_000_000_000
    table = pa.table(
        {
            "received_time": timestamp([base, base + 100_000_000]),
            "sequence_number": [10, 11],
            "bid_0_price": [19_500.0, 19_501.0],
            "bid_0_size": [1.0, 2.0],
            "ask_0_price": [19_499.0 if crossed else 19_501.0, 19_502.0],
            "ask_0_size": [1.5, 2.5],
            "exchange": ["BINANCE", "BINANCE"],
            "symbol": ["BTC-USDT", "BTC-USDT"],
        }
    )
    pq.write_table(table, path)


def test_contract_is_canonical_bounded_and_non_predictive():
    raw = CONTRACT_PATH.read_text(encoding="utf-8")
    payload = json.loads(raw)
    assert raw == canonical_json(payload)
    assert payload["boundaries"]["sealed_2026_access_allowed"] is False
    assert payload["isolation"]["economic_or_predictive_analysis_allowed"] is False
    assert payload["output"]["feature_generation_allowed"] is False
    assert all(not value.startswith("2026-") for value in payload["boundaries"]["allowed_partition_dates"])


def test_url_allowlist_rejects_2026_and_other_hosts():
    payload = contract()
    validate_url(payload, payload["inputs"]["objects"][0]["url"])
    with pytest.raises(ValueError, match="allowlist"):
        validate_url(payload, "https://example.com/sample.crypto.lake/file.parquet")
    with pytest.raises(ValueError, match="sealed-2026"):
        validate_url(
            payload,
            "https://s3.eu-west-1.amazonaws.com/sample.crypto.lake/book/dt=2026-01-01/file.parquet",
        )


def test_valid_book_fixture_passes_bounded_quality_checks(tmp_path):
    path = tmp_path / "book.parquet"
    write_book(path)
    result = inspect_parquet(path, book_spec(), "BINANCE", "BTC-USDT")
    assert result["row_count"] == 2
    assert result["sequence_non_decreasing"] is True
    assert result["venue_values"] == ["BINANCE"]


def test_crossed_or_wrong_partition_book_fails_closed(tmp_path):
    crossed = tmp_path / "crossed.parquet"
    write_book(crossed, crossed=True)
    with pytest.raises(ValueError, match="crossed"):
        inspect_parquet(crossed, book_spec(), "BINANCE", "BTC-USDT")
    wrong_day = tmp_path / "wrong-day.parquet"
    write_book(wrong_day, out_of_partition=True)
    with pytest.raises(ValueError, match="partition"):
        inspect_parquet(wrong_day, book_spec(), "BINANCE", "BTC-USDT")


def test_normalized_samples_cannot_satisfy_native_replay_contract():
    inspections = [
        {
            "columns": book_spec()["required_columns"],
            "dataset": "book",
            "partition_date": "2022-10-01",
        },
        {
            "columns": contract()["inputs"]["objects"][1]["required_columns"],
            "dataset": "trades",
            "partition_date": "2022-10-01",
        },
        {
            "columns": contract()["inputs"]["objects"][2]["required_columns"],
            "dataset": "book_delta_v2",
            "partition_date": "2024-04-01",
        },
    ]
    missing = raw_replay_missing(inspections)
    assert "first_update_id_U" in missing
    assert "final_update_id_u" in missing
    assert "same_partition_snapshot_delta_and_trade_bundle" in missing
    assert "gap_reconnect_resubscribe_parse_clock_and_drop_incident_log" in missing
