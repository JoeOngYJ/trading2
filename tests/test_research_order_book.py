from __future__ import annotations

import json
from pathlib import Path

import pytest

np = pytest.importorskip("numpy", reason="OB1 research tests require requirements-research.txt")
pd = pytest.importorskip("pandas", reason="OB1 research tests require requirements-research.txt")

from trading_platform.research_order_book import (
    build_ob1_dataset,
    development_folds,
    validate_ob1_collection_contract,
)


SPEC = json.loads(
    (Path(__file__).parents[1] / "config/experiments/btc-order-book-ob1-v1.json").read_text()
)


def synthetic_replay(seconds: int = 30, step_ms: int = 100):
    base = pd.Timestamp("2025-01-01T00:00:00Z").value
    count = seconds * (1000 // step_ms) + 1
    receipt = base + np.arange(count, dtype=np.int64) * step_ms * 1_000_000
    mid = 100 + np.arange(count) * 0.001
    book = pd.DataFrame(
        {
            "capture_sequence": np.arange(1, count + 1),
            "connection_id": 1,
            "segment_id": 1,
            "receipt_time_ns": receipt,
            "best_bid": mid - 0.005,
            "best_ask": mid + 0.005,
            "bid_qty_l1": 2.0,
            "ask_qty_l1": 1.0,
            "spread": 0.01,
            "mid_price": mid,
            "microprice_minus_mid_spreads": 1 / 6,
            "queue_imbalance_l1": 1 / 3,
            "queue_imbalance_l5": 0.2,
            "queue_imbalance_l10": 0.1,
            "ofi_l1": 0.25,
            "bid_add_qty": 0.1,
            "bid_remove_qty": 0.0,
            "ask_add_qty": 0.0,
            "ask_remove_qty": 0.05,
        }
    )
    trade_receipt = receipt[::5]
    trades = pd.DataFrame(
        {
            "capture_sequence": np.arange(100_000, 100_000 + len(trade_receipt)),
            "connection_id": 1,
            "receipt_time_ns": trade_receipt,
            "quote_quantity": 10.0,
            "signed_quote_quantity": np.where(np.arange(len(trade_receipt)) % 2, -10.0, 10.0),
        }
    )
    return book, trades


def test_one_second_sampling_uses_receipt_time_and_delayed_mid_labels():
    book, trades = synthetic_replay()
    result = build_ob1_dataset(
        book,
        trades,
        SPEC,
        pd.Timestamp("2025-01-01T00:00:00Z"),
        pd.Timestamp("2025-01-01T00:00:20Z"),
    )
    assert result.quality["decision_rows"] == 20
    assert len(result.frame) > 0
    row = result.frame.iloc[0]
    decision_ns = int(row["decision_time_ns"])
    entry_target = decision_ns + 250_000_000
    exit_target = entry_target + 5_000_000_000
    entry_mid = book.loc[book["receipt_time_ns"].le(entry_target), "mid_price"].iloc[-1]
    exit_mid = book.loc[book["receipt_time_ns"].le(exit_target), "mid_price"].iloc[-1]
    assert row["target_log_return_l250ms_h5s"] == pytest.approx(np.log(exit_mid / entry_mid))
    assert row["depth_event_count_1s"] == 10


def test_future_event_change_does_not_change_current_features():
    book, trades = synthetic_replay()
    start = pd.Timestamp("2025-01-01T00:00:00Z")
    end = pd.Timestamp("2025-01-01T00:00:20Z")
    original = build_ob1_dataset(book, trades, SPEC, start, end).frame
    decision = original.iloc[0]["decision_time"]
    changed = book.copy()
    future = changed["receipt_time_ns"].gt(pd.Timestamp(decision).value)
    for column in ("best_bid", "best_ask", "mid_price"):
        changed.loc[future, column] += 10
    altered = build_ob1_dataset(changed, trades, SPEC, start, end).frame
    feature_columns = [
        *SPEC["features"]["primary_l2"],
        *SPEC["features"]["signed_trade_control"],
        *SPEC["features"]["state_controls"],
    ]
    pd.testing.assert_series_equal(
        original.iloc[0][feature_columns], altered.iloc[0][feature_columns]
    )


def test_stale_book_and_segment_crossing_fail_closed():
    book, trades = synthetic_replay()
    cut = pd.Timestamp("2025-01-01T00:00:12Z").value
    book = book[(book["receipt_time_ns"] < cut) | (book["receipt_time_ns"] >= cut + 2_000_000_000)].copy()
    book.loc[book["receipt_time_ns"] >= cut + 2_000_000_000, "segment_id"] = 2
    result = build_ob1_dataset(
        book,
        trades,
        SPEC,
        pd.Timestamp("2025-01-01T00:00:00Z"),
        pd.Timestamp("2025-01-01T00:00:20Z"),
    )
    decisions = set(result.frame["decision_time"])
    assert pd.Timestamp("2025-01-01T00:00:13Z") not in decisions
    assert result.quality["rejected_stale_or_missing_current"] > 0
    assert result.quality["rejected_primary_label"] > 0


def test_one_second_trade_aggregates_do_not_cross_connection():
    book, trades = synthetic_replay()
    boundary = pd.Timestamp("2025-01-01T00:00:15Z").value
    foreign = trades["receipt_time_ns"].between(
        boundary - 1_000_000_000, boundary - 500_000_000, inclusive="right"
    )
    trades.loc[foreign, "signed_quote_quantity"] = 999
    trades.loc[foreign, "connection_id"] = 2
    result = build_ob1_dataset(
        book,
        trades,
        SPEC,
        pd.Timestamp("2025-01-01T00:00:00Z"),
        pd.Timestamp("2025-01-01T00:00:25Z"),
    )
    row = result.frame.loc[
        result.frame["decision_time"].eq(pd.Timestamp("2025-01-01T00:00:15Z"))
    ].iloc[0]
    assert row["depth_event_count_1s"] == 10
    assert abs(row["signed_trade_quote_qty_1s"]) < 999


def test_development_folds_require_sixty_accepted_days_and_are_chronological():
    days = pd.date_range("2025-01-01", periods=60, freq="1D", tz="UTC")
    folds = development_folds(days, SPEC)
    assert len(folds) == 4
    assert len(folds[0]["training_days"]) == 30
    assert len(folds[0]["validation_days"]) == 7
    assert folds[0]["training_days"][-1] < folds[0]["validation_days"][0]
    assert len(folds[-1]["training_days"]) == 51
    with pytest.raises(ValueError, match="requires 60"):
        development_folds(days[:59], SPEC)


def test_collection_contract_requires_locked_development_and_later_contiguous_sealed_test():
    development = pd.date_range("2025-01-01", periods=60, freq="1D", tz="UTC")
    sealed = pd.date_range("2025-03-02", periods=30, freq="1D", tz="UTC")

    def row(day):
        return {
            "date": day.isoformat(),
            "acceptance_status": "accepted",
            "replay_manifest_sha256": "a" * 64,
        }

    contract = {
        "experiment_id": SPEC["experiment_id"],
        "status": "locked",
        "development_days": [row(day) for day in development],
        "sealed_test_days": [row(day) for day in sealed],
        "sealed_test_access": "metadata_only_unread",
    }
    result = validate_ob1_collection_contract(contract, SPEC)
    assert result["status"] == "development_ready_test_sealed"
    assert result["development_days"] == 60
    broken = {**contract, "sealed_test_days": contract["sealed_test_days"][:-1]}
    with pytest.raises(ValueError, match="exactly 30"):
        validate_ob1_collection_contract(broken, SPEC)
