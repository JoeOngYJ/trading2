from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.types.json import Jsonb

from .artifacts import ArtifactStore
from .capture import (
    _lock_owned_capture_session,
    canonical_digest,
    seal_capture_session,
)
from .contracts import (
    ArtifactRef,
    CaptureFence,
    CaptureSession,
    EvidenceManifest,
    ExecutionMarketSnapshot,
    InstrumentIdentity,
    SemanticInvocationRecord,
    VendorAttemptRecord,
)
from .evidence import manifest_digest
from .source_policy import (
    PolicyVerdict,
    SourcePolicyConfiguration,
    SourcePolicyInput,
    SourcePolicyResult,
    evaluate_source_policy,
)


def _artifact_ref(row: dict[str, Any], prefix: str = "") -> ArtifactRef:
    return ArtifactRef(
        digest=row[f"{prefix}digest"],
        media_type=row[f"{prefix}media_type"],
        byte_length=row[f"{prefix}byte_length"],
        storage_path=row[f"{prefix}storage_path"],
    )


def load_source_policy_input(
    connection: Connection,
    session_id: UUID,
    fence: CaptureFence,
    artifact_dir: Path,
) -> SourcePolicyInput:
    """Lock one owned evaluating attempt and materialize its verified policy input."""
    session = _lock_owned_capture_session(connection, session_id, fence)
    if session["status"] != "evaluating" or session["collection_closed_at"] is None:
        raise ValueError("source policy can only load a frozen evaluating session")

    instrument = connection.execute(
        "SELECT * FROM instruments WHERE instrument_id=%s",
        (session["instrument_id"],),
    ).fetchone()
    if instrument is None:
        raise ValueError("capture instrument is missing")
    snapshot = connection.execute(
        """
        SELECT snapshot.*,artifact.digest AS raw_digest,
               artifact.media_type AS raw_media_type,
               artifact.byte_length AS raw_byte_length,
               artifact.storage_path AS raw_storage_path
        FROM execution_market_snapshots AS snapshot
        JOIN artifacts AS artifact ON artifact.digest=snapshot.raw_artifact_digest
        WHERE snapshot.snapshot_id=%s AND snapshot.instrument_id=%s
        """,
        (session["execution_snapshot_id"], session["instrument_id"]),
    ).fetchone()
    if snapshot is None:
        raise ValueError("capture execution snapshot is missing or mismatched")
    invocation_rows = connection.execute(
        "SELECT * FROM semantic_invocations WHERE session_id=%s ORDER BY ordinal",
        (session_id,),
    ).fetchall()
    attempt_rows = connection.execute(
        """
        SELECT * FROM vendor_attempts WHERE session_id=%s
        ORDER BY invocation_id,fallback_ordinal
        """,
        (session_id,),
    ).fetchall()

    invocations = tuple(SemanticInvocationRecord(
        invocation_id=row["invocation_id"],
        session_id=row["session_id"],
        ordinal=row["ordinal"],
        method=row["method"],
        category=row["category"],
        policy_subject=row["policy_subject"],
        consumer=row["consumer"],
        sanitized_arguments=row["sanitized_arguments"],
        arguments_hash=row["arguments_hash"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        first_seen_at=row["first_seen_at"],
        information_cutoff_at=row["information_cutoff_at"],
        outcome=row["outcome"],
        error_code=row["error_code"],
        normalized_artifact_digest=row["normalized_artifact_digest"],
        observation_id=row["observation_id"],
        typed_metadata=row["typed_metadata"],
        replay_safe=row["replay_safe"],
        replay_unsafe_reason=row["replay_unsafe_reason"],
    ) for row in invocation_rows)
    attempts = tuple(VendorAttemptRecord(
        attempt_id=row["attempt_id"],
        invocation_id=row["invocation_id"],
        session_id=row["session_id"],
        fallback_ordinal=row["fallback_ordinal"],
        vendor=row["vendor"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        first_seen_at=row["first_seen_at"],
        outcome=row["outcome"],
        error_code=row["error_code"],
        raw_artifact_digest=row["raw_artifact_digest"],
        normalized_artifact_digest=row["normalized_artifact_digest"],
        observation_id=row["observation_id"],
    ) for row in attempt_rows)

    referenced_digests = {snapshot["raw_artifact_digest"]}
    referenced_digests.update(
        digest for row in invocation_rows
        if (digest := row["normalized_artifact_digest"]) is not None
    )
    for row in attempt_rows:
        referenced_digests.update(
            digest for digest in (
                row["raw_artifact_digest"], row["normalized_artifact_digest"]
            ) if digest is not None
        )
    artifact_rows = connection.execute(
        "SELECT * FROM artifacts WHERE digest = ANY(%s)",
        (sorted(referenced_digests),),
    ).fetchall()
    store = ArtifactStore(artifact_dir)
    verified: list[str] = []
    for row in artifact_rows:
        reference = _artifact_ref(row)
        try:
            store.read(reference)
        except (OSError, ValueError):
            continue
        verified.append(reference.digest)

    session_model = CaptureSession(
        session_id=session["session_id"],
        run_id=session["run_id"],
        manifest_id=session["manifest_id"],
        instrument_id=session["instrument_id"],
        execution_snapshot_id=session["execution_snapshot_id"],
        job_id=session["job_id"],
        job_attempt=session["job_attempt"],
        fencing_token=session["fencing_token"],
        mode=session["mode"],
        status=session["status"],
        upstream_version=session["upstream_version"],
        upstream_commit=session["upstream_commit"],
        adapter_version=session["adapter_version"],
        configuration_hash=session["configuration_hash"],
        started_at=session["started_at"],
        deadline_at=session["deadline_at"],
        collection_closed_at=session["collection_closed_at"],
        completed_at=session["completed_at"],
        rejection_code=session["rejection_code"],
    )
    instrument_model = InstrumentIdentity(
        instrument_id=instrument["instrument_id"],
        research_symbol=instrument["research_symbol"],
        execution_exchange=instrument["execution_exchange"],
        execution_pair=instrument["execution_pair"],
        market_type=instrument["market_type"],
        base=instrument["base_asset"],
        quote=instrument["quote_asset"],
        research_quote=instrument["research_quote"],
        timezone=instrument["timezone"],
        enabled=instrument["enabled"],
    )
    snapshot_model = ExecutionMarketSnapshot(
        snapshot_id=snapshot["snapshot_id"],
        instrument_id=snapshot["instrument_id"],
        exchange=snapshot["exchange"],
        pair=snapshot["pair"],
        market_type=snapshot["market_type"],
        timeframe=snapshot["timeframe"],
        candle_type=snapshot["candle_type"],
        candle_open_at=snapshot["candle_open_at"],
        candle_close_at=snapshot["candle_close_at"],
        open=str(snapshot["open_price"]),
        high=str(snapshot["high_price"]),
        low=str(snapshot["low_price"]),
        close=str(snapshot["close_price"]),
        volume=str(snapshot["volume"]),
        retrieved_at=snapshot["retrieved_at"],
        exchange_time_at=snapshot["exchange_time_at"],
        clock_offset_ms=snapshot["clock_offset_ms"],
        is_closed=snapshot["is_closed"],
        has_gap=snapshot["has_gap"],
        collector_version=snapshot["collector_version"],
        raw_artifact=_artifact_ref(snapshot, "raw_"),
    )
    return SourcePolicyInput(
        session=session_model,
        instrument=instrument_model,
        execution_snapshot=snapshot_model,
        vendor_plan=session["configured_vendors"],
        invocations=invocations,
        vendor_attempts=attempts,
        verified_artifact_digests=tuple(verified),
        analysis_started_at=session["analysis_started_at"],
        collection_cutoff_at=session["collection_closed_at"],
    )


def _persist_policy_result(
    connection: Connection,
    policy_input: SourcePolicyInput,
    result: SourcePolicyResult,
) -> UUID:
    if result.session_id != str(policy_input.session.session_id):
        raise ValueError("source policy result session identity mismatch")
    if result.input_digest != canonical_digest(policy_input.model_dump(mode="json")):
        raise ValueError("source policy result input digest mismatch")
    evaluation_id = uuid4()
    session = policy_input.session
    connection.execute(
        """
        INSERT INTO source_policy_evaluations(
            evaluation_id,session_id,manifest_id,run_id,job_id,job_attempt,fencing_token,
            instrument_id,execution_snapshot_id,policy_version,policy_configuration_hash,
            input_digest,verdict,permitted_ratings,data_as_of,quality_flags,result_digest
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            evaluation_id, session.session_id, session.manifest_id, session.run_id,
            session.job_id, session.job_attempt, session.fencing_token,
            session.instrument_id, session.execution_snapshot_id, result.policy_version,
            result.policy_configuration_hash, result.input_digest, result.verdict.value,
            Jsonb(list(result.permitted_ratings)), result.data_as_of,
            Jsonb(list(result.quality_flags)), result.result_digest,
        ),
    )
    for ordinal, rule in enumerate(result.rules):
        connection.execute(
            """
            INSERT INTO source_policy_rule_results(
                evaluation_id,ordinal,rule_id,outcome,code,evidence_refs
            ) VALUES (%s,%s,%s,%s,%s,%s)
            """,
            (
                evaluation_id, ordinal, rule.rule_id, rule.outcome.value,
                rule.code, Jsonb(list(rule.evidence_refs)),
            ),
        )
    return evaluation_id


def _reject_evaluated_capture(
    connection: Connection,
    policy_input: SourcePolicyInput,
    evaluation_id: UUID,
    result: SourcePolicyResult,
) -> None:
    session = policy_input.session
    failed = next(rule for rule in result.rules if rule.outcome.value == "fail")
    completed_at = connection.execute("SELECT now() AS completed_at").fetchone()["completed_at"]
    rejection_digest = manifest_digest({
        "manifest_id": str(session.manifest_id),
        "session_id": str(session.session_id),
        "policy_evaluation_id": str(evaluation_id),
        "policy_result_digest": result.result_digest,
        "rejection_code": failed.code,
    })
    manifest = connection.execute(
        """
        UPDATE evidence_manifests SET status='rejected',collection_completed_at=%s,
            replay_safe=false,digest=%s,quality_flags=%s,
            policy_evaluation_id=%s,policy_result_digest=%s
        WHERE manifest_id=%s AND capture_session_id=%s AND status='collecting'
        RETURNING manifest_id
        """,
        (
            completed_at, rejection_digest, Jsonb(list(result.quality_flags)),
            evaluation_id, result.result_digest, session.manifest_id, session.session_id,
        ),
    ).fetchone()
    closed = connection.execute(
        """
        UPDATE capture_sessions SET status='rejected',completed_at=%s,rejection_code=%s
        WHERE session_id=%s AND status='evaluating' RETURNING session_id
        """,
        (completed_at, failed.code, session.session_id),
    ).fetchone()
    if manifest is None or closed is None:
        raise ValueError("evaluated capture could not be rejected atomically")


def evaluate_and_finalize_capture(
    connection: Connection,
    session_id: UUID,
    fence: CaptureFence,
    artifact_dir: Path,
    configuration: SourcePolicyConfiguration | None = None,
) -> tuple[SourcePolicyResult, EvidenceManifest | None]:
    """Verify, evaluate, persist, and terminally close one fenced capture atomically."""
    with connection.transaction():
        policy_input = load_source_policy_input(
            connection, session_id, fence, artifact_dir
        )
        result = evaluate_source_policy(policy_input, configuration)
        evaluation_id = _persist_policy_result(connection, policy_input, result)
        if result.verdict == PolicyVerdict.REJECT:
            _reject_evaluated_capture(connection, policy_input, evaluation_id, result)
            return result, None
        manifest = seal_capture_session(connection, session_id, fence)
        return result, manifest
