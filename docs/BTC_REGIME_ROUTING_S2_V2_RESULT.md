# BTC Regime Routing S2-v2 EWMA Benchmark Result

Experiment ID: `btc-regime-routing-s2-ewma-v2`  
Decision: **passed — mandatory benchmark frozen**  
Development overlay gate: **passed**  
Promotion evidence: **no**  
Live-trading status: **not authorized**

## Result

S2-v2 completed the evaluation that S2-v1 could not reach. The only conceptual change was the
predeclared use of the independently checksummed official daily close ledger for risk returns.
The lambda, 30-return initialization, 40% target, 10% allocation ceiling, locked 67-opportunity
breakout path, costs, controls, statistics, coverage thresholds and economic gates remained
unchanged.

The causal risk estimate was available for all 67 locked opportunities and every calendar year
reached 100% coverage. The fixed breakout reproduced S1 exactly at all three cost levels.

## Standalone forecast evidence

| Horizon | Valid labels | EWMA QLIKE | Expanding control QLIKE | Correlation with realized variance |
|---|---:|---:|---:|---:|
| 1 day | 2,535 | -5.9145 | -5.6846 | 0.4008 |
| 7 days | 2,402 | -3.8454 | -3.7447 | 0.3591 |

Lower QLIKE is better. EWMA also had lower mean-squared forecast error at both horizons. The
realized variance increased monotonically across the four one-day predicted-risk quartiles.
Labels crossing a five-minute execution-data gap or the development boundary were excluded;
future labels never affected allocation.

## Locked breakout comparison

| Round-trip cost | Allocation | Net return | CAGR | Maximum drawdown | Calmar | Worst rolling 90d |
|---|---|---:|---:|---:|---:|---:|
| 30 bps | Fixed 10% | 16.94% | 2.26% | 5.02% | 0.450 | -2.54% |
| 30 bps | EWMA scaled | 18.75% | 2.48% | 3.28% | 0.758 | -2.00% |
| 40 bps | Fixed 10% | 16.14% | 2.16% | 5.14% | 0.420 | -2.58% |
| 40 bps | EWMA scaled | 18.11% | 2.41% | 3.36% | 0.716 | -2.04% |
| 80 bps | Fixed 10% | 13.01% | 1.76% | 5.62% | 0.314 | -2.75% |
| 80 bps | EWMA scaled | 15.61% | 2.09% | 3.68% | 0.569 | -2.17% |

The capital-time matched constant allocation was 8.47%. It returned 14.24% at 30 bps and
10.98% at 80 bps, with Calmar values of 0.449 and 0.313. The EWMA path therefore beat both the
fixed 10% path and the lower constant-exposure control in this consumed development sample;
the result is not explained solely by taking less exposure.

Every predeclared 30 and 80 bps return-retention, Calmar, tail-loss, positive-return and
best-three-month-neutralization gate passed. Planned risk at the maximum 10% allocation remained
within 0.5% under all costs. The one-at-a-time lambda and target variants were reported but were
not eligible to replace the frozen primary configuration.

## Uncertainty and interpretation

The paired month-bootstrap 95% intervals for the EWMA-minus-fixed monthly return difference were
`[-0.0172%, 0.0520%]` at 30 bps and `[-0.0092%, 0.0629%]` at 80 bps. Both include zero. The
predeclared development overlay gate did not require a positive bootstrap lower bound, so the
gate passes, but the incremental return estimate remains statistically uncertain.

S2-v2 establishes the simple continuous risk benchmark required for later comparisons. It does
not independently validate or promote the breakout, convert development evidence into a
holdout, or authorize trading. The official 1d/5m open and volume discrepancies found by the
preceding audit remain disclosed; the risk model consumes only reconciled close values.

## Determinism and safety

An isolated replay under
`artifacts/agent-level-experiment/btc-regime-routing/replays/s2-v2-replay-EEZVFP/` produced
byte-for-byte identical observations, allocations, trades, report and manifest. Evidence is
stored under `artifacts/agent-level-experiment/btc-regime-routing/s2-ewma-v2/`.

No sealed-2026 data, partial L2 data, database, NATS, Freqtrade, container, running service,
production signal, order intent or position path was accessed. Every actionable route remains
`no_trade`; no HMM or jump model was fitted.

## Next permitted action

S2 is passed and frozen. S3 may be planned under a separate request using EWMA as its mandatory
control. Do not alter or select among the S2 variants, and do not treat these consumed-development
results as promotion evidence.
