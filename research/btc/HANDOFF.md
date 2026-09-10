# BTC-focused research handoff

Current status: R2-v2 accounting reconciled; A0 execution defects confirmed; correction specification required; no strategy accepted  
Latest program: `btc-only-research-v1`  
Latest review: `btc-breakout-execution-source-audit-a0-v1` — execution findings confirmed  
Latest experiment: none — E1 is infrastructure qualification, not a strategy experiment  
Selected strategy candidate: none — continuous price-trend blend closed  
Active strategy experiment: none  
Accepted strategy arms: none  
Actionable arm: `no_trade`

## Completed evidence

Consolidated review for the user: `research/btc/BTC_PROGRAM_REVIEW_2026_09_10.md` covers
objectives, layers, strategy triggers, periods/sizing/metrics, evidence limits and next correction.
It changes no experiment result or acceptance decision.

R1-v3 wider numeric domain passed independent review; R2-v2 reconciled all201 archived records
and1005 cash/carryforward comparisons. Largest absolute discrepancy <7.3e-13 USDT. Precision
is resolved; 30/40/80-bps legacy returns reproduce at16.935547/16.139102/13.014102 percent.
A0 synthetic execution probes independently confirmed planned-open/stop chronology, close
timestamp and retrospective segment-exit concerns. No historical candle data or corrected
strategy returns were opened. See `research/btc/reports/BTC_ACCOUNTING_RECONCILED_EXECUTION_AUDIT_RESULT.md`.

R2-v1 reached its numeric compatibility blocker after reviewed code freeze and first trade decode.
All 201 quantities exceed 12 fractional places (maximum19); two entry and two exit fills use13.
Structural/hash/scenario gates passed. Accounting did not run; no return was computed.
See `research/btc/reports/BTC_R2_V1_RESULT.md`. This precision mismatch requires a newly
qualified numeric domain and successor replay ID; no archived quantity was rounded.

R2-v1 replay contract is frozen before trade rows. Source metadata identifies 201 records.
Strict numeric compatibility stops without rounding. See `research/btc/reports/BTC_ARCHIVED_BREAKOUT_R2_FREEZE.md`.

R1-v2 explicit-fill accounting passes independent review, eight literal cases and four test
methods including a 10000-event exact Fraction reconciliation. V1 is preserved as rejected after
the reviewer found precision-50 rounding loss; v2 uses a proven precision-80 domain. Result:
`research/btc/reports/BTC_REFERENCE_R1_RESULT.md`. Reproduce with
`python3 -m unittest -v research.btc.tests.test_reference_r1`.
No historical fills, market rows or strategy performance were evaluated.

Source-only spot-control reconciliation review is complete. R0's hourly timing, separate fees
and rounding differ from the legacy breakout's five-minute combined-cost execution. Earlier
golden-control checks compare saved metrics rather than replay historical fills through R0.
Plan: `research/btc/reports/BTC_REFERENCE_BACKTESTER_R1_RECONCILIATION_PLAN.md`.
Next use synthetic explicit-fill accounting, then separately authorized archived-trade arithmetic,
then a distinct execution/causality audit. No market or trade rows were opened for this review.

R0-v1 synthetic ledger now passes all 17 literal scenarios and four test methods, with independent
review after rounding/context defects were corrected before freeze. Result and limitations:
`research/btc/reports/BTC_REFERENCE_BACKTESTER_R0_V1_RESULT.md`.
Reproduce: `python3 -m unittest -v research.btc.tests.test_reference_r0`.
Historical execution and all strategy qualification remain pending.

R0-v1 synthetic contract and 17 literal accounting cases are frozen before implementation.
Inputs: `research/btc/contracts/btc-reference-backtester-r0-v1-input-manifest.json`.
Specification: `research/btc/contracts/btc-reference-backtester-r0-v1.md`.
Expectations: `research/btc/reports/BTC_REFERENCE_BACKTESTER_R0_V1_EXPECTATIONS.md`.
Primary/stress/severe unchanged-price round trips were independently arithmetically checked.
That pre-implementation freeze is preserved; the narrow synthetic implementation is now accepted.

E0-v12 is rejected after two fresh independent reviews on 2026-09-08. Nine preflight checks and
33 focused/inherited tests passed, but review found a future contract/registry/manifest checksum
cycle, unqualified archive exclusions and semantic tests relying on snapshot pins. The frozen
stop rule closes custom C0 architecture. No E0-v13 retry is permitted. All eight frozen artifacts
are preserved in `research/btc/invalid/unified-backtest-engine-e0-v12-final-review-failure/`.
Run `python3 scripts/validate_btc_focused_context.py` to verify archive bytes and current context.
The new bounded plan is `research/btc/reports/BTC_REFERENCE_BACKTESTER_NEXT_PLAN.md`.

The following sections preserve earlier evidence; their historical permission statements are
superseded by the current status and final next-action section.

The bounded component-design program remains rejected through E0-v11. V5 and v6 repeated broad
schema and ownership failures. V7 narrowed scope to C0 but failed exact scenario, digest, UTC,
bundle, obligation and review gates. V8 and v9 were preserved after frozen path-scan failures. V10
lacked a RunSpec registry and exact selection lineage. V11 added the registry, exact mandate and
scenario-row mappings, typed roles and exact obligation tuples; its nine preflight checks, 21
focused tests and eight inherited tests passed. Both independent reviewers still rejected it for
incomplete whole-tree scanning, role-only authority closure, inconsistent nested consumers,
ambiguous scenario roles, a non-enumerated RunContext projection and incomplete semantic pinning.
No pass review exists and no C0 implementation is authorized. See
`research/btc/invalid/unified-backtest-engine-e0-v11-semantic-closure-review-failure/README.md`.

The former E1-v3 pass is revoked because its required paused-draft lineage cannot be reproduced.
Successors v4 through v14 are preserved under `research/btc/invalid/`; none qualified. The latest
modular v14 candidate compiled and passed 87 focused tests (95 with inherited E0 tests), but two
independent reviews rejected it for forgeable authority/facade boundaries, a non-zero residual on
valid L2 fills, incomplete implementation lineage and cost reports, candle substitution or bypass
on L2 paths, unintegrated fee/tax effects, and unsafe/incomplete pair preflight and recovery. The
passing self-tests are engineering diagnostics, not acceptance evidence.

