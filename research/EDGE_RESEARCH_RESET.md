# Edge research reset

Audit ID: `edge-research-reset-20260912-v1`  
Date: 2026-09-12  
Disposition: **C. CURRENT EVIDENCE DOES NOT SUPPORT AN EDGE — stop strategy engineering and identify what information would be required to continue.**  
Review state: **STOP_FOR_CHATGPT_REVIEW**. This is a research audit, not a new strategy or stage authorization.

## 1. Executive diagnosis

The repository does not currently establish a decision that adds independently confirmed,
practically capturable value beyond appropriate alternatives after realistic costs. That is
an evidence conclusion, not proof that all its inputs contain no information or that every
historical strategy lost money. No personal account or live trading PnL was examined.

The proposed diagnosis is **partly correct and materially incomplete**. Early work and some
later architecture expanded from price patterns into strategies, filters and frameworks ahead
of accepted economic evidence. However, many later experiments already used the requested
sequence: freeze a prediction, test information or count/data eligibility, preserve rejection,
and stop before a strategy. The correct reset is to enforce and simplify that discipline,
repair misleading evidence summaries, and stop treating every failed gate as absence of signal.

The most likely limitations, ranked by the strength and breadth of the inspected evidence:

| Rank | Limitation | Evidence and qualification |
| --- | --- | --- |
| 1 | Incremental return value failed or remains unestablished across tested formulations | Spot/perpetual D1-v3 worsens prediction MSE by 0.5321% after label coverage was repaired; MCS3-P persistence worsens MSE by 1.19%; the trend blend loses 6.41% in consumed 2024–2025. Fixed breakout and top-two selection have favorable point estimates but insufficient comparative evidence. Related formulations are not independent failures of every possible mechanism. |
| 2 | Data and measurement often cannot support the intended claim | CUSUM and compression have inadequate event counts; HAR fails coverage despite good forecasts; historical net-carry economics are missing; current cash-ETF evaluator differs from contracts and mislabels uncertainty. These are different failures, not interchangeable economic rejections. |
| 3 | Independent confirmation and reliable search accounting are lacking | BTC development has been repeatedly consumed; the inspected trial registry has only 10 entries and every `family_history_complete` flag is false; several later families are absent. Small/dependent samples and incomplete trial history undermine selection-adjusted inference. No defensible probability that the whole program is overfit can be calculated from these records. |
| 4 | Some genuine predictability is too small or inefficient to capture | Conditional exhaustion predicts a 5.00-bps reversal but fails a 12-bps economic hurdle. Carry predicts higher future funding, but its gate fails the frozen net-efficiency comparison with same-notional-cap always-on carry. This contradicts a blanket claim of no predictive information. |
| 5 | Execution/reporting defects invalidate particular interpretations | Breakout event order and gap handling remain unqualified historically; cash-ETF and early ridge diagnostics have additional source-level concerns. The historical impact of corrected breakout execution is UNKNOWN. These defects do not explain all information-test failures. |
| 6 | Engineering effort and documentation maintenance are disproportionate | Repeated C0 qualification attempts ended in closure; stale summaries omit later experiments. This delays learning and makes lineage harder to assess, but it is not itself a measured cause of negative trading expectancy. |
| 7 | Risk allocation explains some small account returns and one original safety failure | Breakout uses 10% entry allocation; carry v1 failed margin stress and v2 repaired it at lower size. Neither leverage nor a risk overlay establishes directional alpha. Current evidence does not support outcome D. |

This is an evidential ranking, not an estimated decomposition of lost money. The repository
has not supplied the experiments needed to assign numerical causal shares to these causes.

Three findings require correcting the earlier conversational diagnosis:

- **Useful forecasts exist.** HAR beats two volatility controls on common rows, and MCS3-D
  improves negative-semivariance forecasts. Neither is a validated directional trading edge.
- **An economic mechanism has some empirical support.** Carry's recorded funding cashflow
  dominates its net result, and completed funding predicts subsequent funding. Its proposed
  timing decision still fails its economic comparison. The reported no-funding rerun is not
  independently verified here as a fixed-fills causal intervention.
- **Good rejection is common.** CUSUM stops before labels; crowding and continuation stop
  after information tests; conditional exhaustion stops at the economic hurdle. The record
  is not uniformly an indicator-optimization exercise.

The strongest apparently favorable findings deserve preservation, not promotion: HAR forecast
quality; the carry cashflow mechanism; EWMA entry sizing; and the top-two ranking point estimate.
The conditions that prevent their acceptance are stated below.

## 2. Research-history map

The accompanying specialist maps provide X/T/Y/H, sample/effect details and exact source lines:

- [BTC hypothesis history](btc/review_runs/edge-research-reset-20260912-v1/btc_history.md).
- [Earlier and broader history](btc/review_runs/edge-research-reset-20260912-v1/broader_history.md).
- [Execution, costs and sizing audit](btc/review_runs/edge-research-reset-20260912-v1/execution_audit.md).

In the consolidated table, `NR` means not reported in the inspected
summary, not zero; `N/A` means the experiment did not evaluate that quantity. Calendar labels
such as validation below describe historical partitions, not current independent eligibility.

