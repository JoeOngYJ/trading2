# Research and Backtest Tracker

Last reviewed: 2026-09-10

Consolidated BTC program review: `research/btc/BTC_PROGRAM_REVIEW_2026_09_10.md`.
Summary only; no new market run or acceptance changes.

Current continuation: R1-v3 precision qualification passed; R2-v2 reconciled201 archived trades
and1005 comparisons with errors <7.3e-13 USDT. A0 independently confirmed execution chronology,
close timestamps and future-segment boundary concerns using synthetic probes. Next freeze
execution correction rules before synthetic implementation/historical replay. See
`research/btc/reports/BTC_ACCOUNTING_RECONCILED_EXECUTION_AUDIT_RESULT.md`.

R2-v1 blocked at numeric compatibility after source checksum/structure gates passed. All201
quantities exceed R1 fractional precision; no accounting or returns computed. Frozen result:
`research/btc/reports/BTC_R2_V1_RESULT.md`. Next requires a wider-domain synthetic successor
and new replay identity, not rounding archived values.

R2-v1 archived replay rules frozen before rows; next synthetic implementation/review.
See `research/btc/reports/BTC_ARCHIVED_BREAKOUT_R2_FREEZE.md`.

This tracker is the hand-off point for strategy research. It is deliberately separate
from the production/soak status: no item here authorizes live orders or changes to the
active soak stack.

## E0-v12 final review: custom C0 architecture closed

R1-v2 explicit-fill bookkeeping now passes independent review and eight literal scenarios plus
domain, discrepancy and maximum-count Fraction tests. V1 rejected and preserved for insufficient
numeric precision. Next freeze archived-trade replay boundaries and synthetic tolerances; no
trade rows or market data have been accessed. `research/btc/reports/BTC_REFERENCE_R1_RESULT.md`.

Source-only reconciliation review completed. The legacy fixed breakout differs from R0 in clock,
combined costs, sizing, stops and terminal handling. Prior golden-metric checks establish saved
report regression, not a new historical execution replay. Next: synthetic explicit-fill accounting
R1, followed by separately frozen archived-trade arithmetic and execution audits. See
`research/btc/reports/BTC_REFERENCE_BACKTESTER_R1_RECONCILIATION_PLAN.md`. No rows were opened.

R0-v1 implementation completed: 17 literal cases and four test methods pass; independent review
passed after pre-freeze rounding and Decimal-context corrections. Accepted only as a synthetic
accounting reference. See `research/btc/reports/BTC_REFERENCE_BACKTESTER_R0_V1_RESULT.md`.
Next plan the requirements for one existing spot-control reconciliation; historical inputs remain
blocked until missing execution conventions are separately qualified.

Continuation: R0-v1 contract and 17 literal synthetic accounting cases are now frozen under
`research/btc/contracts/btc-reference-backtester-r0-v1-input-manifest.json`. No engine has been
implemented or accepted. Next is implementation and independent event-by-event reconciliation.

Two fresh independent reviewers rejected the intact E0-v12 bundle despite nine preflight checks
and 33 passing tests. The future contract/registry/manifest checksum graph is cyclic or
underspecified; the path scan exempts arbitrary invalid directories; and claimed semantic-only
tests rely on document pins. Apply the frozen final-attempt stop rule. No E0-v13 or C0
implementation is permitted. Preserved evidence:
`research/btc/invalid/unified-backtest-engine-e0-v12-final-review-failure/README.md`.
Next is a small synthetic BTC spot reference ledger with independently hand-calculated cases,
under `research/btc/reports/BTC_REFERENCE_BACKTESTER_NEXT_PLAN.md`. Strategy evaluation remains
blocked and no strategy is accepted. This engineering rejection adds no new profitability result.

## BTC multi-horizon perpetual trend — v5 rejected and closed

`btc-multihorizon-perp-trend-v5` completed the frozen run and is rejected. At 30 bps it returned
48.30% in 2020–2023 development but lost 6.41% in consumed 2024–2025; both 2024 and 2025 were
negative. Severe-cost stability lost 12.77%. It failed stability, control, bootstrap,
concentration, annual and severe gates. The simple 28-day control earned more in development but
also lost in stability; it remains a control, not a candidate. The replay is byte-identical. Zero
arms are accepted and no strategy experiment is active.

V1 is closed before signal
or return access because the volatility estimator was not uniquely specified. V2 binds the exact
daily sampling, initialization, recursion, funding, reversal, risk, gap and control-RNG semantics
without changing the hypothesis or economic parameters. T1 passed 15 synthetic tests and an
independent audit; zero historical rows or returns were opened. T0 previously passed with 52,608
continuous official hourly bars, 6,576 complete funding events, zero boundary gaps, 2,107 causal
daily decisions and no 2026 access. The first eligible 84-day decision is 2020-03-26 00:05. A
preliminary off-by-one audit assertion is preserved; corrected T0-v2 changed no frozen strategy
field and calculated no return. A separate
`retail-btc-directional-perpetual-research-v1` mandate now permits only offline, zero-capital
simulation of BTCUSDT USD-M perpetual long, short or flat positions at no more than 25% absolute
notional. It does not alter the existing spot or delta-neutral mandates and authorizes no account,
credential, exchange paper order, production integration or live capital.

The hypothesis, daily 00:05 decision clock, next-01:00 fill, completed 7/28/84-day returns,
volatility standardization, equal weights, +/-0.25 flat band, fixed sizing, downward-only EWMA
risk overlay, exact funding, 30/40/80-bps costs, conservative margin stress, controls, partitions,
attribution and rejection gates were frozen before opening a strategy return. The experiment is a
continuous-clock directional-trend test—not another sparse breakout catalogue—and remains in the
same economic family as breakout/SMA. Do not tune or regime-rescue this family.
No arm is accepted and `actionable_arm_id` remains `no_trade`. Plan:
`research/btc/reports/BTC_MULTIHORIZON_PERP_TREND_V2_T1_RESULT.md`.

## BTC causal CUSUM trend onset — TNE1-A v2 rejected on sample gates

`btc-cusum-trend-onset-tne1-v2` was frozen before historical trigger access as a materially
different successor to the count-blocked compression catalogue. It tests distributed positive
hourly drift with an online Page CUSUM (`k=0.25`, `h=4.5`, clipped at two prior-volatility
standard deviations), not compression, a range high, a moving average or a one-candle expansion.
A single hour cannot trigger it. The exact trigger, inclusive 72-hour suppression, label-blind
count gates, normalized continuous 72-hour target, M0/M1/M2 nested chronological comparison,
three-month calendar-block inference and standalone positive-continuation gates are bound in
`research/btc/contracts/btc-cusum-trend-onset-v2.json`. Synthetic design qualification and 46
focused tests pass; independent pre-source audit found no implementation blocker.

The one permitted TNE1-A trigger-only run found 229 model-ready events versus 300 required and
only 75 before 2021 versus 150. It also missed 2021 and 2022 annual minima with 29 and 27 events;
2023--2025 and both concentration gates passed. Reject and close this ID. Do not materialize
labels, run TNE2, lower the Page threshold, shorten suppression or weaken gates. No post-trigger
return, strategy, cost or PnL was opened. This remains negative evidence inside
`btc_directional_trend`; zero arms are accepted and `actionable_arm_id` remains `no_trade`.
Result: `research/btc/reports/BTC_CUSUM_TREND_ONSET_TNE1_V2_RESULT.md`.

The earlier `btc-cusum-trend-onset-tne1-v1` contract is preserved as preflight-invalid: its
explicit event/model binding roles did not match the event runner's legacy generic-role schema.
The failure occurred before any historical source row was deserialized and required the new v2
experiment ID.

## BTC upside compression breakout — BEX1 engineering passed; BEX2 blocked

`btc-upside-compression-breakout-v1-bex1-v5` completed its frozen, non-PnL development
catalogue on the checksummed 878,985-row 2017–2025 BTCUSDT source. Independent audit
recomputed every record/catalogue digest and reconciled all counts. The catalogue contains
92 non-overlapping setups: 46 downside invalidations, 9 setup expiries, 1 source-end and
36 upside confirmations. All 36 confirmations are model-ready; 12 reached the frozen
one-sigma continuation close first and 24 re-entered the range first.

BEX2 is hard-blocked without fitting any model because its price-blind preflight required
200 confirmations and 60 events of each cause. It observed only `36/12/24`, and 2021 had
no eligible evaluation event. Do not relax the compression, confirmation, suppression or
label definition under this ID and do not claim a strategy result: no entries, exits,
costs, positions, return or PnL were computed. The isolated M2/M3 dependency environment
passed fresh-process CPU/single-thread qualification but was not used on historical episodes.
The official-event driver foundation passes synthetic infrastructure tests; numeric driver
attribution remains blocked pending qualified official histories. Zero strategy arms are
accepted and routing remains `no_trade`. Result:
`research/btc/reports/BTC_UPSIDE_BREAKOUT_BEX1_V5_RESULT.md`.

## BTC strategy direction — upside compression breakout selected for design

`btc-strategy-directions-v1` records four price-behaviour families and eight directional legs,
but selects only `range_compression_breakout_upside_long` for the next design packet. The reserved
candidate ID is `btc-upside-compression-breakout-v1`; it is not yet a frozen or testable experiment.
All downside-breakout, pullback, consolidation-fade and failed-break reversal legs are deferred,
and short legs additionally require a new mandate. The candidate remains in the broad
`btc_directional_trend` routing family and would not be independent diversification from another
breakout or moving-average arm.

The novelty boundary requires a separately frozen pre-break compression state and post-range
upside confirmation. Changing only the fixed breakout lookback, buffer or moving-average speed is
prohibited. Before any outcome is opened, a new immutable contract must freeze compression, range,
confirmation, horizon, first eligible 5m fill, exits, sizing separation, 30/40/80-bps costs,
controls, chronology, uncertainty and rejection gates. The fixed breakout, SMA, BOCPD-gated
breakout and volatility-expansion results remain preserved controls/negative evidence; rejected
condition scores cannot rescue the new candidate. No market value, strategy PnL or 2026 holdout
was opened, zero arms are accepted and routing remains `no_trade`. Tracker:
`research/btc/BTC_STRATEGY_DIRECTION_TRACKER.md` and
`research/btc/BTC_STRATEGY_DIRECTION_TRACKER.json`.

## BTC score-combination foundation — passed synthetic infrastructure only

`btc-score-combination-foundation-v1` adds a target-aware score catalogue, causal empirical
midrank calibration and fixed convex same-target ensembles. It does not activate MCS4 or create a
master market score. Catalogue entries bind target, horizon, kind, units, evidence status and
permitted use; rejected/development scores remain diagnostics or controls. Calibration uses only
samples available by each raw score's fit cutoff and remains display/model-input metadata. An
ensemble requires at least two `benchmark` or `accepted` members with the exact same instrument,
axis, target, horizon, kind and units; unknown, stale or unusable members fail closed, weights must
be predeclared non-negative and sum to one, and every new output remains `development` with
`actionable_arm_id = no_trade`. The existing minimum-cap risk fusion is unchanged. Nine focused
and 40 adjacent tests pass with a byte-identical synthetic replay. No current rejected score was
combined, no market value or PnL was opened and no strategy action was created. The next strategy
step remains selection and freeze of one materially new BTC hypothesis. Result:
`research/btc/reports/BTC_SCORE_COMBINATION_FOUNDATION_RESULT.md`.

## BTC market-condition score program — MCS3-P/R/D/J rejected, MCS3-C blocked; branch stopped

`btc-market-condition-scores-v1` now defines a BTC condition vector rather than a universal
`bull`/`bear`/`sideways` classifier. Persistence, reversion, volatility, downside/tail,
jump/change, liquidity/cost, carry, implied-risk and optional on-chain observations have separate
targets, evidence metrics and permitted uses. Persistence and reversion are not complements;
volatility, tail, jump and liquidity forecasts are not alpha; carry is separate from the rejected
absolute-crowding mechanism. A score must pass standalone chronological information gates, and a
strategy must pass unconditioned before a score-conditioned version can run.