E1 therefore remains blocked and E2, historical reconciliation and all strategy evaluation are
prohibited. The next permitted action is a bounded design review: define a supported public API
boundary appropriate to offline Python research, then specify independently qualifiable candle,
L2 and atomic-pair components under a new identity. Do not create or implement v15 before that
review. See
`research/btc/invalid/unified-backtest-engine-e1-v14-accounting-authority-failure/README.md`.

The unified BTC spot/linear-perpetual engine E0 specification passed independent adversarial
review. It freezes exact next-open execution, funding ownership, isolated collateral, signed PnL,
fee assets, liquidation and gap semantics, cost classification, controls, canonical row lineage,
and a structurally independent oracle. Five focused contract tests and all eight semantic gates
pass; eleven machine authority hashes verify. The preserved first invocation failed only while
constructing its manifest path and was not accepted. No market row or strategy return was opened.
E1 may now implement the Decimal accounting kernel on synthetic fixtures only. See
`research/btc/reports/BTC_UNIFIED_BACKTEST_ENGINE_E0_REVIEW.md`.

The frozen 7/28/84-day perpetual trend blend earned 48.30% at 30 bps in 2020–2023 development
but lost 6.41% in consumed 2024–2025, with both years negative; severe stability lost 12.77%.
It failed stability, control, bootstrap, concentration, annual and severe gates. The simple 28-day
control earned 122.21% in development but also lost 7.13% in stability; always-long earned 7.06%
in stability. The byte-identical replay confirms rejection. Do not tune or regime-rescue this
price-trend family. Result: `research/btc/reports/BTC_MULTIHORIZON_PERP_TREND_V5_RESULT.md`.

The prior directional-perpetual trend lineage is closed. Its historical run was opened once under
v5 and rejected; do not follow older handoff text that described a historical run as pending.

Prior completed evidence follows.

Safe funding-carry risk v2 is complete. It preserved v1's funding signal exactly and changed only
risk implementation to 25% per matched leg, 75% planning collateral and a causal 2.0 minimum
20%-shocked margin ratio. On consumed 2024–2025 evidence, the gated strategy returned 2.95% at
primary and 1.33% at severe costs, with 0.21% primary drawdown, six trades, both years positive,
positive funding attribution and zero observed/shocked breaches or risk exits. Minimum shocked
ratio was 9.5117. Normalized return per unit exposure closely matched 49% v1, so the lower headline
return is sizing—not weaker or stronger alpha.

The unchanged timing rule failed again. Same-exposure always-on carry returned 7.75% and earned
0.01061% per exposed day versus 0.00679% for the gate, while retaining zero breaches and a 2.0719
minimum shocked ratio. Close the 60/30 bps funding-timing rule. Always-on remains an unaccepted
structural benchmark: it has one continuous evaluation trade, consumed evidence, unmodeled
collateral opportunity cost and incomplete promotion economics. The isolated replay is byte-
identical and the independent audit passed every check. Exact evidence and commands are in
`research/btc/reports/BTC_SAFE_FUNDING_CARRY_RISK_V2_RESULT.md`.

Current safe carry v2 checksums:

- contract: `bbc26048579c5078ac4e2eeb6262ffc80489a5688b8cd6714ba7f4aad56c9ec8`;
- report: `b894aec7a10675a6ace2169f73e8797aeaf51ba235c14eaff34d311f4d56b254`;
- primary trades: `3820c0cad386259be388c0164fd57c97b21a24e58a9b9ad3f988e253797bd6aa`;
- evidence manifest: `4fbfc4be0e91768a92717a84ad4470c619ed674f2463fdc429cc998eac938e1b`;
- independent audit: `9426d413900cf100d840e69aa1893bf57287e71fa168ff595f5a96784f8b7d81`;
- audit manifest: `ec562ee8342b3a55ba57247bc58f94b8da6659298bdea595cc3812aa1214fb72`;
- result document: `f666c216446f8b08e34b1056030e6ec531250a0cc5871db76f4f27c815b721c5`.

D1-v3 is rejected and the continuation-information hypothesis is closed. It corrected the D1-v2
endpoint-label eligibility defect without changing the feature ledger, horizon, models or gates.
All 2,209 requested endpoints were authenticated in 73 official Binance monthly archives. The
label gate passed at 1,823/1,823 evaluation rows and 100% in every 2021–2025 year. The 48 windows
crossing interior gaps remain diagnostics; no endpoint was missing and no value was interpolated.

The unchanged walk-forward test then rejected the economics. M1 MSE was 0.002792931256 versus
0.002778148523 for price-only M0 and 0.002760098760 for B0, a 0.532107% worsening against M0.
Only 2022 and 2025 improved; all three block-bootstrap intervals crossed zero; excluding the best
three months stayed negative; and both candidate-feature median coefficients had signs opposite
the frozen continuation theory. A clean isolated replay reproduced the endpoint, label, forecast
and snapshot ledgers byte-for-byte, and the independent audit passed every check. This is not a
strategy or profitability result. Do not tune, invert or create D1-v4. Exact evidence and commands
are in `research/btc/reports/BTC_SPOT_PERP_CONTINUATION_D1_V3_RESULT.md`.

Current D1-v3 checksums:

- v3 contract: `2fd5da347538e8ff87fa852d26e822148b3110f944cad124a52e7c380151ab47`;
- reused v2 feature ledger: `2181b5df0a20bc0b545634971ebe1b2d6a2313a22fccfe1a04e73b642070a1fa`;
- endpoint ledger: `f9f840f968401f5537a8d627da3761e6ccf62d668a2a31223b0f7fe7b12a8694`;
- label ledger: `6c3bff77c0af80553312d8135640f93879a6148d21112f99525659cf26bf7f09`;
- forecast ledger: `69778b8edc633657b6fbe2fe8d039db33218c5b68e7550c3c7e25cb33311d2da`;
- model snapshots: `f445b29a873952d39f7b155c061bb9eaed2d0a79baa6bde0b5517ac752cba5f3`;
- model report: `a89f1bf3ebab91cb40c99b69faf4e60382d3610376fbcd8843c688d35c64b1ba`;
- independent audit: `20672beffd1b27956c7f2654073b33d2f4dd8a2f572974b877efc8c0b9ce1452`;
- audit manifest: `cf305d56ce0a5841b48018c1829df1ff335af454a216281a360dd18cd60da9d1`;
- top evidence manifest: `c695eae28edbc065d7e06c4cda0542a9c8f163d9fe58bde2497eaef279672852`;
- result document: `98cacab3944f3b48c86ce4659e1474e12ba23a94e61aa79784103bef88a7b1ce`.

