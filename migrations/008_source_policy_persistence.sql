-- Persist the immutable collection cutoff and deterministic source-policy decision.
ALTER TABLE capture_sessions
    ADD COLUMN IF NOT EXISTS collection_closed_at timestamptz;

UPDATE capture_sessions
SET collection_closed_at=COALESCE(completed_at, LEAST(deadline_at, now()))
WHERE status <> 'collecting' AND collection_closed_at IS NULL;

ALTER TABLE capture_sessions
    DROP CONSTRAINT IF EXISTS capture_sessions_collection_cutoff_check;
ALTER TABLE capture_sessions
    ADD CONSTRAINT capture_sessions_collection_cutoff_check CHECK (
        (status = 'collecting' AND collection_closed_at IS NULL)
        OR (status <> 'collecting' AND collection_closed_at IS NOT NULL
            AND collection_closed_at BETWEEN started_at AND deadline_at)
    );

CREATE TABLE IF NOT EXISTS source_policy_evaluations (
    evaluation_id uuid PRIMARY KEY,
    session_id uuid NOT NULL UNIQUE REFERENCES capture_sessions(session_id),
    manifest_id uuid NOT NULL UNIQUE REFERENCES evidence_manifests(manifest_id),
    run_id uuid NOT NULL UNIQUE REFERENCES analysis_runs(run_id),
    job_id uuid NOT NULL REFERENCES analysis_jobs(job_id),
    job_attempt integer NOT NULL CHECK (job_attempt > 0),
    fencing_token bigint NOT NULL CHECK (fencing_token > 0),
    instrument_id text NOT NULL REFERENCES instruments(instrument_id),
    execution_snapshot_id uuid NOT NULL REFERENCES execution_market_snapshots(snapshot_id),
    policy_version text NOT NULL,
    policy_configuration_hash text NOT NULL
        CHECK (policy_configuration_hash ~ '^sha256:[0-9a-f]{64}$'),
    input_digest text NOT NULL CHECK (input_digest ~ '^sha256:[0-9a-f]{64}$'),
    verdict text NOT NULL CHECK (verdict IN ('pass','hold_only','reject')),
    permitted_ratings jsonb NOT NULL,
    data_as_of timestamptz NOT NULL,
    quality_flags jsonb NOT NULL DEFAULT '[]'::jsonb,
    result_digest text NOT NULL UNIQUE CHECK (result_digest ~ '^sha256:[0-9a-f]{64}$'),
    evaluated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (
        (verdict='pass' AND permitted_ratings =
            '["Buy","Overweight","Hold","Underweight","Sell"]'::jsonb)
        OR (verdict='hold_only' AND permitted_ratings='["Hold"]'::jsonb)
        OR (verdict='reject' AND permitted_ratings='[]'::jsonb)
    )
);

CREATE TABLE IF NOT EXISTS source_policy_rule_results (
    evaluation_id uuid NOT NULL REFERENCES source_policy_evaluations(evaluation_id),
    ordinal integer NOT NULL CHECK (ordinal >= 0),
    rule_id text NOT NULL,
    outcome text NOT NULL CHECK (outcome IN ('pass','warn','degrade','fail')),
    code text NOT NULL CHECK (code ~ '^[a-z][a-z0-9_.-]{2,127}$'),
    evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
    PRIMARY KEY (evaluation_id, ordinal),
    UNIQUE (evaluation_id, rule_id)
);

ALTER TABLE evidence_manifests
    ADD COLUMN IF NOT EXISTS policy_evaluation_id uuid,
    ADD COLUMN IF NOT EXISTS policy_result_digest text
        CHECK (policy_result_digest IS NULL OR policy_result_digest ~ '^sha256:[0-9a-f]{64}$');

ALTER TABLE evidence_manifests
    DROP CONSTRAINT IF EXISTS evidence_manifests_policy_evaluation_fkey;
ALTER TABLE evidence_manifests
    ADD CONSTRAINT evidence_manifests_policy_evaluation_fkey
    FOREIGN KEY (policy_evaluation_id)
    REFERENCES source_policy_evaluations(evaluation_id);

