# A1 Executable-Universe Feasibility Result

Date: 2026-08-30  
Stage: `A1`  
Experiments: `cross-asset-a1-executable-universe-feasibility-v1` and `cross-asset-a1-executable-universe-feasibility-v2`  
Stage disposition: **blocked; exact-line source clarification passed, completion work remains**

## Outcome

The paid Twelve Data subscription is useful for the intended exact LSE cash lines. It is not
rejected as a provider by this review. The separately frozen v2 clarification passed every
source-only gate for `SWDA:LSE`, `VAGS:LSE`, `SGLN:LSE` and `COMM:LSE`:

- all four responses identify the symbol as an ETF on `LSE` / `XLON`;
- SWDA, SGLN and COMM use the expected `GBp` provider unit and VAGS uses `GBP`;
- all four contain the exact 20 expected sessions from 3–28 February 2025;
- earliest daily history predates the frozen listing thresholds: SWDA 2009-09-28, VAGS
  2019-06-18, SGLN 2011-04-14 and COMM 2017-07-18;
- the reused corporate-action responses are structurally valid and checksummed; VAGS contains
  14 unique dividend rows returned in descending order, while the other dividend and split
  arrays are empty within the frozen window.

This is source qualification only. It approves zero execution instruments and zero strategies,
and it computes no return, PnL, score, feature or signal.

## Why v1 rejected

V1 remains immutable negative evidence. Its daily requests used `end_date=2025-02-28`, and all
four responses ended on 27 February. Twelve Data's official historical-data guidance demonstrates
the same convention: an `end_date` request returns observations before that date. The frozen v1
coverage gate therefore failed all four lines.

The v1 audit also required corporate-action rows to be ascending even though its endpoint request
froze no ordering parameter. Twelve Data returned 14 valid, unique VAGS dividends in descending
order. This was an audit-specification defect, not a duplicate or missing-action finding.

V2 used a new experiment ID, changed only the upper request boundary to the exclusive
`2025-03-01`, and accepted unique strictly monotonic action dates in either direction. It reused
the v1 identity, earliest-history and action bytes only after validating their original manifest
and checksums. It did not rewrite v1.

Official provider semantics:

- <https://support.twelvedata.com/en/articles/5214728-getting-historical-data>
- <https://twelvedata.com/docs/introduction/overview>

## Broader-universe feasibility

The parallel official-source review selected no broader universe:

- MES, MGC and MCL are publicly listed by IBKR UK and have usable micro contract sizes, but each
  still needs account permission, current broker margin, expiry/roll rules, exact all-in costs and
  expiry-specific historical data. MGC also needs a mandatory pre-delivery control.
- GBP/USD and EUR/USD spot are publicly supported by IBKR UK, but leveraged spot permission,
  minimum practical size, rollover financing, settlement holidays and same-feed history remain
  unresolved.
- BTC and ETH cash spot are residency/account dependent. UK-retail crypto derivatives remain
  prohibited and are not a fallback path.

Official sources used by the checksummed facts record include CME contract pages, IBKR UK product,
commission and market-data pages, the FCA Handbook and Twelve Data documentation. The normalized
record is
`artifacts/agent-level-experiment/cross-asset/a1-executable-universe-feasibility-v1/public-feasibility-facts.json`.

## Remaining A1 gates

A1 remains blocked because a one-month source pilot is not a research ledger or execution
approval. The next permitted experiment is a separately frozen exact-line full-history
acquisition and complete corporate-action reconciliation. It must also freeze:

1. deterministic historical windows and pagination with the provider's exclusive end-date rule;
2. exact raw-versus-adjusted price policy and GBP/GBp normalization;
3. complete dividend/split reconciliation against issuer records;
4. missing-session, duplicate, OHLCV and calendar-crossing gates;
5. exact broker commissions, exchange and regulatory fees, spreads, FX conversion, taxes where
   applicable, and minimum-order/rounding behavior;
6. immutable lineage, active-subscription retention treatment and no sealed-2026 access.

Do not start A2, calculate returns, rank strategies, access sealed 2026 data, inspect partial OB0,
or connect to PostgreSQL, NATS, Freqtrade, exchange clients or protected soak services.

## Reproduction

From `/data/Trading`:

```bash
.venv/bin/pytest -q tests/test_cross_asset_program.py \
  tests/test_cross_asset_twelvedata_lse_audit.py \
  tests/test_cross_asset_twelvedata_lse_clarification.py
.venv/bin/python scripts/validate_cross_asset_research_context.py
```

The write-once download and audit commands are historical reproduction references only and must
not be rerun into their existing artifact roots.
