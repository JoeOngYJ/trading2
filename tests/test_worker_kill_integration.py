import os
import signal
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg.rows import dict_row

from trading_platform.capture import begin_capture_evaluation, start_capture_session
from trading_platform.contracts import CaptureFence, CaptureSession
from trading_platform.repository import (
    claim_analysis_job, create_analysis_attempt, fail_analysis_job,
    recover_expired_analysis_jobs, renew_analysis_job_lease,
)
from trading_platform.source_allowlist import ALLOWED_INGRESS


DATABASE_URL = os.getenv("TEST_POSTGRES_URL")
POSTGRES_CONTAINER = os.getenv("TEST_POSTGRES_CONTAINER")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="TEST_POSTGRES_URL is not set")
SECRET = "a-reliable-test-secret-that-is-longer-than-32-bytes"
INSTRUMENT = "crypto:binance:spot:BTC-USDT"


def seed_job(
    *, with_observation: bool, clean: bool = True, bot_id: str | None = None,
    candle_age_minutes: int = 5,
) -> tuple[object, str]:
    now = datetime.now(timezone.utc)
    snapshot_id, job_id, observation_id = uuid4(), uuid4(), uuid4()
    digest = "sha256:" + uuid4().hex * 2
    bot_id = bot_id or f"chaos-{job_id.hex[:10]}"
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as connection:
        if clean:
            connection.execute(
                """UPDATE analysis_jobs SET status='dead',lease_owner=NULL,lease_expires_at=NULL,
                   last_error='chaos_fixture_superseded'
                   WHERE status IN ('pending','failed','running')"""
            )
        connection.execute(
            "INSERT INTO artifacts(digest,media_type,byte_length,storage_path) "
            "VALUES (%s,'application/json',2,%s)", (digest, f"chaos/{snapshot_id}"),
        )
        connection.execute(
            """INSERT INTO execution_market_snapshots(
              snapshot_id,instrument_id,exchange,pair,market_type,timeframe,candle_type,
              candle_open_at,candle_close_at,open_price,high_price,low_price,close_price,
              volume,retrieved_at,exchange_time_at,clock_offset_ms,is_closed,has_gap,
              collector_version,raw_artifact_digest)
              VALUES (%s,%s,'binance','BTC/USDT','spot','5m','spot',%s,%s,
                      1,2,1,2,10,%s,%s,0,true,false,'chaos',%s)""",
            (snapshot_id,INSTRUMENT,now-timedelta(minutes=candle_age_minutes+5),
             now-timedelta(minutes=candle_age_minutes), now-timedelta(minutes=4),
             now-timedelta(minutes=4),digest),
        )
        if with_observation:
            connection.execute(
                """INSERT INTO source_observations(
                  observation_id,category,vendor,symbol_or_query,external_id,event_at,
                  first_seen_at,retrieved_at,artifact_digest,request_parameters,status,
                  quality_flags,replay_safe)
                  VALUES (%s,'execution_market','synthetic','BTC/USDT',%s,%s,%s,%s,%s,
                          '{}','available','[]',true)""",
                (observation_id,str(snapshot_id),now-timedelta(minutes=candle_age_minutes),
                 now-timedelta(minutes=4),now-timedelta(minutes=4),digest),
            )
        connection.execute(
            """INSERT INTO analysis_jobs(
              job_id,correlation_id,symbol,pair,timeframe,candle_close_at,status,
              instrument_id,execution_snapshot_id)
              VALUES (%s,%s,'BTC-USD','BTC/USDT','5m',%s,'pending',%s,%s)""",
            (job_id,uuid4(),now-timedelta(minutes=candle_age_minutes),INSTRUMENT,snapshot_id),
        )
        connection.commit()
    return job_id, bot_id


def worker_environment(bot_id: str, marker_dir: Path, checkpoint: str | None = None) -> dict:
    research_mode = (
        "tradingagents" if checkpoint in {
            "worker.after_capture_creation", "worker.after_collection_close",
        } else "synthetic"
    )
    return {
        **os.environ,
        "PYTHONPATH": str(Path.cwd() / "src"),
        "PLATFORM_DATABASE_URL": DATABASE_URL,
        "PLATFORM_ENVIRONMENT": "test",
        "PLATFORM_BOT_ID": bot_id,
        "PLATFORM_EXCHANGE": "binance",
        "PLATFORM_TIMEFRAME": "5m",
        "PLATFORM_HMAC_SECRET": SECRET,
        "PLATFORM_AUDIT_TOKEN": "chaos-audit-token-long-enough",
        "PLATFORM_RESEARCH_MODE": research_mode,
        "PLATFORM_MARKET_DATA_MODE": "synthetic",
        "PLATFORM_ANALYSIS_LEASE_SECONDS": "30",
        "PLATFORM_ANALYSIS_LEASE_RENEW_SECONDS": "5",
        "PLATFORM_FAULT_INJECTION": "1" if checkpoint else "0",
        "PLATFORM_FAULT_CHECKPOINT": checkpoint or "",
        "PLATFORM_FAULT_MARKER_DIR": str(marker_dir),
        "PLATFORM_ARTIFACT_DIR": str(marker_dir / "artifacts"),
        "PLATFORM_PAIR_MAP_PATH": str(Path.cwd() / "config/pair_map.json"),
    }


