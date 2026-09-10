from datetime import datetime, timedelta, timezone

import pytest

from trading_platform.artifacts import ArtifactStore
from trading_platform.contracts import ArtifactRef, ExecutionMarketSnapshot, SourceObservation


def _artifact() -> ArtifactRef:
    return ArtifactRef(
        digest="sha256:" + "a" * 64,
        media_type="application/json",
        byte_length=2,
        storage_path="sha256/aa/aa/" + "a" * 64,
    )


def test_artifact_store_is_content_addressed_and_detects_tampering(tmp_path):
    store = ArtifactStore(tmp_path)
    first = store.put(b'{"price":1}', "application/json")
    second = store.put(b'{"price":1}', "application/json")
    assert first == second
    assert store.read(first) == b'{"price":1}'
    (tmp_path / first.storage_path).chmod(0o640)
    (tmp_path / first.storage_path).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="integrity"):
        store.read(first)


def test_artifact_store_rejects_paths_outside_its_root(tmp_path):
    store = ArtifactStore(tmp_path)
    escaped = ArtifactRef(
        digest="sha256:" + "a" * 64,
        media_type="application/json",
        byte_length=2,
        storage_path="../outside",
    )
    with pytest.raises(ValueError, match="escapes"):
        store.read(escaped)


def test_execution_snapshot_rejects_open_candle():
    now = datetime.now(timezone.utc)
    with pytest.raises(ValueError, match="completed candle"):
        ExecutionMarketSnapshot(
            instrument_id="crypto:binance:spot:BTC-USDT",
            exchange="binance",
            pair="BTC/USDT",
            market_type="spot",
            timeframe="5m",
            candle_open_at=now,
            candle_close_at=now + timedelta(minutes=5),
            open="1", high="1", low="1", close="1", volume="1",
            retrieved_at=now,
            exchange_time_at=now + timedelta(minutes=1),
            clock_offset_ms=0,
            is_closed=False,
            has_gap=False,
            collector_version="test",
            raw_artifact=_artifact(),
        )


def test_replay_unsafe_observation_requires_reason():
    now = datetime.now(timezone.utc)
    with pytest.raises(ValueError, match="require a reason"):
        SourceObservation(
            category="news",
            vendor="test",
            symbol_or_query="BTC",
            first_seen_at=now,
            retrieved_at=now,
            artifact=_artifact(),
            status="available",
            replay_safe=False,
        )
