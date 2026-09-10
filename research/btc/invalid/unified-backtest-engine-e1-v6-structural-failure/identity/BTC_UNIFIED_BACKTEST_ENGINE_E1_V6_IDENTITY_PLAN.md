# BTC unified backtest engine E1-v6 identity plan

Stage: `E1-v6 preimplementation`
Experiment ID: `btc-unified-backtest-engine-e1-v6`
Actionable arm: `no_trade`

## Purpose and inheritance

This plan freezes a new identity before code. E1-v6 inherits E0-v1 through E0-v4 exactly and
makes no economic, accounting, ordering, funding, liquidation, cost, pair, lineage or safety
change. E1-v4 is rejected for structural underimplementation. E1-v5 is rejected before code
because its implementer-readable authorities disclosed independent oracle answers. Both complete
archives are bound as immutable negative evidence and are forbidden implementation inputs.

E1-v6 is offline, synthetic and zero-capital. It may not read historical market rows, strategy
results, sealed 2026 data or partial OB0 data, and may not access credentials, networks, exchanges,
databases, NATS, Freqtrade or production services. Every actionable decision is `no_trade`.

## New clean identity

Only after independent preflight acceptance may a new implementer create:

- `src/trading_platform/btc_accounting_state_machine_e1_v6.py`;
- `research/btc/tests/test_btc_accounting_state_machine_e1_v6.py`.

The candidate snapshot directory is
`research/btc/candidates/unified-backtest-engine-e1-v6/`.

The implementer may read only accepted E0-v1 through E0-v4 plans/contracts, this accepted E1-v6
plan/contract and exact execution/mandate authorities. The implementer must not open, search, read,
import, execute, copy, diff, summarize or repair any invalid archive, prior E1 source/test/result,
prior qualification artifact, prior terminal outcome, prior candidate snapshot or reviewer-only
oracle material. A reviewer may inspect negative evidence only after the v6 candidate snapshot is
immutable.

## Mandatory A–K prequalification gates

A. Every manifest artifact entry contains `path`, exact-file `sha256`, `size_bytes` and
   `semantic_role`. The manifest is canonical compact JSON and binds active/snapshot files, E0-v1
   through E0-v4 and E1-v6 contracts, exact authorities, experiment ID and UTC creation time.
   Active and snapshot file-set identity is checked.
B. The kernel enforces canonical nine-phase progression and inherited same-timestamp priority.
   T-minus funding membership is engine-owned, never caller-supplied. Funding, post-fill,
   adverse-open and close margin/liquidation checkpoints are immediate and mandatory. Rollback and
   irrevocably committed-fill boundaries are phase-enforced.
C. Independent synthetic fixtures cover spot long, linear-perpetual long, linear-perpetual short,
   long-to-short reversal, funding-caused liquidation, exposed-gap invalidation and atomic-pair
   second-leg failure. Fixture inputs explicitly declare starting balances, signed quantities,
   prices, fee assets/rates, implicit cash costs, collateral, funding economic/availability times,
   marks/indexes, event timestamps, rules and source lineage. Additional categories cover closed
   episodes, true partition-boundary buy-and-hold, causal terminal flattening, completed gap
   neutralization and duplicate/permuted-event rejection. No expected terminal NAV or other
   numerical oracle answer appears in an implementer-readable artifact. The independent reviewer
   derives and applies exact expectations only after the immutable snapshot.
D. Atomic pair entry is implemented directly; preloaded state is not a substitute. It obeys
   inherited spot-first entry and committed-first-leg failure/severe-neutralization semantics.
E. Full E0-v3 pair close is implemented. The engine proves Cartesian completeness without trusting
   a caller boolean, requires zero/full endpoints, rejects duplicates and derives a canonical
   permutation-invariant outcome-set digest. Outcomes carry their own VWAP/cost. Preflight binds
   worst severe price and implicit cost; a candle severe fill uses the exact same-instrument open.
   Margin/liquidation follows every committed leg. A mismatch receives one immediate finite,
   non-recursive severe whole-pair attempt. Delayed residual rows fully preserve orders, outputs,
   mismatch, common marks, segment resets, semantic settings and outcome-set identity.
F. Operations enforce the selected machine mandate and reject wrong instruments. Spot/directional
   exposure is capped at 25%, each delta-pair leg at 50%, and delta-neutral leverage at 1x. Naked
   exposure cannot be intended or valid. Scenario ID binds immutable 30/40/80 cost schedules;
   arbitrary caller fees are rejected.
G. Liquidation and terminal state are persistent and monotone. Later ordinary events/orders cannot
   resume trading. Protective or forced authorization is reduction-only.
H. `implementation_digest` is derived from exact active/snapshot bytes and never caller input.
   Every row repeats or references exact transitive contract, implementation, execution config,
   selected mandate, rule, source and semantic-settings lineage. Pair settings and outcome-set
   identity survive serialization.
I. Daily loss blocks at `<= -1.5%`; drawdown blocks at `<= -10%`; reset timing is exact. Reductions
   and protective exits remain allowed.
J. Instrument rules enforce exact price ticks. Canonical mapping rejects distinct keys that collide
   after string conversion. Strict JSON preserves Decimal and rejects nonfinite values.
K. Liquidation order/fill rows include every required field and inherited lineage. Liquidation
   closes the relevant episode with complete entry, exit, funding, cost, MAE and MFE attribution.
   Rejected, expired, partial and unfilled events and invalidation lineage are complete; artifacts,
   reports and manifests are deterministic and `no_trade`.

Any missing or optional gate rejects the complete v6 candidate.

## Blind oracle and immutable snapshot

Before independent E1 review, copy final active module/test bytes into the frozen snapshot directory
and create canonical `candidate-manifest.json`. Every artifact entry includes path, SHA-256, byte
size and semantic role. Active and snapshot bytes/file sets must match. The review record binds the
manifest hash.

Only after that freeze may a structurally independent reviewer derive exact expected outputs from
the declared fixture inputs and inherited contracts. Reviewer-only expectations cannot be
disclosed to or imported by the implementer before snapshot. The oracle cannot share kernel code,
dataclasses, helpers or metrics. Any snapshot mutation or failed gate archives the exact attempt and
requires another experiment ID; v6 is never repaired in place.

## Preimplementation gate

An independent reviewer must verify every inherited and negative-evidence hash/file set, canonical
serialization, absent v6 paths, A–K completeness, absence of leaked numerical oracle outputs,
clean-room separation, snapshot rules and synthetic/`no_trade` boundaries. Until PASS, no v6 code,
tests, snapshot, oracle or downstream work may begin.
