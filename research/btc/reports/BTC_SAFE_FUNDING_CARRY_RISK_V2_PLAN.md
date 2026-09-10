# BTC safe delta-neutral funding carry risk v2 plan

Experiment ID: `btc-safe-delta-neutral-funding-carry-v2`  
Status: frozen before any v2 return calculation  
Scope: offline development risk-implementation experiment; never actionable

## Falsifiable question

Can the unchanged `btc-positive-funding-carry-v1` entry/exit rule be implemented at a fixed,
predeclared safe exposure with zero observed or 20%-shocked planning-margin breaches while
remaining net positive after primary and severe two-leg costs?

This experiment separates implementation from alpha. Lower exposure may reduce both profit and
loss; it is not an improvement in signal quality. Timing alpha remains a separate required result:
the funding-gated implementation must beat an always-on matched carry control in return per exposed
day at the exact same safe leg fraction.

## Frozen conceptual change

Change only carry risk implementation relative to v1:

- reduce each matched leg from 49% to exactly 25% of current strategy equity;
- leave the remaining 75% of equity as isolated planning collateral for the short perpetual;
- after every completed hourly mark, calculate observed and 20%-up-shocked short-margin equity and
  maintenance using the unchanged 10% planning-maintenance assumption;
- require the shocked margin-equity/maintenance ratio to remain at least 2.0;
- if that ratio falls below 2.0 but remains above liquidation, schedule a full matched-pair risk
  exit at the next available hourly open with severe 20/20 bps exit friction;
- after a risk exit, do not re-leverage intratrade or before a later ordinary Monday decision.

The 25% leg cap is chosen before v2 outcomes because it matches the frozen retail spot-allocation
cap and is substantially below the unsafe 49% v1 leg size. The 2.0 ratio is a fixed 100%
maintenance-headroom rule, not a value selected from historical v2 returns.

## Unchanged signal and evidence boundary

- Monday decision at 00:05 UTC after completed funding publication;
- previous 84 completed eight-hour funding events (28 days);
- entry score strictly above 60 bps;
- exit score at or below 30 bps;
- next 01:00 UTC simultaneous spot/perpetual execution;
- 84-day maximum holding period;
- exact matched BTC quantity rounded down to 0.00001 BTC;
- development: 2020-02-03 through 2023-12-31;
- consumed chronological evaluation: 2024-01-01 through 2025-12-31;
- no 2026 access and no claim that the consumed evaluation is promotion evidence.

The v1 14-day and 42-day lookbacks are not searched or selected. They remain preserved v1
diagnostics only. No threshold, clock, horizon, source, funding formula or execution convention is
changed.

## Costs, controls and attribution

Run the unchanged 30, 40 and 80 bps round-trip scenarios independently on both legs. Compare:

1. the unchanged v1 funding gate at 25% per leg;
2. always-on matched carry at 25% per leg;
3. exact signal windows without funding at 25% per leg;
4. funding-only return in the exact signal windows;
5. 25% BTC spot buy-and-hold; and
6. flat/no-trade.

Report spot and perpetual price PnL, basis convergence, funding, explicit fees, implicit costs,
turnover, exposure, margin observations, shocked margin observations, risk exits, annual results,
drawdown, Sharpe, Sortino, Calmar, win rate, profit factor and concentration. Also report net return
per unit leg fraction so the 25% result is not misrepresented as alpha degradation or improvement
relative to 49% v1.

## Frozen gates and dispositions

Risk implementation passes only if, on 2024–2025 evaluation:

1. observed margin breaches, shocked margin breaches and executions below the 2.0 shocked ratio
   are all zero after applying the causal risk-exit rule;
2. primary and severe net returns are strictly positive;
3. primary funding cashflow is strictly positive;
4. primary maximum drawdown is no more than 10%;
5. at least four trades close and both calendar years are strictly positive;
6. best three months and best trade each contribute no more than 60% of positive PnL; and
7. exact data, causality, matched-quantity and no-2026 checks pass.

Timing alpha passes only if the primary gated strategy's return per exposed day is strictly above
the same-exposure always-on control. The outcome is classified as:

- `development_candidate_passed_not_promotable` only if both risk and timing gates pass;
- `risk_implementation_passed_timing_alpha_rejected` if safety/economics pass but timing does not;
- `risk_implementation_rejected` if any risk/economics gate fails.

No disposition accepts a strategy arm because the evaluation period is already consumed. Any
promotion requires a separately frozen prospective observer and complete effective-dated fees,
margin, liquidation, ADL, venue and account eligibility evidence.

## Stopping rule

Do not tune 25%, the 2.0 margin ratio, the 20% shock, the v1 thresholds, lookback or maximum hold
after results. Do not add a regime rescue. If timing alpha fails again at safe exposure, close the
funding-timing rule; a later always-on structural-carry hypothesis would require a new ID and new
evidence. If risk implementation fails, close this carry implementation and move to a materially
different BTC family.

No credentials, network access, live or exchange paper orders, partial OB0, protected service,
premium-index imputation, 2026 data, naked short, production signal, position or actionable route
is permitted. `actionable_arm_id` remains `no_trade`.
