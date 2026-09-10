# Cross-Asset A1 Source-Successor Research

Reviewed: 2026-08-29 18:45 UTC  
Stage disposition: `A1` is **active; Twelve Data v2 is accepted only for a full-history contract**  
Strategy evaluation: **not performed**

## Subsequent broker-access review

After the Marketstack failures, a separately frozen public-document audit tested whether choosing
Trading 212 or IBKR made a US-only free data source valid. It did not access any account or price.
Trading 212 publicly lists all four candidate LSE cash products; IBKR documents LSEETF execution
but leaves exact-contract access account-specific. Neither broker's historical-data interface is
an accepted archival research source. UK-retail access to US company shares does not prove direct
cash access to all US-domiciled funds needed for the four economic roles.

The four LSE listings are candidate implementations, not requirements. Do not purchase a data
plan until the intended broker and exact cash universe are selected. If these LSE listings remain,
the current Twelve Data Grow USD 29 throughput level is the logical pilot ceiling; USD 79 adds
throughput rather than the XLON entitlement needed by the pilot. This is not purchase approval.
See `docs/CROSS_ASSET_A1_UK_BROKER_ACCESS_REVIEW.md`.

## Twelve Data paid-pilot outcome

After the user purchased an individual subscription, v1 was frozen before the token was loaded.
Its source-only responses exposed boundary, venue-identity, earliest-history and corporate-action
metadata contract errors, so v1 is rejected and preserved. A separately frozen v2 corrected only
those data-contract semantics and passed all gates for SPY, EFA, EEM, IEF, TLT, GLD, DBC, BIL and
GBP/USD. This accepts Twelve Data only as a candidate for a new 2008–2025 full-history contract.
It does not pass A1 or authorize strategy evaluation. See
`docs/CROSS_ASSET_A1_TWELVEDATA_PILOT_RESULT.md`.

## Scope and boundary

This review compared public source documentation, product coverage, quote units, research-use
terms and current retail pricing after `cross-asset-a1-lse-source-pilot-v1` rejected Stooq. It did
not download another frozen historical-price partition, call a credentialed API, compute a return,
select a strategy parameter, inspect partial OB0 data or access a protected service. Public market
pages were used only to establish source and instrument metadata; displayed current prices are not
research observations and may not enter any experiment.

The frozen failed pilot remains immutable. Any successor must use a new experiment ID.

## Instrument-identity correction required in the successor

The failed pilot recorded all four listings with `listing_currency = GBP`. That is an ISO monetary
currency, but it is not enough to interpret the numeric price. London listings can disseminate GBP
prices either in pounds (`GBP`) or pence (`GBX`/`GBp`). Official LSE pages identify SWDA and SGLN
in GBX, while Vanguard publishes VAGS market prices in GBP. Twelve Data's exact COMM page displays
GBp; the successor must independently bind that scale to ISIN `IE00BDFL4P12`, MIC `XLON`, ticker
`COMM` and SEDOL `BDFLHQ3` before acceptance.

The successor schema must therefore separate:

- `iso_settlement_currency = GBP`;
- `vendor_quote_unit` exactly as returned (`GBP`, `GBX` or `GBp`);
- `price_to_gbp_multiplier` (`1` for pounds and `0.01` for pence);
- exact ticker, ISIN, SEDOL, MIC and market segment lineage.

This is a contract defect, not a backtest correction: the rejected pilot never parsed a price or
computed PnL.

## Source findings

