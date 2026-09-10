# Cash-ETF C1 Pragmatic Action Ledger Result

Updated: 2026-08-30 22:00 UTC

## Decision

C1 **passes as a development-data infrastructure gate only** under
`cash-etf-c1-pragmatic-action-ledger-v4`. Seven causal GBP total-return ledgers contain 2,516
aligned US sessions from 2009-01-02 through 2018-12-31. No 2019-or-later price or FX row was
JSON-deserialized. No strategy, return summary, trade, PnL, execution instrument or purchase was
evaluated or approved; the actionable arm remains `no_trade`.

Official issuer distributions replace the incomplete provider dividend feed. BIL's exact
2017-11-30 1-for-2 reverse split is applied, GLD has zero distributions under the frozen
issuer/filing triangulation, and the raw-price detector found no other unresolved split-like
event. Provider action files remain diagnostic only.

The frozen Twelve Data GBP/USD line lacked 2011-04-15, 2013-10-08, 2017-07-11 and 2017-11-16.
V3 therefore failed closed rather than forward-filling. V4 retrieves exactly those four values
from the Federal Reserve H.10 DEXUSUK series and treats each as unavailable until ten calendar
days after its observation date. This deliberately conservative delay covers the H.10 weekly
release schedule and prevents same-day use.

V1 rejected zero-cash schedule rows; V2 passed only the USD action subledger; V3 rejected the
missing FX sessions; and V4 changed only the frozen official FX patch and passed C1.

## Reproduce

```bash
.venv/bin/pytest -q tests/test_cash_etf_pragmatic_ledger.py tests/test_cash_etf_program.py
.venv/bin/python scripts/validate_cash_etf_research_context.py
```

The next permitted research action is to freeze and activate C2 separately before reading any
strategy economics. C1 does not authorize C2 execution by itself.