| Family / prediction at its recorded clock | Sample and raw information | Net / comparative evidence | What was learned |
| --- | --- | --- | --- |
| Early candle MA / ridge diagnostics; lagged BTC/ETH price/range/volume predicts a subsequent return | Twelve recorded MA variant cells. Ridge named1h/4h: 14,518/14,515 forecasts, 18/10 traded observations; correlations -.01454/-.00593. | Ridge reported -2.629/-2.102% at24bps; source clock, purge, horizon and return-accounting concerns prevent clean inference. Exact date/input bindings incomplete. | Exploratory/implementation-limited. Horizon4 is one return four rows ahead. Do not claim all ML was properly tested and rejected. See broader appendix for all MA cells. |
| Multi-asset top-two continuation/ranking at frozen entry timestamps, 48-hour holdings | 48 fills; selected-minus-universe +181.98 bps/event; interval [-4.72, 412.98]; nominal random-selection p=.0108. | +44.04% development return; beta 1.82, R² .796; intercept interval crosses zero; gate-date p=.4051; top-three-month contribution 64.5%. | Favorable ranking estimate, insufficient alpha: small sample, concentration and post-hoc universe. Aggregate return is not proof of selection skill. [R0](../docs/MULTI_ASSET_TOP2_ALPHA_ATTRIBUTION_R0_RESULT.md) |
| Raw taker imbalance at completed five-minute close predicts 5m–4h movement | Positive-flow 2025 cohort 8,940 events; next-hour mean -1.87 bps, day-block interval [-2.95,-.80]. | No strategy PnL; magnitude below the then-used 24-bps round trip. | Weak asymmetric predictive information, economically small; executed volume does not identify liquidity-provider intent. [Event study](../docs/BTC_TAKER_FLOW_EVENT_STUDY.md) |
| Conditional taker exhaustion at completed five-minute close predicts next-hour reversal | 152/453/665 events in 2023/24/25; pooled reversal 5.00 bps, interval [1.52,8.48]. | No net strategy run; fails frozen 12-bps gross hurdle despite sign/sample/statistical passes. | Information exists but is too small for the declared use. No new veto/short strategy is inferred. [Hypothesis/result](../docs/BTC_CONDITIONAL_REVERSAL_HYPOTHESIS.md) |
| Sell-flow absorption: completed-hour residual/flow/volume event predicts rebound over up to 12h | 115 primary fills; gross +6.78 bps/trade. | Net -23.22 bps/trade at 30 bps; account -5.28/-7.43/-15.56% at 30/40/80; random p=.5731; 0/12 positive perturbations. | Both cost magnitude and incremental information fail. [Result](../docs/BTC_SELL_FLOW_ABSORPTION_RESULT.md) |
| BTC/ETH relative catch-up following observable relative displacement | 254 fills; paired effect interval [-63.82,-8.15] bps. | -22.71% net; 49.88 bps worse than BTC-only reversal; all six sensitivities negative. | Comparative economic rejection; adding a related asset did not earn its complexity. Detailed clock/cost lineage in broader appendix. |
| 4h SMA10/30 trend, completed bars, variable hold | Earlier full-size development: 353 trades; gross effect NR; only 5/9 slices positive. | Later 25% allocation: +114.9/+97.5/+38.7% at 30/40/80 bps; DD29.1/30.7/36.6%. | Profitable market participation with failed stability and substantial risk. Different allocations/versions are not comparable alpha gains. [Robustness](../docs/BTC_4H_TREND_ROBUSTNESS.md), [cost model](../docs/EXECUTION_COST_MODEL.md) |
| Compression-to-positive-expansion continuation, completed 1h after 4h context, next 5m entry, 24h target | 55 events in 2023–25; raw next-day mean -31.67 bps versus +45-bps hurdle. | Account -6.31/-7.53/-9.54% at 30/40/80; 0/10 positive perturbations. | Wrong-direction/unstable raw effect plus costs. Separate execution assumptions remain, but do not erase the raw prediction failure. [Result](../docs/BTC_VOLATILITY_EXPANSION_DEVELOPMENT_RESULT.md) |
| Fixed 20d/10d breakout: completed 4h close above prior 120-bar high, next 5m open, max14d | 67 trades in 2019–25; 63 valid seven-day diagnostic returns. | Legacy +16.94/+16.14/+13.01% at 30/40/80. Seven-day entry diagnostic at 54.31st random percentile; paired participation lower bound negative. | Positive legacy development control; corrected execution and full-system attribution unresolved. S5 is not a full stop/exit/cadence matched test. [S1](../docs/BTC_REGIME_ROUTING_S1_RESULT.md), [S5](../docs/BTC_REGIME_ROUTING_S5_BREAKOUT_MECHANISM_RESULT.md) |
| BOCPD drift gate on fixed breakout; completed causal daily state | Exact information/count details in execution appendix; gross effect NR. | Gate reduces return, Calmar and mean expectancy; standalone next-seven-day information test fails. | Detector/continuation gate rejected, not an accepted router. [Result](../docs/BTC_ONLINE_REGIME_BREAKOUT_DEVELOPMENT_RESULT.md) |
| Student-t HMM risk state, causal filtering, next-seven-day variance/downside | 2,402 labels; variance separation interval [.0016699,.0103558]; downside interval [-.0054277,.0148960]. | No overlay PnL after joint information failure. | Variance information passes, downside separation fails; do not classify as universally no information. [S3](../docs/BTC_REGIME_ROUTING_S3_RESULT.md) |
| EWMA risk forecast and breakout entry sizing | Same 67 breakout opportunities; common-row risk forecast improves. | +18.75% versus fixed +16.94% and matched-size +14.24%; incremental-return intervals cross zero. | Useful risk benchmark; legacy execution, ex-post matching and consumed history limit inference. [S2-v2](../docs/BTC_REGIME_ROUTING_S2_V2_RESULT.md) |
| HAR-RV: completed daily 1/5/22-day components predict next1d/7d RV | 2,011/1,921 common rows; one-day MSE 27.38% below same-input EWMA; QLIKE interval [.06253,.12323]. | No strategy return; all forecast-quality gates pass; annual coverage down to 41.37%. | Data/coverage rejection despite useful risk prediction. [Result](btc/reports/BTC_HAR_RV_RISK_FORECAST_RESULT.md) |
| Absolute derivatives crowding predicts seven-day variance/downside beyond price controls | 1,263 feature observations; 892 forecasts/30 months; MSE0.1325% worse; interval crosses zero. | No PnL; high/low separation also unsupported. | Information failure, distribution drift; not a test of every signed or carry mechanism. [Result](btc/reports/BTC_DERIVATIVES_CROWDING_INFORMATION_RESULT.md) |
| Spot/perpetual basis impulse and relative turnover, daily00:05, 72h exact-open target | 1,823 evaluated labels, 100% annual coverage after D1-v3 repair; MSE0.5321% worse than price-only. | No PnL; coefficient signs contradict theory; only2/5 years improve. | Measurement issue repaired, economic-information hypothesis then rejected. [Result](btc/reports/BTC_SPOT_PERP_CONTINUATION_D1_V3_RESULT.md) |
| MCS3-P: completed42 four-hour-return efficiency predicts seven-day return beyond cumulative return | 13,573 forecasts; MSE1.19% worse; non-monotone buckets; coverage88.94%<90%. | No PnL. | Actual comparative forecast failure plus coverage failure. [Result](btc/reports/BTC_MARKET_CONDITION_SCORES_MCS3_P_RESULT.md) |
| MCS3-R: completed24h absolute z≥2 displacement predicts one-day symmetric reversal | 300 non-overlapping events; pooled12.46bps versus80 hurdle; equal-month -1.74bps, interval[-57.37,53.97]. | No PnL; matched difference -8.45bps; strict-match coverage68.67%. | Symmetric/incremental/economic claim fails. Favorable downside subset is post-result exploratory. [Result](btc/reports/BTC_MARKET_CONDITION_SCORES_MCS3_R_RESULT.md) |
| MCS3-D: completed negative semivariance predicts next1d risk and scaled VaR/ES | 2,111 common rows; semivariance MSE17.54% lower and positive QLIKE interval. | No PnL; FZ0/pinball worsen;2/7 annual joint passes. | Risk information exists; translating it to this tail model fails. [Result](btc/reports/BTC_MARKET_CONDITION_SCORES_MCS3_D_RESULT.md) |
| MCS3-J: completed four-hour jump proxy EWMA predicts next4h event/intensity | 12,118 rows/99 events; AP/Brier/log-loss/intensity error all worse; every annual comparison negative. | No PnL. | Broad comparative rejection, not merely missing100-event floor by one. [Result](btc/reports/BTC_MARKET_CONDITION_SCORES_MCS3_J_RESULT.md) |
| Compression BEX1-v5: completed range/confirmation predicts continuation before re-entry within7d | 92 setups;36 confirmations,12 continuation/24 re-entry versus200/60/60 required; no2021 event. | Model/strategy/PnL not run. | Insufficient sample. Cause counts consume outcome information; they are not fully price-blind. [Result](btc/reports/BTC_UPSIDE_BREAKOUT_BEX1_V5_RESULT.md) |
| CUSUM TNE1-v2: completed-hour distributed drift predicts normalized72h return | 229 triggers<300; pre2021 75<150. Labels never run. | No gross outcome, PnL or model fit. | Count/design rejection, not a falsified return effect; synthetic-selected parameters are not evidence of historical optimization. [Result](btc/reports/BTC_CUSUM_TREND_ONSET_TNE1_V2_RESULT.md) |
| Funding carry v1/v2: completed84 funding events, Monday00:05, max84d hold and separate28d funding target | 101 weekly targets,6 trades; raw funding differential60.88bps, interval[23.84,105.06]. | V1 +5.83/+2.61% at30/80bps per leg but margin/efficiency fail; v2 +2.95/+1.33%, risk passes, same-size always-on +7.75%. | Positive cashflow and raw prediction, rejected timing; v2 is reused risk comparison, not independent market evidence. [V1](btc/reports/BTC_POSITIVE_FUNDING_CARRY_RESULT.md), [V2](btc/reports/BTC_SAFE_FUNDING_CARRY_RISK_V2_RESULT.md) |
| Perpetual7/28/84-day trend blend, daily00:05, next01:00 fill | 116 development and53 later episodes; gross effect NR. | +48.30% in2020–23, -6.41% in2024–25; severe later -12.77%; same-size always-long later +7.06%. | Stability/control failure; risk cap did not bind, so risk overlay does not explain the result. [Result](btc/reports/BTC_MULTIHORIZON_PERP_TREND_V5_RESULT.md) |
| Cross-asset A2 session breakout: first2h range then closing breach, nextH1 bid/ask entry | Primary1,490 development/1,099 validation trades;2010–21/2022–23. Spread-only validation +2.04bps/trade (not frictionless gross). | Spread-only +2.54% account; spread+5bps -5.35%, -2.96bps/trade; severe -11.61%; only2/7 instruments positive. | Costs consume a small conditional effect; matched always-long also better. A2024 boundary row was decoded despite the nominal holdout. [A2](../docs/CROSS_ASSET_A2_SESSION_BREAKOUT_RESULT.md) |
| Cross-asset A3 gap reversion: gap≥.75 prior20-session median range, first-hour reversal, nextH1 entry,2h hold | Primary1,015 development/848 validation trades;2010–21/2022–25. Spread-only validation +2.53bps/trade. | Spread-only +2.64%; spread+5bps -3.64%, -2.47bps/trade; severe -12.02%; all4 sensitivities and leave-one-instrument-out portfolios negative. | Economic magnitude/stability failure;2024–25 consumed. Relatively better than other losing directions is not accepted alpha. [A3](../docs/CROSS_ASSET_A3_GAP_REVERSION_RESULT.md) |
| Cash-ETF slow trend: monthly252-session GBP-return sign, six slots |2009–18,2,516 sessions; v8 reports42 completed-trade records; gross NR. | Provisional +28.10% at25bps/+7.66% at50bps; DD10.61%; only50% positive years. | Missing required controls and source/equity accounting inconsistencies. Not qualified predictive or execution evidence. [C2 report](../docs/CASH_ETF_C2_PROXY_EVALUATION_RESULT.md); later v8 aggregate in broader appendix. |
| Cash-ETF turn-of-month: intended final-session open to next month's fourth-session open | Same development;119 reported windows. | Provisional -11.45% at25bps/-34.28% at50bps; implemented entry differs from contract. | Preserve negative diagnostic, but it does not validly reject the exact frozen calendar hypothesis. |
| Cash-ETF quarterly defensive rotation: positive top2 of six126-session return scores | Same development;69 reported trade-list items include fee-only entries. | Provisional +62.49% at25bps/+48.28% at50bps; DD25.75% exceeds20% gate. | Third outcome-exposed arm omitted from stale summaries; controls, metrics and accounting unqualified. No accepted alpha. |
| L2 OFI / on-chain / DVOL source work | Native book integrity, historical label revisions or availability unresolved; limited technical pilots. | No accepted net predictive strategy evidence. | Data engineering only. Do not infer accepted alpha from successful capture, a vendor claim or a technical pilot. [L2](../docs/BTC_ORDER_BOOK_RESEARCH.md), [on-chain](btc/reports/BTC_ONCHAIN_SOURCE_FEASIBILITY_REVIEW.md) |
| Score ensembles, routing, C0/reference ledger infrastructure | Synthetic contracts, accounting and lineage checks. | No new alpha; broad C0 attempts closed. | Useful tools or rejected engineering designs, not independent strategy trials or confirmation. [Program review](btc/BTC_PROGRAM_REVIEW_2026_09_10.md) |

