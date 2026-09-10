import asyncio
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import nats
import psycopg
import pytest
from psycopg.rows import dict_row

from trading_platform.atomic_snapshot import read_snapshot
from trading_platform.contracts import PortfolioRating, SignedEnvelope
from trading_platform.nats_support import DEAD_LETTER_STREAM, SIGNAL_STREAM, ensure_streams


DATABASE_URL = os.getenv("TEST_POSTGRES_URL")
NATS_URL = os.getenv("TEST_NATS_URL")
NATS_CONTAINER = os.getenv("TEST_NATS_CONTAINER")
pytestmark = [
    pytest.mark.skipif(not DATABASE_URL,reason="TEST_POSTGRES_URL is not set"),
    pytest.mark.skipif(not NATS_URL,reason="TEST_NATS_URL is not set"),
]
SECRET = "a-reliable-test-secret-that-is-longer-than-32-bytes"


async def reset_broker():
    nc = await nats.connect(NATS_URL,allow_reconnect=False)
    js = nc.jetstream()
    await ensure_streams(js)
    await js.purge_stream(SIGNAL_STREAM)
    await js.purge_stream(DEAD_LETTER_STREAM)
    return nc,js


def routed_signal(signal_factory,bot_id: str,sequence: int=1):
    original = signal_factory(rating=PortfolioRating.BUY)
    payload = original.payload.model_copy(update={
        "environment": "test", "bot_id": bot_id, "sequence": sequence,
    })
    return SignedEnvelope.sign(payload,SECRET)


def bridge_env(bot_id: str,snapshot_dir: Path,checkpoint: str | None=None):
    env = {
        **os.environ,
        "PYTHONPATH": str(Path.cwd()/"src"),
        "PLATFORM_DATABASE_URL": DATABASE_URL,
        "PLATFORM_NATS_CONSUMER_URL": NATS_URL,
        "PLATFORM_NATS_URL": NATS_URL,
        "PLATFORM_ENVIRONMENT": "test",
        "PLATFORM_BOT_ID": bot_id,
        "PLATFORM_EXCHANGE": "binance",
        "PLATFORM_TIMEFRAME": "5m",
        "PLATFORM_HMAC_SECRET": SECRET,
        "PLATFORM_AUDIT_TOKEN": "chaos-audit-token-long-enough",
        "PLATFORM_SNAPSHOT_DIR": str(snapshot_dir),
        "PLATFORM_BRIDGE_ACK_WAIT_SECONDS": "5",
        "PLATFORM_BRIDGE_MAX_DELIVERIES": "5",
    }
    if checkpoint:
        env.update({
            "PLATFORM_FAULT_INJECTION": "1",
            "PLATFORM_FAULT_CHECKPOINT": checkpoint,
            "PLATFORM_FAULT_MARKER_DIR": str(snapshot_dir/"markers"),
        })
    else:
        env.pop("PLATFORM_FAULT_INJECTION",None)
        env.pop("PLATFORM_FAULT_CHECKPOINT",None)
        env.pop("PLATFORM_FAULT_MARKER_DIR",None)
    return env


def start_bridge(bot_id: str,snapshot_dir: Path,checkpoint: str | None=None):
    command = (
        "import asyncio; import trading_platform.bridge as bridge; "
        "bridge.migrate=lambda *a,**k:None; asyncio.run(bridge.run())"
    )
    return subprocess.Popen(
        [sys.executable,"-c",command],env=bridge_env(bot_id,snapshot_dir,checkpoint),
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
    )


def stop_process(process):
    if process.poll() is None:
        process.kill()
        process.wait(timeout=5)


def wait_marker(process,marker: Path,timeout=10):
    deadline = time.monotonic()+timeout
    while not marker.exists() and process.poll() is None and time.monotonic()<deadline:
        time.sleep(0.02)
    if not marker.exists():
        stop_process(process)
        stdout,stderr = process.communicate()
        pytest.fail(f"bridge missed marker {marker.name}: {stdout!r} {stderr!r}")


