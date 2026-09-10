# TradingAgents Source-Capture Milestone

**Implementation status:** Phases 1 and 2 research-tool capture complete; Phase 3 orchestration
implemented, with its exhaustive crash-injection gate still in progress.
The v2 transport correction and fenced renewable worker-attempt foundation are implemented;
audited lifecycle isolation now disables checkpoint reuse, upstream reflection memory,
state-log writes, and fundamentals. The semantic-invocation/vendor-attempt ledger,
immutable `evaluating` boundary, and fenced capture-session identity are implemented.
Source-specific temporal metadata, pre-render news/social hooks, and the strict BTC/ETH
ingress allowlist, pure source-policy evaluator, durable policy persistence, and atomic
policy-bound seal/reject transitions and the fenced publication gate are also implemented.
The worker now runs the pinned graph only inside a fenced capture, freezes collection before
policy evaluation, and atomically commits policy close with either the original permitted signal
or a signed revocation of the latest actionable signal. The bridge materializes revocations as
fail-closed tombstones. Expired-lease recovery now emits the same tombstone atomically; the
complete process-kill and concurrency matrix remains pending.

Phase 3 lifecycle research found that upstream reflection returns, mutable memory context,
and state/memory file writes sit outside the Phase 2 research-tool boundary. They must be
disabled or captured before the full `propagate()` lifecycle can be called closed. See
[`PHASE3_WORKER_RESEARCH.md`](PHASE3_WORKER_RESEARCH.md) for the worker design and gates.

## Goal

Run pinned TradingAgents research in **live-capture mode** while proving exactly which
external inputs reached the graph. A signal may be published only when every consumed
input is stored, integrity-checked, policy-validated, and linked through a sealed evidence
manifest.

This milestone does not optimize prompts, trading logic, or profitability.

## Definition of success

For one BTC or ETH run, we must be able to answer and prove:

1. Which instrument, completed Binance candle, TradingAgents commit, configuration, and
   model versions were used?
2. Which vendor functions were called, with which sanitized arguments and fallback path?
3. What exact bytes or canonical values were returned, when were they first seen, and
   which values were supplied to each analyst?
4. Were any required sources missing, stale, corrupt, mismatched, or obtained after the
   allowed time boundary?
5. Can the research graph be rerun with network access disabled using only captured data?

Success means all five answers come from durable records—not application logs.

## Architectural decision

Add a small integration layer at TradingAgents' **semantic dataflow boundary**. Do not
capture generic HTTP traffic and do not monkey-patch `requests`: that loses source meaning,
misses yfinance internals, risks storing credentials, and cannot prove which transformed
value reached an analyst.

The adapter has two modes:

```text
live_capture:
  TradingAgents call → capture adapter → pinned vendor function
                    → store raw/canonical artifact + observation
                    → return captured value to TradingAgents

captured_replay:
  TradingAgents call → capture adapter → exact observation lookup
                    → verify digest and time policy
                    → return stored value (network forbidden)
```

The manifest remains `collecting` while the graph makes dynamic tool calls. Each response
is persisted before it is returned to the graph. After the graph finishes, the worker
validates the complete call ledger, seals the manifest, and only then constructs a signal.
No observation may be added after sealing.

## Capture surface for v0.3.1

| Boundary | Methods | Category | Initial policy |
|---|---|---|---|
| `dataflows.interface.route_to_vendor` | stock data, indicators | research market | Required |
| `dataflows.interface.route_to_vendor` | ticker/global news | news | Required, may degrade to HOLD |
| Direct sentiment fetch | StockTwits, Reddit | social | Optional; live-only |
| Routed FRED calls | macro indicators | macro | Optional; replay unsafe without vintage |
| Routed Polymarket calls | prediction markets | prediction | Optional; live-at-fetch |
| Fundamental methods | statements/insiders | fundamental | Disabled for initial crypto scope |
| Verified market snapshot | Yahoo-derived validation | research market | Required |

The direct StockTwits and Reddit imports bypass `route_to_vendor`, so the pinned adapter
must explicitly redirect those functions as well. A startup audit must compare the known
function inventory with the pinned upstream commit and refuse to run if the surface changes.

## Records added in this milestone

### Capture session

One session per analysis attempt:

- session/run/manifest IDs and `collecting`, `sealed`, `rejected` state;
- pinned upstream commit and package version;
- execution snapshot, instrument, mode, process and container revision;
- collection start/deadline/end and rejection reason.

### Source call ledger

One row per invocation, including repeated calls:

- monotonically increasing call ordinal;
- semantic method, category, resolved vendor and fallback attempt;
- canonical sanitized arguments hash;
- started/completed/first-seen timestamps and latency;
- outcome: available, no-data, timeout, rate-limit, vendor error, policy rejection;
- raw artifact digest, normalized-return artifact digest, and observation ID;
- analyst/tool consumer when known.

Secrets, authorization headers, API keys, cookies, and signed query parameters must be
removed before persistence. Tests must prove redaction.

### Manifest policy result

The sealed manifest records required-source results, duplicate calls, fallbacks, replay
safety, staleness, temporal violations, and the ordered call-ledger digest. Its digest must
cover the order and hashes of every consumed normalized value.

## Runtime rules

1. The worker creates a capture session before constructing the TradingAgents graph.
2. Historical dates are rejected in `live_capture`; live-only sources may never service a
   historical request.
3. Every external result is written and fsynced before it is returned to an analyst.
4. Vendor exceptions are captured as typed outcomes; arbitrary exception strings are not
   passed into manifests because they may contain secrets.