For information-only rows, gross/net strategy return is N/A. For strategy rows where a report
omits gross returns, they remain NR rather than reconstructed from net returns and assumed fees.
Full stability/sensitivity and source limitations are retained in the linked maps. Favorable
point estimates are preserved with their failed gates; negative diagnostic paths with broken
measurement are not upgraded into trustworthy scientific rejections.

## 3. Prediction vs execution vs sizing

### Prediction

Several direct information comparisons fail without fees, positions or stops: D1-v3,
derivatives crowding, MCS3-P and MCS3-J. Repairing a fill engine cannot explain away those
comparative forecast losses. Conversely, volatility information is demonstrably stronger:
HAR has 2,011 common one-day forecasts, a positive month-bootstrap QLIKE improvement interval
`[0.06253, 0.12323]` versus same-input RV EWMA, and wins all seven evaluation years. Coverage
still fails. MCS3-D lowers semivariance MSE 17.54%, while its VaR/ES mapping worsens proper losses.

Carry's consumed 2024–2025 funding study has 101 eligible weekly observations: 43 threshold-qualified
and 58 nonqualifying weeks. These flags are not actual new position entries; qualifying weeks
can occur while already invested. Qualified-minus-nonqualifying subsequent 28-day funding is 60.8811 bps, with recorded month-block
interval `[23.8434, 105.0562]`. Those overlapping horizons are not 101 independent trades.
This supports conditional cashflow persistence in development; it does not establish that
participants were identified, that a particular causal story was proven, or that net timing
beats a simpler alternative. See the [carry result](btc/reports/BTC_POSITIVE_FUNDING_CARRY_RESULT.md).

