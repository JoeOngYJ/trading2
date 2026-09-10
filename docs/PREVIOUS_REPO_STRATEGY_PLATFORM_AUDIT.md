# Previous-Repository Strategy Platform Audit

**Reviewed:** 2026-08-26  
**Sources:**

- `/home/joe/Desktop/Algo_trading/crypto-research-freqtrade`
- `/home/joe/Desktop/Algo_trading/oanda-trading-system`
- current repository `/data/Trading`

## Executive finding

The previous repositories contain useful architecture and research components, including
regime filters, regime-to-strategy routing, risk governors, sizing, execution simulation,
paper-observation tooling, and monitoring concepts. They do not provide a proven crypto
runtime that can be copied into this repository.

The strongest reusable material is the separation of concerns:

```text
market state -> strategy arms -> router -> portfolio/risk governor
             -> order intent -> execution/fill/reconciliation -> monitoring
```

Reuse that layering and its test ideas. Revalidate or rebuild the implementation against
the current crypto contracts, shared-capital ledger, mandate, and cost model.

## What the previous crypto repository actually contains

### Embedded regime filter

`user_data/strategies/crypto_ltf_continuation.py` contains a causal-looking multi-timeframe
trend gate using completed 4h state, EMA structure, ADX/directional movement, and a
volatility-expansion limit. This is a filter for one continuation strategy, not a general
multi-strategy selector.

The independently reconstructed top-two strategy in this repository also already contains
a hard-coded regime gate: BTC support, cross-asset breadth, near-high breadth, and a BTC
anchor. Therefore the current candidate is not regime-blind. What is missing is a reusable,
versioned regime-state contract and a validated router that can choose among independent
strategy arms or no-trade.

### Regime-selector and router labs

The previous crypto repository includes:

- `crypto_strategy_regime_selector_lab.py`;
- `crypto_multi_strategy_router_architecture_lab.py`;
- `crypto_dynamic_opportunity_risk_router_lab.py`;
- multiple state/risk/brake and route-package labs.

These are predominantly sidecar/report-only research programs. Their own reports prevent
them from being treated as production evidence:

- the regime selector verdict is `selector_rejected`;
- the multi-strategy router verdict is `multi_strategy_router_watchlist_only`;
- the general portfolio risk governor verdict is `risk_governor_rejected`;
- the dynamic opportunity/risk router is only a `dynamic_router_default_off_candidate`.

Several earlier headline results also used additive event accounting rather than the current
shared-cash portfolio accounting. Their absolute return and drawdown values are not portable.

### Useful concepts to preserve

- explicit `no_trade` arm;
- signal-time versus post-entry feature separation;
- deterministic scorecard before machine learning;
- strategy-arm counterfactual outcome tables;
- regime persistence, decay, exhaustion, and unknown-state handling;
- entry router separated from post-entry risk/exit actions;
- concentration, stress-cost, leave-window-out, and matched-return gates;
- default-off packages, parity tests, paper observation, and kill-switch tests.

## What the OANDA repository adds

The OANDA repository has a fuller runtime topology:

- market-data agent;
- regime runtime strategy agent;
- `RegimeSwitchRouter` and regime-aware ensemble;
- pre-trade checker and circuit breaker;
- execution agent, order manager, fill tracker, and monitoring agent;
- backtest portfolio, commission, financing, and slippage components.

It is useful as an architectural reference, not a crypto implementation. Material reasons
not to port it directly include:

- broker- and instrument-specific contracts;
- in-memory order/risk state in key components;
- market-order-first execution assumptions;
- unknown regimes can fall back to a configured or first strategy instead of failing flat;
- its risk calculations and lifecycle assumptions need revalidation against spot inventory,
  reductions, partial fills, and the current durable ledger;
- existence of a runtime path does not establish crypto profitability or causal regime value.

## Current-repository capability matrix

