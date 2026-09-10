# BTC backtest evidence scorecard plan

Experiment ID: `btc-backtest-scorecard-v1`  
Evidence class: offline research infrastructure and retrospective audit only  
Actionable arm: `no_trade`

## Purpose

Create one canonical metric and evidence-gating layer before another BTC strategy or regime
experiment. Existing headline returns, Sharpe ratios and profit factors are descriptive; they do
not establish sufficient evidence when serial dependence, few trades, multiple inspected trials,
tail loss, costs and matched controls are unresolved.

The implementation consumes only immutable, checksummed BTC artifacts through 2025. It may replay
the frozen fixed breakout, EWMA risk benchmark and positive-funding carry without changing their
strategy logic. It must preserve every historical disposition and emit supplemental scorecards;
it cannot promote an arm or reopen a rejected hypothesis.

## Frozen definitions

- Mark-to-market risk metrics use one exact UTC daily equity observation and 365.2425-day
  annualization. Gaps inside a segment, non-positive equity and ambiguous timestamps fail closed.
- Conventional Sharpe remains for parity. The primary Sharpe uses a Bartlett/Newey-West long-run
  variance with a predeclared dependence horizon at least as long as the position/label overlap.
- Tail reports include drawdown depth/duration/recovery, time underwater, worst rolling
  7/30/90/365-day return, historical VaR and expected shortfall at 95% and 97.5%.
- Statistical evidence includes effective observations, a deterministic 10,000-replication block
  bootstrap, probabilistic Sharpe, deflated Sharpe and minimum track-record length. Unknown trial
  history makes deflated evidence insufficient.
- Event strategies require at least 730 daily observations, 24 dependence blocks and 30
  non-overlapping closed trade cohorts. Continuous strategies replace the cohort rule with 36
  monthly-scale blocks.
- Alpha must remain positive at severe frozen costs and have positive lower 95% paired excess-
  return bounds versus every mandatory matched/simple control. Risk overlays remain controls and
  cannot count as independent alpha.
- Every scorecard separates gross return, fees, implicit costs, financing/funding, turnover,
  break-even cost, concentration, calendar stability, controls and strategy-specific risk gates.
- Unsupported quantities are explicit `insufficient` or `not_applicable` values. NaN and infinity
  are prohibited.

## Retrospective targets

1. Fixed 20-day/10-day BTC breakout: alpha-strategy audit using the frozen S1/S2 trade stream and
   the later rejected random-timing mechanism gate.
2. `btc-regime-routing-s2-ewma-v2`: risk-overlay audit against the exact fixed breakout.
3. `btc-positive-funding-carry-v1`: alpha-strategy audit against always-on matched carry and the
   same signal windows without funding, preserving its six trades and failed margin/timing gates.

The trial registry is intentionally conservative: known historical BTC trials are registered, but
family completeness remains false wherever the repository cannot prove that every inspected
configuration is recorded. Retrospective deflated Sharpe therefore cannot support acceptance.

## Prohibited

No 2026 data, mutable/partial OB0, network, database, NATS, Freqtrade, exchange client, credentials,
orders, live/paper capital, regime fitting, parameter tuning, leverage scaling, strategy
combination or historical-report overwrite is permitted.

## Pass condition

The infrastructure passes when formulas and failure modes have deterministic tests, all three
legacy headline results reproduce within frozen tolerance, supplemental artifacts are checksummed,
the trial and context validators pass, and every output preserves zero accepted arms and
`actionable_arm_id = no_trade`. This is not a strategy-acceptance gate.
