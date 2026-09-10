# Cross-Asset A1 Twelve Data Source-Pilot Result

Updated: 2026-08-29  
Stage: `A1` — active  
Accepted data-source candidate: **Twelve Data for a separately frozen full-history contract**  
Accepted strategy arms: **0**  
Approved execution instruments: **0**

## Decision

`cross-asset-a1-twelvedata-economic-proxy-pilot-v2` passed every frozen source-only gate.
This does not pass A1, approve a broker instrument, validate a strategy, or authorize bulk data.
The only permitted successor is a new, frozen full-history acquisition contract.

V1 is preserved as rejected. Its 20 checksummed responses exposed four contract errors before any
economic calculation: provider end-date semantics omitted the final requested session, IEF and TLT
were identified as NASDAQ/XNMS rather than ARCX, four listing-inception thresholds preceded the
provider's history, and corporate-action metadata omitted the asset-type field. V2 used a new
experiment ID, buffered only the acquisition boundary, retained the exact February session gate,
used the returned exact venue identities, required history through the first 2008 session, and
bound SPY corporate actions to its separately validated time-series identity.

## Passed evidence

- SPY, EFA, EEM, IEF, TLT, GLD, DBC, BIL and GBP/USD matched their frozen symbol, type, currency,
  and MIC or FX base/quote identity.
- Every ETF contained exactly 19 expected February 2025 US sessions; GBP/USD contained exactly 20
  expected weekdays. One ordered row outside the boundary was discarded per the frozen v2 rule.
- Earliest timestamps were: SPY 1993-01-29, EFA 2001-08-27, EEM 2008-01-02, IEF 2002-07-30,
  TLT 2002-07-30, GLD 2004-11-18, DBC 2008-01-02, BIL 2007-05-30 and GBP/USD 2003-12-01.
- Unadjusted daily OHLCV relationships, positive prices, non-negative ETF volume, ordered unique
  session labels, strict JSON, request counts, credit phases, raw-byte checksums and manifest
  lineage all passed.
- SPY split and dividend endpoints returned attributable strict schemas. Empty February arrays
  prove endpoint behavior only; they do not prove full-history corporate-action completeness.
- The API token was supplied only in the authorization header and is absent from persisted URLs,
  parameters, logs and artifacts.

No return, PnL, forecast, score, model, signal, order, position, sealed partition, partial OB0 data,
database, NATS, exchange client or protected soak service was accessed.

## Still unresolved

The later full-history contract must resolve or conservatively freeze:

- the exact 2008-01-02 through 2025-12-31 acquisition and calendar boundaries;
- full-history correction/version and all-instrument split/dividend completeness;
- cash-flow and total-return reconstruction without using undocumented adjusted fields;
- FX availability and conversion rules;
- archival use after subscription termination; and
- research-proxy mapping to any later broker-executable instrument.

Until that contract and acquisition pass, A2 and every strategy/PnL experiment remain prohibited.

## Reproduce

```bash
.venv/bin/python scripts/validate_cross_asset_research_context.py
.venv/bin/pytest -q tests/test_cross_asset_program.py \
  tests/test_cross_asset_twelvedata_audit.py
```

Credentialed acquisition is write-once and must not be rerun for either frozen pilot ID.
