# BTC unified backtest engine E1-v10 architecture and identity plan

Stage: `E1-v10 preimplementation`
Experiment ID: `btc-unified-backtest-engine-e1-v10`
Actionable arm: `no_trade`

## Scope and inheritance

E1-v10 is a clean-room implementation identity. It inherits the combined E0-v1 through E0-v4
economics and every E1-v9 architecture requirement except the three corrections frozen below.
E1-v4 through E1-v9 are immutable negative evidence, never implementation inputs.

This is offline, synthetic, zero-capital infrastructure only. Historical rows/results, sealed 2026
and partial OB0 data, credentials, networks, exchanges, databases, NATS, Freqtrade, protected
services, strategies, metrics, routing, paper and live execution are prohibited. Only `no_trade` is
actionable. Implementer-readable records contain no numerical terminal oracle outputs; independent
oracle expectations are derived only after an immutable snapshot.

After independent preflight PASS only, the exact paths are:

- `src/trading_platform/btc_accounting_state_machine_e1_v10.py`;
- `research/btc/tests/test_btc_accounting_state_machine_e1_v10.py`;
- `research/btc/candidates/unified-backtest-engine-e1-v10/`.

The implementer may read accepted E0-v1–v4, this V10 plan/contract, and exact authorities only. It
must not inspect, search, read, import, execute, copy, diff, summarize, or repair prior/invalid E1
artifacts, results, snapshots, qualifications, or reviewer oracles.

## Preserved V9 architecture

The sole construction path is an `AuthorityVerifiedFactory` that verifies role-labelled exact
manifest-bound active/snapshot implementation, V10 contract, execution, selected mandate,
instrument-rule, margin-rule, source-evidence, and semantic-settings bytes. It internally derives
all hashes; callers cannot supply a digest, path, cost, fee, margin, source, or identity override.
It returns an immutable `AccountingStateMachine` with immutable binding and phase.

Public operations cannot bypass phases. IDs and UTC event time are unique and strictly monotone.
Direct generic fill/funding/decision orchestration is unavailable. Wrong-phase, stale, duplicate,
regressing, terminal, or liquidated events reject without mutation. Scenario costs and effective
fee assets are engine-derived; arbitrary fees, tax, base/third assets, and implicit costs reject
unless the exact authority permits them. Mandates enforce instruments, 25% spot/directional caps,
50% per delta-neutral leg, approximately delta-neutral 1x pairing, no naked legs, and no pyramiding
unless explicitly permitted. Daily loss blocks increases at `<= -1.5%` and drawdown at `<= -10%`;
protective reductions remain available.

The engine derives a complete canonical `DepthOutcomeUniverse` from checksummed point-in-time
depth rows and adapter rules, including every intermediate post-fee spot result `R`, every `q` for
each `R`, VWAP, explicit/implicit cost, fee mutation, ticks, depth and severe recovery. Caller
domains, endpoints, recovery booleans, marks, delays, prices, or costs are prohibited. Candles are
all-or-none at the observed same-instrument open. A valid path worse than the frozen severe bound
rejects before voluntary mutation.

`atomic_pair_entry` and `atomic_pair_close` are mandatory first-class methods owning preflight,
spot-first ordering, commits, recovery, per-fill margin/liquidation checks, rows and disposition.
Close preserves E0-v3: spot sells first, the corresponding perpetual short is bought, and a
remaining mismatch receives one immediate finite non-recursive severe whole-pair attempt. All
commits persist; failure is sticky invalid/unknown.

Flat, true partition-boundary buy-and-hold, and same-timestamp/same-absolute-exposure controls are
independent real engine runs with the same costs, eligibility, holding/rebalance schedule,
next-open execution and terminal convention. Same-exposure uses an independent information and
direction rule. Gap safety executes full forced neutralization and emits full ledgers. Output uses
literal E0-v1 decision/order/fill/funding/account/closed-episode field sets, including nullable
`invalidation_reason`, sequential before/after digest chaining, actual observed liquidation
lineage and emitted fill linkage. Episode funding/cost/PnL/MAE/MFE/direction is local; artifact
counts, costs and digests derive from emitted rows, never placeholders.

