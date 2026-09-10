# BTC carry data qualification plan

Audit ID: `btc-carry-data-qualification-v1`  
Status: frozen before new acquisition  
Scope: data and rule evidence only; no strategy, PnL or execution simulation

The audit binds the BTC-only evidence catalogue and the zero-capital delta-neutral research
mandate. It acquires official Binance monthly BTCUSDT USD-M perpetual trade, mark, index and
premium-index hourly archives plus exact funding events for 2020–2025. Every archive must match
its official sidecar checksum.

The audit tests month coverage, CSV identity and numeric validity, UTC timestamps, duplicates,
hourly continuity, synchronization across the four price series and the expected eight-hour BTC
funding schedule. Existing checksummed BTC spot ledgers establish spot coverage without another
copy of the same raw spot history.

Current public spot/futures exchange information, funding information, mark/index observations,
fee tables and official margin/API documentation are archived as retrieval-dated evidence. They
may not be projected backward. Binance's user commission and notional/leverage bracket endpoints
are authenticated; this audit records those historical/effective-dated gaps without credentials
or calls.

The result reports two dispositions separately:

1. whether the official market time series pass data engineering gates; and
2. whether exact effective-dated fees, margin and liquidation inputs make the dataset ready for a
   later strategy contract.

A market-series pass with a strategy-readiness block is a valid B2 result. It does not authorize
imputation, a carry threshold, a return calculation, or the next experiment.