D0 v3 passed all frozen label-blind source gates using official direct daily BTCUSDT spot and
USD-M perpetual bars. All 148 monthly archives and sidecars matched; REST/archive overlaps were
exact; the 2,307 common days from 2019-09-08 through 2025-12-31 form one segment; common coverage
is 100% in every 2020–2025 year; and the 90-day warm-up leaves 391 feature-ready days before 2021
and at least 365 in each evaluation year. D0 v1 remains rejected for hourly gap-reset readiness,
and D0 v2 remains a preserved parser preflight failure on official partial-hour bars. This is not
forecast or strategy evidence: no label, model, PnL, position, order, 2026, partial OB0, protected
service, account or credential was used. Exact result and reproduction commands are in
`research/btc/reports/BTC_SPOT_PERP_CONTINUATION_D0_V3_RESULT.md`.

Current D0 v3 checksums:

- contract: `68070f31edb37c261654512e2e5f73331f839e5012fb825d7a02e39c87140a1d`;
- source manifest: `d7a0e6c2855bb0c67fff91e6712f099040123450973791ca5530460505c90bc3`;
- audit report: `556198f3222e79a660a1bbe49e63c79aea7fdb6423e261c6f6cf57107e423578`;
- segment report: `73e74d26fac65163027d488e76c1ac60c6c7444a8cc5164410c02c6a7408bec1`;
- evidence manifest: `32e0d66a18424b9dfedd4565132e2660922118ba37d1f85759a6dce88a0ef8ac`;
- result document: `11aebe888022dc43a66436b33c9504b79eec2f12a7fd19b21a1ddbac600cabff`.

BEX1-v5 passed its independently audited event-catalogue engineering gates on the immutable
2017–2025 source. It found 92 non-overlapping setups and only 36 model-ready confirmations:
12 continuation and 24 range re-entry. Those counts fail the frozen BEX2 minima of 200/60/60;
2021 also has no evaluation event. Therefore no empirical, linear, histogram-boosted or XGBoost
historical model was fitted, and the thresholds may not be relaxed under this ID. This is not a
strategy or profitability result: no PnL, cost, position or order was computed. The independent
audit verified all bound/artifact hashes, all record and catalogue digests, non-overlap, counts,
boundary safety and `no_trade`. Exact result and reproduction commands are in
`research/btc/reports/BTC_UPSIDE_BREAKOUT_BEX1_V5_RESULT.md`.

The new strategy-direction tracker preserves four price-behaviour families and eight directional
legs while selecting only the long upside break from a completed compression range. Every other
leg is deferred; short legs also require a new mandate. The candidate is explicitly not another
fixed-breakout lookback: its future contract must freeze both a pre-break compression state and an
upside confirmation. Compression, range, target, horizon, entry, exits, sizing, folds, costs,
controls and rejection gates all remain unfrozen, so no market outcome or PnL may be opened and no
runner may be implemented. The candidate remains in the `btc_directional_trend` routing family;
prior fixed breakout, SMA, BOCPD gate and volatility-expansion evidence stays negative or control
evidence. Zero arms remain accepted and `no_trade` remains actionable.

The synthetic-only score-combination foundation now binds score identity to exact target, horizon,
kind, units, evidence status and permitted use; provides causal empirical midrank calibration using
only samples available by each score fit cutoff; and allows fixed convex combination only for
current `benchmark` or `accepted` forecasts sharing identical semantics. Rejected/development,
unknown, stale and mismatched members fail closed. Every ensemble output remains `development`,
exposes `actionable_arm_id = no_trade` and cannot create a strategy action. This does not activate
MCS4, combine any current rejected detector, fit weights or duplicate the existing minimum-cap
risk policy. Nine focused and 40 adjacent tests pass, and the report/manifest replay is
byte-identical. No market value, strategy, PnL, 2026, partial OB0, network or protected service was
used.

The metadata-only MCS3-C readiness audit blocks activation of the named net-carry score. Funding,
perpetual execution and recovered mark/index histories pass; spot is conditionally usable with
hard segment resets; premium's one missing hour is optional and must fail flat/reset if consumed.
Four gates fail independently: effective-dated historical spot/perpetual fees, effective-dated
maintenance-margin brackets, historical contract/funding/liquidation/ADL rules, and a frozen
collateral-financing treatment. Exact account fees are absent but promotion-only. Current rule
snapshots, the generic 30/40/80-bps grid and development-only 10% maintenance/20% shock assumptions
cannot be projected backward as exact historical economics. The whole 2020–2025 boundary is
consumed development evidence and carry-v1 remains rejected and closed. Nine focused tests and a
byte-identical report/manifest replay pass. MCS3-C was not activated, MCS4 is blocked and this
score-panel branch stops. No raw market/PnL ledger, score, strategy, 2026, partial OB0, network or
protected service was used.

MCS3-J is rejected under its frozen jump/change information gates. On 12,118 primary four-hour
common rows, the fixed-lambda 0.94 EWMA was worse than the rolling 180-block control on average
precision (0.013570 versus 0.015547), Brier loss (0.008304 versus 0.008102), log loss (0.063402
versus 0.046138), intensity MSE (0.013082 versus 0.012910) and intensity MAE. Exact-seed
month-block improvement intervals were wholly negative for Brier, log loss and intensity MSE;
all seven annual and all seven leave-one-year-out comparisons were negative, and best-three-month
exclusions stayed negative. There were 99 proxy events versus the 100 minimum, but the rejection
does not hinge on that near miss. Intensity quartiles were monotone and unconditional calibration
passed, neither of which rescues worse comparative forecasts. Twelve focused tests, 35 adjacent
regressions and a byte-identical four-file replay pass. The forecast source digest is an
evaluation-record digest because it also binds the later target; do not reuse it as decision-time
feature lineage. Do not tune MCS3-J or map it to a cap. No strategy, position, cost, PnL, 2026,
partial OB0, network or protected service was used.

