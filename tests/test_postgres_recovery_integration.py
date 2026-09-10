import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import psycopg
import pytest
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from trading_platform.contracts import (
    PortfolioDecision, PortfolioRating, Provenance, RATING_SCORE, SentimentReport,
    SignalPayload, SignedEnvelope,
)
from trading_platform.repository import recover_expired_analysis_jobs
from trading_platform.bridge import materialize
from trading_platform.outbox import claim_pending


DATABASE_URL = os.getenv("TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="TEST_POSTGRES_URL is not set")


def test_expired_pre_capture_attempt_atomically_revokes_latest_signal():
    # Preserve microseconds so the snapshot's natural key also remains unique when this
    # persistent-database test is repeated many times per second.
    now = datetime.now(timezone.utc)
    snapshot_id, old_job_id, old_run_id, manifest_id = (uuid4() for _ in range(4))
    new_job_id, correlation_id = uuid4(), uuid4()
    raw_digest = "sha256:" + uuid4().hex * 2
    secret = "a-reliable-test-secret-that-is-longer-than-32-bytes"
    instrument = "crypto:binance:spot:BTC-USDT"
    bot_id = f"recovery-{uuid4().hex[:10]}"
    research_symbol = f"BTC-USD-{uuid4().hex}"
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as connection:
        connection.execute(
            """UPDATE analysis_jobs SET status='dead',lease_owner=NULL,lease_expires_at=NULL,
               last_error='recovery_fixture_superseded'
               WHERE status IN ('pending','failed','running')"""
        )
        connection.execute(
            "INSERT INTO artifacts(digest,media_type,byte_length,storage_path) "
            "VALUES (%s,'application/json',2,%s)", (raw_digest, f"test/{snapshot_id}"),
        )
        connection.execute(
            """INSERT INTO execution_market_snapshots(
              snapshot_id,instrument_id,exchange,pair,market_type,timeframe,candle_type,
              candle_open_at,candle_close_at,open_price,high_price,low_price,close_price,
              volume,retrieved_at,exchange_time_at,clock_offset_ms,is_closed,has_gap,
              collector_version,raw_artifact_digest)
              VALUES (%s,%s,'binance','BTC/USDT','spot','5m','spot',%s,%s,
                      1,2,1,2,10,%s,%s,0,true,false,'test',%s)""",
            (snapshot_id, instrument, now-timedelta(minutes=10), now-timedelta(minutes=5),
             now-timedelta(minutes=4), now-timedelta(minutes=4), raw_digest),
        )
        connection.execute(
            """INSERT INTO analysis_jobs(job_id,correlation_id,symbol,pair,timeframe,
              candle_close_at,status,attempt,fencing_token,instrument_id,execution_snapshot_id)
              VALUES (%s,%s,%s,'BTC/USDT','5m',%s,'succeeded',1,1,%s,%s)""",
            (old_job_id, uuid4(), research_symbol, now-timedelta(minutes=5),
             instrument, snapshot_id),
        )
        connection.execute(
            """INSERT INTO analysis_runs(run_id,job_id,started_at,completed_at,
              producer_version,code_revision,configuration,outcome,attempt,fencing_token)
              VALUES (%s,%s,%s,%s,'test','revision','{"research_mode":"synthetic"}',
                      'succeeded',1,1)""",
            (old_run_id, old_job_id, now-timedelta(minutes=4), now-timedelta(minutes=3)),
        )
        connection.execute(
            """INSERT INTO evidence_manifests(manifest_id,run_id,instrument_id,
              execution_snapshot_id,mode,status,collection_started_at,collection_completed_at,
              configured_vendors,replay_safe,quality_flags,digest)
              VALUES (%s,%s,%s,%s,'live','sealed',%s,%s,'{}',false,'["synthetic"]',%s)""",
            (manifest_id, old_run_id, instrument, snapshot_id, now-timedelta(minutes=4),
             now-timedelta(minutes=3), "sha256:" + "2" * 64),
        )
        connection.execute(
            "UPDATE analysis_runs SET evidence_manifest_id=%s WHERE run_id=%s",
            (manifest_id, old_run_id),
        )
        payload = SignalPayload(
            run_id=old_run_id, correlation_id=uuid4(), instrument_id=instrument,
            execution_snapshot_id=snapshot_id, evidence_manifest_id=manifest_id,
            environment="production", bot_id=bot_id, exchange="binance",
            pair="BTC/USDT", timeframe="5m", sequence=1,
            candle_close_at=now-timedelta(minutes=5),
            analysis_started_at=now-timedelta(minutes=4),
            analysis_completed_at=now-timedelta(minutes=3), published_at=now-timedelta(minutes=2),
            signal_available_at=now-timedelta(minutes=2), expires_at=now+timedelta(minutes=20),
            decision=PortfolioDecision(rating=PortfolioRating.BUY,
              executive_summary="Test", investment_thesis="Test"),
            sentiment=SentimentReport(overall_band="Neutral",overall_score=5,
              confidence="low",narrative="Test"),
            normalized_rating_score=RATING_SCORE[PortfolioRating.BUY],
            provenance=Provenance(producer_version="test",code_revision="revision",
              llm_provider="synthetic",deep_model="test",quick_model="test",
              configuration_hash="0"*64,data_as_of=now-timedelta(minutes=5)),
        )
        envelope = SignedEnvelope.sign(payload, secret)
        connection.execute(
            """INSERT INTO signals(signal_id,event_id,run_id,correlation_id,environment,
              bot_id,exchange,pair,timeframe,sequence,status,published_at,expires_at,envelope,
              checksum,instrument_id,execution_snapshot_id,evidence_manifest_id,signal_available_at)
              VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,1,'valid',%s,%s,%s,%s,%s,%s,%s,%s)""",
            (payload.signal_id,payload.event_id,payload.run_id,payload.correlation_id,
             payload.environment,payload.bot_id,payload.exchange,payload.pair,payload.timeframe,
             payload.published_at,payload.expires_at,Jsonb(envelope.model_dump(mode="json")),
             envelope.checksum,instrument,snapshot_id,manifest_id,payload.signal_available_at),
        )
        connection.execute(
            "INSERT INTO signal_sequences VALUES ('production',%s,"
            "'binance','BTC/USDT','5m',1)", (bot_id,),
        )
        connection.execute(
            """INSERT INTO analysis_jobs(job_id,correlation_id,symbol,pair,timeframe,
              candle_close_at,status,attempt,fencing_token,max_attempts,lease_owner,
              lease_expires_at,instrument_id,execution_snapshot_id)
              VALUES (%s,%s,%s,'BTC/USDT','5m',%s,'running',1,1,3,'dead-worker',
                      %s,%s,%s)""",
            (new_job_id, correlation_id, research_symbol, now, now-timedelta(seconds=1),
             instrument, snapshot_id),
        )
        connection.commit()

        assert recover_expired_analysis_jobs(connection, {
            "environment": "production", "bot_id": bot_id, "hmac_secret": secret,
            "producer_version": "test", "code_revision": "revision",
        }) == 1
        revocation = connection.execute(
            """SELECT reason_code,evidence_manifest_id,sequence FROM signal_revocations
               WHERE bot_id=%s""", (bot_id,),
        ).fetchone()
        assert revocation == {"reason_code": "worker_lease_expired",
                              "evidence_manifest_id": None, "sequence": 2}
        assert connection.execute(
            """SELECT count(*) AS n FROM outbox event JOIN signal_revocations revocation
               ON revocation.event_id=event.event_id WHERE revocation.bot_id=%s""", (bot_id,),
        ).fetchone()["n"] == 1
        assert connection.execute(
            "SELECT status FROM analysis_jobs WHERE job_id=%s", (new_job_id,)
        ).fetchone()["status"] == "failed"
        recovery_run = connection.execute(
            "SELECT outcome,configuration FROM analysis_runs WHERE job_id=%s", (new_job_id,)
        ).fetchone()
        assert recovery_run["outcome"] == "abandoned"
        assert recovery_run["configuration"]["research_mode"] == "lease_recovery"


def test_concurrent_bridge_delivery_converges_to_highest_sequence(tmp_path, signal_factory):
    bot_id = f"bridge-concurrent-{uuid4().hex[:10]}"
    class BridgeSettings:
        database_url = DATABASE_URL
        hmac_secret = "a-reliable-test-secret-that-is-longer-than-32-bytes"
        environment = "production"
        exchange = "binance"
        timeframe = "5m"
        clock_skew_seconds = 30
        snapshot_dir = tmp_path

    BridgeSettings.bot_id = bot_id
    secret = "a-reliable-test-secret-that-is-longer-than-32-bytes"
    first_seed = signal_factory(sequence=1)
    second_seed = signal_factory(sequence=2)
    first = SignedEnvelope.sign(first_seed.payload.model_copy(update={"bot_id": bot_id}), secret)
    second = SignedEnvelope.sign(second_seed.payload.model_copy(update={"bot_id": bot_id}), secret)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda event: materialize(event, BridgeSettings()),
                                    (second, first)))

    assert sorted(result[0] for result in results) in (
        ["materialized", "materialized"], ["materialized", "stale"],
    )
    from trading_platform.atomic_snapshot import read_snapshot
    assert read_snapshot(tmp_path, "BTC/USDT", "5m").payload.sequence == 2
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as connection:
        cursor = connection.execute(
            """SELECT sequence,event_id FROM materialization_cursors
               WHERE bot_id=%s AND pair='BTC/USDT'""", (bot_id,),
        ).fetchone()
        assert cursor == {"sequence": 2, "event_id": second.payload.event_id}


