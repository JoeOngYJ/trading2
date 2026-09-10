# BTC Upside Compression Breakout Research Plan — Validated Successor

Status: frozen before historical outcome access  
Program: `btc-upside-compression-breakout-v1`  
Frozen at: `2026-09-01T00:30:00Z`  
Supersedes: `BTC_UPSIDE_BREAKOUT_RESEARCH_PLAN.md`, which was preflight-invalid because
its stated freeze time was in the future.

## Scope

The first study is a non-PnL event and forecast experiment, not a strategy backtest. It asks
whether a strict, past-only compression and later upside confirmation can be catalogued and
whether information available at confirmation forecasts continuation versus range re-entry
during the next 168 completed hourly observations.

## Ordered stages

1. **BEX1-v3:** re-derive complete one-hour and four-hour candles from the accepted segmented
   five-minute source; produce a deterministic, causal event/path catalogue and count preflight.
2. **BEX2-v3:** compare an empirical age-hazard control, a regularized linear competing-risk
   hazard, histogram gradient boosting and XGBoost using nested chronological folds.
3. **BEX-D:** qualify immutable official announcement records and deterministic association
   matching. Numeric driver attribution remains blocked until complete official histories pass.
4. **Later experiment ID only:** if the non-PnL forecast study passes, freeze strategy entries,
   exits, risk sizing, 30/40/80-bps costs, PnL controls and prospective evidence before any
   profitability test.

## Audit corrections incorporated before data access

- Range width uses exactly 42 completed four-hour bars strictly before activation; each of the
  three compression widths has its own past-only 540-width q20.
- Confirmation is the first later complete one-hour close above the frozen high, with the exact
  next five-minute open as the execution-timestamp reference only.
- Continuation and re-entry use completed one-hour closes. Expiry and segment loss are censoring.
- All fitted hazards receive the same causal age basis as the empirical age-hazard control.
- The selected primary model must beat the empirical control with a favorable paired
  month-block interval; complexity cannot pass merely by existing.
- Activity features exclude the confirmation hour and are diagnostic only. Missing trade counts
  are never inferred.
- Nonlinear dependencies are isolated, pinned and qualified before model use.
- Driver results are association evidence only; exact release timing is not proof of causation.

## Evidence boundary

All BTC price history through 2025 is consumed development evidence. The 2026 partition is
sealed or ineligible and cannot be opened. A development pass can only authorize a separately
frozen prospective contract. Every output keeps zero accepted arms and
`actionable_arm_id = no_trade`.

## Prohibited actions

No strategy PnL, position, cost optimization, leverage, order, production signal, partial OB0,
network data acquisition, database, NATS, Freqtrade, exchange or soak-system access is allowed.
