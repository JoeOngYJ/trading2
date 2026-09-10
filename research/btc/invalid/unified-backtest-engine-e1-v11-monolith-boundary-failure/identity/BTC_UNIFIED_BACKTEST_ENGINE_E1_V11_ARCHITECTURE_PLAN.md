# BTC unified backtest engine E1-v11 architecture and identity plan

Stage: `E1-v11 preimplementation`
Experiment ID: `btc-unified-backtest-engine-e1-v11`
Actionable arm: `no_trade`

## Scope and inheritance

E1-v11 is a clean-room implementation identity. It inherits the combined E0-v1 through E0-v4
economics and preserves V10's corrected phase, pair-entry recovery and delayed protective-close
semantics. E1-v4 through E1-v10 are immutable negative evidence, never implementation inputs.

This is offline, synthetic, zero-capital infrastructure only. Historical rows/results, sealed 2026
and partial OB0 data, credentials, networks, exchanges, databases, NATS, Freqtrade, protected
services, strategies, metrics, routing, paper and live execution are prohibited. Only `no_trade` is
actionable. Implementer-readable records contain no numerical terminal oracle outputs; independent
oracle expectations are derived only after an immutable snapshot.

After independent preflight PASS only, the exact paths are:

- `src/trading_platform/btc_accounting_state_machine_e1_v11.py`;
- `research/btc/tests/test_btc_accounting_state_machine_e1_v11.py`;
- `research/btc/candidates/unified-backtest-engine-e1-v11/`.

The implementer may read accepted E0-v1–v4, this V11 plan/contract, and exact authorities only. It
must not inspect, search, read, import, execute, copy, diff, summarize, or repair prior/invalid E1
artifacts, results, snapshots, qualifications, or reviewer oracles. Every required executable probe
is therefore stated by value below and in the machine contract; no prohibited archive is needed to
understand or implement the qualification suite.

## Frozen architecture

The sole construction path is an `AuthorityVerifiedFactory` that verifies role-labelled exact
manifest-bound active/snapshot implementation, V11 contract, execution, selected mandate,
instrument-rule, margin-rule, source-evidence, and semantic-settings bytes. It derives hashes
internally; callers cannot supply or override digests, paths, costs, fees, margins, sources,
bindings, phases, or identity. It returns an immutable `AccountingStateMachine`.

The machine owns the UTC clock, unique monotone identifiers, event phases, funding ownership and
all state mutation. There is no public generic fill, funding, decision, phase mutation, or caller
orchestration path. A phase-zero, wrong-phase, stale, duplicate, regressing, terminal, liquidated,
wrong-segment, or invalid-reversal event rejects without mutation. Failed validation, preflight,
authorization and bounds checks are side-effect-free. Terminal and liquidation are monotone.

Scenario costs and effective fee assets are derived from bound authorities. Zero or arbitrary
fees, taxes, base/third fee assets and implicit costs reject unless the selected authority permits
them and the required asset balance is funded. Mandates enforce exact instruments, 25% spot or
directional caps, 50% per delta-neutral leg, approximately delta-neutral 1x pairing, no naked leg,
and no pyramiding unless the selected mandate explicitly permits it. Daily loss blocks increases
at `<= -1.5%` and drawdown blocks them at `<= -10%`; reductions and protective cleanup remain
available and the frozen reset rules apply exactly.

All arithmetic is finite `Decimal`. Price ticks, quantity steps, minimum notional, upper bounds,
canonical decimal text, duplicate keys/rows, nonfinite values and canonical set ordering are
validated. The engine derives the complete permutation-invariant `DepthOutcomeUniverse` from
qualified checksummed point-in-time depth and adapter rules. It enumerates every intermediate
post-fee spot result `R` and every perpetual `q` for each `R`, with depth-derived VWAP, fee mutation,
explicit/implicit cost, tick/step/minimum checks and severe recovery. Callers cannot provide
domains, endpoints, prices, VWAP, costs, recovery booleans, delays or marks. Candle execution is
all-or-none at the observed same-instrument open. Any valid realized path worse than the frozen
severe bound rejects before voluntary mutation.

`atomic_pair_entry` and `atomic_pair_close` are mandatory first-class machine methods that own full
preflight, spot-first commits, recovery, per-fill margin/liquidation checks, rows and disposition.
Pair entry buys spot then shorts the matched perpetual. A zero/rejected perpetual second leg
severe-sells actual net spot directly; a partial second leg first severe-buys the exact filled
perpetual short and then severe-sells actual net spot. Pair close sells spot first, buys the
corresponding perpetual short, and gives any mismatch one immediate finite non-recursive severe
whole-pair attempt. Failed intentions are sticky `invalid_unknown`; committed fills never roll
back, and no naked residual is accepted.

