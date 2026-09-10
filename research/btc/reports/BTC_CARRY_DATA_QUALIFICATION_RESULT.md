# BTC carry data qualification result

Audit ID: `btc-carry-data-qualification-v1`  
Disposition: **data qualification rejected; strategy readiness blocked**  
Actionable arm: `no_trade`

## Scope and boundary

This B2 audit tested only official/public BTCUSDT spot and USD-M perpetual evidence from
2020-01-01 through 2025-12-31. It computed no return, PnL, position, forecast or order. It used no
credentials, did not access 2026, did not inspect partial OB0 data and did not connect to a soak
service. The B1 delta-neutral mandate therefore remains research-only with zero live capital.

## What passed

- All 360 expected monthly Binance public-data archives and all 360 official checksum sidecars
  were acquired; every archive SHA-256 matches its sidecar.
- The BTCUSDT perpetual execution kline series contains all 52,608 expected hourly rows with no
  gaps, duplicates or invalid rows.
- Funding contains all 6,576 expected scheduled eight-hour events with no gaps, duplicates or
  invalid rows. Official publication timestamps have at most 47 milliseconds of jitter; the
  audit preserves that diagnostic while identifying events by their scheduled time.
- Current public spot and perpetual identity, mark/index and funding-override snapshots validate.

## Why the frozen gate failed

The official monthly archives are individually authentic but not mutually complete:

| Series | Unique hours | Missing hours | Gap blocks |
| --- | ---: | ---: | ---: |
| Perpetual execution klines | 52,608 | 0 | 0 |
| Mark-price klines | 52,416 | 192 | 5 |
| Index-price klines | 52,320 | 288 | 8 |
| Premium-index klines | 52,439 | 169 | 5 |

The report records every exact missing interval. Consequently the series do not meet the frozen
zero-gap, exact-row-count or synchronized-timestamp gates. Rows were not filled, interpolated or
dropped to manufacture a pass.

The strategy-readiness gate also fails independently. Effective-dated historical spot/perpetual
fees, effective-dated historical maintenance-margin brackets and the exact future account fee are
not established. Three official documentation pages returned an AWS WAF challenge to the
archiver. Current rules and the current BTCUSDT funding override are retained only as present-day
snapshots and are not projected backward.

## Interpretation

This is a data-infrastructure rejection, not evidence against delta-neutral carry. The complete
execution-kline and funding series are reusable. The incomplete mark/index/premium series cannot
support a continuous 2020–2025 liquidation-aware carry simulation under this contract, and the
missing economics prevent a strategy test even if those price gaps were recovered.

Do not tune or rerun this audit under the same ID. If the program continues, first freeze a
separate gap-recovery qualification contract limited to the exact reported intervals and official
public REST sources. Historical fee/margin uncertainty must remain an explicit fail-closed mask
or conservative predeclared model in any later strategy contract. No additional paid data is
justified by this result alone.

## Evidence and reproduction

- Frozen contract: `research/btc/contracts/btc-carry-data-qualification-v1.json`
- Source manifest: `artifacts/agent-level-experiment/btc-focused/carry-data-qualification-v1/source-manifest.json`
- Machine audit: `artifacts/agent-level-experiment/btc-focused/carry-data-qualification-v1/audit-report.json`
- Evidence manifest: `artifacts/agent-level-experiment/btc-focused/carry-data-qualification-v1/evidence-manifest.json`

```bash
.venv/bin/python -m unittest research.btc.tests.test_carry_data_acquisition research.btc.tests.test_carry_data_audit
.venv/bin/python scripts/audit_btc_carry_data.py
```
