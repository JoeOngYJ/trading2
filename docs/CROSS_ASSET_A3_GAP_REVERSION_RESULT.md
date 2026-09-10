# A3 Overnight-Gap Reversion Result

Experiment: `cross-asset-a3-overnight-gap-reversion-v2`  
Stage result: **rejected**  
Accepted strategy arms: **0**  
Actionable disposition: `no_trade`

## Frozen mechanism

The experiment faded a local-session open gap only when its absolute size reached at least 0.75
times the past-only median range of the preceding 20 complete sessions and the first completed
session hour reversed rather than continued the gap. The first hour and next-hour entry open both
had to remain on the gap side of the prior eligible-session reference. Entry used the next H1
historical ask for a long or bid for a short; exit occurred two hours later or at a one-median-range
protective stop. Risk was 0.25% of current equity per position, notional was capped at 15%, shared
gross exposure at 70%, and leverage was prohibited.

Before price evaluation, a data-only process copied the immutable inputs into 2010–2021
development and 2022–2025 validation files using only timestamp/date routing. It deserialized no
market value and included no prospective row. The seven-market universe, GBP translation,
historical spread, 0/5/15 bps additional round-trip slippage, controls, four robustness variants,
uncertainty and 17 gates were frozen before the one result run.

## Result

| Partition / cost | Trades | Net return | CAGR | Max drawdown | Profit factor | Sharpe | Mean trade |
|---|---:|---:|---:|---:|---:|---:|---:|
| Development 2010–2021, spread only | 2,530 | -6.42% | -0.56% | 7.12% | 0.87 | -0.82 | -1.66 bps |
| Development, spread + 5 bps | 1,015 | -11.97% | -1.06% | 12.04% | 0.51 | -4.03 | -6.67 bps |
| Validation 2022–2025, spread only | 848 | +2.64% | +0.66% | 1.00% | 1.17 | 0.85 | +2.53 bps |
| Validation, spread + 5 bps | 848 | -3.64% | -0.93% | 4.71% | 0.80 | -1.20 | -2.47 bps |
| Validation, spread + 15 bps | 699 | -12.02% | -3.16% | 12.08% | 0.42 | -4.82 | -12.47 bps |

The spread-only validation result was positive, but the gross mechanism was already negative in
development and a realistic 5 bps slippage allowance erased the validation gain. Only 2022 was
profitable at the primary cost; 2023, 2024 and 2025 lost, with the loss worsening to GBP 445 in
2025. All four predeclared lookback/threshold perturbations lost.

Only NAS100_USD and SPX500_USD were positive. The other five instruments lost, every
leave-one-instrument-out portfolio remained negative, and the US equity pair supplied 100% of
positive instrument PnL. The best three positive months supplied 76.66% of positive monthly PnL.
The month-block 95% interval for mean primary trade was -5.57 to +1.47 bps.

The signal beat the threshold-only fade and timestamp-matched long, short and continuation
directions, and ranked at the 99.56th percentile of random directions. Those controls were more
negative, however; relative superiority does not repair an absolute loss. Twelve of 17 gates
failed.

The mechanism is therefore rejected. It may not be tuned, rerun, restricted post hoc to US
indices, levered, or rescued with a regime layer. No prospective prices were accessed, no strategy
arm was accepted, and A4/A5 remain blocked.

Primary evidence:

- `artifacts/agent-level-experiment/cross-asset/a3-overnight-gap-reversion-v2/evidence-manifest.json`
- `artifacts/agent-level-experiment/cross-asset/a3-timestamp-prepartition-v1/evidence-manifest.json`
- `config/experiments/cross-asset-a3-overnight-gap-reversion-v2.json`
