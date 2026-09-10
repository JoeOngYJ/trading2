from __future__ import annotations

import random
import re
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.types.json import Jsonb

from .contracts import (
    ExecutionEvent,
    PortfolioRating,
    SignalPayload,
    SignalRevocationPayload,
    SignedEnvelope,
)
from .fault_injection import checkpoint


class StaleJobLeaseError(RuntimeError):
    """The worker no longer owns the attempt and must not mutate or publish it."""


class PublicationPolicyError(RuntimeError):
    """A stable fail-closed denial at the signal publication boundary."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def claim_analysis_job(connection: Connection, worker_id: str, lease_seconds: int = 900) -> dict[str, Any] | None:
    with connection.transaction():
        row = connection.execute(
            """
            SELECT * FROM analysis_jobs
            WHERE status IN ('pending', 'failed')
              AND available_at <= now()
              AND attempt < max_attempts
            ORDER BY available_at, created_at
            FOR UPDATE SKIP LOCKED
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            return None
        return connection.execute(
            """
            UPDATE analysis_jobs
            SET status = 'running', attempt = attempt + 1,
                fencing_token = fencing_token + 1, lease_owner = %s,
                lease_expires_at = now() + make_interval(secs => %s), updated_at = now()
            WHERE job_id = %s
            RETURNING *
            """,
            (worker_id, lease_seconds, row["job_id"]),
        ).fetchone()


def create_analysis_attempt(
    connection: Connection,
    *,
    run_id: UUID,
    job: dict[str, Any],
    started_at: datetime,
    producer_version: str,
    code_revision: str,
    configuration: dict[str, Any],
) -> None:
    """Create the durable running record before research performs external work."""
    connection.execute(
        """
        INSERT INTO analysis_runs(
            run_id,job_id,started_at,producer_version,code_revision,configuration,
            outcome,attempt,fencing_token
        ) VALUES (%s,%s,%s,%s,%s,%s,'running',%s,%s)
        """,
        (
            run_id,
            job["job_id"],
            started_at,
            producer_version,
            code_revision,
            Jsonb(configuration),
            job["attempt"],
            job["fencing_token"],
        ),
    )
    connection.commit()


def renew_analysis_job_lease(
    connection: Connection,
    *,
    job_id: UUID,
    worker_id: str,
    attempt: int,
    fencing_token: int,
    lease_seconds: int,
) -> bool:
    """Renew only a live lease owned by this exact fenced attempt."""
    row = connection.execute(
        """
        UPDATE analysis_jobs
        SET lease_expires_at=now() + make_interval(secs => %s), updated_at=now()
        WHERE job_id=%s AND status='running' AND lease_owner=%s
          AND attempt=%s AND fencing_token=%s AND lease_expires_at > now()
        RETURNING job_id
        """,
        (lease_seconds, job_id, worker_id, attempt, fencing_token),
    ).fetchone()
    connection.commit()
    return row is not None


