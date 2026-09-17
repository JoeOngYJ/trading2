# Proposed corrected breakout historical claim-resolution contract

Proposed identity: `btc-breakout-corrected-claim-resolution-v1`  
Proposal date: 2026-09-12  
State: **PROPOSED — NOT AUTHORIZED FOR EXECUTION**  
Evidence class: **historical claim resolution on consumed development data**.

This proposal was written only after the parent repair process confirmed that both new clean
legacy builds match all ten authoritative S1 outputs and each other byte for byte. The repair
does not accept breakout, supply independent evidence, or authorize this proposal. ChatGPT
must review and explicitly authorize a frozen version before historical corrected execution.
No performance result, signal count from a corrected run, or control result was calculated
while drafting it. The existing reviewed disposition remains C: no supported edge.

## 1. Question, hypothesis and scope

When a completed UTC four-hour BTC/USDT close is strictly above the maximum high of its prior
120 complete contiguous four-hour bars, known at that close boundary T, the frozen hypothesis
expects continuation that can support positive net expectancy with the original 60-bar exit
channel, 4% fixed stop and 14-day maximum hold. The proposed explanation is persistent price
discovery/directional participation. The identity and constraint of participants causing that
continuation, and this system's capture advantage, remain **UNRESOLVED**. Ordinary BTC exposure,
positive skew/risk bearing, and researcher selection are competing explanations.

This tests the **ungated fixed breakout**, not the rejected BOCPD filter. It adds no indicator,
feature, session rule, model, parameter sensitivity, optimization or sizing overlay. A SURVIVES
decision would justify considering separate independent confirmation of a **coverage-conditioned
historical claim**. It would establish neither causal mechanism nor accepted alpha.

The primary estimand is mean return on allocated budget for every sequentially filled entry leg
whose complete maximum-holding execution path is identifiable under the metadata-only rule in
section 4. It is not the mean of whatever trades happen to close before a gap. The full 2019–2025
continuous-account return and expectancy remain **UNKNOWN** with the present missing coverage.

## 2. Frozen lineage and runtime prerequisite

Use only these unchanged source/data contracts and their qualified reproduction environment:

| Object | SHA-256 |
| --- | --- |
| Frozen S1 contract, `config/experiments/btc-regime-routing-s1-ledger-v1.json` | `9a2000c6f2685a9ae878a024fb3105e7dac8ae968a9d1216b66d8cf3b7122f1d` |
| Authorized compressed development CSV.gz | `316e5789d4b49f79a0adfdd90f0e98c26dd2658060c49fe2366c91dffa2024e8` |
| Authorized development manifest | `506b8839a42fd3c44687020e85e995181a4033e5dbacedfcdc382801d8da18ae` |
| Legacy breakout source | `973280749d3316a055be4b5e99d0234a5cd1b1eff39ca61c0bfb2d2b320bbf61` |
| Ledger/aggregation source | `6b36311efa28c8f58dec1459df0ee146a9a51efd5ff6504fe5531ea0de00e75e` |
| Reviewed corrected breakout candidate | `6d2e796cc61b41ef0311a13327d1bdd63694cc4ce4a2a57fb72cc99ff3c322fc` |
| Reviewed synthetic correction contract | `9f22365f9a5b96e0eec157cb8b183631f98a5f1978462af13e065dfd56687737` |
| Frozen execution scenario configuration | `a020cb07780e88b60fffd4c6e1b205922f0b815f033a4676dd422a7038538f36` |

Resolve paths from S1's exact `allowed_dataset_path` and `development_manifest_path`; do not
substitute other exports. The declared input is 878,985 five-minute rows, 34 source segments,
2017-08-17T04:00:00Z through 2026-01-01T00:00:00Z exclusive. The evaluation boundary remains
2019-01-01T00:00:00Z through 2026-01-01T00:00:00Z exclusive. Pre-2019 data supplies already
permitted same-segment warm-up only. No 2026 row is allowed.

The repair report/runtime addendum, complete project import hashes, interpreter executable
hash, standard-library/dependency identities, source topology hash and approved version of
this document must be copied into the eventual run manifest before loading historical prices.
No implementation change to `sum`, OHLCV serialization, compression, forecast hashes or lineage
is permitted. The archive-compatible runtime does not identify the unknown August binary.

