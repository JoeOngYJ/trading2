# BTC market-condition score research program

Program ID: `btc-market-condition-scores-v1`  
Status: **planned; no score experiment active**  
Actionable arm: `no_trade`

## Decision

Represent the BTC market with a vector of causal, target-specific forecasts rather than one
`bull`/`bear`/`sideways` label or one opaque composite score. A completed observation may be
simultaneously persistent, volatile, jump-prone, illiquid and crowded. Those facts have different
targets and different permissible uses.

The scores do not constitute strategies. Each must first demonstrate standalone out-of-sample
information about its own target. A later strategy must pass without conditioning before any score
is allowed to modify it. A score may not rescue a rejected strategy, and multiple moving-average
or breakout speeds remain one trend family.

No stage authorizes production signals, orders, credentials, live capital, access to protected
services, inspection of partial OB0 data, or use of a sealed/ineligible 2026 partition.

## Score map

| Axis | What it forecasts | Initial benchmark | Primary evidence metric | Permitted later use |
|---|---|---|---|---|
| Persistence | Whether the sign or directional efficiency of a completed move persists over a fixed future horizon | past signed return scaled by past-only volatility | HAC slope, rank IC and monotonic forward-return buckets | Condition a separately accepted trend strategy |
| Reversion | Whether a completed displacement subsequently unwinds | causal standardized displacement with a matched no-displacement control | signed reversal magnitude, matched-cohort interval and net break-even cost | Condition a separately accepted mean-reversion strategy |
| Volatility | Future one- and seven-day realized variance | frozen close-return EWMA | QLIKE, MSE, coverage and calibration | Downward-only sizing; never direction |
| Downside/tail | Future negative semivariance and tail loss | rolling past-only historical tail estimator | quantile loss, exceedance calibration and joint VaR/ES loss | Downward-only risk cap or protective de-risking |
| Jump/change | Future jump occurrence or discontinuous variation | rolling past-only jump frequency/intensity | Brier/log loss, calibration and precision-recall against prevalence | Four-hour shock cap; never automatic re-leveraging |
| Liquidity/cost | Future protected-fill availability and execution cost | candle/trade price-impact and high-low spread proxies | error versus accepted quote/L2 costs, coverage and stale/gap failures | Entry expiry, cost budget or downward-only cap |
| Carry | Future matched spot/perpetual net carry, not BTC direction | completed funding and current basis after frozen costs | net carry error, calibration, margin stress and matched always-on control | A separately accepted delta-neutral carry strategy |
| Implied risk | Future realized risk relative to option-implied risk | DVOL only after full source qualification | forecast loss, calibration and incremental value over EWMA | Optional risk forecast; no option strategy implied |
| On-chain flow | A precisely timestamped future return or risk target | none | unavailable until point-in-time source semantics pass | Optional; absent rather than imputed |

Persistence and reversion are not complements. A low persistence score is not evidence of
reversion. Volatility, downside, jump and liquidity are risk or implementation forecasts, not
alpha scores. Carry opportunity and directional crowding are also separate hypotheses; the
rejected absolute crowding experiment is not a carry score.

## How a score is evaluated

Every score output records instrument, axis, horizon, observation time, availability time, expiry,
fit cutoff, point estimate or probability, interval, confidence, unknown reason, evidence status
and lineage digests. Missing, future-dependent, stale, cross-segment or insufficient-history input
produces `unknown`.

There is no universal F1 target. Continuous forecasts use target-appropriate loss, rank
information, calibration, monotonic buckets and month-block uncertainty. Rare binary jump events
use Brier/log loss, calibration and precision-recall relative to event prevalence; F1 may be a
secondary threshold diagnostic only after the action threshold is frozen. Economic value is
tested later and never substitutes for standalone forecast evidence.

## Stages

### MCS0 — program freeze

This document and its machine-readable contract are planning infrastructure only. Record the
score meanings, boundaries, dependencies, existing rejected families and context protocol. Do not
load market values, fit a score, select a strategy or compute PnL.

Pass condition: the plan is checksummed, the focused context validates, no experiment is active,
zero strategy arms are accepted and the actionable arm remains `no_trade`.

### MCS1 — causal score observation ledger