### Execution and costs

Fixed breakout survives the legacy severe 80-bps scenario: +13.01% versus +16.94% primary.
Therefore commissions alone are not the demonstrated explanation for its lack of acceptance.
The conditional reversal's 5-bps gross effect is a much clearer economic-magnitude failure.
Carry v2's gate earns +2.95% versus +7.75% for same-exposure always-on carry; its return per
exposed day is also lower, so this is not just a difference in total time invested.
Equal 25% leg notional is not equal tail or margin risk: the minimum shocked margin ratio is
9.5117 for gated carry and 2.0719 for always-on. The frozen efficiency gate fails, but this
does not establish that always-on dominates risk-adjusted utility or is a suitable investment.

The general execution module and the legacy breakout are different implementations. Tests of
the general Decimal model do not establish that legacy S1 enforces its rounding, minimum
notional, daily-loss or drawdown policy. S1 preserves its own frozen semantics. Its
`exposure_fraction = 0.1871646` is **time in position across observed rows**, not average
portfolio notional exposure. Do not compare it directly with a 25% allocation.

R2-v2 reconciles 201 recorded trades across three costs, with 1,005 comparisons and errors
below `7.3e-13` USDT. Floating-point accounting is not a material explanation for these returns.
That replay is conditional on the recorded fills; it does not validate the fills themselves.
The A0 example where a later low overrides an earlier scheduled open exit is locally
pessimistic. Retrospective segment exits and other chronology issues have unmeasured net bias.
No blanket claim that corrections improve or erase profitability is justified.

Stage 3A passed source/input/topology checks and the recorded 35/35 integration plus 7/7
inherited synthetic reruns. The first unchanged legacy build passed numeric assertions but
failed canonical `breakout-forecasts.jsonl.gz` identity. Expected SHA-256 begins `c6dda69d…`;
actual begins `a5d634b1…`. The exact identities are in the preserved
[Stage 3A packet](btc/review_runs/stage3a-20260912-v1/STAGE3A_REVIEW_PACKET.md).
Cause remains UNKNOWN; do not infer compression-only differences or accept numeric parity as
byte parity. The required second build was not run after that mismatch; corrected historical
performance remains NOT_RUN.

### Sizing and risk

EWMA changes entry sizes, without continuous intratrade rebalancing. Its legacy +18.75%
return/3.28% intraday drawdown compares with fixed breakout +16.94%/5.02% and a matched constant
8.47% allocation control returning +14.24%. This is better evidence than merely observing
lower drawdown at lower exposure. However, incremental-return confidence intervals cross zero,
the underlying execution is legacy, and the evidence is consumed. Preserve a risk benchmark,
not a claim of independently accepted alpha.

Carry v1 at 49% notional per leg suffered 260 shocked-buffer breaches despite no observed
breach for the gated arm. V2 at 25% repaired that planning-model failure and approximately
scaled return down. The gate still failed economic efficiency. Neither the conservative
shock scenario nor smooth backtest marks quantify venue failure, ADL, stablecoin, liquidity
or true historical margin risk. A delta-neutral pair can retain substantial non-directional risk.

### Newly identified source concerns

These are static audit findings. The affected code was not executed or fixed here.

