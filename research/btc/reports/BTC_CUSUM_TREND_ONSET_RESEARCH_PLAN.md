# BTC Causal CUSUM Trend-Onset Research Plan

Status: pre-registered before historical trigger or outcome access  
Program: `btc-cusum-trend-onset-v1`  
Pre-registered at: `2026-09-01T07:37:12Z`

## Research question and economic mechanism

Does a distributed sequence of unusually positive hourly BTC returns contain incremental
information about the next 72-hour return after controlling for ordinary endpoint momentum?

The proposed mechanism is gradual information diffusion or persistent order imbalance. It is
not the prior compression/range-break mechanism and it is not a new regime filter. Academic
evidence documents time-series momentum in cryptocurrencies and intraday BTC, but also warns
that hourly predictability changes through time and that volatility scaling can manufacture
apparent strategy performance. The experiment therefore uses volatility only to normalize the
online detector and target; it tests signal information before position sizing or PnL.

Primary background:

- Liu and Tsyvinski, *Risks and Returns of Cryptocurrency*:
  https://www.nber.org/papers/w24877
- Shen, Urquhart and Wang, *Bitcoin intraday time series momentum*:
  https://onlinelibrary.wiley.com/doi/10.1111/fire.12290
- Moskowitz, Ooi and Pedersen, *Time Series Momentum*:
  https://fairmodel.econ.yale.edu/ec439/mosk.pdf
- Kim, Tse and Wald, *Time series momentum and volatility scaling*:
  https://doi.org/10.1016/j.finmar.2016.05.003

These sources motivate a falsifiable test. They do not validate this detector or imply that it
will be profitable.

## Novelty and family boundary

This remains one candidate inside the existing `btc_directional_trend` family. It cannot count
as economic diversification from the fixed breakout, SMA, compression breakout or another
trend arm.

The detector is materially new only because it measures the *path* of sequential positive
standardized innovations. It uses no range high, compression state, moving-average crossing,
volume, taker flow, BOCPD, HMM, rejected condition score, news or macro input. A single return
cannot trigger it. If the CUSUM geometry adds no chronological information beyond the endpoint
24/72-hour return controls, the novelty claim fails even if the unconditional event return is
positive.

## Frozen TNE1 trigger

Input is the existing checksummed BTCUSDT five-minute 2017--2025 development source. Aggregate
only complete, contiguous, same-segment one-hour candles. Let
`r_t = log(close_t / close_(t-1))` at the completed-hour availability timestamp.

For every eligible hour:

1. Estimate `sigma_t = sqrt(mean(r^2))` from exactly 168 completed hourly returns strictly
   preceding `r_t`. Zero, non-finite or incomplete history fails closed.
2. Compute `z_t = r_t / sigma_t` and clip it to `[-2, 2]`.
3. Update the one-sided Page statistic
   `S_t = max(0, S_(t-1) + clipped_z_t - 0.25)`.
4. Reset run age and contributor count whenever `S_t` returns to zero.
5. Trigger only on the first crossing from below `4.5` to at least `4.5`, with at least three
   strictly positive net contributions spanning at least three active hours.

The exact next same-segment five-minute open is the fill-time reference, not a trade. A trigger
starts fixed 72-hour suppression: the statistic is neither carried nor updated during that
window, including the hourly return ending exactly at `trigger+72h`; it restarts empty with the
first contribution ending at `trigger+73h`. Gaps and segment changes reset volatility history,
statistic, contributors and suppression. No activation timestamp may reach 2026.

At each trigger record only information available then: frozen volatility; Page statistic;
run age; contributor count; largest one-hour net contribution as a fraction of the statistic;
24/72-hour endpoint momentum divided by `sigma_t*sqrt(24)` and `sigma_t*sqrt(72)` respectively;
the short/long scale ratio
`sqrt(mean(last 24 strictly preceding hourly returns squared)) / sigma_t`; and UTC
hour-of-week sine/cosine. The largest-contribution fraction is the largest strictly positive
`clipped_z - 0.25` contribution in the active run divided by `S_t` at the trigger.

### Parameter provenance

