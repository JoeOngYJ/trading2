# BTC Order-Flow Research Plan

> Historical note (2026-08-25): the bar-level stages in this document are complete.
> The active higher-information workstream is genuine spot L2 acquisition and is defined
> in `docs/BTC_ORDER_BOOK_RESEARCH.md`. `aggTrades` remain a signed-trade control and must
> not be described as an order book.

## Decision

This was the single active strategy-research workstream. Its data-recovery stage is now
complete; the same scope guard continues under the L2 plan.

**Stage 1 status:** accepted on 2026-08-24. All 24 BTC archives and 210,528 rows
validated with zero gaps, duplicates, malformed rows, or invalid rows. A second run
produced byte-identical dataset and manifest checksums.

**Initial Stage 2 status:** complete as an exploratory event study. Extreme positive
imbalance showed short-horizon reversal in 2025, but the average effect was far below
modeled round-trip costs. Because the 2025 holdout has now been observed, the active task
is additional timestamp-safe history before any conditional hypothesis is frozen.

The first objective is to recover and validate BTCUSDT 5m trade-flow fields from the
existing Binance archives. The archives contain total base/quote volume, trade count,
and taker-buy base/quote volume, so no paid dataset is required for this stage.

## Stage 1 — Recover and validate order-flow data

Create a deterministic extractor for all BTCUSDT 5m archives covering 2024–2025. Preserve:

- open and close timestamps;
- OHLC;
- base and quote volume;
- trade count;
- taker-buy base and quote volume.

Derive only causal bar-level measurements:

- taker-sell base volume = total base volume - taker-buy base volume;
- trade-flow imbalance = (taker buy - taker sell) / total volume;
- taker-buy ratio = taker-buy base volume / total base volume;
- quote-volume pressure;
- trade intensity and average volume per trade.

Validation must reject negative volumes, buy volume above total volume, invalid OHLC,
duplicate or non-monotonic timestamps, unexpected bar duration, internal 5m gaps, and
non-finite derived values. Record input/output SHA-256 checksums, row counts, time range,
gap counts, duplicate counts, invalid counts, and monthly coverage in a manifest.

### Stage 1 acceptance criteria

- All 24 BTC monthly archives are processed.
- Expected 2024–2025 time coverage is present.
- No unexplained internal gaps or duplicate timestamps.
- Taker-buy volume is within `[0, total volume]` for every row.
- Derived imbalance is within `[-1, 1]` whenever total volume is positive.
- Re-running produces byte-identical output and manifest checksums.

## Stage 2 — Pattern discovery (blocked until Stage 1 passes)

Measure, without trading optimization:

- future BTC returns after extreme positive/negative flow imbalance;
- continuation versus reversal at 5m, 15m, 1h, and 4h horizons;
- interaction between imbalance, range expansion, realized volatility, and volume shock;
- conditional results by year, hour of day, volatility state, and BTC direction;
- stability of thresholds chosen only from the training period.

Use event studies, quantile bins, block-bootstrap confidence intervals, and HAC-aware
regressions. Separate contemporaneous price impact from prediction: flow measured during
a bar may predict only returns beginning after that bar closes.

## Stage 3 — Predictive model (blocked until Stage 2 finds stable evidence)

Start with regularized logistic/linear models. Predict whether the future BTC move exceeds
round-trip costs, rather than predicting every bar's sign. Compare BTC-native features
against BTC plus ETH flow features only after the BTC control is frozen. A constrained
nonlinear model is allowed only as a challenger.

## Deferred tracks

The following remain documented but inactive: MA/RSI/ADX models, general breakout tuning,
BTC/ETH candle correlation, news/sentiment modeling, mean reversion, broader crypto pairs,
and agent-generated signals. Lagging indicators remain diagnostic baselines only.

## Safety and reproducibility

Use archived files and isolated research scripts only. Do not connect to, restart, or
modify soak PostgreSQL, NATS, Freqtrade, or their volumes. Every report must identify its
data manifest, code revision, parameters, decision timestamp convention, cost model, and
train/validation/test boundaries.
