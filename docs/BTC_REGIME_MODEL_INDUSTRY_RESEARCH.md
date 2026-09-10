# BTC Regime Models: Academic and Systematic-Firm Research

Status: research synthesis; no implementation or live-trading authorization  
Updated: 2026-08-28  
Scope: public primary research and firm publications available online

## Executive conclusion

There is no single industry definition of a market regime. Systematic firms define a regime
according to the decision it is meant to improve:

- macro regimes diversify portfolios across growth and inflation surprises;
- risk-appetite regimes adjust broad risk exposure;
- volatility and liquidity regimes change sizing, execution, or tail protection;
- return-distribution regimes describe which factors are currently rewarded;
- trend systems often blend several speeds continuously instead of choosing one strategy from
  a hard bull/bear label.

The strongest public evidence does **not** support building another daily bullish/bearish
classifier and using it as an all-or-nothing BTC breakout gate. Classification and direction
are different claims. Two Sigma explicitly describes its GMM conditions as non-predictive,
Bridgewater uses economic environments to balance structural beta rather than time regime
turns, and Man AHL emphasizes volatility scaling and diversified trend speeds. This distinction
explains the repository's BOCPD result: a causal state estimator can be statistically coherent
while still being a poor directional entry veto.

For this project, the recommended order is:

1. retain a transparent breakout/trend forecast as the directional component;
2. add continuous volatility scaling as the first risk layer;
3. only then test a small, heavy-tailed, persistent **risk/opportunity state** that adjusts risk
   or trend-speed weights gradually;
4. keep a no-regime control and require incremental out-of-sample value;
5. defer LLM event classification until the deterministic price/risk system passes.

## What public systematic firms actually disclose

The table summarizes public material. It does not claim to reveal proprietary production code.
Some publications are research examples or allocator tools, not statements that the exact model
trades a named fund.

| Organization | Public regime definition and method | How it is used | Important lesson for BTC |
|---|---|---|---|
| Bridgewater | Four structural environments from growth and inflation surprising above/below expectations. Assets are decomposed into environmental betas and risk-balanced across the four quadrants. | Strategic portfolio construction and beta diversification, not a promise to forecast every turn. | Define the economic job first. An environment map can be useful without being a trading signal. Separate cash, beta, and alpha attribution. |
| Two Sigma | Unsupervised Gaussian Mixture Model on the joint distribution of 17 residualized macro/style factor returns. Four clusters were selected by cross-validated likelihood, with AIC and goodness-of-fit checks: Crisis, Steady State, Inflation, and Walking on Ice. Output is a probability vector. | Portfolio diagnosis, tail-risk analysis, and asset-allocation context. The paper explicitly says the model is not predictive. | A cluster label describes the present distribution. Do not assume it forecasts BTC direction. Preserve probabilities rather than force a label. |
| State Street Investment Management | Its operational Market Regime Indicator is a continuous 0–100 risk-aversion gauge using implied equity/FX volatility and fixed-income spreads, mapped to five bands from Euphoria to Crisis. A separate 2025 study uses 23 return/uncertainty features, robust scaling, residualization, a Student-t mixture and GARCH; AIC/BIC choose four regimes. | MRI is one input to tactical allocation. The research model studies conditional asset returns and crisis alignment. | Forward-looking market prices and heavy tails are more appropriate for risk state than a Gaussian BTC mean. A continuous gauge is less brittle than a hard veto. |
| Man AHL | Multiple trend speeds, primarily double-EWMA families plus breakouts, volatility-scaled across markets. Public crypto research says real systems include time-varying costs and regime-dependent signal speeds. | Blend diversifying speeds, normalize risk, and balance long-run Sharpe against fast-model crisis responsiveness. | Do not require a separate bull label before a breakout. Blend slow and fast trend forecasts, size by volatility, and account for the extra cost of faster models. |
| Invesco | Four business-cycle states—Recovery, Expansion, Slowdown, Contraction—from a leading economic index above/below trend and a global-risk-appetite indicator accelerating/decelerating. Uses first-vintage data and causal normalization. | Monthly tactical asset allocation and factor/risk-premia tilts. | Point-in-time vintages and release lags are mandatory. This macro horizon is better suited to monthly allocation than a 4h BTC entry gate. |
| Research Affiliates | Four growth/inflation quadrants. Its published baseline deliberately uses lagged observed regimes and a random-walk next-month forecast; it also reports a perfect-foresight diagnostic. | Tests whether macro mapping has value separately from regime-forecast skill. | Separate the value of the allocation rule from the ability to predict the state. Perfect hindsight must never be mixed with executable results. |
| BlackRock Systematic | Public factor-timing descriptions combine economic regime—growth, recession probability, sentiment, rates and volatility—with valuation, factor momentum and factor-specific stability/crowding. Another publication emphasizes training robustness by upweighting adverse histories. | Factor weighting and model robustness, with multiple signals rather than a single regime oracle. | Treat regime as one input with model uncertainty. Stress adverse histories instead of fitting an elaborate state map to a few BTC cycles. |
| AQR | Public macro studies commonly analyze growth and inflation levels/surprises and compare asset behavior by quadrant, then emphasize diversified or equal-risk portfolios. | Strategic diversification and inflation-risk attribution more often than short-horizon regime timing. | Macro regimes may explain BTC beta/correlation, but their slow publication cadence is mismatched to a 4h trigger unless used only as a slow risk context. |

