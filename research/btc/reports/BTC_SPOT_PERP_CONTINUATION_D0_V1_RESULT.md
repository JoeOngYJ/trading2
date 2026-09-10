# BTC spot/perpetual continuation D0 v1 result

Audit ID: `btc-spot-perp-continuation-d0-v1`  
Decision: **rejected at label-blind feature-readiness gates**  
Actionable arm: `no_trade`

## What passed

- The official REST fallback yielded 2,791 hourly BTCUSDT perpetual rows from
  2019-09-08 17:00 UTC through the frozen 2020-01-02 overlap.
- All 72 bound 2020--2025 perpetual monthly sidecars still match; no upstream archive revision
  was detected.
- The REST fallback matches all 24 official daily-archive rows for 2019-12-31 and all 48 bound
  monthly-archive rows for 2020-01-01 through 2020-01-02 exactly.
- Common spot/perpetual hourly coverage over 2020--2025 is 99.9107%; every yearly coverage gate
  passes.

## Why v1 failed

The accepted segmented spot 5-minute ledger produces 52 unavailable or cross-segment hours over
the common boundary and therefore 19 hourly segments. Under the frozen requirement that rolling
features reset after every discontinuity, the 90-consecutive-day warm-up leaves only 65 eligible
pre-2021 decisions, 20 in 2021, 282 in 2022 and 275 in 2023. These fail the frozen minimum of 300
before 2021, 330 in each evaluation year and representation in every evaluation month.

The gate is not relaxed. The source has high average coverage, but isolated gaps destroy long
continuous warm-up windows; average coverage and feature readiness are different requirements.

## Disposition

Preserve v1 as rejected. A separately frozen v2 data-only successor may replace only the spot
input with official direct hourly spot archives, because the candidate uses hourly features and
the direct source can be evaluated without interpolation. All v1 thresholds and the perpetual
sources remain unchanged.

No next-72-hour return, forecast, model, feature value, strategy, PnL, position, order, 2026 row,
partial OB0 data or protected service was accessed or produced.

Evidence:

- `artifacts/agent-level-experiment/btc-focused/spot-perp-continuation-d0-v1/source-manifest.json`
- `artifacts/agent-level-experiment/btc-focused/spot-perp-continuation-d0-v1/audit-report.json`
- `artifacts/agent-level-experiment/btc-focused/spot-perp-continuation-d0-v1/segment-report.json`
- `artifacts/agent-level-experiment/btc-focused/spot-perp-continuation-d0-v1/evidence-manifest.json`
