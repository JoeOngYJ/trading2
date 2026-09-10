CREATE TABLE IF NOT EXISTS instruments (
    instrument_id text PRIMARY KEY,
    research_symbol text NOT NULL UNIQUE,
    execution_exchange text NOT NULL,
    execution_pair text NOT NULL,
    market_type text NOT NULL CHECK (market_type IN ('spot','margin','future')),
    base_asset text NOT NULL,
    quote_asset text NOT NULL,
    research_quote text NOT NULL,
    timezone text NOT NULL DEFAULT 'UTC' CHECK (timezone = 'UTC'),
    enabled boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (execution_exchange, execution_pair, market_type)
);

CREATE TABLE IF NOT EXISTS artifacts (
    digest text PRIMARY KEY CHECK (digest ~ '^sha256:[0-9a-f]{64}$'),
    media_type text NOT NULL,
    byte_length bigint NOT NULL CHECK (byte_length >= 0),
    storage_path text NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS execution_market_snapshots (
    snapshot_id uuid PRIMARY KEY,
    instrument_id text NOT NULL REFERENCES instruments(instrument_id),
    exchange text NOT NULL,
    pair text NOT NULL,
    market_type text NOT NULL,
    timeframe text NOT NULL,
    candle_type text NOT NULL,
    candle_open_at timestamptz NOT NULL,
    candle_close_at timestamptz NOT NULL,
    open_price numeric NOT NULL,
    high_price numeric NOT NULL,
    low_price numeric NOT NULL,
    close_price numeric NOT NULL,
    volume numeric NOT NULL,
    retrieved_at timestamptz NOT NULL,
    exchange_time_at timestamptz NOT NULL,
    clock_offset_ms bigint NOT NULL,
    is_closed boolean NOT NULL CHECK (is_closed),
    has_gap boolean NOT NULL,
    collector_version text NOT NULL,
    raw_artifact_digest text NOT NULL REFERENCES artifacts(digest),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (instrument_id, timeframe, candle_open_at)
);

CREATE TABLE IF NOT EXISTS source_observations (
    observation_id uuid PRIMARY KEY,
    category text NOT NULL,
    vendor text NOT NULL,
    symbol_or_query text NOT NULL,
    external_id text,
    canonical_url text,
    event_at timestamptz,
    published_at timestamptz,
    first_seen_at timestamptz NOT NULL,
    retrieved_at timestamptz NOT NULL,
    artifact_digest text NOT NULL REFERENCES artifacts(digest),
    request_parameters jsonb NOT NULL DEFAULT '{}'::jsonb,
    status text NOT NULL CHECK (status IN ('available','unavailable','error')),
    error_code text,
    quality_flags jsonb NOT NULL DEFAULT '[]'::jsonb,
    replay_safe boolean NOT NULL,
    replay_unsafe_reason text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS evidence_manifests (
    manifest_id uuid PRIMARY KEY,
    run_id uuid NOT NULL UNIQUE,
    instrument_id text NOT NULL REFERENCES instruments(instrument_id),
    execution_snapshot_id uuid NOT NULL REFERENCES execution_market_snapshots(snapshot_id),
    mode text NOT NULL CHECK (mode IN ('live','captured_replay')),
    status text NOT NULL CHECK (status IN ('collecting','sealed','rejected')),
    collection_started_at timestamptz NOT NULL,
    collection_completed_at timestamptz,
    configured_vendors jsonb NOT NULL,
    vendor_fallbacks jsonb NOT NULL DEFAULT '[]'::jsonb,
    required_sources jsonb NOT NULL DEFAULT '{}'::jsonb,
    replay_safe boolean,
    quality_flags jsonb NOT NULL DEFAULT '[]'::jsonb,
    digest text CHECK (digest ~ '^sha256:[0-9a-f]{64}$'),
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK ((status = 'collecting' AND digest IS NULL) OR (status <> 'collecting' AND digest IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS manifest_observations (
    manifest_id uuid NOT NULL REFERENCES evidence_manifests(manifest_id),
    observation_id uuid NOT NULL REFERENCES source_observations(observation_id),
    ordinal integer NOT NULL CHECK (ordinal >= 0),
    PRIMARY KEY (manifest_id, observation_id),
    UNIQUE (manifest_id, ordinal)
);

ALTER TABLE analysis_jobs ADD COLUMN IF NOT EXISTS instrument_id text REFERENCES instruments(instrument_id);
ALTER TABLE analysis_jobs ADD COLUMN IF NOT EXISTS execution_snapshot_id uuid REFERENCES execution_market_snapshots(snapshot_id);
ALTER TABLE signals ADD COLUMN IF NOT EXISTS instrument_id text REFERENCES instruments(instrument_id);
ALTER TABLE signals ADD COLUMN IF NOT EXISTS execution_snapshot_id uuid REFERENCES execution_market_snapshots(snapshot_id);
ALTER TABLE signals ADD COLUMN IF NOT EXISTS evidence_manifest_id uuid REFERENCES evidence_manifests(manifest_id);
ALTER TABLE signals ADD COLUMN IF NOT EXISTS signal_available_at timestamptz;

CREATE INDEX IF NOT EXISTS market_snapshots_latest_idx
    ON execution_market_snapshots(instrument_id,timeframe,candle_open_at DESC);
CREATE INDEX IF NOT EXISTS observations_first_seen_idx
    ON source_observations(first_seen_at,category,vendor);

INSERT INTO instruments(
    instrument_id,research_symbol,execution_exchange,execution_pair,market_type,
    base_asset,quote_asset,research_quote,timezone,enabled
) VALUES
    ('crypto:binance:spot:BTC-USDT','BTC-USD','binance','BTC/USDT','spot','BTC','USDT','USD','UTC',true),
    ('crypto:binance:spot:ETH-USDT','ETH-USD','binance','ETH/USDT','spot','ETH','USDT','USD','UTC',true)
ON CONFLICT (instrument_id) DO UPDATE SET
    research_symbol=excluded.research_symbol,
    execution_pair=excluded.execution_pair,
    enabled=excluded.enabled;
