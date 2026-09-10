# BTC market-condition scores MCS3-C readiness result

Audit: `btc-market-condition-scores-mcs3-c-readiness-v1`  
Disposition: **blocked; MCS3-C not activated**  
Role: metadata-only consolidation of already consumed evidence  
Boundary: 2020-01-01 through 2025-12-31 development evidence; 2026 remained inaccessible

## Decision

Do not freeze or run the program's named MCS3-C net-carry score with the current repository
evidence. Stop the current market-condition score-panel branch. MCS4 remains blocked because no
standalone score has passed.

This is not a conclusion that carry can never work. It is a narrower conclusion: the repository
can reproduce a segmented gross-carry diagnostic, but cannot causally label historical **net**
carry after the fees, collateral and margin/liquidation economics required by the frozen program.

## What is ready

- All 6,576 scheduled eight-hour funding events from 2020–2025 are present with no missing event,
  duplicate, invalid row or irregular interval.
- Perpetual execution klines contain all 52,608 hours.
- Exact REST recovery brings mark and index histories to all 52,608 hours with no gaps.
- Spot execution history is checksummed and segment-aware. Its gaps must remain unknown/reset
  boundaries; they may not be interpolated.
- The one missing premium-index hour at 2020-12-01 23:00 UTC does not block a basic score that
  excludes premium. If premium is later consumed, that hour is a hard fail-flat/reset boundary.
- The rejected carry-v1 identity remains fixed: 60/30-bps entry/exit thresholds, 84-event primary
  lookback and 42/126-event robustness controls may not be tuned or rescued by a score.

## Blocking gates

| Required gate | Result | Reason |
|---|---|---|
| Effective-dated historical spot and perpetual fees | Fail | No checksummed 2020–2025 maker/taker, VIP, discount or promotion schedule with applicability intervals |
| Effective-dated maintenance-margin brackets | Fail | No historical BTCUSDT notional tiers, maintenance rates, cumulative amounts or leverage-bracket effective dates |
| Historical contract, funding, liquidation and ADL rules | Fail | Current snapshots cannot establish historical cap/floor/interval, filter, liquidation or ADL semantics |
| Frozen collateral and financing treatment | Fail | Opportunity cost is required by the mandate but absent from carry-v1's frozen attribution/model |

Exact account fees are also absent, but remain a promotion-only requirement. The generic
30/40/80-bps scenarios and the development-only 10% maintenance/20% shock assumptions are useful
stress controls; they are not historical facts and may not be projected backward to manufacture
an exact net-carry label.

Additional causal constraints remain unresolved: archived price rows do not carry explicit
per-row `available_at`; a future funding runner must use actual `calc_time` or a preregistered
conservative delay; all spot gaps must propagate unknown/reset; and the whole 2020–2025 carry
boundary is already consumed development evidence rather than promotion evidence.

## Integrity

- The audit opened only checksummed contracts, manifests and summary reports—no raw market,
  funding, trade, feature, label or PnL ledger.
- No score/model was fitted and no strategy, position, PnL, order, route or risk cap was evaluated.
- No network, database, NATS, Freqtrade, exchange, soak, partial OB0 or 2026 data was accessed.
- Nine focused tests pass and report/manifest replay is byte-identical.

## Next permitted research action

Do not build MCS4 and do not create a weaker `gross_carry_information` experiment merely to keep
the score program moving. Return to one materially new, economically explained BTC strategy
hypothesis, frozen independently before outcomes. EWMA remains the mandatory risk benchmark.

MCS3-C may be reconsidered only after a separately bounded source-qualification packet acquires
effective-dated historical economics and rules. Even then, it requires a genuinely new fixed-
horizon per-unit net-carry forecasting hypothesis, the rejected carry-v1 controls unchanged,
chronological forecast-loss/calibration gates and prospective promotion evidence.

Accepted condition scores and strategy arms remain empty. Every actionable route remains
`no_trade`.
