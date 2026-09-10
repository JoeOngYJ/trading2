ALTER TABLE capture_sessions
    ADD COLUMN IF NOT EXISTS next_call_ordinal integer NOT NULL DEFAULT 0
        CHECK (next_call_ordinal >= 0),
    ADD COLUMN IF NOT EXISTS replay_source_session_id uuid REFERENCES capture_sessions(session_id);

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
           NEW.replay_source_session_id)
       IS DISTINCT FROM
       ROW(OLD.session_id,OLD.run_id,OLD.manifest_id,OLD.instrument_id,
           OLD.execution_snapshot_id,OLD.mode,OLD.upstream_version,OLD.upstream_commit,
           OLD.adapter_version,OLD.configuration_hash,OLD.started_at,OLD.deadline_at,
           OLD.replay_source_session_id) THEN
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
