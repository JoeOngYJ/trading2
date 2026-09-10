# BTC multi-horizon perpetual trend v2 — implementation clarification

Experiment ID: `btc-multihorizon-perp-trend-v2`  
Status: **frozen before signal or return access**  
Frozen: 2026-09-05

V1 passed source-only T0 but is closed before T1 because “EWMA hourly volatility” did not bind
the sampling series, initialization or recursive update. V2 inherits the v1 hypothesis, source,
7/28/84-day horizons, equal weights, clipping, +/-0.25 direction band, daily decision/fill clock,
25% fixed-size evaluation, costs, controls, partitions and gates. It changes no economic claim.

The exact implementation is now:

- Sample one completed close per UTC day: the close of the 23:00–23:59:59.999 hourly bar,
  available at 00:00 and used by the 00:05 decision.
- Daily return is the log ratio of consecutive sampled closes. At a decision, all daily returns
  through the just-completed close are available.
- Initialize daily variance as the arithmetic mean of the first 20 squared daily returns. From
  the 21st return onward update `variance_t = 0.94*variance_(t-1) + 0.06*return_t^2`. No mean is
  subtracted. Zero/non-finite variance fails closed.
- Each component is `log(close_t/close_(t-h))/(sqrt(h)*daily_vol_t)`, with `h` equal to 7, 28 or
  84 days, clipped to [-2,2]. The blend is the exact arithmetic mean.
- Fixed-size targets are -25%, 0 or +25% of current equity. Quantity rounds down to 0.00001 BTC.
  Rebalance only at the next 01:00 open. A reversal is one close and one new entry, with costs on
  both transactions. Mark-to-market equity is updated before sizing.
- Funding cashflow at an exact scheduled timestamp is `-direction * quantity * mark * rate` for
  the position held entering that timestamp: positive funding is paid by longs and received by
  shorts.
- The EWMA risk implementation uses the same causal daily volatility. Its absolute fraction is
  `min(0.25, 0.40/(sqrt(365)*daily_vol_t))`, so it can only reduce fixed exposure.
- The seeded control draws independently from long/flat/short probabilities 0.45/0.10/0.45 using
  Python's local `random.Random(20260905)` in chronological decision order; it never shares global
  RNG state.
- Isolated planning collateral is 75% of pre-position equity. Every completed hour stresses the
  current mark 50% down for a long or 50% up for a short. Maintenance is 10% of shocked notional.
  A shocked equity/maintenance ratio below 2 triggers a severe-cost exit at the next hourly open.
- A missing hour, missing applicable funding event or discontinuity forces flat at the next
  available hourly open under severe cost and resets the daily-return/EWMA history.

T0-v2 evidence is inherited as source qualification; it opened no signal or return. T1 must use
synthetic fixtures only and independently audit every formula above. Historical execution is not
permitted until T1 passes. V2 remains development-only, in `btc_directional_trend`, and incapable
of creating an actionable route.
