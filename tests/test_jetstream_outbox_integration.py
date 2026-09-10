import asyncio
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import nats
import psycopg
import pytest
from psycopg.rows import dict_row

from trading_platform.outbox import publish_pending


DATABASE_URL = os.getenv("TEST_POSTGRES_URL")
NATS_URL = os.getenv("TEST_NATS_URL")
NATS_CONTAINER = os.getenv("TEST_NATS_CONTAINER")
pytestmark = [
    pytest.mark.skipif(not DATABASE_URL, reason="TEST_POSTGRES_URL is not set"),
    pytest.mark.skipif(not NATS_URL, reason="TEST_NATS_URL is not set"),
]


def settings(batch_size=1):
    return SimpleNamespace(
        database_url=DATABASE_URL,outbox_batch_size=batch_size,outbox_claim_seconds=30,
    )


def seed_outbox(subject: str, count: int = 1):
    event_ids = [uuid4() for _ in range(count)]
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            """UPDATE outbox SET published_at=now(),claim_owner=NULL,claim_token=NULL,
               claim_expires_at=NULL WHERE published_at IS NULL"""
        )
        with connection.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO outbox(event_id,subject,payload) VALUES (%s,%s,'{}')",
                [(event_id,subject) for event_id in event_ids],
            )
        connection.commit()
    return event_ids


async def new_stream():
    nc = await nats.connect(NATS_URL, allow_reconnect=False)
    js = nc.jetstream()
    suffix = uuid4().hex
    name, subject = f"CHAOS_{suffix.upper()}", f"chaos.outbox.{suffix}"
    await js.add_stream(name=name,subjects=[subject],duplicate_window=24*60*60)
    return nc, js, name, subject


async def message_count(js, stream: str) -> int:
    return (await js.stream_info(stream)).state.messages


def kill_relay_at(checkpoint: str, marker_dir: Path) -> None:
    marker = marker_dir / f"{checkpoint.replace('.', '_')}.json"
    env = {
        **os.environ,
        "PYTHONPATH": str(Path.cwd() / "src"),
        "PLATFORM_DATABASE_URL": DATABASE_URL,
        "PLATFORM_NATS_URL": NATS_URL,
        "PLATFORM_ENVIRONMENT": "test",
        "PLATFORM_HMAC_SECRET": "a-reliable-test-secret-that-is-longer-than-32-bytes",
        "PLATFORM_AUDIT_TOKEN": "chaos-audit-token-long-enough",
        "PLATFORM_OUTBOX_BATCH_SIZE": "1",
        "PLATFORM_OUTBOX_CLAIM_SECONDS": "30",
        "PLATFORM_FAULT_INJECTION": "1",
        "PLATFORM_FAULT_CHECKPOINT": checkpoint,
        "PLATFORM_FAULT_MARKER_DIR": str(marker_dir),
    }
    command = (
        "import asyncio,nats\n"
        "from trading_platform.settings import Settings\n"
        "from trading_platform.outbox import publish_pending\n"
        "async def main():\n"
        " s=Settings(); nc=await nats.connect(s.nats_url,allow_reconnect=False); "
        "await publish_pending(s,nc.jetstream(),'killed-relay')\n"
        "asyncio.run(main())"
    )
    process = subprocess.Popen(
        [sys.executable,"-c",command],env=env,stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,text=True,
    )
    deadline = time.monotonic()+10
    try:
        while not marker.exists() and process.poll() is None and time.monotonic()<deadline:
            time.sleep(0.02)
        if not marker.exists():
            stdout,stderr = process.communicate(timeout=2)
            pytest.fail(f"relay missed {checkpoint}: stdout={stdout!r} stderr={stderr!r}")
        process.kill()
        assert process.wait(timeout=5) == -signal.SIGKILL
    finally:
        if process.poll() is None:
            process.kill(); process.wait(timeout=5)


