# Cross-Asset A1 Twelve Data Recovery v3 Result

Reviewed: 2026-08-29 20:22 UTC  
Experiment: `cross-asset-a1-twelvedata-recovery-v3`  
Decision: **essential source roles accepted for remaining A1 review; A1 still blocked**

## Result

The write-once recovery acquired 51 responses in thirteen quota windows and audited them without
computing returns, PnL, features, forecasts, or signals. Eight instruments passed source-quality
subset review: SPY, EFA, IEF, TLT, GLD, DBC, BIL, and GBP/USD. EEM remains rejected because each
bounded response still contained duplicate dates; v3 did not select or average conflicting rows.

- SPY, EFA, IEF, TLT, GLD, and BIL contain every corrected 2008–2025 US session exactly once after
  exact-equality overlap merging.
- IEF, TLT, and BIL dividend histories expanded from the capped 100-row responses to 178, 163, and
  110 records. Every bounded response stayed below the frozen cap and overlaps agreed.
- DBC contains every corrected exchange session, but the two holiday-labelled records are
  quarantined and all fields begin eligibility on 2009-01-02 because its 2008 OHLC/volume remains
  independently unverified.
- GBP/USD retains 13 explicit missing reference sessions and 60 quarantined labels. The missing
  fraction and maximum three-session run meet the frozen limits; no missing date is filled.
- Split records now preserve provider factors and distinguish price from unit multipliers.

All essential economic roles have a source-qualified representative. This is not an A1 pass:
issuer corporate-action reconciliation, archival-use permission, broker-executable mappings,
account permissions, and costs remain unresolved. EEM remains absent from the qualified subset.
A2 is not permitted and the actionable route remains `no_trade`.

## Verification

```bash
.venv/bin/python scripts/validate_cross_asset_research_context.py
.venv/bin/pytest -q tests/test_cross_asset_calendar_v2.py \
  tests/test_cross_asset_twelvedata_recovery.py tests/test_cross_asset_program.py
```

Do not rerun v3 or overwrite its raw, normalized, report, or evidence artifacts.