def pause_worker_at(checkpoint: str, bot_id: str, marker_dir: Path) -> subprocess.Popen:
    marker = marker_dir / f"{checkpoint.replace('.', '_')}.json"
    env = worker_environment(bot_id, marker_dir, checkpoint)
    if env["PLATFORM_RESEARCH_MODE"] == "tradingagents":
        command = (
            "from trading_platform.settings import Settings; "
            "import trading_platform.worker as worker; "
            "from trading_platform.research import synthetic_result; "
            "worker.build_tradingagents_configuration=lambda *a,**k:{}; "
            "worker.TradingAgentsCaptureAdapter=lambda *a,**k:object(); "
            "worker.run_tradingagents=lambda symbol,*a,**k:synthetic_result(symbol); "
            "worker.process_one(Settings(), 'chaos-worker')"
        )
    else:
        command = (
            "from trading_platform.settings import Settings; "
            "from trading_platform.worker import process_one; "
            "process_one(Settings(), 'chaos-worker')"
        )
    process = subprocess.Popen(
        [sys.executable, "-c", command],env=env,stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,text=True,
    )
    deadline = time.monotonic() + 10
    while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
        time.sleep(0.02)
    if not marker.exists():
        stdout, stderr = process.communicate(timeout=2)
        pytest.fail(f"worker missed {checkpoint}: stdout={stdout!r} stderr={stderr!r}")
    return process


def kill_worker_at(checkpoint: str, job_id, bot_id: str, marker_dir: Path) -> None:
    process = pause_worker_at(checkpoint, bot_id, marker_dir)
    try:
        process.kill()
        assert process.wait(timeout=5) == -signal.SIGKILL
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as connection:
        claimed = connection.execute(
            "SELECT status,lease_owner FROM analysis_jobs WHERE job_id=%s", (job_id,),
        ).fetchone()
        assert claimed["status"] in ("running", "succeeded")


def expire(job_id) -> None:
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "UPDATE analysis_jobs SET lease_expires_at=now()-interval '1 second' "
            "WHERE job_id=%s AND status='running'", (job_id,),
        )
        connection.commit()


def recover(bot_id: str) -> int:
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as connection:
        return recover_expired_analysis_jobs(connection, {
            "environment": "test", "bot_id": bot_id, "hmac_secret": SECRET,
            "producer_version": "chaos", "code_revision": "chaos",
        })


def create_partial_capture(job_id, *, evaluating: bool):
    run_id = uuid4()
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as connection:
        job = claim_analysis_job(connection, "dead-capture-worker", 30)
        assert job["job_id"] == job_id
        create_analysis_attempt(
            connection,run_id=run_id,job=job,started_at=datetime.now(timezone.utc),
            producer_version="chaos",code_revision="chaos",
            configuration={"research_mode": "tradingagents"},
        )
        started = datetime.now(timezone.utc)
        session = CaptureSession(
            run_id=run_id,manifest_id=uuid4(),instrument_id=job["instrument_id"],
            execution_snapshot_id=job["execution_snapshot_id"],job_id=job["job_id"],
            job_attempt=job["attempt"],fencing_token=job["fencing_token"],
            mode="live_capture",upstream_version="0.3.1",upstream_commit="a" * 40,
            adapter_version="chaos",configuration_hash="b" * 64,started_at=started,
            deadline_at=min(started+timedelta(seconds=20),job["lease_expires_at"]),
        )
        fence = CaptureFence(
            job_id=job["job_id"],worker_id="dead-capture-worker",
            attempt=job["attempt"],fencing_token=job["fencing_token"],
        )
        with connection.transaction():
            start_capture_session(
                connection,session,
                configured_vendors={method: rule.vendors for method, rule in ALLOWED_INGRESS.items()},
                required_sources={method: "missing" for method in ALLOWED_INGRESS},
                worker_id="dead-capture-worker",
            )
        if evaluating:
            with connection.transaction():
                begin_capture_evaluation(connection,session.session_id,fence)
        return job, run_id, session, fence


