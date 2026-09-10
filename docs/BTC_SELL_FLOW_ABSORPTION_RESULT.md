# BTC Sell-Flow Absorption Development Result

Experiment ID: `btc-sell-flow-absorption-v1`  
Decision: **development reject; holdout remains sealed**  
Frozen contract: [`BTC_SELL_FLOW_ABSORPTION_HYPOTHESIS.md`](BTC_SELL_FLOW_ABSORPTION_HYPOTHESIS.md)

## Outcome

The completed-hour flow/price residual did not isolate an executable long rebound. Across
115 price-protected primary fills, the underlying move averaged only **+6.78 bps gross**.
After the frozen 30 bps round-trip model, mean trade return was **−23.22 bps** and the shared
account lost **5.28%**.

| Scenario | Filled trades | Mean net trade | Account return | Maximum drawdown | Profit factor |
|---|---:|---:|---:|---:|---:|
| Primary, 30 bps round trip | 115 | −23.22 bps | −5.28% | −6.37% | 0.73 |
| Stress, 40 bps round trip | 115 | −33.20 bps | −7.43% | −8.19% | 0.64 |
| Severe, 80 bps round trip | 115 | −73.11 bps | −15.56% | −15.56% | 0.39 |

The primary win rate was 32.17%; 46 of 115 fills hit the protective stop. Only 2022 and
2025 were positive at primary cost. The UTC-month block-bootstrap 95% interval for mean net
trade return was **−51.96 to +6.56 bps**, so uncertainty includes zero and its point estimate
is negative.

## Attribution and robustness

- The extreme-sell-only control averaged −21.70 bps after cost. Adding the absorption
  residual made the candidate approximately **1.52 bps worse**, failing the required
  incremental-information test.
- The price-only reversal control averaged −20.88 bps after cost and also lost money.
- The candidate did not beat 5,000 month/hour-matched random samples (`p=0.5731`); the
  matched-random mean was −19.98 bps.
- All 12 predeclared one-factor perturbations lost at primary cost. This includes shorter
  and longer lookbacks, nearby flow/residual/volume quantiles, 6-hour and 24-hour holds,
  and 1% and 2% stops.
- Monthly return attribution estimated essentially zero BTC beta but a negative monthly
  intercept. Avoiding market beta did not produce positive alpha.

Nine binding economic, statistical, incremental, stability, and robustness gates failed.
The drawdown, sample-size, concentration, exposure, planned-risk, causality, and sealed-data
gates passed, but they cannot rescue negative expectancy.

## Decision and next direction

Do not tune this experiment, select a less-negative perturbation, or open the 2026
January-July holdout. Together with the earlier raw-imbalance and positive-exhaustion
results, this closes threshold variants of **aggregate five-minute taker-flow bars** as the
active alpha family.

Aggregate flow remains useful as a baseline control. New microstructure research should
wait for accepted genuine L2 data, where resting liquidity, cancellations, depth and queue
changes can distinguish actual absorption from a bar-level proxy. The running partial OB0
capture remains data-engineering evidence only and was not read by this experiment.

## Reproduction artifacts

- Backtest: `scripts/backtest_btc_sell_flow_absorption.py`
- Frozen configuration: `config/experiments/btc-sell-flow-absorption-v1.json`
- Checksummed report and trades:
  `artifacts/agent-level-experiment/btc-sell-flow-absorption/development-v1/`
- Development input SHA-256:
  `316e5789d4b49f79a0adfdd90f0e98c26dd2658060c49fe2366c91dffa2024e8`

The report explicitly records `holdout_read: false`. No exchange, PostgreSQL, NATS,
Freqtrade, soak, or live-capture service was contacted.
