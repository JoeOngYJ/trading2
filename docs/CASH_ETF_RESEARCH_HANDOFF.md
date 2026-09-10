# Cash-ETF Research Session Handoff

Updated: 2026-08-30 22:00 UTC  
Program: `retail-cash-etf-multi-strategy-v1`  
Current stage: `C2` — **active, contract frozen; evaluator not yet run**  
Accepted strategy arms: **0**  
Approved execution instruments: **0**  
Actionable route: `no_trade`

## Completed evidence

C0 froze the no-futures, unlevered long/flat research mandate; the eight-item proxy registry;
the four precommitted exact UK candidates; chronological evidence boundaries; and both proxy
strategy hypotheses before any ETF economic result was read. The predecessor A2/A3 rejections
remain unchanged.

The pragmatic v4 successor builds seven aligned causal GBP total-return ledgers over the open
development partition only: 2,516 sessions from 2009-01-02 through 2018-12-31. Official issuer
distributions replace incomplete provider dividends; BIL's reverse split is applied; and no other
split-like discontinuity remains. Four missing GBP/USD sessions use official Federal Reserve H.10
DEXUSUK values with a conservative ten-day availability delay. No 2019+ numeric row was
deserialized. Earlier negative results remain preserved. See
`docs/CASH_ETF_C1_PRAGMATIC_ACTION_LEDGER_RESULT.md`.

## Reproduce

From `/data/Trading`, without database, message-bus, broker or exchange access:

```bash
.venv/bin/pytest -q tests/test_cash_etf_pragmatic_ledger.py tests/test_cash_etf_program.py
.venv/bin/python scripts/validate_cash_etf_research_context.py
```

## Next permitted action

The C2 evaluation contract is now frozen and activated. Implement the isolated evaluator against
the v4 GBP ledgers, preserving both frozen proxy hypotheses, all controls, costs and gates. Keep
2019+ partitions locked and every actionable decision at `no_trade`.

The first C2 preflight blocked safely because v4 omitted `open`. The frozen v5 C1 successor now
adds causal `open` and `gbp_open_equivalent` fields, and the preflight passes without close-for-open
substitution. C2 successor v2 binds those ledgers. The next permitted action is implementing the
isolated evaluator; no gate-complete economics have yet been computed.
The corrected C2 development run is now complete on v5. Its diagnostics are recorded in
`docs/CASH_ETF_C2_PROXY_EVALUATION_RESULT.md`; validation remains locked and C2 is not yet passed.

Do not acquire futures data, inspect locked economics, use broker-private state, buy another data
plan, inspect partial OB0, touch the soak, or treat C1 as strategy acceptance.
