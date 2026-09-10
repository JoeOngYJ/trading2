# BTC research review — 10 September 2026

## Executive assessment

We have useful research infrastructure, several positive historical results, and preserved negative
experiments. We do not have an accepted trading strategy or a validated production trading system.
The most recent achievement is independent reconciliation of the fixed-breakout archived cash
arithmetic. The main remaining engineering problem is its execution assumptions. Separately,
the research has not established sufficiently robust incremental strategy value over simple controls.

“Nothing profits” is inaccurate. “We have not established a strategy whose profits we can rely on”
is the better description. Fixing accounting or execution does not guarantee discovery of alpha.

## Objective and scope

Build a credible BTC-only research and backtesting process, establish one economically explainable
strategy after costs and risk constraints, and only then consider risk overlays, complementary
strategies, routing and prospective paper observation. A strategy need not profit every calendar
year, but its losses, drawdowns, concentration and comparative performance must meet rules set
before evaluation. Favorable periods selected afterward are not independent validation.

BTC is the active market. ETH, ETFs and cross-asset research are archived lanes, not current work.
Separate research mandates cover spot long/flat, directional perpetuals, and matched spot-long /
perpetual-short carry. These are distinct permissions, not one unrestricted leverage mandate.
Research capital is normalized (commonly 1000 USDT); live capital remains zero. User return
aspirations are not optimizer targets. No account execution, live PnL or accepted strategy arm exists.
All actionable output remains `no_trade`. Keep applicable 2026 partitions sealed; consumed
2017–2025 observations do not become a fresh holdout merely because an experiment gets a new ID.

## Architecture: what each layer does and its actual status

| Layer | Purpose | What we have / what remains |
|---|---|---|
| Evidence and context | Preserve inputs, assumptions, failures and reproduction | Checksummed catalogue, contracts, manifests, chained decision log, tracker, handoff and context validator |
| Market data and causal features | Make information available at the right simulated time | Segment-aware 5m/4h/daily price research; daily close risk data; separate funding/perpetual archives. Coverage and source differences remain dataset-specific |
| Strategy / alpha | Decide whether and when a position has expected net value | Breakout, directional trend and carry experiments; zero accepted arms |
| Risk / market-condition forecasts | Estimate volatility, downside or other distinct properties | EWMA retained benchmark; several other forecasts rejected. Risk sizing does not establish directional alpha |
| Score combination | Represent compatible forecasts and combine qualified inputs | Synthetic contracts, causal percentile calibration, same-target weighted combination and downward-only risk caps; no accepted hybrid predictor |
| Execution and accounting | Convert decisions into defensible fills, fees, cash and inventory | R0 and R1 synthetic references accepted; R2 archived accounting reconciled; legacy breakout execution defects need correction |
| Metrics and validation | Compare net returns, risks, controls and uncertainty | Canonical scorecard and chronological research methodology; historical strategy evidence remains insufficient/rejected |
| Routing / deployment | Choose accepted strategies and eventually observe execution | Deferred. Routing needs two economically distinct accepted arms. Production/soak services are outside this research task |

These are logical responsibilities, not proof that one fully integrated end-to-end system is ready.
L2 capture is background data engineering; it is not an accepted order-book strategy.

## Strategies and triggers

**Fixed 20/10 breakout — development control.** BTC spot long/flat. At a completed four-hour
bar, enter when close exceeds the highs of the preceding 120 four-hour bars (20 days). Exit
channel uses the preceding 60 bars (10 days). Legacy implementation uses a 4% protective stop,
14-day maximum hold, segment exits and five-minute execution references. Allocation is 10% of
account cash/equity when flat. This seeks continuation after a price-channel break; it is not
a news-event strategy. Legacy event ordering and segment handling remain under correction.

**EWMA-scaled breakout — mandatory risk benchmark.** Keeps the same breakout opportunities,
uses causal daily-close volatility and scales allocation downward from the 10% ceiling. Its
purpose is risk control, not a second alpha family or independently accepted trading strategy.

**7/28/84-day perpetual trend blend v5 — rejected.** Combines completed return horizons using
volatility standardization, equal weights and a +/-0.25 flat band, with daily decisions and next
01:00 fills. Permits long/short/flat within a 25% absolute-notional research cap. Tests sought
persistent price direction. The blend failed later stability and comparisons with simpler controls.

