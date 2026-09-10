from __future__ import annotations

import asyncio
import json
import logging
import random
import socket
from uuid import uuid4

import nats
from nats.aio.msg import Msg
from nats.js.errors import APIError

from .db import connect, migrate
from .fault_injection import checkpoint
from .nats_support import ensure_streams
from .repository import heartbeat
from .settings import Settings


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("outbox")


def claim_pending(connection, settings: Settings, relay_id: str) -> list[dict]:
    """Lease a disjoint batch without retaining database locks during NATS I/O."""
    claim_token = uuid4()
    rows = connection.execute(
        """
        WITH candidates AS (
            SELECT outbox_id FROM outbox
            WHERE published_at IS NULL AND next_attempt_at <= now()
              AND (claim_expires_at IS NULL OR claim_expires_at <= now())
            ORDER BY outbox_id
            FOR UPDATE SKIP LOCKED
            LIMIT %s
        )
        UPDATE outbox AS event
        SET claim_owner=%s,claim_token=%s,
            claim_expires_at=now() + make_interval(secs => %s)
        FROM candidates
        WHERE event.outbox_id=candidates.outbox_id AND event.published_at IS NULL
        RETURNING event.outbox_id,event.event_id,event.subject,event.payload,
                  event.publish_attempts,event.claim_token
        """,
        (settings.outbox_batch_size, relay_id, claim_token, settings.outbox_claim_seconds),
    ).fetchall()
    connection.commit()
    return rows


async def publish_pending(settings: Settings, js, relay_id: str | None = None) -> int:
    published = 0
    relay_id = relay_id or f"{socket.gethostname()}:{uuid4()}"
    with connect(settings.database_url) as connection:
        rows = claim_pending(connection, settings, relay_id)
        checkpoint("outbox.after_claim")
        for row in rows:
            checkpoint("outbox.before_publish")
            headers = {"Nats-Msg-Id": str(row["event_id"]), "Content-Type": "application/json"}
            try:
                await js.publish(
                    row["subject"],
                    json.dumps(row["payload"], separators=(",", ":"), default=str).encode(),
                    headers=headers,
                    timeout=5,
                )
                checkpoint("outbox.after_publish_before_mark")
                updated = connection.execute(
                    """
                    UPDATE outbox SET published_at=now(), publish_attempts=publish_attempts+1,
                        last_error=NULL,claim_owner=NULL,claim_token=NULL,claim_expires_at=NULL
                    WHERE outbox_id=%s AND published_at IS NULL
                      AND claim_owner=%s AND claim_token=%s AND claim_expires_at>now()
                    RETURNING outbox_id
                    """,
                    (row["outbox_id"],relay_id,row["claim_token"]),
                ).fetchone()
                connection.commit()
                checkpoint("outbox.after_mark")
                published += 1 if updated is not None else 0
            except Exception as exc:
                connection.rollback()
                attempt = row["publish_attempts"] + 1
                delay = min(300, 2 ** min(attempt, 8)) + random.random()
                connection.execute(
                    """
                    UPDATE outbox SET publish_attempts=publish_attempts+1,
                        next_attempt_at=now() + make_interval(secs => %s), last_error=%s,
                        claim_owner=NULL,claim_token=NULL,claim_expires_at=NULL
                    WHERE outbox_id=%s AND published_at IS NULL
                      AND claim_owner=%s AND claim_token=%s
                    """,
                    (delay,str(exc)[:2000],row["outbox_id"],relay_id,row["claim_token"]),
                )
                connection.commit()
                logger.exception("outbox publish failed", extra={"event_id": str(row["event_id"])})
    return published


async def run() -> None:
    settings = Settings()
    migrate(settings.database_url)
    nc = await nats.connect(
        settings.nats_url,
        name="signal-outbox-relay",
        reconnect_time_wait=2,
        max_reconnect_attempts=-1,
    )
    js = nc.jetstream()
    await ensure_streams(js)
    relay_id = f"{socket.gethostname()}:{uuid4()}"
    try:
        while True:
            count = await publish_pending(settings, js, relay_id)
            with connect(settings.database_url) as connection:
                heartbeat(connection, "outbox", "healthy", {"last_batch": count})
            await asyncio.sleep(settings.outbox_poll_seconds if count == 0 else 0)
    finally:
        await nc.drain()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
