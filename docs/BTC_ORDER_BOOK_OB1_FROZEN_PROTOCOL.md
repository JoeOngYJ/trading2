# BTC Order-Book OB1 Frozen Protocol

Frozen: 2026-08-25, before completion or predictive inspection of the seven-day OB0
capture.

## Purpose and scope

This protocol tests whether Binance BTCUSDT spot L2 information adds short-horizon
predictive information beyond signed trades. It does not authorize strategy promotion,
live orders, or joins to the sealed January–July 2026 kline holdout.

The active seven-day OB0 capture is pipeline validation only. It cannot be used to fit a
model, choose a threshold, compare feature profitability, or change this protocol based
on predictive results.

## Dataset boundary

- Use only intervals accepted by the deterministic L2 replayer.
- Require at least 60 accepted calendar days for development.
- Acquire and seal a later contiguous 30-day test period before development results are
  reviewed for promotion.
- The first 60 accepted days are development; the following 30 accepted days are sealed
  test. Missing/rejected time does not count as an accepted day.
- Provider data may accelerate acquisition only if it passes the identical raw-message,
  timestamp, sequence, snapshot, checksum, and replay contract.

## Timestamp and sampling convention

- Decisions occur once per second on a UTC grid.
- A decision may use only events whose **local receipt timestamp** is no later than that
  grid point. Exchange event time is audit metadata, not an availability timestamp.
- Never carry a book across an update gap, reconnect, rejected interval, or stale-book
  boundary.
- Discard a decision if the most recent accepted depth event is older than 500 ms.
- Do not create multiple observations from repeated exchange updates inside the same
  one-second decision interval.

## Frozen predictors

Primary L2 feature set:

1. latest top-of-book queue imbalance;
2. sum of Cont-style L1 OFI received during the trailing one second;
3. latest microprice-minus-mid displacement normalized by spread.

Required signed-trade control:

- signed aggregate-trade quote quantity received during the trailing one second;
- trade count and absolute traded quote quantity over the same window;
- trailing one-second return.

State controls:

- spread, L1 total depth, event rate, stale-book age, and trailing ten-second realized
  volatility.

Depth imbalance at L5/L10 and additions/removals are secondary diagnostics. They cannot
replace the primary result or rescue a failed primary hypothesis.

## Frozen target

The primary target is the log mid-price return over five seconds, beginning after a
250 ms decision-to-arrival delay:

`log(mid(t + 5.25 s) / mid(t + 0.25 s))`

Secondary sensitivity horizons are 1, 2, and 10 seconds. Secondary latency assumptions
are 100, 500, and 1,000 ms. They must all be reported and cannot be used to relabel a
failed primary test as successful.

Next-tick direction and contemporaneous return are descriptive diagnostics only.

## Models and comparison

Fit these models in order:

1. training-mean/null forecast;
2. regularized linear and logistic signed-trade control models;
3. the same models with the primary L2 feature set added.

Standardization is fitted on training data only. The fixed regularization grid is
`{0.01, 0.1, 1, 10}` and is selected using chronological inner validation. No nonlinear
model, feature search, interaction search, or threshold trading rule is allowed in the
primary experiment.

## Walk-forward design

- Development days 1–30 initialize training.
- Validate on days 31–37, 38–44, 45–51, and 52–58 using an expanding training window.
- Days 59–60 are included in the final development fit after diagnostics are frozen.
- Purge ten seconds before and after every fold boundary.
- Bootstrap whole UTC days, not individual one-second rows; report 95% moving-block
  confidence intervals and per-day distributions.
- Open the 30-day sealed test once, after code, features, costs, and model settings are
  checksummed and frozen.

## Decision gates

The L2 information gate passes only if:

- incremental primary out-of-sample R-squared versus the signed-trade control is positive;
- the day-block bootstrap 95% lower confidence bound for the incremental primary metric
  is above zero;
- the incremental result is positive in at least three of four development folds;
- it is not attributable to one UTC day, one spread state, or stale/high-latency records;
- calibration/log-loss results do not contradict the return-regression conclusion.

A passed information gate is not yet a trading strategy. Stage OB3 must separately use
contemporaneous bid/ask execution, observed depth, and 100/250/500/1,000 ms latency. A
standalone taker strategy must remain positive after observed spread plus 10, 20, and 30
bps round-trip cost scenarios; failure at the 20 bps primary scenario rejects standalone
use. Evaluation as an entry/adverse-selection filter for a slower strategy remains a
separate, later pre-registration.

## Prohibited changes before sealed evaluation

- adding news, ETH, derivatives, cross-venue books, technical indicators, or agent output;
- selecting only profitable hours, volatility regimes, horizons, or imbalance tails;
- analyzing OB0 partial data for direction or profitability;
- changing the decision grid, primary horizon, primary latency, cost gate, or acceptance
  rule after viewing development results without creating a new experiment ID and a new
  untouched dataset.
