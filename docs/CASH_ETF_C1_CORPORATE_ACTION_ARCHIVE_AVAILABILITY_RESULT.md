# Cash-ETF C1 Corporate-Action Archive Availability Result

**Experiment:** `cash-etf-c1-corporate-action-archive-availability-v1`  
**Boundary:** SPY, EFA, IEF, TLT, GLD, DBC and BIL; 2009-01-02 through 2023-12-31  
**Decision:** **blocked; no purchase-eligible archive identified**

## Outcome

The bounded public-source check reviewed six candidate services without opening an account,
starting a trial, contacting sales or purchasing data. None passed all frozen gates. C1 therefore
remains blocked before numeric ledger construction, with zero approved execution instruments,
zero accepted strategies and `no_trade` as the only actionable route.

NYSE is the strongest authoritative route but is **contact required**, not purchase eligible.
Its product covers NYSE Arca and documents the required identifiers, dates, cash fields and
forward-split ratios. A public schema sample exists. Public materials do not establish complete
2009-2023 history for the exact seven ETFs, zero-event semantics, retention rights or price. The
Ex-Date Distributions specification also expressly excludes reverse stock splits, so a usable
archive must include and reconcile the other NYSE notice reports.

ICE and LSEG appear technically broad enough in principle: ICE states global ETF coverage and
history since 1970, while LSEG states 25-plus years of equity history. FactSet documents global
corporate-action reports and dated split extraction. All three remain **contact required** because
their public pages do not confirm the exact symbol histories, scoped samples, zero-event meaning,
retention rights or price.

EODHD is **rejected for this reproducible archive role**. Its paid product advertises long history
and has a low public price, but the current terms require deletion of stored data within one month
after a subscription ends. Its demo is restricted to AAPL and it does not document zero-event
completeness for the scoped symbols.

Massive is also **rejected under the public terms reviewed**. Its endpoints expose useful dividend
and split fields and paid plans advertise full history, but its public market-data terms grant
display use only unless another agreement says otherwise. Its free history is too short and no
public source establishes exact-symbol completeness or zero-event semantics.

## Exact written request needed

Any follow-up must ask a candidate to:

1. Confirm SPY, EFA, IEF, TLT, GLD, DBC and BIL coverage separately for distributions and both
   forward and reverse splits from 2009-01-02 through 2023-12-31.
2. Confirm that an empty response means no event occurred within a completely covered interval.
3. Provide a sample containing one known event and one asserted zero-event interval, including
   identifiers, ex/effective, record and pay dates, amounts/ratios, cancellations, revisions and
   provenance.
4. State private-research storage and reproducibility rights during and after cancellation.
5. Quote all one-time, monthly and annual non-professional fees.

No message was sent by this experiment. Written answers and a scoped sample require separate user
authorization and must be checksummed before any purchase decision.

## Safety and next action

- Data purchase: **not recommended or authorized from current evidence**
- Numeric ledger: **not built**
- C2 strategy evaluation: **not run**
- Approved execution instruments: **0**
- Accepted strategy arms: **0**
- Actionable route: `no_trade`

The next permitted action is a user-authorized written request to NYSE first, or another
contact-required candidate, using the questions above. If no vendor provides the exact sample and
rights within the frozen budget, the lower-cost alternative is to obtain written zero-action
confirmations from the seven issuers rather than buy a broad enterprise feed.

Checksummed evidence is stored at
`artifacts/agent-level-experiment/cash-etf/c1-corporate-action-archive-availability-v1/evidence-manifest.json`.
