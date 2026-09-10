# Operations Runbook

## Service responsibilities

| Service | Durable responsibility | Safe failure behavior |
|---|---|---|
| PostgreSQL | Jobs, runs, signals, outbox, receipts, execution audit | New delivery pauses; Freqtrade entries fail closed |
| Scheduler | Creates unique per-candle research jobs | No new analysis; existing jobs remain |
| Worker | Runs TradingAgents and commits signal + outbox | Lease expires and job retries with backoff |
| Outbox | Publishes committed events to JetStream | Unpublished rows remain replayable |
| JetStream | Durable notification delivery | PostgreSQL can rebuild the stream |
| Bridge | Validates and atomically materializes newest signals | Heartbeat expires; new entries stop |
| Freqtrade | Strategy evaluation and exchange execution | Protective execution remains independent of LLM |
| Audit API | Low-latency execution feedback | Reconciler recovers missing webhook events |
| Reconciler | REST-based execution state repair | Alerts and retries without touching Freqtrade DB |

## Daily checks

Run `ops/check_readiness.sh` and investigate:

- unpublished outbox age greater than 10 seconds;
- dead analysis jobs;
- bridge or reconciler heartbeat older than 60 seconds;
- any `rejected`, `expired`, or dead-letter growth;
- host clock drift, disk pressure, container restart loops, or failed backups;
- Freqtrade trades without corresponding signal lineage.

The bridge health file must stay newer than `PLATFORM_BRIDGE_HEALTH_MAX_AGE`.
Freqtrade treats any older or malformed file as unhealthy and clears its in-memory signals.

## Kill switches

Enable globally before maintenance, unexplained reconciliation differences, database
recovery, clock drift, schema deployment, or exchange irregularities:

```bash
ops/kill_switch.sh enable global "maintenance"
```

The bridge refuses to materialize new signals while enabled. Existing snapshots expire
naturally. To stop entries immediately, also pause Freqtrade through its private API or
stop the bot after confirming how open positions will be managed.

## Deployment procedure

1. Enable the global kill switch.
2. Confirm outbox backlog is zero and take an off-host backup.
3. Build images and run unit and contract tests.
4. Apply changes with `docker compose up -d --build`.
5. Confirm health checks, service heartbeats, broker stream state, and database counts.
6. Produce one synthetic HOLD event and trace its IDs through signal, outbox, receipt, and snapshot.
7. Restart the outbox and bridge and repeat the event to confirm idempotency.
8. Disable the kill switch only after reconciliation reports no differences.

Pin release tags and production image digests. Do not automatically track
TradingAgents `main` or an unreviewed Freqtrade update.

## Scaling to 50 pairs

- Add worker replicas; database `SKIP LOCKED` leases distribute jobs safely.
- Set concurrency from provider rate limits and observed analysis duration, not CPU alone.
- Create one bridge durable consumer and snapshot volume per Freqtrade bot.
- Give each bot a unique `bot_id`, NATS durable name, signal scope, and Freqtrade database.
- Alert when analysis duration approaches signal cadence or expiry.
- Move to replicated PostgreSQL and a three-node JetStream cluster before requiring host-level HA.

## Live-readiness gates

Do not add exchange credentials until all gates pass:

- two-week dry-run with zero stale or malformed entries;
- crash tests at each persist/publish/materialize boundary;
- duplicate and out-of-order event tests;
- successful backup restore on a clean host;
- measured RPO no worse than five minutes and RTO no worse than thirty minutes;
- reviewed non-LLM exits, stop-loss behavior, and operator kill procedure;
- complete signal → intent → order → fill → exit traceability.