1. [Old ridge diagnostic](../scripts/walkforward_btc_causal_model.py): `y = ret.shift(-horizon)`
   is followed by training through `y[i-1]` without a label-availability purge. For horizon 4,
   that includes a return at row `i+3` under the natural row-i forecast convention. The
   precise forecast clock is itself undefined; horizon-1 leakage depends on that clock.
   Horizon 4 means a one-bar return four rows ahead, not cumulative four-bar return. Joining,
   dropping rows and shifting do not enforce elapsed-time or segment continuity; log returns
   are compounded with `(1+t)` as if simple returns. Do not generalize these findings to the
   later explicitly embargoed models, or use the old output as a clean test of ML's potential.
2. [Cash-ETF evaluator](../scripts/evaluate_cash_etf_c2_proxy.py): lines 18–25 compute order
   statistics of individual trade values and name them `month_block_*`; they are neither a
   block bootstrap nor a confidence interval for mean excess return. The current turn-of-month
   code enters the next month's first open, while its frozen contract specifies the prior
   month's final-session open. Slow trend applies new holdings to full close-to-close daily
   returns despite a next-open claim; costs/trade records differ from the daily equity path.
   Quarterly rotation also has mismatched trade/equity accounting. Positive and negative
   outputs from these paths are provisional and cannot qualify the frozen hypotheses.
3. Cash-ETF history summaries are stale; a later third arm and numeric processing of nominally
   locked years exist. A file named `frozen` or a report asserting `sealed_partitions_accessed:
   false` cannot by itself establish the full pre-result timeline.
4. Legacy [carry code](../src/trading_platform/btc_carry.py) checks observed liquidation using
   the hour's closing mark and then closes at that same hour's opening prices (lines 225–230,
   338–345). The v1 report records one observed liquidation for always-on and none for the gated
   arm. V2 reports no observed breaches, so this branch is not a demonstrated explanation of
   v2's efficiency failure. Historical effects and exact source-to-output lineage were not
   replayed; do not infer a corrected comparator from this static finding.

Static defects establish what the inspected code does. Without exact producer binding they do
not prove every earlier similarly named report used those bytes. Archived report outcomes remain
preserved, with qualification stated here rather than silently rewritten.

## 4. Data-contamination and false-discovery assessment

Every known exposure is relevant to independence. Metadata-only access, numerical data
engineering, diagnostic outcomes and strategy outcomes are distinguished in the ledger, but
none is silently treated as a pristine untouched sample. Under the user's conservative rule,
uncertain prior access means **independent eligibility UNKNOWN**, not approved.

| Data/window | Known use | Current interpretation |
| --- | --- | --- |
| BTC spot 2017–2022; especially 2019 onward | Discovery thresholds, many information/strategy/risk studies | Exploration/development only. |
| BTC spot 2023–2025 | Earlier chronological checks, later model/strategy decisions, repeated summaries | Consumed development; refits/walk-forward do not restore researcher independence. |
| BTC/perpetual/funding 2020–2023 | Crowding, carry development, continuation and trend development | Consumed development. |
| BTC/perpetual/funding 2024–2025 | Carry v1/v2, trend stability and other information tests | Consumed; v2 is a risk comparison on reused observations, not an independent replication. |
| Multi-asset 2021–2025 | Reconstructed top-two and R0; later cross-family decisions | Consumed, with a post-hoc seven-asset universe and unknown historical eligibility. |
| Existing 2026 partitions | Sealed; top-two predecessor family inspected through May2026 and its registry excludes January–August2026; other histories have their own restrictions | Do not access. A new filename, repository, instrument proxy or experiment ID cannot clear contamination. No current lockbox authorization is inferred. |
| Cross-asset OANDA 2010–2023 | A2/A3 development and chronological evaluation | Consumed economic evidence. |
| Cross-asset OANDA 2024–2025 | A2 decoded2024 boundary rows without final-period metrics; A3 later evaluated2022–2025 outcomes | Outcome-consumed for these tested families. Distinct from the cash-ETF dataset with some of the same calendar years. |
| Cash-ETF 2009–2018 | Source repairs and repeated provisional strategy evaluations, including three arms | Consumed development. |
| Cash-ETF 2019–2023 | Earlier pragmatic ledger v2 numerically processed 3,774 sessions spanning 2009–2023 | Not untouched. Later development-only rebuilding does not erase that exposure. No strategy-outcome access is established, but independent eligibility is UNKNOWN. |
| Cash-ETF 2024–2025 | Locked in inspected metadata; no strategy output found in reviewed evidence | Potentially unused numeric outcomes, not certified clean under incomplete/global exposure history; archived lane, no opening authorized. |
| L2/OB0 and provider pilots | Protected acquisition/technical validation; source failures and gaps | No accepted predictive sample established by this audit. Partial capture remains prohibited. |
| On-chain and implied-volatility data | Source-only feasibility or small technical pilots | Availability/revision/retention insufficiently established; not an approved alpha dataset. |
| A genuinely future period after a new freeze | Not yet defined/collected/authorized here | Potential independent confirmation only with prior hypotheses, source eligibility, sealed collection, event/sample stopping rule and one reviewed unlock. |

No market partition was opened to produce this assessment. It is based on contracts, access
records, schema/source code and existing summary artifacts. The detailed broader-history
appendix identifies the cash-ETF source/manifest discrepancies.

Specific false-discovery findings:

- **Confirmed exposure/selection risk:** repeated development reuse and multiple related
  hypotheses; fixed-seven survivor/universe selection; top-two gate-date and concentration
  failures; incomplete trial registry; post-result favorable downside subsets; reporting drift.
- **Confirmed implementation concerns:** explicit future-segment handling in legacy breakout;
  the old ridge horizon-4 training issue; cash-ETF outcome/uncertainty interpretation defects.
- **Not established:** widespread brute-force optimization, secret discarded winners/losers,
  systematic cost understatement across every runner, or a numerical false-discovery rate.
  Some sensitivities were predeclared. Version changes often repaired data/contract/software
  errors; they cannot all be counted as economically independent parameter searches.
