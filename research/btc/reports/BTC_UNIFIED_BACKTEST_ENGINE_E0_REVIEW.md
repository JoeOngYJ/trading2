# BTC unified backtest engine E0 independent review

Qualification ID: `btc-unified-backtest-engine-e0-v1`  
Disposition: **PASS — E1 synthetic kernel only is permitted**  
Actionable arm: `no_trade`

## Independent audit

The audit found that no existing repository engine is authoritative for unified BTC spot and
linear USD-M perpetual research. In particular, the legacy spot core can fill an exit at its
signal reference rather than the execution-row open and conflates decision and fill time. The
perpetual runners disagree on funding/rebalance order, use bespoke incomplete collateral state,
can omit funding across gaps, check margin only at close, and do not provide a genuinely
independent accounting oracle. One historical runner also attributes reversal entry costs to the
episode being closed and substitutes a post-warm-up always-long series for true
partition-boundary buy-and-hold.

Those historical results remain preserved; E0 does not rewrite them. E4 must reconcile them using
the qualified engine and report any difference before any result is relied upon.

## Adversarial contract review

The first E0 draft failed review. Fourteen blocking areas were corrected: bound machine
authorities, opening-gap liquidation precedence, isolated-collateral movements, signed realized
PnL, native fee effects, cross-gap invalidation, deterministic pair-leg sequencing, canonical
Decimal and digest rules, oracle independence, the synthetic/metamorphic fixture matrix, control
semantics, row-level lineage, cash-cost versus diagnostic classification, and the candle
all-or-none evidence boundary.

The final independent review verified:

- recursively sorted canonical JSON with duplicate and non-finite values rejected;
- exact hashes for all eleven bound authority files;
- unambiguous next-open execution, funding ownership, liquidation and partition termination;
- complete balance/memo accounting, fee-asset valuation and no cost double counting;
- row digests, event sequence, before/after state and residual fields on every ledger;
- an E2 oracle isolated from kernel code, dataclasses, ledgers, helpers and metrics;
- no historical return access through E2 and `no_trade` as the only actionable arm.

Final reviewed checksums:

- plan: `db515111ebf718d14c73d894911de61278b4835234ab66cb9e1846d50e23b122`;
- contract: `af23751e6ef08a4c0dc11eb33559b4d939ec38260ae2d3ae22fcb73237856c0e`.

## Boundary

This pass accepts a specification, not a backtest engine or a strategy. It permits only E1: an
offline Decimal accounting kernel exercised on synthetic fixtures. It does not permit historical
market access, strategy PnL, 2026, partial OB0, production imports, credentials, external services,
paper execution or live trading.