The current synthetic `simulate` stops on the first gap and has no multi-cohort reporting
contract. Any later cohort adapter is new **evidence plumbing**, requiring source hashing and
synthetic qualification against this document before market execution; do not pretend those
reporting semantics already exist in the reviewed candidate. Preserve the original files.

## 3. Exact signal, execution and cost conventions

Four-hour bars start on the UTC 00/04/08/12/16/20 grid, comprise exactly 48 contiguous accepted
five-minute children from one segment, and become available at their close boundary. Incomplete
bars are discarded without imputation; channel state resets at each source segment. Preserve
the original aggregator and feature construction. Daily bars are not an additional signal.

Entry uses current close strictly greater than the maximum high of the **previous** 120
same-segment complete bars; exit channel uses current close strictly below the minimum low of
the **previous** 60. The current bar is excluded from both prior channels. At least 121 total
complete bars are needed for the first entry decision. Keep the source forecast convention
`decision_ms > evaluation_start_ms`; entries also require `decision_ms < evaluation_end_ms`.

Entry occurs only at the exact next source open with `open_ms == decision_ms`, in the same
segment. This inherited same-boundary availability/fill is an idealized zero-latency convention,
not a proven sub-candle executable delay. Missing exact next open expires the entry; do not
search forward for a favorable or merely available price. No new timing sensitivity is run.

Preserve BTC/USDT spot long/flat, 1,000 initial accounting units per cohort, 10% of current cash
at a flat entry, one position, no borrowing/leverage, fixed stop at **entry reference open × .96**,
and maximum hold exactly 14 elapsed days. Preserve one admitted entry decision per UTC day and
four per rolling seven days: timestamps exactly seven days old still count; an admitted decision
consumes cadence before price-cap expiry; busy/missing-next-open decisions do not. No new entry
on the same source row as the previous exit. Do not add daily/drawdown stops absent from S1.

An **admitted entry decision** is a proposal that passes the frozen cadence check; it can
subsequently expire at the price cap. A **filled entry leg** is an executed entry with strictly
positive quantity and committed budget. Only filled entry legs enter trade-return means,
entry-budget sums and censor bounds. Expired/rejected/busy attempts remain separately counted;
they are not zero-return trades and do not enter the trade-mean denominator.

Qualify each row before processing it. For an existing position, chronological precedence is:

1. Open at/below an already active stop: protective exit at that observed open.
2. Previously scheduled channel exit at that open.
3. Maximum-holding exit at that open; a scheduled channel exit wins an exact tie.
4. Otherwise a later intrabar low at/below the stop: exit at the stop reference.

A new opening entry activates its protection immediately afterward; a later low in that same
candle can stop it. An opening price jump through the stop fills at the worse opening price,
with exit friction. This is distinct from a **missing source interval**, whose path/fills are
unknown and cannot be imputed. Opening fills have exact timestamps. Intrabar fills have unknown
event time in `(bar.open_ms, bar.close_ms]`, observed at close, and holding-time bounds.
The intrabar reference-at-stop convention is the reviewed candle-model assumption, not proof
that a stop could fill at that price: the five-minute OHLC data cannot resolve a jump through
the level within the candle, available depth, latency or partial quantity. The frozen friction
grid does not supply a proven bound on those unobserved losses. Any SURVIVES claim remains
conditional on this execution model and requires later practical fill qualification.

At a reached predeclared global endpoint, inventory is marked at the closing boundary without
sale or exit fee. An unexpected source boundary retains cash, inventory and last valid valuation;
it does not liquidate, claim cash proceeds, or use the next segment to determine a prior exit.

| Case | Fee/side | Implicit/side | Combined cost c/side | Entry reference cap |
| --- | ---: | ---: | ---: | ---: |
| Primary | 10 bps | 5 bps | .0015 | 10 bps |
| Stress | 10 bps | 10 bps | .0020 | 20 bps |
| Severe | 20 bps | 20 bps | .0040 | 50 bps |

