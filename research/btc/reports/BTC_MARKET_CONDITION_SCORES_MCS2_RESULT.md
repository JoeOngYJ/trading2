# BTC market-condition scores MCS2 result

Experiment ID: `btc-market-condition-scores-mcs2-v1`  
Decision: **passed — synthetic score/primitives infrastructure only**  
Forecast, strategy or PnL evidence: **none**  
Actionable arm: `no_trade`

## Result

MCS2 implemented an immutable, target-specific `MarketConditionScore` with score identity,
independent axis, forecast kind, horizon, fit/observation/availability/expiry timestamps, point and
interval estimates, confidence, evidence status, explicit unknown reason and checksummed lineage.
Probability outputs are constrained to `[0, 1]`; unknown outputs cannot carry numeric estimates.
Only benchmark or accepted evidence can ever report itself eligible for later conditioning.

`MarketConditionScorePanel` sorts and checks scores but exposes no average, vote or universal
regime label. It rejects duplicate score/axis/horizon identities and future-dependent inputs.
Development and rejected scores remain research records, not conditioning evidence.

## Frozen primitives

The new pure functions implement:

- volatility-scaled return and directional efficiency;
- lag-one autocovariance and an overlapping finite-sample variance-ratio diagnostic;
- current displacement standardized only against a preceding reference window;
- realized variance, positive/negative semivariance, finite-sample-adjusted bipower variation,
  non-negative jump variation and jump share;
- mean Amihud price-impact and two-period Corwin–Schultz high-low spread proxies; and
- annualized completed funding, completed short-perpetual funding and instantaneous perpetual
  basis transforms.

These names preserve their limitations. Variance ratio and autocovariance do not establish trend
or reversion. Realized jump variation measures a completed window and does not forecast the next
jump. Amihud and Corwin–Schultz are labelled low-frequency proxies and cannot represent protected
fill cost. Funding and basis transforms are not net carry or strategy PnL.

`completed_field_values` enforces that every input observation is known, in one source segment and
available no later than the decision timestamp before a primitive receives it. Constant,
insufficient, non-finite, non-positive-volume and invalid-price inputs fail closed where the
formula would otherwise be undefined.

## Verification

- Eleven focused synthetic tests pass.
- A second isolated qualification is byte-identical for the report and evidence manifest.
- No candle, trade, funding, feature, label or PnL file was opened.
- No BTC or other market value, randomness, fitted score, threshold, strategy, 2026 row, partial
  OB0 input, protected service, production signal or executable action was used.
- Synthetic qualification report SHA-256:
  `01014659587faa7eccadacf91dad6f0d90a834d083257fe8a6a39a9e441f9661`.
- Evidence manifest SHA-256:
  `6f5f696e1ed426c135f65911d31cd43efe774d0d3357026eff1853c1eca7f6b6`.

## Next permitted action

Freeze MCS3-P before reading any BTC value. Its persistence hypothesis must predeclare the exact
4h, 1d and 7d targets, development chronology, observation and execution-independent target
timestamps, simple lagged-return benchmark, score construction, HAC and month-block inference,
coverage, annual stability and monotonicity gates. It is a standalone information experiment, not
a strategy backtest, and it may not reopen the rejected breakout or moving-average family.

