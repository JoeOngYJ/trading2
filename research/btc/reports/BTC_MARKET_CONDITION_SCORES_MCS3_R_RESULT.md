# BTC market-condition scores MCS3-R result

Experiment ID: `btc-market-condition-scores-mcs3-r-v1`  
Decision: **rejected — symmetric completed-displacement unwind was not stable or incremental**  
Strategy, position, execution, cost or PnL evidence: **none**  
Accepted strategy arms: **none**  
Actionable arm: `no_trade`

## Frozen question

Does a completed BTC 24-hour move at least two causal standard deviations from its preceding
126-observation displacement distribution unwind over the next day? The test required positive
direction-adjusted forward return for both upward and downward events, improvement over a
previously completed same-direction quiet observation matched on past realized variance, stable
calendar-year evidence, non-overlapping targets and enough gross movement to clear the frozen
30/40/80 bps friction references.

This is a displacement-event test, not the negative of MCS3-P persistence. It defines no entry,
exit, position, order, fill, leverage or PnL.

## Primary one-day result

The cohort contained 300 non-overlapping events, with at least 24 in every evaluation year. Event
direction was balanced: 48.33% followed negative displacements and 51.67% followed positive
displacements. Those sample gates passed, but the information and economic gates did not:

- Pooled signed reversal was only `12.46 bps`, below the frozen `80 bps` point-estimate gate.
- The equal-month estimate was `-1.74 bps`; its exact-seed month-block 95% interval was
  `[-57.37, 53.97] bps`, far below the required 30 bps lower bound.
- Negative displacements rebounded by `52.35 bps` on average, but positive displacements continued
  rather than unwound: their mean signed reversal was `-24.86 bps`. The frozen requirement that
  both directions revert therefore failed.
- Excluding the best three months changed mean signed reversal to `-5.68 bps`.
- Only four of seven annual event means were positive. Only two of seven annual matched deltas
  were positive, versus five required for each.
- 206 events received strict historical controls, or 68.67%, below the frozen 80% overall gate.
  The equal-month matched event-minus-control estimate was `-8.45 bps`, with interval
  `[-114.20, 104.05] bps`; the candidate did not beat quiet matched observations.

Feature coverage was `83.57%`, below the frozen 85% overall gate. The 2019, 2020 and 2021 annual
fractions were 66.24%, 66.65% and 61.80%, below 75%, because the 132-bar causal warm-up resets at
every accepted source segment. Bridging those gaps or relaxing the reference window after seeing
the result is prohibited.

The secondary horizons provide no rescue. Four-hour pooled signed reversal was `-2.75 bps`; the
seven-day value was `-81.04 bps`. Their month-block intervals crossed zero, and matched deltas were
negative on an equal-month basis.

## Interpretation

The symmetric claim is false for this frozen construction. Large completed upward moves tended to
continue, while large completed downward moves showed a pooled rebound. That asymmetry is an
exploratory observation, not an accepted score: selecting only the favorable side now would be a
new hypothesis chosen after results. It may be tested later only under a new experiment ID and
fresh evidence; it cannot rescue this experiment or any rejected strategy.

Do not tune the z threshold, 24-hour displacement, 21-day reference, match rule or target horizons
under this ID. Preserve the score as a rejected control. Low persistence also remains distinct
from reversion.

## Verification

- Seven focused tests cover the causal formula, reference exclusion, segment reset, non-overlap,
  strict historical matching, deterministic bootstrap and import isolation.
- The isolated replay produced byte-identical `report.json` and `events.jsonl.gz` files.
- Independent ledger checks confirm no overlapping event targets, no reused controls, control
  targets available strictly before their events, and the frozen variance-ratio caliper.
- No 2026 row, partial OB0 input, network, database, NATS, Freqtrade, exchange, protected service,
  production signal, order, position, cost calculation or PnL was accessed or created.

## Next permitted action

Freeze MCS3-D before reading any downside/tail outcome. It must forecast future negative
semivariance and tail loss against a past-only historical benchmark. It may become only a
downward-risk cap after independent coverage and calibration gates pass; it cannot change trade
direction or rescue a rejected strategy.
