# A1 XLON and Listed-Futures Expansion Result

Experiment ID: `cross-asset-a1-lse-futures-expansion-v1`  
Decision: **rejected exact-XLON full history; A1 remains blocked**  
Actionable disposition: `no_trade`

## Frozen scope

The successor mandate adds offline data-research candidates MES, MGC, MCL, M6E and MTN, with
ES, GC, CL, 6E and TN as mechanism-only parent histories. It preserves SWDA, VAGS, SGLN and COMM
as exact XLON cash controls and freezes their inherited usable starts through 2025-12-31.
No derivative, listed fund, strategy, paper route or live route is approved.

The source comparison is deterministic: CME DataMine is preferred unless both sources pass every
gate and Databento is more than 10% cheaper on twelve-month total cost. Any purchase still requires
the user's approval of the exact quote and dataset list.

## XLON result

The new calendar generator binds UK holiday rules, exceptional closures and the repository-owned
official 2025 LSE calendar. The acquisition used calendar v1 because it was frozen before the
provider calls. That audit exposed an independent defect: v1 did not move Christmas/New-Year
half-days to the preceding valid session when 24 or 31 December was not tradable. V1 remains bound
to this rejected experiment; corrected `xlon-uk-rules-2009-2025-v2` preserves the same session set
and moves all 34 half-days deterministically.

The transactionally acquired Twelve Data histories failed the no-duplicate/no-gap source gates:

| Instrument | Raw rows | Unique sessions | Duplicate dates | Conflicting duplicates | Missing sessions |
|---|---:|---:|---:|---:|---:|
| SWDA | 4,095 | 4,094 | 1 | 1 | 9 |
| VAGS | 1,646 | 1,646 | 0 | 0 | 0 |
| SGLN | 3,707 | 3,706 | 1 | 1 | 8 |
| COMM | 2,261 | 2,092 | 169 | 109 | 38 |

VAGS returned 65 provider dividend rows even though the exact issuer share class is accumulating.
They are retained only as an unreconciled provider inventory; none is eligible for cash credit.
No row was deduplicated, forward-filled, selected or normalized after the first frozen failure.

## Decision and next gate

This is a material source-quality rejection, not a close pass. Another call to the same endpoint is
not justified. A new experiment may compare an official LSE source or another licensed vendor for
the affected exact lines, or predeclare an instrument-specific exclusion decision. It must use the
corrected XLON v2 calendar and preserve VAGS's issuer-action conflict.

The futures path remains pending price-blind coverage, retention and quote evidence from CME
DataMine and Databento. No purchase was made. Exact histories, rolls, current contract rules,
margins, GBP conversion and effective-dated costs are unfinished.

No return, PnL, feature, forecast, strategy signal, 2026 observation, partial OB0 data, broker
account, order preview, order, database, NATS, Freqtrade or protected soak service was accessed.

## Reproduce

```bash
.venv/bin/python scripts/generate_cross_asset_xlon_calendar_v2.py --check
.venv/bin/pytest -q tests/test_cross_asset_xlon_calendar.py \
  tests/test_cross_asset_xlon_calendar_v2_successor.py \
  tests/test_cross_asset_a1_expansion.py \
  tests/test_cross_asset_lse_history.py
.venv/bin/python scripts/validate_cross_asset_research_context.py
```

Do not rerun the v1 downloader or auditor into its write-once artifact root.
