# BTC Taker-Trade-Flow History Expansion

## Outcome

Official Binance BTCUSDT 5m monthly archives from August 2017 through July 2026 were
downloaded or reused and verified against Binance checksum sidecars. The development and
holdout partitions are content-addressed and deterministic.

| Partition | Rows | Segments | Recorded gaps | Status |
|---|---:|---:|---:|---|
| Development, Aug 2017–Dec 2025 | 878,985 | 34 | 33 | Accepted for research |
| Holdout, Jan–Jul 2026 | 61,056 | 1 | 0 | Sealed; pattern analysis prohibited |

The early official archives contain genuine continuity and schema anomalies. The build
preserves 33 source gaps as segment boundaries, excludes 15 incomplete-duration bars and
241 bars shifted off UTC 5m boundaries, and records 35,443 nonzero legacy values in
Binance's documented ignore column. Nothing was forward-filled or timestamp-snapped.

The 2026 holdout is gap-free. Its analysis entry point rejects access without a frozen
hypothesis document bound to the holdout dataset checksum.

## Reproduction

- `scripts/download_btc_taker_history.py` verifies official source checksums.
- `scripts/extract_btc_taker_history.py` validates, segments, and publishes both partitions.
- Manifests and datasets are under
  `artifacts/agent-level-experiment/btc-taker-history/validated/`.

Two complete builds produced identical development and holdout manifest checksums.
