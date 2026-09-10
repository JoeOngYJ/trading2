# BTC backtest engine E0-v5 component-boundary plan

Stage: `E0-v5 design qualification`  
Experiment ID: `btc-unified-backtest-engine-e0-v5-component-boundaries`  
Actionable arm: `no_trade`

## Objective

Replace the failed monolithic E1 lineage with a realistic supported-public-API contract and seven
independently qualifiable components. This stage freezes design only. It creates no accounting
engine, numerical oracle answer, historical backtest, strategy signal, PnL, position or order.

E0-v5 supersedes only E0-v4's proposed `next_E1` implementation path. E0-v4 remains immutable
incident and lineage evidence; it is not retroactively treated as implementation authorization.
All economic semantics frozen by E0-v1, E0-v2 and E0-v3 remain inherited without relaxation.

## Supported boundary and threat model

The future engine guarantees behavior only through the documented public API. A normal caller may
select a frozen RunSpec ID and an authorized target; it may not supply authoritative prices,
timestamps, fills, fees, scenarios, state, event sequence or lineage.

Python reflection, direct private-module imports, underscore-prefixed members, monkey-patching,
`object.__setattr__`, closure inspection and arbitrary memory mutation are explicitly unsupported.
The engine is accounting research infrastructure, not a security sandbox for hostile code already
executing in its process. Qualification must not claim that Python internals are unforgeable.

Implementer tests use only the supported API except for tests of isolated, documented pure
functions. Independent oracle tests consume canonical emitted JSON and frozen authorities without
importing implementation packages. Neither test layer may mutate private state, advance a private
cursor, invoke a private constructor or use an internal capability token.

## Component sequence

| ID | Future experiment | Owns | Cannot own |
|---|---|---|---|
| C0 | `btc-backtest-authorities-c0-v1` | canonical parsing, authority verification, immutable RunContext, complete implementation identity | prices, fills, balances, strategy |
| C1 | `btc-backtest-ledger-c1-v1` | execution-neutral Decimal state transitions, inherited nine-phase clock, funding, margin, liquidation and exact reconciliation | price discovery, adapter selection, pair recovery, controls |
| C2 | `btc-backtest-candle-adapter-c2-v1` | exact-next-open, all-or-none candle `ExecutionFact` creation | balances, L2, pair recovery, controls |
| C3 | `btc-backtest-l2-adapter-c3-v1` | book validation, latency, depth walk, VWAP, side-aware price bounds and partial/unfilled `ExecutionFact` creation | balances, pair recovery, controls |
| C4 | `btc-backtest-pair-coordinator-c4-v1` | exhaustive current-outcome preflight, final-fill commit ordering, compensating neutralization and truthful recovery | price discovery, book walking, rollback, new accounting formula |
| C5 | `btc-backtest-candle-controls-c5-v1` | independent candle control intentions executed through accepted C2/C1 and full candle cost-scenario reports | deriving controls from candidate rows, changing adapter logic |
| C6 | `btc-backtest-integration-c6-v1` | wiring independently accepted C0-C5 artifacts and end-to-end conformance | new economic behavior |

Qualification is sequential: C0, C1, C2, C5 candle qualification, C3, C4, then C6. A later L2
control/reporting extension requires `btc-backtest-l2-controls-c5-v2` after C3; a pair extension
requires a separately frozen C5 identity after C4. A failure closes that experiment ID and blocks
dependent components. Candle qualification deliberately precedes L2 and pair work because credible
long-history research does not require either subsystem.

## Accounting invariants

Each committed event must satisfy exactly, in Decimal arithmetic:

```text
ending_NAV = starting_NAV
           + realized_price_PnL
           + unrealized_PnL_change
           + funding
           - explicit_fees
           - taxes
           - implicit_costs
           - liquidation_costs
```

A closed-form synthetic transition must have exact zero residual. The inherited runtime gate
remains `abs(exact residual) <= 0.00000001 USDT`; a larger residual, missing economic term,
unavailable fee asset, invalid timestamp or incomplete lineage fails closed. Quote-, base- and
permitted third-asset commissions and taxes mutate their actual balances; diagnostics never
substitute for balance mutation.

L2 execution always uses a qualified book at decision time plus the frozen latency, walks the
correct side, respects the price bound and reports VWAP, filled and unfilled quantity, spread,
visible-depth and residual-impact fields. Protective, liquidation, recovery and terminal L2 fills
use the same adapter. No L2 path may call candle execution.

Candle 30/40/80-bps scenarios are separate complete economic runs and may change admission or
expiry only where their frozen price caps require it. L2 30/40/80-bps comparisons are reporting-
only transformations of the same actual book-filled notional. L2 comparisons may not change
price, quantity, latency, fill status, execution mode or source and must never be labelled as
candle fills.

## Pair transaction boundary

C4 must preflight all currently bound permitted outcomes before leg one mutates state: full/full, rejected second
leg, expired second leg, partial second leg, insufficient cash/collateral/fee asset, successful or
failed severe neutralization, gap/terminal boundary, and currently knowable funding or liquidation.

Every fill is final and rollback is forbidden, preserving E0-v3. After leg-one commit, failures use
bounded compensating neutralization. An unforeseen post-commit exception produces sticky
`invalid_unknown`, a canonical record with complete before/after state and a bounded pending safety
intention; it may not leave an apparently active valid run or contribute performance. Pair episodes
use `delta_neutral_pair`, not a directional spot label.

## Test independence

Three layers are frozen:

1. implementer tests of public behavior, fail-closed inputs and invariants, without hidden oracle
   terminal values;
2. Q0 independent closed-form oracle fixtures created only after the implementation candidate is
   checksummed, consuming emitted JSON without implementation imports; and
3. mutation tests that inject double fees, missed funding, wrong-side execution, candle/L2
   substitution, partial pair mutation, non-zero residual and broken lineage.

Probe ownership is exclusive. An integration test may prove wiring but cannot replace component
semantic qualification. Passing implementer tests is never acceptance evidence by itself.

## E0-v5 gates

E0-v5 passes only when the machine contract and validator prove that:

- every v4-v14 failure maps to a requirement, component owner and independent probe;
- the public boundary contains no anti-introspection or unforgeability promise;
- C0-C5 responsibilities and prohibited responsibilities do not overlap;
- E0-v1-v3 economics are inherited and E0-v4 is retained only as incident evidence;
- every row binds the complete run-context/implementation manifest and event-specific source,
  mandate, rule, margin, settings and scenario digests or explicit `not_applicable`;
- candle and L2 execution cannot substitute for each other;
- zero residual, integrated fee/tax balances and full funding timestamps are mandatory;
- pair preflight is complete before mutation and recovery terminates truthfully;
- oracle answers are absent and future implementation paths are absent;
- historical rows/results, 2026, partial OB0 and protected/external systems remain prohibited; and
- the only actionable arm is `no_trade`.

Failure rejects E0-v5 before any component implementation. Passing permits only C0 under its new
experiment ID. It does not permit C1-C6, E2, historical reconciliation or strategy evaluation.

## Frozen deliverables

- this plan;
- `research/btc/reports/BTC_UNIFIED_BACKTEST_ENGINE_E0_V5_FAILURE_MATRIX.md`;
- `research/btc/specs/btc-backtest-component-interfaces-e0-v5.json`;
- `research/btc/specs/btc-backtest-component-fixtures-e0-v5.json`;
- `research/btc/contracts/btc-unified-backtest-engine-e0-v5-component-boundaries.json`;
- `scripts/validate_btc_unified_engine_e0_v5.py`; and
- `research/btc/tests/test_unified_engine_e0_v5.py`.