**Funding-gated matched carry v2 — risk implementation passed, timing hypothesis rejected.**
Long BTC spot and matched short perpetual, 25% notional per leg with conservative collateral.
The frozen 60/30-bps funding entry/exit thresholds seek funding income while reducing time exposed.
Funding earned money, but the gate underperformed same-exposure always-on carry.

**Always-on carry — unaccepted structural benchmark.** Same matched exposure held continuously.
It is informative about funding economics but has inadequate independent evidence and incomplete
venue/account/collateral economics. It is not ready to deploy.

Other rejected research includes BOCPD-gated breakout, aggregate taker-flow absorption variants,
sparse event/continuation tests and several market-condition forecasts. These are not dormant
accepted strategies waiting for a router. Preserve the exact rejected hypotheses; do not erase
negative evidence by selecting a favorable threshold or period afterward.

## Recorded returns, sizing and risk

Figures below come from the linked reports. Net return is cumulative account return, not annual
return or return on the invested leg alone. Bps refer to the report's frozen cost scenario.
Comparisons across rows are limited by different periods, exposure and execution conventions.

| Strategy / scenario | Period | Allocation | Net return | CAGR | Maximum drawdown | Other metrics |
|---|---|---|---:|---:|---:|---|
| Fixed breakout, 30 bps | 2019–2025 consumed development | 10% spot | 16.94% | 2.26% | 5.02% legacy | Calmar 0.450; profit factor 1.876; 67 trades |
| Fixed breakout, 40 bps | Same | 10% spot | 16.14% | 2.16% | 5.14% legacy | Calmar 0.420; 67 trades |
| Fixed breakout, 80 bps | Same | 10% spot | 13.01% | 1.76% | 5.62% legacy | Calmar 0.314; 67 trades |
| EWMA breakout, 30 bps | Same locked opportunities | <=10% spot | 18.75% | 2.48% | 3.28% legacy | Calmar 0.758; 67 opportunities |
| EWMA breakout, 80 bps | Same | <=10% spot | 15.61% | 2.09% | 3.68% legacy | Calmar 0.569 |
| Perpetual trend v5, 30 bps | 2020-02-03–2023-12-31 | <=25% absolute notional | 48.30% | 10.60% | 14.22% | Sharpe 0.776; 116 episodes |
| Perpetual trend v5, 30 bps | 2024–2025 consumed stability | Same | -6.41% | -3.25% | 13.87% | Sharpe -0.305; 53 episodes |
| Perpetual trend v5, 80 bps | 2024–2025 | Same | -12.77% | Not reproduced here | Not reproduced here | Rejected |
| Funding-gated carry v2, 30 bps | 2024–2025 consumed | 25% per matched leg | 2.95% | 1.46% | 0.21% | 6 trades |
| Funding-gated carry v2, 80 bps | Same | Same | 1.33% | 0.66% | 0.75% | 6 trades |
| Always-on carry, 30 bps | Same | Same | 7.75% | 3.81% | 0.14% | 1 continuous trade |

Metric-definition warning: the later daily-sampled scorecard reports breakout/EWMA drawdown of
4.83%/3.15%, versus legacy 5.02%/3.28%. Daily sampling can miss intraday equity lows; these are
different observation grids, not evidence that risk improved. The daily scorecard reports
conventional Sharpe 0.884/1.112 and dependence-adjusted Sharpe 0.739/0.896 respectively. Do not
mix the scorecard drawdown with a Calmar ratio computed from the legacy series.

The supplemental carry scorecard's 5.83% return concerns older 49%-per-leg v1, not safe v2's
2.95%. Its conventional Sharpe 5.066 falls to 1.566 after dependence adjustment; six trade cohorts
and nine independent blocks do not justify confidence from the large headline Sharpe.

F1/accuracy are not profit metrics, and no strategy-level F1 score is established here. Risk
forecasts instead use proper forecast losses and calibration; strategies need net expectancy,
turnover, costs, drawdown, exposure, concentration and matched-control uncertainty alongside returns.

## Risk and score experiments

| Component | Finding / disposition |
|---|---|
| EWMA volatility | Retained mandatory benchmark; one-day QLIKE -5.9145 vs -5.6846 for expanding control (lower better). Overlay development gates passed, but monthly incremental-return confidence intervals include zero |
| Student-t HMM | Rejected: next-seven-day downside separation interval crossed zero, despite variance separation and stable states; stopped before overlay PnL |
| Persistence score | Rejected: primary seven-day MSE 1.19% worse than simpler comparison; also coverage/stability failures |
| Displacement/reversion score | Rejected: pooled reversal 12.46 bps vs frozen 80-bps gate; symmetric mechanism failed |
| Downside/tail forecast | Semivariance information promising, but joint tail-loss tests failed; not an accepted risk cap |
| Jump/change score | Rejected: comparative probability/error losses worse than rolling controls |
| HAR realized volatility | Forecast quality promising but coverage failed; do not treat it as accepted |
| Carry market-condition score | Not activated in the score program; do not confuse this with the separate executed carry strategy experiments |
| Hybrid score foundation | Synthetic infrastructure passed. Rejected predictors cannot become accepted by combining them |

