# Retail Cross-Asset Multi-Strategy Research Program

Program ID: `retail-cross-asset-multi-strategy-v1`  
Current stage: `A3` — **rejected; A4 and A5 blocked**  
Actionable disposition: `no_trade`

## Why this program exists

The prior BTC-only routing program correctly prevented overfitting, but it produced no accepted
strategy arms. Its fixed breakout was profitable only as consumed development evidence, its
entry-timing mechanism failed an independent random-entry falsifier, and the more complex HMM
failed its frozen downside-risk separation gate. Scaling that evidence cannot meet a 50% return
aspiration inside a 20% drawdown ceiling.

This program broadens the research opportunity set without rewriting any prior result. Its aim
is a portfolio of economically distinct forecasts, not a universal regime classifier and not a
backtest selected for a requested headline return.

## Architecture

```text
lawful instrument access + point-in-time data
                    |
      independently tested strategy families
                    |
     simple volatility/correlation/liquidity risk
                    |
 shared-capital comparison and counterfactual routing
                    |
         prospective paper observation
```

After A1 there are zero accepted strategies and zero approved execution instruments. All missing,
stale, ambiguous or jurisdictionally unresolved inputs fail closed.

## Stages

### A0 — Mandate and feasibility foundation

Freeze GBP 20,000 research equity, the GBP 17,600 soft stop, GBP 16,000 hard floor, research-only
authority, jurisdiction/access matrix, cross-asset data requirements, stage graph, checksummed
context and validator. No market data, PnL or strategy score is allowed.

### A1 — Instrument and data qualification

Select a small exact instrument universe under a lawful venue path. Require point-in-time
eligibility, raw and total-return lineage, calendars, corporate actions, cashflows, futures rolls,
funding, FX conversion, market rules, costs, gaps, timestamps and checksums as applicable. Source
qualification may not inspect strategy results.

### A2 — Diversified cross-asset trend

Freeze one trend mechanism before results. Evaluate it chronologically across qualified equity,
bond, commodity, gold, FX, cash and eligible crypto instruments. Multiple speeds are one family.
Compare with flat, static allocation, matched exposure and simpler controls after costs.

### A3 — One independent non-trend family

Choose through access facts before PnL: lawful carry if derivative and cashflow data are complete;
otherwise one liquid-instrument mean-reversion mechanism. Do not open the alternative after
observing the chosen experiment. It must pass independently before it can enter a portfolio.

### A4 — Continuous risk layer

Begin with EWMA volatility and transparent covariance/correlation and liquidity controls. Risk
may scale accepted exposure downward or abstain. No HMM or universal bull/bear oracle is planned.

### A5 — Shared-capital portfolio and router

Only after two economically distinct arms pass, compare the best single arm, static blend,
risk-balanced blend, deterministic router and `no_trade`. Account for dependence, turnover,
costs, capacity and uncertainty. Actionable output remains `no_trade` throughout research.

### A6 — Prospective paper observer

Observe each accepted arm and the shared-capital portfolio with timestamps, availability,
forecasts, intended and realized costs, fills, risk decisions and decay. A new execution mandate,
exact venue and written approval are required before paper or live activity.

## Prohibited shortcuts

- Do not select leverage to reach 50% annualized return.
- Do not treat several trend speeds or assets as independent alpha families.
- Do not use a current-survivor universe as historical membership.
- Do not use adjusted prices without raw price and corporate-action lineage.
- Do not use vendor continuous futures without a deterministic roll recipe.
- Do not infer execution permission from public market-data availability.
- Do not use offshore residency or an unregistered venue to circumvent product restrictions.
- Do not tune or reuse rejected BTC, BOCPD, HMM, taker-flow or top-two experiment IDs.
- Do not inspect partial OB0 data or access protected soak services.

## A0 pass gate

A0 passes when every contract serializes canonically, all context checksums match, invalid stage,
capital, jurisdiction, source, timestamp or access states fail closed, no strategy or instrument is
approved, no runtime dependency is imported, and the only actionable disposition is `no_trade`.

The next permitted action is a separately authorized A1 source-and-instrument qualification
contract. It must freeze exact products and a small pilot before bulk download or strategy work.

## A1 pilots

`cross-asset-a1-lse-source-pilot-v1` freezes the GBP LSE trading lines SWDA, VAGS, SGLN
and COMM plus zero-yield GBP cash. It may retrieve only official issuer identity pages, the
official 2025 LSE calendar and one January 2025 CSV per listed instrument. It may not compute
returns, PnL, forecasts or signals. A syntactically valid free CSV is not enough: missing
adjustment, corporate-action, availability-time or reuse semantics rejects the candidate source.

That pilot is complete and rejected the Stooq candidate. Official issuer identities and the LSE
calendar passed, but all four Stooq endpoints returned JavaScript challenge pages instead of CSV,
and the source semantics remained undocumented. Its negative result remains immutable.

The separately authorized Marketstack pilot family froze
freezes 1–30 September 2025, 22 sessions, the same four exact GBP/GBX LSE trading lines, and at
most 20 free-plan requests across `/v2/tickers`, `/v2/eod`, `/v2/splits` and `/v2/dividends`.
Only an environment-held `MARKETSTACK_API_KEY` is permitted; it must never be serialized or
logged. The downloader and offline auditor compute no return, PnL, score, forecast or signal.
The list ticker route returned HTTP 404, the documented symbol ticker route returned HTTP 404,
and the final primary EOD route returned HTTP 422. Transactional acquisition retained no response
body or partial dataset, and no price was inspected. Marketstack Free is rejected without suffix
or parameter tuning. A1 has no accepted source and is blocked; A2 remains prohibited.

