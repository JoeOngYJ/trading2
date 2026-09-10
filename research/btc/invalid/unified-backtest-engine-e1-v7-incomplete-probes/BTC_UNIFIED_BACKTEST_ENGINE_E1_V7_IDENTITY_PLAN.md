# BTC unified backtest engine E1-v7 identity plan

Stage: `E1-v7 preimplementation`
Experiment ID: `btc-unified-backtest-engine-e1-v7`
Actionable arm: `no_trade`

## Boundary and inheritance

E1-v7 freezes a new identity before code. It inherits E0-v1 through E0-v4 byte-for-byte and
changes none of their economics, accounting, ordering, funding, liquidation, cost, pair, lineage or
safety rules. The complete E1-v4, E1-v5 and E1-v6 archives are immutable negative evidence and are
not implementation inputs.

E1-v7 preserves the blind-oracle boundary: no implementer-readable artifact may contain a prior or
expected numerical terminal output. The implementer may see named fixture categories and declared
input fields only. An independent reviewer derives exact expectations only after the candidate
snapshot is immutable, and the reviewer oracle shares no kernel code, dataclass, helper or metric.

Work is offline, synthetic and zero-capital. Historical rows, strategy results, sealed 2026 data,
partial OB0 data, credentials, network/exchange/database/NATS/Freqtrade access and production or
paper/live integration are prohibited. Every actionable decision remains `no_trade`.

## New clean identity

Only after independent preflight PASS may a new implementer create:

- `src/trading_platform/btc_accounting_state_machine_e1_v7.py`;
- `research/btc/tests/test_btc_accounting_state_machine_e1_v7.py`;
- snapshot `research/btc/candidates/unified-backtest-engine-e1-v7/`.

The implementer may read only accepted E0-v1–v4 and E1-v7 plans/contracts and exact machine
authorities. Opening, searching, reading, importing, executing, copying, diffing, summarizing or
repairing any invalid/prior E1 artifact, prior result, prior terminal outcome or reviewer oracle is
forbidden. A reviewer may inspect negative evidence only after snapshot freeze.

## Mandatory semantics

1. The candidate manifest uses the literal key `UTC_creation_timestamp`. Every artifact entry has
   exact `path`, `sha256`, `size_bytes` and `semantic_role`; active/snapshot file sets and bytes are
   identical.
2. The canonical nine phases own timestamp and segment progression. Phase 2 permits protective
   reductions only. All preflight—including funding identity insertion and third-fee valuation—is
   side-effect-free. No helper may rewrite timestamp/segment outside its canonical phase. Adverse
   marks are used for liquidation checks only; close-to-close PnL attribution remains separate.
   Observed-open liquidation is terminal and forbids every later funding event and row.
3. Atomic pair entry validates every forced recovery leg, price, fee, rule, cap and funding path
   before spot leg 1 commits. Any failed pair intention is `invalid_unknown` even when immediate
   neutralization returns flat.
4. Flat, true partition-boundary buy-and-hold and same-exposure controls are real ledger runs with
   the frozen partition/terminal convention—not timestamp predicates. Gap neutralization uses the
   first valid open inside the frozen boundary, captures the complete observed path, invalidates the
   interval and resets segment/rolling state.
5. A qualified partial adapter supplies an explicit, checksummed, point-in-time depth/outcome
   universe. The engine derives and proves every intermediate spot reduction `R` and every
   permitted perpetual `q` for each `R`; caller endpoints are insufficient. Every spot/perpetual
   outcome binds VWAP, explicit/implicit cost, fee mutation, rules and ticks.
6. Candle severe price/source is the engine-owned observed same-instrument open and the actual path
   cannot exceed the frozen worst bound. State memo, common marks, delay and segment transition are
   engine-owned and source-derived, never caller substitutes. Delayed safety is `invalid_unknown`
   before any permitted segment crossing and cannot inspect or cross the frozen terminal/partition
   boundary.
7. A pair mismatch gets exactly one finite, non-recursive severe whole-pair close. Fill failures are
   caught, committed fills remain recorded and the intention becomes invalid; no naked state is
   accepted as valid.
8. Run binding is immutable. Operations and order rows enforce the selected mandate/instrument,
   caps, leverage and exact effective cost/fee authority. Arbitrary taxes or base fees are rejected
   unless an exact effective authority explicitly permits them. Pyramiding is rejected unless the
   selected mandate explicitly permits it.
9. Terminal/liquidated state rejects future timestamps, ordinary decisions/orders and fills.
   Protective authorization is reduction-only and cannot permit phase-2 ordinary increases.
   Implementation digest is derived only from exact manifest-bound active/snapshot bytes, accepts
   no caller path/value, and fill rule/source/margin digests verify immutable run bindings.
10. Exact daily-loss and drawdown thresholds, boundary inequalities, resets and protective/reduction
    allowance remain required. Exact price-tick validation, Decimal canonicalization, duplicate and
    post-stringification-key collision rejection remain required.
11. Outputs use every exact E0 ledger field name. Account rows carry the real segment and exact
    maintenance requirement. Every ordinary row has `invalidation_reason_or_null`. Liquidation
    order then fill are sequentially reconcilable transitions with full observed lineage; its
    episode references the actual emitted fill-row digest. Funding attribution is per episode, not
    lifetime cumulative. Spot and pair direction plus MAE/MFE are correct. Invalid intervals remain
    sticky in rows/results. Pair outcomes validate prices against bound ticks/rules.

## Mandatory adversarial probes

Before qualification, independent probes must reject: phase-2 ordinary increase; any state/key/order
mutation after a failing preflight; post-liquidation funding; incomplete pair-entry recovery;
caller-endpoint L2 Cartesian sets; caller-substituted candle price/marks/memo/delay/segment;
out-of-bound delayed neutralization; wrong-instrument order rows; arbitrary unauthorized tax/base
fees; prohibited pyramiding; post-terminal order or timestamp; caller-path implementation digest;
and mismatched fill rule/source/margin digests. They must reconcile sequential liquidation rows,
episode fill links, per-episode funding, spot/pair PnL and MAE/MFE, invalid-interval persistence,
real controls and pair-outcome tick rejection.

## Snapshot and gate

Before independent E1 review, copy final active module/test bytes into the snapshot and create a
canonical compact `candidate-manifest.json` with the required entry schema. The review record binds
the manifest hash. Mutation or any failed gate archives the exact attempt and requires a new ID;
v7 is never repaired in place.

An independent reviewer must verify inherited/negative hashes and complete file sets, canonical
serialization, absent v7 paths, all mandatory semantics/probes, blind-oracle separation and
synthetic/`no_trade` boundaries. Until PASS, no v7 code, test, snapshot or oracle may begin.
