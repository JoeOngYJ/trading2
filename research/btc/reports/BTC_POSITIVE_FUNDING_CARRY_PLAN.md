# BTC positive-funding carry development plan

Experiment ID: `btc-positive-funding-carry-v1`  
Status: frozen before outcome calculation  
Scope: offline development backtest; never actionable

## Hypothesis

Positive BTC perpetual funding is persistent enough that a slow, matched long-spot/short-perpetual
position entered only when the previous 28 days of completed funding can cover conservative
two-leg execution costs will earn positive net carry without directional BTC exposure.

The economic background is direct: when the perpetual trades with persistent long demand,
positive funding transfers value from long perpetual holders to short holders. A matched spot long
offsets the short perpetual's BTC direction, leaving funding and basis convergence as the intended
return sources. This does not presume the mechanism works after costs.

## Frozen causal rule

- Evaluate each Monday at 00:05 UTC, after the scheduled 00:00 funding event and its observed
  publication jitter.
- Use exactly the most recent 84 completed eight-hour funding events (28 days).
- Enter at the simultaneous 01:00 UTC spot and perpetual opens only when their cumulative funding
  exceeds 60 basis points, the primary full round-trip cost of two legs.
- Hold the matched pair until a weekly score falls to 30 basis points or lower, or 84 days elapse.
- Execute exits at the next 01:00 UTC opens. A time-stop exit cannot re-enter until the following
  weekly decision.
- Allocate 49% of current equity to each leg, round BTC quantity down to 0.00001, and require exact
  matched quantity and no more than 1% notional mismatch.
- Never consume premium-index data. Missing price, funding, mark or spot data fails the affected
  decision or position closed; no value is imputed.

Development is 2020-02-03 through 2023-12-31. Chronological validation is 2024-01-01 through
2025-12-31. Positions are flattened at the partition boundary. The validation period is useful
chronological evidence but is not a clean promotion holdout because its data was previously
inspected for quality. All 2026 history remains unread.

## Costs, accounting and controls

Run the frozen 30, 40 and 80 bps round-trip scenarios independently on both legs. Attribute spot
price PnL, perpetual price PnL, funding, basis convergence, explicit fees and implicit costs.
Check the frozen conservative planning-margin model hourly, including a 20% adverse mark shock.
This is not a historical bracket claim; exact historical rules remain a promotion blocker.

Compare against flat, 49%-notional BTC spot buy-and-hold, always-on matched carry, the exact signal
windows with funding removed, and funding-only return at the exact signal windows. Report exposure,
turnover, trade count, calendar results, concentration and margin stress separately.

## Frozen acceptance gates

The strategy is rejected unless all of the following pass on chronological validation:

1. Net return is positive at both 30 and 80 bps per-leg round-trip costs.
2. Primary profit factor is at least 1.10 and Sharpe at least 0.50.
3. Primary maximum drawdown is no more than 10%.
4. At least four trades close and both validation calendar years are positive.
5. Funding cashflow is positive and the strategy's return per exposed day exceeds always-on carry.
6. Entry weeks have higher subsequent 28-day funding than non-entry weeks with a positive
   month-block 95% confidence lower bound.
7. No observed or 20%-shock planning-margin breach occurs.
8. Neither the best three months nor best trade contributes more than 60% of positive PnL.
9. Predeclared 14-day and 42-day lookback variants are both net positive at primary cost without
   changing the 60/30-basis-point entry/exit thresholds.

No failed gate may be repaired under this experiment ID. No regime model may filter or rescue it.