MCS3-D is rejected under its frozen joint downside/tail gates. On 2,111 primary one-day common
rows, the causal monthly log-HAR negative-semivariance component improved QLIKE from -6.609755 to
-6.769489, reduced MSE by 17.54%, had a positive exact-seed month-block interval and produced
monotone realized-risk quartiles. The frozen square-root scaling of historical VaR/ES failed:
candidate FZ0 was -2.631575 versus the better -2.640870 benchmark, candidate pinball was 0.003698
versus 0.003661, FZ0 uncertainty crossed zero, exclusion of the best three FZ0 months was negative,
and only two of seven annual and two of seven leave-one-year-out joint comparisons passed. VaR/ES
calibration and all coverage gates passed but cannot offset worse proper tail losses. Independent
review caught that the preliminary run improperly restricted historical losses to feature-eligible
rows; it and its replay are preserved under `invalid` paths. Correcting only that eligibility bug
confirmed rejection. Eleven focused tests and a byte-identical corrected four-file replay pass. Do
not tune the favorable semivariance diagnostic or map it to a cap. No strategy, position, cost,
PnL, 2026, partial OB0, protected service or executable action was used.

MCS3-R is rejected under its separately frozen displacement-unwind gates. Its causal 24h
displacement z-score used only the preceding 126 completed observations; absolute z>=2 events and
their targets were chronologically non-overlapping. The primary one-day cohort contained 300
events with balanced directions and adequate yearly counts. Pooled signed reversal was only 12.46
bps versus the 80 bps gate; the equal-month estimate was negative and its interval crossed zero.
Negative displacements rebounded by 52.35 bps on average, while positive displacements continued
with -24.86 bps signed reversal, rejecting the frozen symmetric claim. Matched deltas, annual
stability, best-three-month exclusion, 68.67% strict matched-control coverage and 83.57% feature
coverage also failed. The downside-only observation is exploratory and cannot be selected under
this ID. Seven focused tests, invariant checks and a byte-identical replay pass. No strategy,
position, execution, cost, PnL, 2026, partial OB0, protected service or executable action was used.

MCS3-P is rejected under its frozen standalone information gates. Using completed same-segment 4h
BTC candles, it asked whether signed directional efficiency across the prior 42 returns added
information beyond the same seven-day cumulative log return. Monthly expanding fits used only
labels available strictly before each cutoff. At the primary seven-day horizon the expanded model
worsened MSE by 1.19%; the incremental HAC interval crossed zero; month-block rank IC and
squared-error improvement intervals were negative; score buckets were non-monotone; and only four
of seven annual coefficients were positive. Overall seven-day coverage was 88.94%, below the
frozen 90% gate. Secondary 4h/1d results did not jointly pass. Seven focused tests and a
byte-identical report/forecast replay pass. A preliminary seed-offset run is preserved as invalid;
the final run uses the exact single frozen bootstrap seed for every metric. This exact score cannot
condition a strategy. No strategy, cost, PnL, 2026, partial OB0, protected service or executable
action was used or created.

MCS2 passes as synthetic score/primitives infrastructure. `MarketConditionScore` preserves one
target-specific axis, forecast kind, horizon, fit/observation/availability/expiry timestamps,
point/interval, confidence, evidence status, unknown reason and lineage; only benchmark or accepted
evidence can report itself eligible for later conditioning. Its panel rejects future/duplicate
scores and deliberately exposes no aggregate or universal label. Causal extraction plus 12 frozen
primitives cover volatility-scaled return, efficiency, autocovariance, variance ratio,
standardized displacement, signed semivariance, bipower/jump variation, labelled Amihud and
Corwin–Schultz proxies, and completed funding/basis transforms. Eleven focused tests, 37 combined
regressions and a byte-identical replay pass. No market value, threshold, fit, strategy, PnL, 2026,
partial OB0, protected service or executable action was accessed or created. None of the primitives
has yet demonstrated BTC forecast information.

MCS1 passes as metadata and immutable-contract infrastructure. It verified 14 frozen metadata
inputs and emitted eight deterministic availability records. Segment-aware 5m/4h/1d candles are
research-ready for separately frozen persistence, reversion, volatility, downside/tail and jump
experiments; official daily closes remain the mandatory volatility benchmark and matched
spot/perpetual data are conditional carry-research inputs. The legacy 1h manifest fails closed
because it lacks explicit coverage and segment boundaries; rederive it later from accepted
segmented 5m data. Liquidity is proxy-only pending OB1; DVOL and on-chain remain blocked. The new
`MarketConditionObservation` preserves independent axis, segment, source-window,
observed/available timestamps, unknown state and lineage. Seven tests and a byte-identical replay
pass. No market value, score, model, strategy, PnL, 2026 row, partial OB0, protected service or
executable action was accessed or created.

The public-document-only BTC on-chain source review approved no dataset and acquired no metric
value. CryptoQuant fails causality because it explicitly revises historical exchange-flow values
as wallet clusters change. Glassnode has the strongest immutable point-in-time design, but its
verified `computed_at` history begins only in September 2024 and most PiT metrics have limited
history; exact Professional price and durable exported-data rights are unresolved. Coin Metrics
does not publicly establish historical label-version semantics. Nansen claims historical
label-as-of reconstruction and offers a free allowance, but public documentation does not yet
prove an exact aggregate BTC exchange-flow endpoint, history start or publication timestamp. No
purchase or signal freeze is justified. A separately frozen free-tier Nansen technical pilot is
the only bounded successor before this historical source branch is closed.

