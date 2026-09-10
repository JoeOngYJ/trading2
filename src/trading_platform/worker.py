from __future__ import annotations

import logging
import os
import socket
import threading
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from .capture import (
    begin_capture_evaluation,
    reject_capture_session,
    start_capture_session,
)
from .contracts import (
    CaptureFence,
    CaptureSession,
    Provenance,
    RATING_SCORE,
    SignalPayload,
    SignedEnvelope,
)
from .fault_injection import checkpoint
from .db import connect, migrate
from .evidence import seal_manifest
from .repository import (
    claim_analysis_job,
    complete_analysis_without_signal,
    create_analysis_attempt,
    fail_analysis_job,
    persist_signal_and_outbox,
    recover_expired_analysis_jobs,
    renew_analysis_job_lease,
)
from .research import (
    build_tradingagents_configuration,
    configuration_hash,
    run_tradingagents,
    synthetic_result,
)
from .settings import Settings
from .source_allowlist import ALLOWED_INGRESS
from .source_policy import PolicyVerdict, RuleOutcome, SourcePolicyConfiguration
from .source_policy_persistence import evaluate_and_finalize_capture
from .tradingagents_capture import (
    PINNED_COMMIT,
    PINNED_VERSION,
    TradingAgentsCaptureAdapter,
)


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("worker")


class LeaseRenewer:
    """Renew a fenced job lease on a separate database connection."""

    def __init__(self, settings: Settings, job: dict, worker_id: str):
        self.settings = settings
        self.job = job
        self.worker_id = worker_id
        self._stop = threading.Event()
        self._lost = threading.Event()
        self._thread = threading.Thread(target=self._run, name="analysis-lease-renewer", daemon=True)

    def __enter__(self) -> "LeaseRenewer":
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self._stop.set()
        self._thread.join(timeout=self.settings.analysis_lease_renew_seconds + 5)

    def ensure_owned(self) -> None:
        if self._lost.is_set():
            raise RuntimeError("analysis job lease was lost")

    def _run(self) -> None:
        while not self._stop.wait(self.settings.analysis_lease_renew_seconds):
            try:
                with connect(self.settings.database_url) as connection:
                    renewed = renew_analysis_job_lease(
                        connection,
                        job_id=self.job["job_id"],
                        worker_id=self.worker_id,
                        attempt=self.job["attempt"],
                        fencing_token=self.job["fencing_token"],
                        lease_seconds=self.settings.analysis_lease_seconds,
                    )
                if not renewed:
                    self._lost.set()
                    return
            except Exception:
                logger.exception("analysis lease renewal failed", extra={"job_id": str(self.job["job_id"])})
                self._lost.set()
                return


