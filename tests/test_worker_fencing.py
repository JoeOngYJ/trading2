from contextlib import nullcontext
from datetime import datetime, timedelta, timezone

import pytest
from uuid import uuid4

from trading_platform.capture import begin_capture_evaluation
from trading_platform.contracts import CaptureFence, PortfolioRating
from trading_platform.nats_support import SIGNAL_SUBJECT, SIGNAL_SUBJECTS, bridge_consumer_config
from trading_platform.repository import (
    PublicationPolicyError,
    StaleJobLeaseError,
    authorize_signal_publication,
    complete_analysis_without_signal,
    persist_signal_and_outbox,
    recover_expired_analysis_jobs,
    renew_analysis_job_lease,
)
from trading_platform.source_policy_persistence import evaluate_and_finalize_capture


class Result:
    def __init__(self, *, one=None, all_rows=None):
        self.one = one
        self.all_rows = all_rows or []

    def fetchone(self):
        return self.one

    def fetchall(self):
        return self.all_rows


class ScriptedConnection:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []
        self.commits = 0

    def execute(self, query, parameters=None):
        self.calls.append((" ".join(query.split()), parameters))
        if self.results:
            return self.results.pop(0)
        return Result()

    def transaction(self):
        return nullcontext()

    def commit(self):
        self.commits += 1


def synthetic_gate_row(envelope):
    payload = envelope.payload
    return {
        "capture_session_id": None,
        "run_manifest_id": payload.evidence_manifest_id,
        "run_configuration": {"research_mode": "synthetic"},
        "manifest_status": "sealed",
        "manifest_instrument_id": payload.instrument_id,
        "manifest_snapshot_id": payload.execution_snapshot_id,
        "collection_completed_at": payload.analysis_completed_at,
        "manifest_policy_digest": None,
        "manifest_quality_flags": ["synthetic"],
        "capture_status": None,
        "verdict": None,
        "permitted_ratings": None,
        "data_as_of": None,
        "policy_quality_flags": None,
        "evaluation_result_digest": None,
        "snapshot_exchange": payload.exchange,
        "snapshot_pair": payload.pair,
        "snapshot_timeframe": payload.timeframe,
        "snapshot_candle_close_at": payload.candle_close_at,
    }


def captured_gate_row(envelope, *, verdict="pass", permitted_ratings=None, digest=None):
    payload = envelope.payload
    digest = digest or payload.source_policy_result_digest
    return {
        **synthetic_gate_row(envelope),
        "capture_session_id": uuid4(),
        "run_configuration": {"research_mode": "tradingagents"},
        "manifest_quality_flags": [],
        "manifest_policy_digest": digest,
        "capture_status": "sealed",
        "verdict": verdict,
        "permitted_ratings": permitted_ratings or [rating.value for rating in PortfolioRating],
        "data_as_of": payload.provenance.data_as_of,
        "policy_quality_flags": [],
        "evaluation_result_digest": digest,
    }


def test_transport_uses_one_v2_subject_constant():
    config = bridge_consumer_config("bridge-test", ack_wait_seconds=30, max_deliver=5)
    assert SIGNAL_SUBJECT == "signals.v2.>"
    assert SIGNAL_SUBJECTS == [SIGNAL_SUBJECT]
    assert config.filter_subject == SIGNAL_SUBJECT


@pytest.mark.parametrize(("result", "expected"), [({"job_id": "job"}, True), (None, False)])
def test_lease_renewal_is_fenced(result, expected):
    connection = ScriptedConnection([Result(one=result)])
    renewed = renew_analysis_job_lease(
        connection,
        job_id="job",
        worker_id="worker-a",
        attempt=3,
        fencing_token=8,
        lease_seconds=900,
    )
    assert renewed is expected
    query, parameters = connection.calls[0]
    assert "lease_owner=%s" in query
    assert "attempt=%s" in query
    assert "fencing_token=%s" in query
    assert "lease_expires_at > now()" in query
    assert parameters == (900, "job", "worker-a", 3, 8)
    assert connection.commits == 1