def test_postgres_rejects_cursor_regression_and_same_sequence_forgery():
    """D2: the database independently enforces cursor order and identity."""
    consumer_id = f"cursor-{uuid4()}"
    event_id, signal_id = uuid4(), uuid4()
    route = (consumer_id, "test", f"bot-{uuid4()}", "binance", "BTC/USDT", "5m")
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            """INSERT INTO materialization_cursors(
               consumer_id,environment,bot_id,exchange,pair,timeframe,sequence,event_id,
               signal_id,checksum,disposition)
               VALUES (%s,%s,%s,%s,%s,%s,2,%s,%s,%s,'materialized')""",
            (*route, event_id, signal_id, "a" * 64),
        )
        connection.commit()

    with psycopg.connect(DATABASE_URL) as connection:
        with pytest.raises(psycopg.errors.RaiseException, match="sequence cannot decrease"):
            connection.execute(
                "UPDATE materialization_cursors SET sequence=1 WHERE consumer_id=%s",
                (consumer_id,),
            )

    with psycopg.connect(DATABASE_URL) as connection:
        with pytest.raises(psycopg.errors.RaiseException, match="identity cannot change"):
            connection.execute(
                "UPDATE materialization_cursors SET event_id=%s WHERE consumer_id=%s",
                (uuid4(), consumer_id),
            )