MCS1 passed the metadata foundation. MCS2 passes as synthetic infrastructure: immutable
target-specific score and non-aggregating panel contracts, causal completed-field extraction and
12 frozen primitives cover persistence/reversion diagnostics, realized semivariance and jump
variation, explicitly labelled low-frequency liquidity proxies, and completed funding/basis
transforms. Development/rejected scores cannot condition a strategy, probability bounds and
unknown rows fail closed, and the panel provides no universal label or vote. Eleven focused tests,
37 combined regressions and a byte-identical qualification pass.

MCS3-P is now rejected under its frozen real-data gates. The causal monthly expanding experiment
tested whether 42-return signed directional efficiency added information beyond the same completed
seven-day BTC log return. At the primary seven-day horizon, candidate MSE was 1.19% worse, its HAC
incremental-coefficient interval crossed zero, its month-block rank-IC and error-improvement
intervals were negative, buckets were non-monotone, and only four of seven annual coefficients
were positive. Overall seven-day coverage was 88.94%, below the frozen 90% gate. Secondary 4h/1d
diagnostics did not jointly pass. The replay is byte-identical. Do not tune or use this score to
condition a strategy; it remains a rejected control. No strategy, cost, PnL, 2026, partial OB0,
protected service or executable action was used. Zero arms remain accepted and `no_trade` remains
actionable. Next is a separately frozen MCS3-R reversion-information packet, not `-persistence`.
Result: `research/btc/reports/BTC_MARKET_CONDITION_SCORES_MCS3_P_RESULT.md`.

MCS3-R is also rejected under its separately frozen information gates. It tested a completed
24-hour displacement at absolute causal z-score 2 or greater against previously completed,
same-direction quiet controls matched on past realized variance. The primary one-day cohort had
300 non-overlapping events, but pooled reversal was only 12.46 bps versus the 80 bps gate; the
equal-month estimate was negative and its interval crossed zero. Downward events rebounded while
upward events continued, so the frozen symmetric mechanism failed. Matched deltas, annual
stability, best-month exclusion, strict match coverage and causal feature coverage also failed.
The favorable downside subset is post-result exploratory only and cannot be selected or tuned
under this ID. No strategy, position, execution, cost, PnL, 2026, partial OB0 or protected service
was used. MCS3-D downside/tail information is next under a new frozen contract. Result:
`research/btc/reports/BTC_MARKET_CONDITION_SCORES_MCS3_R_RESULT.md`.

MCS3-D is rejected under its frozen joint downside/tail gates. The corrected one-day log-HAR
negative-semivariance forecast was informative: QLIKE improved from `-6.609755` to `-6.769489`,
its equal-month improvement interval was `[0.112791, 0.248077]`, MSE fell 17.54%, and realized
risk was monotone across forecast quartiles. But scaling the historical VaR/ES benchmark by that
forecast worsened both FZ0 (`-2.631575` versus `-2.640870`) and pinball loss (`0.003698` versus
`0.003661`). FZ0 uncertainty crossed zero, best-three-month exclusion was negative, and only two
of seven annual and two of seven leave-one-year-out joint comparisons passed. Coverage and
calibration passed but cannot rescue worse proper loss. An independently found preliminary
historical-loss eligibility bug was corrected without changing the frozen contract; the invalid
first run remains preserved and excluded. Preserve the favorable semivariance result only as a
diagnostic inside a rejected joint experiment; do not tune it or map it to a risk cap. No
strategy, position, cost, PnL, 2026, partial OB0 or protected service was used. MCS3-J is next
under a separately frozen contract. Result:
`research/btc/reports/BTC_MARKET_CONDITION_SCORES_MCS3_D_RESULT.md`.

MCS3-J is rejected under its frozen jump/change information gates. On 12,118 common primary
four-hour rows it observed 99 dominant-discontinuity proxy events (0.8170% prevalence). The fixed
lambda 0.94 EWMA was worse than the rolling 180-block control on average precision (`0.013570`
versus `0.015547`), Brier (`0.008304` versus `0.008102`), log loss (`0.063402` versus `0.046138`),
intensity MSE (`0.013082` versus `0.012910`) and intensity MAE. Exact-seed month-block intervals
for Brier, log-loss and intensity-MSE improvement were wholly negative, every annual and
leave-one-year-out comparison was negative, and best-three-month exclusions remained negative.
The 99-event count also missed the 100 minimum and 2024/2025 missed per-year counts, but the broad
loss failure makes this more than a near-threshold rejection. Intensity quartiles were monotone
and unconditional calibration passed, but neither rescues worse comparative forecasts. Twelve
focused tests, 35 adjacent regressions and a byte-identical four-file replay pass. Do not tune or
map this score to a cap. MCS4 is not permitted because no MCS3 score passed. Result:
`research/btc/reports/BTC_MARKET_CONDITION_SCORES_MCS3_J_RESULT.md`.

The metadata-only MCS3-C readiness audit is complete and blocks activation of the named net-carry
score. Funding (6,576 scheduled events), perpetual execution, recovered mark and recovered index
histories pass; matched spot remains usable only with explicit segment resets, and the single
premium-index gap is optional for a basic score. Four independent requirements fail: no
effective-dated historical spot/perpetual fee schedule, no effective-dated maintenance-margin
brackets, no historical contract/funding/liquidation/ADL rule ledger, and no frozen collateral-
financing treatment. Current snapshots, generic 30/40/80-bps scenarios and development-only
margin stress assumptions cannot be projected backward as historical net-carry economics. The
rejected carry-v1 thresholds/lookbacks remain closed and cannot be rescued by relabelling them as a
score. Nine tests and a byte-identical report/manifest replay pass. MCS3-C was not activated; MCS4
remains blocked and the current score-panel branch stops. Result:
`research/btc/reports/BTC_MARKET_CONDITION_SCORES_MCS3_C_READINESS_RESULT.md`.

## Cash-ETF successor — pragmatic C1 ledger passed; no alpha tested

`retail-cash-etf-multi-strategy-v1` replaces the proposed direct-futures lane. C0 passed after
freezing an unlevered long/flat, no-futures mandate; the non-executable SPY/EFA/IEF/TLT/GLD/DBC/BIL
proxy set; GBP/USD conversion; exact UK candidates SWDA/IGLT/SGLN/AGCP; chronological boundaries;
and both `cash-etf-slow-trend-proxy-v1` and `cash-etf-turn-of-month-proxy-v1` before ETF economics.

The C1 prerequisite bound 22 existing normalized sources and produced 66 immutable development,
validation and historical-confirmation files by extracting only `session` or `action_date`. The
first official audit proved provider omissions in SPY, IEF, TLT and BIL while EFA distributions
and BIL's 2017-11-30 1-for-2 reverse split passed. The final issuer-led v2 successor acquired 17/17
official sources and now closes DBC distributions: SEC annual reports cover all 2009–2023 years,
and its four nonzero events match issuer amounts and pre-2024 NYSE Arca rule-derived ex-dates.
Those strict archive-completeness findings remain preserved. A separately frozen pragmatic
successor then passed C1 as development-data infrastructure: seven aligned GBP total-return
ledgers contain 2,516 sessions from 2009-01-02 through 2018-12-31; issuer distributions replace
provider dividends; BIL's reverse split is exact; and four missing GBP/USD dates use official
Federal Reserve H.10 observations with ten-day availability delays. No 2019+ numeric row was
deserialized. No strategy metric, trade or PnL was computed, and no proxy, arm or execution
instrument is approved. See `docs/CASH_ETF_C1_PRAGMATIC_ACTION_LEDGER_RESULT.md`.

The separately frozen `cash-etf-c1-corporate-action-archive-availability-v1` public-source check
found no purchase-eligible archive under the older strict gate. NYSE, ICE, LSEG and FactSet remain contact-required because
public materials do not jointly confirm the exact seven-symbol 2009-2023 boundary, scoped sample,
zero-event semantics, durable private-research retention and price. EODHD is rejected for this
role because its terms require deletion after subscription expiry; Massive is rejected under the
reviewed public display-use license. No account, trial, contact or purchase occurred. This
negative sourcing result no longer blocks the explicitly relaxed pragmatic ledger. The next
permitted action is to freeze C2 separately; do not unlock 2019+ data. See
`docs/CASH_ETF_C1_CORPORATE_ACTION_ARCHIVE_AVAILABILITY_RESULT.md`.

## Current research hypothesis

No score or strategy experiment is active. MCS3-P, MCS3-R, MCS3-D and MCS3-J are rejected and
cannot be tuned or combined. The MCS3-C readiness audit failed on historical economics and rules,
so MCS3-C was not activated. MCS4 panel/cap construction is blocked because it requires at least
one accepted standalone score. Stop this score-panel branch and return to one materially new,
separately frozen BTC strategy hypothesis. Historical fee/margin/rule acquisition may be a future
data workstream, but it is not justification to keep building detectors. No score result creates
direction, a position, PnL or executable authority.

**BTC point-in-time on-chain source feasibility:** `btc-onchain-source-feasibility-review-v1`
completed a public-document-only review before any on-chain strategy hypothesis. No provider is
approved for historical strategy evaluation. CryptoQuant explicitly says its exchange-flow
history is not point-in-time accurate because wallet clustering revises historical values;
Professional currently costs USD 99 monthly but its API comparison limits history to one year.
Glassnode provides the strongest immutable point-in-time semantics, but recorded `computed_at`
only from September 2024 and says most PiT metrics have limited history; its Professional price
and permanent exported-data rights require clarification. Coin Metrics does not publicly prove
historical label-version semantics. Nansen's new June 2026 backtesting API claims historical
label-as-of reconstruction and offers free trial credits/USD 49 Pro access, but its public docs do
not yet bind that claim to an exact aggregate BTC exchange-flow endpoint, history boundary or
availability timestamp. Do not buy data or freeze a signal yet. The only justified successor is a
new, data-only Nansen free-tier pilot or written clarification; failure closes retrospective
on-chain flow research and redirects the program to another materially distinct strategy family.
No API key, metric value, strategy, PnL, 2026 strategy evidence, partial OB0 data or protected
service was accessed. Result:
`research/btc/reports/BTC_ONCHAIN_SOURCE_FEASIBILITY_REVIEW.md`.

**BTC HAR-RV standalone risk forecast:** `btc-har-rv-risk-forecast-v1` is rejected at its
predeclared coverage gate, although all frozen forecast-quality gates passed. The causal monthly
expanding log-HAR used complete same-segment five-minute realized variance at one-, five- and
22-day horizons and compared only common rows against the mandatory close-return EWMA and a
same-input RV EWMA. On 2,011 one-day rows its QLIKE was -6.173005 versus -6.091550 and -6.086221,
its MSE was 12.68% and 27.38% lower, it won all seven calendar years, and its paired month-block
QLIKE-improvement interval versus RV EWMA was `[0.06253, 0.12323]`. Seven-day QLIKE and MSE also
beat both controls on 1,921 rows. However, the 34 absent/incomplete/cross-segment RV days propagate
through the 22-day HAR and 30-day RV-EWMA reset windows: 2021 one-day coverage was 49.59%, while
2019 and 2021 seven-day coverage were 49.86% and 41.37%, below the frozen 50% per-year gate.
Do not relax or tune v1. It creates no usable risk cap, strategy, PnL or promotion evidence. A new
experiment may only begin with a separately frozen data-only gap and reset-window investigation.
Result: `research/btc/reports/BTC_HAR_RV_RISK_FORECAST_RESULT.md`.