def test_stale_attempt_cannot_allocate_sequence_or_publish(signal_factory):
    envelope = signal_factory()
    connection = ScriptedConnection([Result(one=None)])
    with pytest.raises(StaleJobLeaseError, match="no longer owns"):
        persist_signal_and_outbox(
            connection,
            envelope,
            {
                "job_id": "job",
                "worker_id": "stale-worker",
                "attempt": 1,
                "fencing_token": 2,
                "hmac_secret": "a-reliable-test-secret-that-is-longer-than-32-bytes",
                "configuration": {},
            },
        )
    assert len(connection.calls) == 1
    query, parameters = connection.calls[0]
    assert "FOR UPDATE" in query
    assert parameters == ("job", "stale-worker", 1, 2)


def test_revocation_cannot_enter_created_signal_persistence_path(revocation_factory):
    connection = ScriptedConnection([])
    with pytest.raises(PublicationPolicyError) as caught:
        persist_signal_and_outbox(
            connection,
            revocation_factory(),
            {"job_id": "job", "worker_id": "worker-a", "attempt": 1,
             "fencing_token": 1, "hmac_secret": "unused"},
        )
    assert caught.value.code == "publication.event_type_invalid"
    assert connection.calls == []


def test_expired_lease_recovery_tombstones_before_retrying_job():
    now = datetime.now(timezone.utc)
    job_id, run_id, signal_id = uuid4(), uuid4(), uuid4()
    row = {
        "job_id": job_id, "attempt": 2, "fencing_token": 7, "max_attempts": 4,
        "correlation_id": uuid4(), "instrument_id": "crypto:binance:spot:BTC-USDT",
        "execution_snapshot_id": uuid4(), "pair": "BTC/USDT", "timeframe": "5m",
        "run_id": run_id, "evidence_manifest_id": None, "capture_session_id": None,
        "producer_version": "test", "code_revision": "revision", "exchange": "binance",
    }
    connection = ScriptedConnection([
        Result(all_rows=[row]),
        Result(one={"last_sequence": 1}),
        Result(one={"kind": "created", "signal_id": signal_id, "sequence": 1,
                    "checksum": "a" * 64, "expires_at": now + timedelta(minutes=5),
                    "rating": PortfolioRating.BUY.value}),
        Result(one={"last_sequence": 2}), Result(), Result(), Result(), Result(),
    ])

    recovered = recover_expired_analysis_jobs(connection, {
        "environment": "production", "bot_id": "freqtrade-primary",
        "hmac_secret": "a-reliable-test-secret-that-is-longer-than-32-bytes",
        "producer_version": "test", "code_revision": "revision",
    })

    assert recovered == 1
    queries = [query for query, _ in connection.calls]
    revocation_index = next(i for i, query in enumerate(queries)
                            if "INSERT INTO signal_revocations" in query)
    run_index = next(i for i, query in enumerate(queries) if "UPDATE analysis_runs" in query)
    job_index = next(i for i, query in enumerate(queries) if "UPDATE analysis_jobs" in query)
    assert revocation_index < run_index < job_index
    outbox_query, outbox_parameters = next(
        call for call in connection.calls if "INSERT INTO outbox" in call[0]
    )
    assert outbox_query
    assert outbox_parameters[2].obj["payload"]["reason_code"] == "worker_lease_expired"
    assert outbox_parameters[2].obj["payload"]["evidence_manifest_id"] is None


