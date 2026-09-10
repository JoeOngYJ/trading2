from trading_platform.atomic_snapshot import atomic_write_snapshot, read_snapshot, snapshot_name
from conftest import TEST_SECRET


def test_snapshot_is_atomic_and_verifiable(tmp_path, signal_factory):
    envelope = signal_factory()
    target = atomic_write_snapshot(tmp_path, envelope)
    assert target.name == "BTC_USDT__5m.json"
    assert not list(tmp_path.glob(".*"))
    restored = read_snapshot(tmp_path, "BTC/USDT", "5m")
    assert restored.verify(TEST_SECRET)
    assert restored.payload.event_id == envelope.payload.event_id


def test_snapshot_name_cannot_escape_directory():
    assert snapshot_name("../../BTC/USDT", "../5m") == ".._.._BTC_USDT__.._5m.json"


def test_revocation_atomically_replaces_signal_with_tombstone(
    tmp_path, signal_factory, revocation_factory
):
    signal = signal_factory()
    atomic_write_snapshot(tmp_path, signal)
    revocation = revocation_factory(target=signal)
    atomic_write_snapshot(tmp_path, revocation)
    restored = read_snapshot(tmp_path, "BTC/USDT", "5m")
    assert restored.payload.event_type == "signal.revoked"
    assert restored.payload.signal_id == signal.payload.signal_id
