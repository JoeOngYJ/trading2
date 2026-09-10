from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

import nats
from nats.errors import Error as NatsError
from nats.js.errors import NotFoundError
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from .atomic_snapshot import atomic_write_snapshot, read_snapshot, write_health
from .contracts import SignalRevocationPayload, SignedEnvelope
from .db import connect, migrate
from .nats_support import (
    DEAD_LETTER_STREAM,
    SIGNAL_STREAM,
    SIGNAL_SUBJECT,
    bridge_consumer_config,
    ensure_streams,
)
from .repository import heartbeat, kill_switch_enabled
from .fault_injection import checkpoint
from .settings import Settings
from .signal_validation import validate_for_materialization


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("bridge")


def materialize(envelope: SignedEnvelope, settings: Settings) -> tuple[str, str | None]:
    """Persist one event idempotently and replace a snapshot only when newer."""
    now = datetime.now(timezone.utc)
    invalid_reason = validate_for_materialization(envelope, settings, now)
    payload = envelope.payload
    consumer_id = f"bridge:{settings.bot_id}"
    with connect(settings.database_url) as connection:
        with connection.transaction():
            route = (
                consumer_id,payload.environment,payload.bot_id,payload.exchange,
                payload.pair,payload.timeframe,
            )
            connection.execute(
                """
                INSERT INTO materialization_cursors(
                    consumer_id,environment,bot_id,exchange,pair,timeframe
                ) VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING
                """,
                route,
            )
            cursor = connection.execute(
                """
                SELECT sequence,event_id,signal_id,checksum,disposition
                FROM materialization_cursors
                WHERE consumer_id=%s AND environment=%s AND bot_id=%s
                  AND exchange=%s AND pair=%s AND timeframe=%s
                FOR UPDATE
                """,
                route,
            ).fetchone()
            existing = connection.execute(
                "SELECT disposition FROM delivery_receipts WHERE consumer_id=%s AND event_id=%s",
                (consumer_id, payload.event_id),
            ).fetchone()
            if existing:
                return "duplicate", None

            file_envelope = None
            try:
                candidate = read_snapshot(settings.snapshot_dir, payload.pair, payload.timeframe)
                candidate_payload = candidate.payload
                if (
                    candidate.verify(settings.hmac_secret)
                    and candidate_payload.environment == payload.environment
                    and candidate_payload.bot_id == payload.bot_id
                    and candidate_payload.exchange == payload.exchange
                    and candidate_payload.pair == payload.pair
                    and candidate_payload.timeframe == payload.timeframe
                ):
                    file_envelope = candidate
            except (FileNotFoundError, ValueError):
                pass

            disposition = (
                "revoked" if isinstance(payload, SignalRevocationPayload) else "materialized"
            )
            reason = invalid_reason
            same_file_event = bool(
                file_envelope and file_envelope.payload.sequence == payload.sequence
                and file_envelope.payload.event_id == payload.event_id
                and file_envelope.checksum == envelope.checksum
            )
            cursor_sequence = int(cursor["sequence"])
            file_sequence = file_envelope.payload.sequence if file_envelope else 0
            highest_sequence = max(cursor_sequence, file_sequence)
            highest_identity = None
            if file_envelope and file_sequence == highest_sequence:
                highest_identity = (file_envelope.payload.event_id, file_envelope.checksum)
            elif cursor_sequence == highest_sequence and cursor_sequence > 0:
                highest_identity = (cursor["event_id"], cursor["checksum"])

            if invalid_reason:
                disposition = "expired" if invalid_reason == "expired" else "rejected"
            elif payload.sequence < highest_sequence:
                disposition, reason = "stale", "sequence_not_newer"
            elif payload.sequence == highest_sequence and highest_identity != (
                payload.event_id,envelope.checksum,
            ):
                disposition, reason = "rejected", "sequence_identity_conflict"
            elif disposition == "materialized" and kill_switch_enabled(connection, settings.bot_id):
                disposition, reason = "rejected", "kill_switch_enabled"

            if disposition in ("materialized", "revoked"):
                if not same_file_event:
                    atomic_write_snapshot(settings.snapshot_dir, envelope)
                checkpoint("bridge.after_snapshot_replace")
            connection.execute(
                """
                INSERT INTO delivery_receipts(consumer_id,event_id,signal_id,sequence,disposition,reason)
                VALUES (%s,%s,%s,%s,%s,%s)
                """,
                (consumer_id,payload.event_id,payload.signal_id,payload.sequence,disposition,reason),
            )
            if disposition in ("materialized", "revoked"):
                connection.execute(
                    """
                    UPDATE materialization_cursors
                    SET sequence=%s,event_id=%s,signal_id=%s,checksum=%s,
                        disposition=%s,updated_at=now()
                    WHERE consumer_id=%s AND environment=%s AND bot_id=%s
                      AND exchange=%s AND pair=%s AND timeframe=%s
                    """,
                    (
                        payload.sequence,payload.event_id,payload.signal_id,envelope.checksum,
                        disposition,*route,
                    ),
                )
    return disposition, reason


