# Repository Agent Instructions

These instructions apply to the entire repository. They supplement the project documents;
they do not authorize live trading or changes to an active soak.

## Protect running reliability tests

- Treat PostgreSQL, NATS, Freqtrade, and every container used by an active soak or
  acceptance run as read-protected external state.
- Strategy research must use archived/checksummed inputs and isolated scripts only.
- Do not connect to, restart, reconfigure, or send test traffic through the soak stack.

## Mandatory strategy-research method

Follow `docs/STRATEGY_RESEARCH_STANDARD.md` for every new strategy experiment. In
particular:

1. Freeze one falsifiable hypothesis, experiment ID, data boundary, decision timestamp,
   execution convention, cost scenarios, parameters, and rejection gates before reading
   evaluation results.
2. Use point-in-time data and prove causality. Fail closed on gaps, invalid rows,
   unavailable historical constituents, or publication/retrieval timestamp ambiguity.
3. Separate signal quality from position sizing. Never present higher exposure or leverage
   as an improvement in alpha or Sharpe.
4. Compare against flat, buy-and-hold, and exposure/timestamp-matched controls. A
   cross-sectional selector must also beat an eligible-universe basket, seeded random
   selection, and a selected-minus-remainder diagnostic after costs.
5. Attribute returns to market beta, regime timing, asset selection, sizing, and costs
   before tuning the strategy.
6. Use realistic execution costs and report every frozen cost scenario, including rejected,
   expired, rounded, and partially filled orders where the data can support them.
7. Require chronological walk-forward or genuinely unseen forward evidence, robustness
   tests, concentration analysis, and uncertainty intervals. A development backtest is
   never promotion evidence.
8. Preserve negative results. Any change to data, universe, feature, threshold, cost, or
   execution logic requires a new experiment ID; do not tune a rejected experiment.
9. Validate each alpha independently before combining signals. Portfolio construction may
   combine only economically distinct, individually accepted forecasts and must account
   for correlation, turnover, costs, capacity, and risk.
10. Do not optimize for a requested headline return. Report return at the frozen risk level,
    and report risk-normalized comparisons separately.

## Current strategy-research priority

- Keep `multi-asset-top2-causal-v1` as a development baseline, not a live candidate.
- Before increasing its exposure or changing its score, run the frozen selection-alpha
  decomposition specified in `docs/STRATEGY_RESEARCH_STANDARD.md` and record it in
  `docs/RESEARCH_TRACKER.md`.
- Keep the BTC L2 OB0 capture as a data-engineering workstream. Do not inspect partial OB0
  data, derive a strategy from it, or disturb its persistent capture services.
- `btc-sell-flow-absorption-v1` is rejected on development evidence. Together with the prior
  taker-flow results, this closes threshold variants of aggregate five-minute taker flow;
  retain it only as a control and do not open its sealed 2026 partition.
- `btc-online-regime-breakout-v1` is rejected on development evidence. The causal daily
  BOCPD drift gate reduced the fixed breakout's return, Calmar, and mean trade expectancy and
  failed its standalone next-seven-day information test. Do not tune that detector or open
  its sealed 2026 partition. Retain the ungated breakout only as a development control until
  a separately frozen chronological validation establishes stability and attribution.
- The sealed 2026 partitions remain sealed wherever the applicable experiment documents say
  they are not a clean or eligible holdout.

## Required hand-off documents

Start strategy work with:

- `docs/RESEARCH_TRACKER.md`
- `docs/STRATEGY_RESEARCH_STANDARD.md`
- `docs/RETAIL_TRADING_MANDATE.md`
- `docs/EXECUTION_COST_MODEL.md`

Record material decisions and reproducible artifact paths in the tracker before moving to
another strategy family.
