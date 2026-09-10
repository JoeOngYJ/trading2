# BTC backtest-core qualification result

Qualification ID: `btc-backtest-core-qualification-v1`  
Decision: **B3 passed — engineering infrastructure only**  
Accepted strategy arms: none  
Actionable arm: `no_trade`

## Result

The new offline BTC long/flat candle core passes its frozen engineering gates. It validates
causal decision and execution timestamps, rejects duplicates, reversals, same-segment gaps and
segment-crossing plans, uses the shared Decimal execution and portfolio ledger, and enforces
allocation, planned-risk, entry-frequency, daily-loss and strategy-drawdown limits. It records
expired, rejected, busy, frequency-blocked and risk-disabled intentions and emits a canonical
result digest with mark-to-market equity, costs, turnover, exposure, annual returns, Sharpe,
Sortino, Calmar, profit factor and drawdown where the evaluation duration supports them.

The deterministic synthetic replay was byte-identical and included a real simulated entry and
protective exit with explicit and implicit execution costs. Short fixtures intentionally emit no
CAGR or Calmar rather than annualizing a few minutes of test data.

## Frozen historical regression evidence

B3 did not test a new strategy. It verified that the two consumed development controls remain
unchanged:

| Control at 30 bps | Net return | CAGR | Maximum drawdown | Profit factor | Trades |
| --- | ---: | ---: | ---: | ---: | ---: |
| Fixed 20-day/10-day breakout, 10% allocation | 16.94% | 2.26% | 5.02% | 1.88 | 67 |
| 4h SMA 10/30, 25% allocation | 114.88% | 9.56% | 29.10% | 1.51 | 353 |

Those are regression targets, not acceptance evidence. The breakout timing previously failed its
random-entry falsifier; the SMA previously failed stability and drawdown requirements. B3 does
not reopen either family or convert consumed development history into a holdout.

## Boundaries and limitations

This core is for BTC spot long/flat candle research. A future strategy adapter must generate its
own causal entry and exit plans and exact flat, buy-and-hold and timestamp/exposure-matched
controls. Paired spot/perpetual funding, collateral, liquidation and funding-cashflow accounting
are deliberately not implemented here; they require a separately frozen extension after the B2
data gaps are addressed.

No new strategy outcome, regime model, 2026 market data, partial L2 data, network, database, NATS,
Freqtrade, exchange client, production signal, paper order or live order was used.

## Evidence and reproduction

- Contract: `research/btc/contracts/btc-backtest-core-qualification-v1.json`
- Core: `src/trading_platform/btc_backtest.py`
- Qualification report:
  `artifacts/agent-level-experiment/btc-focused/backtest-core-qualification-v1/qualification-report.json`
- Evidence manifest:
  `artifacts/agent-level-experiment/btc-focused/backtest-core-qualification-v1/evidence-manifest.json`

```bash
.venv/bin/pytest -q tests/test_btc_backtest_core.py tests/test_execution_model.py \
  tests/test_research_ledger.py tests/test_research_breakout.py tests/test_btc_4h_trend.py
.venv/bin/python scripts/qualify_btc_backtest_core.py \
  --output artifacts/agent-level-experiment/btc-focused/replays/backtest-core-qualification-<new-empty-id>
```

The next permitted work is a new, official-source-only carry gap-recovery audit. Do not build a
regime detector or evaluate carry returns until that prerequisite is separately frozen and
recorded.
