# A1 OANDA Hourly History Qualification Result

Experiment family: `cross-asset-a1-oanda-hourly-history-v1` / `v2`  
Stage: `A1`  
Result: **passed by no-download v2 successor**  
Strategy arms accepted: **0**  
Execution instruments approved: **0**  
Actionable disposition: `no_trade`

## Frozen acquisition

V1 made exactly 224 GET requests: 32 six-month H1 bid/ask candle chunks for each of
SPX500_USD, NAS100_USD, DE30_EUR, UK100_GBP, XAU_USD, EUR_USD and USD_JPY. The boundary is
2010-01-01T00:00:00Z inclusive through 2026-01-01T00:00:00Z exclusive. It archived 124,956,623
raw response bytes and retained bid and ask OHLC separately. The previously checksummed account
catalogue proved all seven identities; no catalogue request was repeated.

No 2026 price, account balance, summary, position, trade, transaction, order, preview, return,
PnL, feature, label or signal was accessed or computed. The literal account identifier and token
do not appear in artifacts. Oil and bond CFDs remain excluded because their historical continuous
financing is unresolved.

## V1 rejection and preserved correction

V1 correctly rejected its own two-percent incomplete-observed-session gate: only DE30_EUR and
UK100_GBP passed it. The other five candidates had 3.50% to 5.59% incomplete observed local dates.
Inspection was limited to source availability. Those dates are dominated by Sunday-local market
fragments, holidays and early closes, while every candidate has full frozen history edges, valid
uncrossed bid/ask rows, more than 3,995 complete usable session days and no gap over 168 hours.

The v1 result and raw bytes remain immutable. V2 is a separately frozen, no-download successor.
It changes no price, fills no bar and preserves every incomplete date as `no_trade`. It publishes
one checksummed availability mask per instrument and applies the originally intended usable-data
test to complete dates: at least 3,000 complete session windows, both history edges, valid prices
and no outage over 168 hours. All seven candidates pass v2.

| Instrument | H1 candles | Complete windows | Incomplete / `no_trade` | Longest gap (h) |
|---|---:|---:|---:|---:|
| SPX500_USD | 95,553 | 4,001 | 145 | 86 |
| NAS100_USD | 95,552 | 3,995 | 150 | 86 |
| DE30_EUR | 68,929 | 4,057 | 9 | 131 |
| UK100_GBP | 73,462 | 4,006 | 40 | 117 |
| XAU_USD | 97,058 | 4,018 | 238 | 77 |
| EUR_USD | 101,147 | 4,141 | 211 | 76 |
| USD_JPY | 101,077 | 4,141 | 210 | 76 |

## What A1 passing means

A1 now qualifies these broker-native histories for a separately frozen, intraday-only A2
strategy experiment. Entries and exits must use historical bid/ask, add the frozen 0/5/15 bps
round-trip slippage scenarios, report GBP conversion separately, and be flat before 17:00
America/New_York. Any date marked `no_trade` remains unavailable in every later experiment.

This does not establish profitability, execution access, lawful product eligibility, financing
accuracy for overnight holdings, or live readiness. A new A2 contract is required before any
return is calculated.

## Reproduce

```bash
.venv/bin/pytest -q tests/test_cross_asset_oanda_hourly.py tests/test_cross_asset_oanda_audit.py
.venv/bin/python scripts/validate_cross_asset_research_context.py
```

Do not rerun either immutable hourly artifact root.

