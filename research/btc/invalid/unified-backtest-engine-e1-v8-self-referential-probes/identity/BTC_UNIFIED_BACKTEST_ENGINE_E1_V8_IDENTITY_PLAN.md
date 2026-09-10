# BTC unified backtest engine E1-v8 identity plan

Stage: `E1-v8 preimplementation`
Experiment ID: `btc-unified-backtest-engine-e1-v8`
Actionable arm: `no_trade`

## Scope

E1-v8 freezes a new implementation identity before code. It preserves every E1-v7 requirement and
inherits E0-v1 through E0-v4 byte-for-byte without changing economics, accounting, event order,
funding, liquidation, costs, pair semantics, lineage or safety. E1-v4 through E1-v7 are immutable
negative evidence, not implementation inputs.

The blind-oracle boundary remains mandatory. Implementer-readable material contains named fixture
categories and declared inputs but no prior or expected numerical terminal outputs. An independent
reviewer derives exact expectations only after immutable snapshot and shares no kernel code,
dataclasses, helpers or metrics.

This is offline, synthetic, zero-capital infrastructure. Historical rows, strategy results, sealed
2026 or partial OB0 data, credentials, network/exchange/database/NATS/Freqtrade access and
production, paper or live integration are prohibited. Only `no_trade` is actionable.

## Frozen identity and clean-room rule

After independent preflight PASS only:

- module: `src/trading_platform/btc_accounting_state_machine_e1_v8.py`;
- test: `research/btc/tests/test_btc_accounting_state_machine_e1_v8.py`;
- snapshot: `research/btc/candidates/unified-backtest-engine-e1-v8/`.

The implementer may read accepted E0-v1–v4 and E1-v8 plans/contracts and exact authorities only.
The implementer must not open, search, read, import, execute, copy, diff, summarize or repair any
invalid/prior E1 artifact, prior result/outcome/snapshot or reviewer oracle. Reviewers may inspect
negative evidence only after snapshot freeze.

## Preserved mandatory semantics A–K

A. Manifest literal `UTC_creation_timestamp`; each artifact entry has exact `path`, `sha256`,
   `size_bytes`, `semantic_role`; canonical compact JSON; active/snapshot bytes and sets identical.
B. Canonical nine phases own timestamp/segment progression; phase 2 allows protective reductions
   only; all preflight is side-effect-free; no out-of-phase timestamp/segment rewrite; adverse mark
   is risk-only while close-to-close PnL remains separate; no funding event/row after observed-open
   liquidation.
C. Every atomic-pair recovery leg/path is validated before spot leg 1. Any failed pair intention is
   sticky `invalid_unknown` after neutralization even when flat.
D. Flat, true partition-boundary buy-and-hold and same-exposure controls are real ledger runs under
   predeclared partition/terminal convention. Gap safety uses the first valid in-bound open,
   captures the full observed path, invalidates the interval and resets segment/rolling state.
E. Qualified partial depth/outcome source is checksummed and point-in-time. The engine proves every
   intermediate `R` and every permitted `q` for each `R`; every spot/perpetual outcome binds VWAP,
   explicit/implicit cost, fee mutation, rules and ticks. Caller endpoints are insufficient.
F. Candle severe price/source is the engine-owned observed same-instrument open and actual path is
   no worse than the frozen worst bound. Marks, memo, delay and segment are source-derived, not
   caller inputs. Delayed safety is invalid before crossing, remains inside exact terminal/partition
   boundary and cannot search beyond it. Pair mismatch gets one finite non-recursive whole-pair
   attempt; failures retain commits and invalidate.
G. Run binding is immutable. Operations and order rows enforce mandate, instrument, caps, leverage
   and effective cost/fee authority. Unauthorized taxes/base fees and prohibited pyramiding reject.
   Terminal/liquidated state rejects future timestamps and ordinary decisions/orders/fills;
   protective authorization is reduction-only.
H. Implementation digest comes only from manifest-bound active/snapshot bytes, never caller path or
   value. Fill rules, sources and margin digests verify immutable binding; every row has exact
   transitive lineage.
I. Daily loss blocks at `<= -1.5%`, drawdown at `<= -10%`; reset timing is exact and reductions or
   protective exits remain allowed.
J. Exact tick/quantity rules, Decimal canonicalization, duplicate/nonfinite and post-string key
   collision rejection; pair-outcome prices validate bound ticks/rules.
K. Exact E0 ledger field sets; account actual segment and numeric exact maintenance requirement;
   explicit `invalidation_reason_or_null` on ordinary decision/order/fill/funding/account rows;
   sequential liquidation order/fill transitions with observed mark/source/rule/margin lineage and
   actual emitted fill digest linked by the closed episode; per-episode funding; correct spot/pair
   direction, PnL and MAE/MFE; sticky invalid intervals and complete order/cost attribution.

## Three additional distinct executable probes

These probes are mandatory and independent; prose conformance is insufficient:

1. A valid source-derived observed severe path whose actual execution price is worse than the
   frozen worst permitted bound must reject before voluntary first-leg mutation.
2. Assert exact per-ledger E0 schema equality, account rows use the actual segment and numeric exact
   maintenance requirement, and every ordinary decision/order/fill/funding/account row has explicit
   `invalidation_reason_or_null`.
3. Reject or detect placeholder or mismatched observed mark source, rule digest and margin-rule
   lineage in liquidation order/fill/episode rows, with exact transitive bindings.

All earlier v7 adversarial probes remain required in the machine contract.

## Snapshot and gate

Before E1 review, copy final active bytes into the snapshot and create canonical
`candidate-manifest.json`; its entries use the exact schema and the review record binds its hash.
Mutation or failure archives the exact candidate and requires a new ID—never patch v8 in place.

Independent preflight verifies all inherited/negative hashes and file sets, A–K, every probe,
blind-oracle separation, absent v8 paths and `no_trade`. No code/test/snapshot/oracle begins before
PASS.
