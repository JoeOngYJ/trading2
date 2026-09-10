# TradingAgents + Freqtrade Infrastructure Feasibility Study

**Version:** 2.0  
**Date:** 2026-08-23  
**Decision:** Feasible for asynchronous 5–60-minute research, subject to dry-run and recovery gates.

## Conclusion

Tauric Research TradingAgents can serve as a first-layer research producer while
Freqtrade remains the execution engine. This architecture cannot guarantee profit;
profitability depends on strategy quality, costs, market regime, risk controls, and live
execution. It can guarantee strict validation, durable storage, replayable delivery,
idempotent consumption, stale-data rejection, and complete audit lineage within stated
recovery limits.

TradingAgents is explicitly research-oriented and LLM results are nondeterministic. Its
current release supports crypto mode, typed decision schemas, configurable retry budgets,
and checkpoint resume. Freqtrade provides external-data callbacks, dry-run execution,
webhooks, an authenticated REST API, and persistent trade metadata. Neither system alone
provides a guaranteed research-to-exchange transaction.

Primary references:

- [TradingAgents upstream and persistence](https://github.com/TauricResearch/TradingAgents)
- [TradingAgents structured schemas](https://github.com/TauricResearch/TradingAgents/blob/main/tradingagents/agents/schemas.py)
- [Freqtrade strategy callbacks](https://www.freqtrade.io/en/stable/strategy-callbacks/)
- [Freqtrade REST and WebSocket API](https://www.freqtrade.io/en/stable/rest-api/)
- [Freqtrade webhook retry behavior](https://www.freqtrade.io/en/stable/webhook-config/)
- [NATS JetStream delivery model](https://docs.nats.io/concepts/jetstream)
- [PostgreSQL point-in-time recovery](https://www.postgresql.org/docs/current/continuous-archiving.html)

## Implemented architecture

The original shared-volume transport has been replaced. A shared file alone cannot
prove whether a producer committed, a consumer read, or an execution used a particular
version. The implemented pipeline is:

1. Database-leased jobs invoke synthetic research or a pinned TradingAgents worker.
2. Analysis run, immutable signed signal, monotonic sequence, and outbox event commit atomically.
3. The outbox publishes to file-backed JetStream using `event_id` for deduplication.
4. A durable bridge validates HMAC, checksum, schema, routing, timestamps, status, sequence, expiry, and kill switches.
5. The bridge records a receipt and atomically replaces a local Freqtrade snapshot before acknowledging.
6. Freqtrade loads snapshots in `bot_loop_start()` and performs no remote work in order-critical callbacks.
7. Webhooks provide fast execution feedback; periodic REST reconciliation repairs gaps.

This is at-least-once delivery with idempotent effects. “Exactly once” is intentionally
not claimed across PostgreSQL, NATS, Freqtrade, and an exchange.

## Reliability and scaling assessment

The single-node Compose deployment is suitable for an initial universe of up to 50 pairs
at 5–60-minute cadence. Workers scale horizontally through leased jobs, while each
Freqtrade bot receives an independently scoped durable consumer and snapshot. PostgreSQL
remains the replay source if JetStream is lost.

New entries fail closed when signals or bridge health are missing, stale, corrupt,
future-dated, revoked, or mismatched. Protective exits remain independent of the LLM
layer. HMAC signatures and explicit pair mapping prevent silent tampering and symbol
translation errors.

Single-node deployment is not highly available. Live use requires demonstrated off-host
backup RPO ≤5 minutes, clean-host RTO ≤30 minutes, two weeks of dry-run, failure injection,
and full signal-to-fill reconciliation. Near-zero host-failure downtime would require a
later replicated PostgreSQL deployment, a three-node JetStream cluster, and orchestrated
multi-host failover.

## Verified implementation state

- Strict versioned signal contract and signed envelope
- PostgreSQL jobs, runs, sequences, signals, outbox, receipts, audit, heartbeats, and kill switches
- JetStream relay, durable consumer, dead-letter handling, and replay semantics
- Atomic per-pair snapshot bridge and fail-closed Freqtrade reference strategy
- Webhook audit ingress and REST reconciliation
- Docker Compose isolation, health checks, pinned infrastructure images, and non-root platform services
- Prometheus-format metrics, backup/readiness/kill-switch operations, and recovery runbooks
- Automated tests for contract invariants, tampering, expiry, future data, pair mapping, parser validation, and atomic snapshots

Strategy development and profitability claims remain intentionally out of scope.