### Primary firm sources

- Bridgewater, [The All Weather Story](https://www.bridgewater.com/resources/all-weather-story.pdf)
- Two Sigma, [A Machine Learning Approach to Regime Modeling](https://www.twosigma.com/wp-content/uploads/2021/10/Machine-Learning-Approach-to-Regime-Modeling_.pdf)
- State Street, [Market Regime Indicator update](https://www.ssga.com/us/en/institutional/insights/how-the-alpha-meeting-informs-our-model-portfolios)
- State Street, [Decoding Market Regimes with Machine Learning](https://www.ssga.com/library-content/assets/pdf/global/pc/2025/decoding-market-regimes-with-machine-learning.pdf)
- Man AHL, [The Need for Speed in Trend-Following Strategies](https://www.man.com/insights/need-for-speed-trend-following)
- Man AHL, [In Crypto We Trend](https://www.man.com/insights/in-crypto-we-trend)
- Man Group/Oxford-Man Institute, [An Investor's Guide to Crypto](https://www.man.com/insights/investor-guide-to-crypto)
- Invesco, [Tactical Asset Allocation, Risk Premia, and the Business Cycle](https://doi.org/10.3905/jpm.2022.1.456)
- Research Affiliates, [Beware the Shocks in the Road](https://www.researchaffiliates.com/content/dam/ra/publications/pdf/822-beware-the-shocks-in-the-road.pdf)
- BlackRock, [Time to Tilt: Harnessing Factor Cyclicality](https://www.blackrock.com/us/financial-professionals/insights/factor-timing)
- AQR, [Inflation in 2010 and Beyond, Part II](https://www.aqr.com/-/media/AQR/Documents/Insights/White-Papers/Inflation-in-2010-and-Beyond--Part-II.pdf)

## Academic model families

### 1. Rule-based economic quadrants

States are defined before fitting—for example growth rising/falling crossed with inflation
rising/falling. They are interpretable and useful for long-horizon asset allocation. Their
weaknesses are slow and revised macro releases, arbitrary thresholds, and too few independent
cycles for a complex trading rule.

Use: structural portfolio attribution or a very slow contextual layer.  
Do not use: as an apparent real-time 4h signal unless point-in-time release vintages and lags are
modeled.

### 2. Finite mixtures: GMM and Student-t mixtures

Mixture models fit several conditional return distributions but do not require a temporal state
transition process. They provide membership probabilities and are useful for discovering
cross-sectional market conditions. A Student-t emission is preferable for heavy-tailed financial
returns. Without an explicit persistence mechanism, classifications may flicker.

Use: descriptive clustering, stress sampling, factor/asset conditional analysis.  
Do not use: treat a retrospectively labeled cluster as a directional forecast.

### 3. Markov switching and Hidden Markov Models

Hamilton's model treats autoregressive parameters as outcomes of an unobserved discrete Markov
state. HMMs add explicit transition probabilities and therefore encode persistence. Multivariate
regime-switching research shows that expected returns, variances, and correlations can change
together, producing materially different portfolio allocations.

For executable research, use **filtered** probabilities based only on observations through time
`t`. Full-sample smoothed probabilities or a Viterbi path revised with future observations are
diagnostic only and cause look-ahead if used for trades.

Use: a small number of persistent probabilistic states and conditional risk estimates.  
Risks: Gaussian tails, local likelihood optima, state-label switching on refit, overconfident
probabilities, and weak identification from a short history.

### 4. Online change-point models

Bayesian Online Change-Point Detection estimates the posterior distribution of run length since
the last structural break. It is causal and valuable when abrupt parameter resets are the actual
mechanism. It does not by itself say that the new state predicts a positive return. The observation
model and the downstream action still require independent evidence.

The repository's first BOCPD test used daily open-to-close BTC drift. The detector was causal, but
the chosen state lacked forward information and removed profitable breakout exposure. That is a
mechanism failure, not a reason to replace filtered inference with hindsight smoothing.

### 5. Persistent jump and change-penalty models

Statistical jump models classify states while penalizing unnecessary transitions. Recent research
reports that this can produce more persistent, robust risk states than conventional switching
models and evaluates it with time-series cross-validation, costs, and execution delay. Sparse
variants can select a limited set of state-defining variables.

Use: a candidate alternative when state flicker is an observed problem.  
Risk: choosing the transition penalty to maximize the same strategy backtest turns the regime
model into hidden strategy optimization.

### 6. Continuous state models

Many production-style systems do not need discrete labels. A composite risk score, volatility
forecast, correlation estimate, or posterior expected risk can move continuously. Bands and
hysteresis may be used operationally, but position changes can remain gradual.

Use: volatility targeting, drawdown reduction, execution aggression, or exposure caps.  
This is the closest match to State Street's public MRI and to Man AHL's volatility scaling.

### Foundational papers

- Hamilton (1989), [A New Approach to the Economic Analysis of Nonstationary Time Series and the Business Cycle](https://doi.org/10.2307/1912559)
- Ang and Bekaert (2002), [International Asset Allocation with Regime Shifts](https://doi.org/10.1093/rfs/15.4.1137)
- Guidolin and Timmermann (2007), [Asset Allocation under Multivariate Regime Switching](https://doi.org/10.1016/j.jedc.2006.12.004)
- Adams and MacKay (2007), [Bayesian Online Changepoint Detection](https://arxiv.org/abs/0710.3742)
- Shu, Yu, and Mulvey (2024), [Downside Risk Reduction Using Regime-Switching Signals](https://doi.org/10.1057/s41260-024-00376-x)

## What is specific to BTC

BTC is not simply a high-volatility equity index. The public crypto evidence highlights:

- volatility is large and non-stationary, making volatility scaling a first-order control;
- short histories contain very few independent boom, crash, deleveraging, and liquidity cycles;
- correlations with traditional risky assets rise in their left tails;
- liquidity and costs change sharply across coins and stress periods;
- continuous 24/7 trading creates strong intraday periodicity;
- price direction, volatility, liquidity, cross-asset contagion, and speculative attention are
  different regime axes and should not be collapsed into one bull/bear label.

Relevant studies include:

- Li and Miu (2023), [Are Cryptocurrencies a Safe Haven for Stock Investors?](https://doi.org/10.1016/j.jempfin.2022.12.010), finding stock–crypto correlation depends on both markets' volatility states.
- Chaim and Laurini (2019), [Is Bitcoin a Bubble?](https://doi.org/10.1016/j.frl.2018.03.018), applying Bayesian change-point analysis to Bitcoin returns and volatility.
- Man Group's [crypto trend research](https://www.man.com/insights/in-crypto-we-trend), emphasizing volatility scaling, liquidity, costs, breakouts, multiple coins, and regime-dependent speed rather than a single directional regime oracle.
- [Periodicity in Cryptocurrency Volatility and Liquidity](https://arxiv.org/abs/2109.12142), documenting recurrent intraday patterns across Bitcoin and Ether venues.

## What a professional regime research contract contains

### Decision first

Specify the regime's job before choosing a model:

| Job | Suitable target | Example action |
|---|---|---|
| Direction forecast | Forward return distribution | Usually leave to the alpha model, not the regime layer |
| Risk state | Forward volatility, downside tail, correlation, or liquidity | Scale exposure or cap risk |
| Opportunity state | Trend persistence or post-cost alpha by horizon | Blend already validated trend speeds |
| Execution state | Spread, depth, impact, adverse selection | Change order urgency or stand aside |
| Macro context | Growth, inflation, liquidity surprises | Slow portfolio attribution or strategic weights |

One model should not be judged by all five objectives.

### Causal input contract

- Every feature has an `observed_at`, `available_at`, source version, and maximum age.
- Macro data use first releases, not revised final histories.
- Rolling normalization is fitted only on the expanding or trailing past.
- State inference is forward-filtered; smoothing is prohibited for executable results.
- A model refit at time `t` may use only data available by `t`.
- State identities are mapped consistently across refits to prevent label switching.
- Unknown, stale, missing, or out-of-distribution input produces an explicit unknown state.

### Output contract

Store more than a label:

- probability of each state;
- entropy or confidence;
- state age and transition probability;
- feature cutoff and model-fit cutoff;
- model/version and feature checksums;
- stale/unknown reasons;
- the action mapping separately from the inferred state.

### Validation contract

1. Compare against no-regime, simple observable thresholds, and a continuous risk control.
2. Evaluate state information separately from downstream strategy performance.
3. Use expanding or rolling walk-forward refits with purging/embargo where labels overlap.
4. Report dwell times, transition counts, flicker, probability calibration, and label stability.
5. Report conditional returns, volatility, drawdown, tail loss, correlation, liquidity and costs.
6. Charge turnover created by state changes and include an implementation delay.
7. Compare hard switching with probability-weighted gradual action.
8. Test state-count, feature, refit-window, emission-family, and persistence sensitivity without
   selecting the best development variant.
9. Require value across multiple genuinely unseen transitions, not just high full-period Sharpe.
10. Attribute improvement to risk reduction, beta timing, alpha selection, sizing, and costs.

## Why “no lagging signal” is not an achievable requirement

Every inferred regime uses observations and therefore reacts after evidence arrives. Macro releases
are delayed; realized volatility is backward-looking; HMM probabilities are filtered estimates;
implied volatility and spreads are forward-looking prices but still respond to current information.
Professional systems manage this trade-off rather than claim to eliminate it:

- use several trend speeds instead of one perfect turning-point estimate;
- use liquid, forward-looking risk prices where available;
- expose probabilities and uncertainty;
- adjust weights gradually;
- use faster states for risk control and slower states for allocation;
- measure detection delay explicitly against the cost of false transitions.

For BTC, a regime layer that is slightly late but correctly reduces tail exposure may be useful. A
late bullish label that vetoes the early portion of every breakout is likely destructive—as the
frozen BOCPD experiment demonstrated.

## Recommended BTC architecture

```text
BTC market data
   ├─ directional forecasts: fixed breakouts / trend speeds
   ├─ risk forecast: realized volatility + downside/tail measures
   ├─ context state: small persistent probabilistic model
   └─ execution state: spread/depth only after accepted L2 data
                    ↓
       probability-weighted risk and speed blend
                    ↓
          mandate and portfolio risk kernel
                    ↓
             realistic execution model
```

The regime model must not select an unvalidated strategy arm. Until multiple arms independently
pass, its only permitted experimental action should be risk scaling or a blend among frozen trend
speeds, always compared with the same strategy without the regime layer.

## Recommended next research experiment—not yet frozen

Do **not** immediately implement an HMM because firms use one. First complete a design study with
one narrow question:

> Does a causal BTC risk state improve a fixed breakout's drawdown and tail loss while retaining
> at least 90% of its net CAGR, compared with both constant 10% allocation and simple continuous
> volatility scaling?

Recommended controls and candidate:

1. **Control A:** fixed 10% allocation, existing breakout.
2. **Control B:** same breakout with causal EWMA volatility scaling and frozen caps.
3. **Candidate:** two-state persistent Student-t HMM or statistical jump model using only risk
   features; output probability scales exposure continuously and never changes entry direction.
4. **Features:** log realized volatility at two horizons, downside/upside semivariance ratio,
   high-low range or jump measure, and—only when independently accepted—liquidity/depth.
5. **Prohibited in v1:** news/LLM, revised macro data, full-sample smoothing, return-sign labels,
   parameter selection on strategy PnL, and sealed 2026 data.

This experiment should not start until the fixed breakout control receives its own chronological
attribution and stability contract. Otherwise the regime layer would be optimizing risk around an
unaccepted base strategy.

## Decision for the repository

- **Retain:** breakout/trend as the directional research family.
- **Retain:** causal probabilities, explicit uncertainty, state age, and unknown behavior as P2
  infrastructure requirements.
- **Reject:** BOCPD daily drift as a directional entry gate under its closed experiment ID.
- **Do next:** independently validate the breakout control, then test simple volatility scaling.
- **Research afterward:** a two-state heavy-tailed persistent risk model, only if it beats simple
  volatility scaling out of sample.
- **Defer:** LLM regime labels and strategy routing. An LLM may later provide a separately tested,
  timestamp-safe event-risk veto.