def test_concurrent_outbox_relays_claim_disjoint_batches_and_expired_claim_recovers():
    prefix = f"test.claim.{uuid4()}"
    expected = {uuid4() for _ in range(20)}
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as connection:
        connection.execute(
            """UPDATE outbox SET published_at=now(),claim_owner=NULL,claim_token=NULL,
               claim_expires_at=NULL WHERE published_at IS NULL"""
        )
        with connection.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO outbox(event_id,subject,payload) VALUES (%s,%s,'{}')",
                [(event_id, prefix) for event_id in expected],
            )
        connection.commit()

    settings = type("OutboxSettings", (), {
        "outbox_batch_size": 10, "outbox_claim_seconds": 60,
    })()

    def claim(relay_id):
        with psycopg.connect(DATABASE_URL, row_factory=dict_row) as connection:
            return claim_pending(connection, settings, relay_id)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first, second = list(executor.map(claim, ("relay-a", "relay-b")))
    first_ids = {row["event_id"] for row in first}
    second_ids = {row["event_id"] for row in second}
    assert len(first_ids) == len(second_ids) == 10
    assert first_ids.isdisjoint(second_ids)
    assert first_ids | second_ids == expected

    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as connection:
        connection.execute(
            "UPDATE outbox SET claim_expires_at=now()-interval '1 second' "
            "WHERE claim_owner='relay-a' AND subject=%s", (prefix,),
        )
        connection.commit()
    recovered = claim("relay-c")
    assert {row["event_id"] for row in recovered} == first_ids