Expire when `entry.open > signal.close × (1 + cap/10000)`; equality passes. Preserve
`quantity = budget/[entry.open×(1+c)]` and `proceeds = quantity×exit.reference×(1-c)`.
No second fee debit, maker fill, changed fee tier, or cost reduction is allowed. Different caps
can admit different trades; separate admission effects from fixed-reference cost effects.

## 4. Proposed source-cohort and censoring convention

This section is a **new proposed analysis convention requiring explicit review**, not an
authorization inferred from synthetic gap tests.

Use every one of the 23 evaluation-overlapping segments already enumerated by Stage 3A metadata.
Do not select segments based on strategy results, trend, length, volatility or returns. Each is
a separate flat-start counterfactual account, with its own 1,000 units and empty cadence state
at the first observed evaluation row. For the segment crossing 2019-01-01, retain only its
permitted pre-evaluation channel history. For later segments, reset histories and wait for
the full original warm-up. These separate starting accounts are research cohorts, **not** an
executable restart of inventory from the previous account.

Each cohort processes all otherwise eligible source rows/entry decisions. At its first unknown
boundary, preserve its open inventory and stop. Do not turn a known future segment end into a
prior liquidation. Cohort starts/ends and the primary analysis mask are fixed from the existing
timestamp topology **before** reading corrected results.

Define the common analysis eligibility mask M(T), using identity/time structure only:

- T is an exact potential next-open entry timestamp after a complete, warmed-up decision bar,
  strictly after the global evaluation start and before its exclusive end.
- The entire source interval from T through the **opening row at T + 14 days** exists,
  continuously in the same segment and strictly inside the allowed input/evaluation rows.
- Thus `T + 14d < min(segment_last_close, evaluation_end)` on this complete five-minute grid.
  Equality with the last close does not supply the opening row needed for a maximum-hold sale.

M is an **analysis mask only**. It must never suppress a trading decision, create an exit,
alter cash/cadence, or reveal a future gap to the simulator. Process both M=true and M=false
entries in chronological order. Primary trade expectancy includes **all** filled M=true entry
legs, irrespective of outcome/exit reason; each has an observable maximum-hold exit.
Unexpected non-resolution of an M=true position is an implementation/data failure, not an
observation to discard. This identifies conditional expectancy where a complete path exists;
it does not estimate expectancy during source outages or missing boundary windows.

Retain M=false trades and open legs in a separate compulsory boundary table. Report counts,
entry-budget sums, observed closed returns, unresolved quantity/cash, last-valid marks, entry
year/month/segment and exit reason if known. Do not replace an open leg by a zero return or
silently drop it. For any unfinished long spot leg, `r >= -1` is a valid eventual return-on-
allocated-budget lower bound under this no-leverage model. Report the all-entry lower bound
`[sum(known net leg returns) - number(unresolved legs)] / number(all entries)`, and the analogous
budget-weighted bound, `[sum(B_i*r_i for known legs) - sum(B_i for unresolved legs)]/sum(B_i
for all filled legs)`. Here all entries means all filled legs, not admitted-but-expired decisions.
These bounds concern the existing filled legs only; they cannot bound unobserved future
entries or provide a continuous-account return.

For relative performance, candidate lower bounds minus control lower bounds are **not**
conservative. An unresolved long control has no finite upper return bound from this dataset.
If such a comparison depends on unresolved control inventory, its full-cohort relative effect
is **UNKNOWN**. The primary comparison uses the same M mask for all arms to avoid this defect.

Report M coverage versus all metadata-eligible next-open opportunities by segment and year,
plus the proportion of actual entry count/budget lying outside M. This is observed-coverage
conditioning and may be market-state-selected; no missing-at-random claim is made. SURVIVES can
refer only to the M-conditioned claim. The disposition for the **full frozen continuous strategy**
remains **AMBIGUOUS / UNIDENTIFIABLE** under the present coverage even if the conditional claim
SURVIVES. M is never an actionable future-coverage filter and does not define a new deployable
strategy. Any materially different boundary evidence is a stated limitation, not an invitation
to change M after observing results.