## Why the results are weak or not accepted

1. **Low account exposure limits headline return.** The fixed breakout invests only 10% when in a
   trade. Raising exposure would also raise losses and risk; it does not improve alpha. We should
   compare at matched risk/exposure rather than optimize for a desired headline return.
2. **Positive returns do not establish incremental value.** Breakout evidence failed comparative
   timing/participation checks; funding gating earned less efficiently than always-on carry.
3. **Directional stability failed in a tested candidate.** The perpetual blend lost in both 2024
   and 2025 and failed uncertainty/control gates. One bad year alone is not the universal issue.
4. **Evidence is consumed, sparse or concentrated.** Carry's few trades and incomplete research-
   trial history limit inference. Repeatedly tuning these observations cannot create unseen data.
5. **Execution correctness remains unfinished for the legacy breakout.** Accounting replay can
   verify arithmetic conditional on fills, while the fills themselves are still questionable.
6. **Our process overexpanded infrastructure.** Repeated broad C0 design attempts did not deliver
   one trustworthy historical execution path. Narrow reference accounting made concrete progress.

We have not measured how much the confirmed execution issues change historical breakout return.
They can bias outcomes in different directions; correcting them is not a promised profitability fix.
Do not generalize this breakout audit into a claim that every separate research result is invalid.

## Latest engineering findings and what is solved

R0 passed synthetic cash/inventory cases. R1-v1 precision 50 failed an extreme allowed input;
that result was preserved. R1-v2 and then wider R1-v3 passed independent exact-rational tests.
R2-v1 stopped at the archived precision boundary; R2-v2 then reconciled all 201 recorded trades
across three costs and 1005 comparisons. Largest cash discrepancy was below 7.3e-13 USDT.
The precision mismatch is resolved; there is no material arithmetic mismatch in this replay.

The independently reproduced A0 execution counterexamples remain:

- A scheduled exit at open 110 is overridden by a later low 95, producing stop 96.
- A segment-end close 105 is recorded at its bar's opening time, five minutes too early.
- Changing a future segment label triggers an exit at the preceding close, exposing retrospective
  boundary handling. Unexpected gaps must not be modeled as known in advance.

## Next work: one bounded execution correction

Freeze chronological open/stop precedence, close timestamps and known-terminal versus unexpected-
gap handling; test synthetic counterexamples; obtain independent review. Then freeze one historical
comparison of the unchanged BTC breakout, attributing differences to each correction and all three
cost scenarios. Keep parameters fixed and distinguish idealized same-boundary fills from latency.
Only after this should we decide whether further independent strategy research is justified.
Do not buy data, add detectors, increase leverage or build routing to address these engineering issues.

## Primary repository evidence

- [Latest accounting and execution result](reports/BTC_ACCOUNTING_RECONCILED_EXECUTION_AUDIT_RESULT.md)
- [Independent execution review](reports/BTC_EXECUTION_A0_REVIEW.md)
- [EWMA benchmark and legacy breakout metrics](../../docs/BTC_REGIME_ROUTING_S2_V2_RESULT.md)
- [Canonical scorecard and definition differences](reports/BTC_BACKTEST_SCORECARD_RESULT.md)
- [Perpetual trend rejection](reports/BTC_MULTIHORIZON_PERP_TREND_V5_RESULT.md)
- [Safe carry v2 attribution and limitations](reports/BTC_SAFE_FUNDING_CARRY_RISK_V2_RESULT.md)
- [Score-combination scope](reports/BTC_SCORE_COMBINATION_FOUNDATION_RESULT.md)
- [Full research tracker](../../docs/RESEARCH_TRACKER.md)
- [Current handoff](HANDOFF.md), [machine index](INDEX.json), [decision history](DECISIONS.jsonl)

This document summarizes existing evidence; it runs no new market experiment and changes no
strategy acceptance decision. Context validation: `python3 scripts/validate_btc_focused_context.py`.
