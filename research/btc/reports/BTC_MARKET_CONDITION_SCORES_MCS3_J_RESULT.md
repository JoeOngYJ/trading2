# BTC market-condition scores MCS3-J result

Experiment: `btc-market-condition-scores-mcs3-j-v1`  
Disposition: **rejected**  
Evidence role: offline jump/change information test only  
Evaluation: 2019-01-01 through 2025-12-31; 2026 remained inaccessible

## Frozen question

Does a fixed-lambda (`0.94`) EWMA of completed four-hour dominant-discontinuity events and
jump shares forecast the next four-hour event and intensity better than a causal rolling
180-block Jeffreys-prevalence and mean-intensity control? The event is the preregistered
`jump_share >= 0.50` estimator proxy. It is not a formal structural-jump classification.

## Primary result

The candidate is rejected. It was worse than the control on every primary comparative loss.

| Primary four-hour measure | Candidate | Control |
|---|---:|---:|
| Average precision | 0.013570 | 0.015547 |
| Brier loss | 0.008304 | 0.008102 |
| Log loss | 0.063402 | 0.046138 |
| Intensity MSE | 0.013082 | 0.012910 |
| Intensity MAE | 0.087373 | 0.087204 |

There were 12,118 common evaluation rows, 99 events (0.8170% prevalence), 11,675.81
effective observations and 78.99% calendar coverage. The candidate mean probability of
0.8399% lay inside the event-fraction Wilson interval and calibration ECE was 0.00871, but
calibration of the unconditional level does not offset worse forecast ranking and proper losses.
The event-count gate missed by one, and 2024/2025 had only four/five events, but the rejection
does not depend on those near-threshold counts.

The exact-seed month-block 95% intervals for control-minus-candidate improvement were wholly
negative:

- Brier: `[-0.000288, -0.000121]`
- Log loss: `[-0.020257, -0.010493]`
- Intensity MSE: `[-0.000244, -0.000064]`
- Top-minus-bottom probability-quintile event-rate stability: `[-0.046092, -0.004454]`

All seven annual Brier, log-loss and intensity-MSE improvements were negative, as were all
seven leave-one-year-out comparisons. Removing each metric's best three months still left
negative improvements. Although realized mean intensity increased monotonically across the
candidate intensity quartiles, that descriptive ordering did not beat the rolling control.
The secondary one-day diagnostic was also worse on AP, Brier, log loss, intensity MSE and MAE
and cannot rescue the primary result.

## Integrity and boundary checks

- Exact four-hour blocks used 48 contiguous five-minute close-to-close returns plus the
  contiguous prior close; gaps and segment crossings failed closed.
- Candidate and control forecasts were made only after the current complete block, and target
  observations did not affect forecast values.
- The stored forecast `source_digest` binds both history and the later target and is therefore
  an evaluation-record digest, not a decision-time feature-lineage digest.
- Twelve focused tests and 35 adjacent jump/volatility/downside regressions passed.
- A second run reproduced measurements, forecasts, report and manifest byte for byte.
- No strategy, position, cost, PnL, risk cap, order, 2026 data, partial OB0 data, network client
  or protected service was used.

## Decision

Do not tune this experiment ID and do not map the score to a cap or strategy. MCS3-J adds no
accepted market-condition score. MCS4 panel/cap construction is not permitted because MCS3-P,
MCS3-R, MCS3-D and MCS3-J are all rejected. A later carry-economics score (MCS3-C) would require
its own readiness audit and frozen contract; otherwise the current score-panel branch should
stop. Accepted strategy arms remain empty and every actionable route remains `no_trade`.