The causal monthly expanding log-HAR-RV challenger used complete same-segment five-minute realized
variance with one-, five- and 22-day components. Against both the mandatory close-return EWMA and
a same-input RV EWMA, it passed every frozen forecast-quality gate at one and seven days. One-day
QLIKE was -6.173005 versus -6.091550/-6.086221, MSE was 12.68%/27.38% lower, all seven years won,
and the paired month interval versus RV EWMA was `[0.06253, 0.12323]`. It is still rejected: two
missing day starts and 32 incomplete/cross-segment days propagate through 22-day HAR and 30-day
EWMA resets, reducing 2021 one-day coverage to 49.59% and 2019/2021 seven-day coverage to
49.86%/41.37%, below the frozen 50% per-year gate. The replay is byte-identical. Do not relax or
tune v1; it creates no usable cap, strategy, PnL or promotion evidence.
The initial horizon-offset bootstrap report is preserved as invalid; the final evidence uses the
exact frozen seed `20260831`.

The new risk foundation separates volatility, downside/tail, jump/change, implied-risk and future
liquidity forecasts instead of producing one universal market label. It supports daily risk-budget
and four-hour shock clocks. Only benchmark or accepted caps are usable; a missing required axis
fails to zero, while an existing position can only remain unchanged or shrink. Automatic
re-leveraging, direction changes, actionable routing and orders remain impossible. Six focused
tests pass and no model or strategy was fitted.

The V1 DVOL source pilot is preserved as rejected after its official documentation path returned
HTTP 404 before data acquisition. V2 changed only that path. Its three pre-2026 15-day windows
returned 45 valid daily rows with zero duplicates, non-daily gaps, invalid OHLC rows or JSON-RPC
errors; official API and methodology evidence also passed. This is technical source evidence only.
DVOL is not an approved historical model input until complete coverage, effective-dated
methodology changes, publication/revision semantics and retention rights pass separately.

The new canonical scorecard applies one UTC daily mark-to-market and evidence convention to the
fixed breakout, mandatory EWMA risk benchmark and rejected funding carry. All legacy carry
headlines reproduce exactly, while the common evidence view exposes the uncertainty hidden by six
trades: carry has only nine independent 84-day blocks, an adjusted Sharpe of 1.566 versus 5.066
conventional, a negative paired lower bound versus always-on carry and 92.50% top-three-trade
positive-PnL concentration. Fixed breakout also fails paired participation and its preserved random
timing gate; EWMA remains a control, not alpha. All three supplemental dispositions are evidence-
insufficient. No verdict changed, no strategy arm was accepted and no 2026, OB0, network, protected
service, regime model or tuning was used.

B0 keeps BTC as the only active market in this focused program, EWMA as the mandatory risk
benchmark and L2 as background engineering. B1 permits only offline, zero-capital research on a
matched long BTCUSDT spot / short BTCUSDT USD-M perpetual pair. It authorizes no credentials,
orders, transfers or live allocation.

B2 acquired and verified all 360 official monthly archives and sidecars. Execution klines and all
6,576 scheduled funding events pass, but 192 mark-price, 288 index-price and 169 premium-index
series-hours are absent, and historical effective-dated fee/margin economics remain incomplete.
No carry strategy was evaluated.

B3 now passes as engineering infrastructure. The new BTC spot long/flat core validates causal
exact-time fills, rejects gaps and segment crossings, uses the shared Decimal execution and cash/
inventory ledger, enforces mandate allocation/risk/frequency/loss stops, marks positions to market
and emits deterministic checksummed results. Thirty-eight targeted tests pass. The synthetic
replay is byte-identical and the frozen breakout and SMA development-control metrics match exactly.
This does not accept or reopen either strategy and does not fit a regime model.

The separately frozen B2 gap successor called only 18 exact unauthenticated official Binance REST
requests. It recovered all 192 mark rows, all 288 index rows and 168 of 169 premium-index rows.
The sole 2020-12-01 23:00 UTC premium request returned HTTP 200 with `[]`; the raw two-byte
response is preserved. The strict successor is rejected, although mark and index are now complete.
No interpolation, strategy result, PnL or regime model was produced.

The subsequently frozen carry v1 strategy never consumes premium index. It trades a matched 49%
long-spot/short-perpetual pair from weekly, past-only 28-day funding scores. On 2024–2025 it made
5.83% at primary and 2.61% at severe costs; primary drawdown was 0.42%, and funding attribution and
forward-information tests passed. It is still rejected because 260 hours failed the extra 20%
isolated-margin shock buffer and its return per exposed day did not exceed always-on carry. The
byte-identical replay is under
`artifacts/agent-level-experiment/btc-focused/replays/positive-funding-carry-v1-replay-20260830T2245/`.
Do not tune or regime-filter v1.

Latest checksums:

- strategy-direction tracker JSON: `8e1d0a274f3a7afb98f027ea61e159714ee10f8868a34c09d6af37e0b699da72`;
- strategy-direction tracker document: `7d3807cc2d96d878c0c02ba519718c206ad50c315c26cbba472fb34b414fe90f`;

- score-combination foundation contract: `52757b49393cf3dd70d80cf376525637565929ebc3b40b16a7907b3837016a0f`;
- score-combination foundation plan: `1fc30dbb9b93d6c43eda0ecec2f84e3fbef631aadbb8de1f26837930face8050`;
- score-combination foundation implementation: `86d8d963a407c71a660fd2cc5e5be9c8eaf450427c9812fd684cd2fdf5025e39`;
- score-combination foundation runner: `7cc86a500ad003c8a43e68ce602e892116840a1b7e22e970debd7016f0310bf4`;
- score-combination foundation tests: `d1c03125b2a8598e881cab5ca8e3d9aee9334f711cb00eb9d7fd8310a580c397`;
- score-combination foundation report: `ed78abe4c24305371c64883e5f002ef61deccd7afb37ba8dcc4f3ba99ce6c00a`;
- score-combination foundation manifest: `c06a03ab208ad61e70ffee156c6d2544255df4e10771e432dd66241084b8bf13`;
- score-combination foundation result: `281617e1a06b3e2bfdffdefb085474b164bc785f00497df1caa173c142cba7fe`;

