# R2 preparation completed

The S1 manifest identifies an archived 201-record fixed-breakout trade ledger covering three
cost scenarios. Only manifest metadata and generating source code were inspected. No trade rows
were decoded. R2-v1 now freezes exact source hashes, required fields, boundaries, strict R1 input
compatibility, per-trade checks and cash/PnL tolerances before access.

Synthetic tolerance probe: 12 combinations (four reference prices and three cost rates), each
with 1000 recursively funded float trades, were compared against Decimal arithmetic on serialized
input values. The frozen cash threshold is 1e-8 USDT plus 1e-12 times absolute source cash/PnL.
This comfortably covers the observed tiny representation differences while rejecting a 0.01
USDT error at the fixture's capital scale. The implementation must reproduce the probe and
corruption tests before first historical decode. No tolerance changes after viewing differences.

Potential blocker identified in advance: Python float serialization can produce quantities with
more than 12 fractional digits, outside R1's qualified domain. The first R2 gate must report this
and stop if present; do not truncate archived quantities. This is a compatibility question, not
a reason to reinterpret old strategy performance.

Next: implement and synthetically review the frozen R2 gate/replay, then perform its one bounded
archived-trade run if review passes. Contract:
`research/btc/contracts/btc-archived-breakout-reconciliation-r2-v1.md`.
