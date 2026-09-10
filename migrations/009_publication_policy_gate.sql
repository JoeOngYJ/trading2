-- Bind real captured signals to the exact publishable source-policy decision.
ALTER TABLE signals
    ADD COLUMN IF NOT EXISTS source_policy_result_digest text
        CHECK (source_policy_result_digest IS NULL
               OR source_policy_result_digest ~ '^sha256:[0-9a-f]{64}$');

ALTER TABLE signals
    DROP CONSTRAINT IF EXISTS signals_source_policy_result_fkey;
ALTER TABLE signals
    ADD CONSTRAINT signals_source_policy_result_fkey
    FOREIGN KEY (source_policy_result_digest)
    REFERENCES source_policy_evaluations(result_digest);

CREATE OR REPLACE FUNCTION enforce_signal_source_policy() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    capture_id uuid;
    run_manifest_id uuid;
    run_configuration jsonb;
    manifest_status text;
    manifest_instrument text;
    manifest_snapshot uuid;
    manifest_policy_digest text;
    manifest_flags jsonb;
    capture_status text;
    evaluation_verdict text;
    evaluation_ratings jsonb;
    evaluation_data_as_of timestamptz;
    evaluation_flags jsonb;
    payload_rating text;
    payload_data_as_of timestamptz;
    payload_flags jsonb;
    snapshot_exchange text;
    snapshot_pair text;
    snapshot_timeframe text;
    snapshot_close timestamptz;
BEGIN
    IF NEW.event_id::text IS DISTINCT FROM NEW.envelope #>> '{payload,event_id}'
       OR NEW.signal_id::text IS DISTINCT FROM NEW.envelope #>> '{payload,signal_id}'
       OR NEW.run_id::text IS DISTINCT FROM NEW.envelope #>> '{payload,run_id}'
       OR NEW.instrument_id IS DISTINCT FROM NEW.envelope #>> '{payload,instrument_id}'
       OR NEW.execution_snapshot_id::text IS DISTINCT FROM
          NEW.envelope #>> '{payload,execution_snapshot_id}'
       OR NEW.evidence_manifest_id::text IS DISTINCT FROM
          NEW.envelope #>> '{payload,evidence_manifest_id}'
       OR NEW.exchange IS DISTINCT FROM NEW.envelope #>> '{payload,exchange}'
       OR NEW.pair IS DISTINCT FROM NEW.envelope #>> '{payload,pair}'
       OR NEW.timeframe IS DISTINCT FROM NEW.envelope #>> '{payload,timeframe}'
       OR NEW.sequence IS DISTINCT FROM
          (NEW.envelope #>> '{payload,sequence}')::bigint
       OR NEW.source_policy_result_digest IS DISTINCT FROM
          NEW.envelope #>> '{payload,source_policy_result_digest}'
       OR NEW.checksum IS DISTINCT FROM NEW.envelope #>> '{checksum}' THEN
        RAISE EXCEPTION 'signal columns do not match the signed envelope';
    END IF;

    SELECT run.capture_session_id,run.evidence_manifest_id,run.configuration,
           manifest.status,manifest.instrument_id,manifest.execution_snapshot_id,
           manifest.policy_result_digest,manifest.quality_flags,
           session.status,evaluation.verdict,evaluation.permitted_ratings,
           evaluation.data_as_of,evaluation.quality_flags,
           snapshot.exchange,snapshot.pair,snapshot.timeframe,snapshot.candle_close_at
    INTO capture_id,run_manifest_id,run_configuration,manifest_status,
         manifest_instrument,manifest_snapshot,manifest_policy_digest,manifest_flags,
         capture_status,evaluation_verdict,evaluation_ratings,evaluation_data_as_of,
         evaluation_flags,snapshot_exchange,snapshot_pair,snapshot_timeframe,snapshot_close
    FROM analysis_runs AS run
    JOIN evidence_manifests AS manifest ON manifest.manifest_id=NEW.evidence_manifest_id
                                    AND manifest.run_id=run.run_id
    JOIN execution_market_snapshots AS snapshot
      ON snapshot.snapshot_id=manifest.execution_snapshot_id
    LEFT JOIN capture_sessions AS session ON session.session_id=run.capture_session_id
    LEFT JOIN source_policy_evaluations AS evaluation
      ON evaluation.session_id=session.session_id
     AND evaluation.manifest_id=manifest.manifest_id
    WHERE run.run_id=NEW.run_id;

    IF run_manifest_id IS DISTINCT FROM NEW.evidence_manifest_id
       OR manifest_status <> 'sealed'
       OR manifest_instrument IS DISTINCT FROM NEW.instrument_id
       OR manifest_snapshot IS DISTINCT FROM NEW.execution_snapshot_id
       OR snapshot_exchange IS DISTINCT FROM NEW.exchange
       OR snapshot_pair IS DISTINCT FROM NEW.pair
       OR snapshot_timeframe IS DISTINCT FROM NEW.timeframe
       OR snapshot_close IS DISTINCT FROM
          (NEW.envelope #>> '{payload,candle_close_at}')::timestamptz THEN
        RAISE EXCEPTION 'signal publication identity does not match sealed evidence';
    END IF;

    IF capture_id IS NULL THEN
        IF COALESCE(run_configuration->>'research_mode',run_configuration->>'mode')
              <> 'synthetic'
           OR NOT (manifest_flags ? 'synthetic')
           OR NEW.source_policy_result_digest IS NOT NULL THEN
            RAISE EXCEPTION 'non-captured signal is not an authorized synthetic result';
        END IF;
        RETURN NEW;
    END IF;

    payload_rating := NEW.envelope #>> '{payload,decision,rating}';
    payload_data_as_of := (NEW.envelope #>> '{payload,provenance,data_as_of}')::timestamptz;
    payload_flags := COALESCE(NEW.envelope #> '{payload,provenance,quality_flags}', '[]'::jsonb);
    IF capture_status <> 'sealed'
       OR evaluation_verdict NOT IN ('pass','hold_only')
       OR manifest_policy_digest IS DISTINCT FROM NEW.source_policy_result_digest
       OR manifest_policy_digest IS DISTINCT FROM
          (NEW.envelope #>> '{payload,source_policy_result_digest}')
       OR NOT (evaluation_ratings ? payload_rating)
       OR evaluation_data_as_of IS DISTINCT FROM payload_data_as_of
       OR NOT (payload_flags @> evaluation_flags) THEN
        RAISE EXCEPTION 'signal is not authorized by its source policy';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS signals_source_policy_gate ON signals;
CREATE TRIGGER signals_source_policy_gate
BEFORE INSERT OR UPDATE ON signals
FOR EACH ROW EXECUTE FUNCTION enforce_signal_source_policy();

CREATE OR REPLACE FUNCTION enforce_signal_outbox_lineage() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE stored_envelope jsonb;
BEGIN
    IF NEW.subject LIKE 'signals.v2.%' THEN
        SELECT envelope INTO stored_envelope FROM signals WHERE event_id=NEW.event_id;
        IF stored_envelope IS NULL OR stored_envelope IS DISTINCT FROM NEW.payload THEN
            RAISE EXCEPTION 'signal outbox payload lacks an authorized stored signal';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS outbox_signal_lineage_gate ON outbox;
CREATE TRIGGER outbox_signal_lineage_gate
BEFORE INSERT OR UPDATE ON outbox
FOR EACH ROW EXECUTE FUNCTION enforce_signal_outbox_lineage();
