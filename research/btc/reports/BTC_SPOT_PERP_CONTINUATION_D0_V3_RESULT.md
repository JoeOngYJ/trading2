# BTC spot/perpetual continuation D0 v3 result

Experiment: `btc-spot-perp-continuation-d0-v3`  
Candidate reserved: `btc-spot-perp-continuation-information-v1`  
Disposition: **D0 passed; D1 is not frozen or authorized**  
Actionable arm: `no_trade`

## Result

The third, label-blind data qualification passed every frozen gate. It uses official direct daily
BTCUSDT spot and USD-M perpetual klines because the proposed decision clock and cross-market inputs
are daily. This is a data-source result only. No future-return label, forecast, fitted model,
strategy return, PnL, position, order, 2026 row, partial OB0 data, protected service, account, or
credential was accessed or created.

The canonical common history contains 2,307 consecutive UTC days from 2019-09-08 through
2025-12-31 in one segment. Common coverage is 100% in each of 2020–2025. After the frozen 90-day
normalization warm-up, 391 observations are feature-ready before 2021, followed by 365, 365, 365,
366, and 365 observations in 2021–2025. Every evaluation month is represented.

All 148 monthly archives and their official checksum sidecars passed. The one-day REST/archive
overlap and the three-day REST/monthly overlap match exactly. The source and audit replay are
deterministic.

## Preserved predecessors

- D0 v1 remains rejected. Its segmented five-minute-to-hourly spot input had 52 missing or
  cross-segment hours; the mandatory 90-day reset reduced feature-ready coverage below the frozen
  gates.
- D0 v2 remains a failed preflight. Its 76 direct hourly spot archives are preserved, but official
  partial-hour close boundaries violated the frozen parser contract. No audit report was emitted.
- V3 did not relax a gate or repair either predecessor. It changed the input frequency to direct
  daily bars, matching the already planned once-daily decision and 24-hour features.

## Exact evidence

- contract: `research/btc/contracts/btc-spot-perp-continuation-data-audit-v3.json`
- source manifest: `artifacts/agent-level-experiment/btc-focused/spot-perp-continuation-d0-v3/source-manifest.json`
- audit report: `artifacts/agent-level-experiment/btc-focused/spot-perp-continuation-d0-v3/audit-report.json`
- segment report: `artifacts/agent-level-experiment/btc-focused/spot-perp-continuation-d0-v3/segment-report.json`
- evidence manifest: `artifacts/agent-level-experiment/btc-focused/spot-perp-continuation-d0-v3/evidence-manifest.json`

## Reproduction

```bash
.venv/bin/python scripts/acquire_btc_spot_perp_continuation_data_v3.py \
  --output artifacts/agent-level-experiment/btc-focused/spot-perp-continuation-d0-v3
.venv/bin/python scripts/audit_btc_spot_perp_continuation_data_v3.py \
  --output artifacts/agent-level-experiment/btc-focused/spot-perp-continuation-d0-v3
.venv/bin/python -m unittest research.btc.tests.test_spot_perp_continuation_data_v3 -v
```

Re-acquisition is unnecessary while the checksummed raw files remain present. The audit command is
the deterministic offline replay.

## Next permitted action

Freeze D1 before opening any future-return label or fitting any model. D1 must specify the exact
daily close-based spot and perpetual input formulas, basis and relative-turnover transforms,
availability timestamp, raw next-72-hour spot-return target, purged chronological folds, price-only
controls, incremental-information tests, missing-data behavior, uncertainty method, and rejection
gates. D1 is an information test, not a backtest. It may reject the candidate but cannot accept a
strategy arm or create an actionable route.
