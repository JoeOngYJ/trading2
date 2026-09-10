CREATE TABLE IF NOT EXISTS signal_revocations (
    revocation_id uuid PRIMARY KEY,
    event_id uuid NOT NULL UNIQUE,
    signal_id uuid NOT NULL REFERENCES signals(signal_id),
    target_sequence bigint NOT NULL CHECK (target_sequence > 0),
    target_checksum text NOT NULL CHECK (target_checksum ~ '^[0-9a-f]{64}$'),
    run_id uuid NOT NULL REFERENCES analysis_runs(run_id),
    correlation_id uuid NOT NULL,
    instrument_id text NOT NULL REFERENCES instruments(instrument_id),
    execution_snapshot_id uuid NOT NULL REFERENCES execution_market_snapshots(snapshot_id),
    evidence_manifest_id uuid NOT NULL REFERENCES evidence_manifests(manifest_id),
    source_policy_result_digest text REFERENCES source_policy_evaluations(result_digest),
    environment text NOT NULL,
    bot_id text NOT NULL,
    exchange text NOT NULL,
    pair text NOT NULL,
    timeframe text NOT NULL,
    sequence bigint NOT NULL CHECK (sequence > target_sequence),
    reason_code text NOT NULL CHECK (reason_code ~ '^[a-z][a-z0-9_.-]{2,127}$'),
    denied_rating text,
    published_at timestamptz NOT NULL,
    revoked_at timestamptz NOT NULL CHECK (revoked_at >= published_at),
    envelope jsonb NOT NULL,
    checksum text NOT NULL CHECK (checksum ~ '^[0-9a-f]{64}$'),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (environment,bot_id,exchange,pair,timeframe,sequence)
);

CREATE INDEX IF NOT EXISTS signal_revocations_latest_idx
    ON signal_revocations(environment,bot_id,exchange,pair,timeframe,sequence DESC);

DROP TRIGGER IF EXISTS signals_source_policy_gate ON signals;
CREATE TRIGGER signals_source_policy_gate
BEFORE INSERT ON signals
FOR EACH ROW EXECUTE FUNCTION enforce_signal_source_policy();

CREATE OR REPLACE FUNCTION keep_signals_immutable() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'created signals are immutable';
END;
$$;

DROP TRIGGER IF EXISTS signals_immutable ON signals;
CREATE TRIGGER signals_immutable
BEFORE UPDATE OR DELETE ON signals
FOR EACH ROW EXECUTE FUNCTION keep_signals_immutable();

