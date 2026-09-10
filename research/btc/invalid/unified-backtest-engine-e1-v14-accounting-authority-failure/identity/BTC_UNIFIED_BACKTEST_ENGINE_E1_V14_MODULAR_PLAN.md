# BTC unified backtest engine E1-v14 modular architecture plan

Stage: `E1-v14 preimplementation`
Experiment ID: `btc-unified-backtest-engine-e1-v14`
Actionable arm: `no_trade`

## Scope

E1-v14 is offline, synthetic, zero-capital accounting infrastructure. It preserves the accepted
E0-v1–v4 economics and the V12 modular design while closing all prior preflight defects: all four
RunSpecs and their support authorities exist and are checksummed before implementation, and every
semantic probe has exactly one primary test owner. No historical strategy data, sealed 2026,
partial OB0, credentials, network, exchange, database, NATS, Freqtrade, protected service, strategy
metric, paper order or live execution is permitted. Only `no_trade` is actionable.

Prior E1 artifacts are immutable negative evidence, available to validators/reviewers only after
snapshot freeze. Implementers may read E0-v1–v4, this V14 plan/contract, exact execution/mandate
authorities and the six V14 fixture authorities. They may not inspect, search, read, import,
execute, copy, diff, summarize or repair prior E1 evidence. Every requirement and probe is stated
by value. Numerical terminal oracle outputs remain reviewer-only after snapshot.

## Exact preimplementation authorities

The canonical files under `research/btc/fixtures/unified-engine-e1-v14/` are frozen inputs:

| Role | File | SHA-256 |
|---|---|---|
| instrument rules | `instrument-rules.json` | `858c96ce58abe4c02189f2102160a28bbc029d76b87515fa819d93ce1d770bb5` |
| margin rules | `margin-rules.json` | `b887b06d13ee414dc45ac6f76764586062c275b2581f46db979a8ebb00c79d60` |
| semantic settings | `semantic-settings.json` | `e47527842e8ae7d4a046576beac3146e69fac5e169e51e76e246143c2690647c` |
| candle observations | `candle-source-observations.json` | `96b80f8502a612b2475eb8a23f984380e747c00f5f3813802ef90d9fafd78ff5` |
| qualified L2/depth | `l2-source-depth-observations.json` | `9b7d9ba8e95ec814f1f02eb3e740284a5838bad4274c234d1a38e12ed7077e3c` |
| four RunSpecs | `run-specs.json` | `7e341a480e3c6edba78ba02aa445c0feb9df65e9c8dadba3fb0f7b308a1abf4b` |

Each RunSpec fixes its schema, ID, selected mandate ID/path/hash, its adapter-compatible primary
scenario, 80-bps severe cost budget, permitted comparison-budget IDs, synthetic UTC partition
start and exclusive terminal, next-hour execution and terminal convention, initial NAV `1000`,
leverage `1`, and rule/margin/source/settings roles, paths and hashes. The four identities are
`spot_candle_primary`, `directional_candle_primary`, `pair_candle_primary`, and `pair_l2_primary`.
Only the exact execution authority may derive the 40/80 sensitivities; callers never provide rates.
Candle observations are all-or-none. Full, zero-by-bound, rejected-adapter and partial-by-bound
patterns exist only in qualified L2 evidence; no candle partial can be synthesized.

`pair_l2_primary` is exactly `qualified_l2` with `book-taker-primary-250ms-v1`, mode
`book_taker`, and latency `250` ms. Its actual ledger uses that authority's 10-bps fee, visible
depth VWAP, residual-impact and price-protection fields. Separately named 30/40/80-bps comparison
budgets apply the exact taker-fee plus implicit-cost fields from the three bound candle cost rows to
the same actual book-filled notional for reporting only. They never change price, quantity, fill
mode or latency and are never labelled as candle executions. Caller rates remain forbidden.

## Modules, snapshot and facade

The exact active modules remain:

```text
src/trading_platform/btc_accounting_e1_v14/
  __init__.py canonical.py authorities.py ledger.py pair.py controls.py
```

The exact tests remain:

```text
research/btc/tests/btc_accounting_e1_v14/
  test_canonical_authorities.py test_ledger.py test_pair.py
  test_controls_outputs.py test_integration.py
```

The candidate root `research/btc/candidates/unified-backtest-engine-e1-v14/` mirrors all eleven
relative source/test paths and contains exact copies of the six fixture authorities plus a
canonical manifest. All active/mirror bytes and file sets must match before oracle review.

Imports are acyclic: `canonical` has no internal dependency; `authorities -> canonical`;
`ledger -> canonical + authorities`; `pair -> ledger + authorities`; `controls -> ledger + pair`;
`__init__` is the facade over them. No prior E1, network or production import is allowed.