Build an inventory of already accepted, checksummed BTC inputs and declare exactly which score
axes each can support. Reuse the segment-aware 5-minute, one-hour, four-hour and daily ledgers;
do not copy their market values into a new dataset unnecessarily. Add a generic immutable
`MarketConditionObservation` contract with point-in-time timestamps and lineage.

This stage reads schemas, timestamps, coverage and checksums only. It produces a coverage matrix
and explicit blocked statuses:

- persistence, reversion, volatility, downside and jump may use accepted candle ledgers;
- carry may use accepted completed funding, spot, perpetual, mark and index inputs, while exact
  historical economics remain a strategy-level constraint;
- liquidity remains proxy-only until independent OB1 acceptance;
- implied risk remains blocked on full DVOL source qualification;
- retrospective on-chain flow remains absent unless a separate source pilot proves point-in-time
  semantics.

### MCS2 — score contracts and pure primitives

Implement canonical score serialization, checksums, stale/unknown behavior, horizon separation and
synthetic-only formula tests. Implement only past-window primitives needed by later experiments:

- volatility-scaled return and directional efficiency;
- variance-ratio/autocovariance diagnostics;
- standardized displacement;
- realized variance and positive/negative semivariance;
- bipower variation and non-negative jump variation;
- low-frequency price-impact/spread proxies; and
- completed funding and basis transforms.

Do not choose thresholds from BTC outcomes and do not combine the primitives into a master score.
Synthetic tests must reject naive/non-UTC timestamps, reversed availability, future windows,
segment crossings, invalid probabilities, insufficient history and duplicate axis/horizon keys.

### MCS3 — standalone score experiments, one packet at a time

Each substage is a separate experiment ID, frozen before output, and small enough for one session:
one contract, one runner/module change, one focused test file, one report and one manifest. Only one
substage may be active.

1. `MCS3-P` persistence: predeclare 4h, 1d and 7d targets, a simple lagged-return benchmark,
   chronology, HAC/block inference and monotonicity gates. It describes trend opportunity; it does
   not reopen the rejected SMA or breakout.
2. `MCS3-R` reversion: predeclare completed displacement events, matched controls, non-overlapping
   horizons and cost break-even gates. It must establish an unwind mechanism independently; it is
   not `-persistence`.
3. `MCS3-D` downside/tail: forecast negative semivariance and joint VaR/ES against a past-only
   historical benchmark. It can become a risk cap only after coverage and calibration pass.
4. `MCS3-J` jump/change: construct current realized jump measures from completed 5-minute returns
   and forecast future jump/tail events against rolling prevalence. Current jump detection and
   future jump prediction must be reported separately.
5. `MCS3-C` carry: only after a new contract separates expected net carry from directional
   crowding and preserves the rejected carry-v1 parameters. It must include collateral, funding,
   basis, fees and margin stress; it cannot tune the rejected threshold strategy.
6. `MCS3-L`, `MCS3-I` and `MCS3-O` remain blocked/optional for liquidity, implied risk and on-chain
   flow until their source gates pass.

Every substage reports coverage by year, dependence-adjusted effective observations, chronological
walk-forward loss, paired month-block intervals, leave-one-year-out stability, score-bucket
monotonicity, calibration where applicable and a deterministic replay. A failed score remains a
control; changing target, horizon, feature, threshold or source requires a new ID.

### MCS4 — condition panel, no universal label

Combine only individually accepted score observations into a time-aligned `MarketConditionPanel`.
The panel preserves every axis value, confidence, horizon, expiry and unknown reason. It does not
average axes, vote on a regime label or map anything to a position. Correlation and disagreement
are diagnostics, not reasons to discard an inconvenient score.

Pass condition: deterministic joins, no future availability, no implicit filling across gaps,
explicit unknown axes and byte-identical replay.

### MCS5 — one new strategy family

Freeze one economically explained strategy hypothesis using only an appropriate accepted data
source. Freeze its unconditioned form and its possible score-conditioned form at the same time,
but evaluate the unconditioned strategy first under the canonical scorecard and 30/40/80 bps cost
grid. The mechanism must beat flat, buy-and-hold, a simple baseline and timestamp/exposure-matched
controls with uncertainty and concentration gates.

If the unconditioned strategy fails, reject it and do not run the conditioned form. This is the
critical protection against using a score to rescue a weak strategy.

### MCS6 — paired conditional-value test