Do not multiply cohort returns, carry cash between accounts, or insert flat returns in gaps.
Full 2019–2025 total return, CAGR, Sharpe, drawdown and continuous-system exposure are **N/A /
UNKNOWN**. Per-cohort observed-prefix valuation return/drawdown may be reported with explicit
valid timestamps. Those marks are not realized final cash. The last cohort can reach the true
predeclared endpoint and retain terminal marked inventory without an exit fee.

## 5. Attribution and controls

### Raw predictive information, without stop or sizing rules

For every warmed-up potential decision with M=true, define X as the frozen breakout predicate
and Y as `open(T+14d)/open(T)-1`. This is a fixed 14-day raw continuation diagnostic, not a new
trading exit. For each X=true observation compare Y with the mean Y of X=false observations
in the **same source cohort/segment, UTC calendar month and four-hour clock slot**. Matching
uses no future return,
new feature or volatility estimator. Compute event-weighted mean/median Y, distribution and
hit rate; primary incremental statistic is the event-weighted mean of those paired differences.

If a stratum has no eligible nonbreakout observation, retain its event and mark its comparison
unavailable; do not widen the matching definition. Report unmatched counts. Primary predictive
comparison requires at least 90% of X=true observations matched; otherwise AMBIGUOUS. All event
overlap is retained and described; uncertainty uses the common calendar-block method below.
The 14-day diagnostic cannot by itself validate adaptive stops/exits or prove participant intent.

### Sequential strategy and simple participation control

Run the corrected frozen candidate independently under all three original cost scenarios.
The primary control uses the identical source cohorts, available four-hour opportunity grid,
warm-up, one-position/cadence, stop, channel exit, maximum hold, cash sizing and scenario-specific
caps/costs. Its sole difference is a **signal-blind entry proposal** at each eligible opportunity.

Freeze control proposal probability `p = 291/15303`, using the already exposed legacy count of
291 breakout conditions and 15,303 forecast rows. This is explicitly consumed-development
frequency calibration for a comparator, not an untouched estimate and not a value to update
after corrected results. Some legacy forecast rows lacked same-segment warm-up; therefore this
matches approximate proposal frequency, not exact fills, calendar exposure or opportunity count.

Generate 199 control schedules, numbered k=1..199, with standard-library
`random.Random(20260903+k)`. For each schedule traverse the full metadata-eligible opportunity
grid in `(decision_ms, segment_id)` order, drawing one uniform random number **before** inspecting
X or outcomes. Propose entry iff the draw is less than p. Draw at every opportunity, including
when the account is busy or the proposal subsequently expires; do not draw only after a fill.
Reuse that schedule under all three cost scenarios and the same M analysis mask. Preserve all
199 schedules/results; there is no best-seed selection or probability sweep.

The primary participation statistic is candidate mean net allocated return minus the mean
of the 199 controls' mean net allocated returns on M=true entries, under primary costs. The
minimum-count rules below prevent an empty control mean being imputed as zero. Report actual
trade counts, turnover, holding periods, exposure and rejected/expired entries for every arm.
Specifically, `mu_B = sum(r_B)/n_B`, `mu_Ck = sum(r_Ck)/n_Ck`, and
`Delta = mu_B - sum(mu_Ck for k=1..199)/199`; n counts **all** M=true filled entry legs,
not only a post-result subset. Express returns/intervals in bps by multiplying fractions
by10,000. Calculate the same ratios from the paired resampled month sums/counts in each draw.
This is a common-opportunity, common-risk-policy participation comparison; it does **not**
claim exact realized exposure matching or independent randomized market evidence.

### Flat, buy/hold and timestamp/exposure diagnostics

- Flat remains cash, with zero return/cost and the same observed timestamps.
- Buy/hold purchases 10% of its own 1,000-unit cohort account at the first observed evaluation
  open, with the scenario's combined entry friction, and holds its fixed quantity. It is
  passive, so it does not invent a prior signal reference for a price cap. Report last-valid
  or true-terminal mark, cash/inventory and drawdown on the same observed row grid. There is
  no boundary sale. This contextual passive-risk benchmark has different duration/tail risk;
  its mark is not a matched realized-trade expectancy.
