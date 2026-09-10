# BTC Causal CUSUM Trend-Onset TNE1-A v2 Result

Status: **rejected at frozen trigger/count gate; labels and models not opened**  
Experiment: `btc-cusum-trend-onset-tne1-v2`  
Decision: `no_trade`

## Result

The one permitted TNE1-A run completed on the bound 878,985-row BTCUSDT five-minute
2017--2025 development source. It aggregated 73,234 complete one-hour rows and found 229
model-ready, non-overlapping Page-CUSUM triggers. Every trigger was research-only and no
post-trigger return or label was deserialized.

| Frozen gate | Required | Observed | Result |
|---|---:|---:|---|
| Model-ready triggers | 300 | 229 | Fail |
| Triggers before 2021 | 150 | 75 | Fail |
| 2021 triggers | 30 | 29 | Fail |
| 2022 triggers | 30 | 27 | Fail |
| 2023 triggers | 30 | 32 | Pass |
| 2024 triggers | 30 | 34 | Pass |
| 2025 triggers | 30 | 32 | Pass |
| Distinct UTC months | 36 | 93 | Pass |
| Maximum year share | at most 30% | 14.8472% | Pass |
| Top-three-month share | at most 20% | 6.5502% | Pass |

Earlier annual counts were 2017: 9, 2018: 13, 2019: 23 and 2020: 30. The pre-2021 gate
therefore missed by 75 events, not by a rounding or boundary ambiguity. Later prospective
collection cannot change that historical prerequisite. The total count was 76.33% of the
minimum. The sequential detector was more frequent than the prior 92-setup compression
catalogue, but not frequent enough for its frozen nested annual forecast design.

## Disposition

Reject this experiment ID at TNE1-A. Do not lower the Page threshold, shorten the inclusive
72-hour suppression, change the volatility window, weaken annual gates, or materialize labels
under this ID. TNE1-B and TNE2 were not run, so there is no finding about continuation,
reversal, forecast accuracy, strategy return, costs or PnL.

The negative result is primarily a research-design/sample-coverage finding. It does not prove
that distributed positive drift lacks information; it proves that this exact event definition
cannot support the pre-registered evaluation on the available causal Binance history.

## Reproducible evidence

- Contract SHA-256:
  `b66d558c2c9dcad1179ca775e9c7f66fe1f1f42ed6e94ef2d810e3f3dbfa168b`
- Trigger catalogue:
  `artifacts/agent-level-experiment/btc-focused/cusum-trend-onset-v1/tne1-v2/trigger/triggers.jsonl.gz`
  (`cc4ad2f43690a043aa45f20b06df91f88084a384f0ee881f50724125e07ce516`)
- Trigger report:
  `artifacts/agent-level-experiment/btc-focused/cusum-trend-onset-v1/tne1-v2/trigger/trigger-gate-report.json`
  (`d2111cfb101464ee3b76d783c04a9e00520c5ce69f6bcd8dfc9753b29610f917`)
- Evidence manifest:
  `artifacts/agent-level-experiment/btc-focused/cusum-trend-onset-v1/tne1-v2/trigger/evidence-manifest.json`
  (`db916a469e4db16b090243108eaf808adcb94ac7dae764250bf34b608a3dd9e7`)
- Catalogue digest:
  `0c5972dccb5fd9e6605a71690b76056e52e00bafa6663e9d5c2b4c63bdc3b5e8`

Exact completed command:

```bash
.venv/bin/python scripts/run_btc_cusum_trend_catalogue.py \
  --contract research/btc/contracts/btc-cusum-trend-onset-v2.json \
  --experiment-id btc-cusum-trend-onset-tne1-v2 \
  --phase trigger
```

No label or model directory exists. No 2026 strategy row, partial OB0 data, network, database,
NATS, Freqtrade, exchange, protected soak service, production signal, order, position, strategy
cost or PnL was accessed or created. Zero arms remain accepted and `actionable_arm_id` remains
`no_trade`.

Independent audit recomputed all 229 records and the catalogue digest exactly under the
repository `.venv` Python 3.13 environment. System Python 3.10 produced identical IDs, counts and
gate decisions but approximately `1e-15` floating-point differences and therefore a different
record/catalogue digest. This does not affect the rejection. Any successor must bind the exact
interpreter/dependency environment or freeze canonical float quantization before historical
access; the current ID must not be rewritten.
