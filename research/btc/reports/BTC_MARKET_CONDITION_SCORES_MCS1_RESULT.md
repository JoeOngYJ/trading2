# BTC market-condition scores MCS1 result

Experiment ID: `btc-market-condition-scores-mcs1-v1`  
Decision: **passed — metadata and contract infrastructure only**  
Score, model, strategy or PnL evidence: **none**  
Actionable arm: `no_trade`

## Result

MCS1 implemented an immutable `MarketConditionObservation` with instrument, venue, independent
axis, interval, segment, source-window start, observed/available timestamps, finite field values or
an explicit unknown reason, and checksummed lineage. The contract rejects naive or non-UTC time,
future availability ordering, invalid axes, duplicate fields, non-finite values, unknown rows with
values and cross-segment sequences. It creates no score, regime label, signal, route or position.

The metadata-only audit verified 14 frozen manifests, reports and program records by checksum and
produced eight availability records. It opened no candle, trade, funding, feature, label or PnL
file and deserialized no market value.

## Availability decision

| Axis | Research-ready source | Disposition |
|---|---|---|
| Persistence | Segment-aware 5m/4h/1d BTC candles | Ready for a separately frozen score experiment |
| Reversion | Segment-aware 5m/4h/1d BTC candles | Ready for a separately frozen score experiment |
| Volatility | Segmented candles plus official close-only daily source | Frozen EWMA remains the benchmark |
| Downside/tail | Segment-aware 5m/4h/1d BTC candles | Ready for a separately frozen score experiment |
| Jump/change | Segment-aware 5m/4h/1d BTC candles | Ready for a separately frozen score experiment |
| Carry | Completed matched spot/perpetual inputs | Conditional research only; historical fees/margin still constrain a strategy |
| Liquidity/cost | Candle proxies only | Not research-ready without accepted quote/OB1 cost targets |
| Implied risk | Three-window DVOL technical pilot | Blocked pending full source qualification |
| On-chain flow | No approved point-in-time source | Absent |

The legacy derived one-hour manifest fails closed for all candidate axes because it records rows
and checksums but not exact start/end or source-segment boundaries. Any later one-hour score must
rederive completed one-hour observations from the accepted segmented five-minute source under a
new frozen contract. This does not block the existing 4h/daily MCS2 foundation.

Low-frequency liquidity measures may be implemented later as explicitly labelled proxies, but
they cannot be treated as forecasts of protected-fill cost until accepted quote/L2 observations
provide the target. Partial OB0 remains unread and OB1 remains blocked.

## Verification

- Seven focused tests pass.
- A second isolated audit is byte-identical for both the availability report and evidence
  manifest.
- Availability matrix digest:
  `0898ebfca94a25e4bc8d8c25720b0f53d90a01cc4f0f7f7d74b3f1db2a4c16f8`.
- Availability report SHA-256:
  `b181832638bf69c34123ded46f67c9570fc84d36518ebc0be82ab11d4cbcc931`.
- Evidence manifest SHA-256:
  `24867b0db7f0bbe1f28004ba41b3aa0d6d008edddf2fc0c65d694b0105c04a8a`.

## Next permitted action

Freeze MCS2 separately before implementation. MCS2 may add canonical score-output contracts and
past-only mathematical primitives with synthetic fixtures. It may not deserialize BTC values,
choose thresholds, fit a score, calculate PnL, inspect partial OB0 or open an ineligible 2026
partition. MCS3-P persistence remains the first permitted real-data score experiment only after
MCS2 passes.