- **Safeguards that worked:** preserved negatives, no-trade disposition, rejection before PnL,
  explicit same-input controls, monthly training embargoes, and refusing to lower frozen gates.
- **Methodological caution:** minimum counts and mechanical pass gates are necessary design
  constraints, not universal power calculations. Evaluate dependence, effective sample size
  and an economically meaningful effect before the next freeze. Do not change old gates.

The safe carry v2 narrative calls its result a “second independent failure.” That wording
overstates independence: it reused the same 2024–2025 history and timing rule with different
risk implementation. Computational replay, independent code review and independent market
confirmation are three different claims.

## 5. Candidate mechanisms — maximum three

These are mechanism audits, not three new experiments. Scores use 0 = missing/not established,
1 = plausible but weak, 2 = partial development support, 3 = direct relevant support. They
are qualitative judgments, not probabilities; no weighted total selects a winner. Risk
forecast quality does not earn an alpha score merely by being statistically strong.

| Candidate | Economic plausibility | Observable before outcome | Falsifiable | Suitable data | Magnitude vs costs | Independence | Practical capture |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Funding persistence / supplying matched spot-perpetual capital | 3 | 2 | 3 | 1 | 1 | 0 | 1 |
| Volatility persistence measured by complete intraday RV | 2 | 3 | 3 | 2 | 0 (no net trading test) | 0 | 1 |
| Temporary liquidity demand / absorption distinguishable from information | 2 | 0 (mechanism distinction missing) | 1 | 0 | 0 | 0 (no qualified confirmation) | 0 |

### Candidate 1: funding persistence and compensation for arbitrage capital

- **Mechanism/participant:** perpetual holders pay for leveraged exposure; matched spot-long/
  perpetual-short capital can receive funding. Competition may be constrained by collateral,
  margin fragmentation, venue exposure and balance-sheet costs. Actual participant identities
  and constraints are not observed by the repository.
- **Observable information:** completed eight-hour funding, spot/perpetual prices and recorded
  archive-event timestamp jitter. Actual public receipt is not established by that jitter.
  Historical fee/margin/funding-rule applicability and complete per-row
  availability remain inadequate for an exact historical net-carry label.
- **Prediction/horizon:** the existing frozen 84-event funding statistic predicts greater
  subsequent 28-day funding. A separate economic claim says this timing earns more per exposed
  day than always-on matched carry. The first has favorable development evidence; the second
  is rejected. Perpetual future funding is not locked like delivery-futures convergence.
- **Possible advantage:** willingness to allocate collateral patiently and operate a small
  matched pair. **UNRESOLVED:** evidence of a comparative execution/information advantage,
  account eligibility, actual fees, capital, financing and acceptable risk.
- **Competing explanation:** compensation for funding, margin, basis, liquidity and venue risk;
  persistent market-wide leveraged demand that simple continuous participation also captures.
- **Cheapest falsification:** reuse the recorded cashflow attribution and same-size always-on
  comparison. They reject the timing bridge. The reported no-funding control is a fresh
  simulation with funding disabled, not a proven fixed-fills intervention. Do not rerun these
  studies or weaken the question into gross carry.
- **Rejection:** the frozen gate's nonpositive incremental net efficiency is sufficient; it
  already failed. Broader always-on economics are unproven, not rejected by this timing test.
- **Data/contamination:** 2020–2025 is consumed; the MCS3-C readiness audit already reports four
  missing economics/rules gates. A new source review is justified only by genuinely new evidence,
  not another copy of the same missing-source audit.

### Candidate 2: volatility persistence

- **Mechanism/participant:** persistent information arrival, trading activity and risk
  adjustment can produce clustered volatility. This is a risk-state hypothesis; the repository
  does not separately identify which participant channel causes it.
- **Observable/prediction/horizon:** complete same-segment daily squared five-minute log returns;
  1/5/22-day completed components forecast next 1-day and 7-day RV at the contract's UTC clock.
- **Possible advantage:** improved measurement relative to close-only risk. HAR also beats a
  same-input RV EWMA, so more frequent data alone does not explain the comparison. There is no
  demonstrated exclusive data advantage or accepted mapping to economic decisions.
- **Alternative explanation:** coverage selects predictable periods; variance predictability
  provides risk measurement without return predictability; costs from future resizing may offset utility.
- **Cheapest falsification/rejection:** the original common-row forecast test already exists.
  It passes quality and fails coverage. Preserve both findings. A data-only audit of the 34
  invalid days/reset propagation is the named possible successor; no HAR retuning or risk-cap
  mapping is authorized by this reset.
- **Data/contamination:** consumed 2017–2025 history; 22-/30-observation rebuilding magnifies gaps.
  This is the strongest prediction counterexample, but it is not a new alpha hypothesis.

### Candidate 3: temporary liquidity pressure rather than negative information

- **Mechanism/participant:** urgent inventory reduction or hedging may trade through available
  liquidity; a patient opposite side might be paid for immediacy. “Forced” intent cannot be
  inferred merely from an extreme candle or taker-buy ratio.
- **Observable information:** **UNRESOLVED** for the mechanism distinction. Five-minute aggregates
  show executed flow, not inventory constraints, cancellations, resting depth or order urgency.
  Reconstructable timestamped L2/trades could improve measurement, but are not proof of intent.
- **Prediction/horizon:** a transient component should reverse after the urgent flow ends.
  An exact qualifying event, cessation indicator and horizon are **UNRESOLVED**. Choosing a
  winning downside subset from the rejected symmetric reversal would be post-result selection.
- **Possible advantage:** **UNRESOLVED**; the present data and fees do not establish a retail
  execution advantage at seconds-to-hours horizons.
- **Alternative explanation:** informed selling, market beta, bid/ask bounce, adverse selection,
  mechanically selected extremes or a price rise compensating for left-tail risk.