async def wait_receipt(bot_id,event_id,timeout=12):
    deadline = time.monotonic()+timeout
    while time.monotonic()<deadline:
        with psycopg.connect(DATABASE_URL,row_factory=dict_row) as connection:
            row = connection.execute(
                "SELECT disposition,reason FROM delivery_receipts "
                "WHERE consumer_id=%s AND event_id=%s",
                (f"bridge:{bot_id}",event_id),
            ).fetchone()
        if row:
            return row
        await asyncio.sleep(0.05)
    raise AssertionError(f"receipt {event_id} did not appear")


async def wait_consumer_acked(js,bot_id,timeout=12):
    durable = f"bridge-test-{bot_id}".replace("_","-")
    deadline = time.monotonic()+timeout
    while time.monotonic()<deadline:
        try:
            info = await js.consumer_info(SIGNAL_STREAM,durable)
            if info.num_ack_pending == 0 and info.num_pending == 0:
                return
        except Exception:
            pass
        await asyncio.sleep(0.05)
    raise AssertionError(f"consumer {durable} did not acknowledge its delivery")


async def publish(js,envelope):
    pair = envelope.payload.pair.replace("/","_").replace(":","_")
    subject = (
        f"signals.v2.{envelope.payload.environment}.{envelope.payload.exchange}."
        f"{envelope.payload.bot_id}.{pair}"
    )
    await js.publish(
        subject,envelope.model_dump_json().encode(),
        headers={"Nats-Msg-Id":str(envelope.payload.event_id)},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("checkpoint","receipt_before_kill"),
    [
        ("bridge.before_materialization",False),
        ("bridge.after_snapshot_replace",False),
        ("bridge.after_receipt_before_ack",True),
    ],
)
async def test_bridge_kill_boundaries_redeliver_and_converge(
    tmp_path,signal_factory,checkpoint,receipt_before_kill,
):
    nc,js = await reset_broker()
    bot_id = f"bridge-{uuid4().hex[:10]}"
    envelope = routed_signal(signal_factory,bot_id)
    process = start_bridge(bot_id,tmp_path,checkpoint)
    try:
        await publish(js,envelope)
        marker = tmp_path/"markers"/f"{checkpoint.replace('.', '_')}.json"
        await asyncio.to_thread(wait_marker,process,marker)
        with psycopg.connect(DATABASE_URL,row_factory=dict_row) as connection:
            receipt = connection.execute(
                "SELECT disposition FROM delivery_receipts WHERE consumer_id=%s AND event_id=%s",
                (f"bridge:{bot_id}",envelope.payload.event_id),
            ).fetchone()
        assert (receipt is not None) is receipt_before_kill
        process.kill(); assert process.wait(timeout=5) == -signal.SIGKILL
        process = start_bridge(bot_id,tmp_path)
        row = await wait_receipt(bot_id,envelope.payload.event_id)
        assert row["disposition"] in ("materialized","duplicate")
        await wait_consumer_acked(js,bot_id)
        assert read_snapshot(tmp_path,"BTC/USDT","5m").payload.event_id == envelope.payload.event_id
    finally:
        stop_process(process)
        await nc.close()


@pytest.mark.asyncio
async def test_concurrent_bridges_never_move_stream_backwards(tmp_path,signal_factory):
    nc,js = await reset_broker()
    bot_id = f"bridge-{uuid4().hex[:10]}"
    first = routed_signal(signal_factory,bot_id,1)
    second = routed_signal(signal_factory,bot_id,2)
    processes = [start_bridge(bot_id,tmp_path),start_bridge(bot_id,tmp_path)]
    try:
        await publish(js,second)
        await publish(js,first)
        await wait_receipt(bot_id,second.payload.event_id)
        await wait_receipt(bot_id,first.payload.event_id)
        assert read_snapshot(tmp_path,"BTC/USDT","5m").payload.sequence == 2
    finally:
        for process in processes: stop_process(process)
        await nc.close()