def _persist_publishable_result(
    connection,
    *,
    settings: Settings,
    job: dict,
    worker_id: str,
    run_id,
    started_at: datetime,
    result,
    manifest,
    policy_result,
    lease: LeaseRenewer,
) -> None:
    if settings.research_mode == "synthetic":
        observation = connection.execute(
            """
            SELECT observation_id FROM source_observations
            WHERE category='execution_market' AND external_id=%s
              AND status='available'
            ORDER BY retrieved_at LIMIT 1
            """,
            (str(job["execution_snapshot_id"]),),
        ).fetchone()
        if observation is None:
            raise RuntimeError("execution snapshot has no immutable source observation")
        with connection.transaction():
            manifest = seal_manifest(
                connection,
                manifest_id=uuid4(),
                run_id=run_id,
                instrument_id=job["instrument_id"],
                execution_snapshot_id=job["execution_snapshot_id"],
                observation_ids=[observation["observation_id"]],
                configured_vendors={"execution_market": settings.market_data_mode},
                required_sources={"execution_market": "available"},
                collection_started_at=started_at,
                quality_flags=["synthetic"],
                replay_safe=True,
            )
    if manifest is None:
        raise RuntimeError("publishable analysis lacks a sealed manifest")
    completed_at = datetime.now(timezone.utc)
    published_at = datetime.now(timezone.utc)
    result_configuration = result.configuration
    policy_flags = list(policy_result.quality_flags) if policy_result is not None else []
    provenance = Provenance(
        producer_version=settings.producer_version,
        code_revision=settings.code_revision,
        llm_provider=(
            result_configuration.get("llm_provider", settings.llm_provider)
            if settings.research_mode == "tradingagents" else "synthetic"
        ),
        deep_model=result_configuration.get("deep_think_llm", settings.deep_model),
        quick_model=result_configuration.get("quick_think_llm", settings.quick_model),
        configuration_hash=configuration_hash(result_configuration),
        data_as_of=(
            policy_result.data_as_of if policy_result is not None
            else min(job["candle_close_at"], completed_at)
        ),
        quality_flags=policy_flags if policy_result is not None else ["synthetic"],
    )
    payload = SignalPayload(
        run_id=run_id,
        correlation_id=job["correlation_id"],
        instrument_id=job["instrument_id"],
        execution_snapshot_id=job["execution_snapshot_id"],
        evidence_manifest_id=manifest.manifest_id,
        source_policy_result_digest=(
            policy_result.result_digest if policy_result is not None else None
        ),
        environment=settings.environment,
        bot_id=settings.bot_id,
        exchange=settings.exchange,
        pair=job["pair"],
        timeframe=job["timeframe"],
        sequence=1,
        candle_close_at=job["candle_close_at"],
        analysis_started_at=max(started_at, job["candle_close_at"]),
        analysis_completed_at=completed_at,
        published_at=published_at,
        signal_available_at=published_at,
        expires_at=published_at + timedelta(seconds=settings.signal_ttl_seconds),
        decision=result.decision,
        sentiment=result.sentiment,
        normalized_rating_score=RATING_SCORE[result.decision.rating],
        provenance=provenance,
    )
    envelope = SignedEnvelope.sign(payload, settings.hmac_secret)
    lease.ensure_owned()
    persist_signal_and_outbox(
        connection,
        envelope,
        {
            "job_id": job["job_id"],
            "worker_id": worker_id,
            "attempt": job["attempt"],
            "fencing_token": job["fencing_token"],
            "hmac_secret": settings.hmac_secret,
            "configuration": result.configuration,
            "raw_state": result.raw_state,
            "report_path": result.report_path,
        },
    )


