from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID

from .contracts import (
    CaptureSession,
    CaptureFence,
    EvidenceManifest,
    SemanticInvocationRecord,
    SourceCallOutcome,
    SourceCallRecord,
    VendorAttemptRecord,
)

if TYPE_CHECKING:
    from psycopg import Connection


REDACTED = "[REDACTED]"
_SENSITIVE_KEYS = {
    "api_key", "apikey", "authorization", "cookie", "set_cookie", "access_token",
    "refresh_token", "client_secret", "password", "passwd", "signature", "sig",
    "token", "x_api_key",
}
_CREDENTIAL_TEXT = re.compile(
    r"(?i)\b(authorization|api[-_ ]?key|token|password|cookie)\s*[:=]\s*([^\s,;]+)"
)


def _normalized_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _sanitize_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return value
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return value
    query = [
        (key, REDACTED if _normalized_key(key) in _SENSITIVE_KEYS else item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
    ]
    hostname = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    netloc = f"{hostname}{port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, urlencode(query), parsed.fragment))


def sanitize(value: Any, *, key: str | None = None) -> Any:
    """Return a deterministic, JSON-safe value with credentials removed."""
    if key is not None and _normalized_key(key) in _SENSITIVE_KEYS:
        return REDACTED
    if isinstance(value, dict):
        return {str(item_key): sanitize(item, key=str(item_key)) for item_key, item in value.items()}
    if isinstance(value, set):
        return sorted((sanitize(item) for item in value), key=lambda item: json.dumps(item, sort_keys=True))
    if isinstance(value, (list, tuple)):
        return [sanitize(item) for item in value]
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("capture arguments cannot contain naive datetimes")
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, (UUID, Decimal)):
        return str(value)
    if isinstance(value, bytes):
        return {"byte_length": len(value), "sha256": hashlib.sha256(value).hexdigest()}
    if isinstance(value, str):
        sanitized = _sanitize_url(value)
        return _CREDENTIAL_TEXT.sub(lambda match: f"{match.group(1)}={REDACTED}", sanitized)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)


