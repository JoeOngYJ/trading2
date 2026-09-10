# BTC/ETH Relative Catch-Up R2 Development Result

**Experiment:** `btc-eth-relative-catchup-r2-v1`  
**Frozen:** 2026-08-26, before execution  
**Decision:** `development_mechanism_reject`  
**Promotion eligible:** no

## Question and frozen mechanism

The experiment tested whether BTC catches up over the next 24 hours after an unusually
negative completed 4-hour BTC return residual versus ETH, conditional on positive ETH
participation and a positive completed BTC/ETH 24-hour context.

ETH was context only. The simulated action remained BTC/USDT spot long or flat under
`retail-btc-spot-v2`: one position, no leverage, and at most 25% of current account equity.
The regression, residual threshold, holding period, controls, costs, sensitivities, seeds,
and gates were frozen in
`config/experiments/btc-eth-relative-catchup-r2-v1.json` before this run.

## Data and causal boundary

The runner used only the checksummed Binance BTC/ETH 15-minute archives from 2021-01-01
through 2025-12-31. Both inputs end before 2026; no 2026 row was read.

- BTC SHA-256: `e1254333eb3ed9e28d268975221f6134988c17577026177f503df012816ed688`
- ETH SHA-256: `44bb979c6e01652ff3a7d563be4480e1766a42b51a038beb23a519137d5079e3`
- rows per pair in development: 175,226
- detected gaps per pair: 7; rolling features reset after every gap
- a 4-hour bar required exactly 16 consecutive UTC-aligned 15-minute rows
- regression coefficients used the previous 180 completed 4-hour returns
- the residual threshold used the previous 180 causal residuals and excluded the current row
- entry was the first 15-minute open after the completed 4-hour bar
- exit was the 15-minute open exactly 24 hours later
- signals crossing any missing 15-minute execution row were rejected

Automated tests alter current and future observations to verify that the current beta,
threshold, and signal cannot use post-decision information.

## Primary result

| Metric | Primary 30 bps | Stress 40 bps | Severe 80 bps |
|---|---:|---:|---:|
| Raw executable signals | 364 | 364 | 364 |
| Filled non-overlapping trades | 254 | 254 | 254 |
| Account net return | **-22.71%** | -27.45% | -43.65% |
| Maximum drawdown | **-24.84%** | -29.28% | -44.57% |
| Profit factor | **0.66** | 0.60 | 0.42 |
| Mean filled-trade allocated return | -39.50 bps | -49.46 bps | -89.18 bps |

Primary-cost calendar returns were negative in four of five years:

| Year | Account return |
|---|---:|
| 2021 | -2.76% |
| 2022 | -12.12% |
| 2023 | +6.16% |
| 2024 | -6.63% |
| 2025 | -8.75% |

For scale, a frozen 25% initial-equity BTC buy-and-hold allocation gained 50.53% at the
same primary cost assumptions. This is a market-exposure baseline, not a risk-matched
claim, but it makes clear that the catch-up rule did not capture the interval's BTC drift.

## Mechanism and control tests

The paired primary event mean after 30 bps round-trip cost was **-34.89 bps**. The frozen
UTC-month block-bootstrap 95% interval was **-63.82 to -8.15 bps**. The interval is wholly
negative, so sampling uncertainty does not rescue the proposed positive catch-up effect.

The same-month random joint-risk-on control averaged -5.76 bps. The proposed signal was
at only the 2.16th percentile of 5,000 seeded draws; its one-sided positive-alpha p-value
was 0.9784. The simpler BTC-only reversal event control averaged +14.98 bps, leaving the
candidate **49.88 bps worse per event**. This specifically rejects incremental information
from the frozen ETH-relative residual condition.

The shared-account BTC-only reversal control was slightly positive (+2.30%) but failed its
own promotion-quality criteria: profit factor was only 1.05, and it was a predeclared
control rather than an independently frozen candidate. It must not be promoted or tuned
from this result.

## Predeclared sensitivities

Every sensitivity lost money at the primary cost:

| Variant | Filled trades | Net return | Max drawdown | Profit factor |
|---|---:|---:|---:|---:|
| beta window 120 | 269 | -24.63% | -25.77% | 0.65 |
| beta window 240 | 242 | -15.03% | -18.84% | 0.76 |
| residual quantile 5% | 152 | -2.10% | -12.01% | 0.95 |
| residual quantile 15% | 337 | -22.36% | -24.89% | 0.73 |
| hold 12 hours | 298 | -20.68% | -21.23% | 0.63 |
| hold 48 hours | 215 | -9.71% | -15.26% | 0.85 |

The less-negative variants are robustness diagnostics, not candidates. Selecting the best
one after inspection would be threshold and horizon optimization and requires a different
economic mechanism, new ID, and new evidence.

## Gate decision

Eleven frozen gates failed: primary and severe return, profit factor, drawdown, event mean,
bootstrap lower bound, matched-random significance, incremental value over BTC-only
reversal, positive-year count, profitable-month concentration, and sensitivity breadth.
Only sample count, exposure cap, causality, and the sealed-2026 boundary passed.

This exact mechanism is closed. Do not tune the beta window, threshold, context, or holding
period under this experiment ID. The result supports the prior warning that strong
contemporaneous BTC/ETH co-movement does not automatically imply a tradable lead/lag or
catch-up forecast.

## Reproduction and evidence

```bash
PYTHONPATH=src python3 scripts/backtest_btc_eth_relative_catchup.py
```

The runner refuses to overwrite an existing result and accepts only the frozen input
directory. Result evidence is under
`artifacts/agent-level-experiment/btc-eth-relative-catchup-r2/development-v1/`:

- `report.json` — result, controls, statistics, gates, limitations, and data quality;
- `signals.csv.gz` — causal primary, control, and sensitivity signal ledger;
- `trades.csv.gz` — shared-account fills and PnL;
- `event_returns.csv.gz` — timestamp-matched paired returns;
- `random_distribution.csv.gz` — seeded same-month null distribution; and
- `manifest.json` — checksums for specifications, code, inputs, and outputs.

These artifacts are development rejection evidence only. The interval and related feature
family were previously inspected, so even a pass would not have been independently
promotion eligible.
