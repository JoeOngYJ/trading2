# BTC HAR-RV standalone risk-forecast result

Experiment: `btc-har-rv-risk-forecast-v1`  
Decision: **rejected at the frozen coverage gate; model-quality evidence retained**  
Evidence class: consumed 2019–2025 development only  
Actionable arm: `no_trade`

## Frozen question

Can a causal log-HAR-RV model using completed one-day, five-day and 22-day BTC realized
variance forecast next-one-day and next-seven-day realized variance better than both the
mandatory close-return EWMA and a same-input realized-variance EWMA?

The model used only complete, same-segment five-minute returns. It was refitted at the first UTC
midnight of each month on an expanding window. A training row was unavailable until its complete
future target ended. The three predictors were standardized from past training data, the fixed
ridge penalty was `1e-6`, and past-only smearing and 1st/99th training-target limits converted the
log forecast back to variance. Nothing was selected after observing the result.

## Result

On the 2,011 common one-day rows, HAR mean QLIKE was `-6.173005`, versus `-6.091550` for
the mandatory close-return EWMA and `-6.086221` for the same-input RV EWMA; lower is better.
HAR MSE was `1.28538e-6`, 12.68% below the close EWMA and 27.38% below the RV EWMA. HAR beat
the RV EWMA in every calendar year from 2019 through 2025. The paired UTC-month bootstrap
interval for RV-EWMA-minus-HAR QLIKE was `[0.06253, 0.12323]`.

On 1,921 common seven-day rows, HAR mean QLIKE was `-4.146364`, versus `-4.083522` and
`-4.112323`; HAR MSE was `2.90549e-5`, 11.06% below the close EWMA and 35.60% below the RV
EWMA. Its additional diagnostic month interval was also positive at `[0.01060, 0.09263]`.
Forecast quartiles ordered realized risk correctly at both horizons, all leave-one-year-out
one-day improvements remained positive, and 83 monthly refits completed for each horizon.

## Why the experiment is still rejected

The frozen rule required at least 70% overall common-row coverage and 50% in every calendar year
at both horizons. Overall coverage passed at 78.65% for one day and 75.30% for seven days, but:

- 2021 one-day coverage was 49.59%;
- 2019 seven-day coverage was 49.86%; and
- 2021 seven-day coverage was 41.37%.

The source contained 3,024 valid realized-variance days from 3,058 possible days: two UTC day
starts were absent and 32 days were incomplete or crossed a source segment. Each break invalidates
the following 22-day HAR window and forces the same-input EWMA to rebuild 30 observations, so a
small number of raw gaps creates long forecast outages. Relaxing the threshold now would be
post-result tuning. V1 is therefore closed as a coverage rejection even though every frozen
forecast-quality gate passed.

## Reproducibility and boundary

The isolated replay under
`artifacts/agent-level-experiment/btc-focused/replays/har-rv-risk-forecast-v1-replay-20260831T0230/`
matched all four primary artifact hashes byte-for-byte. No strategy signal, return, PnL,
allocation, risk cap, direction, 2026 row, partial OB0 input, credential, protected service,
paper order or live action was created. The result does not make HAR usable by the fusion policy.

An initial report incorrectly offset the frozen bootstrap seed by horizon. It is retained under
the explicit `invalid-bootstrap-seed-offset` paths and its uncertainty bounds are not evidence.
The corrected run changed only those bounds; forecasts, model snapshots, coverage, QLIKE, MSE and
the rejection reason were identical.

The justified next step is a separately frozen data-only investigation of the 34 invalid daily
RV observations and the long reset windows. Do not change V1's coverage gate, ridge penalty,
features, horizons, clipping, controls or evaluation period.