def test_expired_claim_without_run_gets_auditable_recovery_run():
    row = {
        "job_id": uuid4(), "attempt": 1, "fencing_token": 1, "max_attempts": 3,
        "correlation_id": uuid4(), "instrument_id": "crypto:binance:spot:BTC-USDT",
        "execution_snapshot_id": uuid4(), "pair": "BTC/USDT", "timeframe": "5m",
        "run_id": None, "evidence_manifest_id": None, "capture_session_id": None,
        "producer_version": None, "code_revision": None, "exchange": "binance",
    }
    connection = ScriptedConnection([
        Result(all_rows=[row]), Result(), Result(one=None), Result(), Result(),
    ])
    assert recover_expired_analysis_jobs(connection, {
        "environment": "production", "bot_id": "freqtrade-primary",
        "hmac_secret": "a-reliable-test-secret-that-is-longer-than-32-bytes",
        "producer_version": "test", "code_revision": "revision",
    }) == 1
    queries = [query for query, _ in connection.calls]
    create_index = next(i for i, query in enumerate(queries)
                        if "INSERT INTO analysis_runs" in query)
    abandon_index = next(i for i, query in enumerate(queries)
                         if "UPDATE analysis_runs" in query)
    assert create_index < abandon_index


def test_expired_mid_capture_closes_evidence_before_revocation_attempt():
    row = {
        "job_id": uuid4(), "attempt": 2, "fencing_token": 3, "max_attempts": 3,
        "correlation_id": uuid4(), "instrument_id": "crypto:binance:spot:BTC-USDT",
        "execution_snapshot_id": uuid4(), "pair": "BTC/USDT", "timeframe": "5m",
        "run_id": uuid4(), "evidence_manifest_id": uuid4(),
        "capture_session_id": uuid4(), "producer_version": "test",
        "code_revision": "revision", "exchange": "binance",
    }
    connection = ScriptedConnection([
        Result(all_rows=[row]), Result(), Result(), Result(one=None), Result(), Result(),
    ])
    assert recover_expired_analysis_jobs(connection, {
        "environment": "production", "bot_id": "freqtrade-primary",
        "hmac_secret": "a-reliable-test-secret-that-is-longer-than-32-bytes",
        "producer_version": "test", "code_revision": "revision",
    }) == 1
    queries = [query for query, _ in connection.calls]
    manifest_index = next(i for i, query in enumerate(queries)
                          if "UPDATE evidence_manifests" in query)
    session_index = next(i for i, query in enumerate(queries)
                         if "UPDATE capture_sessions" in query)
    sequence_index = next(i for i, query in enumerate(queries)
                          if "SELECT last_sequence" in query)
    assert manifest_index < session_index < sequence_index


def test_policy_rejection_terminally_consumes_owned_job_without_signal():
    connection = ScriptedConnection([
        Result(one={"job_id": "job"}),
        Result(one={"run_id": "run"}),
        Result(one={"job_id": "job"}),
    ])
    digest = "sha256:" + "a" * 64
    complete_analysis_without_signal(
        connection,
        job_id="job",
        run_id="run",
        worker_id="worker-a",
        attempt=2,
        fencing_token=4,
        outcome_code="source.required.get_stock_data",
        policy_result_digest=digest,
    )
    queries = [query for query, _ in connection.calls]
    assert "FOR UPDATE OF job,run" in queries[0]
    assert "outcome='rejected'" in queries[1]
    assert "status='succeeded'" in queries[2]
    assert not any("INSERT INTO signals" in query for query in queries)
    assert not any("INSERT INTO outbox" in query for query in queries)