| Source | Publicly established | Blocking issue / permitted role |
| --- | --- | --- |
| London Stock Exchange Data Shop | Official EOD summary contains opening, closing, high/low and volume data, is normally published by 19:00 London time, uses ISO 4217 plus GBX/USX, and is explicitly unadjusted for corporate actions. The 2025 price list quoted GBP 525 for one month of data or GBP 6,300 annually. | EOD Summary history starts only in March 2022, too short for the intended slow-trend development. Cost is disproportionate to GBP 20,000 research capital. Use as an authoritative specification or limited reconciliation source only, not the full-history primary source. |
| Marketstack Free | Official pricing offers 100 requests per month, EOD data, one year of history, splits/dividends, ticker and exchange information, currencies/timezones and HTTPS at no charge. Documentation covers LSE among its global exchanges and returns raw plus adjusted OHLCV, split factor, dividend, symbol, MIC-style exchange code and an ISO-8601 date. It says data is licensed from multiple high-authority providers. | Best next zero-cost pilot candidate, but not accepted. Public pages do not prove exact coverage for SWDA, VAGS, SGLN and COMM, ISIN/SEDOL identity, GBP-versus-GBX interpretation, adjustment methodology, correction/version policy or exact EOD availability. The one-year limit cannot reach January 2025 or provide full development history. A new September 2025 source-only pilot and free API key are required before any conclusion. |
| Twelve Data Grow | Exact public market pages exist for SWDA, VAGS, SGLN and COMM on LSE/XLON. Documentation describes full-history EOD OHLCV, reference data including ISIN/MIC, corporate actions, exchange timezone, and explicit adjustment modes `none`, `splits`, `dividends`, `all`. Confirmed prices are made available after exchange reconciliation. Individual Grow is USD 79 month-to-month and permits personal/internal non-commercial research and testing. | Best-documented self-serve successor candidate, but not accepted yet. The public pages do not prove the API response binds every exact ISIN/SEDOL, distinguish a confirmed bar from a preliminary bar, or expose the exact vendor publication time. A paid, checksummed, one-month pilot and conservative availability rule are still required. |
| Alpha Vantage | Documentation offers global daily raw OHLCV and an adjusted endpoint with split/dividend events; free use is limited to 25 requests/day. Its terms explicitly allow private individual investment analysis, research, testing and monitoring. | Exact coverage for all four frozen LSE lines, quote scale, MIC/ISIN binding and the price of the required full-history entitlement were not publicly verifiable. Do not choose it merely because a free key exists. |
| Interactive Brokers | Historical bars distinguish `TRADES` (split-adjusted) from `ADJUSTED_LAST` (split- and dividend-adjusted). UK LSE level-one data is listed at GBP 1/month for a non-professional subscriber. | Requires a funded account, authenticated session and market-data permissions, which the current mandate prohibits. IBKR also filters some trade data, so its volume is not an independent golden record. Reserve it for later broker/execution reconciliation after a separate access mandate. |
| EODHD | Advertises an inexpensive global EOD plan and a public SWDA page. | Public exact coverage was not established for the other three lines. Its own SWDA disclaimer says prices are aggregated/indicative rather than exchange-feed prices and are not appropriate for trading. Reject as the primary execution-price source; at most retain as a later diagnostic. |
| Issuer pages | Vanguard provides a downloadable VAGS history with both NAV and GBP market price from inception. iShares verifies the exact SWDA, SGLN and COMM listings and provides NAV/performance material. | Useful identity and reconciliation evidence, but not a uniform four-instrument execution-price source. NAV must never be substituted for the exchange close. |

Primary documentation reviewed:

- LSE historical products and EOD specification:
  <https://www.londonstockexchange.com/equities-trading/market-data/historical-data-products> and
  <https://docs.londonstockexchange.com/sites/default/files/documents/HDP_EOD_Summary_Technical_Specification.pdf>;
- LSE Data Shop history and 2025 price list:
  <https://docs.londonstockexchange.com/sites/default/files/documents/lse_data_shop_factsheet_0.pdf>
  and <https://docs.londonstockexchange.com/sites/default/files/documents/data-shop-2025_0.pdf>;
- Marketstack pricing, documentation, coverage and free sign-up:
  <https://marketstack.com/pricing/>,
  <https://marketstack-wp.apilayer.green/documentation/>,
  <https://marketstack.com/about> and
  <https://app.apilayer.com/signup/marketstack/starter>;
- Twelve Data EOD, API, timezone, coverage, use and pricing documentation:
  <https://support.twelvedata.com/en/articles/12682324-end-of-day-eod-pricing-market-data>,
  <https://twelvedata.com/docs/introduction/overview>,
  <https://support.twelvedata.com/en/articles/5745849-timezones>,
  <https://twelvedata.com/exchanges?country=United+Kingdom>,
  <https://support.twelvedata.com/en/articles/5332349-commercial-and-personal-usage> and
  <https://twelvedata.com/pricing>;
- exact Twelve Data coverage pages:
  <https://twelvedata.com/markets/534332/etf/lse/swda>,
  <https://twelvedata.com/markets/658215/etf/lse/vags>,
  <https://twelvedata.com/markets/973734/etf/lse/sgln> and
  <https://twelvedata.com/markets/712745/etf/lse/comm/historical-data>;
- official issuer listings:
  <https://www.vanguard.co.uk/professional/product/etf/bond/9685/global-aggregate-bond-ucits-etf-gbp-hedged-accumulating>
  and <https://www.blackrock.com/uk/individual/products/287254/ishares-diversified-commodity-swap-ucits-etf-fund>;
