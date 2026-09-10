# BTC multidimensional risk foundation result

Experiment ID: `btc-multidimensional-risk-foundation-v1`  
Decision: **passed — offline risk-contract infrastructure only**  
Strategy or risk-model evidence: **none**  
Actionable arm: `no_trade`

## Result

The repository now represents risk as independent target-specific forecasts rather than one
universal bull, bear, sideways or stress label. `RiskForecast` preserves detector identity,
risk axis, daily or four-hour clock, horizon, observed/available/expiry/fit timestamps, forecast
interval, confidence, evidence status, unknown reason and checksummed lineage. `RiskPanel`
rejects future-dependent and duplicate detector/axis/clock/horizon observations.

The separate `RiskCap` and `DownwardOnlyRiskFusionPolicy` contracts preserve the action mapping:

- only `benchmark` or `accepted` detectors can set usable caps;
- a new entry receives the minimum of its requested allocation and every required usable cap;
- an open position receives the minimum of its current allocation and every required usable cap;
- missing, stale, unknown, development or rejected required inputs produce a zero allocation;
- an intratrade decision can never increase the current allocation;
- no automatic re-leveraging, direction change, executable arm or order intent is possible.

The frozen architecture uses a daily slow risk-budget clock and a four-hour shock clock. EWMA
remains the mandatory volatility benchmark. HAR-RV, downside/tail, jump/change and implied-risk
detectors are only planned future experiments; liquidity remains blocked pending independent OB1
acceptance. The rejected BOCPD and Student-t HMM remain closed and were neither changed nor run.

Six focused contract tests pass. Together with the existing routing, EWMA and HMM regression
tests, 34 targeted tests pass. The module uses only the Python standard library and imports no
production signal, execution, database, transport or exchange component.

No strategy, feature fit, forecast result, PnL, 2026 row, partial OB0 data, protected service,
account, order, signal or position was accessed or created.
