# BTC unified backtest engine E1-v5 identity plan

Stage: `E1-v5 preimplementation`
Experiment ID: `btc-unified-backtest-engine-e1-v5`
Actionable arm: `no_trade`

## Purpose and inheritance

This document freezes a new implementation identity before code exists. E1-v5 inherits the exact
E0-v1, E0-v2, E0-v3 and E0-v4 plans and contracts. It makes no new economic choice and cannot
relax their accounting, event order, funding, liquidation, cost, pair, lineage, offline or safety
rules. The E1-v4 candidate is structurally rejected and fully bound as immutable negative evidence;
it must not be imported, executed, copied, repaired or used downstream.

E1-v5 remains synthetic, offline and zero-capital. It may not read historical market rows,
strategy results, sealed 2026 data or partial OB0 data, and may not access credentials, networks,
exchanges, databases, NATS, Freqtrade or production services. Every actionable decision is
`no_trade`.

## New identity and clean-room boundary

Only after independent preflight acceptance of the machine contract may a new implementer create:

- `src/trading_platform/btc_accounting_state_machine_e1_v5.py`;
- `research/btc/tests/test_btc_accounting_state_machine_e1_v5.py`.

The implementer may read only the accepted E0-v1 through E0-v4 plans/contracts, this accepted
E1-v5 identity plan/contract and the exact execution/mandate authorities. The implementer must not
open, search, read, import, execute, copy, diff, summarize or repair any invalid archive or prior
E1 source, tests, result, qualification report, terminal outcome or candidate snapshot. A reviewer
may inspect negative evidence after the candidate snapshot is frozen.

## Mandatory A–K prequalification gates

A. Every candidate-manifest artifact entry has `path`, exact-file `sha256`, `size_bytes` and
   `semantic_role`. The manifest uses inherited canonical compact JSON and binds active and
   snapshot files, all E0 contracts, exact authorities, experiment ID and UTC creation time.
B. The kernel enforces canonical nine-phase progression and inherited same-timestamp priority.
   T-minus funding membership is an engine-owned snapshot, never caller-supplied. Funding,
   post-fill, adverse-open and close margin/liquidation checkpoints are immediate and mandatory;
   phases also enforce every rollback boundary and every committed fill that cannot roll back.
C. Independent exact synthetic fixtures establish: spot long and perpetual long `1019.37`,
   perpetual short `1019.43`, long-to-short reversal `989.58`, funding liquidation `982.17` and
   invalid, exposed gap `979.68` and invalid, atomic-pair failure `999.45` and invalid. They also
   cover closed episodes, true partition-boundary buy-and-hold and causal terminal flattening,
   completed gap neutralization and duplicate/permuted-event rejection.
D. Atomic pair entry is implemented directly; preloaded pair state is not a substitute. It obeys
   inherited spot-first entry and committed-first-leg failure/severe-neutralization semantics.
E. Full E0-v3 pair close is implemented. The engine—not a caller boolean—proves Cartesian
   completeness; requires zero/full endpoints; rejects duplicates; and derives a canonical,
   permutation-invariant outcome-set digest. Each outcome carries its own VWAP/cost. Preflight binds
   the worst severe price and implicit cost; a candle severe fill uses the exact same-instrument
   open. Margin/liquidation is checked after every committed leg. A mismatch triggers one immediate,
   finite, non-recursive severe whole-pair attempt rather than only being queued. Delayed residuals
   emit complete orders, outputs, mismatch, common-mark and segment-reset semantics. Semantic
   settings and outcome-set digests persist on rows.
F. Operations enforce the selected machine-readable mandate and reject wrong instruments. Spot or
   directional exposure is capped at 25%; each delta-pair leg at 50%; a delta-neutral pair uses 1x
   leverage. Naked exposure cannot be intended or valid. Scenario ID binds the immutable 30/40/80
   cost schedule, and arbitrary caller fees are rejected.
G. Liquidation/terminal state is persistent and monotone. Later ordinary events and orders cannot
   resume trading. Protective or forced authorization is reduction-only and can never increase
   exposure.
H. `implementation_digest` is derived from exact active/snapshot bytes and is never caller input.
   Every row repeats or references exact transitive lineage for E0-v1 through E0-v4, E1-v5,
   execution config, selected mandate, rules, sources and semantic settings. Pair settings and
   outcome-set identity survive serialization.
I. Daily loss blocks at `<= -1.5%`; drawdown blocks at `<= -10%`. Reset timing is exact. Risk gates
   block increases but continue to allow reductions and protective exits.
J. Instrument rules validate exact price ticks. Canonical mapping rejects distinct keys that collide
   after canonical string conversion, while strict JSON preserves Decimal values and rejects
   nonfinite values.
K. Liquidation order and fill rows include every required order/fill and inherited lineage field.
   Liquidation emits the relevant closed episode with entry, exit, funding, cost, MAE and MFE
   attribution. Rejected, expired, partial and unfilled events and invalidation lineage are complete;
   every artifact, report and manifest is deterministic and remains `no_trade`.

These are prequalification requirements, not claims of implementation or PASS. Any missing or
optional item rejects the complete candidate under this experiment ID.

## Snapshot before review

Before any independent E1 review, copy the final active module and test byte-for-byte into
`research/btc/candidates/unified-backtest-engine-e1-v5/` and create canonical
`candidate-manifest.json`. Every listed artifact entry must include path, SHA-256, byte size and
semantic role. The manifest itself is frozen by its hash in the independent review record. Active
and snapshot bytes must match. No candidate edit is allowed after snapshot; a change or failed gate
requires archiving the exact attempt and issuing a new experiment ID.

## Preimplementation gate

An independent reviewer must verify exact inherited and negative-evidence hashes/file sets,
canonical serialization, unique absent E1-v5 paths, all A–K requirements, clean-room separation,
snapshot rules, and the synthetic/`no_trade` boundary. Until that review passes, creating or running
E1-v5 code or tests is prohibited.