Later, separately frozen Twelve Data pilots qualified a source-quality subset for SPY, EFA, IEF,
TLT, GLD, DBC, BIL and GBP/USD. The completion review did not promote that subset. The provider's
public terms do not establish a durable right to retain the data after subscription termination,
the US-listed funds are not approved exact UK-retail execution lines, complete corporate-action
reconciliation is unfinished, and costs cannot be frozen before an execution line is selected.
A1 therefore remains blocked with zero approved instruments and zero accepted strategies. See
`docs/CROSS_ASSET_A1_COMPLETION_REVIEW_RESULT.md` for the checksummed result and next actions.

The later authenticated, read-only account verification found all four candidates in IBKR as
LSEETF Stock results. A separately frozen public review then used direct official issuer, LSE and
IBKR pages to bind all four expected listings to their ISIN, `XLON`, quote unit and the IBKR LSE
venue group. VAGS is verified as the exact account line for identity only. SWDA, SGLN and COMM
remain conditional-unapproved because the account's `GBp` UI label was not explicitly defined by
an allowed official source as LSE `GBX`; inference is prohibited. Zero execution instruments
remain approved. The Twelve Data retention request is pending, and full actions, same-line history
and exact costs remain incomplete.

The subsequently frozen `cross-asset-a1-lse-futures-expansion-v1` kept those four exact XLON
lines and added MES, MGC, MCL, M6E and MTN as offline data-research candidates. ES, GC, CL, 6E
and TN are parent-mechanism bridges only. The 12-response exact-line acquisition completed, but
the frozen audit rejected it before normalization: SWDA and SGLN each contain one conflicting
duplicate plus 9 and 8 missing sessions; COMM contains 169 duplicate dates (109 conflicting)
plus 38 missing sessions. VAGS alone has complete price-session coverage, but its 65 provider
dividend rows cannot be cash-credited without issuer reconciliation because the line is
accumulating. No row was deduplicated or filled and no economic result was computed.

The original calendar remains immutable evidence for that rejected experiment. Its successor,
`xlon-uk-rules-2009-2025-v2`, preserves the session set and correctly assigns Christmas and
New-Year half-days to the last valid preceding session. Futures specifications remain explicitly
incomplete and all five candidates remain conditional-unapproved. CME DataMine and Databento
remain unselected pending exact, price-blind coverage/licence quotes; purchase requires explicit
user approval. A2 remains prohibited.

The later `cross-asset-a1-oanda-source-pilot-v1` used an account-bound, GET-only contract for
SPX500_USD, XAU_USD, WTICO_USD, EUR_USD and USB10Y_USD. Four candidates passed directly. V1
rejected oil for one 120-hour November 2005 gap. The no-download v2 successor starts oil at the
first post-gap candle and passes the five-market daily bid/ask source pilot without rewriting raw
data. This replaces neither the negative XLON evidence nor the unresolved futures work.

The separately frozen hourly v1 archived 224 H1 bid/ask responses for seven FX, metal and index-CFD
candidates over 2010–2025. Its two-percent incomplete-session gate rejected five candidates by
counting Sunday-local fragments, holidays and early closes as source defects. V1 remains rejected.
The no-download v2 successor changes no price, fills no bar and emits complete/`no_trade`
availability masks. All seven candidates have at least 3,995 complete windows, both history edges,
valid uncrossed bid/ask and no gap over 168 hours, so A1 passes for intraday research data only.

A2 remains inactive until a complete strategy contract is frozen. A4's machine dependency is A1,
but it may activate only after at least one A2 or A3 arm is independently accepted; this permits a
valid A3 arm to reach risk research if A2 rejects without pretending the rejected trend stage
passed.

The subsequent A2 contract froze one seven-market long/short session-breakout continuation family
and the independent A3 overnight-gap-reversion hypothesis before any PnL. A2 failed: primary-cost
development returned -11.99% and validation -5.35%, ten of thirteen gates failed and only the two
US indices were positive. The ID is closed. A boundary audit also found that the loader decoded a
2024 cutoff row before discarding it; no final-period economics were computed, but the partition is
not clean for A2. A3 remained a frozen economic hypothesis only and required a new partitioned-data
experiment ID plus separate authorization.

That separate authorization was recorded. `cross-asset-a3-timestamp-prepartition-v1` copied
the existing immutable inputs into 2010–2021 development and 2022–2025 validation files using
only timestamp/date routing; it deserialized no prices and included no prospective rows. The
replacement `cross-asset-a3-overnight-gap-reversion-v2` preserved the pre-result mechanism and was
frozen before evaluation. It rejected: development lost even at spread-only cost, primary-cost
validation lost 3.64%, all four robustness variants lost, only the two US indices were positive,
and 12 of 17 gates failed. No prospective price was accessed. Do not tune, rerun, restrict it to
the profitable instruments, add leverage or use a regime overlay to rescue it. With zero accepted
arms, A4 risk-overlay and A5 portfolio/router research are blocked.
