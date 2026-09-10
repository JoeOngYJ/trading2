# BTC Taker-Trade-Flow Event Study

## Decision

The extreme-imbalance signal is **not tradable standalone** at the current cost
assumption. It remains a possible conditioning feature, but the 2025 evaluation period
has now been observed and must not be reused as an untouched promotion test.

## Method

- Dataset: accepted BTCUSDT 5m taker-trade-flow, 2024–2025.
- Thresholds: 2024 base-flow-imbalance q05/q95, frozen for 2025.
- Outcomes: post-event close-to-close log returns at 5m, 15m, 1h, and 4h.
- Dependence control: deterministic 2,000-replicate UTC-day block bootstrap.
- Positive continuation means price followed the imbalance direction; negative means reversal.

## Main out-of-sample result

Extreme positive taker imbalance in 2025 was followed by reversal:

| Horizon | Events | Mean return after positive imbalance | 95% block-bootstrap continuation CI |
|---|---:|---:|---:|
| 5m | 8,940 | -0.22 bps | -0.45 to approximately 0.00 bps |
| 15m | 8,940 | -0.90 bps | -1.32 to -0.50 bps |
| 1h | 8,940 | -1.87 bps | -2.95 to -0.80 bps |
| 4h | 8,939 | -1.74 bps | -5.15 to +1.79 bps |

Extreme negative imbalance also leaned toward reversal, but its 2025 confidence
intervals included zero at every horizon. Direction hit rates were below 50%, which is
consistent with exhaustion/reversal rather than continuation.

## Interpretation

The asymmetric short-horizon reversal is statistically interesting, but its average
magnitude is far below the current 24 bps round-trip cost assumption. It cannot justify
a strategy by itself. Bar-aggregated taker flow also cannot reveal within-bar trade
sequencing or true L2 order-book imbalance.

Do not optimize q-levels, holding periods, or filters against the observed 2025 result.
The next hypothesis requires additional historical data and a new untouched evaluation
period. Conditional research may later test whether volume/range shocks isolate larger
events, but only under a newly frozen design.

## Reproduction

Run `scripts/analyze_btc_taker_flow_events.py` with the accepted dataset and manifest.
The machine-readable result is
`artifacts/agent-level-experiment/btc-taker-trade-flow/btc-taker-trade-flow-event-study.json`.
