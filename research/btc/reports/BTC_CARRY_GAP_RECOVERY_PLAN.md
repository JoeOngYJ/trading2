# BTC carry reference-price gap recovery plan

Experiment ID: `btc-carry-gap-recovery-v1`  
Status: frozen before any recovery request  
Scope: official-source data repair and continuity audit only

## Question

Can the 649 missing hourly mark, index, and premium-index observations identified by the
rejected B2 qualification be recovered exactly from Binance's unauthenticated USD-M REST
market-data endpoints?

## Frozen method

The machine-readable contract fixes 18 requests covering only the missing timestamp blocks.
Every request uses HTTPS GET against `fapi.binance.com`, the documented 1-hour kline endpoint,
the exact start and end open times, and a limit equal to the expected row count. No credential
or account endpoint is permitted.

Each raw response is retained before interpretation and checksummed. A response passes only if
it is HTTP 200 JSON, contains the exact frozen timestamp set, has 12 fields per row, has exact
hour boundaries, and has finite, correctly ordered OHLC values. Mark and index values must be
positive; premium-index values may be negative. Empty, partial, extra, malformed, or substituted
data fail closed.

The audit then combines valid recovered open times with the immutable B2 archive open times.
Each series must contain exactly 52,608 unique hourly opens from 2020-01-01 through 2025-12-31,
with no gaps, duplicates, or invalid rows. No interpolation is allowed.

## Interpretation boundary

A pass repairs only the successor's price-series continuity gate. It does not erase B2's
rejection, does not resolve historical fees or effective margin brackets, does not calculate a
strategy or PnL, and does not authorize paper or live trading. A failure records the exact
unrecoverable blocks and leaves carry strategy research blocked.
