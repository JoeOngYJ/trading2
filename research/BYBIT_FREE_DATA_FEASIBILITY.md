# Bybit free-data feasibility

**NEED PAID DATA for the currently identified historical source route; no complete free route was qualified. This is not a recommendation to buy yet.** Free sources were sufficient to verify that the proposed information exists and to resolve much of the OI-field question. They do not supply the continuous, receipt-bearing history required by the frozen study. This is not an exhaustive claim that no other free archive could exist.

| Question | Verified result |
|---|---|
| Can the official OI API retrieve selected 2025 dates? | Yes: all ten first-of-month dates, March–December; 2,880/2,880 expected five-minute observations. |
| Are official Bybit BTCUSDT trades free? | Three complete calendar-selected daily files downloaded; 6,204,866 records. All ten sampled archive paths answered HTTP 200 to HEAD. Full intervening history was not downloaded/verified. |
| Do Tardis free samples contain liquidations/ticker/trades/quotes? | Yes: 10 liquidation days, 10 ticker days, and three trade/quote days; all GETs succeeded without a key. |
| Are these actually `allLiquidation` records? | 697 native records in 40 fixed/source-selected minute slices exactly reconcile with the corresponding normalized records, across all ten months. This verifies those slices, not every intervening day. |
| Is historical `openInterest` legitimate? | Yes, as the original **both-sided BTC** field. The newer single-side field was not required to observe OI in 2025. It must not silently replace the old field or change the proposal's denominator. |
| How much history does the existing proposal require? | 306 population days plus February 28 context: at least 307 calendar days, with initialization/coverage qualification. Ten free first days cannot meet 60 event dates or 80% coverage per month. |
| Purchase or outcome experiment now? | Neither. Resolve the remaining free-sample lineage issues and obtain a source/rights scope before considering spending. No signal, return, matching or bootstrap experiment ran. |

Run: `bybit-free-data-feasibility-20260912-v1`; evidence: [review directory](btc/review_runs/bybit-free-data-feasibility-20260912-v1/). The [Phase 1 proposal](ALPHA_DISCOVERY_PHASE1.md) and prior rejected breakout remain unchanged. This is source qualification on newly downloaded 2025 records; it is not alpha evidence or independent confirmation.

## What was actually downloaded

All market retrieval used direct HTTPS API/archive endpoints. No market-page scraping, credentials, paid access, account activity, vendor contact, collector or service interaction occurred. No protected 2026 or OB0/L2 payload was opened. Public 2026 documentation was inspected only to establish schema changes; API server-time metadata is not a market observation.

- Official OI: `/v5/market/open-interest`, `category=linear`, `symbol=BTCUSDT`, `intervalTime=5min`, explicitly bounded 2025 dates and cursor pagination. Ten dates each returned 200+88 rows, with no duplicate/missing/out-of-window timestamps. These responses were obtained today; they do not prove historical publication/receipt times.
- Official trades: `https://public.bybit.com/trading/BTCUSDT/BTCUSDT2025-MM-01.csv.gz` for March, July and December, chosen by calendar before price inspection.
- Tardis CSV: `https://datasets.tardis.dev/v1/bybit/{type}/2025/MM/01/BTCUSDT.csv.gz`. Every March–December first day for `liquidations` and `derivative_ticker`; March/July/December for `trades` and `quotes`.
- Tardis raw replay: native `allLiquidation.BTCUSDT` on all ten sample dates, offset zero plus three distinct minutes chosen mechanically from the first normalized receipt timestamps for source parity. Six additional calendar-fixed `tickers.BTCUSDT` minutes—00:00 and 01:00 on March/July/December first days—qualify the historical native OI field and clocks. The source-only addition was documented before retrieval.

There were **95 successful market-source GET responses**, preserving **496,350,908 body bytes** (about 496 MB), within the initial 2 GiB limit. Documentation/source retrieval is recorded separately. All 29 downloaded daily gzip files passed full-stream CRC validation. Native API bodies were plain receipt-prefixed JSON despite the requested compression parameter; the original bytes and actual encoding are preserved. Empty successful native minutes remain empty, not invented missing-data incidents.

