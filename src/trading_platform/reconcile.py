from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

import httpx

from .contracts import ExecutionEvent
from .db import connect, migrate
from .repository import heartbeat, record_execution_event
from .settings import Settings


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("reconciler")


def reconcile_once(settings: Settings) -> int:
    auth = (settings.freqtrade_username, settings.freqtrade_password)
    with httpx.Client(base_url=settings.freqtrade_url, auth=auth, timeout=5) as client:
        response = client.get("/api/v1/trades", params={"limit": 500, "offset": 0})
        response.raise_for_status()
        body = response.json()
    trades = body.get("trades", body if isinstance(body, list) else [])
    count = 0
    with connect(settings.database_url) as connection:
        for trade in trades:
            trade_id = str(trade.get("trade_id", trade.get("id")))
            is_open = bool(trade.get("is_open", False))
            event_type = "open" if is_open else "closed"
            occurred_raw = trade.get("open_date") if is_open else trade.get("close_date")
            occurred = datetime.fromisoformat(occurred_raw.replace("Z", "+00:00")) if occurred_raw else datetime.now(timezone.utc)
            event_key = f"{settings.bot_id}:{trade_id}:{event_type}:{occurred.isoformat()}"
            event = ExecutionEvent(
                event_id=uuid5(NAMESPACE_URL, event_key),
                event_type=event_type,
                occurred_at=occurred,
                bot_id=settings.bot_id,
                exchange=settings.exchange,
                pair=trade.get("pair"),
                trade_id=trade_id,
                payload=trade,
            )
            record_execution_event(connection, event, "reconciliation")
            count += 1
        heartbeat(connection, f"reconciler:{settings.bot_id}", "healthy", {"trades_seen": count})
    return count


def main() -> None:
    settings = Settings()
    migrate(settings.database_url)
    while True:
        try:
            reconcile_once(settings)
        except Exception:
            logger.exception("Freqtrade reconciliation failed")
        time.sleep(60)


if __name__ == "__main__":
    main()

