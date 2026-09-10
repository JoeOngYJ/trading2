# Next Steps

## Immediate priority: prove the automated hard-crash/concurrency matrix

The executable design and acceptance gates are in
[`docs/HARD_CRASH_CONCURRENCY_PLAN.md`](docs/HARD_CRASH_CONCURRENCY_PLAN.md).
The full matrix is automated: W1–W8 worker process-kill, O1–O5 live JetStream, B1–B8 bridge,
D1–D3 PostgreSQL restart/serialization, and F1–F2 Freqtrade snapshot boundaries. This includes
broker and database restart, DLQ, filesystem failure, redelivery, ACK recovery, concurrent
same-stream publication, atomic snapshot reads, and fail-closed entry gating. The focused D/F
slice passed 10 consecutive runs, and the PostgreSQL-enabled suite currently passes 147 tests.

The immutable-candidate 100-run gate passed with 100/100 matrices, 16,000 test executions, and
zero failures or errors. The immediate work remains operational proof, not strategy work:

1. Run the 24-hour accelerated chaos soak and record convergence/recovery-time percentiles.
2. Prove backup plus clean-host restore for PostgreSQL, JetStream configuration, artifacts, and
   deployment secrets/configuration.
3. Only then perform the end-to-end Freqtrade dry-run with real timestamp-safe research signals.

The repeatable runner is `ops/run_chaos_matrix.sh`; it supports `--runs 100` and
`--duration-hours 24`, fails on the first violated invariant, preserves per-run logs/JUnit, and
generates per-scenario convergence percentiles in `summary.json`.

The contract foundation is implemented: instrument registry, completed-candle snapshots,
content-addressed artifacts, source observations, sealed manifests, and v2 signal references.

Phases 1 and 2 of the capture layer are complete. The strict BTC/ETH ingress allowlist is
also implemented: instrument identity, semantic method/category/consumer, research symbol,
per-method vendor chain, and observed fallback order are enforced before evidence is accepted.
Fundamental, insider, unknown, and drifted upstream ingress fails closed.

The pure, deterministic source-policy evaluator is now implemented. It evaluates the typed
ledger and returns `pass`, `hold_only`, or `reject` without reading LLM prose or using a score.
It verifies identity, capture state, execution freshness, ledger ordering, ingress identity,
timestamps, artifact digests, fallback paths, and required/degraded/optional source outcomes.

Durable policy persistence is now implemented. The platform loads only a live fenced
`evaluating` session, uses its immutable collection cutoff, verifies artifact bytes and paths,
persists the evaluation plus the complete ordered v1 rule inventory, and atomically seals or
rejects the manifest with the policy result digest. Database triggers prevent mutation and
refuse incomplete or verdict-conflicting policy bindings.

The fenced publication rating gate is now implemented. Captured signals must carry the exact
policy result digest inside the signed payload, match the sealed run/manifest/snapshot and
`data_as_of`, preserve policy quality flags, and retain an original rating present in
`permitted_ratings`. Ratings are never rewritten. PostgreSQL independently enforces the same
binding, and the outbox refuses any payload that is not byte-equivalent JSON to an authorized
stored signal.

The TradingAgents worker now executes the complete capture → freeze → evaluate → seal/reject
→ gated-publication state machine. It freezes the per-method vendor plan before graph
construction, binds the capture to the current job fence and execution snapshot, and records
policy rejection as a terminal no-signal outcome. Infrastructure failures reject an open
capture and retry the job; stale attempts cannot close or publish it.

Signed revocation is implemented. Policy rejection, caught worker failure, and expired-lease
recovery append a distinct
signed tombstone for the latest actionable signal; they never manufacture a `HOLD`. PostgreSQL
checks the target checksum, route, sequence, current fence, evidence state, and policy reason.
The bridge atomically materializes the tombstone, older deliveries cannot overwrite it, and a
newer valid signal can recover the stream.

Expired-lease recovery is now fail-closed: it verifies the exact attempt/fence and expired lease,
closes partial evidence, appends revocation plus outbox, and releases the retry only in the same
transaction. It also covers process death before capture starts using snapshot-bound lineage.
Transition-by-transition process-kill and concurrency injection now cover two sweepers, terminal
transaction rollback, NATS redelivery, broker restart, and PostgreSQL restart.

Phase 3 research is complete. The design, discovered lifecycle gaps, revocation contract,
and failure gates are in
[`docs/PHASE3_WORKER_RESEARCH.md`](docs/PHASE3_WORKER_RESEARCH.md). Implementation should
follow its ordered checklist. The bridge subject correction, fenced renewable attempts,
audited lifecycle isolation, and typed source-policy evaluator are complete. The structural
ledger prerequisite is also complete: semantic graph invocations,
ordered vendor fallback attempts, exact router results, and the immutable `evaluating`
boundary are implemented. Capture sessions are now bound to the live fenced job attempt,
and stale workers cannot begin evaluation, seal, or reject them. Source-specific temporal
metadata is now captured for Yahoo/Alpha Vantage market data and news, StockTwits, Reddit,
verified snapshots, and identity resolution; incomplete optional-source chronology is
explicitly flagged. The crypto method allowlist, pure evaluator, and durable evaluation
persistence, the fenced publication gate, worker orchestration, signed revocation, and
hard-crash lease recovery and full failure-injection matrix automation are complete. See
[`docs/SOURCE_POLICY_RESEARCH.md`](docs/SOURCE_POLICY_RESEARCH.md).

Confirm that:

- pair and exchange mappings are exact;
- market, news, and sentiment timestamps are trustworthy;
- structured decisions always pass schema validation;
- malformed or incomplete LLM output produces no signal;
- signals expire appropriately for their timeframe;
- historical analysis cannot access future information.

## Following milestones

1. Complete a signal-to-fill Freqtrade dry-run with full audit lineage.
2. Test crashes, duplicates, stale data, clock skew, and component outages.
3. Prove off-host backup and clean-host recovery targets.
4. Harden secrets, exchange permissions, monitoring, and kill switches.
5. Run a two-week infrastructure soak using real research and dry-run execution.
6. Build a timestamp-correct historical research dataset.
7. Begin strategy and profitability work only after the infrastructure gates pass.

## Next acceptance milestone

> Deliver real, timestamp-safe BTC and ETH TradingAgents signals through the platform and prove that invalid or future-contaminated data fails closed.

Research and contract decisions are documented in
[`docs/REAL_DATA_CONTRACT.md`](docs/REAL_DATA_CONTRACT.md). The implementation milestone
and its gates are defined in
[`docs/SOURCE_CAPTURE_PLAN.md`](docs/SOURCE_CAPTURE_PLAN.md).
