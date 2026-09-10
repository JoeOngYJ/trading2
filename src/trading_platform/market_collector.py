from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import ccxt
from psycopg.types.json import Jsonb

from .artifacts import ArtifactStore
from .contracts import ExecutionMarketSnapshot, SourceObservation
from .db import connect, migrate
from .evidence import persist_artifact, persist_observation
from .repository import heartbeat
from .settings import Settings


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("market-collector")


def _utc_from_ms(value: int) -> datetime:
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc)


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()


def _synthetic_candles(timeframe_seconds: int) -> tuple[list[list[object]], int, int, list[str]]:
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    width_ms = timeframe_seconds * 1000
    current_open = now_ms - (now_ms % width_ms)
    candles = [
        [current_open - 2 * width_ms, "1", "1", "1", "1", "0"],
        [current_open - width_ms, "1", "1", "1", "1", "0"],
        [current_open, "1", "1", "1", "1", "0"],
    ]
    return candles, now_ms, 0, ["synthetic_market_data"]


def _exchange_candles(exchange_name: str, pair: str, timeframe: str) -> tuple[list[list[object]], int, int, list[str]]:
    if exchange_name != "binance":
        raise ValueError(f"unsupported execution exchange: {exchange_name}")
    exchange = ccxt.binance({"enableRateLimit": True})
    exchange.load_markets()
    local_before = exchange.milliseconds()
    exchange_ms = exchange.fetch_time()
    local_after = exchange.milliseconds()
    midpoint = (local_before + local_after) // 2
    candles = exchange.fetch_ohlcv(pair, timeframe=timeframe, limit=3)
    return candles, exchange_ms, exchange_ms - midpoint, []


def collect_instrument(settings: Settings, instrument: dict) -> ExecutionMarketSnapshot | None:
    timeframe_seconds = int(ccxt.Exchange.parse_timeframe(settings.timeframe))
    if settings.market_data_mode == "synthetic":
        candles, exchange_ms, offset_ms, quality_flags = _synthetic_candles(timeframe_seconds)
        collector_version = "synthetic"
    elif settings.market_data_mode == "exchange":
        candles, exchange_ms, offset_ms, quality_flags = _exchange_candles(
            instrument["execution_exchange"], instrument["execution_pair"], settings.timeframe
        )
        collector_version = f"ccxt-{ccxt.__version__}"
    else:
        raise ValueError(f"unsupported market data mode: {settings.market_data_mode}")
    if abs(offset_ms) > settings.max_clock_offset_ms:
        raise RuntimeError(f"exchange clock offset {offset_ms}ms exceeds limit")
    width_ms = timeframe_seconds * 1000
    closed = [candle for candle in candles if int(candle[0]) + width_ms <= exchange_ms]
    if not closed:
        raise RuntimeError("exchange returned no completed candle")
    latest = closed[-1]
    has_gap = len(closed) > 1 and int(closed[-2][0]) + width_ms != int(latest[0])
    retrieved_at = datetime.now(timezone.utc)
    raw = {
        "exchange": instrument["execution_exchange"],
        "pair": instrument["execution_pair"],
        "timeframe": settings.timeframe,
        "exchange_time_ms": exchange_ms,
        "clock_offset_ms": offset_ms,
        "candles": candles,
    }
    store = ArtifactStore(settings.artifact_dir)
    artifact = store.put(_canonical_json(raw), "application/json")
    snapshot_id = uuid4()
    snapshot = ExecutionMarketSnapshot(
        snapshot_id=snapshot_id,
        instrument_id=instrument["instrument_id"],
        exchange=instrument["execution_exchange"],
        pair=instrument["execution_pair"],
        market_type=instrument["market_type"],
        timeframe=settings.timeframe,
        candle_open_at=_utc_from_ms(int(latest[0])),
        candle_close_at=_utc_from_ms(int(latest[0]) + width_ms),
        open=str(Decimal(str(latest[1]))),
        high=str(Decimal(str(latest[2]))),
        low=str(Decimal(str(latest[3]))),
        close=str(Decimal(str(latest[4]))),
        volume=str(Decimal(str(latest[5]))),
        retrieved_at=retrieved_at,
        exchange_time_at=_utc_from_ms(exchange_ms),
        clock_offset_ms=offset_ms,
        is_closed=True,
        has_gap=has_gap,
        collector_version=collector_version,
        raw_artifact=artifact,
    )
    observation = SourceObservation(
        category="execution_market",
        vendor=instrument["execution_exchange"] if settings.market_data_mode == "exchange" else "synthetic",
        symbol_or_query=instrument["execution_pair"],
        external_id=str(snapshot_id),
        event_at=snapshot.candle_close_at,
        first_seen_at=retrieved_at,
        retrieved_at=retrieved_at,
        artifact=artifact,
        request_parameters={"timeframe": settings.timeframe, "limit": 3},
        status="available",
        quality_flags=quality_flags + (["candle_gap"] if has_gap else []),
        replay_safe=True,
    )
    with connect(settings.database_url) as connection:
        with connection.transaction():
            existing = connection.execute(
                """
                SELECT snapshot_id FROM execution_market_snapshots
                WHERE instrument_id=%s AND timeframe=%s AND candle_open_at=%s
                """,
                (snapshot.instrument_id, snapshot.timeframe, snapshot.candle_open_at),
            ).fetchone()
            if existing:
                return None
            persist_artifact(connection, artifact)
            connection.execute(
                """
                INSERT INTO execution_market_snapshots(
                    snapshot_id,instrument_id,exchange,pair,market_type,timeframe,candle_type,
                    candle_open_at,candle_close_at,open_price,high_price,low_price,close_price,
                    volume,retrieved_at,exchange_time_at,clock_offset_ms,is_closed,has_gap,
                    collector_version,raw_artifact_digest
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    snapshot.snapshot_id, snapshot.instrument_id, snapshot.exchange, snapshot.pair,
                    snapshot.market_type, snapshot.timeframe, snapshot.candle_type,
                    snapshot.candle_open_at, snapshot.candle_close_at, snapshot.open, snapshot.high,
                    snapshot.low, snapshot.close, snapshot.volume, snapshot.retrieved_at,
                    snapshot.exchange_time_at, snapshot.clock_offset_ms, snapshot.is_closed,
                    snapshot.has_gap, snapshot.collector_version, artifact.digest,
                ),
            )
            persist_observation(connection, observation)
    return snapshot


def collect_once(settings: Settings) -> int:
    with connect(settings.database_url) as connection:
        instruments = connection.execute(
            """
            SELECT * FROM instruments
            WHERE enabled AND execution_exchange=%s AND market_type='spot'
            ORDER BY instrument_id
            """,
            (settings.exchange,),
        ).fetchall()
    count = 0
    for instrument in instruments:
        try:
            count += int(collect_instrument(settings, instrument) is not None)
        except Exception:
            logger.exception("market collection failed", extra={"instrument_id": instrument["instrument_id"]})
    with connect(settings.database_url) as connection:
        heartbeat(connection, "market-collector", "healthy", {"snapshots_created": count})
    return count


def main() -> None:
    settings = Settings()
    migrate(settings.database_url)
    settings.artifact_dir.mkdir(parents=True, exist_ok=True)
    while True:
        collect_once(settings)
        time.sleep(settings.market_collection_seconds)


if __name__ == "__main__":
    main()