- **Cheapest falsification/rejection:** source/schema identifiability first. Reject the current
  dataset as a test of forced-vs-informed flow if it contains no pre-outcome discriminator.
  That is a measurement rejection, not proof that temporary pressure never exists.
- **Data/contamination:** candle-flow variants are closed; L2 is protected/unqualified for
  predictive use. No provider acquisition or new OFI experiment is proposed here.

**Selection: no new trading hypothesis meets the required standard.** Candidate 1 is the best
documented participant/payment mechanism; Candidate 2 has the strongest risk forecast evidence.
Neither supplies a ready new alpha test. Candidate 3 lacks the necessary observation.

## 6. Selected hypothesis statement

There is **no selected new strategy hypothesis**. For a concrete primary audit target, use the
existing funding-persistence claim; it has both positive raw evidence and an already rejected
economic bridge, making it a concrete completed audit example.

> When the last 84 completed eight-hour BTCUSDT funding rates sum to more than 60 bps (X),
> assigned Monday 00:05 UTC under the original archive-timestamp-plus-delay convention
> (T; actual historical public availability **UNRESOLVED**), we expect greater cumulative
> funding over the next 28 days than in nonqualifying weeks (Y/H), because demand for leveraged
> perpetual exposure may persist and pay matched arbitrage capital (Z). We could receive the
> funding through the frozen equal-BTC long-spot/short-perpetual pair, but a practical comparative
> advantage and fully evidenced historical net economics remain **UNRESOLVED** (A). Persistent
> compensated risk and continuous funding exposure could explain the observation (C). We reject
> the raw prediction if its frozen month-block lower confidence bound is nonpositive, and reject
> the trading-timing claim if its frozen net return-per-exposed-day advantage over always-on
> matched carry is nonpositive or the risk gates fail (B).

**Known outcome:** raw prediction passes in consumed development; the trading-timing claim
fails. V1 also fails planning-margin shock; V2 repairs that risk implementation but again fails
economic efficiency on reused observations. This statement does not reopen the rejected
60/30-bps rule or authorize a weaker gross-carry score. The mechanism behind positive cashflow
is stronger evidence than “nothing predicts anything,” but weaker than accepted alpha.

## 7. Missing information

Before any materially new trading proposal can be justified:

1. A specific information or implementation advantage for this user, with capital, weekly time,
   account/venue eligibility and tolerable loss known. The 1,000-USDT unit is only normalization.
2. For carry: effective-dated spot/perpetual fees, maintenance tiers/cumulative amounts,
   funding/contract/liquidation/ADL rules, collateral financing/opportunity cost and availability
   timestamps. Current snapshots or generic stress assumptions are not historical facts.
3. For directional alpha: an unconsumed confirmation plan and an adequately powered comparison
   of a fixed hypothesis. Failed models do not identify a promising replacement automatically.
4. For risk forecasting: whether valid coverage can be obtained without selecting on outcomes;
   whether a separately frozen decision using the forecast adds net utility. HAR's earlier
   quality pass does not answer that second question.
5. For flow mechanisms: a pre-outcome discriminator beyond the rejected aggregate-flow proxies,
   with complete timestamps, book reconstruction and feasible costs.
6. For historical credibility: a reconciled experiment/inspection ledger, exact source-to-output
   bindings for provisional older work, and closure of the existing S1 byte-identity issue before
   any corrected historical comparison. **WE DO NOT KNOW** the corrected breakout's performance.

## 8. Minimal falsification experiment and why no new run is warranted now

The cheapest scientifically useful action is to reuse the existing experiment that already
answers the primary audit target. This is an evidence extraction, not a new market analysis.
Its specification is recorded here to make the inference reviewable; the immutable original
[carry contract](btc/contracts/btc-positive-funding-carry-v1.json) and
[plan](btc/reports/BTC_POSITIVE_FUNDING_CARRY_PLAN.md) remain authoritative.

| Component | Existing specification / inference boundary |
| --- | --- |
| Event | At weekly Monday decisions, sum exactly 84 completed eight-hour funding events; qualifying condition strictly above 60 bps, independent of whether the strategy is already invested. This flag is named entry in the old information report but is not an actual fill indicator. |
| Timestamp | Monday00:05UTC under the original archive-timestamp-plus-delay availability convention; next01:00 spot/perpetual opens for the legacy execution. Recorded event jitter is retained, but does not prove actual historical public receipt. A future input contract must establish availability rather than relabel archive timestamps. |
| Raw target | Sum of subsequent funding over 28 days, compared across threshold-qualified and nonqualifying weekly observations. This is a cashflow target, not BTC directional return. |
| Sample | Consumed2024–25 only:101 eligible weekly observations,43 qualifying/58 nonqualifying, each with84 subsequent observed funding events within28 days. Weekly targets overlap;6 closed strategy trades and9 non-overlapping84-day scorecard blocks show why counts are not interchangeable. |
| Control | Nonqualifying weeks for the raw cashflow question; frozen flat,49%-spot, always-on matched carry and reported no-funding/funding-only diagnostics for v1 economics. The no-funding runner simulates again with funding disabled, allowing equity/quantity/margin-path changes; exact original-window equality is unverified here. V2 compares the unchanged gate and always-on at its own frozen25% leg exposure. |
| Measurement | Raw funding differential and recorded 5,000-resample UTC-month interval, seed 20260830; separately full net return, return per exposed day, drawdown, turnover, funding/basis/cost decomposition, observed/shocked margin and concentration. |
| Costs | Preserve 30/40/80 bps round trip **per leg**. For two equal legs, 30 bps per leg totals 60 bps relative to one leg's notional, not 60 bps of total account equity. Historical financing/rule gaps remain limitations. |
| Alternative | Funding persistence without incremental entry-timing value; risk premia; favorable calendar exposure; basis and venue/margin risk. |
| Robustness | Only the original 42/126-event lookbacks at unchanged thresholds and recorded cost/margin stresses. No additional lookback, sign, horizon or filter search. |
| Raw rejection | Lower month-block bound for qualified-minus-nonqualifying subsequent funding must exceed zero under the frozen plan. The recorded bound is positive. |
| Economic rejection | The frozen gate must beat always-on return per exposed day and pass its other risk/economic gates. V1 fails both efficiency and shocked margin; V2 still fails efficiency. |
| Observed decision | Preserve the raw predictive finding with its availability convention; close the timing hypothesis. Replaying the same consumed observations supplies no independent market evidence. |