| Capability | Current state | Assessment |
|---|---|---|
| Point-in-time evidence, checksums and timestamp contracts | Implemented | Retain; this is stronger than the older research repos. |
| Reliable jobs, leases, outbox, JetStream, bridge and snapshots | Implemented and soak-tested | Retain; do not rebuild it inside the strategy layer. |
| Kill switch, signal expiry, fail-closed bridge and Freqtrade boundary | Implemented | Retain; extend decisions without weakening the final gate. |
| Freqtrade reconciliation and audit capture | Implemented | Retain and later connect strategy/order attribution. |
| Offline cost/execution model | Strong v1 | Supports candle taker, L2 walk, maker timeout, partial fills, market rules, commissions, price protection, unknown-state reconciliation, and deterministic manifests. Account calibration remains pending. |
| Generic shared-capital research engine | Partial | Present in specific experiments, not yet a reusable strategy/portfolio harness. |
| Regime-state engine and versioned state contract | Missing | Regime logic is embedded in individual scripts; there is no canonical state, probability/confidence, age, transition, or unknown/stale behavior. |
| Strategy-arm interface and registry | Missing | No versioned contract for arm availability, forecast, horizon, capacity, required regime, or abstention. |
| Multi-strategy router | Missing | No validated current-repo router or counterfactual arm ledger. |
| Central account and risk engine | Partial/documented | Mandate limits and experiment-specific enforcement exist, but no durable central mark-to-market risk decision component owns daily loss, drawdown, exposure, concurrent positions, and protective-exit precedence. |
| Portfolio allocator | Missing | No general covariance/correlation-aware allocator using one cash account across accepted alphas. |
| Runtime order-intent and fill lifecycle | Partial | Freqtrade owns execution and the offline model is strong, but no current strategy-intent contract carries sizing, protection, expiry, router/risk attribution, and observed fill/cost feedback end to end. |
| Strategy/risk observability | Missing | Infrastructure metrics exist; regime age/transitions, selected arm, abstentions, exposure, PnL attribution, risk state, order/fill costs, and model decay do not. |
| Forward paper observer and promotion registry | Missing | Research observers exist only in the prior repo; accepted strategy identities and promotion states are not wired into the current platform. |

## Priority implementation order

### P0 — Preserve the reliable boundary

Do not disturb the active soak or replace the existing durable signal pipeline. Treat the
execution-cost model, mandate, timestamps, evidence, kill switch, reconciliation, and
Freqtrade final entry gate as fixed dependencies.

### P1 — Build the reusable causal research and attribution harness

This comes before a runtime router. Generalize shared-cash accounting, matched controls,
regime attribution, selection-alpha decomposition, cost scenarios, confidence intervals,
and experiment manifests. Implement R0 in this harness. A router built before this layer
would make it easier to overfit regime labels and harder to attribute returns.

Definition of done:

- byte-reproducible experiment artifact and manifest;
- point-in-time universe and gap handling;
- shared cash/inventory and mark-to-market equity;
- matched beta, regime-gate, selection, sizing, and cost attribution;
- no-trade and simple baselines;
- walk-forward/block-bootstrap/concentration reports.

**Implementation status (2026-08-26):** the first offline P1/R0 foundation is implemented
in `src/trading_platform/research_attribution.py` and
`scripts/analyze_multi_asset_top2_alpha.py`. It now provides isolated checksummed inputs,
arbitrary-leg shared-capital controls, matched event diagnostics, deterministic random and
gate-date controls, beta/intercept attribution, month-block confidence intervals, cost and
concentration reports, and reproducible manifests. R0 correctly rejected the selection
claim because uncertainty, sample, concentration, gate-timing, and point-in-time-universe
gates failed. The follow-on P1 contract now implements evidence-backed eligible/ineligible/
unknown timelines, gap and checksum validation, label embargoes, locked prospective
collection, and family-wide inspection contamination. It correctly fails the current data:
membership evidence and a clean forward partition still do not exist. See
`docs/MULTI_ASSET_TOP2_ALPHA_ATTRIBUTION_R0_RESULT.md` and
`docs/RESEARCH_EVIDENCE_CONTRACT.md`.

