# Phase 3 Worker Research and Design

**Status:** Worker orchestration, signed revocation, expired-lease recovery, and the W1–W8
worker process-kill matrix are implemented and verified. Transport v2, fenced attempts,
lifecycle isolation, deterministic policy, durable policy binding, atomic publication/no-signal
completion, bridge tombstones, and live JetStream O1–O5 recovery are implemented. Bridge
filesystem/acknowledgement B1–B8 is also verified. Database restart and execution-boundary
failure scenarios remain.

## Objective

Make one TradingAgents analysis attempt crash-safe, fully attributable, and incapable of
publishing a signal unless its execution snapshot, source ledger, manifest, typed result,
and worker ownership all remain valid at commit time.

This phase is about infrastructure correctness. It does not enable live orders, tune the
research strategy, or assess profitability.

## Research conclusion

The current Phase 2 adapter captures the enabled TradingAgents research tools, but the
worker is not yet safe to publish real results. Phase 3 must close five gaps first:

1. TradingAgents reads and writes reflection memory outside the captured tool boundary.
2. Its pre-run reflection path fetches returns directly through `yfinance`.
3. Checkpoint resume can combine old graph state with a new capture session.
4. A fixed worker lease can expire during a long LLM run, allowing concurrent attempts.
5. A failed new run leaves the previous valid signal usable until expiry.

There is also a separate wiring defect: publishers and the JetStream configuration use
`signals.v2.>`, while the bridge currently subscribes to `signals.v1.>`. This must be fixed
before any end-to-end Phase 3 test.

## Observed upstream lifecycle

At pinned TradingAgents commit
`01477f9afb7a47b849ed4c9259d3a9a4738d9fda`, a call to `propagate()` performs:

```text
resolve deferred reflection
  -> direct yfinance returns for asset and benchmark
  -> reflector LLM
  -> mutate memory log

run graph
  -> read prior memory context
  -> resolve instrument
  -> analyst tools and vendor calls
  -> LLM debate, trader, and risk nodes
  -> write state log
  -> append decision to memory log
  -> clear checkpoint on success
```

The instrument and analyst data calls are covered by the Phase 2 adapter. Direct return
fetches, memory reads, reflection LLM input/output, state-log writes, and decision-memory
writes are not. Consequently, the existing build audit proves the known research-tool
surface at the pinned commit; it does not yet prove every input and side effect in the full
`propagate()` lifecycle.

## Decisions for the first live-capture version

### 1. Disable checkpoint reuse

Set `checkpoint_enabled=False` explicitly. Every retry receives a new run, capture session,
and complete graph execution.

The current worker forces checkpointing on. The upstream checkpoint key is based on ticker,
date, and graph shape rather than the platform capture session. A retry could therefore
resume nodes whose inputs belong to an earlier session, producing an incomplete ledger for
the new session. Shared local SQLite checkpoints also complicate multi-worker scaling.

LangGraph checkpointing can be reintroduced only when each nondeterministic call is a
durably recorded, idempotent task tied to the platform attempt and checkpoint identity.

### 2. Disable upstream reflection memory initially

For the first safe version:

- skip deferred reflection and its direct return fetches;
- inject an empty `past_context`;
- suppress state-log and decision-memory file writes during graph execution;
- record these settings in the immutable configuration and provenance.

This requires a small pinned integration patch or adapter with a startup source/signature
audit. A later phase may add captured memory snapshots and an idempotent post-commit memory
outbox. Uncaptured mutable files must not influence a publishable run.

Implemented isolation forces a fresh configuration, replaces memory with a side-effect-free
empty implementation, and suppresses pending reflection and state logging on the graph
instance. The capture adapter also enforces one active installation per process and restores
all upstream module bindings after each run so sequential sessions cannot capture into one
another's ledgers.

### 3. Limit the crypto analyst set

Construct the graph explicitly with `market`, `social`, and `news` analysts. Do not enable
the fundamentals analyst for the initial BTC/ETH scope; the upstream default currently does.

### 4. Keep research and operational outcomes separate

Do not rewrite an LLM `BUY` or `SELL` into a synthetic `HOLD` when sources degrade. That
would misrepresent the research result. Instead:

