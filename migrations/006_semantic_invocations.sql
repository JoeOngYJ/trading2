-- Separate graph-level values from the vendor attempts used to produce them.
ALTER TABLE capture_sessions
    ADD COLUMN IF NOT EXISTS next_invocation_ordinal integer NOT NULL DEFAULT 0
        CHECK (next_invocation_ordinal >= 0);

DO $$
DECLARE constraint_row record;
BEGIN
    FOR constraint_row IN
        SELECT conname
        FROM pg_constraint
        WHERE conrelid = 'capture_sessions'::regclass
          AND contype = 'c'
          AND pg_get_constraintdef(oid) ILIKE '%status%'
    LOOP
        EXECUTE format(
            'ALTER TABLE capture_sessions DROP CONSTRAINT %I',
            constraint_row.conname
        );
    END LOOP;
END;
$$;

ALTER TABLE capture_sessions
    ADD CONSTRAINT capture_sessions_status_v2_check
        CHECK (status IN ('collecting','evaluating','sealed','rejected','abandoned')),
    ADD CONSTRAINT capture_sessions_state_v2_check CHECK (
        (status IN ('collecting','evaluating') AND completed_at IS NULL AND rejection_code IS NULL)
        OR (status = 'sealed' AND completed_at IS NOT NULL AND rejection_code IS NULL)
        OR (status IN ('rejected','abandoned') AND completed_at IS NOT NULL
            AND rejection_code IS NOT NULL)
    );

ALTER TABLE source_calls DROP CONSTRAINT IF EXISTS source_calls_outcome_check;
ALTER TABLE source_calls DROP CONSTRAINT IF EXISTS source_calls_outcome_v2_check;
ALTER TABLE source_calls ADD CONSTRAINT source_calls_outcome_v2_check CHECK (
    outcome IN ('available','no_data','unavailable','timeout','rate_limited','auth_error',
                'vendor_error','policy_rejected','invalid_response')
);

