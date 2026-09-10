# BTC positive-funding carry development result

Experiment ID: `btc-positive-funding-carry-v1`  
Decision: `development_strategy_rejected`  
Actionable arm: `no_trade`

## Result

The first BTC strategy backtest is economically positive but formally rejected because two of 15
frozen gates failed. On chronological 2024–2025 validation, the matched long-spot/short-perpetual
strategy produced:

| Per-leg round-trip cost | Net return | CAGR | Max drawdown | Sharpe | Profit factor | Trades |
|---|---:|---:|---:|---:|---:|---:|
| 30 bps | 5.83% | 2.87% | 0.42% | 5.29 | 71.94 | 6 |
| 80 bps | 2.61% | 1.30% | 1.47% | 1.40 | 3.37 | 6 |

Primary validation returned 5.42% in 2024 and 0.52% in 2025. Severe-cost 2025 was negative
(-0.76%), although the full severe partition remained positive. The small trade count and smooth
delta-neutral daily marks make the headline Sharpe imprecise; it is not promotion evidence.

## Attribution

At primary cost, the 58.28 USDT net profit on 1,000 USDT starting equity decomposes into:

- funding cashflow: +76.44 USDT;
- spot price PnL: +353.64 USDT;
- perpetual price PnL: -352.49 USDT;
- net basis convergence: +1.15 USDT;
- explicit fees: -12.87 USDT;
- implicit execution cost: -6.43 USDT.

The same exact position windows without funding lost 1.74%; funding-only after the same costs made
5.71%. This supports the intended funding mechanism rather than disguised BTC direction. Entry
weeks also led non-entry weeks by 60.88 bps of subsequent 28-day funding, with a frozen month-block
95% interval of `[23.84, 105.06]` bps. Both 14-day and 42-day lookback variants were positive.

## Failed gates

1. **Conservative margin shock:** no observed margin breach occurred, but 260 exposed hours would
   breach the frozen planning buffer if a further instantaneous 20% adverse mark shock were applied.
   The isolated short-perpetual collateral is therefore not robust enough at 49% notional per leg,
   even though the overall pair remains delta-neutral.
2. **Incremental timing value:** return per exposed day was 0.01343%, versus 0.01370% for the
   always-on carry control. The difference was -0.000268 percentage points per exposed day. The
   28-day timing rule successfully identified higher future funding but did not improve economic
   efficiency after its additional turnover.

The always-on control returned 9.93% at primary cost but itself suffered one observed planning-
margin liquidation and 1,104 shock-buffer breaches at the frozen 49% leg size. It is therefore not
an accepted alternative; it demonstrates that collateral design, not funding predictability, is
the immediate problem.

## Interpretation and next research step

Do not tune the 60/30-bps thresholds, select the best lookback, reduce the shock after seeing the
result, or add a regime rescue. This experiment is closed and remains a useful control.

The next defensible experiment is a separately frozen carry-risk implementation, not another entry
indicator: substantially lower matched notional with more isolated collateral and a predeclared
margin-buffer deleveraging rule. It should compare always-on and the unchanged v1 funding gate at
the same safe exposure, attribute any improvement to risk implementation rather than alpha, and
remain development-only because 2024–2025 has now been consumed. New promotion evidence must be
prospective.

## Evidence

- report: `artifacts/agent-level-experiment/btc-focused/positive-funding-carry-v1/report.json`;
- primary validation trades:
  `artifacts/agent-level-experiment/btc-focused/positive-funding-carry-v1/validation-primary-trades.jsonl`;
- evidence manifest:
  `artifacts/agent-level-experiment/btc-focused/positive-funding-carry-v1/evidence-manifest.json`.
