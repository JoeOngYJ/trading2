# BTC multi-horizon perpetual trend v5 — result

Decision: **rejected on frozen historical gates**  
Accepted arms: none  
Actionable arm: `no_trade`

At 30 bps the fixed 7/28/84-day blend earned 48.30% in development (2020-02-03 through
2023-12-31), a 10.60% CAGR, 0.776 Sharpe and 14.22% maximum drawdown across 116 episodes. It then
lost 6.41% in the already-consumed 2024–2025 stability period, with -3.25% CAGR, -0.305 Sharpe,
13.87% drawdown and 53 episodes. Both 2024 (-6.42%) and 2025 (-0.26%) were negative.

At severe 80-bps costs, development retained 26.52% but drawdown rose to 21.52%; stability lost
12.77%. The monthly bootstrap lower bound was negative in both partitions and stability positive-
month profit was 70.53% concentrated in its best three months.

The proposed blend did not add trend alpha. The simpler same-size 28-day sign control earned
122.21% in development and lost 7.13% in stability; always-long earned 53.28% and 7.06%
respectively. The blend therefore failed both exposure-normalized control gates as well as
positive-stability, severe-cost, annual-stability, Sharpe, bootstrap and concentration gates.
Positive development performance cannot rescue those failures.

Fixed and EWMA-downscaled results were identical because the frozen 40% portfolio-volatility cap
never bound at 25% notional. This is risk-implementation attribution, not evidence of alpha.

The byte-identical replay and independent audit confirm the rejection, all controls and the
absence of 2026, accepted arms or actionable output. Do not tune horizons, weights, threshold,
volatility target or costs under this family/ID.

## Next permitted action

Close this continuous price-trend blend. Preserve the simple 28-day rule only as a development
control—it also lost in 2024–2025 and is not accepted. Select and freeze a materially different
BTC alpha family rather than another price-trend speed, blend or regime rescue.