@pytest.mark.parametrize("checkpoint", ["worker.after_claim", "worker.after_run_creation"])
def test_killed_worker_is_recovered_at_early_boundaries(tmp_path, checkpoint):
    job_id, bot_id = seed_job(with_observation=False)
    kill_worker_at(checkpoint, job_id, bot_id, tmp_path)
    expire(job_id)
    assert recover(bot_id) == 1
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as connection:
        job = connection.execute(
            "SELECT status,last_error FROM analysis_jobs WHERE job_id=%s", (job_id,),
        ).fetchone()
        run = connection.execute(
            "SELECT outcome,error_code FROM analysis_runs WHERE job_id=%s", (job_id,),
        ).fetchone()
        assert job == {"status": "failed", "last_error": "worker_lease_expired"}
        assert run == {"outcome": "abandoned", "error_code": "worker_lease_expired"}


def test_kill_inside_terminal_transaction_rolls_everything_back(tmp_path):
    job_id, bot_id = seed_job(with_observation=True)
    kill_worker_at("worker.during_terminal_transaction", job_id, bot_id, tmp_path)
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as connection:
        assert connection.execute(
            "SELECT count(*) AS n FROM signals WHERE run_id IN "
            "(SELECT run_id FROM analysis_runs WHERE job_id=%s)", (job_id,),
        ).fetchone()["n"] == 0
    expire(job_id)
    assert recover(bot_id) == 1
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as connection:
        assert connection.execute(
            "SELECT status FROM analysis_jobs WHERE job_id=%s", (job_id,),
        ).fetchone()["status"] == "failed"


@pytest.mark.skipif(
    not POSTGRES_CONTAINER, reason="TEST_POSTGRES_CONTAINER is not set",
)
def test_postgres_restart_inside_terminal_transaction_rolls_everything_back(tmp_path):
    """D1: a server restart cannot expose a partially committed terminal state."""
    job_id, bot_id = seed_job(with_observation=True)
    process = pause_worker_at("worker.during_terminal_transaction", bot_id, tmp_path)
    try:
        subprocess.run(
            ["docker", "stop", "--time", "0", POSTGRES_CONTAINER],
            check=True, capture_output=True, text=True,
        )
        subprocess.run(
            ["docker", "start", POSTGRES_CONTAINER],
            check=True, capture_output=True, text=True,
        )
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            ready = subprocess.run(
                ["docker", "exec", POSTGRES_CONTAINER, "pg_isready", "-U", "platform"],
                capture_output=True,
            )
            if ready.returncode == 0:
                break
            time.sleep(0.1)
        else:
            pytest.fail("PostgreSQL did not become ready after restart")
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        subprocess.run(
            ["docker", "start", POSTGRES_CONTAINER], capture_output=True, text=True,
        )

    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as connection:
        state = connection.execute(
            """SELECT job.status,run.outcome,
               (SELECT count(*) FROM signals WHERE run_id=run.run_id) AS signals,
               (SELECT count(*) FROM outbox event JOIN signals signal
                  ON signal.event_id=event.event_id WHERE signal.run_id=run.run_id) AS outbox_events
               FROM analysis_jobs job JOIN analysis_runs run ON run.job_id=job.job_id
               WHERE job.job_id=%s""", (job_id,),
        ).fetchone()
        assert state == {
            "status": "running", "outcome": "running", "signals": 0, "outbox_events": 0,
        }
    expire(job_id)
    assert recover(bot_id) == 1


def test_two_workers_serialize_publication_on_one_stream(tmp_path):
    """D3: concurrent publishers allocate a single gap-free stream order."""
    bot_id = f"chaos-concurrent-{uuid4().hex[:10]}"
    first_job, _ = seed_job(
        with_observation=True, bot_id=bot_id, candle_age_minutes=5,
    )
    second_job, _ = seed_job(
        with_observation=True, clean=False, bot_id=bot_id, candle_age_minutes=6,
    )
    command = (
        "from trading_platform.settings import Settings; "
        "from trading_platform.worker import process_one; "
        "process_one(Settings(), 'concurrent-' + __import__('uuid').uuid4().hex)"
    )
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", command], env=worker_environment(bot_id, tmp_path),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        for _ in range(2)
    ]
    for process in processes:
        stdout, stderr = process.communicate(timeout=20)
        assert process.returncode == 0, f"stdout={stdout!r} stderr={stderr!r}"

    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as connection:
        jobs = connection.execute(
            "SELECT job_id,status FROM analysis_jobs WHERE job_id IN (%s,%s) ORDER BY job_id",
            (first_job, second_job),
        ).fetchall()
        assert {row["status"] for row in jobs} == {"succeeded"}
        stream = connection.execute(
            """SELECT sequence FROM signals
               WHERE environment='test' AND bot_id=%s AND exchange='binance'
                 AND pair='BTC/USDT' AND timeframe='5m' ORDER BY sequence""", (bot_id,),
        ).fetchall()
        assert [row["sequence"] for row in stream] == [1, 2]
        assert connection.execute(
            """SELECT count(*) AS n FROM outbox event JOIN signals signal
               ON signal.event_id=event.event_id WHERE signal.bot_id=%s""", (bot_id,),
        ).fetchone()["n"] == 2