## Correction 1 — exact inherited phase order

No phase is reclassified. The canonical order and same-timestamp priority are:

1. validate cadence, boundary and segment, and snapshot incoming ownership/state;
2. apply opening marks and immediately test observed-open liquidation—nothing else;
3. execute only protective or gap exits whose cause existed before this interval, reduction-only;
4. settle funding from the engine-owned t-minus snapshot, then immediately test liquidation;
5. apply risk permissions;
6. execute ordinary exits, rebalances and eligible next-open new orders/fills;
7. immediately checkpoint margin/liquidation after each committed phase-6 fill;
8. test intrabar adverse risk, preserve separate close-to-close PnL, and mark the close;
9. reconcile and emit the account row.

Thus same-time priority is liquidation, protective exit, funding, then ordinary/new/rebalance.
Phase 3 cannot contain ordinary exits and phase 2 cannot contain any exit or entry.

## Correction 2 — atomic-pair entry recovery

Before spot leg 1, entry preflight proves every possible spot result, perpetual result and recovery
leg. Spot buy commits first; the matched perpetual short is attempted second.

- If the perpetual leg fills zero or rejects, severe-sell the actual net spot inventory received,
  including base-fee mutation.
- If the perpetual leg fills partially, first severe-buy to close the exact filled perpetual short,
  then severe-sell the actual net spot inventory.
- Each recovery fill uses the preflighted adapter-owned price/cost/rule path and receives an
  immediate margin/liquidation checkpoint. No naked residual is accepted.

Any failed pair-entry intention is sticky `invalid_unknown` even after complete neutralization.
Committed fills never roll back.

## Correction 3 — sole delayed segment-cross exception

Ordinary input and ordinary execution never cross a segment. The only exception is exactly one
already-pending protective severe perpetual buy-to-close created by pair-close failure:

1. before crossing, mark the interval `invalid_unknown` and preserve the pending order and prior
   segment lineage;
2. consume the first valid qualified price in the new segment, strictly before the frozen terminal
   timestamp and inside the same partition;
3. execute that severe perpetual buy-to-close once, emit complete order/fill/account and mismatch
   lineage, and perform the mandatory margin/liquidation checkpoint;
4. only after the fill, reset segment and rolling state.

No spot leg, ordinary order, pair entry, second delayed attempt, terminal/partition crossing, or
beyond-boundary search may use this exception. If no eligible in-bound price exists, remain
invalid/unknown with safety pending and do not inspect outside the boundary.

## Mandatory executable gates

Every inherited V8/V9 A–K gate and probe remains mandatory against E0 authority fields, plus three
distinct tests:

1. `exact_E0_phase_priority_and_no_reclassification`: proves phase 2 only marks/liquidates, phase 3
   executes a previously caused reduction, phase 4 funding follows it and rechecks liquidation,
   and phase 6 owns ordinary/new/rebalance fills.
2. `atomic_pair_entry_zero_and_partial_second_leg_recovery_order`: zero/reject sells actual net spot
   directly; partial first closes the actual perpetual fill then sells net spot; every path was
   preflighted before leg 1 and ends sticky `invalid_unknown`.
3. `sole_pending_perpetual_close_segment_exception`: ordinary crossings reject; exactly one
   pre-invalidated pending severe perpetual buy-to-close may use the first valid new-segment price
   strictly in-bound, emits full lineage, and resets only after fill; all other crossings reject.

Preflight verifies complete V4–V9 negative archive file sets and hashes/sizes/roles, strict
canonical JSON, all authority bindings, absent V10 paths, blind-oracle separation, and `no_trade`.
Failure archives exact V10 authorities and requires a new ID; V10 is never patched in place.