Flat, true partition-boundary buy-and-hold, and same-timestamp/same-absolute-exposure controls are
independent real machine runs under identical scenario costs, eligibility, holding/rebalance
schedule, next-open execution and terminal convention. The same-exposure replacement has an
independent information and direction rule. Gap safety consumes the first valid common in-bound
observations, executes complete forced neutralization, emits full rows, becomes sticky invalid,
then resets segment and rolling state only after cleanup. Outputs use the literal E0-v1 decision,
order, fill, funding, account and closed-episode fields. Every event chains the immediately prior
after-state digest. Liquidation binds the actual observed mark, instrument/rule/margin sources,
order and emitted fill. Episode funding, price PnL, costs, MAE, MFE and direction are local;
artifact counts, costs, summaries and digests derive from emitted rows, never constants.

## Exact event phases and priority

No phase is reclassified:

1. validate cadence, boundary and segment, and snapshot incoming ownership/state;
2. apply opening marks and immediately test observed-open liquidation—nothing else;
3. execute only protective or gap exits whose cause existed before this interval, reduction-only;
4. settle funding from the engine-owned t-minus snapshot, then immediately test liquidation;
5. apply risk permissions;
6. execute ordinary exits, rebalances and eligible next-open new orders/fills;
7. immediately checkpoint margin/liquidation after each committed phase-6 fill;
8. test intrabar adverse risk, preserve separate close-to-close PnL, and mark the close;
9. reconcile and emit the account row.

Same-time priority is liquidation, protective exit, funding, then ordinary/new/rebalance. Phase 3
cannot contain ordinary exits and phase 2 cannot contain any exit or entry.

## Sole delayed segment-cross exception

Ordinary input and execution never cross a segment. The sole exception is one already-pending
protective severe perpetual buy-to-close created by pair-close failure. Before crossing, the
machine marks `invalid_unknown` and preserves the pending order and prior-segment lineage. It may
consume only the first qualified price in the new segment, strictly before terminal and inside the
same partition; execute once; emit complete order/fill/account/mismatch lineage; checkpoint margin
and liquidation; and reset segment/rolling state only after fill. No spot leg, ordinary order,
pair entry, second delayed attempt, terminal/partition crossing, or beyond-boundary search can use
the exception. Without an eligible price, safety stays pending and the engine inspects nothing
outside the boundary.

## Executable qualification probes, stated by value

The V11 contract freezes each probe separately. The suite must prove:

- factory-only construction, exact manifest role/path/hash/size verification, literal
  `UTC_creation_timestamp`, active/snapshot byte identity, immutable bindings and phase, internal
  digest derivation, and rejection of caller digest/path/value overrides;
- direct `atomic_pair_entry` and `atomic_pair_close` success paths and recovery paths, with full
  preflight before leg 1, committed fills, immediate checkpoints, rows and sticky dispositions;
- phase-zero fill/funding/decision, every wrong-phase operation, direct phase mutation, duplicate
  or regressing ID/time, stale reversal and post-terminal/liquidation activity reject without
  mutation; post-liquidation funding and adverse risk never run;
- exact phase-2 mark/liquidation only, actual pre-caused phase-3 protection, phase-4 t-minus
  funding plus liquidation, phase-6 ordinary/new/rebalance, and separate intrabar versus close PnL;
- pair-entry zero/reject and partial-second-leg recovery in their distinct required order;
- pair-close full Cartesian `R × q` preflight from engine-derived depth, including intermediate
  fee-mutated results, VWAP, ticks, quantities, minimums, explicit/implicit/severe economics,
  duplicate/permutation rules, realized-versus-bound comparison, mismatch immediate attempt,
  per-fill liquidation, delayed persistence and the sole segment exception;
- unauthorized zero/arbitrary cost, fee, tax, base/third fee asset, wrong instrument, 100% exposure,
  cap excess, naked pair, non-1x pair and unpermitted pyramid all fail before mutation;
- unbound or changed implementation, contract, execution, mandate, instrument, margin, source, or
  settings bytes reject; liquidation and every row retain transitive real-source lineage;
- gap cleanup executes full forced neutralization with rows, sticky invalid state and post-fill
  reset, while missing/out-of-bound cleanup remains pending without boundary inspection;
- flat, buy-and-hold and same-exposure controls contain real decisions/orders/fills/accounts/costs,
  correct exposure, schedule, next-open and terminal treatment, and independent control logic;
- exact E0 field sets and nullable ordinary invalidation, sequential digest chains, emitted
  liquidation fill linkage, matched-pair episode direction, local episode attribution, and real
  artifact counts/costs/digests;
- exact `Decimal` thresholds, rounding/ticks/steps/minimums, finite/canonical serialization,
  duplicate/nonfinite/key-collision rejection and deterministic permutation-invariant digests.

No test may assert only a candidate-local constant or call a self-referential helper as its oracle.
Independent numerical expectations are derived by the reviewer only after the immutable candidate
snapshot exists.

Preflight verifies complete V4–V10 negative archive closure, strict canonical JSON, exact authority
bindings, absent V11 paths, blind-oracle separation and `no_trade`. Failure archives exact V11
authorities and requires a new ID; V11 is never patched in place.