def recover_expired_analysis_jobs(
    connection: Connection,
    revocation_defaults: dict[str, Any] | None = None,
    limit: int = 100,
) -> int:
    """Atomically tombstone actionable state before retrying an expired attempt."""
    recovered = 0
    with connection.transaction():
        rows = connection.execute(
            """
            SELECT job.job_id,job.attempt,job.fencing_token,job.max_attempts,
                   job.correlation_id,job.instrument_id,job.execution_snapshot_id,
                   job.pair,job.timeframe,run.run_id,run.evidence_manifest_id,
                   run.capture_session_id,run.producer_version,run.code_revision,
                   snapshot.exchange
            FROM analysis_jobs AS job
            LEFT JOIN analysis_runs AS run ON run.job_id=job.job_id
              AND run.attempt=job.attempt AND run.fencing_token=job.fencing_token
              AND run.outcome='running'
            JOIN execution_market_snapshots AS snapshot
              ON snapshot.snapshot_id=job.execution_snapshot_id
            WHERE job.status='running' AND job.lease_expires_at < now()
            ORDER BY job.lease_expires_at,job.created_at
            FOR UPDATE OF job SKIP LOCKED
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        for row in rows:
            run_id = row["run_id"]
            producer_version = row["producer_version"]
            code_revision = row["code_revision"]
            if run_id is None and revocation_defaults is not None:
                run_id = uuid4()
                producer_version = revocation_defaults["producer_version"]
                code_revision = revocation_defaults["code_revision"]
                connection.execute(
                    """
                    INSERT INTO analysis_runs(
                        run_id,job_id,started_at,producer_version,code_revision,
                        configuration,outcome,attempt,fencing_token
                    ) VALUES (%s,%s,now(),%s,%s,%s,'running',%s,%s)
                    """,
                    (
                        run_id,row["job_id"],producer_version,code_revision,
                        Jsonb({"research_mode": "lease_recovery",
                               "recovery_reason": "worker_lease_expired"}),
                        row["attempt"],row["fencing_token"],
                    ),
                )
            if row["evidence_manifest_id"] is not None:
                recovery_digest = "sha256:" + hashlib.sha256(
                    f"{row['evidence_manifest_id']}:worker_lease_expired".encode()
                ).hexdigest()
                connection.execute(
                    """
                    UPDATE evidence_manifests
                    SET status='rejected',collection_completed_at=now(),replay_safe=false,
                        quality_flags=quality_flags || '["worker_lease_expired"]'::jsonb,
                        digest=%s
                    WHERE manifest_id=%s AND run_id=%s AND status='collecting'
                    """,
                    (recovery_digest, row["evidence_manifest_id"], run_id),
                )
                connection.execute(
                    """
                    UPDATE capture_sessions
                    SET status='abandoned',completed_at=now(),
                        collection_closed_at=COALESCE(collection_closed_at,LEAST(deadline_at,now())),
                        rejection_code='worker_lease_expired'
                    WHERE session_id=%s AND run_id=%s AND status IN ('collecting','evaluating')
                    """,
                    (row["capture_session_id"], run_id),
                )
            if revocation_defaults is not None and run_id is not None:
                _persist_revocation_if_actionable(
                    connection,
                    run_id=run_id,
                    reason_code="worker_lease_expired",
                    policy_result_digest=None,
                    denied_rating=None,
                    context={
                        **revocation_defaults,
                        "exchange": row["exchange"],
                        "pair": row["pair"],
                        "timeframe": row["timeframe"],
                        "correlation_id": row["correlation_id"],
                        "instrument_id": row["instrument_id"],
                        "execution_snapshot_id": row["execution_snapshot_id"],
                        "evidence_manifest_id": row["evidence_manifest_id"],
                        "producer_version": producer_version,
                        "code_revision": code_revision,
                    },
                )
            connection.execute(
                """
                UPDATE analysis_runs
                SET outcome='abandoned',completed_at=now(),error_code='worker_lease_expired',
                    error_metadata='{}'::jsonb
                WHERE job_id=%s AND attempt=%s AND fencing_token=%s AND outcome='running'
                """,
                (row["job_id"], row["attempt"], row["fencing_token"]),
            )
            connection.execute(
                """
                UPDATE analysis_jobs
                SET status=CASE WHEN attempt >= max_attempts THEN 'dead' ELSE 'failed' END,
                    available_at=now(),last_error='worker_lease_expired',lease_owner=NULL,
                    lease_expires_at=NULL,updated_at=now()
                WHERE job_id=%s AND status='running' AND attempt=%s AND fencing_token=%s
                """,
                (row["job_id"], row["attempt"], row["fencing_token"]),
            )
            recovered += 1
    return recovered


def fail_analysis_job(
    connection: Connection,
    *,
    job_id: UUID,
    run_id: UUID,
    error_code: str,
    error_metadata: dict[str, Any],
    attempt: int,
    worker_id: str,
    fencing_token: int,
    revocation_context: dict[str, Any] | None = None,
) -> bool:
    delay = min(900, (2 ** max(0, attempt - 1)) * 15) + random.randint(0, 10)
    with connection.transaction():
        owned = connection.execute(
            """
            SELECT job_id FROM analysis_jobs
            WHERE job_id=%s AND status='running' AND lease_owner=%s
              AND attempt=%s AND fencing_token=%s AND lease_expires_at > now()
            FOR UPDATE
            """,
            (job_id, worker_id, attempt, fencing_token),
        ).fetchone()
        if owned is None:
            return False
        if revocation_context is not None:
            _persist_revocation_if_actionable(
                connection,
                run_id=run_id,
                reason_code=revocation_context.get("reason_code", error_code),
                policy_result_digest=None,
                denied_rating=None,
                context=revocation_context,
            )
        connection.execute(
            """
            UPDATE analysis_runs
            SET outcome='failed',completed_at=now(),error_code=%s,error_metadata=%s
            WHERE run_id=%s AND job_id=%s AND attempt=%s AND fencing_token=%s
              AND outcome='running'
            """,
            (error_code, Jsonb(error_metadata), run_id, job_id, attempt, fencing_token),
        )
        connection.execute(
            """
            UPDATE analysis_jobs
            SET status=CASE WHEN attempt >= max_attempts THEN 'dead' ELSE 'failed' END,
                available_at=now() + make_interval(secs => %s),last_error=%s,
                lease_owner=NULL,lease_expires_at=NULL,updated_at=now()
            WHERE job_id=%s AND status='running' AND lease_owner=%s
              AND attempt=%s AND fencing_token=%s
            """,
            (delay, error_code, job_id, worker_id, attempt, fencing_token),
        )
    return True


def complete_analysis_without_signal(
    connection: Connection,
    *,
    job_id: UUID,
    run_id: UUID,
    worker_id: str,
    attempt: int,
    fencing_token: int,
    outcome_code: str,
    policy_result_digest: str | None = None,
    denied_rating: PortfolioRating | None = None,
    revocation_context: dict[str, Any] | None = None,
) -> SignedEnvelope | None:
    """Terminally consume one fenced job when policy permits no signal."""
    if not re.fullmatch(r"[a-z][a-z0-9_.-]{2,127}", outcome_code):
        raise ValueError("outcome code must be stable and machine-readable")
    with connection.transaction():
        owned = connection.execute(
            """
            SELECT job.job_id FROM analysis_jobs AS job
            JOIN analysis_runs AS run ON run.job_id=job.job_id
            WHERE job.job_id=%s AND job.status='running' AND job.lease_owner=%s
              AND job.attempt=%s AND job.fencing_token=%s
              AND job.lease_expires_at>now() AND run.run_id=%s
              AND run.attempt=job.attempt AND run.fencing_token=job.fencing_token
              AND run.outcome='running'
            FOR UPDATE OF job,run
            """,
            (job_id, worker_id, attempt, fencing_token, run_id),
        ).fetchone()
        if owned is None:
            raise StaleJobLeaseError("analysis attempt no longer owns its job lease")
        revocation = None
        if revocation_context is not None:
            revocation = _persist_revocation_if_actionable(
                connection,
                run_id=run_id,
                reason_code=outcome_code,
                policy_result_digest=policy_result_digest,
                denied_rating=denied_rating,
                context=revocation_context,
            )
        updated = connection.execute(
            """
            UPDATE analysis_runs SET outcome='rejected',completed_at=now(),error_code=%s,
                error_metadata=%s
            WHERE run_id=%s AND job_id=%s AND attempt=%s AND fencing_token=%s
              AND outcome='running' RETURNING run_id
            """,
            (
                outcome_code,
                Jsonb({"policy_result_digest": policy_result_digest}),
                run_id, job_id, attempt, fencing_token,
            ),
        ).fetchone()
        closed = connection.execute(
            """
            UPDATE analysis_jobs SET status='succeeded',lease_owner=NULL,
                lease_expires_at=NULL,last_error=%s,updated_at=now()
            WHERE job_id=%s AND status='running' AND lease_owner=%s
              AND attempt=%s AND fencing_token=%s RETURNING job_id
            """,
            (outcome_code, job_id, worker_id, attempt, fencing_token),
        ).fetchone()
        if updated is None or closed is None:
            raise StaleJobLeaseError("analysis attempt changed before terminal rejection")
    return revocation


def _signal_subject(payload: Any) -> str:
    subject_pair = payload.pair.replace("/", "_").replace(":", "_")
    return (
        f"signals.v2.{payload.environment}.{payload.exchange}."
        f"{payload.bot_id}.{subject_pair}"
    )


def _persist_revocation_if_actionable(
    connection: Connection,
    *,
    run_id: UUID,
    reason_code: str,
    policy_result_digest: str | None,
    denied_rating: PortfolioRating | None,
    context: dict[str, Any],
) -> SignedEnvelope | None:
    """Append a signed tombstone only when the latest materialization is actionable."""
    stream = (
        context["environment"], context["bot_id"], context["exchange"],
        context["pair"], context["timeframe"],
    )
    sequence_row = connection.execute(
        """
        SELECT last_sequence FROM signal_sequences
        WHERE environment=%s AND bot_id=%s AND exchange=%s AND pair=%s AND timeframe=%s
        FOR UPDATE
        """,
        stream,
    ).fetchone()
    if sequence_row is None:
        return None
    latest = connection.execute(
        """
        SELECT kind,signal_id,sequence,checksum,expires_at,rating FROM (
            SELECT 'created' AS kind,signal_id,sequence,checksum,expires_at,
                   envelope #>> '{payload,decision,rating}' AS rating
            FROM signals
            WHERE environment=%s AND bot_id=%s AND exchange=%s AND pair=%s AND timeframe=%s
            UNION ALL
            SELECT 'revoked' AS kind,signal_id,sequence,NULL,NULL,NULL
            FROM signal_revocations
            WHERE environment=%s AND bot_id=%s AND exchange=%s AND pair=%s AND timeframe=%s
        ) AS events ORDER BY sequence DESC LIMIT 1
        """,
        (*stream, *stream),
    ).fetchone()
    if latest is None:
        raise RuntimeError("signal sequence exists without a durable event")
    if int(sequence_row["last_sequence"]) != int(latest["sequence"]):
        raise RuntimeError("signal sequence does not match the durable event stream")
    if (
        latest["kind"] != "created"
        or latest["rating"] == PortfolioRating.HOLD.value
        or latest["expires_at"] <= datetime.now(timezone.utc)
    ):
        return None
    next_row = connection.execute(
        """
        UPDATE signal_sequences SET last_sequence=last_sequence+1
        WHERE environment=%s AND bot_id=%s AND exchange=%s AND pair=%s AND timeframe=%s
        RETURNING last_sequence
        """,
        stream,
    ).fetchone()
    if next_row is None:
        raise RuntimeError("locked signal sequence disappeared")
    published_at = datetime.now(timezone.utc)
    payload = SignalRevocationPayload(
        signal_id=latest["signal_id"],
        target_sequence=latest["sequence"],
        target_checksum=latest["checksum"],
        run_id=run_id,
        correlation_id=context["correlation_id"],
        instrument_id=context["instrument_id"],
        execution_snapshot_id=context["execution_snapshot_id"],
        evidence_manifest_id=context["evidence_manifest_id"],
        source_policy_result_digest=policy_result_digest,
        environment=context["environment"],
        bot_id=context["bot_id"],
        exchange=context["exchange"],
        pair=context["pair"],
        timeframe=context["timeframe"],
        sequence=next_row["last_sequence"],
        reason_code=reason_code,
        denied_rating=denied_rating,
        published_at=published_at,
        revoked_at=published_at,
        producer_version=context["producer_version"],
        code_revision=context["code_revision"],
    )
    envelope = SignedEnvelope.sign(payload, context["hmac_secret"])
    envelope_json = envelope.model_dump(mode="json")
    connection.execute(
        """
        INSERT INTO signal_revocations(
            revocation_id,event_id,signal_id,target_sequence,target_checksum,run_id,
            correlation_id,instrument_id,execution_snapshot_id,evidence_manifest_id,
            source_policy_result_digest,environment,bot_id,exchange,pair,timeframe,
            sequence,reason_code,denied_rating,published_at,revoked_at,envelope,checksum
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            payload.revocation_id,payload.event_id,payload.signal_id,
            payload.target_sequence,payload.target_checksum,payload.run_id,
            payload.correlation_id,payload.instrument_id,payload.execution_snapshot_id,
            payload.evidence_manifest_id,payload.source_policy_result_digest,
            payload.environment,payload.bot_id,payload.exchange,payload.pair,
            payload.timeframe,payload.sequence,payload.reason_code,
            payload.denied_rating.value if payload.denied_rating else None,
            payload.published_at,payload.revoked_at,Jsonb(envelope_json),envelope.checksum,
        ),
    )
    connection.execute(
        "INSERT INTO outbox(event_id,subject,payload) VALUES (%s,%s,%s)",
        (payload.event_id, _signal_subject(payload), Jsonb(envelope_json)),
    )
    return envelope