The facade exposes the verified factory, immutable value views, `open_next_interval`, authorized
spot/directional targets, `atomic_pair_entry`, `atomic_pair_close`, `close_interval`, `terminate`,
named control runs and immutable state/rows/episodes/bindings/artifacts. The caller chooses only a
fixed RunSpec ID and an authorized target quantity. There is no generic fill/funding/decision,
clock, phase, source, price, outcome, cost, state, row or binding input/mutator. Construction uses
a module-private closure or weak-key capability—not an exported/readable token. Exact authority
bytes are verified and loaded once; operations never reopen files.

## Economic and event contract

The nine phases remain exact: boundary/source validation and t-minus snapshot; open mark and
immediate liquidation only; pre-caused protective/gap reduction only; t-minus funding and immediate
liquidation; risk permissions; ordinary exit/rebalance/next-open entry; checkpoint after each fill;
intrabar adverse risk separated from close PnL and close mark; reconciliation/account. Same-time
priority is liquidation, protection, funding, ordinary. Invalid source/timestamps fail before any
mutation. Terminal/liquidation is monotone and suppresses every later event except required terminal
rows. Protective/delayed work is genuinely phase 3, never phase-6 impersonation.

All economics use finite `Decimal`. Costs use one accounting price and one separately recorded and
debited explicit/implicit charge. Quote, base, permitted third-asset fees and tax mutate actual
balances/NAV; insufficient assets fail before voluntary fills. Isolated collateral, proportional
margin release, funding ownership, exit reserve, maintenance, liability and liquidation follow E0.
Severe rows use the exact severe scenario ID/rates. Transition residual is calculated. Every row
chains the immediately prior state digest and binds actual implementation, RunSpec, source, rule,
margin, order and emitted fill lineage.

Orders truthfully preserve requested, rounded, filled, unfilled, status and reason for zero,
rejected, expired, partial and recovery paths. Liquidation cannot accept caller lineage, emits its
full order/fill/account, closes the episode and stops later work. Episodes are local across
directional/reversal/pair/gap/liquidation: costs, price/funding/net PnL, MAE/MFE, reason and lineage
do not leak between episodes. Daily loss blocks increases at `<= -1.5%`, drawdown at `<= -10%`;
UTC-day, segment and rolling resets are exact, while protective reductions remain available.

Mandates enforce exact instruments, 25% spot/directional caps, 50% per pair leg, price-based
approximately 1x delta within the 1% pair tolerance, no naked leg, and no unpermitted pyramiding.
Candle is exact-open all-or-none. L2 walks qualified visible depth and is the only source of partial
fills. The pair engine emits and binds the complete priced, funded, canonical, duplicate-free and
permutation-invariant `R × q` outcome set. Entry preflights all outcomes before spot; zero/rejected
leg 2 emits its failed order then neutralizes spot; partial leg 2 reports the original intention,
closes its exact fill first, then spot. Close is spot-first then perp, with one finite immediate
severe mismatch attempt. The sole delayed cross-segment exception remains the pre-invalidated
pending perp buy-to-close at the first qualified new-segment price strictly inside terminal and
partition; reset occurs only after fill.

Gap timing is authority-owned: first valid common in-bound observations, full severe cleanup,
complete rows and episode, sticky invalidity, then reset. Missing cleanup stays pending without
boundary search. Flat, true partition-boundary spot buy-and-hold, and independently directed
same-timestamp/same-absolute-exposure controls are full economic runs under identical source,
costs, eligibility, next-open schedule and terminal rules. Outputs use literal E0 schemas; counts,
costs, summaries and digests derive from real rows and bound bytes, never placeholders.

## Test ownership

Each A01–K06 probe and R01–R22 audit regression has exactly one primary owner in the machine
contract:

- canonical/authority A, H, J and construction/authority/collision regressions:
  `test_canonical_authorities.py`;
- ledger B, G, I, K ledger semantics and phase/funding/liquidation/episode/reset regressions:
  `test_ledger.py`;
- pair/depth C, E, F and truthful-order/Cartesian/severe/delta regressions: `test_pair.py`;
- control/gap/artifact D, K05 and economic-control/gap regressions: `test_controls_outputs.py`.

`test_integration.py` owns only separately named W01–W06 wiring probes: import graph, facade-only
surface, all four RunSpecs, active/snapshot mirror, public failure metamorphics and blind-oracle
input handoff. It may invoke semantic tests but cannot own, replace or duplicate their assertions.
Tests use the public facade except isolated pure functions in their owning unit module.

Preflight requires exact hashes, canonical finite JSON, complete V4–V12 archive closure, all six
fixtures present, all reserved code/test/snapshot paths absent, no oracle output and `no_trade`.
Failure archives exact V14 bytes and requires a new ID; V14 is never patched in place.