### P2 — Define and validate the regime-state engine

Start research-only. Emit a versioned state such as trend/expansion, range, stress/reversal,
and unknown, with confidence, information cutoff, age, transition reason, and feature digest.
Unknown, stale, gap-crossing, or low-confidence state must mean no new entry. Add hysteresis
and minimum-state-duration controls to reduce unstable switching.

Do not assume the old regime rules work. Compare each strategy arm inside and outside each
state, versus unconditional and matched controls. A regime is useful only if it improves an
arm or the no-trade decision after costs out of sample.

### P3 — Define the strategy-arm interface and registry

Each arm must declare identity/version, direction, universe, horizon, forecast/score,
confidence, expected holding period, capacity, cost budget, required/forbidden regime,
expiry, and abstention reason. Begin with `no_trade` and one validated arm. Rejected and
watchlist arms cannot be registered as selectable.

### P4 — Implement the central portfolio/account risk kernel

Use one mark-to-market account state and make risk decisions independently of strategy
selection. Enforce position allocation, planned loss, cash/inventory, concurrent position,
daily loss, high-water drawdown, stale data, concentration, and global/manual kill switches.
Risk may reduce or reject entries, but it must never block protective exits. Persist the
decision and reason so it can be reproduced.

### P5 — Research and validate the deterministic router

Route only between registered arms and `no_trade`. Start with explicit scorecards; do not
start with ML. Log all arm forecasts, availability, regime state, chosen arm, rejection
reason, and counterfactual arm outcome for later attribution. Unknown state, disagreement,
or unavailable inputs fail flat. Promotion requires incremental out-of-sample value over the
best single-arm reference after costs, not merely lower drawdown or a better headline period.

### P6 — Connect order intent to the existing execution boundary

Extend rather than replace `execution_model.py`. Add a versioned order-intent contract with
strategy, regime, router and risk decision IDs; desired/maximum quantity; price protection;
expiry; maker deadline/fallback; and protective-exit priority. Reconcile intended, accepted,
filled, cancelled, expired, rejected, and unknown states. Keep Freqtrade as the only order
placer unless a separately reviewed architecture changes that boundary.

### P7 — Add portfolio allocation only after two alphas pass

Estimate forecast and PnL dependence, allocate one shared risk budget, cap correlated
exposure, and apply turnover/cost/capacity limits. Do not add standalone backtest returns or
call multiple transformations of trend diversified.

### P8 — Add strategy, risk and execution observability

Expose regime state/age/transitions, arm availability and selection, no-trade reasons,
forecast decay, exposure, mark-to-market PnL, drawdown, daily stop, rejected intents,
partial/unfilled quantity, fill slippage, realized fees, and reconciliation differences.
Dashboard and alerts must identify the decision layer that caused an action or abstention.

### P9 — Forward paper observation and promotion control

Paper-observe each frozen accepted arm as soon as it passes standalone research. Then test
the router and eventual combined portfolio. Compare predicted with observed availability,
latency, fills, fees, and state transitions. Promotion requires a versioned registry entry,
reviewed mandate, rollback plan, and explicit approval; no backtest or router status enables
capital.

## Immediate priority

The P1/R0 replay and evidence-enforcement foundations are implemented while L2 acquisition
continues independently. R0 found a promising ranking point estimate but rejected the
selection-alpha claim, and the evidence contract prevents missing membership or inspected
2026 data from passing as validation. Acquire defensible sources and declare a genuinely
prospective partition only under a new frozen version. In parallel only at the
data-engineering level, complete OB0 and continue toward the frozen 60-day development plus
30-day sealed-test requirement. Do not build a production regime router or tune the
rejected ranking yet.