**BTC multidimensional risk foundation and DVOL pilot:**
`btc-multidimensional-risk-foundation-v1` passes as offline contract infrastructure only. Risk is
now represented as independent volatility, downside/tail, jump/change, optional implied-risk and
future liquidity axes on daily and four-hour clocks. Only benchmark or accepted detector caps may
be fused; missing required axes fail to zero, and an open position can only remain unchanged or
shrink with no automatic re-leveraging. No detector or strategy was fitted. The rejected BOCPD and
Student-t HMM remain closed.

The first frozen DVOL pilot is preserved as rejected because its official documentation URL
returned HTTP 404 before any data request. Its V2 successor changed only that URL and passed its
bounded technical source gate: three pre-2026 15-day windows returned 45 valid daily observations
with zero duplicates, non-daily gaps, invalid OHLC rows or JSON-RPC errors, and both checksummed
official documentation records passed. DVOL is not approved for historical risk research because
full coverage, effective-dated methodology changes, revision/publication semantics and durable
retention rights remain unresolved. No strategy, feature, label, model or PnL was evaluated; zero
arms remain accepted and every actionable route remains `no_trade`. Results:
`research/btc/reports/BTC_MULTIDIMENSIONAL_RISK_FOUNDATION_RESULT.md` and
`research/btc/reports/BTC_DERIBIT_DVOL_SOURCE_PILOT_RESULT.md`.

**BTC canonical scorecard:** `btc-backtest-scorecard-v1` passes as offline research
infrastructure only. One deterministic engine now applies common UTC daily mark-to-market,
365.2425-day annualization, serial-dependence-adjusted Sharpe, expected shortfall, drawdown
duration/recovery, rolling losses, trade concentration, costs, matched controls and layered
evidence gates. The conservative trial registry leaves historical family completeness false, so
deflated evidence cannot pass by assuming unrecorded trials away. Supplemental replays preserve
all legacy headlines and decisions. Fixed breakout, EWMA and carry are all evidence-insufficient;
EWMA remains a risk control rather than alpha. Carry has only six trade cohorts and nine 84-day
blocks, its adjusted Sharpe is 1.566 versus 5.066 conventional, its paired lower bound versus
always-on carry is negative, and its top three trades contribute 92.50% of positive trade PnL.
No 2026, OB0, external service, regime model or strategy tuning was used. Zero arms remain
accepted. Result: `research/btc/reports/BTC_BACKTEST_SCORECARD_RESULT.md`.

**BTC B3 backtest core:** `btc-backtest-core-qualification-v1` passes as engineering
infrastructure only. The new deterministic BTC spot long/flat candle core validates causal
decision/fill timestamps, rejects same-segment gaps and segment crossings, uses the shared Decimal
execution and portfolio ledger, enforces allocation, planned-risk, frequency, daily-loss and
strategy-drawdown limits, marks open positions to market and emits checksummed costs, trades,
equity and performance metrics. Thirty-eight targeted core/execution/ledger/control tests pass.
The synthetic replay is byte-identical. The consumed fixed breakout and 4h SMA primary-cost
metrics match their frozen reports exactly; this is regression evidence and does not reopen either
rejected strategy. No new alpha, regime model, 2026 row, partial L2 data or external service was
used. Zero arms remain accepted. Result:
`research/btc/reports/BTC_BACKTEST_CORE_QUALIFICATION_RESULT.md`.

**BTC-only B0–B2 foundation:** BTC is now the only active market in the focused program; ETH,
cash-ETF, cross-asset and multi-asset work are archived rather than deleted. The BTC evidence
catalogue preserves zero accepted arms, `no_trade` as the only actionable arm, EWMA as the
mandatory risk benchmark, L2 as background data engineering only and at most one active strategy
hypothesis. A separate zero-capital derivatives mandate permits only research on a matched long
BTCUSDT spot / short BTCUSDT USD-M perpetual pair with conservative collateral assumptions; it
does not authorize credentials, paper exchange orders or live trading.

`btc-carry-data-qualification-v1` is rejected at its frozen data gate. All 360 official Binance
monthly archives and checksum sidecars passed, BTCUSDT perpetual execution klines are complete at
52,608 hours, and all 6,576 scheduled funding events pass after preserving at most 47 ms of
publication jitter. However, the official archives omit 192 mark-price hours, 288 index-price
hours and 169 premium-index hours, so exact row-count and synchronization gates fail. Historical
effective-dated fees, maintenance-margin brackets and exact account fees are also unresolved;
current rules were not projected backward. No strategy, return, PnL, position, order, credential,
2026 row or partial OB0 data was accessed. Preserve this result and use a new ID for any bounded
official-source gap recovery. Result:
`research/btc/reports/BTC_CARRY_DATA_QUALIFICATION_RESULT.md`.

The separately frozen `btc-carry-gap-recovery-v1` successor is also rejected under its exact
all-series gate. Seventeen of 18 official unauthenticated Binance REST responses passed: all 192
missing mark-price rows, all 288 index-price rows and 168 of 169 premium-index rows were recovered
without overlap, duplicate, invalid row, interpolation or alternate-venue substitution. The exact
2020-12-01 23:00 UTC premium-index request returned HTTP 200 with an empty JSON list. Mark and index
are therefore continuous at 52,608 hours each; premium index has 52,607 hours and one remaining
gap. Historical fee and maintenance-margin evidence also remains incomplete. No strategy, PnL,
position, order, regime model, 2026 row, partial OB0 data or protected service was accessed.
Result: `research/btc/reports/BTC_CARRY_GAP_RECOVERY_RESULT.md`.

`btc-positive-funding-carry-v1` is the first completed paired BTC strategy backtest and is
**rejected under its frozen gates despite positive economics**. It deliberately never consumed
premium-index data, so the single unavailable hour was irrelevant. On chronological 2024–2025
validation, matched long spot/short perpetual returned +5.83% at 30 bps and +2.61% at 80 bps
per-leg round-trip costs; primary drawdown was 0.42% across six trades. Funding contributed
+76.44 USDT, net basis +1.15, explicit fees -12.87 and implicit costs -6.43 on 1,000 USDT initial
equity. The same windows without funding lost 1.74%, and high-score weeks led other weeks by
60.88 bps of future 28-day funding with month-block CI `[23.84, 105.06]`. However, 260 exposed
hours failed the predeclared additional 20% isolated-margin shock buffer, and return per exposed
day was slightly below always-on carry. Do not tune its thresholds, lookback or shock and do not
add a regime rescue. A future experiment must address collateral/risk implementation under a new
ID and use prospective evidence for promotion. No strategy arm is accepted. Result:
`research/btc/reports/BTC_POSITIVE_FUNDING_CARRY_RESULT.md`.

`btc-safe-delta-neutral-funding-carry-v2` is now complete. It froze risk implementation before
recalculation while preserving v1's 84-event funding score, 60/30 bps thresholds, Monday clock and
84-day hold unchanged. Each matched leg was reduced from 49% to the retail 25% cap, leaving 75%
planning collateral; a completed-hour shocked margin ratio below 2.0 would force a causal severe-
cost exit at the next available hour with no intratrade re-leveraging.

The risk implementation passed every frozen gate on consumed 2024–2025 evidence. Primary return
was +2.95%, severe return +1.33%, primary drawdown 0.21%, funding attribution positive and all six
trades preserved. There were zero observed breaches, shocked breaches, entry margin rejections or
risk exits; minimum shocked margin ratio was 9.5117. Return per unit leg fraction closely matched
v1, proving that lower exposure scaled return rather than improving alpha.

The funding-timing claim is rejected again. At the exact same 25% exposure, always-on carry
returned +7.75% and earned 0.01061% per exposed day versus 0.00679% for the gated strategy, with
zero margin breaches and a 2.0719 minimum shocked ratio. Close the 60/30 bps timing family without
threshold, lookback, exposure or regime tuning. Always-on remains an unaccepted structural
benchmark because it contains only one continuous evaluation trade, uses consumed evidence and
lacks complete promotion economics. The replay report and trade ledger are byte-identical and the
independent audit passed. Result:
`research/btc/reports/BTC_SAFE_FUNDING_CARRY_RISK_V2_RESULT.md`. Zero arms remain accepted.

**Latest BTC-focused information result:** `btc-derivatives-crowding-information-v1` is rejected
and closed. Its mean absolute past-only z-score of completed-day Binance funding, completed-day
perpetual basis and conservatively lagged CME leveraged-money positioning did not forecast
next-seven-day BTC risk beyond causal EWMA variance and absolute seven-day momentum. The expanded
walk-forward model worsened log-variance MSE by 0.1325%; its paired monthly improvement interval
crossed zero. High-minus-low realized-variance and downside-loss intervals both crossed zero and
their point estimates were negative. Coverage passed with 1,263 complete observations and 892
forecasts across 30 months, while numeric 2024–2025 rows remained unread. Do not tune the score,
windows, weights or groups, and do not derive a strategy from the diagnostics. There are still
zero accepted arms and every route remains `no_trade`. Result:
`research/btc/reports/BTC_DERIVATIVES_CROWDING_INFORMATION_RESULT.md`.

**Latest A3 result:** `cross-asset-a3-overnight-gap-reversion-v2` is rejected and closed. Its
data-only prerequisite produced 30 checksummed development
and validation files from the immutable seven-market, seven-mask and GBP-conversion sources using
only `observed_at` or `local_date`; it deserialized no market value and included no prospective
row. V2 preserves the overnight-gap-reversion hypothesis frozen before A2 results. It fixes a
20-session past-only median range, 0.75-range gap threshold, completed first-hour reversal,
next-hour bid/ask entry, two-hour exit, one-range protective stop, 0/5/15 bps slippage, exact GBP
accounting, shared-capital limits, controls, robustness variants, uncertainty and 17 rejection
gates. Development was 2010–2021 and chronological validation 2022–2025. At spread plus 5 bps,
development returned -11.97% and validation -3.64%, with validation profit factor 0.80, Sharpe
-1.20 and mean trade -2.47 bps. Development was negative even at spread-only cost. Only 2022 and
the two US indices were positive; all four robustness variants and every leave-one-instrument-out
portfolio lost, the month-block interval crossed zero, and 12 of 17 gates failed. The signal beat
several controls only because those controls lost more. No prospective row was accessed. Do not
tune, rerun, choose the US indices post hoc, add leverage or apply a regime rescue. Zero arms and
execution instruments are approved, so A4 and A5 are blocked. See
`docs/CROSS_ASSET_A3_GAP_REVERSION_RESULT.md`.

**Latest A2 result:** `cross-asset-a2-session-breakout-continuation-v1` is rejected and may not be
tuned or rerun. The seven-market long/short session breakout was frozen together with exact local
timestamps, protective stops, GBP conversion, historical bid/ask, 0/5/15 bps slippage, fixed risk,
shared capital, controls, uncertainty and gates. At the primary spread-plus-5-bps cost it returned
-11.99% in 2010–2021 development and -5.35% in 2022–2023 validation. Validation profit factor was
0.83, Sharpe -1.37 and mean trade -2.96 bps; only the two US indices were positive, the month-block
interval crossed zero and ten of thirteen gates failed. Spread-only validation made +2.54%, but
spread-only development still lost 8.57%, so the result does not support a stable gross mechanism.

An integrity review also rejects the runner's `final_partition_accessed: false` claim: the loader
decoded at least one 2024 boundary JSON row per input before applying the cutoff. No final-period
signal, trade or metric was computed, but 2024–2025 is not a clean byte-level holdout for A2. The
A3 overnight-gap-reversion economic hypothesis was frozen before A2 results and remains preserved,
but its matching-partition rule is blocked. Any implementation requires a new ID, timestamp-only
prepartitioning and prospective final evidence. Zero strategy arms and execution instruments are
approved. See `docs/CROSS_ASSET_A2_SESSION_BREAKOUT_RESULT.md`.

