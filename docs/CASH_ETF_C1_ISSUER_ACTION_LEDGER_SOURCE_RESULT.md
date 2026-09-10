# Cash-ETF C1 Issuer-Action Source Result

**Final experiment:** `cash-etf-c1-issuer-action-ledger-source-v2`  
**Boundary:** 2009-01-02 through 2023-12-31  
**Decision:** **blocked before numeric ledger construction**

## Outcome

The source-only successor acquired all 17 allowlisted official issuer, SEC and NYSE responses.
It read no price, NAV, return, feature, signal, trade or PnL field and built no numeric ledger.

DBC's distribution series is now reconciled. Five issuer-filed annual reports explicitly cover
every calendar year from 2009 through 2023. They establish no distributions in 2009–2017, 2020
and 2021, and four distributions in 2018, 2019, 2022 and 2023. The issuer-filed record, payable
and exact per-share amounts combine with the effective pre-2024 NYSE Arca Rule 7.4-E to derive
the ex-dates. All four dates and amounts match the provider rows within the previously frozen
precision rule:

| Ex-date | Record date | Payable date | Official amount | Provider amount |
|---|---|---|---:|---:|
| 2018-12-24 | 2018-12-26 | 2018-12-31 | 0.18853 | 0.189 |
| 2019-12-23 | 2019-12-24 | 2019-12-31 | 0.25383 | 0.254 |
| 2022-12-19 | 2022-12-20 | 2022-12-23 | 0.14467 | 0.145 |
| 2023-12-18 | 2023-12-19 | 2023-12-22 | 1.08926 | 1.089 |

This closes DBC distributions only. DBC is not instrument-qualified because its zero-split
history remains unresolved.

GLD's official materials state that the trust generates no income, but the trust indenture also
allows cash distributions in specified circumstances. Neither the issuer page nor the 2023
Form 10-K supplies an explicitly complete 2009–2023 cash-distribution event history. The frozen
zero-event gate therefore remains unresolved rather than inferring zero.

The official product and document indexes for SPY, EFA, IEF, TLT, GLD and DBC do not state that
they are complete corporate-action archives for the full boundary. Their failure to display a
split is not affirmative proof that no split occurred. BIL's already verified 2017-11-30
1-for-2 reverse split remains the only passed split history.

The inherited distribution findings are unchanged: EFA passes; SPY, IEF, TLT and BIL fail because
the provider series is incomplete or inconsistent. No incomplete provider series will be used to
construct total returns.

## Preserved implementation result

`cash-etf-c1-issuer-action-ledger-source-v1` is preserved as rejected implementation evidence.
Its first run used a case-sensitive parser that missed valid lowercase issuer wording and an
obsolete GLD document-index URL. V2 changed only those implementation inputs; it did not alter
the economic evidence gate or expected DBC events.

## Safety decision

- Approved execution instruments: **0**
- Accepted strategy arms: **0**
- Actionable route: `no_trade`
- Numeric ledger: **not built**
- C2 strategy evaluation: **not run**
- Data purchase: **not authorized or required by this run**

The next permitted task is a bounded availability and cost check for a complete official or
qualified corporate-action archive covering the six zero-split histories and GLD cash
distributions. A written issuer confirmation is also eligible. Do not buy a feed, build the
numeric ledger, or run C2 until a separately frozen source contract passes.

## Reproduce

From `/data/Trading`:

```bash
.venv/bin/pytest -q tests/test_cash_etf_actions.py tests/test_cash_etf_issuer_actions.py
.venv/bin/python scripts/validate_cash_etf_research_context.py
```

Checksummed evidence is at
`artifacts/agent-level-experiment/cash-etf/c1-issuer-action-ledger-source-v2/evidence-manifest.json`.
