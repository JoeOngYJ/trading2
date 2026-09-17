# Alpha Discovery Phase 2

Run: `prospective-and-alpha-phase2-20260912-v1`. Evidence class: mechanism and source review; **zero new market-outcome trials**.

**No free/cheap historical candidate currently clears the information and capture gates.** Three mechanisms were examined. Public sources establish that reports are published and contracts expire; they do not establish a usable prediction after our decision delay and costs. I recommend selecting **NONE**, rather than turning free data into another indicator search.

Existing tested profitability does not establish accepted alpha. Breakout remains closed as an entry-information hypothesis. Funding timing, aggregate-flow reversal, BTC/ETH catch-up, derivatives crowding, spot/perpetual continuation and the other reviewed exclusions remain closed. HAR is not directional alpha; top-two lacks a qualified point-in-time universe. Their historical results were not rerun or changed.

The forced-liquidation idea now belongs to the separate [prospective collection lane](PROSPECTIVE_LIQUIDATION_COLLECTION_PLAN.md). The $22,800–$26,400 annual historical routes are commercially rejected by the user for this unproven hypothesis. No purchase, quote submission or provider contact occurred. Phase 2 did not wait for a quote and did not read the prospective or protected datasets.

## What information is available at low cost?

| Information | Existing or free source | What is still missing |
|---|---|---|
| BTC spot reference prices | Reviewed consumed Binance 2017–2025 five-minute input, 878,985 rows / 34 source segments | Continuous coverage and measured historical receipt are not established by OHLC; preserve segments and prior contamination. No prices reopened here. |
| CME participant-category positioning | Existing consumed CFTC TFF input; free official historical exports/API | First-release values, exceptional release clocks, trading motive and corresponding spot/cross-market hedges. |
| Contract expiry and settlement rules | Free official exchange specifications and notices | Effective-dated historical rules plus signed, remaining participant hedge/roll inventory. |
| Initial CPI releases | Free BLS archived releases, retaining release-specific values | A verified extraction/availability ledger, not a latest-revised CPI series. |
| Prior public inflation forecasts | Cleveland Fed daily nowcasts and documented real-time published history | Exact downloadable vintages/first-publication provenance for the chosen series and dates; these are model forecasts, not a market-consensus series. |
| Synchronized cross-venue quotes, signed option inventory, residual ETF orders | Not qualified in the reviewed inventory | A cheap price series does not recover historical executable quotes or private participant state. No further proxy candidate was created. |

The inherited inventory and contamination analysis come from [Phase 1](ALPHA_DISCOVERY_PHASE1.md), [free feasibility](BYBIT_FREE_DATA_FEASIBILITY.md) and the [acquisition-route review](FORCED_LIQUIDATION_DATA_ACQUISITION_ROUTE.md). Newly inspected external material is documentation/literature, not repository alpha evidence.

## Candidate 1 — a public CME positioning disclosure

**Screened out.** A weekly report is genuine participant-category information, but the same CFTC source already entered the rejected crowding work. A signed change does not become a new mechanism merely by replacing an absolute z-score.

| Component | Operational input or unresolved requirement |
|---|---|
| **X** | First-published weekly change in CME Bitcoin TFF futures-only leveraged-fund net contracts: `(long − short)` in the new vintage minus the corresponding previous first release. No qualifying threshold was selected or calculated. |
| **T** | Actual first-publication timestamp of that vintage, with a separately qualified receipt delay. Tuesday position date is not T. Exact historical first-release ledger: **UNRESOLVED**. |
| **Y** | Incremental subsequent BTC spot return versus publication-time, pre-T market-state and carry-matched observations. Direction: **UNRESOLVED**. |
| **H** | **UNRESOLVED**: no identified constraint pins a later one-hour, one-day or one-week effect. Testing all three would be searching. |
| **Z** | Disclosure might reveal risk demand not previously known. However, net futures positions mix directional trades and hedged/carry activity; forced future spot demand is **UNRESOLVED**. |
| **A** | Public access and small own impact are possible; an advantage over automated users of a scheduled report is **UNRESOLVED**. |
| **C** | Cash-and-carry, other hedges, trend exposure, changing classifications and trades completed days before release. |
| **B** | Stop unless an independently justified sign/horizon and public activity distinction exist and first-release values/clocks qualify. Those requirements do not pass. No outcome test is nominated. |

