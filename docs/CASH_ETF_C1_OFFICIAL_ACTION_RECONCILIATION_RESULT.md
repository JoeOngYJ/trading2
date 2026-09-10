# Cash-ETF C1 Official Action Reconciliation Result

**Experiment:** `cash-etf-c1-official-action-reconciliation-v2`  
**Decision:** **blocked**  
**Scope:** official issuer actions from 2009-01-02 through 2023-12-31 only  
**Actionable route:** `no_trade`

## Outcome

The existing provider action files are not complete enough to build the frozen total-return
ledger. This is a data-layer rejection, not a strategy result. No price, NAV, adjusted-price,
return, feature, signal, trade or PnL field was preserved or evaluated, and no data was purchased.

The audit froze exact ex-date matching, bidirectional completeness, exact split factors and an
amount tolerance equal to half the last decimal recorded by the provider before acquiring issuer
evidence. Its results are:

| Symbol | Provider distributions | Official distributions | Distribution result | Split result |
|---|---:|---:|---|---|
| SPY | 59 | 60 | Failed: one missing event and one amount mismatch | Complete zero-split history unresolved |
| EFA | 31 | 31 | Passed exactly within frozen precision | Complete zero-split history unresolved |
| IEF | 154 | 180 | Failed: 26 official events missing | Complete zero-split history unresolved |
| TLT | 139 | 180 | Failed: 41 official events missing | Complete zero-split history unresolved |
| GLD | 0 | — | Complete affirmative zero-distribution capture unresolved | Complete zero-split history unresolved |
| DBC | 4 | — | Complete event-level issuer series unresolved | Complete zero-split history unresolved |
| BIL | 74 | 180 | Failed: 107 official events missing and one provider-only date | Passed: 1-for-2 reverse split on 2017-11-30 |

SPY's provider feed omits the 2012-09-21 distribution. On 2021-12-17 it records `1.633`,
while the State Street workbook totals `1.636431`; the difference is the omitted capital-gain
component and exceeds the frozen `0.0005` tolerance. EFA is the only complete distribution
series among the seven. IEF and TLT omissions are concentrated in the earlier history. BIL's
omissions are much larger and include long stretches of monthly distributions.

State Street's image-only Form 8937 independently establishes BIL CUSIP `78468R663`, the
2017-11-30 effective date, and a 1-for-2 reverse share split. The provider's date and factors
match it exactly.

## Source and implementation notes

The first frozen source contract, v1, was rejected before acquisition because its GLD URL was
obsolete and its BIL SEC supplement did not contain the split ratio. V2 preserved that negative
result and replaced only those source references before acquisition.

V2 acquired nine of eleven allowlisted responses. The SEC rejected two automated requests with
HTTP 403; these were retained as failures rather than bypassed. The separate State Street tax
form was successfully captured, so BIL's split still reconciled. Invesco's public documents
confirm DBC-related annual distribution evidence but do not expose a complete, exact per-event
series for all four required years. They therefore cannot satisfy the frozen completeness gate.

The complete checksummed result is
`artifacts/agent-level-experiment/cash-etf/c1-official-action-reconciliation-v2/evidence-manifest.json`.

## Decision and next permitted action

C1 remains blocked. Do not use the incomplete provider actions, construct the numeric ledger,
run either C2 strategy, promote an instrument or buy another data plan.

The next bounded source task, if authorized, is an issuer-led action-ledger successor: use the
now-complete official distribution series for SPY, EFA, IEF, TLT and BIL as the candidate ledger
source, and close only the DBC, GLD and affirmative zero-split evidence gaps. If those gaps cannot
be closed without prices, replace the affected proxy under a new frozen experiment rather than
silently imputing actions or relaxing the gate.
