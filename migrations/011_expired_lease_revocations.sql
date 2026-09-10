ALTER TABLE signal_revocations ALTER COLUMN evidence_manifest_id DROP NOT NULL;

CREATE OR REPLACE FUNCTION enforce_signed_revocation() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    target record;
    attempt record;
BEGIN
    IF NEW.event_id::text IS DISTINCT FROM NEW.envelope #>> '{payload,event_id}'
       OR NEW.revocation_id::text IS DISTINCT FROM NEW.envelope #>> '{payload,revocation_id}'
       OR NEW.signal_id::text IS DISTINCT FROM NEW.envelope #>> '{payload,signal_id}'
       OR NEW.target_sequence IS DISTINCT FROM (NEW.envelope #>> '{payload,target_sequence}')::bigint
       OR NEW.target_checksum IS DISTINCT FROM NEW.envelope #>> '{payload,target_checksum}'
       OR NEW.run_id::text IS DISTINCT FROM NEW.envelope #>> '{payload,run_id}'
       OR NEW.instrument_id IS DISTINCT FROM NEW.envelope #>> '{payload,instrument_id}'
       OR NEW.execution_snapshot_id::text IS DISTINCT FROM NEW.envelope #>> '{payload,execution_snapshot_id}'
       OR NEW.evidence_manifest_id::text IS DISTINCT FROM NEW.envelope #>> '{payload,evidence_manifest_id}'
       OR NEW.environment IS DISTINCT FROM NEW.envelope #>> '{payload,environment}'
       OR NEW.bot_id IS DISTINCT FROM NEW.envelope #>> '{payload,bot_id}'
       OR NEW.exchange IS DISTINCT FROM NEW.envelope #>> '{payload,exchange}'
       OR NEW.pair IS DISTINCT FROM NEW.envelope #>> '{payload,pair}'
       OR NEW.timeframe IS DISTINCT FROM NEW.envelope #>> '{payload,timeframe}'
       OR NEW.sequence IS DISTINCT FROM (NEW.envelope #>> '{payload,sequence}')::bigint
       OR NEW.reason_code IS DISTINCT FROM NEW.envelope #>> '{payload,reason_code}'
       OR NEW.denied_rating IS DISTINCT FROM NEW.envelope #>> '{payload,denied_rating}'
       OR NEW.source_policy_result_digest IS DISTINCT FROM NEW.envelope #>> '{payload,source_policy_result_digest}'
       OR NEW.checksum IS DISTINCT FROM NEW.envelope #>> '{checksum}'
       OR NEW.envelope #>> '{payload,event_type}' <> 'signal.revoked' THEN
        RAISE EXCEPTION 'revocation columns do not match the signed envelope';
    END IF;

    SELECT environment,bot_id,exchange,pair,timeframe,sequence,checksum,
           envelope #>> '{payload,decision,rating}' AS rating
    INTO target FROM signals
    WHERE signal_id=NEW.signal_id AND status='valid'
      AND envelope #>> '{payload,event_type}'='signal.created';
    IF target.environment IS NULL
       OR ROW(target.environment,target.bot_id,target.exchange,target.pair,target.timeframe,
              target.sequence,target.checksum)
          IS DISTINCT FROM ROW(NEW.environment,NEW.bot_id,NEW.exchange,NEW.pair,NEW.timeframe,
                               NEW.target_sequence,NEW.target_checksum)
       OR target.rating='Hold' THEN
        RAISE EXCEPTION 'revocation target is missing, mismatched, or non-actionable';
    END IF;
    IF EXISTS (
        SELECT 1 FROM signals WHERE environment=NEW.environment AND bot_id=NEW.bot_id
          AND exchange=NEW.exchange AND pair=NEW.pair AND timeframe=NEW.timeframe
          AND sequence>NEW.target_sequence AND sequence<NEW.sequence
    ) OR EXISTS (
        SELECT 1 FROM signal_revocations WHERE environment=NEW.environment AND bot_id=NEW.bot_id
          AND exchange=NEW.exchange AND pair=NEW.pair AND timeframe=NEW.timeframe
          AND sequence>NEW.target_sequence AND sequence<NEW.sequence
    ) THEN
        RAISE EXCEPTION 'revocation does not target the latest durable event';
    END IF;

    SELECT run.evidence_manifest_id AS run_manifest,run.capture_session_id AS run_session,
           run.outcome AS run_outcome,run.attempt AS run_attempt,run.fencing_token AS run_fence,
           job.status AS job_status,job.attempt AS job_attempt,job.fencing_token AS job_fence,
           job.lease_expires_at,job.instrument_id AS job_instrument,
           job.execution_snapshot_id AS job_snapshot,manifest.status AS manifest_status,
           manifest.instrument_id AS manifest_instrument,
           manifest.execution_snapshot_id AS manifest_snapshot,session.status AS capture_status,
           session.rejection_code AS capture_rejection,evaluation.verdict AS evaluation_verdict,
           evaluation.permitted_ratings AS evaluation_ratings,
           evaluation.result_digest AS evaluation_digest,snapshot.exchange AS snapshot_exchange,
           snapshot.pair AS snapshot_pair,snapshot.timeframe AS snapshot_timeframe
    INTO attempt
    FROM analysis_runs AS run
    JOIN analysis_jobs AS job ON job.job_id=run.job_id
    JOIN execution_market_snapshots AS snapshot ON snapshot.snapshot_id=job.execution_snapshot_id
    LEFT JOIN evidence_manifests AS manifest ON manifest.manifest_id=NEW.evidence_manifest_id
                                             AND manifest.run_id=run.run_id
    LEFT JOIN capture_sessions AS session ON session.session_id=run.capture_session_id
    LEFT JOIN source_policy_evaluations AS evaluation
      ON evaluation.session_id=session.session_id AND evaluation.manifest_id=manifest.manifest_id
    WHERE run.run_id=NEW.run_id;

    IF attempt.run_outcome<>'running' OR attempt.job_status<>'running'
       OR attempt.run_attempt IS DISTINCT FROM attempt.job_attempt
       OR attempt.run_fence IS DISTINCT FROM attempt.job_fence
       OR attempt.job_instrument IS DISTINCT FROM NEW.instrument_id
       OR attempt.job_snapshot IS DISTINCT FROM NEW.execution_snapshot_id
       OR attempt.snapshot_exchange IS DISTINCT FROM NEW.exchange
       OR attempt.snapshot_pair IS DISTINCT FROM NEW.pair
       OR attempt.snapshot_timeframe IS DISTINCT FROM NEW.timeframe
       OR (NEW.reason_code='worker_lease_expired' AND attempt.lease_expires_at>=now())
       OR (NEW.reason_code<>'worker_lease_expired' AND attempt.lease_expires_at<=now()) THEN
        RAISE EXCEPTION 'revocation is not owned by the required fenced analysis attempt';
    END IF;
    IF NEW.evidence_manifest_id IS NULL THEN
        IF attempt.run_manifest IS NOT NULL OR attempt.run_session IS NOT NULL
           OR NEW.source_policy_result_digest IS NOT NULL THEN
            RAISE EXCEPTION 'manifest-free revocation does not match attempt lineage';
        END IF;
    ELSIF attempt.run_manifest IS DISTINCT FROM NEW.evidence_manifest_id
       OR attempt.manifest_instrument IS DISTINCT FROM NEW.instrument_id
       OR attempt.manifest_snapshot IS DISTINCT FROM NEW.execution_snapshot_id THEN
        RAISE EXCEPTION 'revocation manifest does not match attempt lineage';
    END IF;

    IF EXISTS (SELECT 1 FROM signals WHERE environment=NEW.environment AND bot_id=NEW.bot_id
      AND exchange=NEW.exchange AND pair=NEW.pair AND timeframe=NEW.timeframe AND sequence=NEW.sequence)
       OR EXISTS (SELECT 1 FROM signal_revocations WHERE environment=NEW.environment
      AND bot_id=NEW.bot_id AND exchange=NEW.exchange AND pair=NEW.pair
      AND timeframe=NEW.timeframe AND sequence=NEW.sequence AND revocation_id<>NEW.revocation_id) THEN
        RAISE EXCEPTION 'revocation sequence is already occupied';
    END IF;

    IF NEW.source_policy_result_digest IS NOT NULL THEN
        IF attempt.evaluation_digest IS DISTINCT FROM NEW.source_policy_result_digest THEN
            RAISE EXCEPTION 'revocation policy digest does not match the current run';
        ELSIF attempt.evaluation_verdict='reject' THEN
            IF attempt.capture_status<>'rejected' OR attempt.manifest_status<>'rejected'
               OR attempt.capture_rejection IS DISTINCT FROM NEW.reason_code THEN
                RAISE EXCEPTION 'rejected-policy revocation has invalid terminal evidence';
            END IF;
        ELSIF NEW.denied_rating IS NULL OR attempt.evaluation_ratings ? NEW.denied_rating
           OR attempt.capture_status<>'sealed' OR attempt.manifest_status<>'sealed'
           OR NEW.reason_code<>'publication.rating_not_permitted' THEN
            RAISE EXCEPTION 'rating revocation is not denied by source policy';
        END IF;
    ELSIF NEW.reason_code='worker_lease_expired' THEN
        IF NEW.evidence_manifest_id IS NOT NULL AND NOT (
            attempt.capture_status='abandoned' AND attempt.manifest_status='rejected'
            AND attempt.capture_rejection='worker_lease_expired'
        ) THEN RAISE EXCEPTION 'expired-lease revocation lacks terminal capture evidence'; END IF;
    ELSIF NEW.reason_code<>'worker.analysis_failed' OR NOT (
        (attempt.capture_status='rejected' AND attempt.manifest_status='rejected'
         AND attempt.capture_rejection=NEW.reason_code)
        OR (attempt.capture_status='sealed' AND attempt.manifest_status='sealed')
    ) THEN
        RAISE EXCEPTION 'operational revocation lacks a rejected capture';
    END IF;
    RETURN NEW;
END;
$$;
