# BTC Regime-to-Strategy Routing Research Program

Program ID: `btc-regime-strategy-routing-v1`  
Status: **S0 passed; consult the checksummed status registry for the active stage**  
Machine-readable program:
[`../config/research/btc-regime-routing-program-v1.json`](../config/research/btc-regime-routing-program-v1.json)

## Purpose

This program establishes a causal, offline path from BTC risk-state research to eventual
strategy routing. It does not authorize a runtime router. During S0 through S7 every
actionable decision remains `no_trade`; only counterfactual rankings may vary. Live trading,
production signal creation, order intents, executable positions, network access, the database,
NATS, Freqtrade, and the active soak stack are outside this program.

The current mandate remains `retail-btc-spot-v2`: BTC/USDT spot, long or flat, and zero live
capital. The 2026 BTC partition remains sealed. The running partial OB0 capture is a separate
data-engineering workstream and may not be inspected here.

## Architecture

The research-only interfaces live in `src/trading_platform/research_routing.py`. They are
immutable value contracts for feature observations, regime state, arm specifications,
forecasts, and routing decisions. The module uses only the Python standard library and has no
imports from production signal, execution, transport, database, or exchange modules.

`StrategyArmRegistry` validates identities and evidence dispositions. `CounterfactualRouter`
ranks complete, non-stale forecasts deterministically by score, confidence, arm ID, and
version. Rejected arms are excluded before ranking. Missing forecasts and unknown or stale
state return a fail-closed counterfactual `no_trade` decision. Regardless of the ranking,
`RoutingDecision` rejects any `actionable_arm_id` other than `no_trade`.

S0 registers exactly three arms:

- `no_trade`, eligible and the only actionable identity;
- `btc_breakout_20d_10d`, development-only and counterfactual;
- `btc_bocpd_gated_breakout`, rejected and excluded from selection.

No placeholder future arms are registered.

## Stages and gates

### S0 — context bundle and safe contracts

Provide deterministic serialization, checksummed immutable contracts, a stage registry,
append-only chained decisions, a concise handoff, offline research interfaces, synthetic
ranking fixtures, and a fail-closed context validator. Pass only when the tests prove that no
route can become executable and the validator proves that required context is present,
unchanged, dependency-consistent, and sealed where required.

### S1 — shared causal research ledger

After a separate request, consolidate exact segment-aware 5-minute, 4-hour, and daily
aggregation; emit point-in-time feature observations; adapt the fixed breakout without changing
parameters; reproduce its development result and attribution; and create a BTC evidence-boundary
registry. No model fit and no holdout access are permitted.

### S2 — continuous EWMA risk benchmark

Freeze a causal daily EWMA volatility estimate and compare downward-only scaling of the
breakout's 10% allocation with fixed allocation under 30, 40, and 80 bps costs. Direction and
entry timestamps remain unchanged. This control remains mandatory even if it does not improve
performance.

### S3 — Student-t HMM risk model

Only after S2 is frozen, evaluate a two-state persistent risk model with an operational unknown
state. Use risk-only features, causal robust scaling, monthly expanding refits, and daily forward
filtering. Full-sample smoothing and Viterbi executable labels are prohibited. Both the frozen
standalone risk-separation gates and overlay gates versus EWMA must pass.

### S4 — conditional statistical jump model

Build this model only when S3 passes forward-risk separation but fails specifically on flicker,
transition timing, or dwell stability. Skip it if S3 passes all gates; reject the latent-risk
branch if S3 fails separation. A built jump model must beat both EWMA and HMM under the same
frozen gates.

### S5 — independent strategy-arm acceptance

Keep routing counterfactual until two economically distinct strategy families independently
pass their own research programs. Multiple breakout speeds are one trend family. If fewer than
two distinct families pass, pause the routing program.

### S6 — counterfactual router evaluation

With two accepted arms, compare routing against the best single arm, a static accepted-arm
blend, `no_trade`, and exposure-matched controls using chronological walk-forward evaluation,
shared capital, frozen costs, turnover, and transition attribution. Actionable output remains
`no_trade`.

### S7 — locked evaluation and forward paper observer

Unlock a final partition only once after the pipeline and gates are frozen. If the current
partition cannot provide at least 12 months, 30 filled routed trades, and four risk-state
transitions, leave it sealed and collect prospective evidence. Runtime or live integration
requires a separate mandate and explicit approval.

## Durable context protocol

Every session starts by reading, in order:

1. `AGENTS.md` and the four mandatory research handoff documents;
2. this program document and the machine-readable program status;
3. the concise routing handoff and active frozen stage contract; and
4. the preceding evidence manifest named by the status registry.

Work on at most one active stage. Before leaving a stage, update the status registry, append a
chained decision record without rewriting earlier records, refresh the handoff and checksums,
and run:

```bash
.venv/bin/python scripts/validate_btc_regime_routing_context.py
.venv/bin/pytest -q tests/test_research_routing.py tests/test_research_program.py
```

Any data, universe, feature, threshold, cost, execution, or model change requires a new frozen
experiment ID. Negative results remain immutable. Essential context may not exist only in chat.
