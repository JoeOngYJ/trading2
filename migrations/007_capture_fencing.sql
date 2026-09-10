-- Bind every new capture session to one durable analysis attempt.
UPDATE capture_sessions AS session
SET job_id=run.job_id,
    job_attempt=run.attempt,
    fencing_token=run.fencing_token
FROM analysis_runs AS run
WHERE run.run_id=session.run_id
  AND session.job_id IS NULL
  AND run.attempt IS NOT NULL
  AND run.fencing_token IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS analysis_runs_capture_identity_idx
    ON analysis_runs(run_id,job_id,attempt,fencing_token);

ALTER TABLE capture_sessions
    DROP CONSTRAINT IF EXISTS capture_sessions_run_attempt_fkey;
ALTER TABLE capture_sessions
    ADD CONSTRAINT capture_sessions_run_attempt_fkey
    FOREIGN KEY (run_id,job_id,job_attempt,fencing_token)
    REFERENCES analysis_runs(run_id,job_id,attempt,fencing_token)
    NOT VALID;

ALTER TABLE capture_sessions
    DROP CONSTRAINT IF EXISTS capture_sessions_fence_complete_check;
ALTER TABLE capture_sessions
    ADD CONSTRAINT capture_sessions_fence_complete_check CHECK (
        (job_id IS NULL AND job_attempt IS NULL AND fencing_token IS NULL)
        OR (job_id IS NOT NULL AND job_attempt IS NOT NULL AND fencing_token IS NOT NULL)
    );

CREATE OR REPLACE FUNCTION require_capture_fence_on_insert() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.job_id IS NULL OR NEW.job_attempt IS NULL OR NEW.fencing_token IS NULL THEN
        RAISE EXCEPTION 'new capture sessions require complete fenced attempt identity';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS capture_sessions_require_fence ON capture_sessions;
CREATE TRIGGER capture_sessions_require_fence
BEFORE INSERT ON capture_sessions
FOR EACH ROW EXECUTE FUNCTION require_capture_fence_on_insert();
