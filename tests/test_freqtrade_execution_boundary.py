import importlib.util
import json
import sys
import types
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

from trading_platform.atomic_snapshot import atomic_write_snapshot, snapshot_name, write_health
from trading_platform.contracts import PortfolioRating, SignedEnvelope
from conftest import TEST_SECRET


STRATEGY_PATH = Path("user_data/strategies/ReliableSignalStrategy.py")


def load_strategy(monkeypatch, snapshot_dir: Path):
    """Load the shipped strategy without requiring the full Freqtrade image in unit tests."""
    pandas = types.ModuleType("pandas")
    pandas.DataFrame = dict
    freqtrade = types.ModuleType("freqtrade")
    freqtrade_strategy = types.ModuleType("freqtrade.strategy")
    freqtrade_strategy.IStrategy = object
    monkeypatch.setitem(sys.modules, "pandas", pandas)
    monkeypatch.setitem(sys.modules, "freqtrade", freqtrade)
    monkeypatch.setitem(sys.modules, "freqtrade.strategy", freqtrade_strategy)
    monkeypatch.setenv("PLATFORM_SNAPSHOT_DIR", str(snapshot_dir))
    monkeypatch.setenv("PLATFORM_ENVIRONMENT", "production")
    monkeypatch.setenv("PLATFORM_BOT_ID", "freqtrade-primary")
    monkeypatch.setenv("PLATFORM_EXCHANGE", "binance")
    monkeypatch.setenv("PLATFORM_TIMEFRAME", "5m")
    monkeypatch.setenv("PLATFORM_HMAC_SECRET", TEST_SECRET)
    name = f"reliable_signal_strategy_{id(snapshot_dir)}"
    spec = importlib.util.spec_from_file_location(name, STRATEGY_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    strategy = module.ReliableSignalStrategy()
    strategy.dp = type("DataProvider", (), {"current_whitelist": lambda self: ["BTC/USDT"]})()
    return strategy


def healthy_bridge(snapshot_dir: Path, now: datetime) -> None:
    write_health(snapshot_dir, {"status": "healthy", "observed_at": now.isoformat()})


def test_strategy_reads_only_complete_signed_envelopes_during_replacement(
    tmp_path, monkeypatch, signal_factory, revocation_factory,
):
    """F1: rapid rename replacement never exposes partial JSON to Freqtrade."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    created = signal_factory(now=now, rating=PortfolioRating.BUY)
    revoked = revocation_factory(target=created, now=now)
    atomic_write_snapshot(tmp_path, created)
    healthy_bridge(tmp_path, now)
    target = tmp_path / snapshot_name("BTC/USDT", "5m")
    allowed_ids = {created.payload.event_id, revoked.payload.event_id}

    def writer():
        for index in range(300):
            atomic_write_snapshot(tmp_path, created if index % 2 == 0 else revoked)

    def reader(strategy):
        for _ in range(300):
            envelope = SignedEnvelope.model_validate_json(target.read_text(encoding="utf-8"))
            assert envelope.verify(TEST_SECRET)
            assert envelope.payload.event_id in allowed_ids
            strategy.bot_loop_start(now)
            loaded = strategy._signals.get("BTC/USDT")
            if loaded is not None:
                assert loaded["payload"]["event_id"] == str(created.payload.event_id)
                assert strategy._verify(loaded, now)

    strategies = [load_strategy(monkeypatch, tmp_path) for _ in range(3)]
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(writer)] + [
            executor.submit(reader, strategy) for strategy in strategies
        ]
        for future in futures:
            future.result(timeout=20)


def test_strategy_fails_closed_for_non_actionable_snapshots_without_gating_exits(
    tmp_path, monkeypatch, signal_factory, revocation_factory,
):
    """F2: only a current, correctly routed BUY can pass the final long-entry gate."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    strategy = load_strategy(monkeypatch, tmp_path)
    healthy_bridge(tmp_path, now)

    buy = signal_factory(now=now, rating=PortfolioRating.BUY)
    atomic_write_snapshot(tmp_path, buy)
    strategy.bot_loop_start(now)
    entry_arguments = {
        "pair": "BTC/USDT", "order_type": "limit", "amount": 1.0, "rate": 1.0,
        "time_in_force": "gtc", "current_time": now,
        "entry_tag": f"llm:{buy.payload.signal_id}", "side": "long",
    }
    assert strategy.confirm_trade_entry(**entry_arguments)

    hold = signal_factory(now=now, rating=PortfolioRating.HOLD)
    atomic_write_snapshot(tmp_path, hold)
    strategy.bot_loop_start(now)
    assert not strategy.confirm_trade_entry(
        **{**entry_arguments, "entry_tag": f"llm:{hold.payload.signal_id}"}
    )

    revocation = revocation_factory(target=buy, now=now)
    atomic_write_snapshot(tmp_path, revocation)
    strategy.bot_loop_start(now)
    assert not strategy.confirm_trade_entry(**entry_arguments)

    expired_payload = buy.payload.model_copy(update={"expires_at": now - timedelta(seconds=1)})
    atomic_write_snapshot(tmp_path, SignedEnvelope.sign(expired_payload, TEST_SECRET))
    strategy.bot_loop_start(now)
    assert not strategy.confirm_trade_entry(**entry_arguments)

    wrong_route = buy.payload.model_copy(update={"bot_id": "another-bot"})
    atomic_write_snapshot(tmp_path, SignedEnvelope.sign(wrong_route, TEST_SECRET))
    strategy.bot_loop_start(now)
    assert not strategy.confirm_trade_entry(**entry_arguments)

    target = tmp_path / snapshot_name("BTC/USDT", "5m")
    target.write_text(json.dumps({"incomplete": True}), encoding="utf-8")
    strategy.bot_loop_start(now)
    assert not strategy.confirm_trade_entry(**entry_arguments)

    # Snapshot state gates entries only. Freqtrade's ROI/stop-loss protection remains configured,
    # and strategy exit columns are produced identically with no actionable snapshot.
    dataframe = {}
    assert strategy.populate_exit_trend(dataframe, {"pair": "BTC/USDT"}) == {
        "exit_long": 0, "exit_short": 0,
    }
    assert strategy.stoploss == -0.10
    assert strategy.minimal_roi == {"0": 100.0}
    assert strategy.use_exit_signal is True
