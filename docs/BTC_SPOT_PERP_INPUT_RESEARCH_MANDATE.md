# BTC spot strategy with perpetual-data inputs

Mandate ID: `retail-btc-spot-cross-market-input-research-v1`  
Status: **frozen offline information research only**  
Machine-readable source:
`config/mandates/retail-btc-spot-cross-market-input-research-v1.json`

## Purpose

This mandate resolves the boundary between the frozen spot-only trading mandate and public
derivatives observations. It permits checksummed BTCUSDT USD-M perpetual klines to be used only
as offline explanatory or forecast inputs for a possible BTCUSDT spot long/flat strategy.

It does not permit a perpetual position, a naked short, margin, leverage, credentials, account
access, orders, transfers, production integration, paper orders sent to an exchange, or live
capital. `actionable_arm_id` remains `no_trade` and maximum live allocation remains zero.

## Current stage

The only authorized work is the label-blind D0 source qualification for
`btc-spot-perp-continuation-information-v1`. D0 may validate completed spot and perpetual prices,
quote turnover, timestamps, continuity, source revisions and feature-availability counts. It may
not calculate a future-return label, fit a model, select a strategy threshold, calculate PnL or
emit a position.

Any later information experiment requires a separately frozen D1 contract. Any later spot
strategy requires a further conditional contract, the mandatory EWMA risk benchmark and the
frozen spot execution-cost scenarios.
