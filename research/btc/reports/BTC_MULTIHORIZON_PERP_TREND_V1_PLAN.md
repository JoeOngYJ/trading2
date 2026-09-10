# BTC multi-horizon perpetual trend v1 — frozen plan

Experiment ID: `btc-multihorizon-perp-trend-v1`  
Status: **frozen before strategy-return access**  
Frozen: 2026-09-05

## Falsifiable claim

BTC exhibits sufficiently persistent directional movement that the sign of a fixed blend of
completed 7-, 28- and 84-day perpetual returns earns positive net returns long and short after
funding and severe costs, and adds value beyond both always-long exposure and a simpler 28-day
sign rule at the same position size. The mechanism is slow under-reaction and position adjustment,
not prediction of news, breakout labelling, funding timing or a regime classifier.

This is a continuous-clock trend experiment: it evaluates every eligible UTC day rather than
selecting a sparse catalogue of conspicuous historical breakouts. It remains part of the existing
`btc_directional_trend` family and cannot later be counted as diversification from breakout/SMA.

## Frozen signal and execution

At 00:05 UTC each day, use only hourly candles completed by 00:00. For horizons 168, 672 and
2,016 hours, calculate log close-to-close return divided by the square root of its horizon and by
the causal daily EWMA hourly-volatility estimate. Clip each standardized component to [-2, 2] and
take their equal-weight mean. A score above +0.25 targets long, below -0.25 targets short, and
otherwise targets flat. Execute a change at the next 01:00 UTC hourly open. Hold the previous
position between decisions; never pyramid or re-leverage intraday.

Fixed alpha sizing is 25% absolute notional of current equity. A separately reported mandatory
risk implementation may only scale that notional downward using daily EWMA volatility with
lambda 0.94 and a 40% annualized volatility target. It may not change direction or improve the
reported signal-quality comparison through extra exposure.

Funding is applied at its exact archived timestamp with the correct long/short sign. Reversals
are a close plus a new entry. Missing hours, missing scheduled funding, a source segment change,
or stale features force flat at the next eligible open under severe exit costs.

## Evidence and controls

- Source: checksummed official Binance USD-M BTCUSDT hourly klines and funding archives.
- Development: 2020-02-03 through 2023-12-31.
- Consumed stability diagnostic: 2024-01-01 through 2025-12-31.
- 2026 is forbidden. The diagnostic period is already observed by related work and is not a
  holdout or promotion evidence.
- Costs: frozen 30, 40 and 80 bps round trip, charged on actual turnover.
- Controls: flat; BTC perpetual buy-and-hold; always-long at identical daily sizing; simple
  28-day return-sign trend at identical size/timestamps; lagged seeded random signs; and the
  mandatory downward-only EWMA implementation.
- Attribution: long/short price PnL, funding, explicit and implicit cost, turnover, exposure,
  sizing, calendar year/month, best months and best trades.

## Frozen gates

The fixed-size signal must have at least 12 closed position episodes, positive net return at 30
and 80 bps in both partitions, positive 2024 and 2025 returns, at least four positive calendar
years across 2020–2025, primary Sharpe above 0.50, profit factor above 1.10, maximum drawdown no
greater than 20%, and best-three-month positive-PnL concentration no greater than 60%.

At 30 bps its return per unit absolute exposure must strictly exceed both always-long and the
simple 28-day sign control. A deterministic month-block bootstrap 95% interval for mean monthly
net return must have a lower bound above zero. All causal, funding-completeness, margin-stress and
2026-exclusion checks must pass. Failure of any gate rejects this ID; no threshold, horizon,
weight, target-volatility or cost may then be tuned under it.

Even if every gate passes, the consumed evaluation period prevents promotion. The maximum result
is a development candidate requiring prospective evidence. Every actionable route stays
`no_trade`; no credential, position, order, protected service or partial OB0 dataset is touched.

## Implementation stages

1. T0: validate contract, archives, continuity, funding schedule and causal timestamp fixtures.
2. T1: implement the signal, controls, ledger, stress/risk accounting and synthetic tests.
3. T2: independent audit of formulas, fills, costs, funding signs, gaps and deterministic replay.
4. T3: run once, publish all frozen scenarios and gates, append the immutable decision record,
   update the tracker/handoff and validate the checksummed BTC context.
