# BTC spot/perpetual continuation D0 v2 result

Audit ID: `btc-spot-perp-continuation-d0-v2`  
Decision: **preflight-invalid; preserve without audit result**  
Actionable arm: `no_trade`

All 76 official direct BTCUSDT spot one-hour monthly archives from September 2019 through
December 2025 and their checksum sidecars downloaded successfully. The frozen audit parser then
stopped on the official 2020-02-19 11:00 UTC bar: its recorded close time was 11:35:32.286 UTC,
not the scheduled end of the hour. Seven other hourly rows use abnormal close-time boundaries,
and the direct series retains 17 open-time discontinuities associated with exchange interruptions.

This is an implementation/source-contract failure, not a data or alpha conclusion. No audit
report was emitted and the parser is not edited under v2. Even accepting exchange-defined partial
hour bars would not solve the intended 90-consecutive-day normalization after genuine hourly
interruptions.

A v3 data-only successor may use direct daily spot and perpetual bars because the proposed D1
decision is daily and its cross-market inputs are 24-hour basis and turnover. Daily realized
volatility, rather than an hourly estimator that repeatedly loses 90 days after maintenance,
must be frozen explicitly in D1 if D0 v3 passes.

No future-return label, feature, forecast, model, strategy, PnL, position, order, 2026 row,
interpolation, partial OB0 data or protected service was accessed or produced.

Preserved source manifest:
`artifacts/agent-level-experiment/btc-focused/spot-perp-continuation-d0-v2/source-manifest.json`.