def test_policy_rejection_revokes_latest_actionable_signal_in_same_transaction():
    target_signal_id = uuid4()
    connection = ScriptedConnection([
        Result(one={"job_id": "job"}),
        Result(one={"last_sequence": 3}),
        Result(one={
            "kind": "created",
            "signal_id": target_signal_id,
            "sequence": 3,
            "checksum": "a" * 64,
            "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
            "rating": "Buy",
        }),
        Result(one={"last_sequence": 4}),
        Result(),
        Result(),
        Result(one={"run_id": "run"}),
        Result(one={"job_id": "job"}),
    ])
    digest = "sha256:" + "b" * 64
    envelope = complete_analysis_without_signal(
        connection,
        job_id="job",
        run_id=uuid4(),
        worker_id="worker-a",
        attempt=2,
        fencing_token=4,
        outcome_code="execution_snapshot.invalid",
        policy_result_digest=digest,
        denied_rating=PortfolioRating.BUY,
        revocation_context={
            "environment": "production",
            "bot_id": "freqtrade-primary",
            "exchange": "binance",
            "pair": "BTC/USDT",
            "timeframe": "5m",
            "correlation_id": uuid4(),
            "instrument_id": "crypto:binance:spot:BTC-USDT",
            "execution_snapshot_id": uuid4(),
            "evidence_manifest_id": uuid4(),
            "producer_version": "test",
            "code_revision": "test",
            "hmac_secret": "a-reliable-test-secret-that-is-longer-than-32-bytes",
        },
    )
    assert envelope is not None
    assert envelope.payload.event_type == "signal.revoked"
    assert envelope.payload.signal_id == target_signal_id
    assert envelope.payload.sequence == 4
    queries = [query for query, _ in connection.calls]
    assert any("INSERT INTO signal_revocations" in query for query in queries)
    assert any("INSERT INTO outbox" in query for query in queries)
    assert not any("INSERT INTO signals(" in query for query in queries)


def test_stale_attempt_cannot_terminally_consume_policy_rejection():
    connection = ScriptedConnection([Result(one=None)])
    with pytest.raises(StaleJobLeaseError, match="no longer owns"):
        complete_analysis_without_signal(
            connection,
            job_id="job",
            run_id="run",
            worker_id="stale-worker",
            attempt=1,
            fencing_token=2,
            outcome_code="publication.rating_not_permitted",
        )
    assert len(connection.calls) == 1


def test_stale_attempt_cannot_close_capture_collection():
    session_id = uuid4()
    job_id = uuid4()
    connection = ScriptedConnection([Result(one=None)])
    with pytest.raises(StaleJobLeaseError, match="capture attempt"):
        begin_capture_evaluation(
            connection,
            session_id,
            CaptureFence(
                job_id=job_id, worker_id="stale-worker", attempt=1, fencing_token=2
            ),
        )
    assert len(connection.calls) == 1
    query, parameters = connection.calls[0]
    assert "job.lease_owner=%s" in query
    assert "job.lease_expires_at>now()" in query
    assert "run.capture_session_id=session.session_id" in query
    assert parameters == (session_id, job_id, 1, 2, "stale-worker")


def test_stale_attempt_cannot_load_or_persist_source_policy(tmp_path):
    session_id = uuid4()
    job_id = uuid4()
    connection = ScriptedConnection([Result(one=None)])
    with pytest.raises(StaleJobLeaseError, match="capture attempt"):
        evaluate_and_finalize_capture(
            connection,
            session_id,
            CaptureFence(
                job_id=job_id, worker_id="stale-worker", attempt=1, fencing_token=2
            ),
            tmp_path,
        )
    assert len(connection.calls) == 1
    assert "FOR UPDATE OF session,manifest,run,job" in connection.calls[0][0]


def test_owned_attempt_updates_existing_run_before_signal_publish(signal_factory):
    envelope = signal_factory()
    connection = ScriptedConnection(
        [
            Result(one={"job_id": "job"}),
            Result(one=synthetic_gate_row(envelope)),
            Result(one={"last_sequence": 7}),
            Result(one={"run_id": str(envelope.payload.run_id)}),
        ]
    )
    persisted = persist_signal_and_outbox(
        connection,
        envelope,
        {
            "job_id": "job",
            "worker_id": "worker-a",
            "attempt": 2,
            "fencing_token": 4,
            "hmac_secret": "a-reliable-test-secret-that-is-longer-than-32-bytes",
            "configuration": {"mode": "synthetic"},
        },
    )
    assert persisted.payload.sequence == 7
    queries = [query for query, _ in connection.calls]
    assert "UPDATE analysis_runs" in queries[3]
    assert any("INSERT INTO signals" in query for query in queries)
    assert any("INSERT INTO outbox" in query for query in queries)


