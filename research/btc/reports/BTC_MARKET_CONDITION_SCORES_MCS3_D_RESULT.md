# BTC market-condition scores MCS3-D result

Experiment ID: `btc-market-condition-scores-mcs3-d-v1`  
Decision: **rejected — semivariance forecasting improved, but the scaled VaR/ES tail forecast did not**  
Strategy, position, execution, cost, risk-cap or PnL evidence: **none**  
Accepted strategy arms: **none**  
Actionable arm: `no_trade`

## Frozen question

Does a causal monthly expanding log-HAR forecast of BTC negative semivariance improve next-day
downside-risk prediction over the preceding 22-day mean, and does scaling a 500-observation
historical VaR/ES forecast by that semivariance ratio improve joint tail loss while remaining
calibrated?

The primary horizon was one day. Seven days was diagnostic only. Complete days required 288
contiguous five-minute candles in one source segment plus the contiguous prior close. Model fits
used only targets ending strictly before the monthly cutoff. This was an information experiment,
not a trading strategy or an exposure rule.

## Primary one-day result

The experiment produced 2,111 common candidate/control forecasts across 83 monthly refits.
Overall coverage was 82.59%, and the negative-semivariance component was informative:

- Candidate QLIKE was `-6.769489` versus `-6.609755` for the 22-day-mean benchmark. The
  equal-month QLIKE improvement was `0.174736`, with exact-seed 95% interval
  `[0.112791, 0.248077]`.
- Candidate MSE was `17.54%` lower than the benchmark; the frozen ratio was `0.824609`.
- Realized negative semivariance increased monotonically across all four candidate-risk
  quartiles.

Those successes did not extend to the frozen tail forecast:

- Candidate FZ0 loss was `-2.631575` versus the better benchmark value of `-2.640870`.
  Equal-month FZ0 improvement was `-0.033803`, with interval `[-0.106392, 0.026935]`.
- Candidate pinball loss was `0.003698` versus the better benchmark value of `0.003661`.
- Excluding the candidate's best three FZ0 months left improvement at `-0.058049`.
- Only 2019 and 2022 improved both QLIKE and FZ0, versus five of seven required years. Every
  leave-one-year-out comparison retained positive QLIKE improvement, but only two of seven had
  positive FZ0 improvement, versus six required by the joint stability rule.

VaR and ES calibration themselves passed. Candidate VaR exceedance was 4.50%, with Wilson
interval `[3.70%, 5.47%]`, and the month-block ES-calibration interval
`[-0.000768, 0.000083]` contained zero. Calibration is necessary but does not offset worse
pinball and joint VaR/ES loss.

The corrected per-year coverage gate passed: 2019 coverage was 62.09%, 2021 was 60.55%, and every
other year exceeded 66%. Changing the historical window or coverage gate after seeing this
outcome remains prohibited under this ID.

## Seven-day diagnostic

The diagnostic result had the same shape on 1,968 observations: QLIKE and MSE improved, but FZ0
and pinball worsened. Candidate FZ0 was `-1.732798` versus benchmark `-1.759452`; candidate
pinball was `0.009112` versus benchmark `0.008914`. Its FZ0 month-block interval also crossed
zero. The secondary horizon cannot rescue a failed primary result.

## Interpretation

The log-HAR features contain standalone information about the magnitude of future negative
semivariance. The predeclared square-root scaling of historical VaR and ES does not translate
that information into a better forecast of the full tail-loss distribution. This distinction is
important: forecasting how much intraday negative variation will occur is not the same as
forecasting the next daily loss quantile and expected shortfall.

MCS3-D is therefore rejected in full. Its favorable semivariance component is a post-result
diagnostic inside a failed joint experiment and is not an accepted risk score. Do not map it to a
risk cap, tune the tail scaling, shorten the historical window, or use it to condition or rescue a
strategy under this experiment ID.

## Verification

- Eleven focused synthetic tests cover the exact 288-plus-prior-close construction, gaps and
  segments, valid zero semivariance, causal horizons, strict fit cutoff, quantile ties, tail-score
  domains, independent historical-loss eligibility, exact seeded bootstrap and import isolation.
- The isolated replay produced byte-identical forecast, model, report and evidence-manifest files.
- Thirty-five incomplete or missing daily starts were excluded; no feature or target window was
  allowed to cross a gap or segment.
- A preliminary rejection used feature-eligible sample rows for historical tail losses, which
  incorrectly excluded individually complete losses lacking the 22-day model warmup. It and its
  replay are preserved under explicit `invalid` paths. The final run corrects only that contract-
  implementation mismatch; the frozen hypothesis, data, model, formulas, thresholds, seed and
  gates were unchanged. Two earlier executions also stopped before artifact creation on report-key
  wiring errors.
- No 2026 row, partial OB0 input, network, database, NATS, Freqtrade, exchange, protected service,
  production signal, order, position, cost calculation, allocation, risk cap or PnL was accessed
  or created.

## Next permitted action

MCS3-J jump/change information may be frozen under a new experiment ID. It must distinguish
measuring a completed jump from forecasting a future jump, use a past-only prevalence/intensity
benchmark, and predeclare event labels, probability losses, calibration, coverage and stability
gates before reading outcomes. MCS3-D remains a rejected control.
