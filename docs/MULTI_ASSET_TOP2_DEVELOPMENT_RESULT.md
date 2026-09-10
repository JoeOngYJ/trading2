# Multi-Asset Top-Two Causal Development Result

**Experiment:** `multi-asset-top2-causal-v1`  
**Development period:** 2021-01-01 through 2025-12-31 UTC  
**Decision:** development candidate found; no paper/live promotion

## What was tested

This is an independent reconstruction of the strongest causal idea found in
`/home/joe/Desktop/Algo_trading/crypto-research-freqtrade`. It does not reuse the
earlier additive-return accounting.

At a completed 15-minute candle on the four-hour UTC grid, the experiment:

1. requires the frozen broad risk-on, near-20-day-high, and BTC-anchor gates;
2. ranks BTC, ETH, SOL, XRP, BNB, DOGE, and ADA using only information available at
   the decision timestamp;
3. selects the strongest two assets;
4. enters at the next 15-minute open;
5. exits after 48 hours; and
6. optionally sells half after a completed 12-hour observation when the basket is
   non-positive and neither leg demonstrated strong first-four-hour follow-through.

The account starts with 1,000 USDT. All overlapping cohorts share one cash account.
New allocations are capped so aggregate entry exposure cannot exceed 25%. This removes
the hidden leverage created when overlapping 48-hour event returns are simply summed.

## Primary development results

Results use the shared `candle-primary-30bps-rt-v1` execution scenario.

| Variant | Net return | CAGR | Max drawdown | Profit factor | Daily Sharpe | Cohorts | Positive years |
|---|---:|---:|---:|---:|---:|---:|---:|
| Four-hour cohort, hold 48h | 16.91% | 3.17% | -1.80% | 2.54 | 1.32 | 292 | 5/5 |
| Four-hour cohort, 12h half-reduction | 8.89% | 1.72% | -5.09% | 1.56 | 0.70 | 292 | 3/5 |
| Midnight UTC control, hold 48h | 44.04% | 7.57% | -6.46% | 2.72 | 1.04 | 48 | 5/5 |
| Midnight UTC control, 12h half-reduction | 40.63% | 7.06% | -5.91% | 2.65 | 1.00 | 48 | 5/5 |

The 12-hour overlay does not dominate the simple hold. In the four-hour schedule it
loses 8.02 percentage points of return and makes drawdown 3.29 percentage points worse.
It also creates 17 rejected reductions because half of a small retail cohort can fall
below the generic minimum-notional rule. The overlay is rejected for the next stage.

## Cost stress

The simpler hold variants remain positive at every frozen cost level.

| Scenario | Four-hour hold | Midnight hold |
|---|---:|---:|
| 30 bps round trip | 16.91% | 44.04% |
| 40 bps round trip | 17.20% | 41.80% |
| 80 bps round trip | 14.26% | 34.89% |

The four-hour 40 bps result is slightly higher than its 30 bps result because the
40 bps scenario permits a wider protected entry: it fills seven baskets that expire
under the 10 bps primary price-protection limit. It is not evidence that higher costs
improve the strategy.

## Reproduction and causality checks

- Seven source files were copied into an isolated research directory and checksummed.
- Invalid OHLCV, duplicate timestamps, and off-grid timestamps fail closed.
- Rolling features reset after missing-candle gaps rather than bridging them.
- The signal candle must complete before the entry timestamp.
- The 12-hour observation can only execute at the following 15-minute open.
- No 2026 row was loaded into the feature or execution path.
- The final signal and cohort ledgers were reproduced byte-for-byte after a
  reporting-only correction.
- A diagnostic comparison with the earlier repository found 280 shared signal
  timestamps through 2025; all 280 selected the same top-two pairs. The stricter
  gap handling produces 299 signals here versus 430 in the earlier artifact.

Checksummed evidence is under
`artifacts/agent-level-experiment/multi-asset-top2/development-v1/`.

## Limitations and decision

The result is promising but is not independent proof:

- The strategy family was selected after inspecting the same historical era in the
  earlier repository. The nominal 2026 partition is also not a clean holdout for this
  family because the earlier research used data through May 2026.
- The best three profitable months contribute approximately 62.9% of positive PnL for
  the four-hour hold and 64.5% for the midnight hold. This exceeds the preferred 50%
  concentration threshold.
- The midnight control has only 48 filled cohorts across five years.
- Generic research tick, lot-size, and minimum-notional rules are used for non-BTC
  assets because historical exchange-rule snapshots are unavailable.
- Candle data cannot verify intrabar liquidity, partial fills, or queue position.
- Both variants trade two assets and therefore violate the frozen BTC-only mandate.
  The four-hour version also violates its entry-frequency limit.

The result supports the cross-sectional top-two entry idea, but not the old +305%
headline and not the 12-hour half-reduction. The next eligible experiment is the
predeclared midnight-UTC hold-only route, tested with frozen parameters on genuinely
forward data and paper-observed costs. Advancing it requires a new multi-asset research
mandate; the current BTC-only mandate must not be silently widened.