An initial sandbox DNS attempt failed before any HTTP response. Authorized network execution then succeeded. Ten official-trade HEAD requests returned 200; forty Tardis HEAD requests returned 404 even where subsequent GETs returned complete files. **HEAD 404 is not evidence that these Tardis archives are absent.** No failed response was replaced or hidden.

Endpoints and free-first-day mechanics are documented by [Bybit's trade API documentation](https://bybit-exchange.github.io/docs/v5/market/recent-trade), [Tardis CSV API](https://docs.tardis.dev/downloadable-csv-files/api.md) and [raw replay API](https://docs.tardis.dev/api/http-api-reference.md). Actual response identities and content findings are in `http_requests.jsonl`, `requests/`, `raw/` and `qualification/`.

## Exactly which liquidation evidence exists

The following are **source-record counts**, not qualifying 0.5%-OI events or trading opportunities. Normalized `sell` denotes a forced long closure; `buy` denotes a forced short closure. No price response or intensity ratio was calculated.

| Free sample date | All liquidation records | Long-closure records (`sell`) | Short-closure records (`buy`) | OI rows |
|---|---:|---:|---:|---:|
| 2025-03-01 | 2,092 | 563 | 1,529 | 288 |
| 2025-04-01 | 1,987 | 513 | 1,474 | 288 |
| 2025-05-01 | 2,753 | 231 | 2,522 | 288 |
| 2025-06-01 | 1,053 | 468 | 585 | 288 |
| 2025-07-01 | 1,340 | 1,205 | 135 | 288 |
| 2025-08-01 | 5,565 | 5,256 | 309 | 288 |
| 2025-09-01 | 2,091 | 1,618 | 473 | 288 |
| 2025-10-01 | 2,873 | 102 | 2,771 | 288 |
| 2025-11-01 | 175 | 54 | 121 | 288 |
| 2025-12-01 | 7,042 | 6,026 | 1,016 | 288 |
| **Total** | **26,971** | **16,036** | **10,935** | **2,880** |

Every normalized liquidation record lacked an ID. No exact event-payload duplicate was found in these ten files, but tuple uniqueness does not create an exchange ID. Receipt ordering was monotone; three exchange-update backward steps occurred across August/December. Retain both clocks rather than sorting away arrival history. Quiet intervals cannot establish feed health or the end of forced selling.

Native parity covered timestamp, collector receipt, side, exact decimal quantity and bankruptcy price. All 697 compared records matched as multisets; no price or quantity values were printed. The source identifies forced position reports, not uniquely linked public market executions. Bankruptcy price is not a fill reference.

The provider advertises native `allLiquidation` capture from February 25, 2025; its pinned mapper switches normalization on February 26. Both precede the March population. **What exists on every non-sample date remains unverified locally.** The free files prove first-day availability in every month; provider coverage documentation supports a route to broader history but is not a complete loss/contents audit. [Coverage description](https://docs.tardis.dev/historical-data-details/bybit.md), [pinned 2025 normalizer](https://raw.githubusercontent.com/tardis-dev/tardis-node/6425998044f5604ed9de0867a6e3382a1e50f989/src/mappers/bybit.ts).

## The denominator question

**Use the historically observed `openInterest` as the source field. Do not require a field that did not exist in 2025.** However, distinguish source field from the quantity required by the hypothesis.

Official documentation pinned before March 2025 explicitly defines `openInterest` as the sum of both sides, in BTC for BTCUSDT linear. The definition is also present in the December 2025 snapshot and predates 2025. June 2026 added `singleOpenInterest` alongside the original field; this was not a rename. [February 2025 official source](https://raw.githubusercontent.com/bybit-exchange/docs/544fea254b53dbc6425bd2ed81cef3c1b61921c2/docs/v5/market/open-interest.mdx), [field-addition diff](https://api.github.com/repos/bybit-exchange/docs/commits/c416bd5bd9ee1723f140cc91d384e9ca9ac28f6c).

The existing proposal explicitly uses **single-sided** OI. A transparent accounting derivation is therefore `Decimal(native_2025_openInterest) / 2`, retaining the native both-sided value and its precision. This is an accounting inference from historically documented summed-side counting, not proof of the server's exact single-sided computation or a fitted scaling factor. The source-binding/derivation must be recorded and reviewed before constructing X. Using unadjusted both-sided OI at the same 0.5% cutoff would double the required closure intensity and change the proposed hypothesis. No such change or alternative event count was made.

Today's API also returns `singleOpenInterest` on the queried 2025 rows. These are historical observations returned under a later response schema; whether the added field was backfilled or computed at request time is UNKNOWN. Its current presence is not evidence that the named field was available then. On 1,506/2,880 rows, exact `openInterest == 2*singleOpenInterest` fails. The maximum absolute residual is **0.00100001 BTC**, at most approximately **2.213×10⁻⁸ of reported openInterest**. This is compatible with quantization/representation effects, but their exact server-side cause is unproven. Do not claim exact identity with the newer field or round away disagreement to force it.

The six native ticker slices contain the old field and no `singleOpenInterest`. All **1,326 anchored native-to-normalized OI comparisons** agree exactly. Normalized `open_interest` copies the old field directly; it is not automatically halved. One July snapshot arrived after a newer delta with a native cross-sequence rollback; its normalized generation timestamp differs by **199 ms**, while OI agrees. This remains an explicit source-clock/state qualification issue, not an automatic normalization pass. No exactly coincident native-generation/REST sample timestamps were available for a strict same-time REST/ticker comparison; we did not fit an offset or scale.

This separates three claims: historical REST field semantics are documented; archived native/normalized value mapping is observed; complete production timestamp/state qualification remains unfinished. See [the detailed semantics report](btc/review_runs/bybit-free-data-feasibility-20260912-v1/semantics/OI_SEMANTICS.md).

## Trades, quotes and availability

| Date | Official trade rows | Tardis trade rows | Tardis quote rows |
|---|---:|---:|---:|
| 2025-03-01 | 1,418,706 | 1,418,703 | 1,714,045 |
| 2025-07-01 | 1,116,387 | 1,116,359 | 2,643,080 |
| 2025-12-01 | 3,669,773 | 3,669,821 | 1,978,764 |

Full reconciliation pairs **6,204,834 trade IDs**. Every paired side, decimal price and decimal size agrees exactly. Official event times are 0–900 microseconds later; flooring to milliseconds matches Tardis for all paired records, with original precision preserved. The sets nevertheless differ: March has three official-only trades at the last second; July has 29 official-only **intraday** records plus one prior-day Tardis record; December has 48 Tardis-only **intraday** records. Boundary partitioning cannot explain all differences. Their origin remains UNKNOWN; neither archive is declared interchangeable or lossless.

Official trades have event timestamps but **no collector receipt timestamp**. Tardis uses receipt-day file boundaries. Detailed ID/source parity is preserved with the final qualification evidence; no resulting selling fraction or outcome was calculated.

The ten normalized ticker days contain **2,340,280 rows**. Their timestamps can advance when another state field changes while OI is carried. Such carry is usable only after an OI anchor and qualified uninterrupted native state—not simply because another normalized row arrived. Current REST retrieval cannot replace historical receipt evidence.

The three quote files contain **6,335,889 rows**, with no locked/crossed rows in the parser's check. They are Bybit reconstructed BBO from Tardis's book processing, not Binance spot quotes and not a raw exchange-native BBO tape. This sample says nothing about protected OB0. The frozen flow control is **Bybit total sell-aggressor flow**; the frozen spread control is **Binance spot L1**. Buying four Bybit datasets would still not supply that Binance source. [Dataset distinctions](https://docs.tardis.dev/downloadable-csv-files/data-types.md).

These observations do not prove every historical row was known on our infrastructure before T, nor that gaps/revisions are harmless. The current sample supports source feasibility, not a pass of every future implementation/availability gate.

## How much full data is actually needed?

For the unchanged proposed population, request a **narrow instrument/channel scope**, not every instrument or an L2 order-book history:

1. BTCUSDT Bybit native `allLiquidation`, with original receipt/generation/update times and incident/disconnect metadata, through March–December 2025 and necessary prior-hour context.
2. BTCUSDT native `tickers` with OI anchors and receipt/state continuity. Free REST is useful for historical values and cross-checks but does not independently satisfy the first-receipt requirement.
3. Bybit public trades for the fixed selling control. Official archives offer a free event-time route; whether they can replace receipt-bearing native trade capture needs an explicitly reviewed availability bridge. Do not silently assume it. If that bridge cannot be justified, include native `publicTrade` in the same source scope.
4. Separately qualified Binance spot L1 for the fixed spread control, and the already-frozen consumed spot bar input. Bybit quotes are unnecessary as a substitute because they are the wrong control venue.

The minimum calendar envelope is **February 28–December 31: 307 days** (306 population days plus 24-hour context), subject to obtaining a valid initialization anchor. Ten first-day samples leave **297 non-free-sample days in that envelope**. More history or symbols are not justified merely to expand the research space. Conversely, buying only favorable or high-liquidation days would select the sample and destroy the intended comparison.

Ten free days cover only **3.268%** of the population calendar, cannot yield 60 distinct event dates, and supply only 3.2–3.3% of each month before prior-day requirements. They cannot satisfy the existing design, however many records they contain. This conclusion requires no new event or return test.

Indicative compressed sizes, extrapolated from the downloaded first days only:

| Source/type | Observed daily size range | Mean-size estimate for 307 days |
|---|---:|---:|
| Normalized liquidations | 2.6–76.5 kB | 9.3 MB |
| Normalized derivative ticker | 1.78–4.52 MB | 0.89 GB |
| Official trades, free route | 39.6–128.5 MB | 22.46 GB |
| Normalized Tardis trades | 30.7–99.8 MB | 17.42 GB |
| Bybit reconstructed quotes, not the required Binance control | 20.9–29.9 MB | 7.78 GB |

These decimal-byte estimates are not whole-history measurements, vendor quotes or upper bounds. First days may be unrepresentative; raw envelopes, initialization and incident evidence add overhead. Full native replay at ten-minute slices would require roughly 44,208 requests per channel-filter bundle over 307 days. Storage size is not what establishes licensing price or data quality.

## Spending versus forward collection

**Do not spend approximately $300 solely because the normalized liquidation file is small or because a positive alpha story sounds plausible.** A current price/entitlement quote has not been established. The historical scope must include the required channels, raw receipt/state evidence and lawful durable retention; a liquidation-only purchase may leave the test blocked. No purchase or quote request was sent.

Before any spending decision, review the source derivation, remaining timestamp/sequence/trade-parity findings, and the missing Binance L1/availability bridge. Then compare the actual complete source/rights offer with a separately frozen forward collection plan. Forward collection substitutes waiting and operational work for some historical-access cost; it does not produce the old historical experiment immediately, guarantee 60 usable event dates, or authorize using existing protected 2026 data. No recorder or parallel alpha search starts in this stage.

## Evidence and disposition

Original bodies, headers/statuses, hashes, scripts, commands/exit codes, historical documentation commits, scope/addendum and source-only parser outputs are preserved in the run directory. Seven source-qualification executions exited zero; eight historical-document assertions passed. These are not strategy/synthetic tests or a declaration that all future source gates pass. Earlier Phase 1 files remain byte-identical. Git repository identity remains UNKNOWN; exact local and pinned external source bytes provide provenance. Full-day contents were checked, but selected native slices are not represented as a full losslessness audit.

The numerical outputs here concern **source counts, identity, timestamps and storage**. No 0.5%-OI event membership, future spot return, matched payoff, bootstrap draw or strategy result was calculated. There is no empirical claim that the proposed recovery exists. The need for historical receipt coverage is real; the absence of the newer field in 2025 is not itself a fatal obstacle.

**NEED PAID DATA**

**STOP_FOR_CHATGPT_REVIEW**
