# BTC unified backtest engine E1-v12 modular architecture plan

Stage: `E1-v12 preimplementation`
Experiment ID: `btc-unified-backtest-engine-e1-v12`
Actionable arm: `no_trade`

## Purpose and boundary

E1-v12 is a clean-room, modular implementation identity for the accepted E0-v1 through E0-v4
accounting economics. It is offline synthetic infrastructure with zero capital. It does not read
historical strategy results, sealed 2026 or partial OB0 data; connect to credentials, networks,
exchanges, databases, NATS, Freqtrade or protected services; calculate strategy performance; or
authorize paper/live execution. Only `no_trade` is actionable.

E1-v4 through E1-v11 are immutable negative evidence and are validator/reviewer inputs only. The
implementer may read accepted E0-v1–v4, this V12 plan/contract and exact manifest-bound authorities.
It may not inspect, search, read, import, execute, copy, diff, summarize or repair a prior E1 file,
result, qualification, snapshot or oracle. V12 therefore states all behavior and executable probes
by value. No numerical terminal oracle output is implementer-readable; the independent reviewer
derives it only after the active and snapshot trees are frozen byte-for-byte.

## Frozen package and import graph

After independent preflight PASS, and not before, implementation may create exactly:

```text
src/trading_platform/btc_accounting_e1_v12/
  __init__.py
  canonical.py
  authorities.py
  ledger.py
  pair.py
  controls.py

research/btc/tests/btc_accounting_e1_v12/
  test_canonical_authorities.py
  test_ledger.py
  test_pair.py
  test_controls_outputs.py
  test_integration.py
```

The snapshot root is `research/btc/candidates/unified-backtest-engine-e1-v12/`. It mirrors those
eleven source/test relative paths exactly and also contains `candidate-manifest.json`, qualified
`source-evidence.json`, `instrument-rules.json`, `margin-rules.json`, and three separately hashed
immutable run specifications: `run-spec-spot.json`, `run-spec-directional.json`, and
`run-spec-pair.json`.

Imports are acyclic and exact:

```text
canonical:   standard library only
authorities: canonical
ledger:      canonical + authorities
pair:        ledger + authorities
controls:    ledger + pair
__init__:    facade over authorities + ledger + pair + controls
```

No module imports a prior E1, network, database, broker, exchange, messaging or production client.
Tests import the public package facade; only isolated pure canonical/authority unit tests may import
their owning module. Cross-module behavior is proven through `test_integration.py`.

## Ownership and interfaces

`canonical.py` exclusively owns finite `Decimal` parsing, canonical decimal text, strict duplicate-
free/nonfinite-free JSON, canonical UTF-8 sorted compact LF serialization, SHA-256 domains, exact
UTC parsing and price/quantity quantization. Mapping keys must already be canonical strings;
normalization collisions reject before serialization.

`authorities.py` exclusively owns candidate-manifest verification, exact role/path/hash/size and
active/snapshot file-set checks, authority loading, structural mandate/scenario/rule validation,
point-in-time source ordering, and immutable `RunSpec` creation. A caller supplies only one of the
three fixed run-spec IDs; it cannot provide a path, digest, value, fee, scenario, mandate, source,
rule, margin or setting override. All exact authority bytes are loaded and verified once. No later
operation reopens a mutable file. Spot, directional perpetual and matched-pair identities are each
selectable through their separately checksummed fixed manifest role.

`ledger.py` exclusively owns cash, inventory, isolated collateral, liabilities, fee assets, NAV,
realized/unrealized PnL, margin, funding, liquidation, the nine event phases, the engine clock,
unique monotone IDs, rows, episodes, daily/high-water risk state and terminal state. Its constructor
requires a module-private capability issued only by the verified authority factory. The capability
is held in a closure or module-private weak-key registry; it is neither exported nor stored as a
readable class attribute. There is no generic public fill, funding, decision, clock, phase, state,
row or binding mutator. Public state, rows, episodes, bindings and artifacts are recursive immutable
views. Every validation and preflight failure is side-effect-free unless E0 explicitly requires a
sticky protective-safety transition.

