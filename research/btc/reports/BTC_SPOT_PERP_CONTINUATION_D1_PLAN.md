# BTC spot/perpetual continuation D1 implementation plan

Experiment ID: `btc-spot-perp-continuation-information-d1-v1`  
Candidate ID: `btc-spot-perp-continuation-information-v1`  
Stage: D1 incremental information test  
Actionable arm: `no_trade`

## Frozen question

At 00:05 UTC, after controlling for BTC's completed spot return, realized volatility and spot
turnover, do completed daily perpetual-basis changes and spot-versus-perpetual turnover add stable
information about the raw next-72-hour BTC spot log return?

This is not a strategy, regime, execution or PnL experiment. Perpetual data is input-only. All
history through 2025 is consumed development evidence, and no 2026 timestamp may be read.

## Observation clock and target

For a UTC day whose direct daily bar opens at `t`, the spot and perpetual bars are observed when
they complete at `t + 24h`. Their conservative availability and the forecast decision are both
`t + 24h + 5m`.

The target is `log(spot_open(decision + 72h) / spot_open(decision))`, using exact five-minute
opens from the bound segmented spot ledger. Both opens must exist, share a source segment and be
strictly before 2026. The target becomes available at its ending five-minute open. A missing open,
segment crossing or non-finite price makes the row ineligible; nothing is interpolated.

## Frozen features

Let `S_t`, `F_t`, `QS_t` and `QF_t` be the completed daily spot close, perpetual close, spot quote
turnover and perpetual quote turnover. Define:

- `r72_t = log(S_t / S_(t-3))`;
- `rv7_t = sqrt(sum(i=0..6, log(S_(t-i) / S_(t-i-1))^2))`;
- `basis_t = log(F_t / S_t)`;
- `basis_impulse_t = basis_t - basis_(t-1)`;
- `log_spot_turnover_t = log(QS_t)`;
- `log_perpetual_turnover_t = log(QF_t)`.

Every raw series is scaled causally against its preceding 90 valid daily observations, excluding
the current value. The centre is the median; scale is `1.4826 * median(abs(x - median(x)))`.
Zero/non-finite scale makes the observation unknown. Each robust z-score is clipped to `[-5, 5]`.

M0 contains exactly:

- `lagged_72h_spot_return_z`;
- `log_spot_rv7_z`;
- `spot_turnover_z`.

M1 adds exactly:

- `basis_impulse_z`;
- `spot_minus_perpetual_turnover_z = spot_turnover_z - perpetual_turnover_z`.

The expected coefficient sign is positive for both added features. No basis level, funding, open
interest, liquidation, news, interaction, threshold, alternative window or alternative horizon is
permitted.

## Frozen models and chronology

- B0: expanding arithmetic mean of eligible raw 72-hour labels.
- M0: expanding OLS with intercept and the three M0 controls.
- M1: expanding OLS with intercept, the M0 controls and the two added features.
- Fit schedule: first eligible decision of each UTC calendar month.
- Training eligibility: target availability strictly earlier than the fit cutoff.
- Minimum training observations: 300.
- Evaluation decisions: 2021-01-01 00:05 UTC through the last decision whose target ends before
  2026.
- No parameter, model, feature, horizon or sign selection occurs.

Feature and label values are rounded to 12 decimal places before canonical serialization and are
reloaded from their ledgers for fitting. The frozen environment is CPython 3.13.14, NumPy 2.5.2,
float64 and single-thread numeric libraries.

## Sequential gates

### D1-A — synthetic qualification

Implement the offline module and phase runner, then test timestamp, gap, robust-scaling, exact
target-open, segment, fit-cutoff, OLS, bootstrap, deterministic-gzip and prohibited-import rules.

### D1-B — feature-only preflight

Feature mode may open only D0 daily source evidence. It must emit no label, target, forecast,
coefficient, strategy or PnL field/file. Required gates are one common segment, at least 300
feature rows before 2021, at least 340 in every 2021--2025 year, at least 98% overall evaluation
coverage, every evaluation month present and zero invalid causal rows.

### D1-C — label qualification

Only a passing feature report permits the bound five-minute ledger to open. Required gates are at
least 300 training labels before 2021, at least 1,700 evaluation labels, at least 340 in every
2021--2025 year, at least 98% overall and 95% per-year coverage against target-eligible feature
decisions, zero 2026 timestamps and zero segment-crossing labels.

### D1-D — one walk-forward evaluation

Only a passing label report permits B0/M0/M1 fitting. Required gates are:

- M1 MSE strictly below B0 and M0;
- M1 relative MSE improvement over M0 at least 0.5%;
- the 95% lower bound for mean M0-minus-M1 squared-error improvement strictly above zero;
- the 95% lower bound for Spearman rank correlation between `M1 - M0` and the M0 residual
  strictly above zero;
- positive M1-versus-M0 MSE improvement in at least four of five evaluation years;
- no evaluation year worse than M0 by more than 2%;
- aggregate improvement positive after excluding each evaluation year separately;
- aggregate improvement positive after excluding the best three months;
- positive median coefficients for both added features and each positive in at least 60% of
  monthly refits;
- at least 9,500 valid replications from 10,000 deterministic non-circular three-month moving-
  block bootstrap samples, using PCG64 seed `20260901` jointly for the named statistics.

MAE, causal training-score quintiles, top-minus-bottom M0 residual and coefficient paths are
reported as diagnostics only. They cannot rescue a failed primary gate.

## Disposition

Any failed frozen gate rejects and closes this D1 ID without tuning. A complete pass permits only
a separately frozen D2 offline spot long/flat strategy-design experiment. It does not accept a
strategy arm, establish profitability, create a position or authorize routing. D2 would have to
freeze forecast-to-position mapping, exits, five-minute execution, 30/40/80-bps costs, EWMA sizing
comparison and prospective-evidence requirements before any strategy backtest.