The existing design does not establish a full causal mechanism: calendar-state matching,
independent samples and participant intent remain limited. Its bootstrap interval is not
selection-adjusted across the entire incomplete research history. A positive raw test is
therefore supportive development evidence only. Its negative economic bridge is sufficient
to avoid more strategy engineering, without pretending to prove a universal absence of carry.

For the broader, untimed net-carry question, the **next necessary test would be a source
readiness test**, not another profitability run. This exact readiness question has already
been answered negatively by [MCS3-C](btc/reports/BTC_MARKET_CONDITION_SCORES_MCS3_C_READINESS_RESULT.md).
Reusing that result is preferable to rerunning it:

- The unit of inspection is an effective-dated source/rule interval, not a profitable trade.
- Each required fee, margin, contract/funding/liquidation and collateral record must have an
  applicable instrument/account scope, historical interval, provenance and known availability.
- Every required interval must be covered without present-day backfill assumptions, alternative
  venue substitution or silent interpolation. Missing one required class blocks a net label.
- Its recorded result is **FAIL on four classes**. No acquisition or extra data processing has
  been launched by this audit. A repeat is warranted only if new qualified evidence arrives.

A new prospective economic test cannot yet be fully frozen: executable venue, financing
benchmark, economically material excess-return hurdle, tail-risk acceptance, effective sample
size/power calculation and independent boundary are **UNRESOLVED**. It would be false precision
to invent those choices or declare an executable test contract. Before any future outcome access,
a separate review must bind all of them, the sole primary target/control, complete event handling,
costs, dependence-aware inference and one stopping/unlock rule. Ambiguity currently means C.

## 9. Decision tree and research reset

| Result | Conclusion and justified next step |
| --- | --- |
| Rejected prediction | Close that hypothesis and preserve the observations and trial registration. A new sign/threshold/model is a new search; do not automatically launch one. |
| Predictive effect exists but fails net comparison | Record information separately from economic value. Retire the timing implementation; do not increase exposure or lower assumed costs. This is the carry-gate case. |
| Ambiguous because data or identification is missing | Acquire or qualify only the particular missing information under a bounded reviewed scope, if its expected informational value merits the effort. Otherwise stop. No expanded model can identify an unobserved participant constraint merely by assertion. |
| Supported in development | Register it as a development finding. Freeze a new untouched confirmation boundary, event-count/power design, realistic execution and decision-relevant comparator before future results. Do not reuse an old lockbox or silently reopen 2026. |
| Independently confirmed | Only then design the smallest executable implementation at the approved mandate, test incremental execution and sizing value, and seek separate forward/promotion review. This audit authorizes none of those actions. |

Practical changes proposed now: keep one active economic question; preserve exploration
separately from confirmation; record attempted hypotheses including abandoned outcomes; label
forecast-quality, data-readiness, execution and economic gates separately; use a verified narrow
evaluator only when a prediction warrants one. Existing risk/cost/causality safeguards remain.
No new indicator, ML model, classifier, ensemble, execution filter or optimizer earns approval
without stating the new information it contributes and independently testing that contribution.

The previous proposed ten-hour/two-week budget was advice, not an approved execution budget
or an evidence horizon. This audit does not require further historical engineering as a sunk-cost
obligation. The user can stop active research with the negative and unresolved evidence intact.

## Literature, provenance and audit limits

Literature is separate from repository evidence. BIS research links crypto futures carry to
demand for leveraged exposure and constrained arbitrage capital, while emphasizing margin and
liquidation risk. That supports investigating a compensation mechanism; it does not prove a
retail perpetual-funding edge or validate this repository's parameters. Delivery-futures basis
and stochastic perpetual funding are not interchangeable. [BIS, Crypto carry](https://www.bis.org/publications/working-paper-1087-crypto-carry)

Backtest selection can defeat ordinary holdout reasoning, supporting explicit trial history and
separate confirmation. This audit does not estimate the repository's overfitting probability or
implement another statistical framework. [Bailey et al., institutional abstract](https://scholarworks.wmich.edu/math_pubs/42/)

This audit inspected repository instructions, historical reports/contracts, registries,
representative evaluator/test source, and selected preexisting aggregate artifacts. It did not
exhaustively certify every file or replay every result. Three selected BTC aggregate report
hashes match their INDEX pins; that narrow identity check is not full experimental validation.
No scoped `.ipynb` files were found in the inspected source/document directories. Scripts are
the principal inspected computational record. Unavailable predecessor repositories were assessed
only through current-repository reports, not assumed to have been independently reopened.

Repository: `/data/Trading`; Git commit and dirty state **UNKNOWN**. Both Git root/history
requests fail because usable Git metadata is unavailable (exit 128). Exact inspected-file
hashes, runtime, command observations, parallel audit notes, changes and verification are
preserved in [the audit run](btc/review_runs/edge-research-reset-20260912-v1/).

### CORRECTED_PERFORMANCE_NOT_RUN

No corrected historical breakout execution path, new historical profitability comparison,
market-data simulation, new control, sweep or research test was executed. No sealed 2026
market content or partial OB0 content was opened, hashed, content-searched or aggregated.
Filename-only discovery was used to locate permitted reports/source, not inspect protected content. No trading service,
database, NATS, Freqtrade, account or credentials were accessed. No ZIP or bridge publication was
created; bridge work remains deferred at the user's direction. Only audit documentation and
persistent review/tracker records changed. Historical evidence and strategy source are preserved.

**C. CURRENT EVIDENCE DOES NOT SUPPORT AN EDGE — stop strategy engineering and identify what information would be required to continue.**
