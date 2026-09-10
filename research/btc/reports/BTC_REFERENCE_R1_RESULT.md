# R1 explicit-fill accounting result

Identity: `btc-reference-fill-accounting-r1-v2`. Scope: synthetic BTC spot fill bookkeeping.
Implementation: `research/btc/reference_r1.py`. This module assumes supplied fills; it does not
select trades or assert when market information was available.

Eight literal scenarios pass: flat valuation, combined-cost fills, equivalent explicit fees,
partial exits, multiple trades, terminal valuation, same-time ordered fills and additional buys.
An independent Fraction oracle derives balances directly from input events, compares every row,
and rejects a deliberately altered cash value. Schema, order, domain, cash/inventory and caller
context checks pass. Four R1 test methods pass, eight together with the unchanged R0 suite.

Independent review rejected v1's precision-50 assumption. A valid mixed-scale input rounded away
1e-24 of equity. The original files are preserved in
`research/btc/invalid/reference-fill-r1-v1-precision-failure/`. V2 freezes precision 80 with a
conservative 65-significant-digit bound; the exact reviewer example and a maximum 10000-event
mixed-scale input reconcile against exact rational arithmetic. The specification was refrozen
under v2 before implementing the precision change. Original hand-calculated cases are unchanged.

Independent final review: PASS by `/root/r1_review`, recorded with exact engine/test hashes in
`research/btc/reports/BTC_REFERENCE_R1_REVIEW.md`. Accept v2 as synthetic explicit-fill bookkeeping
only. No historical trade or market rows were accessed.

Reproduce:

```sh
python3 -m unittest -v research.btc.tests.test_reference_r1
python3 scripts/validate_btc_focused_context.py
```

After acceptance, next is a separately frozen archived-trade reconciliation contract: resolve
artifact paths/hashes from existing manifests before opening trade rows, freeze numeric tolerance
using synthetic float/Decimal examples and compare per-trade balances before aggregate return.
R1 does not authenticate historical fills, price sources, timestamp causality or strategy alpha.
Zero accepted strategy arms; `no_trade` remains actionable.