Only for a standalone strategy that passed MCS5, compare the exact same strategy with and without
one predeclared accepted score. Keep entries, exits, risk budget and costs aligned except for the
frozen conditioning action. Attribute the difference to skipped trades, reduced exposure, costs
and tail events.

Require positive incremental net value with a paired block interval, no increase in exposure,
tail-risk improvement appropriate to the score, robustness to the severe cost scenario, and no
dependence on the best three months. A risk score can pass by reducing tail loss while retaining a
predeclared share of return; it is not credited with alpha.

### MCS7 — limited score interaction

Test interaction only after at least two scores independently pass and one strategy passes both
standalone and single-score conditioning. Freeze one simple monotone rule or one regularized model;
do not run an unrestricted interaction grid. Compare it with each single-score version and use
nested chronological training, embargo and a multiple-trial penalty.

### MCS8 — second strategy and counterfactual routing

Repeat MCS5–MCS7 for a materially distinct strategy family. Breakout, moving-average and related
price-trend speeds count as one family. Router work begins only when two distinct strategies have
independently passed. Until then, and throughout counterfactual routing research,
`actionable_arm_id` remains `no_trade`.

### MCS9 — prospective observer and promotion review

After all models, score mappings, costs and gates are frozen, collect genuinely prospective
evidence. Prior inspection makes legacy 2026 data ineligible as a clean holdout where existing
contracts say so. Observe score availability, calibration decay, conditioned-versus-unconditioned
decisions, costs, fills and risk reductions. Live integration requires a separate mandate and
explicit approval.

## Context-window protocol

Each implementation session is intentionally bounded:

1. Read `AGENTS.md`, the four mandatory research documents, this program, the focused `INDEX.json`
   and `HANDOFF.md`.
2. Load only the active substage contract, the exact input manifest it binds and the immediately
   preceding result manifest. Do not load every historical report into chat.
3. Work on one substage and one conceptual change. The normal packet is at most one contract, one
   implementation module or runner, one focused test file, one result and one evidence manifest.
4. Stop at the frozen gate. Never inspect a later result to revise the current ID.
5. End by appending one decision, refreshing the concise handoff and focused index checksums, and
   running the context validator plus focused tests.

Detailed outputs live in per-experiment artifacts. `RESEARCH_TRACKER.md` receives only a concise
disposition and links. This keeps subsequent sessions reproducible without depending on chat
history or repeatedly loading large result tables.

## Recommended next packets

The next implementation request should activate only `MCS1`. If it passes, proceed in separate
requests with `MCS2`, `MCS3-P`, `MCS3-R`, `MCS3-D` and `MCS3-J`. Volatility already has the frozen
EWMA benchmark; HAR remains rejected on coverage and should not displace these packets. Liquidity,
DVOL and on-chain work stay asynchronous and cannot block the price-ledger score foundation.

No data purchase is required for MCS1 through MCS3-J.

## Research basis

- Lo and MacKinlay's variance-ratio framework compares return variance at different sampling
  frequencies, but rejection of a random walk does not by itself prove mean reversion:
  <https://www.mit.edu/~alo/Papers/lo-mackinlay-88.html>.
- Moskowitz, Ooi and Pedersen document time-series momentum over fixed horizons, with partial
  longer-horizon reversal: <https://fairmodel.econ.yale.edu/ec439/mosk.pdf>.
- BTC-specific evidence reports both intraday momentum and reversal whose prevalence changes with
  jumps and liquidity: <https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4080253>.
- Barndorff-Nielsen and Shephard show how realized bipower variation can separate continuous and
  jump variation: <https://papers.ssrn.com/sol3/papers.cfm?abstract_id=821712>.
- Patton and Sheppard show the distinct forecasting content of negative realized semivariance and
  signed jumps: <https://public.econ.duke.edu/~ap172/Patton_Sheppard_good_bad_vol_Nov13_ALL.pdf>.
- Amihud's low-frequency price-impact proxy is absolute return divided by dollar volume; it is a
  rough proxy, not a substitute for quoted or effective spread:
  <https://www.cis.upenn.edu/~mkearns/finread/amihud.pdf>.
- Corwin and Schultz derive a high-low spread estimator while explicitly separating range
  variance from spread: <https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.2012.01729.x>.
- BIS documents that BTC carry is a spot/futures basis mechanism driven partly by leveraged demand
  and limits to arbitrage: <https://www.bis.org/publ/work1087.htm>.

