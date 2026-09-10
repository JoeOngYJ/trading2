# R2-v1 stopped at numeric compatibility

The independently reviewed implementation and tests were frozen before first archive decode.
Input checksums, 201 total records, 67 records per 30/40/80-bps scenario, required fields,
ordering and timestamp boundaries passed. The numeric compatibility gate blocked accounting:

| Field | Incompatible records | Maximum total digits | Maximum fractional digits |
|---|---:|---:|---:|
| quantity | 201 | 20 | 19 |
| entry_fill | 2 | 17 | 13 |
| exit_fill | 2 | 17 | 13 |

R1-v2 accepts at most 18 total digits and 12 fractional places. Archived values were preserved
exactly. No rounding, row skipping, resizing or accounting replay occurred; no PnL or return
was computed. This is a qualification-domain mismatch, not a data-corruption or strategy result.

Machine outcome: `research/btc/reports/btc-r2-v1-compatibility-result.json`.
Reviewed bundle: `research/btc/reports/btc-r2-reviewed-bundle.json`.
Synthetic review: `research/btc/reports/BTC_R2_REVIEW.md`.

Reproduce synthetic checks: `python3 -m unittest -v research.btc.tests.test_reconcile_r2`.
Verify preserved evidence: `python3 scripts/validate_btc_focused_context.py`.
The historical gate was invoked once after review by calling
`research.btc.reconcile_r2.run_archive()` with every reviewed-bundle hash checked first.

Stop here under R2-v1. The bounded next proposal is a successor synthetic accounting qualification
for lossless wider decimal inputs, with a newly proved precision bound and extreme-value tests,
followed by a new archived replay identity. Do not change accepted R1-v2 or this frozen R2-v1
contract to force passage. No change of strategy direction or data purchase is indicated by this
result. No 2026, candle/feature data, OB0 or protected service was accessed. Action remains no_trade.
