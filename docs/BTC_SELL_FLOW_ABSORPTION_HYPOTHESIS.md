# BTC Sell-Flow Absorption Hypothesis

Experiment ID: `btc-sell-flow-absorption-v1`  
Status: **frozen before execution; development subsequently rejected**  
Machine-readable contract: [`../config/experiments/btc-sell-flow-absorption-v1.json`](../config/experiments/btc-sell-flow-absorption-v1.json)

## Decision question

Does unusually aggressive BTC spot selling that produces an unusually resilient completed-hour
price response identify passive buyer absorption and a long-only rebound over the next 12 hours
large enough to survive conservative retail execution costs?

This is not another threshold search over the rejected raw-imbalance reversal. The new information
being tested is the **residual price response conditional on contemporaneous taker flow**. It must
add value over an otherwise identical extreme-selling control that omits that residual.

## Frozen causal measurement

Only exact, contiguous UTC hours containing 12 accepted five-minute bars are eligible. At the end
of an eligible hour, the experiment uses the preceding 720 contiguous completed hours from the same
data segment and excludes the current hour from every estimate:

1. Fit an OLS regression with intercept of hourly log return on hourly base-volume taker-flow
   imbalance.
2. Calculate the current price-response residual from that already fitted relationship.
3. Require current imbalance at or below the historical 10th percentile.
4. Require the current residual at or above the historical residual 90th percentile.
5. Require current quote volume at or above the historical 75th percentile.

The decision exists only after the hour closes. Entry is attempted at the next five-minute open,
subject to the frozen scenario's price-protection bound. The position is long BTC or flat, holds for
12 hours at most, and has a 1.5% protective stop resolved conservatively from five-minute OHLC.
No position, feature, label, stop path, or exit may cross a source gap.

## Portfolio and costs

The backtest uses one shared 1,000-USDT research account and allocates 20% of current equity per
entry. It permits one open position and at most one accepted entry per UTC day. The fixed allocation
keeps planned account risk below 0.5% even under the frozen severe 80 bps round-trip cost assumption
before unplanned stop-gap risk.

The required execution scenarios are 30, 40, and 80 bps round trip. Results must distinguish signal
events, price-protection expiries, fills, stop exits, time exits, gross return, modeled friction, and
account return.

## Controls and rejection gates

The primary candidate must beat flat, 20%-allocated BTC buy-and-hold, an extreme-sell-only rule,
a price-only reversal rule, and 5,000 deterministic calendar-month/hour-matched random samples.
Uncertainty is measured with a 10,000-replicate UTC-month block bootstrap.

Every gate in the machine-readable contract is binding. In particular, the primary and severe
cost scenarios must be profitable, the primary mean-trade lower confidence bound must exceed zero,
the candidate must improve on the extreme-sell-only control, at least five calendar years and eight
of twelve frozen perturbations must be positive, and profit may not be concentrated in three months.

The 2026 January-July partition remains sealed unless all development gates pass. A failure closes
this experiment ID and ends threshold variants of aggregate five-minute taker-flow as the active
alpha direction. Aggregate flow may remain a control for the separately frozen L2 workstream.

Development did fail the frozen gates. The immutable interpretation and result are recorded in
[`BTC_SELL_FLOW_ABSORPTION_RESULT.md`](BTC_SELL_FLOW_ABSORPTION_RESULT.md); this contract remains
unchanged as evidence of what was specified before the run.

## Scope boundary

This is isolated offline research. It does not read the active partial order-book capture, contact
PostgreSQL or NATS, use exchange credentials, authorize a live venue, or submit an order. USD/USDT
is the research accounting unit only; the eventual Malaysian execution quote currency remains a
later venue decision.