- Reconstruct each candidate's **exact timestamp/quantity/reference schedule** at zero combined
  friction solely for a fixed-quantity cash reconciliation. Keep the original scenario quantity
  `q = B/[P_entry*(1+c)]` and original committed budget B as the denominator. The frictionless
  cash ledger debits `q*P_entry` and credits `q*P_exit`; it does not recompute quantity. Thus its
  PnL divided by original B is `gross_reference_return/(1+c)`. This differs from unit-notional
  gross reference return `P_exit/P_entry-1`, whose denominator is the frictionless entry value
  `q*P_entry`. Report both denominators explicitly. Frictionless PnL minus actual PnL equals
  `q*c*(P_entry+P_exit)` for a completed leg under this combined-cost model.
  This ex-post diagnostic intentionally uses realized candidate timing; it is neither
  executable signal-blind participation nor evidence of predictive skill. Never select a
  different signal or holding duration to improve it.

### Separation of effects

Report, in order: raw 14-day event effect; corrected M-conditioned gross reference expectancy;
corrected net expectancy; fixed-reference friction difference; cap/admission differences;
compounded account/cash-sizing effects and observed exposure. Exact fixed-reference net return
is `(1+gross_reference_return)*(1-c)/(1+c)-1`, not gross minus nominal round-trip bps.

For legacy correction impact, preserve the archived full S1 results as labelled legacy
development evidence. Compare only common entry timestamps whose required paths satisfy M in
both representations; list unmatched admissions separately. Show changed exit reference,
chronology, reason, duration/interval and unit-budget gross/net return, then distinguish later
sequential busy/cadence changes. Do not present archived whole-history PnL minus a cohort sum as
execution impact. A difference attributable to cohort starts/coverage is a changed estimand,
not a corrected fill. Any additional legacy replay needed for exact common-cohort attribution
must be named in the separately authorized execution plan and use unchanged legacy source.

## 6. Required outputs and uncertainty

Export full source/config/runtime/input/output manifests, actual commands, exit codes, guard
logs, source-qualification counts, opportunity grid/M mask, forecasts, attempted/rejected/
expired/busy entries, trades, intrabar timestamp bounds, cash events, unresolved inventory,
valuation observations, raw event/control assignments and all 199 participation schedules.
Record all failures and undefined quantities rather than silently replacing them.

Freeze the valuation grid as the initial 1,000-unit baseline at each cohort's first evaluation
open, followed by every accepted five-minute close after chronologically processing that row's
events: `E(t) = cash_after_row + quantity_after_row * row.close`. Maximum observed drawdown is
`max_t(1 - E(t)/max_{s<=t} E(s))` on that grid, including the initial baseline. This is observed
close-grid drawdown, not a bound on unobserved intrabar or missing-interval loss. Do not insert
marks across gaps. Report per-cohort valuation return as `last_observed_E/1000 - 1`, explicitly
an observed-prefix mark for truncated cohorts rather than a completed account return.
Time-in-position exposure has lower/upper duration bounds when an intrabar exit time is
unknown; report those bounds rather than backdating it to the bar open. Marked-notional
exposure is `quantity_after_row * row.close / E(t)` on the same observed close grid, with its
observed-time-weighted average separately labelled; no full-calendar exposure is inferred.

For candidate and controls under every cost case, report:

- Entry count, completed count, M=true/M=false count and entry budget, censor count and coverage.
- Gross/net mean and median allocated return, confidence intervals, hit rate, win/loss means,
  profit factor, 5th/1st percentiles, worst trade and worst-five mean (or N/A if insufficient).
- Entry-year/month/segment stability, holding-time bounds, turnover, time-in-position and
  marked-notional/equity exposure. Distinguish time exposure from the 10% entry allocation.
- Per-cohort observed-prefix and true-terminal valuation return/drawdown, with exact coverage;
  pooled unit-budget expectancy and gross/net PnL per sum of entry budgets labelled as such.
- Top-one/top-three trade and top-three positive entry-month shares of positive PnL; report
  denominators, including undefined zero-positive-PnL cases. Recalculate M-conditioned mean
  expectancy after removing the best trade and, separately, the best positive entry month.
- All seven fixed entry-year slices; leave-one-entry-year-out mean expectancy. No selected
  favorable era, segment or alternative instrument. No strategy parameter perturbations.