- Alpha Vantage documentation and terms:
  <https://www.alphavantage.co/documentation/>,
  <https://www.alphavantage.co/support/> and
  <https://www.alphavantage.co/terms_of_service/>;
- Interactive Brokers historical bars and market-data pricing:
  <https://interactivebrokers.github.io/tws-api/historical_bars.html> and
  <https://www.interactivebrokers.co.uk/en/index.php?f=39876>.

## Decision and next gate

Do not buy L2/L3 data and do not start A2. Slow cross-asset trend needs qualified daily data, not
order-book depth.

Marketstack Free is now the first successor candidate because it can test the source at zero
purchase cost. This finding does **not** accept the source and does not authorize an API key.
The user subsequently authorized the free-source path. The repository has frozen
`cross-asset-a1-marketstack-free-source-pilot-v1` with all of the following:

1. a free account only, no card or paid upgrade, no more than 20 of the 100 monthly requests, and
   explicit user authorization for the provider token;
2. 1–30 September 2025, exactly 22 expected LSE sessions, because January 2025 is outside the
   free one-year window; the changed boundary requires this new ID and still computes no PnL;
3. exact reference binding for ticker, ISIN, SEDOL if supplied, MIC `XLON`, exchange, quote unit
   and GBP multiplier for all four instruments;
4. immutable raw EOD, split and dividend responses; raw fields are primary and adjusted fields
   are reconciliation-only until their methodology is proven;
5. explicit recording of request time, response digest, vendor metadata, exchange timezone and
   date semantics; ambiguous EOD bars fail closed;
6. a conservative availability convention that prevents same-close execution. If exact vendor
   publication time cannot be proven, signals must lag the bar by at least one complete LSE
   session or the source is rejected for execution-timestamp research;
7. issuer reconciliation for VAGS and deterministic unit/range/session/gap checks for every line;
8. a pass only if a separately frozen full-history acquisition contract is supportable. Pilot
   success alone may not activate A2.

If Marketstack passes, its USD 9.99 month-to-month Basic tier advertises ten years of history,
enough to cover the common VAGS-led 2019–2025 development window; any purchase and full-history
contract would still require separate authorization. If it fails, preserve the negative result
and return to Twelve Data under another experiment ID. Do not switch source, symbol, listing or
date boundary inside the Marketstack pilot after seeing its rows.

The frozen downloader makes exactly 16 of the maximum 20 requests when run: four endpoint calls
for each of four instruments. The token is accepted only through `MARKETSTACK_API_KEY`, used only
in memory, redacted from errors, and excluded from every request record. No API request has yet
been made because no token was supplied to this session. A1 is active but has no accepted source;
A2 remains prohibited.

A pre-response review also clarified the acceptance logic. Marketstack's undocumented adjusted-
field methodology does not automatically reject otherwise valid raw prices: adjusted fields are
ineligible, and splits/dividends must come from their separate responses. Likewise, unknown exact
publication time is handled by the frozen one-complete-subsequent-session delay, never same-close
execution. The official service agreement documents use of the Free Plan while the account is
active; whether archived content may be used after account termination remains unresolved and is
a mandatory full-history-contract issue. This clarification occurred before any API response or
price observation and is recorded append-only.

The first credentialed request then exposed a v2 endpoint-contract defect: `/v2/tickers` returned
HTTP 404, while official APILayer documentation specifies `/v2/tickers/{symbol}`. The transactional
downloader retained no response body or partial dataset. Pilot v1 is rejected and immutable.
`cross-asset-a1-marketstack-free-source-pilot-v2` was frozen before retry and changes only the
ticker identity path and write-once artifact root; all data, identity, request, timing and safety
gates remain identical.

The corrected `/v2/tickers/SWDA` route also returned HTTP 404 before price access. V2 is rejected
with no response body or partial artifact set. Final successor v3 removes the ticker endpoint and
freezes only 12 calls to the primary EOD, split and dividend endpoints. Exact identity must be
carried by EOD name, symbol, XLON exchange and GBP price currency plus issuer controls. Failure of
any line ends Marketstack qualification; no suffix guessing or further endpoint search is allowed.

The first v3 EOD request then returned HTTP 422. No response body or partial dataset was committed.
This triggers the frozen stop rule and rejects Marketstack Free. Across v1-v3, only three failed
requests were made and zero price rows were retained or inspected. A1 was blocked at that point. Any Twelve Data
purchase or different free-source pilot requires explicit authorization and a new experiment ID.