- publish a degraded result only when the typed research decision is already `HOLD`;
- otherwise reject the run and publish an operational revocation of the prior actionable
  snapshot, if one exists.

## Source acceptance policy

Policy is evaluated from typed source-call rows and observations, never by parsing report
prose.

| Input | Policy | Failure behavior |
|---|---|---|
| Completed Binance execution snapshot | Required; correct pair/timeframe, closed, gap-free, immutable | Reject and revoke prior actionable signal |
| TradingAgents stock/market context | Required; correct research symbol/date and no future data | Reject and revoke |
| Verified research-market snapshot | Required; consistent identity and time boundary | Reject and revoke |
| Ticker/global news | Degradable | Only an original typed `HOLD` may publish, with quality flags |
| StockTwits/Reddit sentiment | Degradable | Only an original typed `HOLD` may publish, with quality flags |
| FRED macro | Optional enrichment; live-at-fetch | Flag absence; never claim vintage-safe replay |
| Polymarket | Optional enrichment; live-at-fetch | Flag absence |
| Fundamentals | Disabled for initial crypto scope | Any call is an allowlist violation |
| Unknown or newly introduced ingress | Forbidden | Reject startup or the active run |

All successful calls must have a normalized artifact and observation. `no_data`, timeout,
rate-limit, authentication failure, vendor failure, malformed response, wrong symbol,
staleness, and future timestamps remain distinct typed outcomes.

## Attempt state machine

```text
pending/failed job
    -> claimed(attempt, owner, lease, fence)
    -> run=running + session=collecting + manifest=collecting
    -> graph running while lease heartbeat renews
    -> policy evaluation
       -> accepted -> manifest/session sealed
                   -> fenced atomic commit of run + signal/revocation + outbox + job
       -> rejected -> fenced atomic rejection of run/session/manifest + job
                   -> revocation outbox when an old actionable snapshot exists

expired running attempt
    -> sweeper marks run/session abandoned
    -> job becomes retryable
    -> next attempt receives new run/session/manifest IDs and a new fence
```

### Claim and lease rules

- `FOR UPDATE SKIP LOCKED` remains appropriate for the queue claim.
- Claim increments both `attempt` and a monotonic fencing token.
- A heartbeat renews the lease well before expiry using
  `WHERE job_id=? AND status='running' AND lease_owner=? AND attempt=? AND fence=?`.
- Failure, abandonment, and final publication use the same ownership predicate.
- If heartbeat or final fencing fails, the worker is stale and must stop without publishing.
- The capture deadline cannot exceed the renewable job lease budget.

This provides at-least-once attempts with exactly-one accepted state transition, not a false
claim of exactly-once external computation. Duplicate LLM/vendor work may still occur after
a process or network failure, but only the current fenced owner may commit.

### Durable attempt creation

Before constructing TradingAgents or contacting any external system, one transaction must:

1. verify the execution snapshot and source observation;
2. insert `analysis_runs(outcome='running')`;
3. insert the collecting evidence manifest and capture session;
4. link the run, job, attempt, fence, session, manifest, and snapshot.

This makes failed and killed attempts observable. The current implementation inserts an
`analysis_runs` row only on success, which loses the durable record of failed work.

### Atomic success gate

The final success transaction must lock and revalidate the job, then:

1. prove owner, attempt, fence, status, and unexpired lease;
2. prove the execution snapshot still satisfies temporal policy;
3. prove the capture session and manifest are collecting and belong to this run;
4. evaluate and persist the complete ordered-ledger policy result;
5. seal the manifest and session;
6. validate the typed decision and provenance references;
7. allocate the signal sequence;
8. insert the signed envelope and outbox row;
9. mark the analysis run and job succeeded.

Any failed assertion rolls back the entire transaction. No signal may reference a collecting,
rejected, abandoned, or mismatched evidence set.

### Failure and abandonment

Expected failures use stable error codes and sanitized metadata. Raw exception strings must
not be persisted because vendor libraries can include credentials or request details.

A sweeper handles processes that cannot mark their own failure. After lease expiry and a
grace interval, it atomically marks the old running analysis, session, and manifest abandoned
before making the job retryable. A new attempt never reuses their IDs, ledger, checkpoint,
or mutable memory.

