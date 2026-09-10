# BTC backtest-core qualification plan

Qualification ID: `btc-backtest-core-qualification-v1`  
Status: frozen before implementation and qualification  
Actionable arm: `no_trade`

## Purpose

Establish one deterministic BTC long/flat candle backtest core before researching another
strategy or regime detector. This is an engineering qualification, not a new alpha experiment.
The already consumed SMA and breakout results are immutable regression targets only.

## Required behavior

The core must validate causal decision/execution timestamps, reject gaps within a source segment,
use the shared execution scenarios and Decimal portfolio ledger, enforce allocation, planned-risk,
entry-frequency, daily-loss and strategy-drawdown limits, mark open positions to market, record
expired/rejected/busy/risk-blocked intentions and emit a canonical checksummed result.

Future strategies must provide flat, buy-and-hold and timestamp/exposure-matched controls. B3 does
not create those controls for a new strategy because it is prohibited from evaluating one.

## Qualification

Synthetic tests cover causality, gaps, price protection, fees, rounding, stop state, drawdown,
metrics and deterministic serialization. The frozen historical SMA and fixed breakout reports
must retain their exact predeclared primary-cost metrics and checksums. No 2026, partial L2,
network, database, NATS, Freqtrade, exchange, strategy selection or regime fitting is allowed.
