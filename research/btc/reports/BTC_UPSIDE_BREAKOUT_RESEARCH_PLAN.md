# BTC Upside Compression Breakout Research Plan

Status: frozen before historical outcome access  
Program: `btc-upside-compression-breakout-v1`  
Frozen at: `2026-09-01T01:00:00Z`

## Purpose

This packet asks two separate questions without claiming a tradable strategy:

1. Can a strict, causal definition catalogue BTC upside breaks from completed compressed
   ranges?
2. At the confirmation timestamp, can frozen price-path information forecast continuation
   versus range re-entry during the following seven days better than simple empirical and
   linear competing-risk controls?

The historical catalogue is development evidence. It cannot accept a strategy arm, create
positions or PnL, or authorize execution. A separately frozen prospective evaluation is
required before any future promotion review.

## Stages

### BEX1 — Event and path catalogue

- Re-derive exact segment-aware four-hour and one-hour candles from the accepted five-minute
  source.
- Define compression only from bars completed before each four-hour activation decision.
- Confirm an upside break only on a later complete one-hour bar and bind the decision to the
  exact next five-minute open.
- Record two competing follow-through outcomes from completed one-hour closes: one frozen
  volatility unit of continuation or re-entry at/below the frozen range high.
- Treat seven-day survival and segment loss as censoring, not as event classes.
- Suppress overlapping setups through each confirmed episode's full seven-day path.

### BEX2 — Nested chronological competing-risk comparison

- Compare an empirical age-hazard control, a regularized linear discrete-time hazard model,
  histogram gradient boosting and CPU XGBoost.
- Use outer calendar-year folds for 2021–2025 and inner chronological folds only.
- Purge labels unavailable before each fit and apply a fourteen-day embargo.
- Select hyperparameters and temperature calibration only from inner out-of-fold forecasts.
- Use integrated competing-risk Brier score as the primary loss.
- Keep nonlinear models unavailable unless every frozen sample gate passes.

### BEX-D — Driver evidence foundation

- Preserve official announcement records with release, retrieval, revision and source
  lineage.
- Match only causal release timestamps to already frozen breakout episodes.
- Do not call a nearby announcement a cause; association and causal attribution remain
  distinct.
- No numeric driver study is allowed until complete official event histories are separately
  acquired, qualified and checksummed.

## Safety boundary

Only BTCUSDT spot archival development data through 2025 may be read. The study computes no
strategy PnL, order, position, leverage or production signal. The 2026 partition, partial OB0,
network, databases, NATS, Freqtrade, exchanges and soak services are prohibited. Every output
retains `actionable_arm_id = no_trade` and zero accepted arms.

## Interpretation

A BEX2 development pass would mean only that a frozen follow-through forecast merits a new
prospective contract. It would not establish a profitable strategy. Entry, exits, sizing,
costed PnL, market-beta attribution and mandatory controls belong to a later experiment ID.