def test_kill_after_terminal_commit_preserves_success(tmp_path):
    job_id, bot_id = seed_job(with_observation=True)
    kill_worker_at("worker.after_terminal_commit", job_id, bot_id, tmp_path)
    assert recover(bot_id) == 0
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as connection:
        state = connection.execute(
            """SELECT job.status,run.outcome,count(signal.signal_id) AS signals,
               count(event.outbox_id) AS outbox_events
               FROM analysis_jobs job JOIN analysis_runs run ON run.job_id=job.job_id
               LEFT JOIN signals signal ON signal.run_id=run.run_id
               LEFT JOIN outbox event ON event.event_id=signal.event_id
               WHERE job.job_id=%s GROUP BY job.status,run.outcome""", (job_id,),
        ).fetchone()
        assert state == {"status": "succeeded", "outcome": "succeeded",
                         "signals": 1, "outbox_events": 1}


def test_two_recovery_sweepers_have_exactly_one_winner(tmp_path):
    job_id, bot_id = seed_job(with_observation=False)
    kill_worker_at("worker.after_claim", job_id, bot_id, tmp_path)
    expire(job_id)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: recover(bot_id), range(2)))
    assert sorted(results) == [0, 1]
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as connection:
        assert connection.execute(
            "SELECT count(*) AS n FROM analysis_runs WHERE job_id=%s", (job_id,),
        ).fetchone()["n"] == 1


@pytest.mark.parametrize(
    "checkpoint", ["worker.after_capture_creation", "worker.after_collection_close"],
)
def test_killed_tradingagents_capture_converges_to_rejected_evidence(tmp_path, checkpoint):
    job_id, bot_id = seed_job(with_observation=False)
    kill_worker_at(checkpoint, job_id, bot_id, tmp_path)
    expire(job_id)
    assert recover(bot_id) == 1
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as connection:
        state = connection.execute(
            """SELECT job.status AS job_status,run.outcome,session.status AS session_status,
               session.rejection_code,manifest.status AS manifest_status
               FROM analysis_jobs job JOIN analysis_runs run ON run.job_id=job.job_id
               JOIN capture_sessions session ON session.run_id=run.run_id
               JOIN evidence_manifests manifest ON manifest.run_id=run.run_id
               WHERE job.job_id=%s""", (job_id,),
        ).fetchone()
        assert state == {
            "job_status": "failed", "outcome": "abandoned",
            "session_status": "abandoned", "rejection_code": "worker_lease_expired",
            "manifest_status": "rejected",
        }


@pytest.mark.parametrize("evaluating", [False, True])
def test_expired_partial_capture_is_closed_before_retry(evaluating):
    job_id, bot_id = seed_job(with_observation=False)
    _, run_id, session, _ = create_partial_capture(job_id, evaluating=evaluating)
    expire(job_id)
    assert recover(bot_id) == 1
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as connection:
        state = connection.execute(
            """SELECT job.status AS job_status,run.outcome,session.status AS session_status,
               session.rejection_code,manifest.status AS manifest_status
               FROM analysis_jobs job JOIN analysis_runs run ON run.job_id=job.job_id
               JOIN capture_sessions session ON session.run_id=run.run_id
               JOIN evidence_manifests manifest ON manifest.run_id=run.run_id
               WHERE job.job_id=%s""", (job_id,),
        ).fetchone()
        assert state == {
            "job_status": "failed", "outcome": "abandoned",
            "session_status": "abandoned", "rejection_code": "worker_lease_expired",
            "manifest_status": "rejected",
        }


def test_recovered_attempt_rejects_resumed_stale_worker(tmp_path):
    job_id, bot_id = seed_job(with_observation=False)
    kill_worker_at("worker.after_run_creation", job_id, bot_id, tmp_path)
    expire(job_id)
    assert recover(bot_id) == 1
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as connection:
        old_run = connection.execute(
            "SELECT run_id FROM analysis_runs WHERE job_id=%s", (job_id,),
        ).fetchone()["run_id"]
        replacement = claim_analysis_job(connection, "replacement-worker", 30)
        assert replacement["job_id"] == job_id
        assert (replacement["attempt"],replacement["fencing_token"]) == (2, 2)
        assert not renew_analysis_job_lease(
            connection,job_id=job_id,worker_id="chaos-worker",attempt=1,
            fencing_token=1,lease_seconds=30,
        )
        assert not fail_analysis_job(
            connection,job_id=job_id,run_id=old_run,error_code="stale",
            error_metadata={},attempt=1,worker_id="chaos-worker",fencing_token=1,
        )