def canonical_digest(value: Any) -> str:
    canonical = json.dumps(sanitize(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def classify_error(error: BaseException) -> tuple[SourceCallOutcome, str]:
    """Classify without persisting exception text, which may contain credentials."""
    status = getattr(error, "status_code", None) or getattr(getattr(error, "response", None), "status_code", None)
    if isinstance(error, TimeoutError) or error.__class__.__name__.lower() in {
        "timeout", "timeouterror", "readtimeout", "connecttimeout"
    }:
        return SourceCallOutcome.TIMEOUT, "vendor_timeout"
    if status == 429:
        return SourceCallOutcome.RATE_LIMITED, "vendor_rate_limited"
    if status in (401, 403):
        return SourceCallOutcome.AUTH_ERROR, "vendor_auth_failed"
    if status is not None and 400 <= int(status) < 500:
        return SourceCallOutcome.POLICY_REJECTED, "vendor_request_rejected"
    return SourceCallOutcome.VENDOR_ERROR, "vendor_unavailable"


def persist_source_call(connection: Connection, call: SourceCallRecord) -> None:
    from psycopg.types.json import Jsonb

    connection.execute(
        """
        INSERT INTO source_calls(
            call_id,session_id,ordinal,method,category,vendor,fallback_ordinal,consumer,
            sanitized_arguments,arguments_hash,started_at,completed_at,first_seen_at,
            outcome,error_code,raw_artifact_digest,normalized_artifact_digest,observation_id
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            call.call_id, call.session_id, call.ordinal, call.method, call.category,
            call.vendor, call.fallback_ordinal, call.consumer, Jsonb(call.sanitized_arguments),
            call.arguments_hash, call.started_at, call.completed_at, call.first_seen_at,
            call.outcome.value, call.error_code, call.raw_artifact_digest,
            call.normalized_artifact_digest, call.observation_id,
        ),
    )


def start_semantic_invocation(
    connection: Connection,
    *,
    invocation_id: UUID,
    session_id: UUID,
    method: str,
    category: str,
    policy_subject: str,
    consumer: str,
    sanitized_arguments: dict[str, Any],
    arguments_hash: str,
    started_at: datetime,
) -> int:
    """Allocate and durably create one graph-level invocation before vendor I/O."""
    from psycopg.types.json import Jsonb

    row = connection.execute(
        """
        UPDATE capture_sessions SET next_invocation_ordinal=next_invocation_ordinal+1
        WHERE session_id=%s AND status='collecting' AND deadline_at>now()
        RETURNING next_invocation_ordinal-1 AS ordinal
        """,
        (session_id,),
    ).fetchone()
    if row is None:
        raise ValueError("capture session is closed, missing, or past deadline")
    ordinal = int(row["ordinal"])
    connection.execute(
        """
        INSERT INTO semantic_invocations(
            invocation_id,session_id,ordinal,method,category,policy_subject,consumer,
            sanitized_arguments,arguments_hash,started_at
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            invocation_id, session_id, ordinal, method, category, policy_subject, consumer,
            Jsonb(sanitized_arguments), arguments_hash, started_at,
        ),
    )
    return ordinal


def complete_semantic_invocation(
    connection: Connection, invocation: SemanticInvocationRecord
) -> None:
    """Complete a previously started invocation exactly once during collection."""
    from psycopg.types.json import Jsonb

    row = connection.execute(
        """
        UPDATE semantic_invocations SET
            completed_at=%s,first_seen_at=%s,information_cutoff_at=%s,outcome=%s,
            error_code=%s,normalized_artifact_digest=%s,observation_id=%s,
            typed_metadata=%s,replay_safe=%s,replay_unsafe_reason=%s
        WHERE invocation_id=%s AND session_id=%s AND completed_at IS NULL
        RETURNING invocation_id
        """,
        (
            invocation.completed_at, invocation.first_seen_at,
            invocation.information_cutoff_at, invocation.outcome.value,
            invocation.error_code, invocation.normalized_artifact_digest,
            invocation.observation_id,
            Jsonb(invocation.typed_metadata.model_dump(mode="json")),
            invocation.replay_safe, invocation.replay_unsafe_reason,
            invocation.invocation_id, invocation.session_id,
        ),
    ).fetchone()
    if row is None:
        raise ValueError("semantic invocation is missing or already complete")


def persist_vendor_attempt(connection: Connection, attempt: VendorAttemptRecord) -> None:
    connection.execute(
        """
        INSERT INTO vendor_attempts(
            attempt_id,invocation_id,session_id,fallback_ordinal,vendor,started_at,
            completed_at,first_seen_at,outcome,error_code,raw_artifact_digest,
            normalized_artifact_digest,observation_id
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            attempt.attempt_id, attempt.invocation_id, attempt.session_id,
            attempt.fallback_ordinal, attempt.vendor, attempt.started_at,
            attempt.completed_at, attempt.first_seen_at, attempt.outcome.value,
            attempt.error_code, attempt.raw_artifact_digest,
            attempt.normalized_artifact_digest, attempt.observation_id,
        ),
    )


def _lock_owned_capture_session(
    connection: Connection, session_id: UUID, fence: CaptureFence
) -> dict[str, Any]:
    from .repository import StaleJobLeaseError

    row = connection.execute(
        """
        SELECT session.*,manifest.configured_vendors,manifest.required_sources,
               manifest.mode AS manifest_mode,run.started_at AS analysis_started_at
        FROM capture_sessions AS session
        JOIN evidence_manifests AS manifest ON manifest.manifest_id=session.manifest_id
        JOIN analysis_runs AS run ON run.run_id=session.run_id
        JOIN analysis_jobs AS job ON job.job_id=session.job_id
        WHERE session.session_id=%s
          AND session.job_id=%s AND session.job_attempt=%s AND session.fencing_token=%s
          AND run.job_id=session.job_id AND run.attempt=session.job_attempt
          AND run.fencing_token=session.fencing_token AND run.outcome='running'
          AND run.capture_session_id=session.session_id
          AND run.evidence_manifest_id=session.manifest_id
          AND job.status='running' AND job.lease_owner=%s
          AND job.attempt=session.job_attempt AND job.fencing_token=session.fencing_token
          AND job.lease_expires_at>now()
        FOR UPDATE OF session,manifest,run,job
        """,
        (
            session_id, fence.job_id, fence.attempt, fence.fencing_token,
            fence.worker_id,
        ),
    ).fetchone()
    if row is None:
        raise StaleJobLeaseError("capture attempt no longer owns its job lease")
    return row


def begin_capture_evaluation(
    connection: Connection, session_id: UUID, fence: CaptureFence
) -> None:
    """Freeze the evidence ledger before artifact loading or policy evaluation."""
    _lock_owned_capture_session(connection, session_id, fence)
    incomplete = connection.execute(
        """
        SELECT count(*) AS count FROM semantic_invocations
        WHERE session_id=%s AND completed_at IS NULL
        """,
        (session_id,),
    ).fetchone()
    if incomplete is None or int(incomplete["count"]) != 0:
        raise ValueError("capture session has incomplete semantic invocations")
    row = connection.execute(
        """
        UPDATE capture_sessions SET status='evaluating',collection_closed_at=now()
        WHERE session_id=%s AND status='collecting' AND deadline_at>now()
        RETURNING session_id,collection_closed_at
        """,
        (session_id,),
    ).fetchone()
    if row is None:
        raise ValueError("capture session is missing or not collecting")


def start_capture_session(
    connection: Connection,
    session: CaptureSession,
    *,
    configured_vendors: dict[str, Any],
    required_sources: dict[str, str],
    worker_id: str,
) -> None:
    from psycopg.types.json import Jsonb

    if session.status.value != "collecting":
        raise ValueError("new capture sessions must be collecting")
    from .repository import StaleJobLeaseError
    from .source_allowlist import normalize_vendor_plan

    normalized_vendor_plan = normalize_vendor_plan(configured_vendors)

    owned = connection.execute(
        """
        SELECT job.lease_expires_at
        FROM analysis_jobs AS job
        JOIN analysis_runs AS run ON run.job_id=job.job_id
        WHERE job.job_id=%s AND job.status='running' AND job.lease_owner=%s
          AND job.attempt=%s AND job.fencing_token=%s AND job.lease_expires_at>now()
          AND job.instrument_id=%s AND job.execution_snapshot_id=%s
          AND run.run_id=%s AND run.attempt=job.attempt
          AND run.fencing_token=job.fencing_token AND run.outcome='running'
          AND run.capture_session_id IS NULL AND run.evidence_manifest_id IS NULL
        FOR UPDATE OF job,run
        """,
        (
            session.job_id, worker_id, session.job_attempt, session.fencing_token,
            session.instrument_id, session.execution_snapshot_id, session.run_id,
        ),
    ).fetchone()
    if owned is None:
        raise StaleJobLeaseError("cannot start capture without the live fenced job lease")
    if session.deadline_at > owned["lease_expires_at"]:
        raise ValueError("capture deadline cannot exceed the current job lease")
    manifest_mode = "live" if session.mode == "live_capture" else "captured_replay"
    connection.execute(
        """
        INSERT INTO evidence_manifests(
            manifest_id,run_id,instrument_id,execution_snapshot_id,mode,status,
            collection_started_at,configured_vendors,required_sources,capture_session_id
        ) VALUES (%s,%s,%s,%s,%s,'collecting',%s,%s,%s,%s)
        """,
        (
            session.manifest_id, session.run_id, session.instrument_id,
            session.execution_snapshot_id, manifest_mode, session.started_at,
            Jsonb({key: list(value) for key, value in normalized_vendor_plan.items()}),
            Jsonb(required_sources), session.session_id,
        ),
    )
    connection.execute(
        """
        INSERT INTO capture_sessions(
            session_id,run_id,manifest_id,instrument_id,execution_snapshot_id,mode,status,
            upstream_version,upstream_commit,adapter_version,configuration_hash,
            started_at,deadline_at,job_id,job_attempt,fencing_token
        ) VALUES (%s,%s,%s,%s,%s,%s,'collecting',%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            session.session_id, session.run_id, session.manifest_id, session.instrument_id,
            session.execution_snapshot_id, session.mode, session.upstream_version,
            session.upstream_commit, session.adapter_version, session.configuration_hash,
            session.started_at, session.deadline_at, session.job_id, session.job_attempt,
            session.fencing_token,
        ),
    )
    updated = connection.execute(
        """
        UPDATE analysis_runs SET capture_session_id=%s,evidence_manifest_id=%s
        WHERE run_id=%s AND job_id=%s AND attempt=%s AND fencing_token=%s
          AND outcome='running' AND capture_session_id IS NULL
          AND evidence_manifest_id IS NULL
        RETURNING run_id
        """,
        (
            session.session_id, session.manifest_id, session.run_id, session.job_id,
            session.job_attempt, session.fencing_token,
        ),
    ).fetchone()
    if updated is None:
        raise StaleJobLeaseError("analysis attempt changed while capture was starting")


def _call_ledger_digest(
    rows: list[dict[str, Any]], attempts: list[dict[str, Any]] | None = None
) -> str:
    attempts_by_invocation: dict[UUID, list[dict[str, Any]]] = {}
    for attempt in attempts or []:
        attempts_by_invocation.setdefault(attempt["invocation_id"], []).append({
            "fallback_ordinal": attempt["fallback_ordinal"],
            "vendor": attempt["vendor"],
            "outcome": attempt["outcome"],
            "error_code": attempt["error_code"],
            "raw_artifact_digest": attempt["raw_artifact_digest"],
            "normalized_artifact_digest": attempt["normalized_artifact_digest"],
            "observation_id": (
                str(attempt["observation_id"]) if attempt["observation_id"] else None
            ),
            "first_seen_at": attempt["first_seen_at"].astimezone(timezone.utc).isoformat(),
        })
    ledger = [
        {
            "invocation_id": str(row["invocation_id"]),
            "ordinal": row["ordinal"],
            "method": row["method"],
            "category": row["category"],
            "policy_subject": row["policy_subject"],
            "consumer": row["consumer"],
            "arguments_hash": row["arguments_hash"],
            "outcome": row["outcome"],
            "error_code": row["error_code"],
            "normalized_artifact_digest": row["normalized_artifact_digest"],
            "observation_id": str(row["observation_id"]) if row["observation_id"] else None,
            "first_seen_at": row["first_seen_at"].astimezone(timezone.utc).isoformat(),
            "typed_metadata": row["typed_metadata"],
            "replay_safe": row["replay_safe"],
            "vendor_attempts": attempts_by_invocation.get(row["invocation_id"], []),
        }
        for row in rows
    ]
    return canonical_digest(ledger)


def seal_capture_session(
    connection: Connection, session_id: UUID, fence: CaptureFence
) -> EvidenceManifest:
    """Seal the ledger and manifest. Caller owns the surrounding transaction."""
    from .evidence import manifest_digest
    from psycopg.types.json import Jsonb

    session = _lock_owned_capture_session(connection, session_id, fence)
    if session["status"] != "evaluating":
        raise ValueError("capture session is missing or not evaluating")
    evaluation = connection.execute(
        """
        SELECT evaluation_id,result_digest,verdict,quality_flags
        FROM source_policy_evaluations
        WHERE session_id=%s AND manifest_id=%s AND verdict IN ('pass','hold_only')
        FOR UPDATE
        """,
        (session_id, session["manifest_id"]),
    ).fetchone()
    if evaluation is None:
        raise ValueError("capture session lacks a publishable source-policy evaluation")
    from .source_policy import EXPECTED_POLICY_RULE_IDS
    policy_rules = connection.execute(
        """
        SELECT ordinal,rule_id,outcome FROM source_policy_rule_results
        WHERE evaluation_id=%s ORDER BY ordinal FOR UPDATE
        """,
        (evaluation["evaluation_id"],),
    ).fetchall()
    if tuple(row["rule_id"] for row in policy_rules) != EXPECTED_POLICY_RULE_IDS:
        raise ValueError("source-policy rule inventory is incomplete or reordered")
    outcomes = {row["outcome"] for row in policy_rules}
    if "fail" in outcomes or (
        evaluation["verdict"] == "pass" and "degrade" in outcomes
    ) or (
        evaluation["verdict"] == "hold_only" and "degrade" not in outcomes
    ):
        raise ValueError("source-policy verdict conflicts with normalized rule outcomes")
    rows = connection.execute(
        "SELECT * FROM semantic_invocations WHERE session_id=%s ORDER BY ordinal FOR UPDATE",
        (session_id,),
    ).fetchall()
    if not rows:
        raise ValueError("capture session cannot seal an empty invocation ledger")
    if [row["ordinal"] for row in rows] != list(range(len(rows))):
        raise ValueError("semantic invocation ordinals must be contiguous from zero")
    attempts = connection.execute(
        """
        SELECT * FROM vendor_attempts WHERE session_id=%s
        ORDER BY invocation_id,fallback_ordinal FOR UPDATE
        """,
        (session_id,),
    ).fetchall()
    for invocation_id in {row["invocation_id"] for row in attempts}:
        ordinals = [
            row["fallback_ordinal"] for row in attempts
            if row["invocation_id"] == invocation_id
        ]
        if ordinals != list(range(len(ordinals))):
            raise ValueError("vendor fallback ordinals must be contiguous from zero")
    observation_ids = list(dict.fromkeys(
        row["observation_id"] for row in [*rows, *attempts]
        if row["observation_id"] is not None
    ))
    for ordinal, observation_id in enumerate(observation_ids):
        connection.execute(
            """
            INSERT INTO manifest_observations(manifest_id,observation_id,ordinal)
            VALUES (%s,%s,%s)
            """,
            (session["manifest_id"], observation_id, ordinal),
        )
    completed_at = datetime.now(timezone.utc)
    ledger_digest = _call_ledger_digest(rows, attempts)
    digest_data = {
        "manifest_id": str(session["manifest_id"]),
        "run_id": str(session["run_id"]),
        "instrument_id": session["instrument_id"],
        "execution_snapshot_id": str(session["execution_snapshot_id"]),
        "mode": session["manifest_mode"],
        "collection_started_at": session["started_at"].astimezone(timezone.utc).isoformat(),
        "collection_completed_at": completed_at.isoformat(),
        "observation_ids": [str(value) for value in observation_ids],
        "configured_vendors": session["configured_vendors"],
        "vendor_fallbacks": [
            f"{next(row['method'] for row in rows if row['invocation_id'] == attempt['invocation_id'])}:"
            f"{attempt['vendor']}"
            for attempt in attempts if attempt["fallback_ordinal"] > 0
        ],
        "required_sources": session["required_sources"],
        "replay_safe": all(
            row["outcome"] == "available" and row["replay_safe"] for row in rows
        ),
        "quality_flags": evaluation["quality_flags"],
        "call_ledger_digest": ledger_digest,
        "policy_evaluation_id": str(evaluation["evaluation_id"]),
        "policy_result_digest": evaluation["result_digest"],
    }
    digest = manifest_digest(digest_data)
    sealed_manifest = connection.execute(
        """
        UPDATE evidence_manifests SET status='sealed',collection_completed_at=%s,
            replay_safe=%s,digest=%s,call_ledger_digest=%s,
            quality_flags=%s,policy_evaluation_id=%s,policy_result_digest=%s
        WHERE manifest_id=%s AND status='collecting' RETURNING manifest_id
        """,
        (
            completed_at, digest_data["replay_safe"], digest, ledger_digest,
            Jsonb(digest_data["quality_flags"]), evaluation["evaluation_id"],
            evaluation["result_digest"],
            session["manifest_id"],
        ),
    )
    sealed_session = connection.execute(
        """
        UPDATE capture_sessions SET status='sealed',completed_at=%s
        WHERE session_id=%s AND status='evaluating' RETURNING session_id
        """,
        (completed_at, session_id),
    ).fetchone()
    if sealed_manifest.fetchone() is None or sealed_session is None:
        raise ValueError("policy-bound capture could not be sealed atomically")
    return EvidenceManifest(
        **{key: value for key, value in digest_data.items() if key != "call_ledger_digest"},
        digest=digest,
    )


def reject_capture_session(
    connection: Connection,
    session_id: UUID,
    rejection_code: str,
    fence: CaptureFence,
) -> None:
    from psycopg.types.json import Jsonb

    if not re.fullmatch(r"[a-z][a-z0-9_.-]{2,127}", rejection_code):
        raise ValueError("rejection code must be a stable machine-readable value")
    _lock_owned_capture_session(connection, session_id, fence)
    completed_at = datetime.now(timezone.utc)
    rejection_digest = canonical_digest({"session_id": str(session_id), "rejection_code": rejection_code})
    connection.execute(
        """
        UPDATE evidence_manifests SET status='rejected',collection_completed_at=%s,
            replay_safe=false,digest=%s,quality_flags=quality_flags || %s::jsonb
        WHERE capture_session_id=%s AND status='collecting'
        """,
        (completed_at, rejection_digest, Jsonb([rejection_code]), session_id),
    )
    row = connection.execute(
        """
        UPDATE capture_sessions SET status='rejected',completed_at=%s,
            collection_closed_at=COALESCE(collection_closed_at,LEAST(deadline_at,%s)),
            rejection_code=%s
        WHERE session_id=%s AND status IN ('collecting','evaluating') RETURNING session_id
        """,
        (completed_at, completed_at, rejection_code, session_id),
    ).fetchone()
    if row is None:
        raise ValueError("capture session is missing or not collecting")