def allocate_sequence(connection: Connection, envelope: SignedEnvelope) -> int:
    payload = envelope.payload
    row = connection.execute(
        """
        INSERT INTO signal_sequences(environment, bot_id, exchange, pair, timeframe, last_sequence)
        VALUES (%s, %s, %s, %s, %s, 1)
        ON CONFLICT (environment, bot_id, exchange, pair, timeframe)
        DO UPDATE SET last_sequence = signal_sequences.last_sequence + 1
        RETURNING last_sequence
        """,
        (payload.environment, payload.bot_id, payload.exchange, payload.pair, payload.timeframe),
    ).fetchone()
    return int(row["last_sequence"])


def authorize_signal_publication(
    connection: Connection,
    envelope: SignedEnvelope,
    run_record: dict[str, Any],
) -> None:
    """Authorize the original signed rating against its exact sealed policy result."""
    payload = envelope.payload
    if not isinstance(payload, SignalPayload):
        raise PublicationPolicyError("publication.event_type_invalid")
    row = connection.execute(
        """
        SELECT run.capture_session_id,run.evidence_manifest_id AS run_manifest_id,
               run.configuration AS run_configuration,
               manifest.status AS manifest_status,
               manifest.instrument_id AS manifest_instrument_id,
               manifest.execution_snapshot_id AS manifest_snapshot_id,
               manifest.collection_completed_at,
               manifest.policy_result_digest AS manifest_policy_digest,
               manifest.quality_flags AS manifest_quality_flags,
               session.status AS capture_status,
               evaluation.verdict,evaluation.permitted_ratings,
               evaluation.data_as_of,evaluation.quality_flags AS policy_quality_flags,
               evaluation.result_digest AS evaluation_result_digest,
               snapshot.exchange AS snapshot_exchange,snapshot.pair AS snapshot_pair,
               snapshot.timeframe AS snapshot_timeframe,
               snapshot.candle_close_at AS snapshot_candle_close_at
        FROM analysis_runs AS run
        JOIN evidence_manifests AS manifest
          ON manifest.manifest_id=%s AND manifest.run_id=run.run_id
        JOIN execution_market_snapshots AS snapshot
          ON snapshot.snapshot_id=manifest.execution_snapshot_id
        LEFT JOIN capture_sessions AS session
          ON session.session_id=run.capture_session_id
        LEFT JOIN source_policy_evaluations AS evaluation
          ON evaluation.session_id=session.session_id
         AND evaluation.manifest_id=manifest.manifest_id
        WHERE run.run_id=%s AND run.job_id=%s AND run.attempt=%s
          AND run.fencing_token=%s AND run.outcome='running'
        FOR UPDATE OF run,manifest
        """,
        (
            payload.evidence_manifest_id, payload.run_id, run_record["job_id"],
            run_record["attempt"], run_record["fencing_token"],
        ),
    ).fetchone()
    if row is None:
        raise PublicationPolicyError("publication.evidence_identity_mismatch")
    identity_ok = (
        row["manifest_status"] == "sealed"
        and row["manifest_instrument_id"] == payload.instrument_id
        and row["manifest_snapshot_id"] == payload.execution_snapshot_id
        and row["snapshot_exchange"] == payload.exchange
        and row["snapshot_pair"] == payload.pair
        and row["snapshot_timeframe"] == payload.timeframe
        and row["snapshot_candle_close_at"] == payload.candle_close_at
        and row["collection_completed_at"] <= payload.analysis_completed_at
    )
    if not identity_ok:
        raise PublicationPolicyError("publication.evidence_identity_mismatch")

    if row["capture_session_id"] is None:
        configuration = row["run_configuration"] or {}
        flags = set(row["manifest_quality_flags"] or [])
        if (
            configuration.get("research_mode") != "synthetic"
            and configuration.get("mode") != "synthetic"
            or "synthetic" not in flags
            or payload.source_policy_result_digest is not None
            or row["run_manifest_id"] not in (None, payload.evidence_manifest_id)
        ):
            raise PublicationPolicyError("publication.synthetic_provenance_invalid")
        return

    policy_digest = payload.source_policy_result_digest
    if (
        row["run_manifest_id"] != payload.evidence_manifest_id
        or row["capture_status"] != "sealed"
        or row["verdict"] not in ("pass", "hold_only")
        or policy_digest is None
        or row["manifest_policy_digest"] != policy_digest
        or row["evaluation_result_digest"] != policy_digest
    ):
        raise PublicationPolicyError("publication.policy_binding_invalid")
    if payload.decision.rating.value not in tuple(row["permitted_ratings"] or []):
        raise PublicationPolicyError("publication.rating_not_permitted")
    if row["data_as_of"] != payload.provenance.data_as_of:
        raise PublicationPolicyError("publication.data_as_of_mismatch")
    if not set(row["policy_quality_flags"] or []).issubset(
        payload.provenance.quality_flags
    ):
        raise PublicationPolicyError("publication.quality_flags_missing")