CREATE OR REPLACE FUNCTION require_created_signal_envelope() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.envelope #>> '{payload,event_type}' <> 'signal.created'
       OR NEW.status <> 'valid'
       OR NEW.envelope #>> '{payload,status}' <> 'valid'
       OR NEW.environment IS DISTINCT FROM NEW.envelope #>> '{payload,environment}'
       OR NEW.bot_id IS DISTINCT FROM NEW.envelope #>> '{payload,bot_id}'
       OR NEW.correlation_id::text IS DISTINCT FROM
          NEW.envelope #>> '{payload,correlation_id}'
       OR NEW.published_at IS DISTINCT FROM
          (NEW.envelope #>> '{payload,published_at}')::timestamptz
       OR NEW.expires_at IS DISTINCT FROM
          (NEW.envelope #>> '{payload,expires_at}')::timestamptz
       OR NEW.signal_available_at IS DISTINCT FROM
          (NEW.envelope #>> '{payload,signal_available_at}')::timestamptz THEN
        RAISE EXCEPTION 'created signal columns do not match the signed envelope';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS signals_created_envelope ON signals;
CREATE TRIGGER signals_created_envelope
BEFORE INSERT ON signals
FOR EACH ROW EXECUTE FUNCTION require_created_signal_envelope();

ALTER TABLE delivery_receipts DROP CONSTRAINT IF EXISTS delivery_receipts_disposition_check;
ALTER TABLE delivery_receipts ADD CONSTRAINT delivery_receipts_disposition_check
    CHECK (disposition IN ('materialized','revoked','duplicate','stale','rejected','expired'));

CREATE OR REPLACE FUNCTION enforce_signed_revocation() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    target_environment text;
    target_bot text;
    target_exchange text;
    target_pair text;
    target_timeframe text;
    target_sequence_value bigint;
    target_checksum_value text;
    target_rating text;
    run_manifest uuid;
    run_session uuid;
    run_outcome text;
    run_attempt integer;
    run_fence bigint;
    job_status text;
    job_attempt integer;
    job_fence bigint;
    lease_expires timestamptz;
    manifest_status text;
    manifest_instrument text;
    manifest_snapshot uuid;
    capture_status text;
    capture_rejection text;
    evaluation_verdict text;
    evaluation_ratings jsonb;
    evaluation_digest text;
    snapshot_exchange text;
    snapshot_pair text;
    snapshot_timeframe text;
BEGIN
    IF NEW.event_id::text IS DISTINCT FROM NEW.envelope #>> '{payload,event_id}'
       OR NEW.revocation_id::text IS DISTINCT FROM NEW.envelope #>> '{payload,revocation_id}'
       OR NEW.signal_id::text IS DISTINCT FROM NEW.envelope #>> '{payload,signal_id}'
       OR NEW.target_sequence IS DISTINCT FROM
          (NEW.envelope #>> '{payload,target_sequence}')::bigint
       OR NEW.target_checksum IS DISTINCT FROM NEW.envelope #>> '{payload,target_checksum}'
       OR NEW.run_id::text IS DISTINCT FROM NEW.envelope #>> '{payload,run_id}'
       OR NEW.instrument_id IS DISTINCT FROM NEW.envelope #>> '{payload,instrument_id}'
       OR NEW.execution_snapshot_id::text IS DISTINCT FROM
          NEW.envelope #>> '{payload,execution_snapshot_id}'
       OR NEW.evidence_manifest_id::text IS DISTINCT FROM
          NEW.envelope #>> '{payload,evidence_manifest_id}'
       OR NEW.environment IS DISTINCT FROM NEW.envelope #>> '{payload,environment}'
       OR NEW.bot_id IS DISTINCT FROM NEW.envelope #>> '{payload,bot_id}'
       OR NEW.exchange IS DISTINCT FROM NEW.envelope #>> '{payload,exchange}'
       OR NEW.pair IS DISTINCT FROM NEW.envelope #>> '{payload,pair}'
       OR NEW.timeframe IS DISTINCT FROM NEW.envelope #>> '{payload,timeframe}'
       OR NEW.sequence IS DISTINCT FROM (NEW.envelope #>> '{payload,sequence}')::bigint
       OR NEW.reason_code IS DISTINCT FROM NEW.envelope #>> '{payload,reason_code}'
       OR NEW.denied_rating IS DISTINCT FROM NEW.envelope #>> '{payload,denied_rating}'
       OR NEW.source_policy_result_digest IS DISTINCT FROM
          NEW.envelope #>> '{payload,source_policy_result_digest}'
       OR NEW.checksum IS DISTINCT FROM NEW.envelope #>> '{checksum}'
       OR NEW.envelope #>> '{payload,event_type}' <> 'signal.revoked' THEN
        RAISE EXCEPTION 'revocation columns do not match the signed envelope';
    END IF;

    SELECT environment,bot_id,exchange,pair,timeframe,sequence,checksum,
           envelope #>> '{payload,decision,rating}'
    INTO target_environment,target_bot,target_exchange,target_pair,target_timeframe,
         target_sequence_value,target_checksum_value,target_rating
    FROM signals WHERE signal_id=NEW.signal_id
                   AND status='valid'
                   AND envelope #>> '{payload,event_type}'='signal.created';
    IF target_environment IS NULL
       OR ROW(target_environment,target_bot,target_exchange,target_pair,target_timeframe,
              target_sequence_value,target_checksum_value)
          IS DISTINCT FROM
          ROW(NEW.environment,NEW.bot_id,NEW.exchange,NEW.pair,NEW.timeframe,
              NEW.target_sequence,NEW.target_checksum)
       OR target_rating = 'Hold' THEN
        RAISE EXCEPTION 'revocation target is missing, mismatched, or non-actionable';
    END IF;
    IF EXISTS (
        SELECT 1 FROM signals
        WHERE environment=NEW.environment AND bot_id=NEW.bot_id
          AND exchange=NEW.exchange AND pair=NEW.pair AND timeframe=NEW.timeframe
          AND sequence>NEW.target_sequence AND sequence<NEW.sequence
    ) OR EXISTS (
        SELECT 1 FROM signal_revocations
        WHERE environment=NEW.environment AND bot_id=NEW.bot_id
          AND exchange=NEW.exchange AND pair=NEW.pair AND timeframe=NEW.timeframe
          AND sequence>NEW.target_sequence AND sequence<NEW.sequence
    ) THEN
        RAISE EXCEPTION 'revocation does not target the latest durable event';
    END IF;

    SELECT run.evidence_manifest_id,run.capture_session_id,run.outcome,
           run.attempt,run.fencing_token,job.status,job.attempt,job.fencing_token,
           job.lease_expires_at,manifest.status,manifest.instrument_id,
           manifest.execution_snapshot_id,session.status,session.rejection_code,
           evaluation.verdict,evaluation.permitted_ratings,evaluation.result_digest,
           snapshot.exchange,snapshot.pair,snapshot.timeframe
    INTO run_manifest,run_session,run_outcome,run_attempt,run_fence,job_status,
         job_attempt,job_fence,lease_expires,manifest_status,manifest_instrument,
         manifest_snapshot,capture_status,capture_rejection,evaluation_verdict,
         evaluation_ratings,evaluation_digest,snapshot_exchange,snapshot_pair,
         snapshot_timeframe
    FROM analysis_runs AS run
    JOIN analysis_jobs AS job ON job.job_id=run.job_id
    JOIN evidence_manifests AS manifest ON manifest.manifest_id=NEW.evidence_manifest_id
                                      AND manifest.run_id=run.run_id
    JOIN execution_market_snapshots AS snapshot
      ON snapshot.snapshot_id=manifest.execution_snapshot_id
    LEFT JOIN capture_sessions AS session ON session.session_id=run.capture_session_id
    LEFT JOIN source_policy_evaluations AS evaluation
      ON evaluation.session_id=session.session_id
     AND evaluation.manifest_id=manifest.manifest_id
    WHERE run.run_id=NEW.run_id;

    IF run_manifest IS DISTINCT FROM NEW.evidence_manifest_id
       OR manifest_instrument IS DISTINCT FROM NEW.instrument_id
       OR manifest_snapshot IS DISTINCT FROM NEW.execution_snapshot_id
       OR snapshot_exchange IS DISTINCT FROM NEW.exchange
       OR snapshot_pair IS DISTINCT FROM NEW.pair
       OR snapshot_timeframe IS DISTINCT FROM NEW.timeframe
       OR run_outcome <> 'running' OR job_status <> 'running'
       OR run_attempt IS DISTINCT FROM job_attempt
       OR run_fence IS DISTINCT FROM job_fence
       OR lease_expires <= now() THEN
        RAISE EXCEPTION 'revocation is not owned by a live fenced analysis attempt';
    END IF;

    IF EXISTS (
        SELECT 1 FROM signals
        WHERE environment=NEW.environment AND bot_id=NEW.bot_id
          AND exchange=NEW.exchange AND pair=NEW.pair AND timeframe=NEW.timeframe
          AND sequence=NEW.sequence
    ) OR EXISTS (
        SELECT 1 FROM signal_revocations
        WHERE environment=NEW.environment AND bot_id=NEW.bot_id
          AND exchange=NEW.exchange AND pair=NEW.pair AND timeframe=NEW.timeframe
          AND sequence=NEW.sequence AND revocation_id<>NEW.revocation_id
    ) THEN
        RAISE EXCEPTION 'revocation sequence is already occupied';
    END IF;

    IF NEW.source_policy_result_digest IS NOT NULL THEN
        IF evaluation_digest IS DISTINCT FROM NEW.source_policy_result_digest THEN
            RAISE EXCEPTION 'revocation policy digest does not match the current run';
        END IF;
        IF evaluation_verdict='reject' THEN
            IF capture_status<>'rejected' OR manifest_status<>'rejected'
               OR capture_rejection IS DISTINCT FROM NEW.reason_code THEN
                RAISE EXCEPTION 'rejected-policy revocation has invalid terminal evidence';
            END IF;
        ELSIF NEW.denied_rating IS NULL OR evaluation_ratings ? NEW.denied_rating
              OR capture_status<>'sealed' OR manifest_status<>'sealed'
              OR NEW.reason_code<>'publication.rating_not_permitted' THEN
            RAISE EXCEPTION 'rating revocation is not denied by source policy';
        END IF;
    ELSIF NEW.reason_code<>'worker.analysis_failed'
          OR NOT (
              (capture_status='rejected' AND manifest_status='rejected'
               AND capture_rejection=NEW.reason_code)
              OR (capture_status='sealed' AND manifest_status='sealed')
          ) THEN
        RAISE EXCEPTION 'operational revocation lacks a rejected capture';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS signal_revocations_authorized ON signal_revocations;
CREATE TRIGGER signal_revocations_authorized
BEFORE INSERT ON signal_revocations
FOR EACH ROW EXECUTE FUNCTION enforce_signed_revocation();

CREATE OR REPLACE FUNCTION keep_signal_revocations_immutable() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'signal revocations are immutable';
END;
$$;

DROP TRIGGER IF EXISTS signal_revocations_immutable ON signal_revocations;
CREATE TRIGGER signal_revocations_immutable
BEFORE UPDATE OR DELETE ON signal_revocations
FOR EACH ROW EXECUTE FUNCTION keep_signal_revocations_immutable();

CREATE OR REPLACE FUNCTION enforce_signal_outbox_lineage() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE stored_envelope jsonb;
BEGIN
    IF NEW.subject LIKE 'signals.v2.%' THEN
        IF NEW.payload #>> '{payload,event_type}' = 'signal.created' THEN
            SELECT envelope INTO stored_envelope FROM signals WHERE event_id=NEW.event_id;
        ELSIF NEW.payload #>> '{payload,event_type}' = 'signal.revoked' THEN
            SELECT envelope INTO stored_envelope
            FROM signal_revocations WHERE event_id=NEW.event_id;
        END IF;
        IF stored_envelope IS NULL OR stored_envelope IS DISTINCT FROM NEW.payload THEN
            RAISE EXCEPTION 'signal outbox payload lacks an authorized stored event';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