Normal COT publication is Friday afternoon Eastern for Tuesday positions, but exceptions matter. The January 31, 2023 report was delayed until February 24 after the ION incident; 2025 also had reporting delays during the appropriations lapse. The previously used fixed report-date-plus-four-days assumption is not universally causal. Preserve the old **REJECTED** disposition and record this source limitation; it is not permission to repair and rerun crowding. [Release schedule](https://www.cftc.gov/MarketReports/CommitmentsofTraders/ReleaseSchedule/index.htm), [special announcements](https://www.cftc.gov/MarketReports/CommitmentsofTraders/HistoricalSpecialAnnouncements/index.htm).

TFF classifies traders, not each trade's economic purpose. Its spread categories do not identify a spot hedge. A short-futures/long-spot carry position supplies a concrete competing interpretation of aggregate shorts. [TFF explanatory notes](https://www.cftc.gov/idc/groups/public/@commitmentsoftraders/documents/file/tfmexplanatorynotes.pdf), [BIS Crypto carry](https://www.bis.org/publications/working-paper-1087-crypto-carry).

Data price is **$0** for the official aggregate. A publication/vintage audit would plausibly take one or two researcher-days, an estimate rather than completed qualification. The BTC-specific first usable observation and a complete vintage archive remain unverified. Realistic spot friction remains **30/40/80 bps**. A cheap series with no defensible sign or horizon is not a cheap alpha experiment. Detailed evidence: `phase2_positioning/FINDINGS.md` in the run.

## Candidate 2 — signed spot hedge unwinds during derivative expiry

**Screened out.** Contract expiry creates a real constraint conditional on a known position. A public expiry calendar does not reveal the remaining aggregate spot buy or sell order.

| Component | Operational input or unresolved requirement |
|---|---|
| **X** | Publicly known remaining **net BTC spot buy quantity** required to close identified short spot hedges of expiring Deribit BTC exposures during its fixing window, net of already executed hedges and rolls. That signed quantity is **UNAVAILABLE / UNRESOLVED**. Unsigned OI is not X. |
| **T** | Verified first-publication/receipt strictly before the relevant fixing window. A public historical residual-demand disclosure was not established. |
| **Y** | Positive incremental BTCUSDT spot return during that fixing versus calendar/state-matched observations without the identified buy requirement. |
| **H** | The documented **30-minute fixing window**, conditional on effective-dated contract rules. An executable start cannot be specified without X's publication clock. |
| **Z** | Expiration can remove a hedge requirement, causing a constrained buy-to-close order. Publicly observable net remaining demand is **UNRESOLVED**. |
| **A** | Small size limits own impact; capturing a public, anticipated fixing flow after costs remains **UNRESOLVED**. |
| **C** | Opposite inventory, offsetting clients, cash-and-carry spot sales, early hedging, rolls, different hedge venues and ordinary clock effects. |
| **B** | Stop if signed remaining spot demand and first-publication time cannot be reconstructed. Do not substitute a Friday/expiry dummy, assume dealer gamma or buy a public option tape hoping it supplies private inventory. |

Two markets can have identical public strike/expiry/OI while the dealer is long calls in one and short calls in the other. The corresponding hedge unwind has opposite signs. More accurate unsigned OI does not solve that identification problem. Public summary APIs expose OI; authenticated position APIs describe private accounts, not a public aggregate hedge ledger. [Deribit public summary](https://docs.deribit.com/api-reference/market-data/public-get_book_summary_by_currency), [position schema](https://docs.deribit.com/api-reference/account-management/private-get_positions). No private endpoint was called.

Deribit documents settlement delta decay. CME cash settlement does not itself require net spot buying. Current Deribit delivery rules changed in 2026, so current mechanics cannot silently be projected into 2025. [Delta decay](https://support.deribit.com/hc/en-us/articles/25944751433757-Delta-decay-during-settlement), [CME original contract filing](https://www.cmegroup.com/content/dam/cmegroup/market-regulation/rule-filings/2017/12/17-417S.pdf), [Deribit delivery change](https://insights.deribit.com/exchange-updates/change-to-option-delivery-process/).

Calendars and rules cost **$0**, with hours of source work; the missing signed inventory/remaining orders have no established free or priced acquisition route. Buying a $20k option history would not necessarily recover them. No qualified historical option panel exists locally. There is no established 30-minute effect above the unchanged **30/40/80-bps** spot costs. A volatility-at-expiry study would ask another question and is not quietly nominated as directional alpha. Detailed evidence: `phase2_settlement/SETTLEMENT_MECHANISM_SCREEN.md`.

## Candidate 3 — delayed BTC response to a negative inflation forecast error

**Not selected.** This is the closest of the three to a cheap observable event. Its weakest link is a reason for **remaining** profitable information after publication and our delay, rather than the general fact that news can move markets.

The following operational sketch makes the candidate assessable; it is **not a frozen, authorized outcome experiment**. The 0.10-percentage-point cutoff and one-hour horizon are unendorsed, untested choices without mechanism-derived calibration, not prospective commitments or claimed optimal values.

| Component | Operational sketch |
|---|---|
| **X** | Initial released US headline seasonally adjusted month-on-month CPI minus the last Cleveland Fed nowcast for that same measure demonstrably published by the end of the preceding US business day is **≤ −0.10 percentage points**. This is explicitly a forecast error relative to one public model, **not** market-consensus surprise. |
| **T** | Actual BLS release time + five minutes, using the initial release and a qualified prior-day forecast vintage. A scheduled timestamp alone is insufficient for delayed releases. Historical availability bridge: **UNRESOLVED**. |
| **Y** | BTCUSDT spot simple return from release +10 minutes to release +70 minutes, compared with qualified CPI-release observations matched on pre-release inflation/market state. Positive direction only. |
| **H** | Exactly **60 minutes** after the delayed reference start. No instantaneous announcement jump is credited to this target. |
| **Z** | Lower-than-forecast inflation might relax expected rate/financing constraints and cause delayed risk-asset demand. The claim that meaningful adjustment remains after ten minutes is **UNRESOLVED**. |
| **A** | Public sources are inexpensive and a small order has low own impact. An information, latency or slow-adjustment advantage over professional announcement traders is **UNRESOLVED**. |
| **C** | The model error is not investors' surprise; adjustment may finish immediately; ordinary risk-on beta, other simultaneous releases, inflation-risk compensation or persistent model bias could explain a relationship. |
| **B** | Stop before an outcome study unless a prior-vintage/actual-release ledger and a concrete post-delay capture mechanism are established. Even then, a reviewed minimal test must require economic improvement after **30/40/80-bps** frictions, not a positive instantaneous reaction. No horizon/threshold switching after results. |

The free BLS archive distinguishes old release copies from revised databases. Cleveland Fed documentation describes daily updates around 10:00 Eastern; a same-day update can occur after an 08:30 CPI announcement and cannot be a pre-release forecast. Its 2023 assessment distinguishes historical reconstruction from real-time published nowcasts beginning in 2013:Q3. That supports a potentially useful source lead, not a qualified local vintage panel or proof that every current download preserves first publication. No vintage dataset was downloaded. [BLS archive](https://www.bls.gov/bls/news-release/cpi.htm), [nowcast documentation](https://www.clevelandfed.org/indicators-and-data/inflation-nowcasting), [real-time assessment](https://www.clevelandfed.org/publications/economic-commentary/ec-202306-real-time-assessment-inflation-nowcasting-cleveland-fed).

The mechanism literature is not uniformly favorable. A New York Fed study reports little systematic Bitcoin response to macroeconomic news in its sample. Mykola Pinchuk finds a negative reaction to positive inflation surprises but does not support interest-rate exposure as its explanation. Neither establishes positive **post-ten-minute** expectancy from this particular forecast error after retail costs. Their different samples and surprise definitions cannot be combined into a claimed repository edge. [New York Fed Staff Report 1052](https://www.newyorkfed.org/research/staff_reports/sr1052), [Pinchuk, Bitcoin Does Not Hedge Inflation](https://arxiv.org/abs/2301.10117).

The source lead costs **$0**, but date/vintage qualification and release exceptions likely require one or two researcher-days. This is an estimate. Existing 2017–2025 spot data could support later reference measurements only where continuous and authorized; no later data would be opened. At monthly frequency that window has at most 108 release slots before considering scope, interruptions, event filtering and coverage, so effective sample size cannot be assumed large. The event count was not computed. Historical announcement consensus and a first-receipt archive are not qualified substitutes already in hand.

I do not recommend spending those days on a return study yet: data accessibility alone does not supply the missing post-delay mechanism. Source qualification would be necessary but is not the sole blocker. This is why the final disposition is B rather than suggesting that one more download automatically makes a test worthwhile. This is a resource-allocation judgment about these particular formulations; a cheap falsification test need not first prove profitability or causality. It needs a sufficiently concrete, plausible prediction worth trying to disprove.

## Candidate comparison and data-cost penalty

Scores are judgments: 0 = absent/weak, 3 = strong. The cost penalty runs in the opposite direction: 0 = no material cash purchase; 3 = unavailable/private or expensive information that still may not identify X. No total score overrides a failed information gate.

| Dimension | Positioning disclosure | Signed expiry unwind | Delayed CPI forecast error |
|---|---:|---:|---:|
| Economic mechanism for the specified future outcome | 0 | 2 conditional on hidden inventory | 1 |
| Pre-outcome observability | 1 | 0 | 2 conditional on vintages |
| Data quality | 1 | 0 | 1 |
| Magnitude plausibility after costs | 0 | 0 | 1 |
| Cheap, meaningful falsifiability | 1 | 1 at source gate | 2 conditional on source/mechanism |
| Independence from closed repository families | 0 | 2 with actual signed demand | 3 |
| Practical capture advantage | 0 | 0 | 0 |
| Small-capacity relevance | 1 | 1 | 1 |
| Eventual confirmation feasibility | 2 | 0 | 2 |
| **Data-cost penalty** | **0 for aggregates; missing motive is not for sale here** | **3** | **0 cash; nontrivial vintage effort** |

| Candidate | Required free information | Missing information / main risk | Decision |
|---|---|---|---|
| CFTC disclosure | Official category totals and actual publication records | Same consumed source; carry versus direction, first vintages and horizon | Screen out; do not reopen crowding. |
| Expiry unwind | Contract rules/calendar and spot references | Signed remaining hedge/roll demand; expensive public tapes do not reveal it | Screen out at observability. |
| CPI forecast error | Initial BLS release and pre-release public nowcast vintage | Credible delayed capture after ten minutes; consensus and beta confounding | Not selected; cheap source is insufficient reason for a test. |

This ranking penalizes both money and hidden information. We will not replace the rejected expensive acquisition with a different expensive tape, nor with a cheap proxy that changes the mechanism.

## Selected cheap historical candidate and experiment

**Selected: NONE.** No X event set, target, matching graph, bootstrap, account simulation or strategy was implemented. There is no executable experiment proposal to approve in this Phase 2 packet.

Before any of these screens could become a test, the missing participant/availability distinction and one economic direction/horizon would need to be specified without viewing outcomes. An appropriate baseline must address the main alternative: carry exposure for positioning, signed inventory/seasonality for expiry, and public expectation plus broad risk response for macro news. We do not invent unobservable matching variables and call the design controlled.

A future accepted source lead would then need one frozen population, actual T, raw Y, matching rule, dependence treatment, sample floor and economic hurdle. The current negative screen does not authorize that next stage automatically. A supported development result would justify only independent confirmation or a narrowly specified economic bridge, not strategy optimization.

## Contamination, record and stopping decision

No existing protected 2026/OB0/L2 payload was read, no new market dataset acquired and no prospective capture run. Public documentation/searches incidentally show example numbers, current macro tables or previously published research results; those were not used as repository observations or to select an empirical winner. The prospective lane has no first observation yet. Consumed 2017–2025 BTC and CFTC history would remain development evidence if later authorized; changing predictor names does not restore independence.

The old CFTC release-delay defect is recorded in the ledger as a source caveat. Prior dispositions remain unchanged. Unknown prior trials remain UNKNOWN. Source registers, inspected-source hashes, host/config metadata, synthetic collector qualification and separate workstream dispositions are preserved under `research/btc/review_runs/prospective-and-alpha-phase2-20260912-v1/`. Research tracker status: **STOP_FOR_CHATGPT_REVIEW**.

**B. NO FREE/CHEAP HISTORICAL HYPOTHESIS IS CURRENTLY STRONG ENOUGH**