`pair.py` exclusively owns `atomic_pair_entry`, `atomic_pair_close`, complete adapter-derived depth
outcomes, `R × q` Cartesian preflight, mismatch recovery and the one delayed protective close.
`controls.py` exclusively owns full independent flat, true partition-boundary buy-and-hold and
same-timestamp/same-absolute-exposure runs, gap cleanup, and artifact assembly. Controls invoke real
facade execution and emit real ledgers; a tag is not a control.

`__init__.py` exports only immutable value objects, declared errors, the verified factory and the
facade methods needed to advance the next authority-owned interval, submit an authorized target,
atomically enter/close a pair, close an interval, terminate, run a named control, and read immutable
outputs. The engine, not the caller, chooses the next source row, timestamp, segment, funding event,
gap cleanup observation, execution price, partial outcome, fee or terminal boundary.

## Exact event and accounting semantics

The inherited event order is unchanged:

1. validate cadence/boundary/segment and snapshot incoming ownership;
2. apply opening marks and immediately liquidate if required—nothing else;
3. execute only a reduction caused before the interval, including gap protection;
4. settle funding from the engine-owned t-minus position and immediately retest liquidation;
5. apply daily-loss, drawdown, margin and mandate permissions;
6. execute ordinary exits/rebalances and eligible next-open entries;
7. immediately checkpoint margin/liquidation after each committed phase-6 fill;
8. test intrabar adverse risk, keep it separate from close-to-close PnL, and mark the close;
9. reconcile and emit the account row.

Same-time priority is observed-open liquidation, pre-caused protection, funding, then ordinary/new
orders. Phase 2 never trades and phase 3 never performs an ordinary exit. Funding economic and
availability timestamps must be canonical, causal and authority-owned. A missing, duplicate,
reversed, future, stale, wrong-segment or out-of-bound source fails before interval mutation.
Terminal/liquidation state is monotone; no later funding, fill, adverse mark or close row executes.

All arithmetic is finite `Decimal`. A fill applies exactly one accounting price and separately
records/debits its authority-derived explicit and implicit costs once. Quote, base and permitted
third-asset fees, including tax, mutate their actual balances and NAV; insufficient fee assets fail
before voluntary mutation. Spot cash/inventory and perpetual collateral transitions, proportional
margin release, funding ownership, liabilities, exit-reserve memo, maintenance and liquidation
follow E0 exactly. Costs are loaded once from bound bytes and severe fills carry the severe scenario
identity. `event_accounting_residual` is calculated from the transition, not hardcoded.

Each event uses the immediately preceding after-state digest as its before-state digest. Rejected,
expired, rounded, zero, partial, unfilled and recovery intentions report true requested, rounded,
filled and unfilled quantities/status. Liquidation binds the actual observed adverse mark and exact
instrument, rule, margin, source, order and emitted fill digests, emits the required account row,
closes any episode, and cannot accept a caller digest. Episodes are local: entry/exit cost, spot and
perpetual price PnL, funding, net PnL, MAE, MFE, close reason and fill/source/rule sets reset per
episode. Directional, reversal, matched-pair, gap and liquidation closures are covered.

Daily loss blocks increases at `<= -1.5%` from the exact UTC-day start and drawdown blocks at
`<= -10%` from high water. UTC-day, segment and rolling resets occur at their E0 boundaries.
Protective reductions remain available; they never re-leverage. Mandates enforce exact instruments,
25% spot/directional caps, 50% per pair leg, price-based approximately 1x delta neutrality within
the mandate tolerance, no naked leg and no pyramiding unless the selected mandate permits it.

## Pair and depth semantics

Candle execution is all-or-none at the exact observed same-instrument open; a candle run cannot
fabricate a partial fill. Quote/L2 partial quantities come only from qualified depth and adapter
rules. The engine enumerates every intermediate post-fee spot result `R` and every permitted
perpetual `q` for each `R`, with priced VWAP, explicit/implicit/fee-asset economics, tick/step/minimum/
maximum/depth checks, funded collateral and all severe recovery legs. Duplicate outcomes reject;
the complete set and digest are permutation invariant and emitted/bound into the pair decision.
Callers cannot provide a domain, endpoint, price, delay, recovery flag, mark or cost. Actual fills
must equal one priced preflight outcome and cannot be worse than the frozen severe bound.

