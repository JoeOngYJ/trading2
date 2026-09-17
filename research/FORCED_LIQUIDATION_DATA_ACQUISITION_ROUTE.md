# Forced-liquidation study: minimum defensible acquisition route

Reviewed 2026-09-12. Run: `forced-liquidation-data-route-20260912-v1`.

**C. QUOTE REQUIRED BEFORE DECISION.** Tardis has the best documented technical route. Its current licence permits durable internal retention, but the cheapest eligible entitlement for these two instruments is not established. The known broad subscription is substantially more expensive than a one-month $350 purchase. Kaiko and Amberdata do not presently establish equivalent historical source/arrival lineage or durable retention under their standard terms.

| Procurement question | Finding |
|---|---|
| Can the examined free sources execute the frozen study? | No. Historical receipt/state and Binance native L1 coverage remain missing. |
| Best documented source route | Tardis: Bybit `allLiquidation`, `tickers`, `publicTrade`; Binance **spot** `bookTicker`. |
| One entitlement covering all four? | All Exchanges **Professional**, with **yearly billing**, is the documented broad route. Only the requested instruments/dates would be downloaded. |
| Public broad-route cost | **$26,400/year before tax**, derived from $2,200/month × 12. This is not the cheapest narrow-scope quote. |
| Potentially cheaper published-plan combination | Perpetuals Professional + Spot Solo: **$22,800/year before tax**. Conditional on Binance native `book_ticker` CSV having sufficient accompanying source/gap evidence and the combined purchase being available. |
| Cheapest narrow entitlement | **QUOTE REQUIRED**. No valid current two-symbol/raw entitlement price was established. |
| Is continuous, lossless 2025 capture established? | No. Metadata lists four overlapping Bybit incidents and one Binance incident; other losses can exist. |
| Purchase / new market downloads / event sets / outcomes | **None in this stage.** |