5. Calls not in the allowlist fail closed. Network egress is restricted to approved vendor
   and LLM endpoints at deployment level.
6. Required market context must match the registry symbol and allowed date window.
7. News/social items newer than the analysis boundary are excluded and recorded as policy
   rejections; publisher time never overrides `first_seen_at`.
8. Missing required market data rejects the run. Missing news or social data can only yield
   a quality-flagged HOLD/no-entry signal.
9. The manifest is sealed after the graph finishes and before signing/publication.
10. Replay mode disables vendor network access and requires an exact method/vendor/argument
    match; cache misses reject the run.

## Implementation phases

### Phase 1 — Session and call-ledger contract

- Add capture-session and source-call tables, constraints, indexes, and state transitions.
- Add canonical argument hashing, credential redaction, typed error classification, and
  artifact helpers.
- Make sealed manifests immutable with database triggers or revoked update privileges.

**Gate:** database tests prove ordering, immutability, redaction, and retry isolation.

Implemented in `migrations/003_source_capture.sql`, `trading_platform.capture`, and the
strict capture models. The migration and sealed-ledger mutation test pass against PostgreSQL.

### Phase 2 — Pinned TradingAgents adapter

- Maintain a minimal patch against exact commit `01477f9afb7a47b849ed4c9259d3a9a4738d9fda`.
- Wrap `route_to_vendor`, verified snapshot access, StockTwits, and Reddit at their semantic
  return boundary.
- Persist raw vendor responses when accessible and always persist the exact normalized value
  returned to the graph.
- Reject startup if package version, commit, signatures, or capture inventory differ.

**Gate:** fixture tests cover every enabled research-tool method and prove no enabled tool
ingress bypasses capture. Full graph-lifecycle closure is a Phase 3 prerequisite.

Implemented in `trading_platform.tradingagents_capture`. The worker image is pinned to
commit `01477f9afb7a47b849ed4c9259d3a9a4738d9fda` and runs `platform-capture-audit`
during its build. The build fails on version, source hash, vendor inventory, or ingress
binding drift. Live fixture calls verified concurrent-safe ordinals, normalized artifact
storage, typed timeout capture, sealing, and replay-safety propagation.

Runtime adapter installation is exclusive within a worker process and all patched upstream
bindings are restored after a run. This prevents sequential or accidentally concurrent
capture sessions from contaminating one another.

### Phase 3 — Worker state machine

```text
snapshot verified → session collecting → graph running
                 → policy validation → manifest sealed
                 → typed result validated → signed signal committed
```

- Replace the current TradingAgents publication block with this state machine.
- On crash, leave a rejected/abandoned attempt with no signal; retries receive new run and
  manifest IDs but may reuse verified content-addressed artifacts.
- Include manifest, adapter, upstream commit, and call-ledger digest in provenance.

The state machine is implemented. Unit tests prove policy rejection creates no signal and a
research failure rejects an open capture before retry. The remaining Phase 3 gate is the full
database-backed kill/concurrency matrix at every transition, together with signed revocation.

**Gate:** kill the worker at every transition and prove no incomplete attempt publishes.

### Phase 4 — Deterministic replay

- Run the same pinned graph in a network-denied container using stored normalized artifacts.
- Verify identical input ledger and typed-output validity. LLM output is not expected to be
  byte-identical unless model determinism is independently guaranteed; input reconstruction is.
- Record output differences rather than claiming deterministic LLM behavior.

**Gate:** any attempted vendor network access or uncaptured call fails the replay.

### Phase 5 — Live BTC/ETH shadow validation

- Opt-in smoke tests with no Freqtrade entries.
- Compare Yahoo USD context with Binance USDT execution data and record the basis explicitly.
- Exercise timeouts, 429s, malformed payloads, stale data, clock skew, fallback changes,
  corrupt artifacts, and upstream signature drift.

**Gate:** at least 100 consecutive captured runs with complete lineage, zero uncaptured calls,
zero actionable signals on degraded required data, and successful offline replay samples.

## Deliverables

- Migration for capture sessions, call ledger, manifest immutability, and provenance fields.
- `trading_platform.capture` adapter API and policy engine.
- Minimal pinned upstream patch with a documented rebase procedure.
- Sanitized fixtures for every enabled source; no proprietary or credential-bearing payloads.
- Unit, integration, offline-replay, failure-injection, and opt-in live smoke tests.
- Operational metrics: calls/outcomes by vendor, capture latency, manifest rejection reasons,
  uncaptured-call count, replay misses, artifact verification failures, and source freshness.
- Runbook for upstream upgrades and emergency source disablement.

## Explicit non-goals

- Historical backtesting from live APIs.
- Treating LLM output as deterministic.
- Using raw prompts/logs as the evidence store.
- Capturing LLM provider payloads in this phase; that requires a separate privacy and retention
  decision.
- Enabling live orders or evaluating strategy profitability.

## Final acceptance checklist

- [ ] Every enabled TradingAgents data ingress is inventoried and intercepted.
- [ ] Exact normalized inputs are immutable and digest-verifiable.
- [ ] Credentials and personal identifiers follow documented redaction/retention rules.
- [ ] Manifest ordering and source policy are mechanically validated.
- [ ] Missing, stale, future, corrupt, wrong-symbol, and changed-upstream inputs fail closed.
- [ ] No signal exists for collecting, abandoned, or rejected sessions.
- [ ] Captured replay succeeds with vendor network access disabled.
- [ ] BTC and ETH complete the shadow-run gate before real research is exposed to Freqtrade.