**Latest A1 result:** `cross-asset-a1-oanda-hourly-history-v2` passes A1 for intraday research data
only. V1 archived exactly 224 H1 bid/ask responses for SPX500_USD, NAS100_USD, DE30_EUR,
UK100_GBP, XAU_USD, EUR_USD and USD_JPY over 2010–2025. V1 remains rejected because its frozen
two-percent incomplete-session gate counted Sunday-local fragments, holidays and early closes as
source defects. The no-download v2 successor changes no price, fills no bar and emits explicit
availability masks: every incomplete window is permanently `no_trade`. All seven candidates have
at least 3,995 complete windows, both history edges, valid uncrossed bid/ask and no gap over 168
hours. No return, PnL, feature, label, signal or 2026 price was accessed or computed.

A1 passing does not approve an execution instrument or strategy. The next permitted action is to
freeze A2 completely before calculating returns: one intraday session-breakout continuation family,
historical bid/ask plus 0/5/15 bps round-trip slippage, flat before 17:00 America/New_York, and
2010–2021 development / 2022–2023 chronological validation / still-sealed 2024–2025 final evidence.
Freeze the distinct A3 mean-reversion branch before reading A2 PnL. Oil and bond CFDs remain
excluded. See `docs/CROSS_ASSET_A1_OANDA_HOURLY_HISTORY_RESULT.md`.

**Preceding A1 result:** `cross-asset-a1-lse-futures-expansion-v1` is rejected on exact-XLON

full-history quality evidence and may not be repaired or rerun under the same ID. The bounded
12-response acquisition found conflicting duplicate dates and missing expected sessions in SWDA
(1/9), SGLN (1/8) and COMM (169/38; 109 duplicates conflict). VAGS has complete 1,646-session
price coverage, but its 65 provider dividends remain ineligible for cash credit pending issuer
reconciliation for the accumulating line. No row was deduplicated or filled; no return, PnL,
feature, signal or sealed-2026 value was computed. Calendar v1 remains bound to this rejection;
calendar v2 fixes movable Christmas/New-Year half-days under a new immutable ID.

The five offline futures candidates MES, MGC, MCL, M6E and MTN remain conditional-unapproved.
Their exact-expiry histories, official final settlements, current contract definitions, margins,
roll inputs and effective costs are incomplete. CME DataMine and Databento are registered but
unselected pending exact coverage/licence/TCO quotes; no purchase is authorized automatically.
Zero execution instruments and strategies are approved, and A2 remains prohibited. See
`docs/CROSS_ASSET_A1_LSE_FUTURES_EXPANSION_RESULT.md`.

**Preceding exact-line result:** `cross-asset-a1-executable-universe-feasibility-v2` passed its
bounded February 2025 source clarification only. It did not qualify full history, corporate
actions, costs or execution and does not override the later rejection.

**Preceding broker result:** `cross-asset-a1-ibkr-contract-details-public-review-v1` is partially resolved
and blocked. Direct official issuer and LSE pages bind SWDA, VAGS, SGLN and COMM to the frozen
ISINs, `XLON` and expected GBP/GBX quote units; IBKR officially groups `LSEETF` with its LSE stock
exchange venue. VAGS is verified as the exact account line for identity only. SWDA, SGLN and COMM
remain conditional-unapproved because no allowed official source explicitly equates the account's
literal `GBp` label with LSE's `GBX`. No execution instrument is approved. The Twelve Data
retention request is pending and the public-terms failure remains effective. No balance, holding,
history, quote, price, preview or order was retained or accessed. See
`docs/CROSS_ASSET_A1_IBKR_CONTRACT_DETAILS_PUBLIC_REVIEW_RESULT.md`.

The preceding `cross-asset-a1-completion-review-v1` fails the durable archival-use and
exact executable-mapping gates and leaves corporate-action and cost gates incomplete. Twelve
Data's public Terms require all Data to be deleted after subscription termination or expiration;
no written exception is on file. Thirteen issuer distribution samples match within frozen
precision, but complete action histories do not. The source-qualified histories are US-listed
funds, while UK-retail execution access is unapproved and the LSE candidates are different
instruments without qualified same-line histories. Public fees are planning inputs only. A1 stays
blocked with zero approved instruments and strategies; A2 is prohibited. See
`docs/CROSS_ASSET_A1_COMPLETION_REVIEW_RESULT.md`.

The preceding bounded Twelve Data v3 recovery remains valid technical evidence: it accepted SPY,
EFA, IEF, TLT, GLD, DBC, BIL and GBP/USD for the completion review, while EEM was rejected for
duplicate dates. This does not override the later license and mapping decision. See
`docs/CROSS_ASSET_A1_TWELVEDATA_RECOVERY_V3_RESULT.md`.

**New cross-asset foundation:** the user authorized a broader-than-crypto research direction
with GBP 20,000 research capital, a 20% absolute drawdown ceiling and a 50% annualized stretch
objective. `retail-cross-asset-a0-v1` is now frozen and passed as offline infrastructure only.
The user subsequently authorized A1. `cross-asset-a1-lse-source-pilot-v1` was frozen with a
four-instrument, January 2025, GBP-LSE source audit frozen before any historical price request.
Official identities passed, but all four candidate price URLs returned browser-challenge HTML
and the required source semantics were undocumented. Stooq is rejected; A1 was blocked at that point with
zero accepted sources, execution instruments or strategies.
The subsequent public-document-only broker audit, `cross-asset-a1-uk-broker-access-review-v1`,
confirms that Trading 212 publishes Invest pages for SWDA, VAGS, SGLN and COMM and that IBKR
publishes LSEETF execution pricing, but neither result is account-specific execution approval.
UK-retail access to ordinary US shares does not establish direct cash access to the US-domiciled
funds needed for all four economic roles. Neither broker's documented historical-data path meets
the frozen archival source contract without another pilot. The four LSE listings are candidates,
not mandatory instruments. Choose the intended broker and exact cash universe before buying data;
if these listings remain, Twelve Data's lowest-throughput LSE-capable Grow tier is the maximum
justified pilot, not the higher-throughput tier. This paragraph records the pre-purchase decision;
the later purchase and pilot outcome are recorded above.
See `docs/CROSS_ASSET_A1_UK_BROKER_ACCESS_REVIEW.md`.
The subsequent source-successor review did not download prices or run a strategy. It first found
all four exact LSE symbols publicly represented by Twelve Data, then identified Marketstack Free
as a lower-cost candidate worth testing first. Marketstack advertises 100 free EOD requests per
month, one year of history, corporate actions, exchange metadata and LSE coverage. A new frozen
September 2025 pilot must still prove exact four-line coverage, identity, units, adjustment and
availability semantics. The user then authorized the free-source test. The new
`cross-asset-a1-marketstack-free-source-pilot-v1` contract was frozen before any response, with
1–30 September 2025, 22 exact LSE sessions, 16 planned calls across ticker/EOD/split/dividend
endpoints, GBP-versus-GBX multipliers and credential-redaction gates. Its downloader and offline
auditor are implemented and synthetically tested. No API call occurred because the provider token
was not available to that session; no purchase or source acceptance had yet occurred. If it passes, the
pilot may qualify raw OHLCV plus separate corporate actions only: adjusted fields remain ineligible
without methodology, and exact publication-time uncertainty is handled by a one-complete-session
delay. The Free Plan agreement supports private qualification while active, but post-termination
archival use must be resolved by any later full-history contract. If it passes, the
first credentialed v1 call subsequently returned HTTP 404 because v2 requires the documented
`/tickers/{symbol}` route, not the frozen `/tickers` list route. No response body or partial data
was committed. V1 is preserved and rejected; successor v2 changes only the ticker-identity path
and artifact root before retry. If it passes, the
documented `/tickers/SWDA` successor also returned HTTP 404 without committing a body or partial
set. V2 is rejected. Final v3 removes ticker metadata and freezes 12 primary EOD/split/dividend
calls; EOD metadata plus issuer pages must bind the exact XLON lines. No suffix guessing is allowed,
and another failure rejects Marketstack. If it passes, the
advertised ten-year Basic history costs USD 9.99 month-to-month; Twelve Data Grow remains the
better-documented USD 79 fallback. The review also found that the failed pilot's generic GBP field
must be split into settlement currency and quote unit: SWDA and SGLN are disseminated in GBX,
VAGS in GBP, and COMM's vendor-reported GBp scale still requires exact binding. LSE direct history
is official but begins only in March 2022 and its 2025 EOD price was GBP 525 per month; it is not an
economic full-history source for this GBP 20,000 program. See
`docs/CROSS_ASSET_A1_SOURCE_SUCCESSOR_RESEARCH.md`.
It records a 12% soft stop, zero live allocation, UK-retail conservative planning, Malaysia as
a separately revalidated non-circumvention scenario, zero approved instruments, zero accepted
strategy arms and no market-data or PnL access. The stretch return is not an acceptance gate and
may not select leverage. A1 is now active after the Twelve Data v2 source qualification passed;
bulk acquisition still requires a separate frozen contract and strategy evaluation remains
prohibited. See
`docs/CROSS_ASSET_MULTI_STRATEGY_PROGRAM.md` and `docs/CROSS_ASSET_RESEARCH_HANDOFF.md`.

The BTC regime-routing program remains preserved and blocked at S5. The new program does not
repair or relabel its rejected breakout, BOCPD or HMM evidence, and does not inspect partial OB0.

**Background focus:** validate acquisition and deterministic reconstruction of the live
BTCUSDT spot L2 order book. See `docs/BTC_ORDER_BOOK_RESEARCH.md`. The seven-day OB0 pilot
validates data engineering only; it may not be used to claim or tune a strategy.

**Latest hands-on result:** `btc-sell-flow-absorption-v1` tested a materially new aggregate-
flow mechanism: extreme completed-hour selling plus high volume and an unusually positive
causal price-response residual. It was frozen before execution and rejected on the
checksummed 2017–2025 development partition. The 115 primary fills averaged +6.78 bps gross
but −23.22 bps after the 30 bps cost model; the shared account lost 5.28%, the month-block
interval crossed zero, the residual was worse than the extreme-sell-only control, and all
12 frozen perturbations lost. Nine gates failed. The 2026 holdout remains sealed. Do not
tune this ID or create another aggregate-flow threshold variant. See
`docs/BTC_SELL_FLOW_ABSORPTION_RESULT.md`.

**Earlier multi-asset result:** the prior repository's multi-asset leader experiment was
reconstructed under `multi-asset-top2-causal-v1` using a shared 1,000 USDT cash account,
25% aggregate entry cap, next-open execution, and the frozen 30/40/80 bps cost scenarios.
The development result is profitable, but much smaller than the earlier overlapping-event
headline. At 30 bps, the four-hour hold returns 16.91% with -1.80% maximum drawdown; the
midnight-UTC hold control returns 44.04% with -6.46% drawdown. The 12-hour half-reduction
is dominated and is rejected. See `docs/MULTI_ASSET_TOP2_DEVELOPMENT_RESULT.md`.

This is not promotion evidence: the route was historically selected using overlapping
data, profit is concentrated, the midnight control has only 48 cohorts, and the pair
count violates `retail-btc-spot-v2`. The 2026 partition is not clean for this strategy
family because the earlier repository already inspected data through May 2026. A new
multi-asset research mandate and genuinely forward paper evidence are required before it
can advance. Account-specific fees and forward-fill calibration remain pending.

The frozen R0 selection-alpha decomposition is now complete. The ranked top two beat the
eligible universe by 181.98 bps per paired event and reached the 98.94th percentile of
5,000 seeded random selectors, but the month-block 95% interval crosses zero. Only 48
primary cohorts filled, the best three profitable months supply 64.50% of positive monthly
PnL, point-in-time universe membership is unavailable, and the same-month gate-timing test
was insignificant (p=0.4051). The predeclared decision is `selection_alpha_reject`: retain
the frozen route only as an unpromoted research benchmark and do not tune or scale it. See
`docs/MULTI_ASSET_TOP2_ALPHA_ATTRIBUTION_R0_RESULT.md`.

