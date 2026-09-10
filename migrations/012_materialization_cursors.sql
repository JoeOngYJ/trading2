CREATE TABLE IF NOT EXISTS materialization_cursors (
    consumer_id text NOT NULL,
    environment text NOT NULL,
    bot_id text NOT NULL,
    exchange text NOT NULL,
    pair text NOT NULL,
    timeframe text NOT NULL,
    sequence bigint NOT NULL DEFAULT 0 CHECK (sequence >= 0),
    event_id uuid,
    signal_id uuid,
    checksum text CHECK (checksum IS NULL OR checksum ~ '^[0-9a-f]{64}$'),
    disposition text CHECK (disposition IS NULL OR disposition IN ('materialized','revoked')),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_id,environment,bot_id,exchange,pair,timeframe),
    CHECK (
        (sequence=0 AND event_id IS NULL AND signal_id IS NULL
                    AND checksum IS NULL AND disposition IS NULL)
        OR
        (sequence>0 AND event_id IS NOT NULL AND signal_id IS NOT NULL
                    AND checksum IS NOT NULL AND disposition IS NOT NULL)
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS materialization_cursors_event_idx
    ON materialization_cursors(consumer_id,event_id) WHERE event_id IS NOT NULL;

CREATE OR REPLACE FUNCTION keep_materialization_cursor_monotonic() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP='DELETE' THEN
        RAISE EXCEPTION 'materialization cursors cannot be deleted';
    END IF;
    IF NEW.sequence < OLD.sequence THEN
        RAISE EXCEPTION 'materialization cursor sequence cannot decrease';
    END IF;
    IF NEW.sequence = OLD.sequence AND ROW(NEW.event_id,NEW.signal_id,NEW.checksum,NEW.disposition)
       IS DISTINCT FROM ROW(OLD.event_id,OLD.signal_id,OLD.checksum,OLD.disposition) THEN
        RAISE EXCEPTION 'materialization cursor identity cannot change at the same sequence';
    END IF;
    IF ROW(NEW.consumer_id,NEW.environment,NEW.bot_id,NEW.exchange,NEW.pair,NEW.timeframe)
       IS DISTINCT FROM ROW(OLD.consumer_id,OLD.environment,OLD.bot_id,OLD.exchange,
                            OLD.pair,OLD.timeframe) THEN
        RAISE EXCEPTION 'materialization cursor route is immutable';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS materialization_cursors_monotonic ON materialization_cursors;
CREATE TRIGGER materialization_cursors_monotonic
BEFORE UPDATE OR DELETE ON materialization_cursors
FOR EACH ROW EXECUTE FUNCTION keep_materialization_cursor_monotonic();
