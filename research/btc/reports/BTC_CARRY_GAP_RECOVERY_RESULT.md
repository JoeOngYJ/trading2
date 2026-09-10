# BTC carry reference-price gap recovery result

Experiment ID: `btc-carry-gap-recovery-v1`  
Decision: `official_rest_gap_recovery_rejected`  
Actionable arm: `no_trade`

## Outcome

The frozen official REST recovery is rejected because one of 18 exact responses failed. Binance
returned HTTP 200 and an empty JSON list for the missing BTCUSDT premium-index hour at
2020-12-01 23:00 UTC. The response is preserved byte-for-byte with SHA-256
`4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945`.

The other 17 responses passed their exact timestamp and row-quality checks:

| Series | B2 archive rows | Exact rows recovered | Combined rows | Remaining gaps |
|---|---:|---:|---:|---:|
| Mark price | 52,416 | 192 | 52,608 | 0 |
| Index price | 52,320 | 288 | 52,608 | 0 |
| Premium index | 52,439 | 168 | 52,607 | 1 |

All recovered rows are outside the original archive timestamp sets, with zero duplicates and zero
invalid rows. The result therefore repairs mark and index continuity and reduces the premium gap
from 169 hours to one, but it does not pass the predeclared all-series continuity gate. No value
was interpolated, copied from another venue, or reconstructed.

## Meaning

This is a source limitation at one known timestamp, not evidence that carry is unprofitable. No
signal, position, return, PnL or regime state was calculated. B2's rejection remains preserved.
Historical effective-dated fee evidence, effective maintenance-margin brackets and exact account
fees also remain unresolved, so strategy readiness is false independently of this one-hour gap.

A future successor may explicitly treat that hour as unavailable and reset/fail flat across the
segment boundary, but that requires a new contract frozen before any strategy outcome. It may not
silently relax this experiment or impute the missing premium value. The sensible next data task is
to qualify the effective historical fee and margin evidence while preserving the one-hour
unavailable interval; only after those economics are bounded should paired spot/perpetual
accounting or a carry hypothesis be frozen.

## Reproduction

The official output directory is immutable. An isolated replay must use a new empty directory:

```bash
.venv/bin/python -m unittest research.btc.tests.test_carry_gap_recovery -v
.venv/bin/python scripts/recover_btc_carry_gaps.py \
  --output artifacts/agent-level-experiment/btc-focused/replays/carry-gap-recovery-<new-empty-id>
```

Because the source returned an empty exact response, the runner exits with status 2 after writing
the complete raw evidence, source manifest, audit report and evidence manifest.

An isolated replay is stored at
`artifacts/agent-level-experiment/btc-focused/replays/carry-gap-recovery-v1-replay-20260830T2222/`.
Its audit report is byte-identical (SHA-256
`8945f156e398289370580051e2241ffd918e04682411a6d619495ed8029aa31c`) and all 18 raw-response
digests and dispositions match the official run, including the same two-byte empty response.
