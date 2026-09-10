from __future__ import annotations

import logging
import time

from .db import connect, migrate
from .settings import Settings


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("scheduler")


def schedule_once(settings: Settings) -> int:
    with connect(settings.database_url) as connection:
        rows = connection.execute(
            """
            INSERT INTO analysis_jobs(
                symbol,pair,timeframe,candle_close_at,instrument_id,execution_snapshot_id
            )
            SELECT i.research_symbol,s.pair,s.timeframe,s.candle_close_at,
                   s.instrument_id,s.snapshot_id
            FROM execution_market_snapshots s
            JOIN instruments i ON i.instrument_id=s.instrument_id
            WHERE i.enabled AND s.is_closed AND NOT s.has_gap AND s.timeframe=%s
              AND NOT EXISTS (
                  SELECT 1 FROM analysis_jobs j WHERE j.execution_snapshot_id=s.snapshot_id
              )
            ORDER BY s.candle_close_at,s.instrument_id
            LIMIT 100
            ON CONFLICT (symbol,timeframe,candle_close_at) DO NOTHING
            RETURNING job_id
            """,
            (settings.timeframe,),
        ).fetchall()
        connection.commit()
    inserted = len(rows)
    logger.info("scheduled snapshot-backed analysis jobs", extra={"inserted": inserted})
    return inserted


def main() -> None:
    settings = Settings()
    migrate(settings.database_url)
    while True:
        try:
            schedule_once(settings)
        except Exception:
            logger.exception("scheduling failed")
        time.sleep(settings.analysis_schedule_seconds)


if __name__ == "__main__":
    main()