Entry preflights every path before spot leg 1. It buys spot then shorts the matched perpetual. If
leg 2 rejects or fills zero, its truthful failed order is emitted and actual net spot is severe-sold.
If leg 2 partially fills, its original requested/rounded quantity, actual fill and unfilled remainder
are reported; the exact filled short is severe-bought first, then actual net spot is severe-sold.
Every commit is permanent and immediately checked; the failed intention remains `invalid_unknown`.

Close preflights every `R × q` path, sells spot first, then buys the corresponding perpetual. A
mismatch receives one immediate finite, non-recursive severe whole-pair cleanup. If the perpetual
close cannot execute, a truthful failed/partial order and one engine-owned pending protective order
persist. Ordinary operations never cross segments. The sole exception is that already-pending
severe perpetual buy-to-close: pre-mark invalid, use exactly the first qualified new-segment price
strictly before terminal and inside the partition, emit full lineage, checkpoint, close the episode,
then reset. No spot leg, entry, ordinary order, second attempt or terminal/partition search crosses.

## Controls, gaps and outputs

Flat, buy-and-hold and same-exposure are separate real runs with identical qualified source,
scenario costs, eligibility, schedule, next-open and terminal convention. Buy-and-hold enters the
correct spot instrument at the true partition boundary and closes under the frozen terminal rule.
Same-exposure uses an independent information/direction rule while matching absolute exposure and
timestamps; it is not the candidate direction copied under another label.

An exposed gap is discovered from the authority-owned sequence. The engine marks invalid, consumes
the first qualified common in-bound observations, fully neutralizes every leg at severe economics,
emits decision/order/fill/account/episode rows, then resets segment and rolling state. If no eligible
observation exists, safety remains pending without inspecting beyond the partition/terminal bound.

Outputs use literal E0 decision/order/fill/funding/account/closed-episode schemas and nullable
ordinary invalidation. Counts, costs, summaries, implementation/authority/run-setting digests and
ledger digests derive from real rows and bound bytes. No placeholder, self-referential oracle,
hardcoded zero or caller-supplied lineage is accepted.

## Test ownership and qualification gates

- `test_canonical_authorities.py` owns A01–A04, H01–H02 and J01–J03.
- `test_ledger.py` owns B01–B09, G01–G05, I01–I03 and K01–K04/K06 ledger cases.
- `test_pair.py` owns C01–C07, E01–E06 and F01–F05.
- `test_controls_outputs.py` owns D01–D06 and K04–K06 control/artifact cases.
- `test_integration.py` proves all 56 probes across the public facade, exact module/import boundaries,
  all three RunSpecs, snapshot identity, failure-side-effect metamorphics and independent-oracle
  fixture inputs. It may not call a private mutator or use a candidate helper as its oracle.

The machine contract enumerates every probe by ID, requirement and owning test file. It also adds
distinct executable regressions for every V11 audit failure: hidden capability, immutable views,
authority loaded once, causal source failure atomicity, exact terminal/liquidation stop, truthful
zero/partial orders, candle partial rejection, priced/emitted Cartesian binding, severe identity,
all fee assets/tax, price-based pair mismatch, authority-owned gap, real controls, liquidation
lineage/account/episode, local MAE/MFE, UTC reset, key collision and computed residual.

Preflight requires exact E0 and authority hashes, complete V4–V11 negative archive closure,
canonical duplicate/nonfinite-free V12 JSON, absent V12 package/test/snapshot paths, blind-oracle
separation and `no_trade`. After implementation, active and mirrored snapshot file sets/bytes are
frozen before any independent oracle review. Any preflight or candidate failure archives exact V12
bytes and requires a new experiment ID; V12 is never repaired in place.
