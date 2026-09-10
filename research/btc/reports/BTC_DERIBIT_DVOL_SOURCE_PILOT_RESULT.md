# BTC Deribit DVOL source pilot result

Successful experiment ID: `btc-deribit-dvol-source-pilot-v2`  
Predecessor: `btc-deribit-dvol-source-pilot-v1` rejected before data requests  
Decision: **technical pilot passed; historical risk-model use remains blocked**  
Actionable arm: `no_trade`

## Result

V1 failed closed when its frozen official API-reference human-page path returned HTTP 404. It
requested no DVOL data. V2 changed only that path to the current Markdown resource named by
Deribit's official documentation index; all data windows, gates, blockers and safety boundaries
were inherited unchanged.

The unauthenticated V2 pilot preserved checksummed official API and methodology pages and three
pre-2026 daily windows:

| Window | Rows | Duplicate timestamps | Non-daily gaps | Invalid rows |
|---|---:|---:|---:|---:|
| 2021-03-24 through 2021-04-07 | 15 | 0 | 0 | 0 |
| 2022-06-01 through 2022-06-15 | 15 | 0 | 0 | 0 |
| 2025-11-01 through 2025-11-15 | 15 | 0 | 0 | 0 |

Every response was HTTP 200, JSON-RPC-error-free, strictly increasing, UTC-daily, in bounds and
contained positive ordered timestamp/open/high/low/close values. Both official documentation
records contained every predeclared phrase. The bounded technical source gate therefore passes.

## What did not pass

This pilot intentionally cannot approve DVOL as a historical model input. A separate frozen
qualification must still establish:

- complete intended historical coverage;
- an effective-dated archive of methodology and parameter changes;
- historical publication and revision semantics; and
- durable private-research retention rights.

The official methodology says parameters may change, so silently applying the current definition
to all historical observations would violate the point-in-time research standard. DVOL remains an
optional source candidate, not an accepted feature and not a reason to purchase data.

No feature, label, strategy, return, PnL, regime or risk model, 2026 row, partial OB0 data,
credential, order, position, account or protected service was accessed or created.
