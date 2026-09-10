CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS analysis_jobs (
    job_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    correlation_id uuid NOT NULL DEFAULT gen_random_uuid(),
    symbol text NOT NULL,
    pair text NOT NULL,
    timeframe text NOT NULL,
    candle_close_at timestamptz NOT NULL,
    status text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'succeeded', 'failed', 'dead')),
    attempt integer NOT NULL DEFAULT 0,
    max_attempts integer NOT NULL DEFAULT 3,
    available_at timestamptz NOT NULL DEFAULT now(),
    lease_owner text,
    lease_expires_at timestamptz,
    last_error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (symbol, timeframe, candle_close_at)
);
CREATE INDEX IF NOT EXISTS analysis_jobs_claim_idx
    ON analysis_jobs (available_at, created_at)
    WHERE status IN ('pending', 'failed');

CREATE TABLE IF NOT EXISTS analysis_runs (
    run_id uuid PRIMARY KEY,
    job_id uuid NOT NULL REFERENCES analysis_jobs(job_id),
    started_at timestamptz NOT NULL,
    completed_at timestamptz,
    producer_version text NOT NULL,
    code_revision text NOT NULL,
    configuration jsonb NOT NULL,
    raw_decision jsonb,
    raw_state jsonb,
    report_path text,
    outcome text NOT NULL DEFAULT 'running'
        CHECK (outcome IN ('running', 'succeeded', 'failed')),
    error text
);

CREATE TABLE IF NOT EXISTS signal_sequences (
    environment text NOT NULL,
    bot_id text NOT NULL,
    exchange text NOT NULL,
    pair text NOT NULL,
    timeframe text NOT NULL,
    last_sequence bigint NOT NULL,
    PRIMARY KEY (environment, bot_id, exchange, pair, timeframe)
);

CREATE TABLE IF NOT EXISTS signals (
    signal_id uuid PRIMARY KEY,
    event_id uuid NOT NULL UNIQUE,
    run_id uuid NOT NULL REFERENCES analysis_runs(run_id),
    correlation_id uuid NOT NULL,
    environment text NOT NULL,
    bot_id text NOT NULL,
    exchange text NOT NULL,
    pair text NOT NULL,
    timeframe text NOT NULL,
    sequence bigint NOT NULL,
    status text NOT NULL,
    published_at timestamptz NOT NULL,
    expires_at timestamptz NOT NULL,
    envelope jsonb NOT NULL,
    checksum text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (environment, bot_id, exchange, pair, timeframe, sequence)
);
CREATE INDEX IF NOT EXISTS signals_latest_idx
    ON signals (environment, bot_id, exchange, pair, timeframe, sequence DESC);

CREATE TABLE IF NOT EXISTS outbox (
    outbox_id bigserial PRIMARY KEY,
    event_id uuid NOT NULL UNIQUE,
    subject text NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    published_at timestamptz,
    publish_attempts integer NOT NULL DEFAULT 0,
    next_attempt_at timestamptz NOT NULL DEFAULT now(),
    last_error text
);
CREATE INDEX IF NOT EXISTS outbox_pending_idx
    ON outbox (next_attempt_at, outbox_id) WHERE published_at IS NULL;

CREATE TABLE IF NOT EXISTS delivery_receipts (
    consumer_id text NOT NULL,
    event_id uuid NOT NULL,
    signal_id uuid NOT NULL,
    sequence bigint NOT NULL,
    disposition text NOT NULL
        CHECK (disposition IN ('materialized', 'duplicate', 'stale', 'rejected', 'expired')),
    reason text,
    received_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_id, event_id)
);

CREATE TABLE IF NOT EXISTS execution_events (
    event_id uuid PRIMARY KEY,
    event_type text NOT NULL,
    occurred_at timestamptz NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now(),
    bot_id text NOT NULL,
    exchange text NOT NULL,
    pair text,
    trade_id text,
    order_id text,
    signal_id uuid,
    run_id uuid,
    payload jsonb NOT NULL,
    source text NOT NULL,
    UNIQUE (bot_id, event_type, trade_id, order_id, occurred_at)
);
CREATE INDEX IF NOT EXISTS execution_events_reconcile_idx
    ON execution_events (bot_id, occurred_at DESC);

CREATE TABLE IF NOT EXISTS service_heartbeats (
    service_id text PRIMARY KEY,
    status text NOT NULL,
    details jsonb NOT NULL DEFAULT '{}'::jsonb,
    observed_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS kill_switches (
    scope text PRIMARY KEY,
    enabled boolean NOT NULL DEFAULT false,
    reason text,
    updated_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO kill_switches(scope, enabled, reason)
VALUES ('global', false, 'initial state')
ON CONFLICT (scope) DO NOTHING;