@pytest.mark.asyncio
async def test_signal_revocation_race_ends_in_tombstone(
    tmp_path,signal_factory,revocation_factory,
):
    nc,js = await reset_broker()
    bot_id = f"bridge-{uuid4().hex[:10]}"
    signal_envelope = routed_signal(signal_factory,bot_id,1)
    revocation = revocation_factory(target=signal_envelope)
    processes = [start_bridge(bot_id,tmp_path),start_bridge(bot_id,tmp_path)]
    try:
        await publish(js,signal_envelope)
        await publish(js,revocation)
        await wait_receipt(bot_id,revocation.payload.event_id)
        snapshot = read_snapshot(tmp_path,"BTC/USDT","5m")
        assert snapshot.payload.event_type == "signal.revoked"
        assert snapshot.payload.sequence == 2
    finally:
        for process in processes: stop_process(process)
        await nc.close()


@pytest.mark.asyncio
async def test_malformed_message_is_terminated_into_dlq(tmp_path):
    nc,js = await reset_broker()
    bot_id = f"bridge-{uuid4().hex[:10]}"
    process = start_bridge(bot_id,tmp_path)
    try:
        await js.publish(
            f"signals.v2.test.binance.{bot_id}.BTC_USDT",b"not-json",
            headers={"Nats-Msg-Id":str(uuid4())},
        )
        deadline = time.monotonic()+10
        count = 0
        while count != 1 and time.monotonic()<deadline:
            count = (await js.stream_info(DEAD_LETTER_STREAM)).state.messages
            await asyncio.sleep(0.05)
        assert count == 1
    finally:
        stop_process(process)
        await nc.close()


@pytest.mark.asyncio
async def test_snapshot_write_failure_commits_no_receipt_then_retries(
    tmp_path,signal_factory,
):
    nc,js = await reset_broker()
    bot_id = f"bridge-{uuid4().hex[:10]}"
    envelope = routed_signal(signal_factory,bot_id)
    tmp_path.chmod(0o500)
    process = start_bridge(bot_id,tmp_path)
    try:
        await publish(js,envelope)
        await asyncio.sleep(1)
        with psycopg.connect(DATABASE_URL) as connection:
            assert connection.execute(
                "SELECT count(*) FROM delivery_receipts WHERE consumer_id=%s AND event_id=%s",
                (f"bridge:{bot_id}",envelope.payload.event_id),
            ).fetchone()[0] == 0
        tmp_path.chmod(0o700)
        stop_process(process)
        process = start_bridge(bot_id,tmp_path)
        row = await wait_receipt(bot_id,envelope.payload.event_id)
        assert row["disposition"] == "materialized"
    finally:
        tmp_path.chmod(0o700)
        stop_process(process)
        await nc.close()


@pytest.mark.asyncio
@pytest.mark.skipif(not NATS_CONTAINER,reason="TEST_NATS_CONTAINER is not set")
async def test_bridge_reconnects_after_nats_restart(tmp_path,signal_factory):
    nc,js = await reset_broker()
    bot_id = f"bridge-{uuid4().hex[:10]}"
    envelope = routed_signal(signal_factory,bot_id)
    process = start_bridge(bot_id,tmp_path)
    await asyncio.sleep(0.3)
    await nc.close()
    subprocess.run(["docker","stop",NATS_CONTAINER],check=True,capture_output=True,text=True)
    subprocess.run(["docker","start",NATS_CONTAINER],check=True,capture_output=True,text=True)
    replacement = None
    deadline = time.monotonic()+10
    while replacement is None and time.monotonic()<deadline:
        try:
            replacement = await nats.connect(NATS_URL,allow_reconnect=False)
        except Exception:
            await asyncio.sleep(0.05)
    assert replacement is not None
    try:
        await publish(replacement.jetstream(),envelope)
        try:
            receipt = await wait_receipt(bot_id,envelope.payload.event_id)
        except AssertionError:
            status = process.poll()
            if status is not None:
                stdout,stderr = process.communicate()
                pytest.fail(
                    f"bridge exited after NATS restart with {status}: "
                    f"stdout={stdout!r} stderr={stderr!r}"
                )
            raise
        assert receipt["disposition"] == "materialized"
    finally:
        stop_process(process)
        await replacement.close()
