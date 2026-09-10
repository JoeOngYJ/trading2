ALTER TABLE evidence_manifests
    ADD COLUMN IF NOT EXISTS capture_session_id uuid,
    ADD COLUMN IF NOT EXISTS call_ledger_digest text
        CHECK (call_ledger_digest IS NULL OR call_ledger_digest ~ '^sha256:[0-9a-f]{64}$');

CREATE TABLE IF NOT EXISTS capture_sessions (
    session_id uuid PRIMARY KEY,
    run_id uuid NOT NULL UNIQUE,
    manifest_id uuid NOT NULL UNIQUE REFERENCES evidence_manifests(manifest_id),
    instrument_id text NOT NULL REFERENCES instruments(instrument_id),
    execution_snapshot_id uuid NOT NULL REFERENCES execution_market_snapshots(snapshot_id),
    mode text NOT NULL CHECK (mode IN ('live_capture','captured_replay')),
    status text NOT NULL CHECK (status IN ('collecting','sealed','rejected','abandoned')),
    upstream_version text NOT NULL,
    upstream_commit text NOT NULL CHECK (upstream_commit ~ '^[0-9a-f]{40}$'),
    adapter_version text NOT NULL,
    configuration_hash text NOT NULL CHECK (configuration_hash ~ '^[0-9a-f]{64}$'),
    started_at timestamptz NOT NULL,
    deadline_at timestamptz NOT NULL,
    completed_at timestamptz,
    rejection_code text,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (deadline_at > started_at),
    CHECK (
        (status = 'collecting' AND completed_at IS NULL AND rejection_code IS NULL)
        OR (status = 'sealed' AND completed_at IS NOT NULL AND rejection_code IS NULL)
        OR (status IN ('rejected','abandoned') AND completed_at IS NOT NULL AND rejection_code IS NOT NULL)
    )
);

ALTER TABLE evidence_manifests
    DROP CONSTRAINT IF EXISTS evidence_manifests_capture_session_id_fkey;
ALTER TABLE evidence_manifests
    ADD CONSTRAINT evidence_manifests_capture_session_id_fkey
    FOREIGN KEY (capture_session_id) REFERENCES capture_sessions(session_id)
    DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE IF NOT EXISTS source_calls (
    call_id uuid PRIMARY KEY,
    session_id uuid NOT NULL REFERENCES capture_sessions(session_id),
    ordinal integer NOT NULL CHECK (ordinal >= 0),
    method text NOT NULL,
    category text NOT NULL CHECK (
        category IN ('research_market','news','social','macro','prediction','fundamental')
    ),
    vendor text NOT NULL,
    fallback_ordinal integer NOT NULL DEFAULT 0 CHECK (fallback_ordinal >= 0),
    consumer text,
    sanitized_arguments jsonb NOT NULL,
    arguments_hash text NOT NULL CHECK (arguments_hash ~ '^sha256:[0-9a-f]{64}$'),
    started_at timestamptz NOT NULL,
    completed_at timestamptz NOT NULL,
    first_seen_at timestamptz NOT NULL,
    latency_ms bigint GENERATED ALWAYS AS (
        GREATEST(0, floor(extract(epoch FROM (completed_at - started_at)) * 1000)::bigint)
    ) STORED,
    outcome text NOT NULL CHECK (
        outcome IN ('available','no_data','timeout','rate_limited','auth_error',
                    'vendor_error','policy_rejected','invalid_response')
    ),
    error_code text,
    raw_artifact_digest text REFERENCES artifacts(digest),
    normalized_artifact_digest text REFERENCES artifacts(digest),
    observation_id uuid REFERENCES source_observations(observation_id),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (session_id, ordinal),
    CHECK (completed_at >= first_seen_at AND first_seen_at >= started_at),
    CHECK (
        (outcome = 'available' AND normalized_artifact_digest IS NOT NULL
         AND observation_id IS NOT NULL AND error_code IS NULL)
        OR (outcome <> 'available' AND error_code IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS source_calls_session_idx ON source_calls(session_id,ordinal);
CREATE INDEX IF NOT EXISTS source_calls_vendor_outcome_idx
    ON source_calls(vendor,outcome,completed_at DESC);

CREATE OR REPLACE FUNCTION reject_immutable_manifest_change() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.status IN ('sealed','rejected') THEN
        RAISE EXCEPTION 'evidence manifest % is immutable in status %', OLD.manifest_id, OLD.status;
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS evidence_manifests_immutable ON evidence_manifests;
CREATE TRIGGER evidence_manifests_immutable
BEFORE UPDATE OR DELETE ON evidence_manifests
FOR EACH ROW EXECUTE FUNCTION reject_immutable_manifest_change();

CREATE OR REPLACE FUNCTION reject_closed_manifest_child_change() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    parent_status text;
    parent_id uuid;
BEGIN
    IF TG_OP = 'DELETE' THEN
        parent_id := OLD.manifest_id;
    ELSE
        parent_id := NEW.manifest_id;
    END IF;
    SELECT status INTO parent_status FROM evidence_manifests WHERE manifest_id=parent_id;
    IF parent_status <> 'collecting' THEN
        RAISE EXCEPTION 'manifest observations are immutable when manifest % is %', parent_id, parent_status;
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS manifest_observations_immutable ON manifest_observations;
CREATE TRIGGER manifest_observations_immutable
BEFORE INSERT OR UPDATE OR DELETE ON manifest_observations
FOR EACH ROW EXECUTE FUNCTION reject_closed_manifest_child_change();

CREATE OR REPLACE FUNCTION reject_closed_session_call_change() RETURNS trigger
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
        RAISE EXCEPTION 'source calls are immutable when capture session % is %', parent_id, parent_status;
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS source_calls_immutable ON source_calls;
CREATE TRIGGER source_calls_immutable
BEFORE INSERT OR UPDATE OR DELETE ON source_calls
FOR EACH ROW EXECUTE FUNCTION reject_closed_session_call_change();

CREATE OR REPLACE FUNCTION enforce_capture_session_transition() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'capture sessions cannot be deleted';
    END IF;
    IF OLD.status <> 'collecting' THEN
        RAISE EXCEPTION 'capture session % is immutable in status %', OLD.session_id, OLD.status;
    END IF;
    IF NEW.status NOT IN ('sealed','rejected','abandoned') THEN
        RAISE EXCEPTION 'invalid capture session transition: % to %', OLD.status, NEW.status;
    END IF;
    IF ROW(NEW.session_id,NEW.run_id,NEW.manifest_id,NEW.instrument_id,
           NEW.execution_snapshot_id,NEW.mode,NEW.upstream_version,NEW.upstream_commit,
           NEW.adapter_version,NEW.configuration_hash,NEW.started_at,NEW.deadline_at)
       IS DISTINCT FROM
       ROW(OLD.session_id,OLD.run_id,OLD.manifest_id,OLD.instrument_id,
           OLD.execution_snapshot_id,OLD.mode,OLD.upstream_version,OLD.upstream_commit,
           OLD.adapter_version,OLD.configuration_hash,OLD.started_at,OLD.deadline_at) THEN
        RAISE EXCEPTION 'capture session identity and configuration are immutable';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS capture_sessions_transition ON capture_sessions;
CREATE TRIGGER capture_sessions_transition
BEFORE UPDATE OR DELETE ON capture_sessions
FOR EACH ROW EXECUTE FUNCTION enforce_capture_session_transition();
