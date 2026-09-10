# BTC Order-Book CryptoHFTData Hour Audit Result

Audit IDs: `btc-order-book-cryptohftdata-hour-day-audit-v1` and
`btc-order-book-cryptohftdata-hour-day-audit-v2`  
Frozen and completed: 2026-08-29  
Decision: **reject for replay fixtures and OB1 backfill; full-day acquisition not permitted**

## Scope

This was a bounded source-qualification audit of the provider's documented Binance spot
BTCUSDT example hour, 2025-08-01 20:00 UTC. It downloaded exactly one order-book object and
one matching trades object through the provider's public, zero-authentication endpoint. It did
not request another hour or date, access 2026, inspect the active or partial OB0 capture, compute
features, labels, forecasts, or PnL, or connect to PostgreSQL, NATS, Freqtrade, an exchange, or a
running service.

The day boundary was frozen as all 24 hours of 2025-08-01, but the other 23 hours could be
downloaded only after the example hour passed. It did not pass, so the day was not downloaded.

## Immutable source evidence

| Dataset | Compressed bytes | Rows | Compressed SHA-256 | Parquet SHA-256 |
|---|---:|---:|---|---|
| Order book | 7,248,513 | 1,674,190 | `58b7dbbe110b15dd2a009f00e77359eaac7df8f3d27af55ca347def1475fffb8` | `953680f591bfdfcb3d75d6463d1a4b99e8efa198bcf2fe579d3152754c5a5ea4` |
| Trades | 1,721,754 | 170,806 | `887e0504dbb15054091d4bdb165a8412bc1ccc67d05d44d0e58623cca6079b8e` | `3121e6e7c296446d01a7227e46c0c6ed44582d70814696c8c55d8dc191244d83` |

The files matched the previously observed ETags
`f4f97d250ff4901ccbb1a85b44657464` and
`52bbe098d4b529d512192510c5aee58d`.

## V1 timestamp-contract rejection

V1 incorrectly required exchange timestamps and receipt timestamps to remain inside the same
hour. The provider partitions by local receipt time. The first book event was generated 86 ms
before 20:00 and received 36.195 ms after 20:00; the first trade was generated 38 ms before the
boundary and received afterward. This is a causal boundary crossing, not missing data.

V1 remains rejected as frozen. V2 reused the exact checksummed bytes and changed only the
timestamp convention: receipt time owns the partition, exchange time must not be in the future,
and arrival lag may not exceed five seconds. The five-second ceiling was anchored to the prior
OB0 latency evidence, not selected from this hour.

## Decisive V2 source failure

The provider's public documentation states that hourly order-book files contain snapshots and
updates, with `event_type=snapshot` initializing replay and `last_update_id` identifying the
snapshot boundary. The actual frozen Binance spot file contains:

- 1,674,190 rows, all with `event_type=update`;
- zero snapshot rows;
- `last_update_id` null on every row;
- `prev_final_update_id` null on every row; and
- no independent initial book state.

The updates themselves are encouraging but insufficient: 35,991 consecutive update groups had
valid `first_update_id`/`final_update_id` ranges, zero within-hour sequence discontinuities, and
a maximum group receipt gap of 492.473 ms. The 170,806 trade IDs were also unit-contiguous. These
facts cannot reconstruct absolute resting depth without a snapshot. Applying deltas to an empty
or invented book would silently fabricate liquidity and invalidate spread, depth, imbalance,
microprice, and execution results.

The V2 runner also retained V1's trade-specific hour-bound check, so it separately reported the
same legitimate 38 ms pre-boundary `trade_time`. Fixing that implementation omission would not
alter the decision: the independently frozen snapshot requirement fails completely. A V3 solely
to remove the redundant trade-time error would therefore add no evidence and is not authorized.

## Disposition

- Do not download the remaining frozen day under either audit ID.
- Do not use these files for OB0, OB1, book features, execution simulation, or strategy evidence.
- Preserve the files as negative provider-provenance evidence; do not redistribute them.
- Reconsider CryptoHFTData only if the provider identifies and supplies, before a new audit is
  frozen, a same-period initial/reconnect snapshot with `last_update_id`, explicit gap/incident
  boundaries, and a deterministic method to join it to these updates.
- The result does not make paid data automatically acceptable. Tardis raw replay remains blocked
  pending final OB0 acceptance and the separately frozen quote/access gates. Forward native
  capture remains the dependable free path.

## Reproduction and verification

The preserved write-once results can be verified without network access:

```bash
.venv/bin/python scripts/audit_btc_order_book_cryptohftdata.py verify-hour
.venv/bin/python scripts/audit_btc_order_book_cryptohftdata_v2.py verify-hour
.venv/bin/python -m pytest -q \
  tests/test_btc_order_book_cryptohftdata_audit.py \
  tests/test_btc_order_book_cryptohftdata_audit_v2.py
```

Evidence:

- V1 contract SHA-256: `9dee3b804e52643c8cd7bf26732e5ebb2faf8f5c2859f810f68f98bda8aad0ac`;
- V1 hour manifest SHA-256: `91b88b167b163992e5a531072b7183a31c32617a9ad80953db614a31646d0dd4`;
- V2 contract SHA-256: `ad9b217de0ef7c644bab897b6de1e6d34ea078c4a9db8ac237d9fe9e1bef1769`;
- V2 hour report SHA-256: `628542cf57655358ca1eb60b2063bc7a97adb28b684c8228bad766a59da4be95`;
- V2 hour manifest SHA-256: `9011e28da83633fee04384500e0bb9908c12d7c74c725ef6b268e4cdb6b1f25d`.