- Boundary-table outcomes, conservative all-entry candidate bounds and unidentifiable relative
  bounds, alongside complete-path statistics. A favorable interior result cannot erase them.

Trade-distribution statistics use per-filled-leg allocated returns with equal weight per leg;
hit rate is the fraction strictly above zero, with zero returns counted separately. Profit
factor is sum of positive allocated returns divided by the absolute sum of negative allocated
returns; also report the separately labelled cash-PnL analogue. Empirical quantiles use the
same linear interpolation rule specified below. Tail ranking is by allocated return; the
cash-based concentration and best-period removal ranking are defined separately below.

For the primary concentration gate, let `P_m = sum(actual pnl_quote)` over primary-scenario
M=true filled legs assigned to entry month m, using their frozen variable entry budgets.
The month share is `sum(three largest positive P_m)/sum(all positive P_m)`. Trade shares use
the analogous actual positive `pnl_quote` totals. Best trade/month removal uses that same
cash-PnL ranking, then recomputes unit-budget mean expectancy on the remaining legs. Keep
this sizing-dependent concentration diagnostic distinct from mean allocated-return statistics;
do not switch to a more favorable unit-budget ranking. A zero denominator is undefined.
For the severe best-trade removal gate, rank severe-scenario M=true filled legs by their
own actual cash PnL, then recompute severe mean allocated expectancy after removing the
largest. Break tied trade cash-PnL ranks by earliest entry timestamp, then source-segment ID;
break tied month ranks by earliest UTC entry month. These rules also apply to primary ranks.

Use the existing seed 20260903, 10,000 bootstrap draws and two-sided 95% intervals, but freeze
the following **new explicitly proposed block definition**, rather than borrowing the old
trade-quantile label: create 84 entry-month vectors for January 2019 through December 2025,
including zero-count months. A vector retains all candidate/event/control sums and counts
assigned to that month by decision/entry time. Each draw samples 28 starting indices uniformly
from 0..83 and concatenates three consecutive indices modulo84 for each start, yielding 84
sampled months. Resample those same indices for every arm/statistic. Keep trades/events within
their month intact; compute ratio-of-sums means, not a mean of nonempty monthly means.

This three-month circular block bootstrap retains local clustering beyond the 14-day label,
but supplies only descriptive uncertainty on reused observations. It does not reconstruct
alternative price paths, independent cohorts, missing outcomes, or unknown research trials.
Use exact percentile quantiles with sorted samples and linear interpolation at `(n-1)*q`.
Do not redraw undefined samples; report their count. Fewer than 9,900 defined draws for a
required statistic makes that inference AMBIGUOUS. An empty control mean is undefined.

Report the primary-scenario candidate's empirical rank against all 199 primary-scenario
controls with the finite-sample convention
`[1 + count(control_mean >= candidate_mean)]/200`; this is a descriptive random-schedule rank,
not independent validation or a multiple-search-adjusted probability.

## 7. Predeclared decision rules

These are new proposed claim-resolution gates, **not inherited standalone S1 acceptance**.
They emphasize economic margin and identification. They must be accepted before outcomes;
their thresholds may not be adjusted afterward. Engineering or identity failures stop the
run BLOCKED and never become an economic rejection.

Identification/sample adequacy requires: all source/clock/cash/guard checks pass; every M=true
filled leg resolves; at least 30 candidate primary M=true fills represented in at least five entry
years and five source cohorts; at least 30 M=true fills in every one of the 199 primary control
schedules; >=90% raw-event matching; and required bootstrap defined-count >=9,900. These are
minimum screening requirements, not a claim of statistical power or a sufficient independent
sample. Insufficient information yields AMBIGUOUS, with no automatic additional data access.
Any missing denominator, undefined required statistic, or unavailable required confidence
interval also yields AMBIGUOUS; it is never imputed as zero, a failed economic value, or a pass.

**SURVIVES — conditional historical claim only** requires all of:

1. Primary M-conditioned mean net allocated expectancy at least **30 bps**, with its 95% lower
   confidence limit strictly above zero. The 30-bps margin is one additional primary modeled
   round-trip friction allowance; it is a review threshold, not an optimized profit target.
