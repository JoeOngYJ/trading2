from __future__ import annotations

import gzip
import hashlib
from pathlib import Path

import pytest

from trading_platform.research_evidence import load_research_partition_registry
from trading_platform.research_ledger import (
    FIVE_MINUTES_MS,
    FOUR_HOURS_MS,
    ResearchLedgerError,
    SourceCandle,
    aggregate_candles,
    feature_observations,
    iter_jsonl_gzip,
    load_source_candles,
    write_jsonl_gzip,
)


ROOT = Path(__file__).resolve().parents[1]


def candle(index: int, *, segment: int = 1, price: float = 100.0) -> SourceCandle:
    return SourceCandle(
        segment=segment,
        open_ms=index * FIVE_MINUTES_MS,
        open=price,
        high=price + 1,
        low=price - 1,
        close=price + 0.5,
        base_volume=2.0,
        quote_volume=200.0,
        source_row=index,
    )


def test_complete_aggregation_is_utc_aligned_contiguous_and_segment_bound():
    rows = [candle(index, price=100 + index) for index in range(48)]
    bars, discarded = aggregate_candles(rows, FOUR_HOURS_MS, "4h")
    assert len(bars) == 1
    assert discarded == 0
    assert bars[0].open == rows[0].open
    assert bars[0].close == rows[-1].close
    assert bars[0].high == max(row.high for row in rows)
    assert bars[0].start_row == 0 and bars[0].end_row == 47

    crossing = rows[:24] + [candle(index, segment=2) for index in range(24, 48)]
    bars, discarded = aggregate_candles(crossing, FOUR_HOURS_MS, "4h")
    assert bars == []
    assert discarded == 48


def test_features_are_available_at_close_and_reset_close_return_at_segment():
    rows = [candle(index, price=100 + index) for index in range(96)]
    bars, _ = aggregate_candles(rows, FOUR_HOURS_MS, "4h")
    features = feature_observations(bars, "a" * 64)
    assert features[0].observed_at == features[0].available_at
    assert "close_to_close_log_return" not in features[0].feature_values
    assert "close_to_close_log_return" in features[1].feature_values

    second_segment = [candle(96 + index, segment=2, price=200 + index) for index in range(48)]
    later, _ = aggregate_candles(second_segment, FOUR_HOURS_MS, "4h")
    reset = feature_observations([*bars, *later], "a" * 64)
    assert "close_to_close_log_return" not in reset[-1].feature_values
    assert len(reset[-1].feature_digest) == 64


def test_deterministic_gzip_jsonl_has_stable_checksum(tmp_path: Path):
    payload = [{"z": 2, "a": 1}, {"a": 3, "z": 4}]
    first = write_jsonl_gzip(tmp_path / "first.jsonl.gz", payload)
    second = write_jsonl_gzip(tmp_path / "second.jsonl.gz", payload)
    assert first["sha256"] == second["sha256"]
    assert list(iter_jsonl_gzip(tmp_path / "first.jsonl.gz")) == payload


def write_source(path: Path, rows: list[tuple[int, int]]) -> str:
    header = "segment_id,open_time_ms,open,high,low,close,base_volume,quote_volume\n"
    body = "".join(f"{segment},{timestamp},100,101,99,100,1,100\n" for segment, timestamp in rows)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        handle.write(header + body)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_source_loader_rejects_gaps_and_holdout_names(tmp_path: Path):
    source = tmp_path / "development.csv.gz"
    digest = write_source(source, [(1, 0), (1, 2 * FIVE_MINUTES_MS)])
    with pytest.raises(ResearchLedgerError, match="gap inside source segment"):
        load_source_candles(source, digest)

    holdout = tmp_path / "holdout-2026-01-07.csv.gz"
    holdout_digest = write_source(holdout, [(1, 0)])
    with pytest.raises(ResearchLedgerError, match="holdout"):
        load_source_candles(holdout, holdout_digest)


def test_btc_boundary_has_no_clean_unseen_partition_and_preserves_unread_reason():
    registry = load_research_partition_registry(
        ROOT / "config/research/btc-directional-trend-evidence-boundaries-v1.json"
    )
    assert registry.clean_unseen_partition_ids() == ()
    sealed = registry.partition("btc-2026-jan-jul-sealed-ineligible")
    assert sealed.access_state == "sealed_ineligible"
    assert not registry.audit_unseen(sealed.partition_id).genuinely_unseen
    assert registry.audit_unseen(sealed.partition_id).overlapping_inspection_ids == ()
