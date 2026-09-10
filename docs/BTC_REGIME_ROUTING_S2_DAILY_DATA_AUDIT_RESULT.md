# BTC Regime Routing S2 Daily-Data Audit Result

Audit ID: `btc-regime-routing-s2-daily-data-audit-v1`  
Decision: **rejected under the frozen exact-OHLC reconciliation gate**  
EWMA forecasts or strategy PnL evaluated: **no**  
Live-trading status: **not authorized**

## Result

The data-only audit downloaded all 101 official Binance BTCUSDT monthly daily-kline archives
from August 2017 through December 2025 and verified every archive against its official checksum
sidecar. The direct source contains exactly 3,059 ordered UTC daily bars with no missing day,
duplicate, or boundary crossing.

The source resolves the original S2 coverage problem at the interval actually required by the
EWMA. Each of the five previously unavailable observation times exists and has substantially
more than the required 30 consecutive completed daily returns:

| Observation available at | Consecutive direct-daily returns |
|---|---:|
| 2019-04-01 00:00 UTC | 591 |
| 2020-07-23 00:00 UTC | 1,070 |
| 2021-09-03 00:00 UTC | 1,477 |
| 2021-10-19 00:00 UTC | 1,523 |
| 2023-04-14 00:00 UTC | 2,065 |

The strict audit still rejects the source because its frozen gate required exact open, high,
low, and close agreement with every overlapping complete S1 daily bar. Across all 3,024
overlapping days, every close, high, and low matched, but three early daily opens differed:

| UTC day | Official 1d open | Aggregated official 5m open |
|---|---:|---:|
| 2017-08-20 | 4,120.98 | 4,139.98 |
| 2017-09-04 | 4,505.00 | 4,509.08 |
| 2017-10-20 | 5,683.31 | 5,683.90 |

The underlying official five-minute archives contain 288 valid aligned rows on each of these
days, and their first five-minute opens equal S1. The discrepancy is therefore between
Binance's official interval archives, not an S1 aggregation error. Nineteen overlapping days
also have volume differences above the diagnostic tolerance, further demonstrating that the
official daily archives are not exact resamplings of the published five-minute archives.

The direct source contains 35 days that S1 could not aggregate because S1 correctly discarded
partial days at five-minute segment boundaries. It contains no missing S1 day.

## Interpretation

This result does not support tuning or accepting `btc-regime-routing-s2-ewma-v1`; that
experiment remains rejected. It does show that the coverage failure is specific to deriving a
daily risk input from a segmented five-minute ledger. A continuous official daily close series
exists, all overlapping closes reconcile, and the five affected decisions have ample causal
daily history.

Because the frozen audit required all OHLC fields, this audit ID cannot be relabelled as passed.
A future attempt requires a new contract. The defensible successor would be explicitly
**close-only**, because the EWMA consumes only close-to-close returns. It should retain the
unchanged lambda, 30-return initialization, target, opportunity path, coverage thresholds,
economic gates, and costs. It must disclose the official cross-interval inconsistencies and
remain development/control evidence rather than promotion evidence.

No close-only successor is activated by this audit. S3 remains blocked, 2026 remains sealed,
and every actionable route remains `no_trade`.

## Evidence

- Frozen contract:
  `config/experiments/btc-regime-routing-s2-daily-data-audit-v1.json`
- Source manifest:
  `artifacts/agent-level-experiment/btc-regime-routing/s2-daily-data-audit-v1/source-manifest.json`
- Deterministic direct-daily ledger:
  `artifacts/agent-level-experiment/btc-regime-routing/s2-daily-data-audit-v1/btc-usdt-direct-1d-development-2017-2025.jsonl.gz`
- Audit report and manifest:
  `artifacts/agent-level-experiment/btc-regime-routing/s2-daily-data-audit-v1/daily-data-audit-report.json`
  and
  `artifacts/agent-level-experiment/btc-regime-routing/s2-daily-data-audit-v1/manifest.json`

No sealed-2026 data, partial L2 data, database, message bus, Freqtrade, container, running
service, production signal, order intent, position, EWMA forecast, or strategy return was read
or produced.
