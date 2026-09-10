# BTC Regime Routing S2 EWMA Benchmark Result

Experiment ID: `btc-regime-routing-s2-ewma-v1`  
Decision: **rejected — insufficient causal risk-estimate coverage**  
Economic scorecard evaluated: **no**  
Live-trading status: **not authorized**  
Promotion evidence: **no**

## Result

The frozen S2 EWMA benchmark failed its first predeclared evaluation gate. The causal estimate
was available for 62 of the 67 locked S1 breakout opportunities, or 92.54%, below the required
95% overall coverage. It also failed the minimum 90% coverage requirement in 2019 and 2021.

| Year | Usable | Locked opportunities | Coverage | Gate |
|---|---:|---:|---:|---|
| 2019 | 5 | 6 | 83.33% | Fail |
| 2020 | 9 | 10 | 90.00% | Pass |
| 2021 | 6 | 8 | 75.00% | Fail |
| 2022 | 8 | 8 | 100.00% | Pass |
| 2023 | 11 | 12 | 91.67% | Pass |
| 2024 | 15 | 15 | 100.00% | Pass |
| 2025 | 8 | 8 | 100.00% | Pass |
| **Overall** | **62** | **67** | **92.54%** | **Fail** |

All five unavailable opportunities had the frozen reason
`insufficient_same_segment_returns`. The estimator correctly reset after source gaps and did
not bridge missing observations. The 30-return initialization was not shortened after observing
the failure.

## Predeclared stop

The runner stopped after writing the causal EWMA and locked-opportunity allocation ledgers. It
did not evaluate:

- one-day or seven-day forecast quality;
- QLIKE or realized-risk quartiles;
- fixed, scaled, exposure-matched or BTC-participation PnL;
- 30/40/80 bps economic comparisons;
- best-month, bootstrap or leave-one-year-out results; or
- the non-selectable decay and target performance diagnostics.

There is therefore no evidence that the EWMA overlay improves or worsens return, drawdown,
Calmar or tail loss. `development_overlay_gate_met` remains false because the economic scorecard
was not reached, not because a PnL comparison failed.

## Frozen implementation

The implementation still provides reusable offline infrastructure for:

- causally indexed daily EWMA forecasts;
- same-segment initialization and stale/unknown handling;
- future-label isolation for standalone forecast diagnostics;
- locked S1 cohort sizing between zero and 10%;
- planned-risk, exposure-matched, bootstrap and path-dependent metric checks; and
- deterministic, checksummed artifacts with no production execution dependency.

It remains bound to the rejected experiment ID and cannot be rerun with a shorter warm-up,
different gap behavior, relaxed coverage threshold, or replacement parameter under this ID.

## Determinism and artifacts

Two isolated executions produced byte-for-byte identical core files:

- `artifacts/agent-level-experiment/btc-regime-routing/s2-ewma-v1/manifest.json`;
- `artifacts/agent-level-experiment/btc-regime-routing/s2-ewma-v1/s2-ewma-report.json`;
- `artifacts/agent-level-experiment/btc-regime-routing/s2-ewma-v1/ewma-observations.jsonl.gz`;
- `artifacts/agent-level-experiment/btc-regime-routing/s2-ewma-v1/opportunity-allocations.jsonl.gz`;
- `artifacts/agent-level-experiment/btc-regime-routing/s2-ewma-v1/determinism-verification.json`.

The replay remains under
`artifacts/agent-level-experiment/btc-regime-routing/replays/s2-replay-TW9Thp/`. It is
verification evidence, not a separate parameter experiment.

## Evidence boundary and safety

Only checksummed S1 development artifacts were consumed. The versioned evidence registry retains
January-July 2026 as `sealed_ineligible`, and the runner did not open it. No partial OB0,
network, exchange, database, NATS, Freqtrade, container, production signal, order-intent or
position path was accessed. Every actionable route remains `no_trade`.

## Decision and next permitted action

S2 is rejected and S3 is blocked because the mandatory simple benchmark was not evaluable under
its frozen coverage standard. Do not tune this S2 ID and do not proceed to the HMM or jump model.
A future S2 attempt requires a new experiment ID and genuinely suitable evidence—for example,
a prospectively collected continuous partition long enough to satisfy the unchanged warm-up and
coverage requirements. The sealed-ineligible 2026 partition cannot be used to repair this result.