The first frozen R2 BTC/ETH-relative mechanism is also complete and rejected. An extreme
negative 4-hour BTC residual versus ETH during positive joint context did not catch up over
the following 24 hours. At the primary 30 bps cost, 254 non-overlapping trades returned
-22.71% with -24.84% maximum drawdown and 0.66 profit factor. The paired event mean was
-34.89 bps, its month-block 95% interval was wholly negative, it trailed the simpler
BTC-only reversal control by 49.88 bps per event, and all six frozen sensitivities lost.
Do not tune this ID or treat BTC/ETH correlation as directional alpha. See
`docs/BTC_ETH_RELATIVE_CATCHUP_R2_RESULT.md`.

The prior crypto and OANDA repositories were re-audited for regime selection, strategy
routing, risk, execution, portfolio, observation, and monitoring components. They provide
useful architecture and test ideas, but the crypto regime selector was rejected, its
multi-strategy router remained watchlist-only, its general risk governor was rejected, and
many components are report-only or use accounting that is not portable. The current
repository's capability gaps and P0-P9 dependency order are recorded in
`docs/PREVIOUS_REPO_STRATEGY_PLATFORM_AUDIT.md`.

If L2 information later passes its own statistical and economic gates, test it first as
an execution/entry filter for the retained slower strategy design:

* **Primary candidate:** 4h regime -> 1h entries, long/flat first.
* **Slower control:** 1d regime -> 4h entries.
* **5m:** execution/cost stress test only until it demonstrates incremental net edge.

The tested slower design was a compression-to-expansion continuation test: objective 4h realized
volatility compression followed by a positive 1h return, range, volume and taker-flow
expansion. The context cutoff is the trigger 1h bar's open, decisions use completed
candles, and the entry is attempted only on the following 5m bar. MA/RSI/MACD/ADX remain
controls rather than required signals. Its 2023–2025 confirmation mean was −31.67 bps raw
over 55 events, and its 30 bps executable result lost 6.31%; this exact hypothesis is
closed.

## Status

| Area | Status | Evidence / next action |
|---|---|---|
| Cross-asset multi-strategy A0 | **Passed — offline mandate and feasibility only** | GBP 20,000 research equity, GBP 17,600 soft floor, GBP 16,000 hard floor, UK-retail conservative default, zero approved instruments/arms and `no_trade` are frozen. A1 requires separate activation and a one-partition-per-source data qualification pilot; no market data or strategy result was accessed. |
| Cross-asset multi-strategy A1 source/history | **Blocked — exact-line source clarification passed** | Twelve Data v2 passed exact LSE/XLON identity, expected GBP/GBp units, 20-session coverage, listing-history thresholds and action schemas for SWDA, VAGS, SGLN and COMM. This is a source pilot only. Full same-line history, complete issuer-action reconciliation and exact costs remain unresolved; no strategy, execution instrument or live action is authorized. |
| Synthetic safety and dry-run boundary | Complete | `README.md`, `docs/PROJECT_STATUS_AND_SESSION_HANDOFF.md` |
| 24h soak | In progress (other session) | Do not restart or modify its containers |
| Binance BTC/ETH 5m archive | Complete | `artifacts/agent-level-experiment/binance-market-data-manifest.json` |
| Derived 1h/4h candles | Complete | `artifacts/agent-level-experiment/derived-timeframe-manifest.json` |
| Alpha Vantage news capture | Partial | Only late-2025 coverage; exploratory metadata, not a full replay set |
| GDELT cleaning and timestamp gate | Implemented | `scripts/clean_gdelt_gkg.py`, `scripts/validate_news_timestamps.py`; full archive run pending |
| Market SMA baseline | Exploratory complete | `scripts/backtest_market_baseline.py`; not walk-forward or promotion evidence |
| Retail trading mandate | **Frozen for research** | `retail-btc-spot-v2`: Binance research data, BTC/USDT spot long/flat, normalized 1,000 USDT equity, percentage risk limits, one position, 4h/1h cadence; live allocation is zero |
| Realistic cost model | **V1 implemented; calibration pending** | Venue-neutral Decimal ledger; candle taker, L2 depth walk, maker queue/fallback, rules/fee adapters, deterministic manifests; exact account fees remain gated |
| Multi-timeframe regime/entry experiment | Deferred during OB0 | Revisit only if L2 survives its own data, statistical, and economic gates |
| BTC/ETH causal relationship analysis | Initial scaffold complete | `scripts/analyze_btc_relationships.py`; report shows high contemporaneous correlation but near-zero simple lead-lag correlation; requires walk-forward significance tests |
| BTC mathematical breakout scaffold | Initial smoke test complete | `scripts/backtest_btc_breakout.py`; causal raw breakout loses at 1h after costs; EMA/ADX retained as controls only |
| Walk-forward causal BTC model | Initial diagnostic complete | `scripts/walkforward_btc_causal_model.py`; current BTC/ETH/volatility/volume features show no stable 1h/4h predictive edge yet |
| BTC 5m taker-flow recovery | **Complete** | 24 archives, 210,528 rows, zero gaps/duplicates/invalid rows; deterministic dataset and accepted manifest under `artifacts/agent-level-experiment/btc-taker-trade-flow/` |
| Taker-trade-flow event study | **Exploratory complete — not tradable standalone** | 2025 shows asymmetric reversal after extreme buying, but mean effect is far below 24 bps round-trip cost |
| BTC taker-flow history expansion | **Complete** | Official Aug 2017–Jul 2026 archives verified; 878,985-row segmented development set and gap-free 61,056-row sealed 2026 holdout |
| Conditional taker-exhaustion hypothesis | **Rejected before holdout** | Stable 2023–2025 reversal, pooled mean 5.00 bps, but below predeclared 12 bps economic gate; 2026 remains sealed |
| BTC sell-flow absorption residual | **Rejected before holdout; aggregate-flow family closed** | 115 fills; +6.78 bps gross but −23.22 bps after primary costs, −5.28% account return, PF 0.73, 2/7 positive years, random-match p=0.5731, 0/12 profitable perturbations; checksummed evidence under `artifacts/agent-level-experiment/btc-sell-flow-absorption/development-v1/` |
| Higher-information trade-flow feasibility | **Complete** | Binance `aggTrades` add within-bar signed-trade sequencing but cannot reconstruct resting liquidity, cancellations, or historical spot L2 |
| BTC spot L2 order-book acquisition | **Replacement seven-day OB0 running** | First attempt rejected after an 11-hour host-suspend gap. Persistent sleep-inhibited capture `btc-l2-20260825T194700Z-c924306b` started 2026-08-25 19:47 UTC; expected finish about 2026-09-01 19:47 UTC |
| OB0 health and acceptance automation | **Complete; watcher restored 2026-08-28** | Capture service remained active with zero restarts, but the transient watcher unit was absent. A metadata-only health check passed and `btc-l2-ob0-retry-watch.service` was restored without touching capture state. `ops/start_btc_ob0_watcher.sh` now makes recovery idempotent; 60-second health checks and two deterministic replays precede the frozen acceptance decision. |
| OB1 L2 experiment protocol | **Frozen; causal contract foundation implemented; data blocked** | Machine-readable 1 Hz receipt-time sampling, stale/segment rejection, delayed labels, 60-day folds and locked 60+30 collection validation are tested. Real execution still requires 60 accepted development days plus a later unread contiguous 30-day test. See `docs/BTC_ORDER_BOOK_OB1_IMPLEMENTATION_READINESS.md`. |
| Historical L2 provider decision | **Crypto Lake and CryptoHFTData rejected; Tardis raw pilot frozen but blocked; purchase deferred** | Crypto Lake failed its checksummed public-sample audit. CryptoHFTData's exact free Binance spot example hour preserved contiguous update and trade IDs but contained 1,674,190 update rows and zero snapshots, with `last_update_id` null throughout, so no absolute book could be initialized; its remaining day was not downloaded. `btc-order-book-tardis-raw-pilot-v1` freezes three mechanically selected pre-2026 dates, native `depth`/`depthSnapshot`/`aggTrade`, replay and incident gates, and an exact one-off quote request. Execution requires final OB0 acceptance; payment requires separate user approval of the dated total. See `docs/BTC_ORDER_BOOK_CRYPTOHFTDATA_AUDIT_RESULT.md` and `docs/BTC_ORDER_BOOK_TARDIS_RAW_PILOT_PLAN.md`. |
| BTC 4h SMA 10/30 robustness | **Profitable but rejected before holdout** | 35.3% CAGR, -75.5% true drawdown, 5/9 positive calendar slices; failed frozen consistency gate |
| BTC 4h execution-model rerun | **Still rejected before holdout** | At 25% allocation: 9.6%/8.5%/4.0% CAGR under 30/40/80 bps round-trip, but only 5/9 positive years; 2026 stays sealed |
| BTC online-regime breakout v1 | **Complete — BOCPD gate rejected before holdout** | At 10% allocation and 30 bps RT, the fixed breakout control returned +16.94% with 5.02% DD and 0.450 Calmar; the causal daily BOCPD gate returned +6.72% with 3.87% DD and 0.241 Calmar. Its next-7d state difference was -37.60 bps, 9/21 gates failed, and only 1/12 sensitivities improved matched-breakout Calmar. Preserve the breakout as a development control; do not tune this regime model or open 2026. Evidence: `artifacts/agent-level-experiment/btc-online-regime-breakout/development-v1/`. |
| Regime-model academic and firm research | **Complete — design direction recorded** | Public evidence from Bridgewater, Two Sigma, State Street, Man AHL, Invesco, Research Affiliates, BlackRock and AQR shows that regime layers serve different jobs and are commonly used for risk, allocation, or strategy weighting rather than as universal direction oracles. For BTC, validate the breakout first, then simple continuous volatility scaling, and only afterward compare a two-state heavy-tailed persistent risk model. Do not implement another hard bull/bear entry veto. See `docs/BTC_REGIME_MODEL_INDUSTRY_RESEARCH.md`. |
| BTC regime-to-strategy routing program S0 | **Passed — offline infrastructure only** | Immutable research contracts, the three-arm evidence registry, deterministic counterfactual router, chained decision log, stage/status registry, session handoff and fail-closed context validator are implemented. Every actionable route is structurally fixed to `no_trade`; no market data, sealed 2026 partition, partial OB0 data, soak service, production signal or order path was accessed. S1 requires a separate implementation request. See `docs/BTC_REGIME_STRATEGY_ROUTING_PROGRAM.md`. |
| BTC regime-to-strategy routing program S1 | **Passed — development reproduction only** | `btc-regime-routing-s1-ledger-v1` built deterministic causal 5m/4h/daily ledgers and point-in-time feature records, adapted the unchanged 120/60 breakout, and reproduced all frozen 30/40/80 bps legacy results exactly on the checksummed 2017–2025 development source. A second isolated build was byte-identical. The evidence-boundary registry marks 2017–2025 consumed and 2026 sealed-ineligible; no model fitting, parameter change, promotion claim, partial OB0 access, protected-service access, or sealed-2026 access occurred. Evidence: `artifacts/agent-level-experiment/btc-regime-routing/s1-ledger-v1/`; result: `docs/BTC_REGIME_ROUTING_S1_RESULT.md`. S2 is planned but inactive and requires separate activation. |
| BTC regime-to-strategy routing program S2-v1 | **Rejected — insufficient causal EWMA coverage** | `btc-regime-routing-s2-ewma-v1` produced usable same-segment estimates for 62/67 locked S1 opportunities (92.54%), below the frozen 95% overall gate; 2019 (83.33%) and 2021 (75.00%) also failed the 90% annual gate. All five exclusions were insufficient 30-return history after source-segment resets. The runner stopped before forecast-quality or PnL evaluation, did not tune the warm-up, and reproduced the rejection byte-for-byte. Do not alter this ID or use sealed 2026 to repair it. Evidence: `artifacts/agent-level-experiment/btc-regime-routing/s2-ewma-v1/`; result: `docs/BTC_REGIME_ROUTING_S2_RESULT.md`. |
| BTC regime-routing S2 daily-data audit | **Rejected under strict OHLC reconciliation; close-only source remains plausible** | `btc-regime-routing-s2-daily-data-audit-v1` verified 101 official Binance daily archives and a gap-free 3,059-day 2017–2025 series. All 3,024 overlapping closes matched S1 and the five affected observations had 591–2,065 completed returns, but three 2017 opens differed between official 1d and official 5m archives; 19 volume diagnostics also differed. The frozen exact-OHLC gate therefore rejected the audit. No forecasts or PnL were computed. A future close-only attempt requires a new frozen contract and must retain the original EWMA parameters and gates. Result: `docs/BTC_REGIME_ROUTING_S2_DAILY_DATA_AUDIT_RESULT.md`. |
| BTC regime-to-strategy routing program S2-v2 | **Passed — close-only EWMA benchmark frozen** | `btc-regime-routing-s2-ewma-v2` changed only the risk-return source to the continuous checksummed official daily close ledger and retained all S2-v1 parameters and gates. Coverage reached 67/67. One-day QLIKE improved from -5.6846 to -5.9145. At 30 bps, EWMA scaling returned 18.75% with 3.28% drawdown and 0.758 Calmar versus fixed 16.94%, 5.02% and 0.450; at 80 bps it returned 15.61%, 3.68% and 0.569 versus 13.01%, 5.62% and 0.314. Every frozen economic gate passed, including best-three-month neutralization, and an isolated replay was byte-identical. Monthly-difference intervals cross zero, so this is development benchmark evidence, not promotion evidence. Result: `docs/BTC_REGIME_ROUTING_S2_V2_RESULT.md`. |
| BTC regime-to-strategy routing program S3 | **Rejected — forward downside separation failed; latent branch closed** | `btc-regime-routing-s3-student-t-hmm-v2` produced 84 converged monthly refits, stable labels, 57.68%/42.32% occupancy, 148 transitions, 11/12-day median dwell, 6.71% one-day runs, and 67/67 opportunity coverage. Stress minus ordinary next-seven-day realized variance passed with CI `[0.00167, 0.01036]`, but downside loss CI `[-0.00543, 0.01490]` crossed zero. The frozen runner stopped before PnL. S4 is skipped because the HMM passed stability but failed forward-risk separation; do not tune or build the jump model. Result: `docs/BTC_REGIME_ROUTING_S3_RESULT.md`. |
| BTC regime-to-strategy routing program S5 breakout mechanism | **Rejected — S5 blocked with zero accepted arms** | `btc-regime-routing-s5-breakout-mechanism-v2` passed the conditional-background test: 30-bps high-efficiency expectancy was +6.93% versus -1.85% for low efficiency, with high-minus-low CI `[+1.86%, +15.35%]`. It failed the independent timing falsifier: 63 valid breakout entries ranked at only the 54.31st percentile of 5,000 frozen year-count-matched random seven-day samples versus the 95th-percentile minimum. Do not turn the small high-efficiency subset into a post-result filter or tune the breakout. It remains a development control; 2026 is sealed-ineligible, no arm is accepted, S6 is not permitted, and actionable routing remains `no_trade`. Result: `docs/BTC_REGIME_ROUTING_S5_BREAKOUT_MECHANISM_RESULT.md`. |
| Lagging indicators as primary signals | **Rejected for focus strategy** | May remain as diagnostic baselines, never as required entry logic |
| BTC volatility-expansion continuation | **Rejected before holdout** | 55 confirmation events; −31.67 bps raw mean, −6.31% primary net return, PF 0.55, 0/10 positive sensitivities; `docs/BTC_VOLATILITY_EXPANSION_DEVELOPMENT_RESULT.md` |
| Multi-asset top-two causal reconstruction | **Development candidate; not promotable** | Capital-bounded four-hour hold: +16.91%, -1.80% DD at 30 bps. Midnight hold control: +44.04%, -6.46% DD over 48 cohorts. Both remain positive at 80 bps; 12h reduction rejected; concentration and mandate gates remain open. |
| Multi-asset selection-alpha decomposition | **R0 complete — selection claim rejected** | +181.98 bps/event versus eligible universe and random p=0.0108, but bootstrap lower 95%=-4.72 bps, only 48 fills, 64.50% top-three-month concentration, no gate evidence, and no point-in-time universe. Checksummed evidence: `artifacts/agent-level-experiment/multi-asset-top2/alpha-decomposition-r0-v1/`. |
| Point-in-time universe and unseen-partition contract | **P1 enforcement implemented; evidence not ready** | Gap-free eligible/ineligible/unknown timelines, inclusion-rule validity, evidence checksums, embargoes, locked collection and family-wide inspection contamination are enforced. The fixed-seven rule is post hoc, membership remains unknown, and inspected 2026 remains excluded; report: `artifacts/agent-level-experiment/multi-asset-top2/p1-evidence-contract-v1/`. |
| BTC/ETH relative catch-up R2 | **Complete — `development_mechanism_reject`** | Primary 30 bps result -22.71%, -24.84% DD, PF 0.66; event mean -34.89 bps with wholly negative month-block interval; worse than BTC-only control; 0/6 positive sensitivities. Checksummed evidence: `artifacts/agent-level-experiment/btc-eth-relative-catchup-r2/development-v1/`. |
| Walk-forward and embargoed test | Completed for rejected candidate | Deterministic development report reproduced byte-for-byte; 2026 remains sealed because nine of ten gates failed |
| Regime-attributed performance | Open | Report return, drawdown, turnover, and trade count by regime and symbol |
| Agent ablation | Blocked pending evidence | Need frozen timestamp-safe agent output captures; do not invent them |
| Real-data shadow | Not started | Requires approved source contracts and timestamp-safe replay |
| Strategy promotion | Not approved | Requires net-of-cost, walk-forward, robustness, and operational gates |
| DR/security/observability artifacts | Designed/packaged | Apply only through reviewed deployment change; not part of this research run |

