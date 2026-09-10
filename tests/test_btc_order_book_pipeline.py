import csv
import gzip
import importlib.util
import json
from pathlib import Path
import sys

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "btc_order_book_pipeline.py"
SPEC = importlib.util.spec_from_file_location("btc_order_book_pipeline", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def record(sequence, kind, *, connection_id=1, **values):
    return {
        "schema_version": MODULE.SCHEMA_VERSION,
        "capture_id": "test-capture",
        "sequence": sequence,
        "kind": kind,
        "connection_id": connection_id,
        "receipt_time_ns": 1_700_000_000_000_000_000 + sequence,
        **values,
    }


def snapshot(sequence=1, last_update_id=100, bids=None, asks=None):
    payload = {
        "lastUpdateId": last_update_id,
        "bids": bids or [["99", "1"], ["98", "2"]],
        "asks": asks or [["101", "2"], ["102", "3"]],
    }
    return record(
        sequence, "snapshot", last_update_id=last_update_id,
        raw_json=MODULE.canonical_json(payload),
    )


def depth(sequence, first_id, final_id, bids, asks, event_time=1_700_000_000_000):
    payload = {
        "e": "depthUpdate", "E": event_time, "s": "BTCUSDT",
        "U": first_id, "u": final_id, "b": bids, "a": asks,
    }
    envelope = {"stream": "btcusdt@depth@100ms", "data": payload}
    return record(
        sequence, "stream", stream="btcusdt@depth@100ms",
        raw_json=MODULE.canonical_json(envelope),
    )


def trade(sequence, aggregate_id=10, buyer_is_maker=False):
    payload = {
        "e": "aggTrade", "E": 1_700_000_000_001, "s": "BTCUSDT",
        "a": aggregate_id, "p": "100.5", "q": "2", "f": 20, "l": 21,
        "T": 1_700_000_000_000, "m": buyer_is_maker, "M": True,
    }
    envelope = {"stream": "btcusdt@aggTrade", "data": payload}
    return record(
        sequence, "stream", stream="btcusdt@aggTrade",
        raw_json=MODULE.canonical_json(envelope),
    )


def read_csv(path):
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_snapshot_bridge_and_features_are_exact(tmp_path):
    records = [
        snapshot(),
        depth(2, 90, 100, [["99", "9"]], []),  # stale and must not mutate the book
        depth(3, 100, 101, [["99", "3"]], [["101", "1"]]),
    ]
    manifest = MODULE.replay_records(records, tmp_path)
    rows = read_csv(tmp_path / "btc-order-book-features.csv.gz")
    assert manifest["status"] == "accepted"
    assert manifest["stale_depth_events"] == 1
    assert manifest["feature_rows"] == 1
    assert rows[0]["best_bid"] == "99"
    assert rows[0]["best_ask"] == "101"
    assert rows[0]["queue_imbalance_l1"] == "0.500000000000000000"
    assert rows[0]["ofi_l1"] == "3"
    assert rows[0]["bid_add_qty"] == "2"
    assert rows[0]["ask_remove_qty"] == "1"
    assert manifest["hourly_quality"][0]["accepted_depth_events"] == 1
    assert manifest["hourly_quality"][0]["stale_depth_events"] == 1
    assert manifest["hourly_quality"][0]["bid_levels_min"] == 2


def test_update_gap_rejects_until_a_new_snapshot(tmp_path):
    records = [snapshot(), depth(2, 102, 102, [], [])]
    manifest = MODULE.replay_records(records, tmp_path)
    assert manifest["status"] == "rejected"
    assert manifest["feature_rows"] == 0
    assert manifest["rejected_intervals"][0]["reason"] == "update_gap"
    assert manifest["rejected_intervals"][0]["expected_update_id"] == 101


def test_crossed_book_is_rejected(tmp_path):
    records = [snapshot(), depth(2, 101, 101, [["102", "1"]], [])]
    manifest = MODULE.replay_records(records, tmp_path)
    assert manifest["feature_rows"] == 0
    assert "crossed or locked" in manifest["rejected_intervals"][0]["reason"]


@pytest.mark.parametrize(
    ("buyer_is_maker", "side", "signed_quantity"),
    [(False, "buy", "2"), (True, "sell", "-2")],
)
def test_aggregate_trade_aggressor_side(tmp_path, buyer_is_maker, side, signed_quantity):
    manifest = MODULE.replay_records([trade(1, buyer_is_maker=buyer_is_maker)], tmp_path)
    rows = read_csv(tmp_path / "btc-aggregate-trades.csv.gz")
    assert manifest["trade_rows"] == 1
    assert rows[0]["aggressor_side"] == side
    assert rows[0]["signed_base_quantity"] == signed_quantity
    assert rows[0]["trade_time_ms"] == "1700000000000"


def test_replay_outputs_are_deterministic(tmp_path):
    records = [snapshot(), depth(2, 101, 101, [["99", "3"]], [["101", "1"]]), trade(3)]
    first = MODULE.replay_records(records, tmp_path / "first")
    second = MODULE.replay_records(records, tmp_path / "second")
    assert first["feature_sha256"] == second["feature_sha256"]
    assert first["trade_sha256"] == second["trade_sha256"]
    assert (tmp_path / "first" / "replay-manifest.json").read_bytes() == (
        tmp_path / "second" / "replay-manifest.json"
    ).read_bytes()


def test_raw_partitions_and_manifest_are_verified(tmp_path):
    capture_dir = tmp_path / "capture"
    writer = MODULE.RawPartitionWriter(capture_dir / "raw", "test-capture")
    writer.write(
        "audit", 1, receipt_time_ns=1_700_000_000_000_000_000,
        event="connected",
    )
    writer.close()
    manifest = {
        "schema_version": MODULE.SCHEMA_VERSION,
        "record_count": writer.sequence,
        "partitions": writer.partitions,
    }
    (capture_dir / "capture-manifest.json").write_text(
        MODULE.canonical_json(manifest) + "\n", encoding="utf-8"
    )
    assert len(list(MODULE.iter_capture_records(capture_dir))) == 1
    writer.partitions[0]["sha256"] = "0" * 64
    (capture_dir / "capture-manifest.json").write_text(
        MODULE.canonical_json({**manifest, "partitions": writer.partitions}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(MODULE.ValidationError, match="checksum mismatch"):
        list(MODULE.iter_capture_records(capture_dir))


def test_snapshot_without_bridge_is_not_accepted(tmp_path):
    manifest = MODULE.replay_records([snapshot()], tmp_path)
    assert manifest["status"] == "rejected"
    assert manifest["rejected_intervals"][0]["reason"] == "snapshot_without_bridge_event"


def test_aggregate_trade_gap_is_rejected(tmp_path):
    manifest = MODULE.replay_records([trade(1, aggregate_id=10), trade(2, aggregate_id=12)], tmp_path)
    assert manifest["trade_rows"] == 1
    assert manifest["rejected_intervals"][0]["reason"] == "aggregate trade ID gap or duplicate"
