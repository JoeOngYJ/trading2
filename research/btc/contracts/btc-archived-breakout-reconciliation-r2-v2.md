# R2-v2 archived breakout arithmetic replay

Identity `btc-archived-breakout-reconciliation-r2-v2`. Frozen before successor accounting replay; predecessor opened compatibility fields only.
Action `no_trade`. This is consumed-evidence bookkeeping reconciliation, not a strategy experiment.

## Exact authorized inputs

Source manifest: `artifacts/agent-level-experiment/btc-regime-routing/s1-ledger-v1/manifest.json`,
SHA-256 `5a99488be5dd8fac7b5d1628a3335fc9fb3548745cdb0269604e1d9d860af435`.
Only row-bearing input allowed:
`artifacts/agent-level-experiment/btc-regime-routing/s1-ledger-v1/breakout-trades.jsonl.gz`,
SHA-256 `22d68c6174edc18b055041ba3a32c03c1f8945d9e532b7169bcb370507629809`,
25331 bytes and exactly 201 records across the three frozen 30/40/80-bps scenarios.
No candle, feature, forecast, 2026 or OB0 files. Refuse symlinks and verify bytes before decoding.
Data boundary: entry and exit timestamps within 2019-01-01 inclusive to 2026-01-01 exclusive.

## First gate: structural and numeric compatibility

Decode JSON with decimal-number lexemes preserved, reject duplicate keys and nonfinite numbers.
Scenario IDs must be candle-primary-30bps-rt-v1, candle-stress-40bps-rt-v1 and
candle-severe-80bps-rt-v1. Require 67 records each, preserving per-scenario source order.
Required fields: scenario_id, signal_ms, entry_ms, exit_ms, entry_fill, exit_fill,
entry_reference, exit_reference, quantity, cash_before, remaining_cash, cash_after, pnl_quote.
Additional legacy metadata may be preserved but not used for accounting or selection.
Require positive quantity/prices, nonnegative cash, integral millisecond times convertible exactly
to UTC seconds, signal<=entry<=exit, no overlapping trades in a scenario and no boundary crossing.
Equal entry/exit timestamps are allowed; serialize buy then sell. Do not claim timestamps prove
intrabar or close-price availability. The source's known timestamp concerns remain unresolved.

Convert decimal lexemes to ordinary decimal strings exactly, without quantization. Required
event prices, quantities and references must fit R1-v3's <=32 total digits and <=24 fractional
digits domain. If any record cannot be represented, STOP before accounting and emit only a
compatibility-failure report with field names, counts and maximum digit counts. No rounding,
skipping, padding missing fields or weakening the domain to force a historical pass. Any expanded
domain requires a separately frozen synthetic qualification and successor replay identity.

## Accounting replay, only if first gate passes

Use accepted R1-v3 with initial cash 1000 separately for each scenario. Each archived trade becomes
buy then sell with exact recorded quantity and fill price, reference price as explicit mark and
zero quote fee: costs are already embedded in these legacy fills. Do not reconstruct signals,
resimulate prices, resize or recalculate stops. Compare entry cash-before and after-entry cash
with cash_before/remaining_cash; exit cash with cash_after; exit-minus-entry-prestate cash with
pnl_quote. Check carryforward consistency between trades before aggregate diagnostics.

Independent Fraction oracle from mapped INPUT events must match every emitted balance exactly.
Compare source cash/PnL using abs(error)<=1e-8 USDT + 1e-12*abs(source value). This tolerance is
for serialized binary-float arithmetic only. Quantities and event prices are never tolerance-
adjusted. Report every difference, maximum absolute/relative errors and failed comparisons.
Source continuity uses the same cash tolerance; never reset engine cash to a stored balance.
Final cash and terminal return may be reported only after per-trade comparisons; no CAGR, Sharpe,
drawdown or new performance/promotion claim. Report all three scenarios, including failures.

Before historical access test synthetic 1000-trade float chains at reference prices 100/1000/
60000/100000 and side costs .0015/.002/.004, comparing archived-style float values to exact
decimal arithmetic. Also require 0.01 USDT corruption detection, missing-field, numeric-domain,
duplicate-key, scenario/count, timestamp and checksum failures. Freeze implementation and tests
after review, before first decode. If tests/review fail, do not open trade rows.

Acceptance means archived recorded-fill arithmetic reconciles within the predeclared tolerance,
with exact independent accounting checks. A blocked compatibility gate is a useful final result;
it is not evidence for or against strategy profitability. Preserve all outputs and checksums.

Predecessor R2-v1 remains blocked and unchanged. The only substantive change is the
separately qualified wider exact numeric domain. Source hashes, costs, tolerances, scenarios,
counts and execution conventions are unchanged. No tuning or correction of execution here.