## Strategy-platform build priority

This priority list is separate from individual alpha hypotheses. It establishes the system
needed to evaluate, route, risk-manage, execute, and observe accepted strategies. Detailed
acceptance criteria and previous-repository evidence are in
`docs/PREVIOUS_REPO_STRATEGY_PLATFORM_AUDIT.md`.

| Priority | Capability | Status | Dependency / decision |
|---|---|---|---|
| P0 | Preserve reliable data, transport, kill-switch, reconciliation, mandate and cost boundaries | **Implemented; protect** | Do not alter the active soak candidate or weaken the Freqtrade final entry gate. |
| P1 | Reusable causal shared-capital research and alpha-attribution harness | **Enforcement foundation implemented; source/forward evidence open** | In addition to R0 replay, point-in-time membership, checksum, gap/overlap, label-embargo, locked collection and contamination contracts are now implemented and tested. Current membership sources are missing and no clean prospective partition exists, so the contract correctly fails closed; do not build the runtime router yet. |
| P2 | Versioned regime-state engine | **Research prototype implemented; first state rejected** | The causal BOCPD prototype records state, posterior confidence, availability cutoff and unknown/uncertain behavior. Its positive-drift entry gate reduced breakout Calmar and failed standalone forward-information tests, so it is not selectable. A runtime engine remains blocked pending an accepted state mechanism. |
| P3 | Strategy-arm interface and accepted-arm registry | Pending P1/P2 | Begin with `no_trade` and one independently accepted arm. Watchlist/rejected arms are not selectable. |
| P4 | Central portfolio/account risk kernel | Pending P1 contract | One mark-to-market account state; enforce allocation, planned loss, inventory/cash, concurrency, daily loss, high-water drawdown, concentration and protective-exit precedence. |
| P5 | Deterministic regime/strategy router | Pending accepted arms and P2-P4 | Scorecard first, ML later only if justified. Record all available arms and counterfactuals; unknown/disagreement fails flat. Must beat the best single-arm reference out of sample after costs. |
| P6 | End-to-end order-intent and execution/fill integration | Offline model exists; runtime integration pending | Extend the existing Decimal execution model and Freqtrade boundary with strategy/regime/router/risk attribution, price protection, expiry and terminal-state reconciliation. Do not create a second order placer. |
| P7 | Shared-risk multi-alpha portfolio allocator | Blocked pending two accepted families | Correlation/covariance, uncertainty, cost, turnover, capacity and concentration aware; never add standalone backtest returns. |
| P8 | Strategy/risk/execution observability | Infrastructure metrics exist; decision metrics missing | Add regime age/transitions, selected arm, abstentions, exposure/PnL/drawdown, risk state, intent/fill costs and reconciliation alerts. |
| P9 | Standalone then portfolio forward-paper observation and promotion registry | Blocked pending accepted candidate | Observe each accepted arm before combination; require frozen identity, observed-cost calibration, mandate review, rollback and explicit approval. |

## Sequenced strategy-research roadmap

This is the canonical order for strategy research. Data collection and reliability work may
continue in the background, but only one new strategy hypothesis may be under active
evaluation at a time. Completing a stage does not automatically authorize the next one;
record its accept/reject decision and artifact paths first. All stages follow
`docs/STRATEGY_RESEARCH_STANDARD.md`.

| Stage | Research direction | Status | Required work and decision |
|---|---|---|---|
| R0 | Multi-asset top-two selection-alpha decomposition | **Complete — `selection_alpha_reject`** | Ranking point estimate and seeded-random result are promising, but five frozen gates failed: sample count, selection uncertainty, concentration, gate timing and point-in-time universe. Do not change this experiment ID. |
| R1 | Top-two disposition | **Frozen benchmark only; not selectable** | Preserve the exact route for comparison, but do not tune, scale, register, paper-promote or route capital to it. A new experiment requires point-in-time universe/rules plus genuinely chronological or prospective evidence; inspected 2026 data is not a clean holdout. |
| R2 | BTC/ETH relative-information experiment | **Complete — first mechanism rejected** | `btc-eth-relative-catchup-r2-v1` remained BTC/flat with ETH context only and failed 11 frozen gates. Close this residual catch-up formulation; do not choose the least-negative sensitivity. Any later BTC/ETH-relative study needs a materially different mechanism and new ID, and remains part of the price family rather than independent diversification. |
| R3 | BTC L2 OB0 acceptance and full OB1 data acquisition | **Seven-day background capture running; OB1 blocked by 60+30 accepted days** | Finish the uninterrupted seven-day OB0 capture and deterministic replay without inspecting partial data. If OB0 passes engineering gates, continue collecting until 60 accepted development days, then seal a subsequent contiguous 30-day test. Only after those boundaries exist may the frozen OB1 1 Hz/5 s, 250 ms-latency protocol run. OB0 proves data quality, not profitability. |
| R4 | Conditional L2 continuation/reversal and execution filter | Pending OB1 acceptance | Proceed only if OB1 shows stable incremental information. Separate continuation, absorption/reversal, and liquidity-vacuum hypotheses. Test L2 first as an execution/risk filter for an accepted slower strategy; require improvement over the same strategy without L2 after spread, fees, latency, and fill uncertainty. Longer forward capture will be required for regime coverage. |
| R5 | Volatility forecast and portfolio risk allocator | Pending at least one accepted alpha | Compare simple EWMA/HAR-style controls before complex models. Forecast risk, not direction. Use it for exposure normalization, cost-aware stand-aside decisions, and portfolio correlation limits. It must improve frozen risk-adjusted and tail metrics without relying on hindsight thresholds. |
| R6 | Spot/futures basis and funding carry | Deferred; new mandate and data required | Research BTC/ETH delta-neutral cash-and-carry only if derivatives, margin, custody, and venue risk are explicitly approved. Acquire point-in-time spot, mark, index, funding, contract-rule, fee, and liquidation data. Attribute funding, basis, hedge error, execution, margin, and venue-failure risk separately. |
| R7 | Timestamp-safe news/event overlay | Deferred; data incomplete | Complete publication-versus-retrieval timestamp coverage first. Test news as a risk veto or conditional modifier before any primary directional strategy. Require event-time controls, duplicate/story-cluster handling, source fallback, and latency-aware replay. |
| R8 | Multi-alpha portfolio construction | Blocked pending two independently accepted families | Combine only economically distinct accepted forecasts. Estimate forecast/PnL correlations and allocate using frozen expected-return uncertainty, covariance, turnover, costs, capacity, concentration, and risk limits. Re-run the shared-account execution model; do not sum standalone backtest returns. |
| R9 | Standalone then portfolio forward-paper observation and limited-capital review | Blocked pending any standalone acceptance | Paper-observe each frozen strategy as soon as it independently passes; do not wait for portfolio construction. If two independent families later pass, paper-observe their shared-capital portfolio separately. Measure decay and observed costs before any mandate review. No backtest or tracker status authorizes live orders. |