def expire_claim(event_id) -> None:
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "UPDATE outbox SET claim_expires_at=now()-interval '1 second' WHERE event_id=%s",
            (event_id,),
        )
        connection.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("checkpoint","count_before","already_published"),
    [
        ("outbox.before_publish",0,False),
        ("outbox.after_publish_before_mark",1,False),
        ("outbox.after_mark",1,True),
    ],
)
async def test_outbox_kill_boundaries_converge_without_duplicate_messages(
    tmp_path,checkpoint,count_before,already_published,
):
    nc,js,stream,subject = await new_stream()
    event_id = seed_outbox(subject)[0]
    try:
        kill_relay_at(checkpoint,tmp_path)
        assert await message_count(js,stream) == count_before
        with psycopg.connect(DATABASE_URL,row_factory=dict_row) as connection:
            row = connection.execute(
                "SELECT published_at,claim_token FROM outbox WHERE event_id=%s",(event_id,),
            ).fetchone()
        assert (row["published_at"] is not None) is already_published
        if not already_published:
            assert row["claim_token"] is not None
            expire_claim(event_id)
            assert await publish_pending(settings(),js,"recovery-relay") == 1
        else:
            assert await publish_pending(settings(),js,"recovery-relay") == 0
        assert await message_count(js,stream) == 1
    finally:
        await nc.close()


@pytest.mark.asyncio
async def test_two_live_relays_publish_disjoint_batches_once():
    nc,js,stream,subject = await new_stream()
    event_ids = set(seed_outbox(subject,20))
    try:
        results = await asyncio.gather(
            publish_pending(settings(10),js,"relay-a"),
            publish_pending(settings(10),js,"relay-b"),
        )
        assert sorted(results) == [10,10]
        assert await message_count(js,stream) == 20
        with psycopg.connect(DATABASE_URL,row_factory=dict_row) as connection:
            rows = connection.execute(
                "SELECT event_id,published_at,claim_token FROM outbox WHERE event_id=ANY(%s)",
                (list(event_ids),),
            ).fetchall()
        assert {row["event_id"] for row in rows} == event_ids
        assert all(row["published_at"] is not None and row["claim_token"] is None for row in rows)
    finally:
        await nc.close()


@pytest.mark.asyncio
@pytest.mark.skipif(not NATS_CONTAINER,reason="TEST_NATS_CONTAINER is not set")
async def test_broker_outage_keeps_outbox_authoritative_and_restart_drains():
    nc,js,stream,subject = await new_stream()
    event_id = seed_outbox(subject)[0]
    subprocess.run(["docker","stop",NATS_CONTAINER],check=True,capture_output=True,text=True)
    try:
        deadline = time.monotonic()+5
        while not nc.is_closed and time.monotonic()<deadline:
            await asyncio.sleep(0.02)
        assert await publish_pending(settings(),js,"outage-relay") == 0
        with psycopg.connect(DATABASE_URL,row_factory=dict_row) as connection:
            row = connection.execute(
                "SELECT published_at,claim_token,last_error FROM outbox WHERE event_id=%s",
                (event_id,),
            ).fetchone()
        assert row["published_at"] is None and row["claim_token"] is None
        assert row["last_error"]
    finally:
        subprocess.run(["docker","start",NATS_CONTAINER],check=True,capture_output=True,text=True)
    deadline = time.monotonic()+10
    replacement = None
    while replacement is None and time.monotonic()<deadline:
        try:
            replacement = await nats.connect(NATS_URL,allow_reconnect=False)
        except Exception:
            await asyncio.sleep(0.05)
    assert replacement is not None
    try:
        with psycopg.connect(DATABASE_URL) as connection:
            connection.execute("UPDATE outbox SET next_attempt_at=now() WHERE event_id=%s",(event_id,))
            connection.commit()
        replacement_js = replacement.jetstream()
        assert await publish_pending(settings(),replacement_js,"restart-relay") == 1
        assert await message_count(replacement_js,stream) == 1
    finally:
        await replacement.close()