- MCS3-C readiness contract: `9ca6fd35d7e10d90eced628e367641ad63653c993a5719537a8fdef309b72c24`;
- MCS3-C readiness implementation: `06e0d202992cf072bd7a104c2429147018b8ffb969aefa12265409f45f71161a`;
- MCS3-C readiness runner: `87ef72f990c29393cf9090f43eb8e8673f6ae0ddd66f272ed6edad56a6a4d6b2`;
- MCS3-C readiness tests: `5c0142214b1955e44a01eed94dc7111d95581406c16cad427d62228bd989eb13`;
- MCS3-C readiness report: `1db7081ad6dfda02874ae63f9c63ecc4cb19c834f7641524b074afe98a4e5409`;
- MCS3-C readiness manifest: `64b32e59006de9b270ad4f0cb254ae73fecb461f3aa94c12354cbf3ac4b9cefb`;
- MCS3-C readiness result document: `5ca5e1feb4b8c9dbce886d8d968fbd1c41d286c7c3b5a44011a323fc6d99470e`;

- MCS3-J contract: `0b96d3a5624d9a91f59e0c5a484b5515bb9ae06b00ff1ef72e3da384d6976fd2`;
- MCS3-J implementation: `e2aa6a9cfa48cd9e699ebcca13f8d5907099059291675f46d1698706307c8f8c`;
- MCS3-J runner: `2f07d6fc3cd7ab2607974202842834a4f3cbb1356b516de4bb636c0dfaa34b79`;
- MCS3-J tests: `387175636e597c500ae4891c7b587e1f7a385fd4371dba10ed62233fcc053fc2`;
- MCS3-J measurement ledger: `d0f0ed58e70979e198ecb8dc8cb042f2196b49f54330001d4fb64ced56d0ed6e`;
- MCS3-J forecast ledger: `9962704677a9704de539d64d4a1b65275a17afeb8904aca463fd7290c40f3ba8`;
- MCS3-J report: `916bd570a1e671c20530ed18209acb25546b9918f085269f3fff46bbba84d412`;
- MCS3-J evidence manifest: `2b5dede8dce898d6e1908e671013afc899258471414ecdcb927dcdc83e2c2fe0`;
- MCS3-J result document: `931f9c4848a09fb4f7877d4683f2048a674eb0f439a679c279f784fef6697c6a`;

- MCS3-D contract: `1206acf6e80f985bd491e60f1a67aa7135c84f4ea541be5835bd7050cbed1024`;
- MCS3-D implementation: `0e72e8a9691a85083ee56b6aeebf759e8a2caf0dc85154f3902201925e27e1e5`;
- MCS3-D runner: `585ac2d966aaae5cc71da15f912a3200dc8dae530a625cee175be8f2580bc6a3`;
- MCS3-D tests: `98a8eeb6c8aefe77fabc33f19f7d89228bbc9bf280e197b27af2355e0ee241f9`;
- MCS3-D forecast ledger: `c63395131f637688bb7b2deba922bc2d2d24ed529040c3be0465f379ae2d6802`;
- MCS3-D model ledger: `a79b38ecd2f724a4a39320422352b805e1a5e71183bfec0982d2a168c7227104`;
- MCS3-D report: `940a14b70ebe0dbefad0560293a7aa248d58367aeb31c9a1c6ab63e1d175d812`;
- MCS3-D evidence manifest: `003329d9685b692154bcfad710ca3afb47ca1ab6d355adb4f96f90ae9ca0a672`;
- MCS3-D result document: `36bec03178d702d84a775e076d977b434307965174330b756ff6900124fb945b`;

- MCS3-R contract: `76b8d2353ac3f25da9c2be52b3e979c7fc84c9b84e904662a945b5e1f5137f1c`;
- MCS3-R implementation: `ee3f3a7ae938bc26c4da61aaca4f39884240af0d39a78bcc1ca47eefe70a7bec`;
- MCS3-R runner: `28c85b88c25e9d3b8ae8358ee89935f6ecbc4993e33786a7c477bc565def845d`;
- MCS3-R event ledger: `6661ee5fb10d10b5cd8ee884bc826c0ca800630ebcc8aca15ce1c9cdebb6d87e`;
- MCS3-R report: `5644f28bb7e4c7518e5f879f3d1d3dbad7f82c944b589b0c8b09a2d3ab4f5962`;
- MCS3-R evidence manifest: `b457a5e413045417b24b23a0420f72d45f94886b0387baee7aeab0035b95f1e0`;
- MCS3-R result document: `cb0fbd57a2bb66817f1df693a08c2834143939468b57ee3d6cf020cacb01d88d`;
- MCS3-P contract: `c78352b57563155d1055276cdbc1aaaff25f57a453ac07b2441c65ffed044901`;
- MCS3-P implementation: `3b1bbb1a39a183917c0728edc26a0f48267337722beb32419b34ab9a8070a21c`;
- MCS3-P runner: `f0cc6432a4affdff5efd2849f5d112147176fda2964325d5e03f7a01e0adb3b0`;
- MCS3-P forecast ledger: `65ef7ca1ba66ad074a75862c77c8cc97fde9805bf4afbb4b2205c324115309bc`;
- MCS3-P report: `36e2b04f6270d9f13f7c3463099e82aafee2e9fb6ff5e4d33e18a88b088883e4`;
- MCS3-P evidence manifest: `3a3410bbe65c73f0d2432f2519b2401e4e026adb2abc1dd2e1cb6522b0d1cfe7`;
- MCS3-P result document: `3bda4084db13c5f8a7b25a2dc9e0ae4338df913d269d0945dfb064f74d8d4514`;
- market-condition score program: `e4b9a2bdc8b32c76715021bdf71ddc091265ab28ab3ce0ff092b73b8a12d22cb`;
- market-condition score contract: `0e7daffb6cd0ae92f684f6bec19cc40161e2387f00cbbbfd8abf955cedcb43df`;
- MCS1 contract: `244f780e68fa0d9cbe1f714903da282b849bfcc247741ebd424794c5d4c69de7`;
- MCS1 observation implementation: `977fc4e799077cea6f2ab34eb6106a9f587a6c4f2a1d68370f2cd0e92a9615ec`;
- MCS1 availability report: `b181832638bf69c34123ded46f67c9570fc84d36518ebc0be82ab11d4cbcc931`;
- MCS1 evidence manifest: `24867b0db7f0bbe1f28004ba41b3aa0d6d008edddf2fc0c65d694b0105c04a8a`;
- MCS2 contract: `4c3499da9621d6dcfc9ab615934b39c2934bba4fb3749df6cd41b421b1a6ca0a`;
- MCS2 score/primitives implementation: `4d74582802c329c169d892514f25b0ebbe3e73713f86bbb0da7a990687c77219`;
- MCS2 synthetic report: `01014659587faa7eccadacf91dad6f0d90a834d083257fe8a6a39a9e441f9661`;
- MCS2 evidence manifest: `6f5f696e1ed426c135f65911d31cd43efe774d0d3357026eff1853c1eca7f6b6`;
- on-chain source feasibility review: `e5b84ec62daee171de0c893c9f33c20a4e8480103ead1b1b57cd4aaa52bb7c58`;