### Strategy-family boundaries

Treat these as distinct candidate information sources, not parameter variants to search all
at once:

1. **Directional/regime:** slower BTC/ETH/flat allocation and the retained portion, if any,
   of the multi-asset top-two family.
2. **Microstructure:** order-flow continuation, absorption/reversal, liquidity state, and
   execution timing derived from accepted L2 data.
3. **Carry/relative value:** spot/futures basis and funding under a separately approved
   derivatives mandate.
4. **Risk overlays:** volatility, correlation, liquidity, and timestamp-safe events. A risk
   overlay is not directional alpha and must be evaluated as an incremental portfolio change.

### Explicitly low-priority or rejected directions

- Do not reopen the rejected aggregate taker-flow reversal or volatility-expansion
  experiments by changing thresholds; a materially new mechanism requires a new ID.
- The materially different aggregate sell-flow/price-residual mechanism also failed. Treat
  aggregate five-minute taker flow as a control only; do not start another threshold variant.
- Do not make MA, RSI, MACD, ADX, or candle-pattern parameter searches the primary research
  direction. They remain transparent controls.
- Defer millisecond market making, cross-exchange arbitrage, options-volatility trading, and
  reinforcement-learning/deep-candle models until data, execution access, and an economic
  mechanism justify their complexity.
- Do not combine multiple weak trend transformations and describe them as independent alpha.
- Do not target a desired annual return by increasing exposure. Establish incremental alpha
  and uncertainty first, then compare risk-normalized portfolio allocations.

### Immediate hand-off

P0 remains protected. The aggregate taker-flow family, first BTC/ETH residual-catch-up
mechanism, R0 selection claim, and daily BOCPD drift gate are rejected without opening their
sealed partitions or changing the active soak/L2 capture. Do not tune them. The fixed
20-day/10-day breakout remains a development control, not approved trading logic: at the
frozen 10% allocation it was positive but trailed the segmented BTC participation control and
has not passed an independently frozen chronological validation. The next focused strategy step
was therefore frozen and completed as `btc-regime-routing-s5-breakout-mechanism-v2`. Conditional
efficiency attribution passed, but the breakout event ranked only at the 54.31st percentile of
year-count-matched random seven-day entries and failed its 95th-percentile falsifier. The
mechanism is rejected; do not create an efficiency-filter variant from this consumed result.
Independent chronological or prospective evidence under a separately frozen strategy mechanism
would be necessary. S5 is blocked with zero accepted arms, so S6 routing is not permitted. The background
R3 OB0 capture remains the only active new-information acquisition; partial data must not be
inspected.

The staged regime-to-strategy program completed S1, preserved the coverage-rejected S2-v1, and
passed the separately frozen close-only S2-v2 benchmark. S2-v2 reached full opportunity coverage,
improved standalone one-day volatility forecasting, and passed all frozen development overlay
gates versus fixed and capital-time-matched controls under the required costs. Its paired monthly
incremental-return intervals cross zero, so the result is not promotion evidence and does not
validate the underlying breakout. The registry still permits the fixed breakout only in
counterfactual development rankings, excludes the rejected BOCPD-gated breakout, and hard-locks
every actionable decision to `no_trade`. S3 subsequently rejected its Student-t HMM before PnL:
realized-variance separation passed, but the stress-state downside-loss interval crossed zero.
The latent-risk branch is closed and S4 is skipped; the model may not be tuned.

A separately frozen data-only audit verified that official BTCUSDT daily archives
are continuous across 2017–2025 and provide ample causal history at all five excluded S2
opportunities. Every overlapping daily close matched S1, but three 2017 opens and 19 volume
diagnostics differ between Binance's official 1d and 5m archives. The audit's predeclared exact-
OHLC gate rejected the source, so it does not reactivate S2. A close-only data contract is a
plausible materially new successor because EWMA consumes only closes. That successor was frozen
as S2-v2 before output, retained the original parameters and gates, and is now the mandatory
control for any later S3 comparison. The failed all-OHLC audit and S2-v1 rejection remain intact.

## Deferred alternatives — require a new frozen hypothesis

1. 1h standalone SMA baseline (control).
2. 4h regime + 1h entry (primary).
3. 1d regime + 4h entry (slow control).
4. 4h standalone baseline.
5. 4h regime + 5m entry (cost sensitivity only).
6. Multi-asset midnight-UTC top-two hold-only forward observer (requires a new mandate;
   do not use 2026 as a clean historical holdout).

The volatility-expansion hypothesis is closed; do not tune it or launch this matrix as a
reaction to its result. If one alternative is later selected and frozen under a new
experiment ID, record symbol, bar
convention, parameter set, train/test dates, regime
definition, entry/exit timestamps, fee, spread, slippage, turnover, trade count, net
return, Sharpe/Sortino, max drawdown, profit factor, and bootstrap confidence intervals.
Compare against buy-and-hold and a flat/no-trade control. Any change in data, costs, or
parameters creates a new experiment ID.

## Research rationale

Recent crypto research generally warns that finer sampling increases turnover and cost
drag, while trend/momentum effects are regime-dependent. Multi-timeframe studies report
possible drawdown/filter benefits but do not establish profitability after realistic
execution costs. Therefore the repository treats higher-timeframe gating as a falsifiable
risk-control hypothesis, not as an automatic alpha source.

## Definition of done

The next strategy candidate is only eligible for review after: (a) no lookahead tests
pass, (b) all cost scenarios pass, (c) walk-forward and unseen-period results are
reported, (d) results survive parameter perturbation, and (e) operational kill-switch,
reconciliation, and data-freshness checks remain green.

For the current OB0 stage, definition of done is narrower: checksummed raw partitions,
deterministic reconstruction, explicit update-gap segmentation, timestamp-latency and
coverage reports, and a seven-day accepted/rejected manifest. It is not a profitability
result.

## BTC spot/perpetual continuation input qualification — 2026-09-01

Candidate ID: `btc-spot-perp-continuation-information-v1`  
Completed information experiment: `btc-spot-perp-continuation-information-d1-v3`  
Disposition: **D1 information hypothesis rejected and closed; strategy not tested**

After the compression-breakout and CUSUM event studies failed frozen sample gates, the next
candidate changed mechanism and sampling design: a regular daily question about whether signed
perpetual-versus-spot basis and relative turnover add next-72-hour BTC continuation information
beyond price-only controls. A new input-only mandate expressly forbids perpetual positions,
credentials, live access, signals and orders.

D0 v1 remains rejected because hourly gaps and mandatory 90-day segment resets failed readiness
counts. D0 v2 remains a preserved preflight failure because official direct hourly spot archives
contain partial-hour close boundaries that violate its frozen parser. D0 v3 changed the source
frequency to direct daily bars, matching the predeclared daily clock without weakening the
coverage, warm-up or count gates.

D0 v3 verified all 148 official monthly archives and sidecars, exact REST/archive overlaps, no
daily gaps, one common segment and 100% common coverage in each year from 2020 through 2025. The
90-day warm-up leaves 391 feature-ready days before 2021 and 365/365/365/366/365 in 2021–2025.
The audit replay is byte-identical. No future return, model, strategy, PnL, position, order, 2026,
partial OB0, protected service or credential was accessed.

D1-v1 was preserved as preflight-invalid before any historical row because it simultaneously made
missing/cross-segment target candidates ineligible and required their count to be zero. D1-v2
corrected only that gate semantics before data access. Its feature phase passed with 2,209 causal
rows, but its same-segment target rule left only 344/365 labels in 2021. Review established that
this path-continuity rule was inherited from a path-sensitive five-minute ledger even though the
unchanged target depends only on the exact opens at `t` and `t+72h`.

D1-v3 was frozen before opening a new target or result. It reused the feature ledger byte-for-byte
and changed only target eligibility: both endpoints had to be present in independently
authenticated official Binance monthly archives, while interior gaps remained diagnostics. All
73 archives passed exact hash, URL and inventory checks; all 2,209 requested pre-2026 endpoints
were present, positive-volume and equal to the S1 opens. The label gate then passed with 1,823 of
1,823 evaluation labels and 100% coverage in every 2021–2025 year. Forty-eight windows crossing
interior gaps remain explicitly reported; no value was interpolated or stitched across venues.

The unchanged monthly expanding OLS information test rejected the hypothesis. M1 MSE was
0.002792931256 versus 0.002778148523 for price-only M0 and 0.002760098760 for B0, a 0.532107%
worsening versus M0. Only 2022 and 2025 improved. All three month-block uncertainty intervals
crossed zero, the best-three-months-excluded result was negative, and median coefficients for both
candidate variables were negative rather than the frozen positive continuation signs. The
isolated replay reproduced endpoint, label, forecast and snapshot ledgers byte-for-byte and the
closing audit passed every check.

This separates the root cause: D1-v2's near-threshold failure was partly a label-rule defect, but
the corrected evidence shows no stable incremental continuation information. Per the frozen stop
rule, close the candidate without tuning, sign inversion, horizon changes or another successor.
No strategy, PnL or costs were evaluated. The next permitted action is a materially different BTC
hypothesis under a new experiment ID. Zero strategy arms remain accepted and actionable routing
remains `no_trade`.

Evidence:

- `research/btc/reports/BTC_SPOT_PERP_CONTINUATION_D0_V3_RESULT.md`
- `research/btc/reports/BTC_SPOT_PERP_CONTINUATION_D1_V2_RESULT.md`
- `research/btc/reports/BTC_SPOT_PERP_CONTINUATION_D1_V3_RESULT.md`
- `research/btc/BTC_SPOT_PERP_CONTINUATION_TRACKER.json`
- `research/btc/BTC_SPOT_PERP_CONTINUATION_EVIDENCE_CATALOG.json`
- `artifacts/agent-level-experiment/btc-focused/spot-perp-continuation-d0-v3/audit-report.json`
- `artifacts/agent-level-experiment/btc-focused/spot-perp-continuation-d0-v3/evidence-manifest.json`
- `artifacts/agent-level-experiment/btc-focused/spot-perp-continuation-d1-v2/audit/audit-report.json`
- `artifacts/agent-level-experiment/btc-focused/spot-perp-continuation-d1-v2/evidence-manifest.json`
- `artifacts/agent-level-experiment/btc-focused/spot-perp-continuation-d1-v3/audit/audit-report.json`
- `artifacts/agent-level-experiment/btc-focused/spot-perp-continuation-d1-v3/audit/evidence-manifest.json`
- `artifacts/agent-level-experiment/btc-focused/spot-perp-continuation-d1-v3/evidence-manifest.json`

## BTC unified backtest engine E0 — 2026-09-05

