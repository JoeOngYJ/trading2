# Hard-Crash and Concurrency Validation Plan

**Status:** Bounded retry for JetStream stream validation and durable binding passed 100 repeated
real NATS restarts, then the newest immutable candidate passed 100/100 matrices (16,100
executions, zero failures, errors, or skips). Its 24-hour soak is the remaining reliability gate.

## Objective

Prove that process death, restart, duplicate delivery, reordering, and competing replicas cannot:

- publish an unauthorized signal;
- leave a revoked signal actionable;
- lose a committed signal or revocation;
- let a stale worker mutate a newer attempt;
- move a stream snapshot backwards;
- create conflicting terminal state.

This milestone validates infrastructure only. It does not evaluate trading strategy or profit.

## Required invariants

1. **Fenced ownership:** only the current job attempt and fencing token may mutate its run,
   capture, policy decision, signal, or revocation.
2. **Atomic publication:** a created/revoked event and its outbox row either both commit or both
   roll back.
3. **Recoverable delivery:** after commit, an event remains in PostgreSQL or JetStream until the
   bridge records a terminal receipt.
4. **Monotonic materialization:** the snapshot for a route may only advance to a higher sequence.
5. **Fail-closed revocation:** after convergence, the latest revocation cannot coexist with an
   actionable older snapshot.
6. **Idempotency:** repeated recovery, publication, delivery, and acknowledgement have the same
   final state as one successful execution.
7. **Bounded convergence:** after dependencies recover, durable state and the snapshot converge
   within a configured deadline.
8. **Audit completeness:** every terminal job, event, receipt, retry, and rejection remains
   attributable to its job, attempt, fence, run, snapshot, and reason.

## Fault matrix

### Worker and lease recovery

| ID | Kill point | Expected result |
|---|---|---|
| W1 | After job claim, before run creation | Lease recovery creates an auditable recovery run, revokes any latest actionable signal, then retries the job. |
| W2 | After run creation, before capture creation | Same outcome without fabricated capture evidence. |
| W3 | During source capture | Partial evidence becomes rejected/abandoned; revocation precedes retry release. |
| W4 | After collection closes, during policy evaluation | Open transaction rolls back; lease recovery closes the prior durable state. |
| W5 | During signal/revocation transaction | All run, policy, event, outbox, and job changes roll back together. |
| W6 | Immediately after terminal commit | Recovery performs no conflicting mutation; the outbox remains deliverable. |
| W7 | Old worker resumes after lease recovery | Every stale write is rejected by attempt/fence checks. |
| W8 | Two sweepers recover the same lease | `SKIP LOCKED` permits one winner and exactly one recovery result. |

### Outbox and JetStream

| ID | Fault point | Expected result |
|---|---|---|
| O1 | Before publish | Outbox remains pending. |
| O2 | After JetStream accepts, before `published_at` commit | Republish is deduplicated or consumed idempotently by event ID. |
| O3 | After `published_at` commit | Event exists durably in JetStream. |
| O4 | Two outbox replicas select the same row | Duplicate sends cannot create duplicate materialization or regress state. |
| O5 | NATS unavailable/restarted | Backoff occurs; the PostgreSQL outbox remains authoritative and later drains. |

### Bridge, filesystem, and acknowledgement

| ID | Fault point | Expected result |
|---|---|---|
| B1 | Before validation/materialization | JetStream redelivers. |
| B2 | After atomic snapshot rename, before receipt commit | Redelivery safely rewrites the same event and records one receipt. |
| B3 | After receipt commit, before ACK | Redelivery is classified duplicate and ACKed. |
| B4 | Sequences `N` and `N+1` handled concurrently | The final file and durable accepted receipt represent `N+1`. |
| B5 | Revocation races its target signal | Final state is the revocation tombstone. |
| B6 | Invalid event during DLQ publication | Original message is never silently lost; DLQ or redelivery remains durable. |
| B7 | Disk full, read-only volume, or rename failure | No receipt is committed; message is retried and Freqtrade sees the last valid complete file. |
| B8 | Bridge/NATS restart | Durable consumer resumes without sequence regression. |

### Database and execution boundary

| ID | Fault point | Expected result |
|---|---|---|
| D1 | PostgreSQL restart during each transaction | Transaction is wholly committed or wholly absent. |
| D2 | Stale/forged fence, checksum, route, or sequence | PostgreSQL rejects the write. |
| D3 | Concurrent created/revoked events on one route | One serial order is established; sequence and snapshot converge to its maximum. |
| F1 | Freqtrade reads while snapshot is replaced | It reads one complete signed envelope, never partial JSON. |
| F2 | Latest file is a tombstone, expired, malformed, or wrongly routed | New entries remain disabled; protective exits remain enabled. |

## Test harness design

Use a dedicated Compose profile with isolated PostgreSQL, JetStream, artifact, and snapshot
volumes. Never run fault injection against production volumes.

Add test-only named checkpoints to the worker, outbox, and bridge. Checkpoints are disabled by
default and may activate only when both conditions hold:

- `PLATFORM_ENVIRONMENT=test`;
- `PLATFORM_FAULT_INJECTION=1`.

At a selected checkpoint, the process writes a marker to a test volume, flushes it, and pauses.
The external harness then sends `SIGKILL`, restarts the required service, advances the test clock
or lease, and queries durable state. External process death is required; raising an exception is
not a substitute because normal exception handling would run.

Each scenario receives unique job, event, route, and consumer identifiers. Assertions poll with
a strict deadline and print a compact state dump on failure. Tests must not depend on arbitrary
sleeps.

## Required hardening before parallel bridge tests

Materialization must serialize by `(environment, bot_id, exchange, pair, timeframe)` inside
PostgreSQL. Add a durable per-stream materialization cursor and lock it before comparing or
committing a sequence. Because the filesystem write and receipt cannot form one atomic database
transaction, the signed file must also participate in recovery:

1. lock stream cursor;
2. read and verify the current signed file, then compare the incoming event against both the
   cursor and file sequence;
3. reject lower sequences and reject equal sequences with a different event identity;
4. if the file already contains the same event, repair the missing receipt/cursor without
   rewriting it—this is the crash-after-rename recovery path;
5. otherwise atomically replace the file, insert the receipt, and advance the cursor;
6. ACK only after the database commit.

Outbox replicas now claim disjoint batches using `FOR UPDATE SKIP LOCKED`, a random claim token,
owner identity, and bounded expiry. Claims commit before NATS I/O. Only the current unexpired
owner/token may mark publication; failure releases only the matching claim, and process death
allows another relay to recover it after expiry. Live JetStream crash/restart validation covers
O1–O5.

## Implementation order

1. Add the test-only checkpoint mechanism and scenario state dumper.
2. Add the per-stream bridge cursor/lock and concurrent materialization tests.
3. Add leased outbox claims and multi-relay tests.
4. Implement W1–W8 worker/lease scenarios.
5. Implement O1–O5 outbox/NATS scenarios.
6. Implement B1–B8 bridge/filesystem scenarios.
7. Implement D1–D3 and F1–F2 restart/execution-boundary scenarios.
8. Run the full matrix repeatedly, then run a 24-hour accelerated chaos soak.

W1–W8 are automated against PostgreSQL 17. Each scenario launches the actual worker process,
waits for a durable checkpoint marker, sends `SIGKILL`, expires the lease where applicable, and
asserts recovery state. TradingAgents graph execution is replaced only by a deterministic result
stub so capture and transaction orchestration remain the production code paths. The matrix has
passed 10 consecutive runs; the final milestone still requires 100 runs together with all other
scenario groups.

O1–O5 are automated against live JetStream and PostgreSQL. They prove pending-event recovery
before publish, message-ID deduplication after broker acceptance but before database marking,
durability after marking, disjoint multi-relay publishing, and backlog preservation plus drain
across a real NATS container stop/start. The matrix has passed 10 consecutive runs.

B1–B8 run the actual long-lived bridge process and durable consumer. They prove redelivery after
kill-before-validation, signed-file reconciliation after rename-before-receipt, duplicate ACK
after receipt-before-ACK, monotonic concurrent delivery, revocation-race tombstones, malformed
message termination into DLQ, retry after a read-only snapshot volume, and reconnect after a real
NATS stop/start. Five consecutive full runs (40 live failure scenarios) passed with the production
five-second ACK timeout.

D1 restarts PostgreSQL while the worker is paused inside its critical terminal transaction and
proves that run, signal, outbox, and job changes are wholly absent before lease recovery. D2
combines stale worker fencing, signed-envelope/database triggers, and direct monotonic-cursor
forgery checks. D3 runs two real workers against one stream and proves gap-free sequence
allocation; B4/B5 separately prove concurrent created/revoked materialization converges to the
maximum sequence.

F1 repeatedly replaces a signal with a signed revocation while concurrent instances of the
shipped strategy read the file; every observed file is complete, schema-valid, and
signature-valid. F2 proves that revocations, expiry, malformed JSON, wrong routing, and `Hold`
all block entry. The final entry gate now admits a long only for `Buy` (and a short only for
`Sell` when shorting is explicitly enabled). Freqtrade ROI and stop-loss configuration remains
independent of snapshot state. The focused D/F slice passed 10 consecutive runs; this is not yet
the required 100-run full-matrix gate.

## Exit criteria

The milestone passes only when:

- every matrix row is automated and deterministic;
- the suite passes at least 100 consecutive runs with no invariant violation;
- the 24-hour accelerated soak has zero lost events, unauthorized publications, sequence
  regressions, stale-fence writes, or actionable post-revocation snapshots;
- recovery-time objectives are measured and documented;
- failure diagnostics identify the job, attempt, fence, event, stream, and checkpoint;
- actionable Freqtrade operation remains disabled until these gates pass.

The first two implementation slices are complete: the checkpoint harness pauses a process only under
two explicit test guards, the external harness can send a real `SIGKILL`, and bridge replicas
serialize through a monotonic cursor while reconciling the signed file after a rename-before-
commit crash. Outbox relays now use fenced expiring claims, and PostgreSQL concurrency tests prove
disjoint multi-relay batches plus expired-claim recovery. W1–W8 worker process-kill, live
JetStream O1–O5, bridge B1–B8, D1–D3 PostgreSQL boundaries, and F1–F2 Freqtrade execution
boundaries are automated. The next step is the 100-consecutive-run full matrix followed by the
24-hour accelerated soak and recovery-time reporting.

For container scenarios, use the isolated override with a selected checkpoint:

```bash
PLATFORM_FAULT_CHECKPOINT=worker.after_claim \
  docker compose -f compose.yaml -f compose.chaos.yaml up worker
```

Run the repeatable acceptance gate only against explicitly isolated containers:

```bash
CHAOS_ACKNOWLEDGE_ISOLATED=1 \
TEST_POSTGRES_URL=postgresql://platform:platform@<test-postgres>:5432/platform \
TEST_POSTGRES_CONTAINER=<test-postgres-container> \
TEST_NATS_URL=nats://<test-nats>:4222 \
TEST_NATS_CONTAINER=<test-nats-container> \
ops/run_chaos_matrix.sh --runs 100
```

Use `--duration-hours 24` for the soak. The runner is fail-fast and writes one log and JUnit
report per iteration plus `runs.jsonl` and `summary.json`. Scenario p50/p95/p99 values include
fault injection, recovery, and assertions, so they are conservative convergence measurements.