- HAR-RV contract: `fcccd0b23c6501b964b0f9b9ccc429eef32d494b2bdfe7b84abba79d80277945`;
- HAR-RV forecast ledger: `d56cfc92f6b768affdb38d9f704c523871bfb2a91dada1089e3530427ca3d0a0`;
- HAR-RV model snapshots: `6ab3e28767f66897c604acf933867be68f8ed93fdafa5753d86c24bce4a1006e`;
- HAR-RV report: `9990e0dba0d86ca9132eeff9f10c16c5410e6d28a637e628ae28b60f78560e6c`;
- HAR-RV evidence manifest: `8d652a2c5fc514abca8dd911a11d2db5d0d99de87f297353b88cd7a7e736dbc6`;
- multidimensional risk contract: `6b5514f8d53420c99084430e9c85dee964313cfbf22c48fae1d0526346e63212`;
- multidimensional risk implementation: `363ec3bbb098cf11f1a934b4c22cd3b7abb09e834701465eb16acfe7e040db10`;
- DVOL v1 contract: `9be618628ea2efe75118450b1fc156f388f90302333adba098ac7f306b66d93e`;
- DVOL v2 contract: `ba162b70780e09050fda4b48230c48f074ccd3ec6b53f566f27e05a728c1e99b`;
- DVOL source manifest: `634c1f116658fbfffb5cc772ed4ee15ecbe030cbbcfe895a627950f232cfcf9c`;
- DVOL audit report: `b62a3f3fd6042def7661aaf2a95230d1e4d1e032c465e2d4873809691f428749`;
- DVOL evidence manifest: `811d94b79c1129471141658d34960df5a6beb34326e8c440453cc3d15eba3353`;

- B3 contract: `285b5403f515650620227efc43c71864d71f7fce4abe2535f0bb0fe7e02b9029`;
- B3 core: `8fa614335ab854a4335bac4dea48fe4736f8341c89eaf8967e946c8cd4c831c1`;
- B3 qualification report: `f75ef8d73ab25a055671d0fc68417bb5cbc70c8ac79a55a1f78cd19d023e5a22`;
- B3 evidence manifest: `3fdb95da4f8d57361109892cc166cbdbb5b8365ef1fb1b0ef2eaae419d0584cc`;
- B3 human result: `916d22e1467a6cb06451d1019dced15d82498a8878e55377b16f0d67e1aacaa9`;
- gap-recovery contract: `2b6bc794f72b6c123f8976c041bbfe7afbec7bdf919e721a767a66e7fd4c8cf9`;
- gap-recovery source manifest: `7640f3d7e3bb62bf64267498951a79672bde59f102e4f6f0254a2807f6990cb7`;
- gap-recovery audit report: `8945f156e398289370580051e2241ffd918e04682411a6d619495ed8029aa31c`;
- gap-recovery evidence manifest: `451e1a3a0058dc30cb4a00dc8744a32b1078ecd338ec800d9a1c67a45641c289`;
- carry v1 report: `4c3b8fafd945b24a54dfcbf0e23e87ac50872a196159d4e499bdc528f393818a`;
- carry v1 trades: `05bf894049cf8ca11920026d1ca993bd654011d42f1c87326ef0f8ddd8ce6921`;
- carry v1 evidence manifest: `23bd88f671595dd86b20ecc4926dc5be360ddcb07096e766cf80d259a7a68457`;
- scorecard contract: `2d7a3954f0ee2998a08295bf48cb2df29d25e2f0d13ecbe8c8b1088f8240cebf`;
- scorecard manifest: `f18e87d9bff40cb938e9c3aaa04942b3d50233fdd9436d467fcfc0af326c07e4`;
- scorecard report: `def1c9d743507d0f240a898ab143c17fef05e67c6062557ee8b995865d24f510`;
- strategy trial registry: `159208e8ae2f135b0f709bcba5783d32954bacf2325f30e18dab4433630d0582`;
- append-only decision log: `7fc8d1b660010ed76047a33d288f938398e0f7010556561b1ae1500122f4c755`;
- latest decision digest: `18be7d620c437c596f43d0b543821f704cccac353b2c81c31c7f499edd09f6bc`.

## Reproduce

