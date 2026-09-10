# R2 synthetic implementation review

Reviewer: independent subagent `/root/r2_review`. Date: 2026-09-08.
Disposition: PASS for freezing the implementation and proceeding to the exact
archive compatibility gate authorized by R2-v1.

Reviewed frozen contract, replay implementation, accepted R1-v2 implementation,
and synthetic tests. No archived trade files were read or decoded and `run_archive`
was not called during this review.

Reviewed SHA-256 bytes:

- `research/btc/contracts/btc-archived-breakout-reconciliation-r2-v1.md`: `8a4a9ee52eee4ed4e1400d3495c2d08e57fa78a514c17f71f2384c2ae83fec49`
- `research/btc/reconcile_r2.py`: `4fc1d2a3b3eb3dd3df18568e9ab7e993639270ebdcd42838ba44f6eca09a8c87`
- `research/btc/tests/test_reconcile_r2.py`: `3f75af599e70c56a3e9482fb9dc98306f5062019ca7e0bf6e2338f45dd95535f`
- `research/btc/reference_r1.py`: `b86d6d3be65f2d6b4b5e5c3e0e797b811ef4a33f04effa0a6341358f68d438ad`

Command: `python3 -m unittest research.btc.tests.test_reconcile_r2 -v`.
All four test methods pass, including 12 independent 1000-trade float chains
covering four price levels and three side-cost assumptions. Independent exact
cash is carried across each full chain; all four archived cash/PnL values are
compared, and 0.01 USDT corruption is detected.

Verified that incompatible event precision stops before accounting, exact source
bytes are checked before archive decompression, and scenario counts/order,
timestamps, numeric positivity, duplicate JSON keys, checksum/size and symlink
failures are covered. Per-scenario accounting failures are retained while the
other scenarios are reported. The Fraction oracle derives balances from mapped
input events, and source cash carryforward has an explicit tolerance comparison.

Review identified and resolved two issues before freeze: the initial float test
reset its exact cash every trade instead of measuring cumulative drift; and a
single accounting exception prevented the remaining scenarios being reported.
Boundary and checksum regression coverage was also expanded.

This acceptance qualifies only the synthetic replay and its entry gate. It does
not establish that archive precision is compatible, that historical arithmetic
reconciles, that execution timestamps are valid, or that any strategy is profitable.
