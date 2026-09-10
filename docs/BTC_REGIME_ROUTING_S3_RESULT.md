# BTC Regime Routing S3 Student-t HMM Result

Experiment ID: `btc-regime-routing-s3-student-t-hmm-v2`  
Decision: **rejected — forward downside-loss separation failed**  
S4 disposition: **skipped — latent-risk branch stopped**  
Promotion evidence: **no**  
Live-trading status: **not authorized**

## Result

S3 fitted the one frozen two-state diagonal Student-t HMM specification using four causal daily
risk-only features, past-only median/MAD scaling, monthly expanding refits, and daily forward
filtering. The first activation contract, v1, was rejected before output because its downside
label and month-block resampling method were not defined precisely enough. The immutable v2
successor changed no feature, model, mapping, cost, threshold, or branch rule; it only completed
those deterministic definitions.

The model produced 84 converged monthly refits and 2,557 known walk-forward state observations.
Canonical labels were stable at every refit. Both hard states exceeded the 15% occupancy floor:
ordinary risk occupied 57.68% and stress risk 42.32%. The path contained 148 out-of-sample
transitions, median ordinary/stress dwell lengths of 12 and 11 days, and a 6.71% one-day-run
fraction. All 67 locked breakout opportunities had a fresh causal state.

## Frozen forward-risk gates

There were 2,402 valid next-seven-day labels. The stress state had higher realized variance by
`0.0056554`; its 95% calendar-month block interval was `[0.0016699, 0.0103558]`, entirely above
zero. That standalone gate passed.

The stress state's next-seven-day downside loss was higher by `0.0043704` (about 0.437 log-return
percentage points), but its frozen 95% month-block interval was `[-0.0054277, 0.0148960]`. Because
the lower bound is below zero, the downside-loss separation gate failed. This is not a near-pass
that may be repaired by changing the label, features, state cutoff, degrees of freedom, persistence,
or bootstrap method under this experiment ID.

The frozen rule required both forward-risk intervals to be strictly positive. The runner
therefore stopped before strategy simulation, cost comparison, overlay PnL, or allocation-parameter
diagnostics. `development_overlay_gate_met` remains false because economics were intentionally not
computed, not because an observed HMM overlay return was negative.

## Branch decision

S4 is not eligible. Its conditional jump model could be built only when both forward-risk
separation gates passed and the HMM failed specifically on transition, dwell, or flicker stability.
Here the HMM passed every stability gate and failed downside-loss separation, so the latent-risk
branch stops. Do not tune this HMM or build the jump model in response.

The broader routing program may continue only with the next separately authorized work permitted
by the program. The fixed breakout remains a development control, and all actionable routing
remains `no_trade`.

## Determinism and safety

An isolated replay under
`artifacts/agent-level-experiment/btc-regime-routing/replays/s3-v2-replay-J55npS/` reproduced all
seven core files byte-for-byte. No sealed-2026 data, partial L2 data, database, NATS, Freqtrade,
container, running service, production signal, order intent, or position path was accessed.

Official evidence is stored under
`artifacts/agent-level-experiment/btc-regime-routing/s3-student-t-hmm-v1/`.