`k=0.25`, `h=4.5`, clipping at two standard deviations and the three-contributor rule were
chosen from a seeded synthetic standard-normal design, not BTC event counts or outcomes. With
seed `20260901`, 10,000 independent paths and a 3,000-hour cap, the frozen recurrence produced
a null mean/median run length of approximately 125.15/89 hours. Under a 0.5-standard-deviation
positive mean shift, mean/median detection delay was approximately 16.55/14 hours. The
qualification script and exact dependency versions must reproduce these values within frozen
Monte Carlo tolerances before historical deserialization.

## Ordered sample and label gates

TNE1-A materializes trigger timestamps and causal features only. It must not deserialize or
emit any post-trigger label value. It passes only if all conditions hold:

- at least 300 eligible independent triggers;
- at least 150 triggers before 2021;
- at least 30 triggers in each of 2021, 2022, 2023, 2024 and 2025;
- at least 36 populated UTC calendar months;
- no calendar year supplies more than 30% of triggers; and
- the three largest calendar months supply no more than 20% of triggers.

Failure stops this experiment ID. The threshold, scale window, clipping, clock and suppression
may not be changed to repair the count.

Only after TNE1-A passes may TNE1-B materialize the frozen target. The primary target is
`log(close_(fill+72h) / fill) / (sigma_t * sqrt(24))`, using the exact completed same-segment
hour ending at `fill+72h`. Segment/source loss is censoring. Required label coverage is 90%;
every evaluation year must have at least 25 complete targets. First completed-hour passage to
`+/- sigma_t*sqrt(24)` is a symmetric diagnostic only, with adverse-first tie precedence. It
cannot rescue the continuous target.

## Frozen TNE2 forecast comparison

TNE2 is permitted only after both TNE1 gates pass.

- M0: expanding training mean.
- M1: ridge regression using the simple 24/72-hour endpoint momentum controls, scale ratio and
  hour-of-week terms.
- M2: M1 plus Page run age, positive-contributor count, threshold excess and maximum one-hour
  contribution fraction.

Ridge alpha is selected only from `{0.01, 0.1, 1, 10, 100}` using expanding inner folds and
training-only standardization. Outer evaluation years are 2021--2025. Training labels reaching
the boundary are purged and evaluation begins after a further 72-hour embargo, producing 144
hours of total label/prediction separation. Each outer fold requires at least 120 training and
25 evaluation observations. Inner folds require at least 50 training and 15 evaluation
observations, with at least two eligible expanding folds. No preprocessing, calibration or
selection crosses a boundary.

Primary metric is pooled out-of-fold MSE on the normalized 72-hour return. MAE, regression
calibration, directional accuracy and rank correlation are diagnostics. M2 passes only if:

- the pooled out-of-fold realized normalized 72-hour return is positive, its 95% lower
  confidence bound is strictly positive, at least four of five evaluation-year means are
  positive, and its mean remains positive after excluding the best three event months;
- M1 improves on M0 and M2 improves on both;
- M2 improves MSE by at least 2% versus M1;
- the paired calendar-block-bootstrap 95% interval for M2-minus-M1 MSE improvement is wholly
  favorable using circular moving blocks of exactly three contiguous UTC months over the full
  January-2021 through December-2025 calendar (including zero-event months), 10,000 resamples
  and seed `20260901`; the diagnostic M0-to-M1 comparison deterministically uses seed
  `20260902`, and the standalone-return interval uses the same method and seed `20260903`;
- M2 does not worsen MAE;
- M2 beats M1 in at least four of five outer years;
- the improvement remains positive after excluding the best three months; and
- no one year supplies more than 50% of total positive improvement.

Overlap at exact and plus/minus 24-hour timestamps must be reported against the fixed 20/10,
rejected expansion and compression catalogues where compatible event timestamps exist. High
overlap or failure to beat M1 rejects the claimed sequential-path information.

## Later stages and safety

TNE3 strategy PnL is prohibited unless TNE2 passes. A later contract must separately freeze
entries, exits, EWMA sizing, flat, buy-and-hold and exposure/timestamp-matched controls, and
30/40/80-bps costs. Signal information and sizing attribution must remain separate.

All 2017--2025 results are development evidence. The 2026 partition remains sealed or
ineligible. No partial OB0, network, database, NATS, Freqtrade, exchange, production signal,
position, order, cost, PnL or live allocation is permitted. Every output remains
`actionable_arm_id = no_trade`, with zero accepted arms.
