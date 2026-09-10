ALTER TABLE outbox
    ADD COLUMN IF NOT EXISTS claim_owner text,
    ADD COLUMN IF NOT EXISTS claim_token uuid,
    ADD COLUMN IF NOT EXISTS claim_expires_at timestamptz;

ALTER TABLE outbox DROP CONSTRAINT IF EXISTS outbox_claim_complete_check;
ALTER TABLE outbox ADD CONSTRAINT outbox_claim_complete_check CHECK (
    (claim_owner IS NULL AND claim_token IS NULL AND claim_expires_at IS NULL)
    OR
    (published_at IS NULL AND claim_owner IS NOT NULL
     AND claim_token IS NOT NULL AND claim_expires_at IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS outbox_claimable_idx
    ON outbox(next_attempt_at,claim_expires_at,outbox_id)
    WHERE published_at IS NULL;
