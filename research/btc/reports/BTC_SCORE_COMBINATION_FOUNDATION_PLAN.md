# BTC score-combination foundation plan

Experiment ID: `btc-score-combination-foundation-v1`  
Status: **frozen before implementation**  
Evidence boundary: synthetic fixtures only  
Actionable arm: `no_trade`

## Hypothesis

A deterministic offline contract can preserve a catalogue of target-specific BTC condition
forecasts, calibrate each value against history available by its own fit cutoff, and combine only
eligible forecasts of exactly the same target, horizon, kind and units without creating a master
market score or strategy action.

This is an infrastructure hypothesis, not a forecast or trading hypothesis. It does not activate
MCS4. The existing multidimensional-risk foundation remains authoritative for downward-only risk
cap fusion and is not reimplemented here.

## Frozen implementation

1. Add immutable, checksummed `ScoreCatalogueEntry` and `ScoreCatalogue` contracts.
2. Add a causal empirical midrank percentile transform that preserves raw score lineage and uses
   only calibration observations available by the score's fit cutoff.
3. Add predeclared non-negative convex ensembles with weights summing to one.
4. Require every ensemble member to share target, axis, horizon, score kind and units and to have
   `benchmark` or `accepted` evidence.
5. Mark every new ensemble output `development`; an ensemble receives no conditioning authority
   merely because its members were eligible.
6. Fail closed on unknown, stale, future-dependent, rejected or development members.

## Prohibited conclusions

- A percentile is not a favorable-market probability.
- Scores for persistence, reversion, volatility, downside, jump, carry or liquidity cannot be
  averaged merely because they are displayed on a zero-to-one scale.
- Current rejected detector outputs cannot enter an ensemble.
- No strategy direction, expected return, position, PnL, signal or order is produced.
- No market data, 2026 partition, partial OB0 data or protected service is accessed.

## Pass gates

The packet passes only if canonical serialization is deterministic; duplicate catalogue entries,
future calibration samples, mixed-target ensembles, invalid weights and unusable members fail;
synthetic replay is byte-identical; and focused plus adjacent score/risk tests pass.

Passing means the repository can safely represent future score combinations after eligible inputs
exist. It does not mean a hybrid detector, strategy or strategy router has evidence.