2. Stress and severe M-conditioned mean net allocated expectancy strictly above zero; costs
   and caps are unchanged. Scenario admission differences remain separately disclosed.
3. Primary candidate-minus-participation mean difference has 95% lower limit strictly above
   zero, and candidate rank against the 199 controls is <=.05.
4. Raw matched 14-day predictive difference has 95% lower limit strictly above zero. This is
   supporting continuation evidence, not a stand-alone trading acceptance test.
5. Primary M-conditioned mean expectancy remains positive after dropping the best trade,
   after dropping the best positive entry month, and for every leave-one-entry-year-out
   sample. At least five of seven entry-year means are positive; empty years are not wins.
6. Primary worst-five mean loss and observed-prefix drawdowns are explicitly reported; no
   protective/cash invariant fails. Top-three profitable entry months contribute at most
   50% of positive M-conditioned primary PnL. Severe mean must also remain positive after
   dropping the best trade. These concentration tests cannot replace tail disclosure.

A SURVIVES statement must include the M opportunity/entry/budget coverage and boundary-censor
limits in the same summary. It never asserts full-history viability. If the **known closed**
boundary entries have negative mean, or the all-entry conservative candidate bound is not
positive, state that the broader entry population has not been established; do not silently
generalize the conditional result. An unresolved relative bound remains UNKNOWN.

**REJECTED — the proposed conditional claim is not supported economically** applies after
adequacy passes if the upper 95% limit for primary mean net expectancy is below 30 bps, or
the upper 95% limit for candidate-minus-participation or raw matched continuation is <=0.
Also reject if severe mean expectancy is <=0 **and** its upper 95% limit is <=0. These rules
reject this frozen claim, not all possible trend phenomena, and do not justify retuning it.

**AMBIGUOUS** applies to every other combination: insufficient/selected coverage, inadequate
sample, imprecise economic margin, unresolved superiority, instability/concentration, stress
failure not decisive under uncertainty, or missing inference. A positive total or conditional
mean with an uncertainty interval crossing the required gate is not a pass. Failed SURVIVES
robustness without decisive economic rejection is AMBIGUOUS, not an invitation to search.

## 8. Required implementation checks before any historical result

The separately authorized plan must specify and pass synthetic tests for: unchanged signal
and exit channels; 120/60 warm-up/reset; no same-bar channel look-ahead; exact-open availability;
strict lower/exclusive upper boundary; entry-cap equality/expiry and scenario caps; cadence
admission order and seven-day equality; same-row busy protection; scheduled/max/stop ordering;
intrabar timestamp uncertainty; opening stop gaps; missing-source inventory preservation;
global endpoint valuation; source-prefix invariance; M never altering simulated decisions;
same M membership independent of outcomes; no maximum-hold execution from a closing mark;
per-cohort independence without capital stitching; net/gross/cost/cash reconciliation; and
the distinction between absolute censor lower bounds and unbounded relative control outcomes.

Qualify tests and source hashes without market outcomes first. No profitability caller may be
used as its own oracle. The exact qualified legacy outputs must still pass their ten-file
canonical gate; the reviewed 35 integration and 7 inherited suite results must remain attached.
No new architecture or unrelated test suite is requested.

## 9. Review and stopping boundary

This draft does not execute, activate, or approve the corrected claim resolution. ChatGPT must
approve the coverage-conditioned estimand, cohort starts, M mask, participation calibration,
bootstrap, economic gates and proposed implementation scope as one frozen package. Any changed
choice requires an explicitly new revision before outcomes, retaining this proposal.

If REJECTED, preserve the negative result and stop this frozen claim. If AMBIGUOUS, identify
whether the missing information is source coverage, outcome identification or precision;
do not tune thresholds or consume another sample automatically. If SURVIVES, seek separate
review of a genuinely untouched confirmation design and practical execution qualification.
Only independent confirmation could justify later strategy engineering or allocation work.

No protected 2026, OB0/L2 or service data; no live/paper interaction; no HAR, top-two, ridge,
cash-ETF, funding or new alpha-family work is included.

**PROPOSED ONLY — RETURN FOR CHATGPT REVIEW; NO CORRECTED HISTORICAL PERFORMANCE AUTHORIZED.**
