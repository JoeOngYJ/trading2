# BTC Online-Regime Breakout Hypothesis

Experiment ID: `btc-online-regime-breakout-v1`  
Status: **frozen before development execution**  
Machine-readable contract:
[`../config/experiments/btc-online-regime-breakout-v1.json`](../config/experiments/btc-online-regime-breakout-v1.json)

## Question

Can a causal Bayesian online change-point estimate of positive BTC drift improve a fixed
upside-breakout strategy after realistic costs by rejecting range-bound and adverse-regime
entries without removing the relatively few large trends that produce trend-following profit?

The experiment separates three claims that must not be conflated:

1. whether the fixed breakout has positive development expectancy;
2. whether the online state contains forward return information by itself; and
3. whether requiring a positive state improves the identical breakout implementation.

Breakout and trend are one directional family here, not independent diversification. A
long/flat result may be risk-managed BTC beta rather than market-neutral alpha; attribution
and buy-and-hold comparison remain mandatory.

## Frozen breakout control

At a completed UTC four-hour close, an upside breakout occurs only when that close exceeds
the maximum high of the preceding 120 contiguous four-hour bars. Execution is attempted at
the next five-minute open. A position exits at the first of:

- a 4% protective stop, resolved conservatively from five-minute OHLC;
- the end of an accepted source segment;
- 14 elapsed days; or
- a completed four-hour close below the minimum low of the previous 60 four-hour bars.

The account allocates 10% of current equity, permits one position, one entry decision per
UTC day, and four per rolling seven days. This keeps planned loss below 0.5% of account
equity even under the severe 80 bps round-trip scenario before unplanned stop-gap risk.

## Frozen online regime detector

The detector is Bayesian Online Change-Point Detection with a Gaussian return observation
and Normal-Inverse-Gamma posterior. It consumes complete UTC daily log returns and exposes a
state only when that daily bar has closed. It never uses retrospectively smoothed states.

- Constant hazard: expected 90-day run.
- Maximum retained run length: 365 days.
- Neutral prior mean; prior variance estimated only from complete pre-2019 days.
- Minimum MAP run: 10 daily observations.
- Positive state: MAP-run posterior drift z-score at least 0.75 and change probability no
  greater than 0.50.
- Negative state: posterior drift z-score at most −0.75.
- Everything else: uncertain, which fails flat for new entries.

The primary candidate changes only the breakout entry gate: the latest available daily
state must be positive. Its exits are identical to the ungated breakout. This makes the
incremental regime contribution measurable rather than allowing a different exit system to
hide the comparison.

## Validation

The accepted 2017–2025 five-minute dataset is the only permitted input. Pre-2019 complete
days calibrate prior variance; evaluation is 2019–2025. The January–July 2026 partition is
sealed and may not be read unless every development gate passes.

The primary candidate is tested at 30, 40, and 80 bps round trip against flat, segmented
buy-and-hold, the ungated breakout, and a regime-only diagnostic. A separate causal
information test compares non-overlapping next-seven-day returns in positive versus
non-positive states. Confidence intervals resample UTC months, and all 12 predeclared
one-factor perturbations are reported without selecting a winner.

The regime layer must improve Calmar by at least 25%, retain at least 80% of a positive
breakout CAGR, improve mean trade expectancy, show standalone forward-state information,
survive severe cost, and satisfy every other gate in the machine-readable contract. A
visually plausible bull/bear chart is not evidence.

## LLM and L2 boundaries

No LLM is used. A future LLM may classify timestamp-safe event risk or veto an entry only
after the deterministic candidate passes; it may not size positions or manufacture
historical regime labels. The active L2 capture continues in the background and partial
data remain prohibited. L2 is a later incremental execution/adverse-selection test, not the
base trend strategy.

Research basis:

- Adams and MacKay, [Bayesian Online Changepoint Detection](https://arxiv.org/abs/0710.3742)
- Le and Ruthbah, [Trend-following Strategies for Crypto Investors](https://www.monash.edu/__data/assets/pdf_file/0011/3744821/Trend-following-Strategies-for-Crypto-Investors.pdf)
- Chaim and Laurini, [Bayesian change point analysis of Bitcoin returns](https://doi.org/10.1016/j.frl.2018.03.018)
