# BTC strategy-direction tracker

Status: **causal CUSUM trend-onset TNE1-A rejected; labels/models unopened**  
Selected candidate: `btc-cusum-trend-onset-v1`  
Active experiment: none  
Accepted strategy arms: none  
Actionable arm: `no_trade`

## Active successor

The compression catalogue remains preserved but cannot support its model phase. The successor
tested a different mechanism: several positive hourly innovations accumulating through
an online, prior-volatility-normalized Page CUSUM. It uses no compression or range boundary and
one expansion candle could not trigger it. TNE1-A found only 229 model-ready triggers versus 300
required and 75 before 2021 versus 150. It also missed the 2021 and 2022 annual minima. Labels
and models were therefore not opened. Do not tune this ID. The result remains negative evidence
inside the correlated BTC directional-trend family and is not a strategy or PnL finding.

Frozen contract: `research/btc/contracts/btc-cusum-trend-onset-v2.json`. The invalid v1
preflight is preserved and was replaced because its bound-role schema did not match the runner;
no historical row was opened under v1.

## Direction map

| Pattern family | Directional leg | Status |
|---|---|---|
| Range/compression breakout | Upside break, long | **Selected — design only** |
| Range/compression breakout | Downside break, short | Deferred; requires a new short mandate |
| Trend pullback continuation | Uptrend pullback, long | Deferred |
| Trend pullback continuation | Downtrend rally, short | Deferred; requires a new short mandate |
| Consolidation mean reversion | Lower-range fade, long | Deferred |
| Consolidation mean reversion | Upper-range fade, short | Deferred; requires a new short mandate |
| Exhaustion/failed-break reversal | Failed breakdown, long | Deferred |
| Exhaustion/failed-break reversal | Failed upside break, short | Deferred; requires a new short mandate |

Only the first row may receive design work. The table is a research queue, not permission to test
all eight legs or select whichever backtest wins.

## Selected mechanism

The proposed mechanism is not “try another breakout lookback.” A completed period of unusually
low volatility and constrained price range may concentrate latent demand and stop orders. A
causally confirmed break above that completed range may then persist long enough to exceed spot
execution costs.

This candidate remains in the broad `btc_directional_trend` routing family. Even if it eventually
passes, it would not be economically independent from another breakout or moving-average trend
arm.

## Boundary from previous failures

The fixed 20-day/10-day breakout remains a development control and failed its preserved
participation/random-timing evidence. The 4h SMA, BOCPD-gated breakout and volatility-expansion
continuation results remain negative. The new candidate must therefore contain both:

1. a separately frozen pre-break compression state; and
2. a separately frozen upside confirmation after the completed range.

Changing only a lookback, buffer or moving-average speed is prohibited. Rejected condition scores
cannot be used to rescue the candidate.

## Decisions required before any outcome is opened

- Compression measure, duration and past-only reference distribution.
- Range construction and exact upside threshold.
- Confirmation definition, delay and expiry.
- Forecast label and holding horizon.
- First eligible 5m fill after the completed 1h decision candle.
- Protective stop, gap treatment, exit and maximum holding period.
- Signal sizing separated from the frozen EWMA risk comparison.
- Chronological folds, embargo, uncertainty method and deterministic seeds.
- Flat, buy-and-hold, legacy breakout, timestamp/exposure-matched, simple breakout and
  no-confirmation controls.
- Frozen 30/40/80 bps costs, concentration tests and pass/reject gates.

Until those decisions are captured in a new immutable experiment contract, market outcomes and
PnL must not be opened and no runner may be implemented.

## Evidence boundary

BTC price/trend results through 2025 are consumed development evidence. Existing 2026 partitions
remain sealed or ineligible where their contracts say so. A development result can reject the
candidate, but future promotion would require genuinely prospective evidence collected after the
complete contract is frozen.