Pricing references are the [current public tariff](https://tardis.dev/#pricing) and [billing/access rules](https://docs.tardis.dev/faq/billing-and-subscriptions). Full commercial details and uncertainty are below. This is a procurement finding, not a newly qualified dataset or permission to execute the hypothesis.

## Frozen scope and authority

The reviewed [Phase 1 proposal](ALPHA_DISCOVERY_PHASE1.md) and [free-data feasibility](BYBIT_FREE_DATA_FEASIBILITY.md) remain unchanged. Their SHA-256 identities are respectively `8c7d009b91d059516c18e26667e98d326a0fd40b19945cd5e13e49ea95d7a6fa` and `0bd8e54f961573a659ea6ddb41708373e1bd38c3800e8bab7c985a15f16a6b7f`. The machine-readable proposed test remains `330b872d09f718339e49fbb36b6d680c56d61a19bfa725697121d6e26ec8d747`.

Acquisition envelope: **2025-02-28 00:00:00 UTC through 2025-12-31 inclusive**, equivalently an exclusive end at 2026-01-01 00:00:00 UTC. That is **307 UTC dates**, including the February context day. Request Bybit **BTCUSDT linear perpetual** and Binance **BTCUSDT spot**, with no extra symbols, venues, years or L2. The exclusive end is not permission to read any 2026 observation. Initial state must be established within this envelope; a missing anchor is a qualification failure, not authority to widen it.

Preserve the reviewed accounting quantity:

```text
derived_single_side_oi = Decimal(historical_both_sided_openInterest) / 2
```

The original native field and precision must survive. This does not assert that `singleOpenInterest` existed in 2025 or that today's server implements precisely this arithmetic. No unadjusted-denominator variant, 0.5%-OI event, matching, future BTC return, bootstrap or strategy outcome was calculated. Breakout and other rejected families remain closed.

## What can remain free, and what needs receipt-bearing acquisition

| Input | Free and already qualified enough to consider | Remaining paid requirement under the currently established evidence |
|---|---|---|
| Binance spot 5m target/context prices | Existing consumed, checksummed development input; retain its source segments and frozen masks | **Do not purchase duplicate candles or Binance trades.** Existing prices do not supply the L1 spread control. |
| Historical Bybit OI values | Official historical API values and dated documentation establish a legitimate 2025 both-sided BTC source | Receipt-bearing native ticker state, initialization and continuity. A current REST response does not show historical first availability. Do not purchase a second generic OI series in addition to that ticker tape. |
| Bybit public trades | Official archive supplies event time, IDs, side and exact numeric strings; useful as a free cross-check | Historical receipt-bearing executions are currently required for the frozen pre-T Bybit sell-flow control. |
| Forced-liquidation reports | Reviewed first-of-month free samples establish feed presence and selected native/normalized parity | Remaining calendar history, original arrival clocks, native message metadata and gap evidence. Hourly totals are insufficient. |
| Binance spot native L1 | No adequate full-window free source was qualified by the reviewed feasibility stage | Native `bookTicker`, or qualified normalized **`book_ticker`**, with receipt and source/gap evidence. **Bybit quotes are not this control.** |

The official trade archive cannot currently replace paid trade receipt history. The frozen five-minute decision delay is not proof that every relevant execution was available before the cutoff. The previous study also found intraday ID differences between official and collector archives; these were not all explained by UTC boundaries. No bound on first publication, transmission delay or retrospective revision was established. A legitimate free bridge would require historical evidence establishing availability by each frozen cutoff and reconciliation of source discrepancies. Event time alone, or the mere existence of an archive today, cannot supply it. Do not delete the sell-flow control to avoid this expense.

Thus the minimum currently defensible **information bundle is four feeds**, not liquidation history alone. Acquire each once; native replay can generate local derived tables without separately buying duplicate normalized datasets. Previously retained free samples remain evidence/cross-checks; do not splice them into a different source's missing intervals. The prior ten sample dates cannot meet the frozen calendar/sample requirements by themselves.

## Provider comparison: exact information, not generic product labels

“Unknown” means not demonstrated by the inspected public material. It does not prove that a negotiated export is impossible. Channel start dates are not a zero-gap certificate. Provider-specific notes, source registers and access limitations are preserved under this run.

| Provider / requirement | Supports the exact requirement? | Earliest relevant coverage established | Historical local receipt? | Raw/native? | Main caveat |
|---|---|---|---|---|---|
| Tardis A: forced reports | Documented technical route | `allLiquidation` since **2025-02-25**; BTCUSDT symbol predates it | Yes, original arrival prefix | Raw native messages | Full dates have known incidents; old `liquidation` is not a substitute. |
| Tardis B: OI state | Documented route requiring state qualification | V5 `tickers` since **2023-04-05** | Yes | Native snapshots/deltas | Preserve original BTC `openInterest`; qualify anchors, carry, reconnects and rollbacks. |
| Tardis C: public trades | Documented route | V5 `publicTrade` since **2023-04-05** | Yes | Native, or normalized with lineage | Collector recording is not proof of lossless exchange transmission. |
| Tardis D: Binance spot L1 | Documented native route | `bookTicker` since **2019-09-21** | Yes | Native BBO; normalized `book_ticker` available | Native spot message has no documented exchange event clock; preserve that absence. |
| Kaiko A | **Unqualified** | Generic liquidation history from January 2025; exact BTCUSDT new-feed coverage **UNKNOWN** | Separate arrival not established | Normalized event product | Single exchange-or-collection timestamp does not establish both clocks or `allLiquidation` mapping. |
| Kaiko B | **Unqualified** | Generic OI history since 2020; exact state lineage **UNKNOWN** | Live receipt field exists; historical export unproven | Interval metrics | Interval timestamp is not original ticker receipt/initialization. |
| Kaiko C | **Unqualified** | Exact 2025 receipt-bearing tape **UNKNOWN** | Live feed yes; historical product unproven | Normalized | Public live replay is 72 hours; cannot infer 2025 receipts from it. |
| Kaiko D | Potential L1 field match; **unqualified** | Full required BTCUSDT window **UNKNOWN** | Historical BBO CSV has both clocks | Native Binance origin **UNKNOWN** | Must establish source-native BBO and clock fallback, not just a BBO product name. |
| Amberdata A | **Unqualified** | Exact BTCUSDT `allLiquidation` window **UNKNOWN** | Distinct futures receipt not established | Generic normalized liquidations | Native mapping and original message clock/coverage unknown. |
| Amberdata B | **Unqualified** | Original 2025 ticker state **UNKNOWN** | Not established | Generic OI values | Native both-sided BTC units, receipt, snapshots and state transitions unproven. |
| Amberdata C | **Unqualified** | Required arrival-bearing history **UNKNOWN** | Futures receipt not established | Normalized trades | Receipt support documented for spot products cannot qualify Bybit perpetuals. |
| Amberdata D | **Not established as required native L1** | Exact native window **UNKNOWN** | Required native historical clock unproven | Ticker dictionary describes **L2-derived** BBO | Do not substitute reconstruction or purchase L2 by default. |

Tardis support and dates: [Bybit](https://docs.tardis.dev/historical-data-details/bybit), [Binance spot](https://docs.tardis.dev/historical-data-details/binance), [metadata API](https://docs.tardis.dev/api/http-api-reference). Kaiko field/clock distinctions: [liquidations](https://docs.kaiko.com/rest-api/cefi-derivative-market-data/derivative-liquidation-events), [OI](https://docs.kaiko.com/rest-api/analytics/derivatives-risk-indicators/exchange-provided-metrics), [trade stream](https://docs.kaiko.com/stream/cefi-derivative-market-data/all-trades), [BBO cloud schema](https://docs.kaiko.com/cloud-delivery/cefi-spot-market-data/best-bids-and-asks-top-of-book). Amberdata distinctions: [liquidations](https://docs.amberdata.io/http/market/futures-liquidations), [OI](https://docs.amberdata.io/http/market/futures-open-interest), [futures trades](https://docs.amberdata.io/http/market/futures-trades), [ticker construction](https://docs.amberdata.io/data-dictionary/market/tickers).

No additional vendor was added on the strength of generic historical-data marketing. A cheaper quote is not equivalent unless it meets these field, source, clock and retention requirements.

## Tardis: raw versus normalized, and one entitlement

**Raw Bybit replay is necessary for the currently frozen source lineage.** Liquidation CSV retains update time and receipt but omits native message generation `ts` and envelope membership. Ticker CSV does not retain the entire snapshot/delta, cross-sequence, reset and unchanged-field evidence. The reviewed July snapshot rollback and 199-ms timestamp discrepancy remain qualification cases. A CSV-only purchase would not resolve them. Preserve original source bytes and parse quantities with Decimal. The normalizer mapping is evidence of transformation, not evidence that omitted fields can be recovered. [Native replay format](https://docs.tardis.dev/api/http-api-reference), [CSV schemas](https://docs.tardis.dev/downloadable-csv-files/data-types), [pinned Bybit mapper](https://raw.githubusercontent.com/tardis-dev/tardis-node/6425998044f5604ed9de0867a6e3382a1e50f989/src/mappers/bybit.ts).

**Binance native `book_ticker` CSV is potentially sufficient for the frozen spread variable.** It supplies native BBO prices/sizes and receipt; it differs from reconstructed `quotes`. Original update ID is omitted, but the frozen study does not assume consecutive BBO IDs. Where no native exchange time exists, the normalized `timestamp` falls back to receipt and must be explicitly labelled accordingly. Exact required-field preservation, original collection order and source/gap evidence still need qualification. Raw `bookTicker` is necessary only if those cannot be established through the normalized delivery and accompanying records. No L2 is justified. [Native BBO product](https://docs.tardis.dev/downloadable-csv-files/data-types#book_ticker), [Binance stream schema](https://developers.binance.com/docs/binance-spot-api-docs/web-socket-streams#individual-symbol-book-ticker-streams).

One All Exchanges Professional entitlement contains raw replay for both venues plus CSV access. Its acquisition filters would be Bybit `allLiquidation`, `tickers`, `publicTrade`, symbol `BTCUSDT`; Binance `bookTicker`, symbol `btcusdt`. No all-symbol request is needed. A subscription's broader access is not authorization to download other evidence.

The cheaper mixed-plan route would use Bybit raw plus Binance **native** BBO CSV and a satisfactory coverage/disconnect record. It is a conditional procurement option, not an accepted losslessness or gap certificate. If a restricted Professional entitlement for both exact symbols is currently sold, that could supersede either broad plan; its availability and actual terms need explicit confirmation.

## Known coverage defects that a purchase cannot erase

Metadata-only API reads were filtered to the requested instruments and overlapping dates. These are **reported exchange-level capture incidents**, not measured BTCUSDT-specific missing-record counts:

| Venue | UTC interval in 2025 | Published incident reason, paraphrased |
|---|---|---|
| Binance | February 28, 08:06–08:12 | Recording loss during a misconfigured deployment. |
| Bybit | August 14, 12:30–12:50 | Input rate exceeded recording capacity. |
| Bybit | September 22, 06:00–06:17 | Input rate exceeded recording capacity. |
| Bybit | October 10, 21:15–21:22 | Input rate exceeded recording capacity. |
| Bybit | November 21, 07:34–08:55 | Liquidation subscription error followed by an IP rate-limit ban. |

Source: preserved responses from [Bybit exchange metadata](https://api.tardis.dev/v1/exchanges/bybit) and [Binance exchange metadata](https://api.tardis.dev/v1/exchanges/binance); scoped extraction is `tardis_technical_coverage_metadata.json`. “Resolved” records that the incident ended; it does not say lost data was recovered.

Activity-related loss is especially material to a forced-liquidation hypothesis. Missingness cannot be presumed independent of the event intensity. This is a data-identification concern, not an outcome result. The published incidents and raw disconnect markers must remain attached to any acquired archive. Ask whether markers survive channel/symbol filtering and how affected connections map to channels. A silent liquidation interval is not a heartbeat; healthy tickers on another connection do not prove the liquidation connection was healthy. The absence of an incident report does not prove completeness. [Recording caveats](https://docs.tardis.dev/faq/data).

No complete-calendar capture claim is justified. Later authorized source qualification must apply the frozen validity rules and report whether coverage and initialization gates pass before constructing events. If satisfying those rules requires a new state/reset convention or weakening missingness treatment, return for review. Do not select gap handling using outcomes or fill gaps from another vendor without reviewed lineage.

## Current price, entitlement and retention

### Tardis

At the review date, standard monthly access reaches back four months, quarterly twelve months, and yearly Professional four years. Consequently a new September 12, 2026 purchase reaches approximately May 12, 2026 / September 12, 2025 / September 12, 2022 respectively. Only yearly covers this entire envelope. The start boundary is fixed at purchase, not a rolling restoration of earlier history. Academic/Solo provide CSV only; Professional/Business include raw replay. Public policy says no discounts, one-off fixed-date purchases or custom exports. [Billing FAQ](https://docs.tardis.dev/faq/billing-and-subscriptions).

| Public product comparison | Advertised monthly equivalent | Required annual total before tax | Fit |
|---|---:|---:|---|
| Perpetuals Academic | $350 | $4,200 | CSV only, eligibility required, excludes Binance spot; fails this route. |
| All Exchanges Professional | $2,200 | **$26,400** | One documented broad entitlement for all required raw channels. |
| Perpetuals Professional + Spot Solo | $1,000 + $900 | **$22,800** | Potentially sufficient mixed delivery; needs Binance normalized/health and combined-entitlement confirmation. |
| Perpetuals Professional + Spot Professional | $1,000 + $1,350 | $28,200 | Both raw, more expensive than All Exchanges Professional. |

The public page's yearly multiplier is 12; these are published-plan arithmetic, not negotiated quotes. The displayed $300 minimum order is an order floor, not a complete-study price. The $350 Academic rate also requires quarterly/yearly billing; a quarterly $1,050 payment still fails date reach, raw access and venue scope. [Public pricing and embedded calculator](https://tardis.dev/#pricing).

The archived page retains code for individual exchanges/instruments, but its visible plan selector offers only the five broad plans and hides instrument selection. That code is **not proof of a currently purchasable narrow entitlement**. No hidden option was enabled and no checkout/quote request was submitted. Ask which currently supported subscription is actually the cheapest for these exact two instruments. Do not assume the provider will sell a custom ten-month export against its published policy.

**Retention is positively documented:** terms §9.4 preserve the licence for lawfully downloaded data after expiry; §§9.1 and 13.6 permit continued internal storage/use while ending further service access. Internal research is a permitted use; raw public redistribution is not thereby granted. Taxes are additional under §5.3. Pin these terms to the eventual order and confirm any requested external-review access separately. [Current terms, modified August 28, 2026](https://docs.tardis.dev/legal/terms-of-service).

### Kaiko and Amberdata

| Provider | Public product/delivery route | Billing / minimum | History limitation | Durable raw research rights |
|---|---|---|---|---|
| Kaiko | Derivative tick-level pack plus liquidation add-on; historical OI; spot BBO cloud/API. Required raw/receipt export remains unproven. | **QUOTE REQUIRED**; standard initial term one year, fees/invoicing separately specified, maintenance/connectivity fee. | Generic history is not exact feed coverage; 72-hour stream replay cannot retrieve 2025. | Standard termination provisions restrict continued raw use/destruction; written durable-retention amendment required. |
| Amberdata | Exchange-scoped market API; annual bulk S3 add-on/CloudSync. Required native/receipt fields remain unproven. | **QUOTE REQUIRED**; no exact two-instrument tariff/minimum established. | Monthly API one-year lookback misses the window's beginning; yearly provides full history, S3 costs extra. | Standard §4.4 requires deletion at expiry/termination, including reversibly derived data; written exception required. |

Sources: [Kaiko pricing](https://www.kaiko.com/about-kaiko/pricing-and-contracts), [Kaiko standard terms](https://www.kaiko.com/terms), [Amberdata ordering FAQ](https://www.amberdata.io/online-market-data-ordering-faq), [Amberdata pricing](https://www.amberdata.io/pricing), [Amberdata terms](https://www.amberdata.io/terms). These describe public default agreements, not a claim that negotiated terms cannot differ. Neither provider becomes qualified merely by quoting a lower number.

## Smallest scope to request, without purchasing

An unsent scope is preserved in `research/btc/review_runs/forced-liquidation-data-route-20260912-v1/QUOTE_SCOPE_NOT_SENT.md`. It requests only:

1. Bybit BTCUSDT linear perpetual native `allLiquidation`, historical `tickers`, and receipt-bearing `publicTrade` for the 307-day envelope.
2. Binance BTCUSDT spot native `bookTicker`, or required-field-preserving normalized `book_ticker` plus sufficient source/gap evidence, for the same envelope.
3. Historical first-collection clocks, native clocks when supplied, numeric precision, source/mapper identity, initialization/reset lineage, incident/disconnect information, and durable internal retention/reproduction rights.
4. The **minimum total compulsory payment**, currency, billing period, historical start boundary, taxes/add-ons/transfer charges, API/raw versus CSV entitlements and any minimum term. Quote only an actually offered product; state if no restricted entitlement exists.

No duplicate spot candles, generic OI series, L2, other symbol, other exchange or later year is requested. No contact was made. A forward collector would produce different, future evidence and cannot restore this 2025 history; starting one is outside this stage.

## Evidence preservation and review stop

Evidence: `research/btc/review_runs/forced-liquidation-data-route-20260912-v1/`. It contains authority hashes/copies, dated commercial documents, technical source/metadata snapshots, provider matrices, unsent scope, access/failure records, ledger entry, document checks and a hash/size manifest. Repository/worktree Git provenance remains **UNKNOWN**; exact document and script bytes are recorded instead. Prior research evidence is preserved.

This stage used public documentation, source code and coverage metadata. Some public pages/search navigation contain illustrative market snippets; these were not used as empirical observations. No historical market endpoint/archive was requested, no existing raw market partition was reopened, and no event/outcome analysis or purchase occurred. Documentation checks are not alpha tests. Current tracker status: **STOP_FOR_CHATGPT_REVIEW**.

The next decision is whether a confirmed restricted entitlement is affordable and meets the exact lineage/retention requirements. The broad public fallback is documented, but it does not establish the cheapest defensible purchase or guarantee the study can pass source qualification. No automatic acquisition or outcome stage follows.

**C. QUOTE REQUIRED BEFORE DECISION**