def process_one(settings: Settings, worker_id: str) -> bool:
    with connect(settings.database_url) as connection:
        recover_expired_analysis_jobs(
            connection,
            {
                "environment": settings.environment,
                "bot_id": settings.bot_id,
                "hmac_secret": settings.hmac_secret,
                "producer_version": settings.producer_version,
                "code_revision": settings.code_revision,
            },
        )
        job = claim_analysis_job(connection, worker_id, settings.analysis_lease_seconds)
        if job is None:
            return False
        checkpoint("worker.after_claim")
        started_at = datetime.now(timezone.utc)
        run_id = uuid4()
        capture_session: CaptureSession | None = None
        fence: CaptureFence | None = None
        revocation_context: dict | None = None
        try:
            create_analysis_attempt(
                connection,
                run_id=run_id,
                job=job,
                started_at=started_at,
                producer_version=settings.producer_version,
                code_revision=settings.code_revision,
                configuration={"research_mode": settings.research_mode},
            )
            checkpoint("worker.after_run_creation")
            if not job.get("instrument_id") or not job.get("execution_snapshot_id"):
                raise RuntimeError("analysis job is not backed by an execution snapshot")
            with LeaseRenewer(settings, job, worker_id) as lease:
                if settings.research_mode == "synthetic":
                    result = synthetic_result(job["symbol"])
                    policy_result = None
                    manifest = None
                elif settings.research_mode == "tradingagents":
                    if settings.tradingagents_commit != PINNED_COMMIT:
                        raise RuntimeError(
                            "configured TradingAgents commit does not match the audited adapter"
                        )
                    vendor_plan = {
                        method: rule.vendors for method, rule in ALLOWED_INGRESS.items()
                    }
                    graph_configuration = build_tradingagents_configuration(
                        settings, vendor_plan
                    )
                    capture_started_at = datetime.now(timezone.utc)
                    deadline_at = min(
                        capture_started_at + timedelta(
                            seconds=settings.capture_deadline_seconds
                        ),
                        job["lease_expires_at"],
                    )
                    if deadline_at <= capture_started_at:
                        raise RuntimeError("capture deadline is already exhausted")
                    capture_session = CaptureSession(
                        run_id=run_id,
                        manifest_id=uuid4(),
                        instrument_id=job["instrument_id"],
                        execution_snapshot_id=job["execution_snapshot_id"],
                        job_id=job["job_id"],
                        job_attempt=job["attempt"],
                        fencing_token=job["fencing_token"],
                        mode="live_capture",
                        upstream_version=PINNED_VERSION,
                        upstream_commit=PINNED_COMMIT,
                        adapter_version=settings.capture_adapter_version,
                        configuration_hash=configuration_hash(graph_configuration),
                        started_at=capture_started_at,
                        deadline_at=deadline_at,
                    )
                    revocation_context = {
                        "environment": settings.environment,
                        "bot_id": settings.bot_id,
                        "exchange": settings.exchange,
                        "pair": job["pair"],
                        "timeframe": job["timeframe"],
                        "correlation_id": job["correlation_id"],
                        "instrument_id": job["instrument_id"],
                        "execution_snapshot_id": job["execution_snapshot_id"],
                        "evidence_manifest_id": capture_session.manifest_id,
                        "producer_version": settings.producer_version,
                        "code_revision": settings.code_revision,
                        "hmac_secret": settings.hmac_secret,
                        "reason_code": "worker.analysis_failed",
                    }
                    fence = CaptureFence(
                        job_id=job["job_id"], worker_id=worker_id,
                        attempt=job["attempt"], fencing_token=job["fencing_token"],
                    )
                    required_sources = {
                        method: (
                            "available" if method in {
                                "resolve_instrument_identity", "get_stock_data",
                                "get_verified_market_snapshot",
                            }
                            else "degraded" if method in {
                                "get_indicators", "get_news", "get_global_news",
                                "fetch_stocktwits_messages", "fetch_reddit_posts",
                            }
                            else "missing"
                        )
                        for method in ALLOWED_INGRESS
                    }
                    with connection.transaction():
                        start_capture_session(
                            connection,
                            capture_session,
                            configured_vendors=vendor_plan,
                            required_sources=required_sources,
                            worker_id=worker_id,
                        )
                    checkpoint("worker.after_capture_creation")
                    settings.artifact_dir.mkdir(parents=True, exist_ok=True)
                    adapter = TradingAgentsCaptureAdapter(
                        settings.database_url,
                        settings.artifact_dir,
                        capture_session.session_id,
                    )
                    result = run_tradingagents(
                        job["symbol"],
                        job["candle_close_at"].astimezone(timezone.utc).date().isoformat(),
                        settings,
                        adapter,
                        graph_configuration,
                    )
                    lease.ensure_owned()
                    terminal: tuple[str, str] | None = None
                    with connection.transaction():
                        begin_capture_evaluation(
                            connection, capture_session.session_id, fence
                        )
                        checkpoint("worker.after_collection_close")
                        policy_result, manifest = evaluate_and_finalize_capture(
                            connection,
                            capture_session.session_id,
                            fence,
                            settings.artifact_dir,
                            SourcePolicyConfiguration(
                                expected_timeframe=settings.timeframe,
                                allowed_clock_skew_seconds=settings.clock_skew_seconds,
                                max_abs_clock_offset_ms=settings.max_clock_offset_ms,
                            ),
                        )
                        checkpoint("worker.before_terminal_commit")
                        lease.ensure_owned()
                        if policy_result.verdict == PolicyVerdict.REJECT:
                            failed_rule = next(
                                rule for rule in policy_result.rules
                                if rule.outcome == RuleOutcome.FAIL
                            )
                            complete_analysis_without_signal(
                                connection,
                                job_id=job["job_id"], run_id=run_id,
                                worker_id=worker_id, attempt=job["attempt"],
                                fencing_token=job["fencing_token"],
                                outcome_code=failed_rule.code,
                                policy_result_digest=policy_result.result_digest,
                                denied_rating=result.decision.rating,
                                revocation_context=revocation_context,
                            )
                            terminal = ("policy", failed_rule.code)
                        elif result.decision.rating.value not in policy_result.permitted_ratings:
                            complete_analysis_without_signal(
                                connection,
                                job_id=job["job_id"], run_id=run_id,
                                worker_id=worker_id, attempt=job["attempt"],
                                fencing_token=job["fencing_token"],
                                outcome_code="publication.rating_not_permitted",
                                policy_result_digest=policy_result.result_digest,
                                denied_rating=result.decision.rating,
                                revocation_context=revocation_context,
                            )
                            terminal = ("rating", "publication.rating_not_permitted")
                        else:
                            _persist_publishable_result(
                                connection,
                                settings=settings,
                                job=job,
                                worker_id=worker_id,
                                run_id=run_id,
                                started_at=started_at,
                                result=result,
                                manifest=manifest,
                                policy_result=policy_result,
                                lease=lease,
                            )
                    checkpoint("worker.after_terminal_commit")
                    if terminal is not None:
                        message = (
                            "analysis rejected by source policy"
                            if terminal[0] == "policy"
                            else "analysis produced no policy-permitted signal"
                        )
                        logger.info(
                            message,
                            extra={"job_id": str(job["job_id"]), "code": terminal[1]},
                        )
                        return True
                else:
                    raise ValueError(f"unsupported research mode: {settings.research_mode}")
                if settings.research_mode == "synthetic":
                    with connection.transaction():
                        checkpoint("worker.before_terminal_commit")
                        _persist_publishable_result(
                            connection,
                            settings=settings,
                            job=job,
                            worker_id=worker_id,
                            run_id=run_id,
                            started_at=started_at,
                            result=result,
                            manifest=manifest,
                            policy_result=policy_result,
                            lease=lease,
                        )
                    checkpoint("worker.after_terminal_commit")
            logger.info("analysis committed", extra={"job_id": str(job["job_id"]), "run_id": str(run_id)})
            return True
        except Exception as exc:
            logger.exception("analysis failed", extra={"job_id": str(job["job_id"])})
            connection.rollback()
            failure_recorded = False
            if capture_session is not None and fence is not None:
                try:
                    with connection.transaction():
                        reject_capture_session(
                            connection,
                            capture_session.session_id,
                            "worker.analysis_failed",
                            fence,
                        )
                        failure_recorded = fail_analysis_job(
                            connection,
                            job_id=job["job_id"],
                            run_id=run_id,
                            error_code="analysis_failed",
                            error_metadata={"exception_type": type(exc).__name__},
                            attempt=job["attempt"],
                            worker_id=worker_id,
                            fencing_token=job["fencing_token"],
                            revocation_context=revocation_context,
                        )
                        if not failure_recorded:
                            raise RuntimeError("analysis attempt lost its fence during failure")
                except Exception:
                    connection.rollback()
                    logger.exception(
                        "failed to atomically reject capture and record failure",
                        extra={"session_id": str(capture_session.session_id)},
                    )
            if not failure_recorded:
                fail_analysis_job(
                    connection,
                    job_id=job["job_id"],
                    run_id=run_id,
                    error_code="analysis_failed",
                    error_metadata={"exception_type": type(exc).__name__},
                    attempt=job["attempt"],
                    worker_id=worker_id,
                    fencing_token=job["fencing_token"],
                    revocation_context=revocation_context,
                )
            return True


def main() -> None:
    settings = Settings()
    migrate(settings.database_url)
    worker_id = os.getenv("HOSTNAME", socket.gethostname())
    while True:
        worked = process_one(settings, worker_id)
        if not worked:
            time.sleep(2)


if __name__ == "__main__":
    main()