Qualification ID: `btc-unified-backtest-engine-e0-v1`  
Disposition: **E0 specification passed; E1 synthetic kernel only permitted**

Before another BTC hypothesis is evaluated, an independent accounting audit found that the
existing engines cannot yet be treated as one authoritative spot/perpetual backtester. Material
defects include signal-reference exit fills in the legacy spot core, conflated decision/fill time,
inconsistent funding/rebalance order, incomplete isolated-collateral state, possible missing
funding across gaps, close-only liquidation checks, reversal cost misattribution, a warm-up-shifted
always-long control in place of true buy-and-hold, and same-code replay presented as an independent
audit. Prior results remain preserved; E4 must reconcile them rather than rewrite them.

E0 now freezes one canonical Decimal specification for BTC/USDT spot and linear BTCUSDT USD-M
perpetual accounting. It defines exact next-hour candle fills, same-timestamp funding ownership,
opening-gap and adverse-intrabar liquidation, collateral transfers, signed realized/unrealized
PnL, native fee effects, cash costs versus diagnostics, effective-dated rules, gap invalidation,
deterministic pair neutralization, causal partition termination, row-level lineage, controls and an
implementation-independent E2 oracle. Candle execution is all-or-none; partial fills require
synthetic or separately qualified quote/L2 evidence.

The first validator invocation is preserved as a preflight failure: it wrote a report and then
failed while relativizing a caller-supplied output path, before a manifest was emitted. The fixed
validator resolves the output path first. Five mutation/canonicalization tests pass, the complete
qualification verifies all eleven authority hashes and eight semantic gates, and an adversarial
review passed after fourteen blocking areas were corrected. No historical market row or strategy
return was opened, and no 2026, partial OB0, credential, production or protected service was used.
Zero arms remain accepted and actionable routing remains `no_trade`.

Evidence:

- `research/btc/contracts/btc-unified-backtest-engine-e0-v1.json`
- `research/btc/reports/BTC_UNIFIED_BACKTEST_ENGINE_E0_PLAN.md`
- `research/btc/reports/BTC_UNIFIED_BACKTEST_ENGINE_E0_REVIEW.md`
- `scripts/validate_btc_unified_engine_e0.py`
- `research/btc/tests/test_unified_engine_e0.py`
- `artifacts/agent-level-experiment/btc-focused/unified-backtest-engine-e0-v1/qualification-report.json`
- `artifacts/agent-level-experiment/btc-focused/unified-backtest-engine-e0-v1/evidence-manifest.json`
- `artifacts/agent-level-experiment/btc-focused/unified-backtest-engine-e0-v1-failed-preflight-path-normalization/FAILURE.md`

Next permitted action: implement E1's Decimal accounting kernel against synthetic fixtures only.
Historical reconciliation, paper observation and a new strategy hypothesis remain prohibited until
their prerequisite engine phases pass.

## BTC unified backtest engine E0-v2/v3 and E1 — 2026-09-06

Disposition: **E1 clean-room synthetic kernel passed; E2 independent oracle only is next**

Independent oracle construction exposed eight residual economic ambiguities after E0-v1 passed and
an untested E1 draft had been written. The draft was checksummed and removed from active paths.
E0-v2 froze the missing collateral, margin, liquidation, Decimal, terminal and fee semantics and
passed review. A later E1 attempt was independently rejected for copying substantial structure from
the prohibited draft; its exact source, tests and failure history are preserved unchanged.

A genuinely clean-room implementation then exposed an unbound ordinary atomic-pair close path.
E0-v3 froze exact machine-authority lineage and Cartesian spot/perpetual partial outcomes, committed
spot-first fills, native fees, severe residual and whole-pair neutralization, mismatch valuation,
funding/margin/liquidation checkpoints and terminal/segment handling. V3 passed only after repeated
adversarial review closed every literal ambiguity, including the zero-residual case.

The accepted clean E1 module passes 38 focused tests and 46 combined E0/E1 tests. Exact independent
terminal-NAV fixtures reconcile at 1019.37 for spot and perpetual longs, 1019.43 for a perpetual
short, 989.58 for reversal, 982.17 for funding liquidation, 979.68 for an exposed gap and 999.45
for pair-leg failure. The implementation compiles, contains no float literal, uses only standard-
library imports and remains clean-room independent of both invalid drafts. No historical row,
strategy return, 2026, partial OB0, credential or protected service was accessed. This accepts
accounting infrastructure only; zero strategy arms are accepted and `no_trade` remains actionable.

Evidence:

- `research/btc/contracts/btc-unified-backtest-engine-e0-v2.json`
- `research/btc/contracts/btc-unified-backtest-engine-e0-v3-pair-close.json`
- `research/btc/reports/BTC_UNIFIED_BACKTEST_ENGINE_E0_V2_REVIEW.md`
- `research/btc/reports/BTC_UNIFIED_BACKTEST_ENGINE_E0_V3_PAIR_CLOSE_REVIEW.md`
- `src/trading_platform/btc_decimal_ledger_e1.py`
- `research/btc/tests/test_btc_decimal_ledger_e1.py`
- `research/btc/reports/BTC_DECIMAL_LEDGER_E1_RESULT.md`
- `artifacts/agent-level-experiment/btc-focused/unified-backtest-engine-e1-v3/qualification-report.json`
- `artifacts/agent-level-experiment/btc-focused/unified-backtest-engine-e1-v3/evidence-manifest.json`
- `research/btc/invalid/unified-backtest-engine-e1-v1-ambiguous-draft/README.md`
- `research/btc/invalid/unified-backtest-engine-e1-v2-clean-room-violation/README.md`

Next permitted action: E2 must implement an independent oracle that consumes only canonical fixture
and emitted-event JSON. It may not import or share kernel code, dataclasses, ledgers, execution
helpers or metrics. Historical reconciliation remains prohibited through E3.

## BTC unified backtest engine E1 revocation and v4-v14 closure — 2026-09-06

Disposition: **E1 rejected and blocked; E2 and historical reconciliation prohibited**

The E1-v3 pass above is retained as history but revoked. A later context audit established that a
paused draft bound by E0-v3 had been changed at mutable active paths before its exact bytes were
archived; the required lineage is irrecoverable. E0-v4 preserves the incident and freezes lineage
recovery without changing the economic semantics.

Ten successor identities were then evaluated fail-closed. V4 was underimplemented; v5 leaked the
future independent oracle into implementation design; v6 failed structural state-machine gates;
v7 omitted required independent probes; v8 used self-referential probes and lacked atomic-entry
guarantees; v9 contained phase contradictions; v10 inherited opaque probes; v11 remained a
bypassable monolith and substituted incomplete controls; v12 did not freeze RunSpecs and had
overlapping probe ownership; and v13 mismatched the L2 scenario contract. All are preserved in
their corresponding `research/btc/invalid/unified-backtest-engine-e1-v*/` directories and must not
be tuned under the same IDs.

V14 was the strongest candidate: its frozen modular snapshot compiled, verified 20 manifest
bindings, and passed 87 focused tests plus the eight inherited E0 tests. Two independent reviewers
nevertheless rejected it. Blocking defects were forgeable construction/facade authority, a valid
L2 transition with `event_accounting_residual = -0.1`, incomplete whole-implementation and RunSpec
lineage, missing L2 30/40/80-bps reports, candle execution substituted for L2 controls, L2 safety
and terminal paths bypassing depth and latency, unintegrated fee/tax effects, incomplete pair
preflight and unsafe post-commit failures, incorrect pair direction labels, severe-scenario
relabelling, incomplete funding timestamp causality and incorrect sell-side bounds.

Evidence:

- `research/btc/contracts/btc-unified-backtest-engine-e0-v4-lineage-recovery.json`
- `research/btc/reports/BTC_UNIFIED_BACKTEST_ENGINE_E0_V4_LINEAGE_RECOVERY_PLAN.md`
- `research/btc/incidents/unified-engine-v3-missing-paused-draft-tombstone.json`
- `research/btc/invalid/unified-backtest-engine-e1-v4-underimplemented/`
- `research/btc/invalid/unified-backtest-engine-e1-v5-oracle-leak/`
- `research/btc/invalid/unified-backtest-engine-e1-v6-structural-failure/`
- `research/btc/invalid/unified-backtest-engine-e1-v7-incomplete-probes/`
- `research/btc/invalid/unified-backtest-engine-e1-v8-self-referential-probes/`
- `research/btc/invalid/unified-backtest-engine-e1-v9-phase-contradictions/`
- `research/btc/invalid/unified-backtest-engine-e1-v10-opaque-probe-inheritance/`
- `research/btc/invalid/unified-backtest-engine-e1-v11-monolith-boundary-failure/`
- `research/btc/invalid/unified-backtest-engine-e1-v12-unfrozen-runspec-overlap/`
- `research/btc/invalid/unified-backtest-engine-e1-v13-l2-scenario-mismatch/`
- `research/btc/invalid/unified-backtest-engine-e1-v14-accounting-authority-failure/README.md`

No historical market row, strategy result, 2026 partition, partial OB0 data, credential, network or
protected service was accessed. No strategy arm is accepted and `no_trade` remains actionable.

Next permitted action: conduct a bounded design review that replaces the impossible Python
anti-introspection requirement with a precise supported-public-API contract and divides candle
accounting, L2 execution and atomic-pair accounting into independently qualifiable components. Do
not create v15, implement E2 or open historical evidence until that review is frozen under a new
experiment ID.

## BTC unified engine C0 design attempts E0-v5 through E0-v11 — 2026-09-06

Disposition: **all rejected; C0 implementation and every downstream component remain blocked**

The post-E1-v14 architecture review was narrowed from a full component graph to a supported
offline-Python C0 authority/manifest/RunContext boundary. Seven immutable identities were
attempted and preserved. V5 had inconsistent ownership and incomplete schemas/obligations; v6
repeated the over-broad downstream monolith; v7 lacked exact scenario, digest, UTC, bundle and
review semantics; v8 and v9 failed frozen path-scan preflight; v10 lacked a RunSpec registry and
exact cross-record lineage; and v11 still failed independent semantic-closure review.

V11 was the strongest design. Nine preflight checks, 21 focused tests and eight inherited E0 tests
passed. Two independent reviewers rejected it because the on-disk future scan was not whole-tree,
C0 manifest authority closure was role-only rather than byte-exact, nested AuthorityRef consumers
were inconsistent, scenario role semantics were ambiguous, RunContext projection was prose rather
than an exact source/output map, and some contract/spec mutations were not semantically pinned.
Passing self-tests are not acceptance evidence; no review-pass artifact exists.

Preserved evidence:

- `research/btc/invalid/unified-backtest-engine-e0-v5-post-freeze-design-failure/`
- `research/btc/invalid/unified-backtest-engine-e0-v6-overbroad-downstream-contract/`
- `research/btc/invalid/unified-backtest-engine-e0-v7-c0-boundary-review-failure/`
- `research/btc/invalid/unified-backtest-engine-e0-v8-preflight-path-failure/`
- `research/btc/invalid/unified-backtest-engine-e0-v9-preflight-self-path-failure/`
- `research/btc/invalid/unified-backtest-engine-e0-v10-registry-lineage-review-failure/`
- `research/btc/invalid/unified-backtest-engine-e0-v11-semantic-closure-review-failure/`

No C0-C6 implementation, E1-v15, E2, market row, strategy result, 2026 partition, partial OB0,
credential, network or protected service was accessed or created. The next permitted action is a
new E0-v12 C0-only design identity that closes only the enumerated v11 findings. It must scan the
whole repository with an exact whitelist, bind exact C0/E0 authority tuples, enumerate the
RunSpec-to-RunContext projection, use context-appropriate AuthorityRef consumer types, make role
mapping exact, and semantically pin every contract/spec/obligation boundary before freezing its
manifest. `no_trade` remains the only actionable arm.
