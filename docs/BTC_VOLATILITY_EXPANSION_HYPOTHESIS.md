# BTC Volatility-Expansion Continuation Hypothesis

Experiment ID: `btc-volatility-expansion-continuation-v1`  
Status: **frozen before analysis; 2026 holdout locked**  
Machine contract:
[`btc-volatility-expansion-hypothesis.json`](../artifacts/agent-level-experiment/btc-volatility-expansion/btc-volatility-expansion-hypothesis.json)

## Decision being tested

This is the one active slower-strategy hypothesis. It asks whether BTC tends to continue
upward for 24 hours when a strong, buyer-supported 1h expansion follows an objectively
compressed 4h volatility state—and whether that move is still large enough after realistic
retail costs.

This is not a moving-average crossover. MA, RSI, MACD and ADX are excluded as required
inputs because they are transformations of old prices and would add redundant lag. The
model still uses historical observations to estimate a causal state; “no lagging signal”
does not mean “no lookback.” Every input has to exist at decision time, and no input claims
to predict before its source bar closes.

## Exact causal clock

The accepted, checksummed Binance BTCUSDT 5m development archive is the only market input.
An eligible 1h bar contains exactly 12 contiguous UTC-aligned 5m rows; an eligible 4h bar
contains exactly 48. All rows must belong to one accepted data segment. Missing rows,
partial aggregates and cross-gap windows are discarded rather than filled.

The decision occurs after the trigger 1h candle closes. The 4h context is the latest 4h
candle that had already closed by the **open** of that trigger hour. For example, an event
measured from 12:00–13:00 may use a 4h candle ending at 12:00, but never one ending at
16:00. This stricter cutoff prevents the trigger hour from helping classify its own prior
volatility state.

## Frozen event

First calculate 4h close-to-close log returns. The latest 24h realized volatility is the
square root of the sum of squared returns across six completed 4h bars. The market is
compressed when this value is at or below the q20 of the immediately preceding 180 such
observations.

On the completed 1h trigger bar, all of the following must hold:

- log open-to-close return is at least 2.0 robust standard deviations above zero, where
  scale is the prior 168-hour median absolute deviation multiplied by 1.4826;
- log high/low range is at least 2.0 times its prior 168-hour median;
- quote volume is at least 1.5 times its prior 168-hour median;
- the close is in the top 20% of the bar's range;
- aggregate base-volume taker imbalance is positive.

All rolling windows exclude the current bar. Invalid prices, non-positive denominators,
non-finite values or a gap anywhere in a required window produce no event. After an
eligible event, later events are suppressed for 24 completed 1h bars. The primary raw
label is the 24h close-to-close log return. Twelve- and 48-hour labels are diagnostics and
cannot rescue a failed 24h result.

## Frozen trade and risk rules

The strategy is BTCUSDT spot, long or flat, with one position. It attempts a
price-protected taker buy at the first eligible 5m open after the trigger closes. The
entry has a 10 bps protection bound and only that first 5m bar as its deadline; a miss is
recorded and never chased. There is no maker assumption.

The stop sits below the trigger low by 0.25 times the median fractional 1h range over the
prior 168 hours. An entry is rejected if its estimated entry-to-stop distance is below
0.5% or above 5%. Quantity is the smaller of:

1. 25% of current equity divided by estimated entry price; or
2. 0.5% of current equity divided by entry-to-stop distance.

Quantity is rounded down and must pass the frozen venue filters. A stop touched within a
5m bar exits at the stop, or at that bar's open when price gaps below it. Otherwise the
position exits at the first 5m open at or after 24 hours from its first fill. There is no
profit target or trailing stop; adding one would create a different experiment.

At most one entry is allowed per UTC day and four per rolling seven days. A 1.5% UTC-day
loss disables new entries until the next day. A 10% high-water drawdown disables all later
entries pending manual review. Both limits include marked unrealized P&L; neither can
block a protective exit. If a data segment ends while long, the test forces a
protective-cost exit at the final accepted 5m close and includes that result.

## Cost model

The primary result uses `candle-primary-30bps-rt-v1`. The same frozen trades are also
evaluated under the 40 bps stress and 80 bps severe scenarios. The 40 bps case is an
acceptance gate; 80 bps is reported as a severe diagnostic. Fees, implicit spread and
slippage, rounding, rejected orders and missed bounded entries must be attributed through
the shared execution model.

## Development protocol and rejection gates

The 2017–2022 development section is for implementation checks and diagnostics only. The
fixed rule is then confirmed separately in calendar 2023, 2024 and 2025. No threshold is
fitted or selected from those confirmation years.

Every gate below must pass before anyone may unlock 2026:

- at least 30 executed trades in each confirmation year;
- positive raw 24h mean in each confirmation year and at least 45 bps pooled;
- positive mean net trade return and profit factor of at least 1.10 at 30 bps;
- the 95% UTC-day block-bootstrap lower bound for primary net mean is above zero;
- mean net trade return is non-negative at 40 bps;
- maximum drawdown does not exceed 10%;
- no single positive year supplies more than 50% of total positive-year P&L;
- at least seven of ten frozen one-at-a-time threshold perturbations remain positive net
  of the primary costs.

Required reporting includes missed entries, gross/net return, turnover, exposure, trade
count, win rate, profit factor, drawdown, Sharpe/Sortino, component costs, exit reasons,
UTC-year/month attribution, regime attribution and a 10,000-replicate UTC-day bootstrap
with seed 20260825. Benchmarks are flat, buy-and-hold constrained to the same 25% maximum
allocation, and the existing 4h SMA 10/30 lagging control under the same execution model.

Any failed gate rejects this experiment before holdout. It cannot be repaired by changing
thresholds under the same ID. A material change to data, timing, formula, rule, cost,
period or gate requires a new experiment ID.

## Holdout boundary

The January–July 2026 dataset remains sealed. Its manifest and checksum are recorded for
lineage, but its rows were not inspected for this specification. Holdout use requires all
development gates, a checksummed frozen implementation, a checksummed copy of this
contract and passing tests. That permits one run of this exact primary hypothesis. It
does not permit model selection, horizon selection or post-result tuning.
