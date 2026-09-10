# Multi-Asset Top-Two R0 Alpha Attribution Result

**Experiment:** `multi-asset-top2-alpha-decomposition-r0-v1`  
**Source experiment:** `multi-asset-top2-causal-v1`  
**Frozen:** 2026-08-26, before attribution results were computed  
**Decision:** selection-alpha claim rejected; research-only baseline retained, no promotion

## Outcome

The frozen ranking is promising, but the evidence is not yet strong enough to call it
selection alpha. At the primary 30 bps round-trip cost, the shared-capital ranked top two
returned 44.04%, compared with 19.38% for the gate-qualified top four and 16.61% for the
eligible seven-asset basket. The ranked event return beat 98.94% of 5,000 deterministic
random top-two simulations.

The result still fails the predeclared decision rule. The month-block 95% confidence
interval for ranked-minus-universe return crosses zero, only 48 ranked cohorts filled, the
best three profitable months supply 64.50% of positive monthly PnL, and historical
point-in-time universe membership is unavailable. The gate-timing test also found no
significant advantage over same-month non-signal dates.

This is a rejection of the claim that selection alpha has been established. It is not
evidence that the ranking has no value, and it does not justify tuning, scaling, routing,
paper promotion, or live trading.

## Frozen comparison

Every shared-capital control uses the same frozen midnight signals, 1,000 USDT account,
25% cohort and aggregate gross cap, equal-notional basket, next-15-minute-open entry, and
48-hour next-open exit. The 30/40/80 bps scenarios use the repository execution model.

| Control | 30 bps net return | 30 bps max drawdown | 80 bps net return | 30 bps filled cohorts |
|---|---:|---:|---:|---:|
| Ranked top two | 44.04% | -6.46% | 34.89% | 48 |
| Gate-qualified top four | 19.38% | -5.68% | 12.04% | 48 |
| Eligible universe seven | 16.61% | -5.18% | 9.48% | 48 |
| BTC only at signal timestamps | 0.82% | -5.31% | -5.16% | 49 |
| ETH only at signal timestamps | 4.79% | -4.76% | -1.44% | 49 |
| Eligible remainder | 6.71% | -5.31% | 0.36% | 49 |

The primary ranked control reproduces the earlier 44.04% result. One primary-cost ranked,
top-four, and universe basket expired under the frozen price-protection rule; the paired
statistical diagnostics therefore use all 49 predeclared timestamps with an explicit
next-open friction convention that removes order-expiry and sizing differences.

For context, investing 25% of initial equity in BTC from 2021-01-01 through 2025-12-31
returned 50.53% at primary costs. That is a persistent buy-and-hold exposure with a very
different risk and capital-use profile, so it is a required baseline rather than a claim
that the strategies are directly interchangeable.

## Return attribution

At primary costs, the 49 paired event averages are:

| Attribution component | Mean return per event |
|---|---:|
| Ranked top two | 3.098% |
| Gate-qualified top four | 1.488% |
| Eligible seven | 1.278% |
| Eligible remainder | 0.550% |
| Ranked minus top four | +161.00 bps |
| Ranked minus eligible universe | +181.98 bps |
| Selected minus remainder diagnostic | +254.77 bps |

The ranked-minus-universe calendar-month block-bootstrap interval is **-4.72 to
+412.98 bps** per event at 95% confidence. The point estimate is large, but zero remains
plausible because the sample is sparse and clustered.

The ranked basket is in the 98.94th percentile of 5,000 seeded random top-two paths, with a
one-sided randomization p-value of 0.0108. Selection delta is positive in 2021, 2024, and
2025, but slightly negative in 2022 and 2023. This satisfies the frozen randomization and
three-positive-years gates but not the uncertainty or concentration gates.

An OLS attribution of ranked return on the timestamp-matched eligible-universe return gives:

- beta: 1.82;
- intercept: +76.75 bps per event;
- R-squared: 0.796; and
- month-block 95% intercept interval: -62.83 to +200.50 bps.

Most variation is therefore associated with broad crypto movement at high beta. A positive
residual selection component is possible, but its interval also crosses zero.

## Regime-gate attribution

The eligible-universe basket earned 1.278% per gated event. Across 5,000 simulations that
matched each signal with a non-signal midnight in the same UTC month, the mean was 1.126%.
The gated observation was only at the 59.5th percentile, with one-sided p=0.4051. This
experiment does not establish that the current gate improves entry timing.

This diagnostic matches on calendar month to control broad market era, but it is not a
causal randomized trial and cannot eliminate every conditional difference. The correct
conclusion is “gate value not demonstrated,” not “gate known to have zero value.”

## Frozen acceptance decision

Passed gates:

- positive ranked return at 30 and 80 bps;
- positive ranked-minus-top-four and ranked-minus-universe point estimates;
- seeded random-selection test;
- positive selection delta in at least three calendar years;
- 25% exposure cap, causal timestamps, and sealed-2026 boundary.

Failed gates:

- 48 filled primary cohorts versus the minimum 60;
- month-block selection-delta lower confidence bound above zero;
- regime-gate randomization p-value at or below 0.10;
- top-three profitable-month share at or below 50%; and
- point-in-time universe membership availability.

Because the frozen rule requires every gate to pass, the decision is
`selection_alpha_reject`.

## Implementation and reproducibility

P0 isolation is enforced in code: the runner accepts only the frozen archived data
directory, frozen signal ledger, and an output beneath the isolated experiment root. It
rejects checksum changes, symlinked inputs, 2026 rows, path escapes, non-causal signals,
database/message-bus/network permission in the spec, and overwrite of a non-empty output.
It contains no connector to PostgreSQL, NATS, Freqtrade, an exchange, or the L2 capture.

P1 now has reusable components for:

- arbitrary-leg equal-notional controls through the shared-cash mark-to-market simulator;
- frozen top-two/top-four/universe/BTC/ETH/remainder selectors;
- deterministic random-selection and calendar-matched gate controls;
- paired friction-adjusted event returns;
- month-block bootstrap intervals and OLS beta/intercept attribution;
- concentration, sizing, and cost attribution; and
- checksummed reports, ledgers, distributions, and manifests.

Frozen inputs and acceptance rules are in
`config/experiments/multi-asset-top2-alpha-decomposition-r0-v1.json`. The implementation is
in `src/trading_platform/research_attribution.py` and
`scripts/analyze_multi_asset_top2_alpha.py`. Checksummed outputs are under
`artifacts/agent-level-experiment/multi-asset-top2/alpha-decomposition-r0-v1/`.

## Disposition and next work

Do not modify this experiment ID. Preserve the exact ranked route as a rejected development
benchmark so future research can detect whether a new mechanism adds anything beyond it.
Do not register it as a selectable strategy arm or build a production router around it.

The remaining P1 gaps are data/evidence rather than a reason to tune the score. Enforcement
for point-in-time membership and contamination-aware prospective partitions is now
implemented in `src/trading_platform/research_evidence.py`; the current declaration fails
closed because the required evidence does not exist:

1. acquire or construct defensible point-in-time universe membership and historical venue
   rules for a new experiment ID, using a contemporaneous candidate-selection rule rather
   than merely proving listing status for the post hoc fixed seven;
2. freeze and collect a genuinely prospective period that this strategy family has not
   already influenced;
3. increase independent event count and predeclare concentration handling; and
4. generalize the simulator state into the later central risk-kernel contract without
   changing the frozen R0 result.

Until those gaps are closed, the proper interpretation of the 44.04% development return is
“high-beta crypto timing plus a promising but unproven cross-sectional ranking component.”