def persist_signal_and_outbox(
    connection: Connection,
    envelope: SignedEnvelope,
    run_record: dict[str, Any],
) -> SignedEnvelope:
    """Commit analysis result, signal, and outbox notification atomically."""
    payload = envelope.payload
    if not isinstance(payload, SignalPayload):
        raise PublicationPolicyError("publication.event_type_invalid")
    with connection.transaction():
        owned = connection.execute(
            """
            SELECT job_id FROM analysis_jobs
            WHERE job_id=%s AND status='running' AND lease_owner=%s
              AND attempt=%s AND fencing_token=%s AND lease_expires_at > now()
            FOR UPDATE
            """,
            (
                run_record["job_id"],
                run_record["worker_id"],
                run_record["attempt"],
                run_record["fencing_token"],
            ),
        ).fetchone()
        if owned is None:
            raise StaleJobLeaseError("analysis attempt no longer owns its job lease")
        authorize_signal_publication(connection, envelope, run_record)
        sequence = allocate_sequence(connection, envelope)
        payload = payload.model_copy(update={"sequence": sequence})
        envelope = SignedEnvelope.sign(payload, run_record["hmac_secret"], envelope.key_id)
        updated_run = connection.execute(
            """
            UPDATE analysis_runs
            SET completed_at=%s,configuration=%s,raw_decision=%s,raw_state=%s,
                report_path=%s,outcome='succeeded',evidence_manifest_id=%s
            WHERE run_id=%s AND job_id=%s AND attempt=%s AND fencing_token=%s
              AND outcome='running'
            RETURNING run_id
            """,
            (
                payload.analysis_completed_at,
                Jsonb(run_record["configuration"]),
                Jsonb(payload.decision.model_dump(mode="json")),
                Jsonb(run_record.get("raw_state", {})),
                run_record.get("report_path"),
                payload.evidence_manifest_id,
                payload.run_id,
                run_record["job_id"],
                run_record["attempt"],
                run_record["fencing_token"],
            ),
        ).fetchone()
        if updated_run is None:
            raise StaleJobLeaseError("analysis run is not the active fenced attempt")
        envelope_json = envelope.model_dump(mode="json")
        connection.execute(
            """
            INSERT INTO signals(
                signal_id,event_id,run_id,correlation_id,environment,bot_id,exchange,
                pair,timeframe,sequence,status,published_at,expires_at,envelope,checksum,
                instrument_id,execution_snapshot_id,evidence_manifest_id,signal_available_at,
                source_policy_result_digest
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                payload.signal_id, payload.event_id, payload.run_id, payload.correlation_id,
                payload.environment, payload.bot_id, payload.exchange, payload.pair,
                payload.timeframe, payload.sequence, payload.status.value, payload.published_at,
                payload.expires_at, Jsonb(envelope_json), envelope.checksum,
                payload.instrument_id, payload.execution_snapshot_id,
                payload.evidence_manifest_id, payload.signal_available_at,
                payload.source_policy_result_digest,
            ),
        )
        subject_pair = payload.pair.replace("/", "_").replace(":", "_")
        subject = f"signals.v2.{payload.environment}.{payload.exchange}.{payload.bot_id}.{subject_pair}"
        connection.execute(
            "INSERT INTO outbox(event_id, subject, payload) VALUES (%s,%s,%s)",
            (payload.event_id, subject, Jsonb(envelope_json)),
        )
        connection.execute(
            """
            UPDATE analysis_jobs SET status='succeeded', lease_owner=NULL,
                lease_expires_at=NULL, updated_at=now()
            WHERE job_id=%s AND status='running' AND lease_owner=%s
              AND attempt=%s AND fencing_token=%s
            """,
            (
                run_record["job_id"],
                run_record["worker_id"],
                run_record["attempt"],
                run_record["fencing_token"],
            ),
        )
        checkpoint("worker.during_terminal_transaction")
    return envelope


def record_execution_event(connection: Connection, event: ExecutionEvent, source: str) -> None:
    connection.execute(
        """
        INSERT INTO execution_events(
            event_id,event_type,occurred_at,bot_id,exchange,pair,trade_id,order_id,
            signal_id,run_id,payload,source
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT DO NOTHING
        """,
        (
            event.event_id, event.event_type, event.occurred_at, event.bot_id, event.exchange,
            event.pair, event.trade_id, event.order_id, event.signal_id, event.run_id,
            Jsonb(event.payload), source,
        ),
    )
    connection.commit()


def heartbeat(connection: Connection, service_id: str, status: str, details: dict[str, Any]) -> None:
    connection.execute(
        """
        INSERT INTO service_heartbeats(service_id,status,details,observed_at)
        VALUES (%s,%s,%s,now())
        ON CONFLICT (service_id) DO UPDATE
        SET status=excluded.status, details=excluded.details, observed_at=excluded.observed_at
        """,
        (service_id, status, Jsonb(details)),
    )
    connection.commit()


def kill_switch_enabled(connection: Connection, bot_id: str) -> bool:
    row = connection.execute(
        "SELECT bool_or(enabled) AS enabled FROM kill_switches WHERE scope IN ('global', %s)",
        (f"bot:{bot_id}",),
    ).fetchone()
    return bool(row and row["enabled"])
