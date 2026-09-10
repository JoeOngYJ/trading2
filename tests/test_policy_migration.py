from pathlib import Path


def test_policy_migration_enforces_cutoff_identity_and_immutability():
    sql = Path("migrations/008_source_policy_persistence.sql").read_text()
    assert "collection_closed_at" in sql
    assert "source_policy_evaluations" in sql
    assert "source_policy_rule_results" in sql
    assert "policy_evaluation_id" in sql
    assert "policy_result_digest" in sql
    assert "source policy evaluations are immutable" in sql
    assert "policy rules may only be inserted while evaluating" in sql
    assert "verdict='hold_only' AND permitted_ratings='[\"Hold\"]'::jsonb" in sql


def test_publication_migration_enforces_policy_and_outbox_lineage():
    sql = Path("migrations/009_publication_policy_gate.sql").read_text()
    assert "source_policy_result_digest" in sql
    assert "enforce_signal_source_policy" in sql
    assert "evaluation_ratings ? payload_rating" in sql
    assert "payload_flags @> evaluation_flags" in sql
    assert "signal columns do not match the signed envelope" in sql
    assert "NEW.checksum IS DISTINCT FROM NEW.envelope #>> '{checksum}'" in sql
    assert "enforce_signal_outbox_lineage" in sql
    assert "stored_envelope IS DISTINCT FROM NEW.payload" in sql


def test_revocation_migration_is_signed_fenced_ordered_and_immutable():
    sql = Path("migrations/010_signed_revocations.sql").read_text()
    assert "CREATE TABLE IF NOT EXISTS signal_revocations" in sql
    assert "target_checksum" in sql
    assert "revocation does not target the latest durable event" in sql
    assert "revocation is not owned by a live fenced analysis attempt" in sql
    assert "signal revocations are immutable" in sql
    assert "created signals are immutable" in sql
    assert "require_created_signal_envelope" in sql
    assert "'materialized','revoked'" in sql
    assert "payload,event_type" in sql
    assert "authorized stored event" in sql


def test_expired_lease_revocation_is_fenced_and_supports_pre_capture_crashes():
    sql = Path("migrations/011_expired_lease_revocations.sql").read_text()
    assert "ALTER COLUMN evidence_manifest_id DROP NOT NULL" in sql
    assert "NEW.reason_code='worker_lease_expired'" in sql
    assert "attempt.lease_expires_at>=now()" in sql
    assert "attempt.run_fence IS DISTINCT FROM attempt.job_fence" in sql
    assert "manifest-free revocation does not match attempt lineage" in sql
    assert "expired-lease revocation lacks terminal capture evidence" in sql


def test_materialization_cursor_migration_is_monotonic_and_route_scoped():
    sql = Path("migrations/012_materialization_cursors.sql").read_text()
    assert "CREATE TABLE IF NOT EXISTS materialization_cursors" in sql
    assert "PRIMARY KEY (consumer_id,environment,bot_id,exchange,pair,timeframe)" in sql
    assert "NEW.sequence < OLD.sequence" in sql
    assert "identity cannot change at the same sequence" in sql
    assert "materialization cursors cannot be deleted" in sql


def test_outbox_claim_migration_requires_complete_unpublished_leases():
    sql = Path("migrations/013_outbox_claim_leases.sql").read_text()
    assert "claim_owner" in sql and "claim_token" in sql and "claim_expires_at" in sql
    assert "published_at IS NULL AND claim_owner IS NOT NULL" in sql
    assert "CREATE INDEX IF NOT EXISTS outbox_claimable_idx" in sql