CREATE OR REPLACE FUNCTION enforce_policy_evaluation_immutability() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    parent capture_sessions%ROWTYPE;
    manifest_status text;
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'source policy evaluations are immutable';
    END IF;
    SELECT * INTO parent FROM capture_sessions WHERE session_id=NEW.session_id;
    SELECT status INTO manifest_status FROM evidence_manifests
        WHERE manifest_id=NEW.manifest_id AND capture_session_id=NEW.session_id;
    IF parent.status <> 'evaluating' OR manifest_status <> 'collecting'
       OR ROW(NEW.manifest_id,NEW.run_id,NEW.job_id,NEW.job_attempt,NEW.fencing_token,
              NEW.instrument_id,NEW.execution_snapshot_id)
          IS DISTINCT FROM
          ROW(parent.manifest_id,parent.run_id,parent.job_id,parent.job_attempt,
              parent.fencing_token,parent.instrument_id,parent.execution_snapshot_id) THEN
        RAISE EXCEPTION 'policy evaluation identity is not an evaluating capture attempt';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS source_policy_evaluations_immutable ON source_policy_evaluations;
CREATE TRIGGER source_policy_evaluations_immutable
BEFORE INSERT OR UPDATE OR DELETE ON source_policy_evaluations
FOR EACH ROW EXECUTE FUNCTION enforce_policy_evaluation_immutability();

CREATE OR REPLACE FUNCTION enforce_policy_rule_immutability() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE parent_status text;
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'source policy rule results are immutable';
    END IF;
    SELECT session.status INTO parent_status
    FROM source_policy_evaluations AS evaluation
    JOIN capture_sessions AS session ON session.session_id=evaluation.session_id
    WHERE evaluation.evaluation_id=NEW.evaluation_id;
    IF parent_status <> 'evaluating' THEN
        RAISE EXCEPTION 'policy rules may only be inserted while evaluating';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS source_policy_rule_results_immutable ON source_policy_rule_results;
CREATE TRIGGER source_policy_rule_results_immutable
BEFORE INSERT OR UPDATE OR DELETE ON source_policy_rule_results
FOR EACH ROW EXECUTE FUNCTION enforce_policy_rule_immutability();

CREATE OR REPLACE FUNCTION reject_immutable_manifest_change() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    evaluation_verdict text;
    evaluation_digest text;
    rule_count integer;
    fail_count integer;
    degrade_count integer;
    first_rule_ordinal integer;
    last_rule_ordinal integer;
    rule_ids text[];
