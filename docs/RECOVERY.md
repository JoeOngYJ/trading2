# Backup and Recovery Runbook

## Targets and limitations

The v1 target is RPO ≤5 minutes and RTO ≤30 minutes. A single-node deployment cannot
remain available through total host failure; these targets depend on frequent verified
off-host backups and a prepared replacement host.

`ops/backup.sh` creates a PostgreSQL custom-format dump, captures configuration and
contracts, and sends them to an operator-configured off-host Restic repository. Schedule
it at least every five minutes and alert when the last successful snapshot is older than
five minutes. Confirm a complete backup finishes within that interval under production
load; otherwise adopt PostgreSQL WAL-G/pgBackRest continuous archiving before live use.

JetStream is not the source of truth. Its volume may be snapshotted, but committed
signals can always be republished from PostgreSQL outbox records.

## Restore drill

These steps overwrite the selected replacement database. Resolve the exact replacement
host and backup snapshot before running them.

1. Enable the external/global entry stop and ensure exchange-side protective orders remain active.
2. Provision a clean host with the pinned Docker and Compose versions.
3. Restore repository files and `.env` from the encrypted configuration backup.
4. Start only PostgreSQL and NATS.
5. Fetch the selected Restic snapshot into a new temporary restore directory.
6. Restore the dump with `pg_restore --clean --if-exists` into the empty `platform` database.
7. Verify signal counts, latest sequences, outbox state, execution events, kill switches, and checksums.
8. Mark outbox rows missing current broker messages as unpublished; start the outbox relay.
9. Start bridges and confirm signed snapshots rebuild and receipts remain idempotent.
10. Start audit API, monitor, and reconciler; compare Freqtrade REST state with the execution ledger.
11. Start workers and scheduler only after reconciliation succeeds.
12. Start Freqtrade in dry-run or paused state. Disable the kill switch only after operator sign-off.

Record actual data-loss window and elapsed restore time. A drill is unsuccessful if it
exceeds either target, relies on an undocumented credential, or produces an unmatched
order or signal.

## Component-specific recovery

### Lost JetStream volume

Start a clean broker, recreate streams, set `published_at = NULL` only for the required
outbox range, and allow replay. Event IDs and delivery receipts prevent duplicate materialization.

### Lost snapshot volume

Stop new Freqtrade entries, restore the bridge, and replay the latest signal for each
bot/pair/timeframe. Never manually insert an unverified JSON snapshot.

### Lost worker checkpoint

The job lease expires and analysis restarts. Because LLM output is nondeterministic, the
restarted attempt becomes a new run; it must never overwrite a committed signal.

### Webhook outage

Keep webhook retries short so they do not delay the bot. The reconciler queries the
authenticated Freqtrade REST API and inserts deterministic recovery events.
