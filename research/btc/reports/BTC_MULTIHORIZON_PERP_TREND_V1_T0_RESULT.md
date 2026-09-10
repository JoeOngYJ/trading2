# BTC multi-horizon perpetual trend v1 — T0 result

Decision: **T0 passed; synthetic T1 implementation is permitted**  
Strategy return accessed: **no**  
Actionable arm: `no_trade`

The checksummed official Binance archive contains 52,608 continuous BTCUSDT USD-M hourly bars
from 2020-01-01 through 2025-12-31 and 6,576 funding events. Across the experiment boundary there
are zero missing hours, zero missing scheduled eight-hour funding events, no funding observation
later than the permitted next hour and no 2026 row.

The completed 84-day feature window first becomes eligible at the 2020-03-26 00:05 UTC decision,
with execution no earlier than the 01:00 open. There are 2,107 eligible daily decisions and 52
ineligible warm-up decisions. Missing history or the next execution open fails closed.

The preliminary T0 artifact is preserved as invalid implementation evidence. It expected 25 March
and 51 warm-up decisions; the inclusive endpoint correctly reaches one hour before the archive on
25 March, so eligibility begins on 26 March and there are 52 warm-up decisions. That error was in
the audit assertion, not the frozen hypothesis, source or strategy parameters. The corrected T0-v2
artifact passes every gate. Neither run calculated a trend component, direction, position, cost,
return or PnL.

## Evidence

- corrected report: `f5a1a06ae4cfa39b47bc1d09a4546777117431427e46d6af1b858b65d380aff8`;
- corrected manifest: `c3e3a9ee7fc125288277763051375f1d877c261c0a614e8feb3818c7446365ed`;
- preserved preliminary report: `36049f7b92ea32633d887e39746831e44778257a4cc98c549c18a87e0f9b7150`;
- audit script: `5c776c34488b86f4e1d867723f09344539ac804307ff81adcf0b5451ef4ab15d`;
- focused tests: `9326f91be6603d8ea69da3cc166af3ac991f78d3d0928aa98722cac338aef262`.

## Next permitted action

Implement T1 synthetic tests for feature formula, signal thresholds, long/short funding signs,
next-hour fills, reversals, costs, margin stress, gap neutralization, controls and deterministic
serialization. Do not run the historical strategy or inspect any return until T1 and its
independent implementation audit pass.