async def dead_letter(js, msg, reason: str) -> None:
    event_id = msg.headers.get("Nats-Msg-Id", "unknown") if msg.headers else "unknown"
    headers = {"Original-Subject": msg.subject, "Failure-Reason": reason, "Nats-Msg-Id": event_id}
    await js.publish(f"signals.dlq.{event_id}", msg.data, headers=headers)


async def _restore_subscription(nc, js, bind_subscription, settings, reason: str):
    """Wait for both NATS transport and JetStream management readiness, then rebind."""
    delay = 0.1
    while True:
        while not nc.is_connected:
            if nc.is_closed:
                raise ConnectionError("NATS connection closed during bridge restoration")
            await asyncio.sleep(0.1)
        try:
            await ensure_streams(js)
            return await bind_subscription()
        except NatsError as exc:
            logger.warning(
                "bridge waiting for JetStream readiness",
                extra={"bot_id": settings.bot_id, "reason": reason, "error": str(exc)},
            )
            write_health(settings.snapshot_dir, {
                "status": "unhealthy", "observed_at": datetime.now(timezone.utc),
                "reason": reason,
            })
            await asyncio.sleep(delay)
            delay = min(delay * 2, 2.0)


async def run() -> None:
    settings = Settings()
    migrate(settings.database_url)
    settings.snapshot_dir.mkdir(parents=True, exist_ok=True)
    reconnected = asyncio.Event()

    async def disconnected_cb() -> None:
        logger.warning("bridge disconnected from NATS", extra={"bot_id": settings.bot_id})
        write_health(settings.snapshot_dir, {
            "status": "unhealthy", "observed_at": datetime.now(timezone.utc),
            "reason": "nats_disconnected",
        })

    async def reconnected_cb() -> None:
        logger.info("bridge reconnected to NATS", extra={"bot_id": settings.bot_id})
        reconnected.set()

    nc = await nats.connect(
        settings.consumer_nats_url,
        name=f"signal-bridge-{settings.bot_id}",
        reconnect_time_wait=2,
        max_reconnect_attempts=-1,
        disconnected_cb=disconnected_cb,
        reconnected_cb=reconnected_cb,
    )
    js = nc.jetstream()
    durable = f"bridge-{settings.environment}-{settings.bot_id}".replace("_", "-")

    async def bind_subscription():
        return await js.pull_subscribe(
            SIGNAL_SUBJECT,
            durable=durable,
            stream=SIGNAL_STREAM,
            config=bridge_consumer_config(
                durable, settings.bridge_ack_wait_seconds, settings.bridge_max_deliveries,
            ),
        )

    subscription = await _restore_subscription(
        nc, js, bind_subscription, settings, "jetstream_starting",
    )
    try:
        while True:
            if reconnected.is_set():
                reconnected.clear()
                subscription = await _restore_subscription(
                    nc, js, bind_subscription, settings, "jetstream_rebinding",
                )
            try:
                messages = await subscription.fetch(batch=10, timeout=2)
            except asyncio.TimeoutError:
                if reconnected.is_set():
                    continue
                write_health(settings.snapshot_dir, {"status": "healthy", "observed_at": datetime.now(timezone.utc)})
                continue
            except NatsError:
                if nc.is_connected:
                    raise
                write_health(settings.snapshot_dir, {
                    "status": "unhealthy", "observed_at": datetime.now(timezone.utc),
                    "reason": "nats_reconnecting",
                })
                reconnected.clear()
                subscription = await _restore_subscription(
                    nc, js, bind_subscription, settings, "jetstream_rebinding",
                )
                continue
            for msg in messages:
                try:
                    checkpoint("bridge.before_materialization")
                    envelope = SignedEnvelope.model_validate_json(msg.data)
                    disposition, reason = materialize(envelope, settings)
                    if disposition == "rejected":
                        await dead_letter(js, msg, reason or "rejected")
                    checkpoint("bridge.after_receipt_before_ack")
                    await msg.ack()
                except (ValidationError, ValueError) as exc:
                    await dead_letter(js, msg, f"contract_invalid:{exc}"[:500])
                    await msg.term()
                except Exception:
                    logger.exception("bridge processing failed")
                    await msg.nak(delay=2)
            write_health(settings.snapshot_dir, {"status": "healthy", "observed_at": datetime.now(timezone.utc)})
            with connect(settings.database_url) as connection:
                heartbeat(connection, f"bridge:{settings.bot_id}", "healthy", {})
    finally:
        await nc.drain()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
