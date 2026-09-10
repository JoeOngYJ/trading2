# Strategy Research Standard

**Status:** mandatory research policy  
**Effective:** 2026-08-26  
**Scope:** offline strategy research, backtests, paper observers, and promotion reviews

## Objective

The objective is not to discover the backtest with the largest return. It is to build a
portfolio of independently validated, economically explainable forecasts whose combined
return survives costs, changing regimes, and genuinely unseen data.

```text
point-in-time data -> independent forecasts -> causal validation -> alpha attribution
                   -> cost/risk-aware portfolio -> execution -> paper observation
                   -> small-capital review -> continuous decay monitoring
```

Position sizing can scale an accepted forecast's return and loss. It cannot turn market
beta, selection bias, or an unstable signal into alpha.

## Research lifecycle

### 1. State one falsifiable hypothesis

Freeze the economic mechanism, target horizon, universe, features, label, decision time,
entry/exit convention, parameters, cost scenarios, development period, unseen boundary,
and pass/reject gates under a unique experiment ID. Test one conceptual change at a time.

### 2. Establish the data contract

Inputs must be checksummed, timezone-normalized, validated, and available at the simulated
decision timestamp. Constituents and venue rules must be point-in-time where possible.
Publication time and retrieval time must remain distinct for external events. Missing or
ambiguous inputs fail closed; rolling features reset across gaps.

### 3. Prove causality

Generate signals only from completed information and execute no earlier than the first
eligible subsequent price. Automated lookahead and boundary tests are mandatory. Labels,
normalization statistics, universe selection, and parameter selection may not cross a
train/evaluation boundary.

### 4. Decompose the source of return

Every strategy must compare with:

- flat/no-trade;
- buy-and-hold for the relevant asset or market;
- the same exposure at the same timestamps without the proposed signal; and
- a simple baseline using materially less information.

A cross-sectional selector must additionally compare with:

- the equal-weight eligible universe at identical timestamps and holding periods;
- the equal-weight preselection basket, if a gate creates one;
- BTC-only and ETH-only timestamp-matched controls when researching crypto;
- thousands of deterministic, seeded random selections from the same eligible set; and
- selected assets minus the non-selected eligible assets as a diagnostic spread.

Report market beta and intercept/alpha with uncertainty, the incremental return from the
entry gate, the incremental return from ranking, and the effects of sizing and costs. If
the selector does not beat the matched basket or random-selection distribution after
costs, describe the result as regime timing or market exposure—not selection alpha.

### 5. Validate rather than optimize

Use chronological walk-forward evaluation with embargoes appropriate to the label horizon.
Keep a final period genuinely unseen; if related prior research inspected it, it is not a
holdout. Report bootstrap or comparable uncertainty intervals, leave-one-period-out tests,
parameter perturbations, and sensitivity to universe construction. Account for the number
of hypotheses tried when interpreting the best result.

At minimum, report:

- net return, CAGR, volatility, Sharpe, Sortino, and maximum drawdown;
- turnover, exposure, capacity assumptions, trade/cohort count, win rate, and profit factor;
- fees, spread, slippage, latency, rejected/expired orders, rounding, and unfilled quantity;
- calendar-period and regime attribution;
- top-month and top-trade profit concentration; and
- performance excluding the best periods and under every frozen cost stress.

### 6. Construct a portfolio only after standalone acceptance

Do not combine weak variations of one price trend and call them diversified. Estimate
forecast correlation and group economically related features into one signal family.
Only independently accepted families may enter portfolio research. Portfolio allocation
must consider expected return uncertainty, covariance, turnover, execution cost, capacity,
concentration, and a frozen risk budget.

Potentially distinct crypto families include slower trend, short-horizon reversal,
cross-sectional relative value, taker/order-flow imbalance, volatility, derivatives
basis/funding, and timestamp-safe event information. They are research directions, not
presumed sources of profit.

### 7. Observe forward before promotion

Reproduce the frozen strategy in a live paper observer before allocating capital. Compare
predicted and realized fills, costs, latency, data availability, and signal decay. Promotion
requires a separate reviewed mandate; passing a backtest never authorizes trading.

## Retail adaptation

Do not imitate latency-sensitive institutional market making without the data, queue
position, fees, inventory, and infrastructure required to test it. A small account's useful
advantages are low market impact, the ability to trade limited-capacity ideas, patience,
and the freedom to remain flat. Prefer horizons where public data and conservative fills can
support credible reproduction.

Professional systematic managers describe essentially the same high-level disciplines:
combining forecasts with costs and risks in portfolio construction, emphasizing breadth
and implementation rather than cosmetic indicator changes, and paper-trading after long
simulation. See [Two Sigma's investment process](https://www.twosigma.com/businesses/investment-management/),
[AQR on trend implementation](https://www.aqr.com/insights/research/journal-article/which-trend-is-your-friend),
and [Man AHL's research process](https://www.man.com/sites/default/files/uploads/embed/ahl-landing-page-who-is-ahl-1/index.html).

## Immediate application: multi-asset top-two audit

The next eligible offline experiment for `multi-asset-top2-causal-v1` is a frozen
selection-alpha decomposition—not exposure scaling and not score tuning.

Use identical signal timestamps, eligible rows, next-open fills, 48-hour exits, capital
accounting, and 30/40/80 bps scenarios for:

1. the current ranked top two;
2. equal-weight eligible seven-asset universe;
3. equal-weight gate-qualified top four;
4. BTC only;
5. ETH only;
6. seeded random two-asset selections; and
7. top-two minus eligible remainder as a zero-cost diagnostic spread before a tradable
   long/short implementation is considered.

Freeze random seeds, number of simulations, beta model, confidence method, concentration
thresholds, and acceptance rules before running the comparison. Until the ranked top two
show incremental net performance with adequate uncertainty and concentration results, the
44.04% development return must be treated as an unresolved mixture of regime timing,
crypto beta, and asset selection.
