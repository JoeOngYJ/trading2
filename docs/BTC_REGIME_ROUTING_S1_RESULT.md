# BTC Regime Routing S1 Ledger and Breakout Reproduction Result

Experiment ID: `btc-regime-routing-s1-ledger-v1`  
Decision: **S1 passed — development reproduction only**  
Live-trading status: **not authorized**  
Promotion evidence: **no**

## Result

The shared offline research ledger reproduced the frozen fixed 20-day/10-day BTC breakout
control exactly on the checksummed 2017–2025 development source. No model was fitted, no
parameter changed, and the sealed 2026 file was not read.

The causal aggregation matched the legacy implementation:

| Item | Result |
|---|---:|
| Valid five-minute rows | 878,985 |
| Source segments | 34 |
| Complete four-hour bars | 18,282 |
| Four-hour discarded boundary rows | 1,449 |
| Complete daily bars | 3,024 |
| Daily discarded boundary rows | 8,073 |
| Raw breakout conditions | 291 |
| Filled trades | 67 |
| Signals blocked while already positioned | 224 |

Every frozen execution result matched exactly:

| Cost scenario | Net account return | CAGR | Maximum drawdown | Calmar | Mean net trade |
|---|---:|---:|---:|---:|---:|
| 30 bps round trip | 16.94% | 2.26% | 5.02% | 0.450 | 239.39 bps |
| 40 bps round trip | 16.14% | 2.16% | 5.14% | 0.420 | 229.15 bps |
| 80 bps round trip | 13.01% | 1.76% | 5.62% | 0.314 | 188.32 bps |

The reproduced 10%-allocation segmented BTC participation control returned 65.36% with an
11.89% maximum drawdown. This preserves the existing attribution warning: the breakout remains
an unresolved timing of BTC directional exposure, not proven independent alpha. S1 did not add
chronological validation, timestamp-matched controls, uncertainty intervals, or promotion gates.

## Causal ledger

The ledger records completed 5m, 4h, and daily candles with UTC observation and availability
times. A 4h bar requires exactly 48 consecutive five-minute children and a daily bar requires
exactly 288. All children must be in one source segment; incomplete or misaligned boundary rows
are explicitly discarded. Derived 4h and daily observations contain only:

- close-to-close log return;
- open-to-close log return; and
- log high-low range.

Close-to-close return is omitted for the first observation after every segment boundary. Each
feature record carries the frozen source checksum and its own deterministic feature checksum.
No rolling volatility, EWMA, HMM, jump state, normalization, or fitted parameter exists in S1.

## Evidence boundary

`config/research/btc-directional-trend-evidence-boundaries-v1.json` records 2017–2025 as
consumed development/reproduction evidence. January–July 2026 is `sealed_ineligible`: no S1
inspection is recorded, but the partition begins without the 336-hour embargo required by the
14-day holding horizon and contains less than the later twelve-month routing minimum. It remains
sealed and cannot be silently relabelled as a clean holdout.

## Determinism and artifacts

Two isolated executions produced byte-for-byte identical core files. The comparison and all
core checksums are in:

- `artifacts/agent-level-experiment/btc-regime-routing/s1-ledger-v1/manifest.json`;
- `artifacts/agent-level-experiment/btc-regime-routing/s1-ledger-v1/determinism-verification.json`;
- `artifacts/agent-level-experiment/btc-regime-routing/s1-ledger-v1/breakout-reproduction-report.json`;
- deterministic 5m, 4h, daily, feature, forecast, and trade JSONL gzip ledgers in the same
  directory.

The second replay remains under
`artifacts/agent-level-experiment/btc-regime-routing/replays/s1-replay-Ilirmk4u/` because the
environment did not permit destructive cleanup. It is isolated evidence, not an additional
experiment.

## Reproduction

```bash
.venv/bin/python scripts/build_btc_regime_research_ledger.py \
  --output-dir artifacts/agent-level-experiment/btc-regime-routing/s1-ledger-v1
```

The runner refuses a non-empty output directory, any input path differing from the frozen
development path, symlinked input, a holdout-like filename, checksum changes, unsafe evidence
boundaries, or any parity mismatch.

## Decision and next action

S1 passes as infrastructure and reproduction only. The breakout arm remains `development`, the
BOCPD-gated breakout remains `rejected`, and every actionable route remains `no_trade`. S2 is
not active. A separate activation must freeze the causal EWMA definition, initialization,
downward-only multiplier, and comparison gates before any S2 evaluation.
