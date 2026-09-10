# Cross-Asset A1 Twelve Data Full-History Result

Reviewed: 2026-08-29 19:43 UTC  
Experiment: `cross-asset-a1-twelvedata-full-history-v2`  
Decision: **rejected; A1 blocked**

## Outcome

The transactional downloader acquired all 25 frozen responses across nine quota windows and
committed one checksummed raw snapshot. The offline audit rejected the history before creating
normalized rows or computing returns, PnL, features, forecasts, signals, or any strategy metric.
The 2026 partition, partial OB0 data, and protected services were not accessed.

The rejection has three distinct causes:

- The independent US calendar implementation had a deterministic bug: its “last Monday” helper
  selected the penultimate Monday, shifting Memorial Day in every year. This invalidates the v1
  calendar artifact even though the provider dates for seven ETFs otherwise match the corrected
  exchange calendar exactly.
- Large endpoint responses need bounded windows. EEM returned 5,000 rows containing 1,592
  duplicate dates and therefore omitted 1,121 corrected exchange sessions. IEF and TLT dividend
  responses each stopped at exactly 100 records, below the frozen completeness minimum.
- Provider anomalies and semantics require explicit treatment. DBC contains two off-calendar
  labels; GBP/USD contains 13 missing weekday labels and 60 off-calendar labels, including 36
  Saturdays; and EEM's `3-for-1` split reports `ratio=0.33333`, `from_factor=3`, and
  `to_factor=1`, contradicting v2's unit-multiplier interpretation of `ratio`.

These are data-contract findings, not evidence that a strategy does or does not work. The v2 raw
snapshot, audit report, and evidence manifest are immutable negative evidence and must not be
silently reinterpreted or rerun under the same ID.

## Successor boundary

A successor is justified, but it must be frozen under a new experiment ID before any request. It
must:

1. generate and checksum a corrected independent calendar while preserving the rejected v1
   calendar;
2. use bounded date windows for EEM time series and high-frequency dividend histories, with exact
   overlap equality and duplicate rejection;
3. preserve all split fields and distinguish price-adjustment ratio from unit multiplier;
4. quarantine off-calendar rows rather than silently treating them as sessions;
5. freeze an economically justified FX missing-session/staleness rule and report every gap; and
6. retain all existing credential, quota, 2008–2025, no-strategy, no-PnL, no-2026, and runtime
   isolation controls.

A1 remains blocked until such a successor passes and the later research-proxy-to-executable-
instrument boundary is reviewed. A2 is not permitted and the actionable route remains
`no_trade`.

## Reproduction

```bash
.venv/bin/python scripts/validate_cross_asset_research_context.py
.venv/bin/pytest -q tests/test_cross_asset_calendar.py \
  tests/test_cross_asset_twelvedata_history.py tests/test_cross_asset_program.py
```

Do not rerun either full-history ID. The v2 source snapshot is write-once.
