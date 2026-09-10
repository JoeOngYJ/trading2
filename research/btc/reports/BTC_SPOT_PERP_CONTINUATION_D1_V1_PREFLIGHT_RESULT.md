# BTC spot/perpetual continuation D1 v1 preflight result

Experiment ID: `btc-spot-perp-continuation-information-d1-v1`  
Disposition: **preflight invalid before any D1 historical row or label**  
Replacement: `btc-spot-perp-continuation-information-d1-v2`

The frozen v1 contract correctly required a missing exact five-minute target open or a target that
crosses a five-minute source segment to be ineligible and never interpolated. Its label gate then
incorrectly required the count of invalid **or cross-segment candidates** to equal zero. The bound
source manifest already records 34 segments, so the latter condition confuses safe exclusion with
data corruption and could reject solely because the loader obeyed the contract.

No D0 daily archive, D1 feature row, five-minute candle row, future-return label, forecast or model
was opened under v1. No strategy, PnL, 2026, partial OB0, protected service, position or order was
accessed or created.

V2 changes only this gate. Missing/cross-segment target candidates remain excluded and counted;
zero invalid **serialized labels** is required; and the frozen overall/per-year coverage and count
gates decide whether the remaining exact same-segment labels are sufficient. Every formula,
timestamp, source, model, bootstrap, sign, stability and safety rule remains unchanged.
