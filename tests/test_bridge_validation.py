from datetime import datetime, timedelta, timezone
from contextlib import nullcontext
from types import SimpleNamespace

import nats.errors
import pytest

from trading_platform.atomic_snapshot import read_snapshot
from trading_platform.bridge import _restore_subscription, materialize
from trading_platform.contracts import SignedEnvelope
from trading_platform.signal_validation import validate_for_materialization
from conftest import TEST_SECRET


class Result:
    def __init__(self, row=None):
        self.row = row

    def fetchone(self):
        return self.row


class BridgeConnection:
    def __init__(self, cursor=None):
        self.cursor = cursor or {
            "sequence": 0, "event_id": None, "signal_id": None,
            "checksum": None, "disposition": None,
        }
        self.calls = []

    def execute(self, query, parameters=None):
        compact = " ".join(query.split())
        self.calls.append((compact, parameters))
        if "SELECT sequence,event_id,signal_id,checksum,disposition" in compact:
            return Result(self.cursor)
        if "SELECT disposition FROM delivery_receipts" in compact:
            return Result()
        return Result()

    def transaction(self):
        return nullcontext()


def settings(tmp_path):
    return SimpleNamespace(
        database_url="postgresql://test",
        hmac_secret=TEST_SECRET,
        environment="production",
        bot_id="freqtrade-primary",
        exchange="binance",
        timeframe="5m",
        clock_skew_seconds=30,
        snapshot_dir=tmp_path,
    )


@pytest.mark.asyncio
async def test_bridge_retries_binding_until_jetstream_is_ready(monkeypatch, tmp_path):
    state = {"stream_attempts": 0, "bind_attempts": 0, "sleeps": []}

    class Connection:
        is_connected = True
        is_closed = False

    async def delayed_streams(_):
        state["stream_attempts"] += 1
        if state["stream_attempts"] < 3:
            raise nats.errors.TimeoutError

    async def bind():
        state["bind_attempts"] += 1
        return "subscription"

    async def sleep(delay):
        state["sleeps"].append(delay)

    monkeypatch.setattr("trading_platform.bridge.ensure_streams", delayed_streams)
    monkeypatch.setattr("trading_platform.bridge.asyncio.sleep", sleep)
    restored = await _restore_subscription(
        Connection(), object(), bind, settings(tmp_path), "jetstream_rebinding",
    )

    assert restored == "subscription"
    assert state == {
        "stream_attempts": 3, "bind_attempts": 1, "sleeps": [0.1, 0.2],
    }


def test_valid_signal_passes(tmp_path, signal_factory):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    assert validate_for_materialization(signal_factory(now=now), settings(tmp_path), now) is None


def test_expired_signal_is_rejected(tmp_path, signal_factory):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    envelope = signal_factory(now=now - timedelta(hours=2))
    assert validate_for_materialization(envelope, settings(tmp_path), now) == "expired"


def test_tampering_is_rejected(tmp_path, signal_factory):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    envelope = signal_factory(now=now)
    envelope.payload.pair = "ETH/USDT"
    assert validate_for_materialization(envelope, settings(tmp_path), now) == "signature_or_checksum_invalid"


def test_future_publication_is_rejected(tmp_path, signal_factory):
    base = datetime.now(timezone.utc).replace(microsecond=0)
    future = base + timedelta(minutes=10)
    envelope = signal_factory(now=future)
    assert validate_for_materialization(envelope, settings(tmp_path), base) == "published_in_future"


def test_signed_revocation_is_valid_without_signal_expiry(tmp_path, revocation_factory):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    envelope = revocation_factory(now=now)
    assert validate_for_materialization(envelope, settings(tmp_path), now) is None


def test_bridge_materializes_revocation_as_fail_closed_tombstone(
    monkeypatch, tmp_path, revocation_factory
):
    connection = BridgeConnection()
    monkeypatch.setattr(
        "trading_platform.bridge.connect", lambda *_: nullcontext(connection)
    )
    envelope = revocation_factory()
    disposition, reason = materialize(envelope, settings(tmp_path))
    assert (disposition, reason) == ("revoked", None)
    assert any("FROM materialization_cursors" in query for query, _ in connection.calls)
    tombstone = read_snapshot(tmp_path, "BTC/USDT", "5m")
    assert tombstone.payload.event_type == "signal.revoked"


