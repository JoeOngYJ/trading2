# BTC 4h SMA 10/30 Robustness Test

## Decision

**Not approved for the sealed holdout.** The rule is profitable across the full
development history, but it failed the predeclared calendar-year consistency gate and
has a much larger true drawdown than the original exploratory backtest reported.

## Corrected development result

Using complete, segment-safe 4h candles from August 2017 through December 2025 and
10 bps fee plus 2 bps slippage per side:

- total return: 1,156.3%;
- CAGR: 35.3%;
- mark-to-market maximum drawdown: -75.5%;
- 353 completed trades;
- 34.8% win rate and 1.55 profit factor;
- 50.3% time in market;
- matched buy-and-hold: 1,579.5%, 40.1% CAGR, -86.0% maximum drawdown.

The rule remained profitable at 20/5 and 30/10 bps fee/slippage stress scenarios, but
failed at 50/20 bps. It produced positive calendar returns in only 2017, 2019, 2020,
2023, and 2024; the frozen gate required six positive years.

## Why the earlier result looked stronger

The earlier backtester updated drawdown only after closing a trade, excluding adverse
movement while a position remained open. The corrected implementation marks open BTC
positions to every 4h close. The earlier 2024–2025 profit was real under its simplified
cost assumptions, but it occurred during favourable large trends and did not establish
stable performance across regimes.

This rule remains the primary trend benchmark. It may not be tuned or sent to the 2026
holdout based on this result.
