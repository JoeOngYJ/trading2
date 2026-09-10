# Accounting reconciles; execution corrections are required

R1-v3 numeric domain (32 total/24 fractional digits, Decimal precision128) passed independent
review and exact-rational synthetic tests. R2-v2 replay retained source quantities and prices
without rounding and kept all original tolerances and costs. Every one of 201 archived trade
records reconciled, with 67 trades per cost scenario and 335 cash/carryforward comparisons each.

| Legacy scenario | Terminal cash from 1000 | Reproduced net return | Maximum absolute cash/PnL discrepancy |
|---|---:|---:|---:|
| 30 bps | 1169.35547137415345 | 16.935547% | 7.242e-13 USDT |
| 40 bps | 1161.39102227246228 | 16.139102% | 5.566e-13 USDT |
| 80 bps | 1130.14101538893713 | 13.014102% | 6.247e-13 USDT |

These reproduce archived fixed-breakout accounting for consumed 2019–2025 evaluation. They do
not validate fills, execution timing or strategy alpha. Relative-error gates use the frozen
absolute-plus-relative tolerance; all comparisons passed and Fraction event balances matched
exactly. Precision was an interface limitation, not a material source of return differences.

All exact per-trade differences are retained as compressed JSON in
`research/btc/reports/btc-r2-v2-reconciliation-result.json`: decode base64, decompress zlib,
verify `payload_sha256`, then parse UTF-8 JSON. The wrapper contains a readable scenario summary.
The initial full tool output was truncated; an unchanged deterministic recovery replay produced
the saved complete artifact. This technical output recovery changed no inputs or comparisons.

## Bounded execution audit A0

After accounting passed, the predeclared synthetic probes in
`btc-breakout-execution-source-audit-a0-v1` confirmed:

1. A previously scheduled channel exit at the next open110 is overridden by a later intrabar
   low95, returning stop96. Chronological processing should execute the scheduled open exit
   before a subsequent low touch. This source behavior can change fill prices and exit reasons.
2. A segment-end close105 is reported with the bar's open timestamp, five minutes before that
   close becomes available. A predeclared terminal close can be a valid simulation convention,
   but must have the appropriate timestamp and must not masquerade as an opening fill.
3. Changing only a later bar's segment label changes the exit to the preceding bar's close.
   An unexpected gap is not information available in advance. Retrospective segment boundaries
   cannot establish an executable pre-gap exit; distinguish data invalidation from execution.

These are synthetic counterexamples, not measured historical effects. None proves every archived
trade is wrong, and their net effect on historical profitability is unknown. No historical candle
data was accessed and no legacy execution code was changed.

## Next bounded correction proposal

Freeze one execution correction specification before implementation or market access:
open-observed protective breach first; otherwise previously scheduled open exit; only for a
remaining position evaluate a later intrabar stop. Treat simultaneous at-open priorities explicitly.
Timestamp close valuations at close. Separate a known predeclared terminal close from an
unexpected missing-data boundary; mark affected paths invalid rather than invent pre-gap exits.
Retain channel thresholds, sizing and costs. Label same-boundary decision/open fills as an
idealized latency assumption and freeze an alternative timing check rather than invent sub-bar
precision. Inspect cash/risk/cadence conventions without claiming full mandate enforcement.

Then synthetic-test the corrected rules and independently review them. Only afterward freeze
one historical control comparison that reports contributions from each execution correction.
No tuning, extra regime model or data purchase. Existing rejections remain preserved; no_trade.

Reproduction:

```sh
python3 -m unittest -v research.btc.tests.test_reference_r1_v3 research.btc.tests.test_reconcile_r2_v2
PYTHONPATH=src python3 research/btc/audit_breakout_execution_a0.py
python3 scripts/validate_btc_focused_context.py
```