def test_older_signal_cannot_replace_newer_revocation_tombstone(
    monkeypatch, tmp_path, signal_factory, revocation_factory
):
    signal = signal_factory()
    tombstone = revocation_factory(target=signal)
    from trading_platform.atomic_snapshot import atomic_write_snapshot
    atomic_write_snapshot(tmp_path, tombstone)
    monkeypatch.setattr(
        "trading_platform.bridge.connect", lambda *_: nullcontext(BridgeConnection({
            "sequence": 2, "event_id": tombstone.payload.event_id,
            "signal_id": tombstone.payload.signal_id, "checksum": tombstone.checksum,
            "disposition": "revoked",
        }))
    )
    disposition, reason = materialize(signal, settings(tmp_path))
    assert (disposition, reason) == ("stale", "sequence_not_newer")
    assert read_snapshot(tmp_path, "BTC/USDT", "5m").payload.event_type == "signal.revoked"


def test_newer_signal_recovers_from_revocation_tombstone(
    monkeypatch, tmp_path, signal_factory, revocation_factory
):
    old_signal = signal_factory()
    tombstone = revocation_factory(target=old_signal)
    from trading_platform.atomic_snapshot import atomic_write_snapshot
    atomic_write_snapshot(tmp_path, tombstone)
    new_signal = signal_factory()
    new_signal = SignedEnvelope.sign(
        new_signal.payload.model_copy(update={"sequence": 3}), TEST_SECRET
    )
    monkeypatch.setattr(
        "trading_platform.bridge.connect", lambda *_: nullcontext(BridgeConnection({
            "sequence": 2, "event_id": tombstone.payload.event_id,
            "signal_id": tombstone.payload.signal_id, "checksum": tombstone.checksum,
            "disposition": "revoked",
        }))
    )
    monkeypatch.setattr("trading_platform.bridge.kill_switch_enabled", lambda *_: False)
    disposition, reason = materialize(new_signal, settings(tmp_path))
    assert (disposition, reason) == ("materialized", None)
    assert read_snapshot(tmp_path, "BTC/USDT", "5m").payload.event_type == "signal.created"


def test_bridge_repairs_cursor_after_crash_following_snapshot_rename(
    monkeypatch, tmp_path, signal_factory
):
    from trading_platform.atomic_snapshot import atomic_write_snapshot

    envelope = signal_factory(sequence=2)
    atomic_write_snapshot(tmp_path, envelope)
    connection = BridgeConnection({
        "sequence": 1, "event_id": signal_factory().payload.event_id,
        "signal_id": signal_factory().payload.signal_id, "checksum": "a" * 64,
        "disposition": "materialized",
    })
    monkeypatch.setattr("trading_platform.bridge.connect", lambda *_: nullcontext(connection))
    monkeypatch.setattr(
        "trading_platform.bridge.atomic_write_snapshot",
        lambda *_: (_ for _ in ()).throw(AssertionError("same file must not be rewritten")),
    )
    monkeypatch.setattr("trading_platform.bridge.kill_switch_enabled", lambda *_: False)

    assert materialize(envelope, settings(tmp_path)) == ("materialized", None)
    assert any("UPDATE materialization_cursors" in query for query, _ in connection.calls)
    assert any("INSERT INTO delivery_receipts" in query for query, _ in connection.calls)


def test_bridge_rejects_different_event_at_same_sequence(
    monkeypatch, tmp_path, signal_factory
):
    from trading_platform.atomic_snapshot import atomic_write_snapshot

    existing = signal_factory(sequence=2)
    conflicting = signal_factory(sequence=2)
    atomic_write_snapshot(tmp_path, existing)
    connection = BridgeConnection({
        "sequence": 2, "event_id": existing.payload.event_id,
        "signal_id": existing.payload.signal_id, "checksum": existing.checksum,
        "disposition": "materialized",
    })
    monkeypatch.setattr("trading_platform.bridge.connect", lambda *_: nullcontext(connection))

    assert materialize(conflicting, settings(tmp_path)) == (
        "rejected", "sequence_identity_conflict",
    )
    assert read_snapshot(tmp_path, "BTC/USDT", "5m").payload.event_id == existing.payload.event_id