Content-addressed artifact bytes may be reused after digest verification; observations and
call rows remain attempt-specific.

## Signal revocation contract

Failure to emit a new signal is not sufficient. Freqtrade can continue reading the previous
valid local snapshot until its TTL expires, even when the platform now knows that current
research inputs are invalid.

Add a signed, sequenced `signal.revoked` control event for the same environment, bot,
exchange, pair, and timeframe. The event must contain a reason code and reference the signal
being revoked. It advances the normal sequence and is stored in the signal/outbox audit trail.

Bridge behavior must be atomic:

- authenticate and sequence-check the revocation;
- remove or replace the materialized actionable snapshot with a non-actionable tombstone;
- persist the new last-seen sequence before acknowledging the message;
- make missing/corrupt/revoked snapshots fail closed for entries;
- never use revocation to block protective exits, stop losses, or exchange liquidation.

The Freqtrade process continues to read only local materialized state. Network and heavy work
must remain outside `confirm_trade_entry()`, which serves only as a fast final freshness and
revocation check.

## Schema changes anticipated

Exact migration SQL belongs to implementation, but the contract needs:

- `analysis_jobs.fencing_token`;
- `analysis_runs` links to attempt, fence, capture session, and manifest;
- terminal outcomes including `rejected` and `abandoned`;
- sanitized `error_code` and structured error metadata in place of raw errors;
- capture-session links to job and attempt/fence;
- a persisted source-policy result and version;
- revocation fields identifying target signal and reason;
- bridge materialization state that atomically tracks last sequence and active/revoked status.

Database constraints should enforce cross-record identity and terminal-state compatibility;
application checks alone are insufficient.

## Failure-injection acceptance tests

Implementation is not complete until tests kill or pause the worker at every boundary:

- after job claim;
- after run/session creation;
- before and after each captured vendor result;
- during an LLM node;
- after graph completion but before policy evaluation;
- during manifest sealing;
- after sequence allocation;
- after signal insert but before outbox/job updates;
- after transaction commit but before process acknowledgement;
- after lease expiry while the original worker is still running;
- during bridge materialization and before JetStream acknowledgement.

For every case, prove:

- no incomplete or stale-owner attempt publishes;
- terminal attempt records remain inspectable;
- a retry uses new identity and a complete ledger;
- duplicate delivery is harmless;
- sequence never moves backward;
- policy rejection revokes older actionable materialization;
- bridge restart converges to the database/outbox truth;
- protective exits remain available;
- logs and stored errors contain no secrets.

## Recommended implementation order

1. **Complete:** Fix the `signals.v1`/`signals.v2` bridge subject mismatch and add a wiring test.
2. **Complete:** Add durable attempt records, fence tokens, lease renewal, and abandonment recovery.
3. **Complete:** Disable checkpointing, reflection memory, and fundamentals through the pinned adapter.
4. **Complete:** Implement and unit-test the typed source-policy evaluator.
5. **Complete:** Add fenced seal/reject, publication, and terminal no-signal transactions.
6. **Complete:** Implement signed revocation and atomic bridge tombstones.
7. **In progress:** Add transition-by-transition failure injection and concurrency tests.
8. Run BTC/ETH shadow traffic only after all gates pass.

## External basis

- [LangGraph Functional API](https://docs.langchain.com/oss/python/langgraph/functional-api)
  requires nondeterministic API calls and side effects to be idempotent tasks for reliable
  resume behavior.
- [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
  restores checkpoints and successful pending writes, which is why checkpoint identity must
  align with the platform attempt and capture ledger.
- [PostgreSQL `SELECT`](https://www.postgresql.org/docs/17/sql-select.html) documents
  `SKIP LOCKED` as suitable for queue-like multi-consumer access.
- [Freqtrade strategy customization](https://www.freqtrade.io/en/latest/strategy-customization/)
  defines completed-candle signal timing and next-candle execution behavior.
- [Freqtrade callbacks](https://www.freqtrade.io/en/stable/strategy-callbacks/) identifies
  `confirm_trade_entry()` as the last entry gate and warns against network or heavy work there.
