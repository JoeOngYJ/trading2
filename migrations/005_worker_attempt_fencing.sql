ALTER TABLE analysis_jobs
    ADD COLUMN IF NOT EXISTS fencing_token bigint NOT NULL DEFAULT 0
        CHECK (fencing_token >= 0);

ALTER TABLE analysis_runs
    ADD COLUMN IF NOT EXISTS attempt integer CHECK (attempt > 0),
    ADD COLUMN IF NOT EXISTS fencing_token bigint CHECK (fencing_token > 0),
    ADD COLUMN IF NOT EXISTS capture_session_id uuid REFERENCES capture_sessions(session_id),
    ADD COLUMN IF NOT EXISTS evidence_manifest_id uuid REFERENCES evidence_manifests(manifest_id),
    ADD COLUMN IF NOT EXISTS error_code text,
    ADD COLUMN IF NOT EXISTS error_metadata jsonb;

CREATE UNIQUE INDEX IF NOT EXISTS analysis_runs_job_attempt_idx
    ON analysis_runs(job_id, attempt) WHERE attempt IS NOT NULL;

ALTER TABLE capture_sessions
    ADD COLUMN IF NOT EXISTS job_id uuid REFERENCES analysis_jobs(job_id),
    ADD COLUMN IF NOT EXISTS job_attempt integer CHECK (job_attempt > 0),
    ADD COLUMN IF NOT EXISTS fencing_token bigint CHECK (fencing_token > 0);

CREATE UNIQUE INDEX IF NOT EXISTS capture_sessions_job_attempt_idx
    ON capture_sessions(job_id, job_attempt) WHERE job_id IS NOT NULL;

ALTER TABLE analysis_runs DROP CONSTRAINT IF EXISTS analysis_runs_outcome_check;
ALTER TABLE analysis_runs ADD CONSTRAINT analysis_runs_outcome_check
    CHECK (outcome IN ('running','succeeded','failed','rejected','abandoned'));

CREATE OR REPLACE FUNCTION enforce_capture_session_transition() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'capture sessions cannot be deleted';
    END IF;
    IF OLD.status <> 'collecting' THEN
        RAISE EXCEPTION 'capture session % is immutable in status %', OLD.session_id, OLD.status;
    END IF;
    IF ROW(NEW.session_id,NEW.run_id,NEW.manifest_id,NEW.instrument_id,
           NEW.execution_snapshot_id,NEW.mode,NEW.upstream_version,NEW.upstream_commit,
           NEW.adapter_version,NEW.configuration_hash,NEW.started_at,NEW.deadline_at,
           NEW.replay_source_session_id,NEW.job_id,NEW.job_attempt,NEW.fencing_token)
       IS DISTINCT FROM
       ROW(OLD.session_id,OLD.run_id,OLD.manifest_id,OLD.instrument_id,
           OLD.execution_snapshot_id,OLD.mode,OLD.upstream_version,OLD.upstream_commit,
           OLD.adapter_version,OLD.configuration_hash,OLD.started_at,OLD.deadline_at,
           OLD.replay_source_session_id,OLD.job_id,OLD.job_attempt,OLD.fencing_token) THEN
        RAISE EXCEPTION 'capture session identity and configuration are immutable';
    END IF;
    IF NEW.status = 'collecting' THEN
        IF NEW.next_call_ordinal <> OLD.next_call_ordinal + 1
           OR NEW.completed_at IS DISTINCT FROM OLD.completed_at
           OR NEW.rejection_code IS DISTINCT FROM OLD.rejection_code THEN
            RAISE EXCEPTION 'only one call ordinal may be allocated while collecting';
        END IF;
        RETURN NEW;
    END IF;
    IF NEW.status NOT IN ('sealed','rejected','abandoned')
       OR NEW.next_call_ordinal <> OLD.next_call_ordinal THEN
        RAISE EXCEPTION 'invalid capture session transition: % to %', OLD.status, NEW.status;
    END IF;
    RETURN NEW;
END;
$$;