BEGIN
    IF OLD.status IN ('sealed','rejected') THEN
        RAISE EXCEPTION 'evidence manifest % is immutable in status %',
            OLD.manifest_id, OLD.status;
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    IF (NEW.policy_evaluation_id IS NULL) <> (NEW.policy_result_digest IS NULL) THEN
        RAISE EXCEPTION 'manifest policy identity must be complete';
    END IF;
    IF NEW.capture_session_id IS NOT NULL AND NEW.status = 'sealed' THEN
        SELECT verdict,result_digest INTO evaluation_verdict,evaluation_digest
        FROM source_policy_evaluations
        WHERE evaluation_id=NEW.policy_evaluation_id
          AND session_id=NEW.capture_session_id AND manifest_id=NEW.manifest_id;
        SELECT count(*),count(*) FILTER (WHERE outcome='fail'),
               count(*) FILTER (WHERE outcome='degrade'),min(ordinal),max(ordinal),
               array_agg(rule_id ORDER BY ordinal)
        INTO rule_count,fail_count,degrade_count,first_rule_ordinal,last_rule_ordinal,rule_ids
        FROM source_policy_rule_results
        WHERE evaluation_id=NEW.policy_evaluation_id;
        IF evaluation_verdict NOT IN ('pass','hold_only')
           OR evaluation_digest IS DISTINCT FROM NEW.policy_result_digest
           OR rule_count <> 20 OR first_rule_ordinal <> 0 OR last_rule_ordinal <> 19
           OR rule_ids <> ARRAY[
               'contract.identity','contract.capture_state','market.execution_snapshot',
               'contract.invocation_ledger','contract.method_allowlist',
               'temporal.invocations','contract.research_symbols','artifact.integrity',
               'contract.vendor_fallbacks','source.unsafe_outcomes',
               'source.required.resolve_instrument_identity',
               'source.required.get_stock_data',
               'source.required.get_verified_market_snapshot',
               'source.degraded.get_indicators','source.degraded.get_news',
               'source.degraded.get_global_news',
               'source.degraded.fetch_stocktwits_messages',
               'source.degraded.fetch_reddit_posts',
               'source.optional.get_macro_indicators',
               'source.optional.get_prediction_markets']::text[]
           OR fail_count <> 0
           OR (evaluation_verdict='pass' AND degrade_count <> 0)
           OR (evaluation_verdict='hold_only' AND degrade_count = 0)
           OR NEW.call_ledger_digest IS NULL THEN
            RAISE EXCEPTION 'sealed capture manifest lacks a complete publishable policy';
        END IF;
    END IF;
    IF NEW.capture_session_id IS NOT NULL AND NEW.status = 'rejected'
       AND NEW.policy_evaluation_id IS NOT NULL THEN
        SELECT verdict,result_digest INTO evaluation_verdict,evaluation_digest
        FROM source_policy_evaluations
        WHERE evaluation_id=NEW.policy_evaluation_id
          AND session_id=NEW.capture_session_id AND manifest_id=NEW.manifest_id;
        SELECT count(*),min(ordinal),max(ordinal),array_agg(rule_id ORDER BY ordinal)
        INTO rule_count,first_rule_ordinal,last_rule_ordinal,rule_ids
        FROM source_policy_rule_results WHERE evaluation_id=NEW.policy_evaluation_id;
        IF evaluation_verdict <> 'reject'
           OR evaluation_digest IS DISTINCT FROM NEW.policy_result_digest
           OR rule_count <> 20 OR first_rule_ordinal <> 0 OR last_rule_ordinal <> 19
           OR rule_ids <> ARRAY[
               'contract.identity','contract.capture_state','market.execution_snapshot',
               'contract.invocation_ledger','contract.method_allowlist',
               'temporal.invocations','contract.research_symbols','artifact.integrity',
               'contract.vendor_fallbacks','source.unsafe_outcomes',
               'source.required.resolve_instrument_identity',
               'source.required.get_stock_data',
               'source.required.get_verified_market_snapshot',
               'source.degraded.get_indicators','source.degraded.get_news',
               'source.degraded.get_global_news',
               'source.degraded.fetch_stocktwits_messages',
               'source.degraded.fetch_reddit_posts',
               'source.optional.get_macro_indicators',
               'source.optional.get_prediction_markets']::text[] THEN
            RAISE EXCEPTION 'policy-rejected manifest lacks a complete rejecting policy';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

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
           OR NEW.collection_closed_at IS NOT NULL
           OR NEW.completed_at IS DISTINCT FROM OLD.completed_at
           OR NEW.rejection_code IS DISTINCT FROM OLD.rejection_code THEN
            RAISE EXCEPTION 'only one evidence ordinal may be allocated while collecting';
        END IF;
        RETURN NEW;
    END IF;
    IF OLD.status = 'collecting' AND NEW.status = 'evaluating' THEN
        IF NEW.next_call_ordinal <> OLD.next_call_ordinal
           OR NEW.next_invocation_ordinal <> OLD.next_invocation_ordinal
           OR NEW.collection_closed_at IS NULL
           OR NEW.completed_at IS NOT NULL OR NEW.rejection_code IS NOT NULL THEN
            RAISE EXCEPTION 'invalid collection close';
        END IF;
        RETURN NEW;
    END IF;
    IF OLD.status = 'collecting' AND NEW.status IN ('rejected','abandoned') THEN
        IF NEW.collection_closed_at IS NULL OR NEW.completed_at IS NULL
           OR NEW.rejection_code IS NULL
           OR NEW.next_call_ordinal <> OLD.next_call_ordinal
           OR NEW.next_invocation_ordinal <> OLD.next_invocation_ordinal THEN
            RAISE EXCEPTION 'invalid collecting terminal transition';
        END IF;
        RETURN NEW;
    END IF;
    IF OLD.status = 'evaluating' AND NEW.status IN ('sealed','rejected','abandoned') THEN
        IF NEW.collection_closed_at IS DISTINCT FROM OLD.collection_closed_at
           OR NEW.next_call_ordinal <> OLD.next_call_ordinal
           OR NEW.next_invocation_ordinal <> OLD.next_invocation_ordinal THEN
            RAISE EXCEPTION 'invalid evaluating terminal transition';
        END IF;
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'invalid capture session transition: % to %', OLD.status, NEW.status;
END;
$$;