CREATE TABLE IF NOT EXISTS semantic_invocations (
    invocation_id uuid PRIMARY KEY,
    session_id uuid NOT NULL REFERENCES capture_sessions(session_id),
    ordinal integer NOT NULL CHECK (ordinal >= 0),
    method text NOT NULL,
    category text NOT NULL CHECK (
        category IN ('research_market','news','social','macro','prediction','fundamental')
    ),
    policy_subject text NOT NULL,
    consumer text NOT NULL,
    sanitized_arguments jsonb NOT NULL,
    arguments_hash text NOT NULL CHECK (arguments_hash ~ '^sha256:[0-9a-f]{64}$'),
    started_at timestamptz NOT NULL,
    completed_at timestamptz,
    first_seen_at timestamptz,
    information_cutoff_at timestamptz,
    outcome text CHECK (
        outcome IN ('available','no_data','unavailable','timeout','rate_limited','auth_error',
                    'vendor_error','policy_rejected','invalid_response')
    ),
    error_code text,
    normalized_artifact_digest text REFERENCES artifacts(digest),
    observation_id uuid REFERENCES source_observations(observation_id),
    typed_metadata jsonb,
    replay_safe boolean,
    replay_unsafe_reason text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (session_id, ordinal),
    UNIQUE (invocation_id, session_id),
    CHECK (
        (completed_at IS NULL AND first_seen_at IS NULL AND outcome IS NULL
         AND error_code IS NULL AND normalized_artifact_digest IS NULL
         AND observation_id IS NULL AND typed_metadata IS NULL AND replay_safe IS NULL)
        OR
        (completed_at IS NOT NULL AND first_seen_at IS NOT NULL AND outcome IS NOT NULL
         AND typed_metadata IS NOT NULL AND replay_safe IS NOT NULL
         AND completed_at >= first_seen_at AND first_seen_at >= started_at)
    ),
    CHECK (
        outcome IS NULL
        OR (outcome = 'available' AND normalized_artifact_digest IS NOT NULL
            AND observation_id IS NOT NULL AND error_code IS NULL)
        OR (outcome IN ('no_data','unavailable') AND normalized_artifact_digest IS NOT NULL
            AND observation_id IS NOT NULL AND error_code IS NOT NULL)
        OR (outcome NOT IN ('available','no_data','unavailable') AND error_code IS NOT NULL)
    ),
    CHECK (replay_safe IS DISTINCT FROM false OR replay_unsafe_reason IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS vendor_attempts (
    attempt_id uuid PRIMARY KEY,
    invocation_id uuid NOT NULL,
    session_id uuid NOT NULL,
    fallback_ordinal integer NOT NULL CHECK (fallback_ordinal >= 0),
    vendor text NOT NULL,
    started_at timestamptz NOT NULL,
    completed_at timestamptz NOT NULL,
    first_seen_at timestamptz NOT NULL,
    latency_ms bigint GENERATED ALWAYS AS (
        GREATEST(0, floor(extract(epoch FROM (completed_at - started_at)) * 1000)::bigint)
    ) STORED,
    outcome text NOT NULL CHECK (
        outcome IN ('available','no_data','unavailable','timeout','rate_limited','auth_error',
                    'vendor_error','policy_rejected','invalid_response')
    ),
    error_code text,
    raw_artifact_digest text REFERENCES artifacts(digest),
    normalized_artifact_digest text REFERENCES artifacts(digest),
    observation_id uuid REFERENCES source_observations(observation_id),
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (invocation_id,session_id)
        REFERENCES semantic_invocations(invocation_id,session_id),
    UNIQUE (invocation_id, fallback_ordinal),
    CHECK (completed_at >= first_seen_at AND first_seen_at >= started_at),
    CHECK (
        (outcome = 'available' AND normalized_artifact_digest IS NOT NULL
         AND observation_id IS NOT NULL AND error_code IS NULL)
        OR (outcome <> 'available' AND error_code IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS semantic_invocations_session_idx
    ON semantic_invocations(session_id,ordinal);
CREATE INDEX IF NOT EXISTS vendor_attempts_invocation_idx
    ON vendor_attempts(invocation_id,fallback_ordinal);
CREATE INDEX IF NOT EXISTS vendor_attempts_vendor_outcome_idx
    ON vendor_attempts(vendor,outcome,completed_at DESC);

CREATE OR REPLACE FUNCTION reject_closed_session_evidence_change() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    parent_status text;
    parent_id uuid;
BEGIN
    IF TG_OP = 'DELETE' THEN
        parent_id := OLD.session_id;
    ELSE
        parent_id := NEW.session_id;
    END IF;
    SELECT status INTO parent_status FROM capture_sessions WHERE session_id=parent_id;
    IF parent_status <> 'collecting' THEN
        RAISE EXCEPTION 'capture evidence is immutable when session % is %',
            parent_id, parent_status;
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS semantic_invocations_immutable ON semantic_invocations;
CREATE TRIGGER semantic_invocations_immutable
BEFORE INSERT OR UPDATE OR DELETE ON semantic_invocations
FOR EACH ROW EXECUTE FUNCTION reject_closed_session_evidence_change();

DROP TRIGGER IF EXISTS vendor_attempts_immutable ON vendor_attempts;
CREATE TRIGGER vendor_attempts_immutable
BEFORE INSERT OR UPDATE OR DELETE ON vendor_attempts
FOR EACH ROW EXECUTE FUNCTION reject_closed_session_evidence_change();

CREATE OR REPLACE FUNCTION enforce_capture_session_transition() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'capture sessions cannot be deleted';
    END IF;
    IF OLD.status NOT IN ('collecting','evaluating') THEN
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
    IF OLD.status = 'collecting' AND NEW.status = 'collecting' THEN
        IF (NEW.next_call_ordinal - OLD.next_call_ordinal)
             + (NEW.next_invocation_ordinal - OLD.next_invocation_ordinal) <> 1
           OR NEW.next_call_ordinal < OLD.next_call_ordinal
           OR NEW.next_invocation_ordinal < OLD.next_invocation_ordinal
           OR NEW.completed_at IS DISTINCT FROM OLD.completed_at
           OR NEW.rejection_code IS DISTINCT FROM OLD.rejection_code THEN
            RAISE EXCEPTION 'only one evidence ordinal may be allocated while collecting';
        END IF;
        RETURN NEW;
    END IF;
    IF OLD.status = 'collecting' AND NEW.status = 'evaluating' THEN
        IF NEW.next_call_ordinal <> OLD.next_call_ordinal
           OR NEW.next_invocation_ordinal <> OLD.next_invocation_ordinal
           OR NEW.completed_at IS NOT NULL OR NEW.rejection_code IS NOT NULL THEN
            RAISE EXCEPTION 'invalid collection close';
        END IF;
        RETURN NEW;
    END IF;
    IF NEW.status NOT IN ('sealed','rejected','abandoned')
       OR NEW.next_call_ordinal <> OLD.next_call_ordinal
       OR NEW.next_invocation_ordinal <> OLD.next_invocation_ordinal THEN
        RAISE EXCEPTION 'invalid capture session transition: % to %', OLD.status, NEW.status;
    END IF;
    RETURN NEW;
END;
$$;
