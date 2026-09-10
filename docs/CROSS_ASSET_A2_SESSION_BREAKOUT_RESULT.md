# A2 Session Breakout Continuation Result

Experiment: `cross-asset-a2-session-breakout-continuation-v1`  
Stage result: **rejected**  
Accepted strategy arms: **0**  
Actionable disposition: `no_trade`

## Frozen hypothesis

The first two completed liquid local-session hours defined an opening range. A close beyond that
range in the next completed hour triggered a long or short entry at the following H1 bid/ask open.
Positions used the opposite opening-range boundary as a protective stop and exited intraday at the
frozen local hour. Risk was 0.25% of current equity per position, notional was capped at 15%, gross
exposure at 70%, and leverage was prohibited.

The seven-instrument universe, exact GBP translation, historical spread, 0/5/15 bps additional
round-trip slippage, shared-capital accounting, controls, bootstrap and rejection gates were frozen
before results. The distinct A3 overnight-gap-reversion hypothesis was also frozen before A2 PnL.

## Result

| Partition / cost | Trades | Net return | CAGR | Max drawdown | Profit factor | Sharpe | Mean trade |
|---|---:|---:|---:|---:|---:|---:|---:|
| Development 2010–2021, spread only | 5,938 | -8.57% | -0.74% | 10.32% | 0.93 | -0.42 | -1.39 bps |
| Development, spread + 5 bps | 1,490 | -11.99% | -1.06% | 12.03% | 0.72 | -2.17 | -6.39 bps |
| Validation 2022–2023, spread only | 1,099 | +2.54% | +1.27% | 3.22% | 1.09 | 0.64 | +2.04 bps |
| Validation, spread + 5 bps | 1,099 | -5.35% | -2.73% | 7.35% | 0.83 | -1.37 | -2.96 bps |
| Validation, spread + 15 bps | 639 | -11.61% | -6.03% | 12.14% | 0.54 | -4.58 | -12.96 bps |

Only NAS100_USD and SPX500_USD had positive primary validation PnL. The other five instruments
lost. The best three profitable months supplied 70.37% of positive monthly PnL, and the month-block
95% interval for the mean primary trade was -6.94 to +0.62 bps. The primary strategy was at the
98.35th percentile of randomized directions only because both directions generally lost; it still
trailed the timestamp-matched always-long control by 0.63 bps per trade. Ten of thirteen gates
failed.

The mechanism is therefore not an accepted trend arm. It is not eligible for parameter tuning,
speed variants, leverage, instrument selection based on these results, a regime overlay, or final
evaluation.

## Boundary integrity finding

The v1 runner decoded a JSONL row before checking whether its timestamp was at or after the 2024
cutoff. It therefore decoded at least one boundary row in each of nine input loads before breaking.
No such row was stored in a session or conversion map, and no 2024–2025 signal, trade, return or
metric was computed. Nevertheless, the evidence manifest's `final_partition_accessed: false` claim
is rejected under the strict repository standard. The 2024–2025 partition is not a pristine
byte-level holdout for this experiment ID and will never be opened for A2.

The frozen A3 economic hypothesis remains prior-to-result evidence, but its original instruction to
reuse A2 partitions is now blocked. Any A3 implementation needs a new experiment ID, source-only
timestamp prepartitioning and genuinely prospective final evidence.

Primary evidence:

- `artifacts/agent-level-experiment/cross-asset/a2-session-breakout-continuation-v1/evidence-manifest.json`
- `artifacts/agent-level-experiment/cross-asset/a2-session-breakout-integrity-review-v1/evidence-manifest.json`
- `config/experiments/cross-asset-a3-overnight-gap-reversion-v1.json`