def test_pass_policy_authorizes_original_rating(signal_factory):
    digest = "sha256:" + "a" * 64
    envelope = signal_factory(rating=PortfolioRating.BUY)
    envelope.payload.source_policy_result_digest = digest
    connection = ScriptedConnection([Result(one=captured_gate_row(envelope))])
    authorize_signal_publication(
        connection, envelope,
        {"job_id": "job", "attempt": 2, "fencing_token": 4},
    )
    assert envelope.payload.decision.rating == PortfolioRating.BUY


def test_hold_only_policy_accepts_hold_without_transforming_it(signal_factory):
    digest = "sha256:" + "b" * 64
    envelope = signal_factory(rating=PortfolioRating.HOLD)
    envelope.payload.source_policy_result_digest = digest
    connection = ScriptedConnection([Result(one=captured_gate_row(
        envelope, verdict="hold_only", permitted_ratings=["Hold"]
    ))])
    authorize_signal_publication(
        connection, envelope,
        {"job_id": "job", "attempt": 2, "fencing_token": 4},
    )
    assert envelope.payload.decision.rating == PortfolioRating.HOLD


def test_hold_only_policy_rejects_actionable_rating_before_sequence(signal_factory):
    digest = "sha256:" + "c" * 64
    envelope = signal_factory(rating=PortfolioRating.BUY)
    envelope.payload.source_policy_result_digest = digest
    connection = ScriptedConnection([
        Result(one={"job_id": "job"}),
        Result(one=captured_gate_row(
            envelope, verdict="hold_only", permitted_ratings=["Hold"]
        )),
    ])
    with pytest.raises(PublicationPolicyError) as caught:
        persist_signal_and_outbox(
            connection, envelope,
            {
                "job_id": "job", "worker_id": "worker-a", "attempt": 2,
                "fencing_token": 4,
                "hmac_secret": "a-reliable-test-secret-that-is-longer-than-32-bytes",
                "configuration": {},
            },
        )
    assert caught.value.code == "publication.rating_not_permitted"
    assert not any("signal_sequences" in query for query, _ in connection.calls)
    assert envelope.payload.decision.rating == PortfolioRating.BUY


def test_policy_digest_mismatch_rejects(signal_factory):
    envelope = signal_factory()
    envelope.payload.source_policy_result_digest = "sha256:" + "d" * 64
    connection = ScriptedConnection([Result(one=captured_gate_row(
        envelope, digest="sha256:" + "e" * 64
    ))])
    with pytest.raises(PublicationPolicyError) as caught:
        authorize_signal_publication(
            connection, envelope,
            {"job_id": "job", "attempt": 2, "fencing_token": 4},
        )
    assert caught.value.code == "publication.policy_binding_invalid"


def test_policy_data_as_of_mismatch_rejects(signal_factory):
    digest = "sha256:" + "f" * 64
    envelope = signal_factory()
    envelope.payload.source_policy_result_digest = digest
    row = captured_gate_row(envelope)
    row["data_as_of"] = envelope.payload.provenance.data_as_of.replace(year=2025)
    connection = ScriptedConnection([Result(one=row)])
    with pytest.raises(PublicationPolicyError) as caught:
        authorize_signal_publication(
            connection, envelope,
            {"job_id": "job", "attempt": 2, "fencing_token": 4},
        )
    assert caught.value.code == "publication.data_as_of_mismatch"


def test_policy_quality_flags_must_survive_into_signed_provenance(signal_factory):
    digest = "sha256:" + "1" * 64
    envelope = signal_factory()
    envelope.payload.source_policy_result_digest = digest
    row = captured_gate_row(envelope)
    row["policy_quality_flags"] = ["get_news.degraded"]
    connection = ScriptedConnection([Result(one=row)])
    with pytest.raises(PublicationPolicyError) as caught:
        authorize_signal_publication(
            connection, envelope,
            {"job_id": "job", "attempt": 2, "fencing_token": 4},
        )
    assert caught.value.code == "publication.quality_flags_missing"