```bash
.venv/bin/pytest -q tests/test_btc_backtest_core.py tests/test_execution_model.py \
  tests/test_research_ledger.py tests/test_research_breakout.py tests/test_btc_4h_trend.py
.venv/bin/python scripts/qualify_btc_backtest_core.py \
  --output artifacts/agent-level-experiment/btc-focused/replays/backtest-core-qualification-<new-empty-id>
.venv/bin/python -m unittest research.btc.tests.test_carry_gap_recovery -v
.venv/bin/pytest -q tests/test_btc_carry.py
.venv/bin/pytest -q tests/test_research_metrics.py tests/test_btc_backtest_scorecards.py
.venv/bin/pytest -q tests/test_research_market_conditions.py
.venv/bin/python scripts/audit_btc_market_condition_inputs.py \
  --output artifacts/agent-level-experiment/btc-focused/replays/market-condition-scores-mcs1-<new-empty-id>
.venv/bin/pytest -q tests/test_research_condition_scores.py
.venv/bin/pytest -q tests/test_research_score_ensembles.py
.venv/bin/python scripts/qualify_btc_score_combination_foundation.py \
  --output artifacts/agent-level-experiment/btc-focused/replays/score-combination-foundation-v1-<new-empty-id>
.venv/bin/python scripts/qualify_btc_market_condition_primitives.py \
  --output artifacts/agent-level-experiment/btc-focused/replays/market-condition-scores-mcs2-<new-empty-id>
.venv/bin/pytest -q tests/test_research_persistence.py
.venv/bin/python scripts/run_btc_persistence_information.py \
  --output artifacts/agent-level-experiment/btc-focused/replays/market-condition-scores-mcs3-p-v1-<new-empty-id>
.venv/bin/pytest -q tests/test_research_reversion.py
.venv/bin/python scripts/run_btc_reversion_information.py \
  --output artifacts/agent-level-experiment/btc-focused/replays/market-condition-scores-mcs3-r-v1-<new-empty-id>
.venv/bin/pytest -q tests/test_research_downside.py
.venv/bin/python scripts/run_btc_downside_tail_information.py \
  --output artifacts/agent-level-experiment/btc-focused/replays/market-condition-scores-mcs3-d-v1-<new-empty-id>
.venv/bin/pytest -q tests/test_research_jump.py
.venv/bin/python scripts/run_btc_jump_information.py \
  --output artifacts/agent-level-experiment/btc-focused/replays/market-condition-scores-mcs3-j-v1-<new-empty-id>
.venv/bin/pytest -q tests/test_research_carry_readiness.py
.venv/bin/python scripts/audit_btc_mcs3_c_readiness.py \
  --output artifacts/agent-level-experiment/btc-focused/replays/market-condition-scores-mcs3-c-readiness-v1-<new-empty-id>
.venv/bin/pytest -q tests/test_research_risk.py tests/test_btc_deribit_dvol_source.py \
  tests/test_research_routing.py tests/test_research_volatility.py tests/test_research_hmm.py \
  tests/test_research_har.py \
  research/btc/tests/test_focused_context.py
.venv/bin/python scripts/run_btc_har_rv_risk_forecast.py \
  --output artifacts/agent-level-experiment/btc-focused/replays/har-rv-risk-forecast-v1-<new-empty-id>
.venv/bin/python scripts/build_btc_backtest_scorecards.py \
  --output artifacts/agent-level-experiment/btc-focused/replays/backtest-scorecard-v1-<new-empty-id>
.venv/bin/python -m unittest -v \
  research/btc/tests/test_spot_perp_continuation_data.py \
  research/btc/tests/test_spot_perp_continuation_data_v2.py \
  research/btc/tests/test_spot_perp_continuation_data_v3.py \
  research/btc/tests/test_spot_perp_continuation_information.py \
  research/btc/tests/test_spot_perp_continuation_information_v3.py
REPLAY=artifacts/agent-level-experiment/btc-focused/spot-perp-continuation-d1-v3-replay-<new-empty-id>
PYTHONPATH=src:. .venv/bin/python scripts/run_btc_spot_perp_continuation_information_v3.py \
  --phase endpoints --output "$REPLAY"
PYTHONPATH=src:. .venv/bin/python scripts/run_btc_spot_perp_continuation_information_v3.py \
  --phase labels --output "$REPLAY"
PYTHONPATH=src:. .venv/bin/python scripts/run_btc_spot_perp_continuation_information_v3.py \
  --phase model --output "$REPLAY"
PYTHONPATH=src:. .venv/bin/pytest -q tests/test_btc_carry.py tests/test_btc_carry_risk_v2.py
CARRY_REPLAY=artifacts/agent-level-experiment/btc-focused/safe-delta-neutral-funding-carry-v2-replay-<new-empty-id>
PYTHONPATH=src:. .venv/bin/python scripts/backtest_btc_safe_funding_carry_risk_v2.py \
  --output "$CARRY_REPLAY"
.venv/bin/python scripts/validate_btc_focused_context.py
PYTHONPATH=src:. .venv/bin/python -m unittest -v research.btc.tests.test_unified_engine_e0
PYTHONPATH=src:. .venv/bin/python scripts/validate_btc_unified_engine_e0.py \
  --output artifacts/agent-level-experiment/btc-focused/replays/unified-backtest-engine-e0-<new-empty-id>
```

The revoked E1-v3 module and tests are intentionally excluded from permitted reproduction
commands. Their archived reports are historical negative evidence only.

# BTC CUSUM trend-onset result — TNE1-A v2 rejected

`btc-cusum-trend-onset-tne1-v2` completed its one trigger-only run and failed the frozen sample
gates: 229 versus 300 model-ready triggers, 75 versus 150 before 2021, 29 versus 30 in 2021 and
27 versus 30 in 2022. Labels and TNE2 models were not opened. The invalid v1 binding-role
contract is preserved; it opened no historical row. Exact completed command:

`.venv/bin/python scripts/run_btc_cusum_trend_catalogue.py --contract research/btc/contracts/btc-cusum-trend-onset-v2.json --experiment-id btc-cusum-trend-onset-tne1-v2 --phase trigger`

The trigger report sets `label_phase_allowed=false`. Do not run label or model phases and do not
tune the Page threshold, scale, suppression or gates under this ID. The next permitted research
action is a materially new, non-event-sampled BTC hypothesis under a new ID. No strategy PnL,
2026, partial OB0 or protected service was accessed; zero arms are accepted and routing remains
`no_trade`. Result: `research/btc/reports/BTC_CUSUM_TREND_ONSET_TNE1_V2_RESULT.md`.

## Next permitted action

Freeze the execution correction specification and qualify it synthetically before historical execution replay.
Follow `research/btc/reports/BTC_REFERENCE_BACKTESTER_NEXT_PLAN.md`. The custom C0 architecture
is closed under E0-v12's stop rule; do not create E0-v13 or restore the rejected active files.

Do not implement C0, C1-C6, E1-v15, E2, historical reconciliation or strategy evaluation until
under the rejected custom architecture. Do not access market rows or returns, 2026, partial OB0, protected services,
credentials or exchange/production systems. EWMA remains mandatory, zero arms are accepted and
every actionable route remains `no_trade`.
