# BTC Online-Regime Breakout Development Result

Experiment ID: `btc-online-regime-breakout-v1`  
Decision: **rejected before holdout**  
Evaluation: complete UTC data from 2019-01-01 through 2025-12-31  
Live-trading status: **not authorized**

## Result

The fixed 20-day upside breakout had positive development performance, but the frozen
Bayesian Online Change-Point Detection (BOCPD) positive-drift entry gate made it materially
worse. The gate reduced drawdown, but it discarded too much profitable trend exposure and
failed its standalone forward-information test. Nine of 21 predeclared gates failed, so the
experiment is closed without reading the sealed 2026 partition.

At the primary 30 bps round-trip cost and 10% account allocation:

| Metric | Breakout control | Breakout + BOCPD gate |
|---|---:|---:|
| Filled trades | 67 | 45 |
| Net account return, 2019–2025 | 16.94% | 6.72% |
| CAGR | 2.26% | 0.93% |
| Maximum drawdown | 5.02% | 3.87% |
| Calmar | 0.450 | 0.241 |
| Mean net return per allocated trade | 239.39 bps | 149.91 bps |
| Profit factor | 1.88 | 1.49 |
| Positive calendar years | 5/7 | 4/7 |
| Exposure | 18.72% | 9.82% |

The combined candidate remained positive at the frozen 40 and 80 bps round-trip costs,
returning 6.23% and 4.32%, respectively. That is not sufficient: the incremental regime
claim was the subject of the experiment, and it failed.

## Why the regime claim failed

- BOCPD classified 32.98% of evaluation days as positive, 13.77% as negative, and 53.25%
  as uncertain. Occupancy was within the frozen bounds.
- Of 291 raw breakout conditions, 153 occurred with a positive state. Account/cadence and
  position-overlap rules produced 45 combined fills versus 67 ungated fills.
- Positive states had a **37.60 bps lower** mean next-seven-day log return than non-positive
  states in 348 non-overlapping observations. The month-block 95% interval for the
  difference was −199.72 to +126.06 bps and crossed zero.
- The month-block 95% interval for mean net combined-trade return was −147.25 to +485.60
  bps and also crossed zero.
- The combined result retained only 41% of the breakout control's CAGR and 54% of its
  Calmar. Its top three profitable months supplied 61.97% of all profitable-month PnL.
- All 12 one-factor perturbations had positive account return, but only one improved Calmar
  versus its matched ungated breakout. This supports the breakout family more than the
  frozen regime gate.

The 10%-allocation segmented BTC buy-and-hold diagnostic returned 65.36% with 11.89%
maximum drawdown. It is not directly equivalent to the intermittent strategy, but it makes
the attribution warning explicit: the profitable breakout control is a lower-exposure,
risk-managed form of BTC directional participation, not proven independent alpha.

## Interpretation and next action

This result does **not** reject breakout/trend following as the current research direction.
It rejects this specific daily open-to-close Gaussian BOCPD drift state as a breakout entry
filter. Do not tune its hazard, z-score, run length, channel, stop, or holding period under
this experiment ID, and do not choose the best observed sensitivity.

The useful next hypothesis should remain narrow: independently validate the fixed breakout
control with chronological folds and exposure-matched BTC controls, then test a materially
different, causal regime representation only if it has a clear mechanism. Candidate regime
inputs should first describe trend opportunity or risk—such as volatility state and
drawdown/tail conditions—rather than assume a noisy daily drift estimate forecasts direction.
An LLM remains deferred to a timestamp-safe event-risk veto after a deterministic candidate
passes; it is not a replacement for the failed state model.

## Reproduction and evidence

Run:

```bash
.venv/bin/python scripts/backtest_btc_online_regime_breakout.py \
  --data artifacts/agent-level-experiment/btc-taker-history/validated/BTCUSDT-5m-taker-trade-flow-development-2017-2025-316e5789d4b49f79a0adfdd90f0e98c26dd2658060c49fe2366c91dffa2024e8.csv.gz \
  --manifest artifacts/agent-level-experiment/btc-taker-history/validated/development-2017-2025-manifest.json \
  --contract config/experiments/btc-online-regime-breakout-v1.json \
  --scenario-config config/execution_scenarios.json \
  --output-dir artifacts/agent-level-experiment/btc-online-regime-breakout/development-v1
```

Two clean executions reproduced all four evidence files byte-for-byte. Checksums are stored
in `artifacts/agent-level-experiment/btc-online-regime-breakout/development-v1/manifest.json`.
The primary evidence checksums are:

- `development-report.json`: `22e7b5f9c0c3b109c0f8ace146af11850ddb5b63f66494f92595077cba777d89`
- `primary-trades.csv`: `77a707a08ee124b05069e33f692f1dc0b2639cf915c812ccecc81d5cf3366ff2`
- `regime-states.csv`: `7ebcac249669b763417a68d764d1178477c661defefc120e6b9a9199410053b5`

No network, PostgreSQL, NATS, soak container, partial L2 artifact, or 2026 holdout was read.
