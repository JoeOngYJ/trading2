# BTC derivatives-crowding public-source audit result

The bounded v1 call archived 4,383 BTCUSDT funding observations from 2020-01-01 through
2023-12-31. Binance basis accepted the frozen historical request and returned the first 500 daily
rows beginning 2020-01-01, so a separately frozen pagination successor may test full coverage.
The historical open-interest request failed with HTTP 400 and code `-1130` because the old
`startTime` is invalid under the current endpoint.

The generated v1 report's `source_gate_passed` field is rejected as an implementation error: it
counted Binance funding plus Binance basis as two sources, while the frozen whole gate requires
funding plus an independently sourced positioning or leverage series. No price, forward label,
strategy metric or trade was calculated. The correct qualification disposition is **blocked**
pending checksummed CFTC CME Bitcoin positioning archives and full basis pagination under a new
successor ID.
