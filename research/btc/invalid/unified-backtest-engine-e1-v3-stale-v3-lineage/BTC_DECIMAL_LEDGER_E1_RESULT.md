# BTC unified Decimal ledger E1 result

Stage: `E1`  
Disposition: **PASS — E2 independent oracle implementation only is next**  
Actionable arm: `no_trade`

## Implemented

The clean-room module `src/trading_platform/btc_decimal_ledger_e1.py` implements the combined
E0-v1/v2/v3 synthetic accounting contract. It provides exact Decimal spot and linear USD-M
perpetual balances, isolated collateral, signed realized/unrealized PnL, funding ownership,
cost/fee treatment, liquidation, gaps, partial/rejected fills, daily and drawdown entry controls,
terminal guards, episode attribution, canonical row lineage and deterministic atomic-pair entry,
failure and close behavior.

Every event is transactional and phase-ordered. Observed liquidation is terminal. Invalidation is
monotone. Candle fills are all-or-none at their bound source price; qualified quote/L2 paths use a
canonical Cartesian outcome set. Rows remain offline-only and carry `actionable_arm_id=no_trade`.

## Preserved failures

The first E1 draft was stopped before qualification when oracle construction exposed eight E0-v1
ambiguities. It remains checksummed outside importable paths. A second attempt was rejected for a
clean-room violation after substantial overlap with that draft; its source, tests and failure
history are also preserved. Neither attempt is accepted or reusable.

## Verification

Independent closed-form expectations pass, including:

| Synthetic path | Terminal NAV |
|---|---:|
| Spot long 100 to 110 | 1019.37 |
| Perpetual long 100 to 110 | 1019.37 |
| Perpetual short 100 to 90 | 1019.43 |
| Long-to-short reversal | 989.58 |
| Funding-caused liquidation | 982.17, invalid |
| Exposed gap severe close | 979.68, invalid |
| Atomic-pair second-leg failure | 999.45, invalid |

The focused suite passes 38 tests; the combined E0-v1, E0-v2 and E1 suites pass 46 tests. Python
compilation passes. AST review found no float literals. Imports are standard-library only, with no
network, database, NATS, Freqtrade, exchange, strategy or metric dependency. Similarity to the two
invalid drafts is low and contains no substantial copied block.

Final checksums:

- module: `d70cca4f0a51e3873b92023a7fadd3f1d3d7440a541e7d5a0121b26e9e8c89f5`;
- tests: `ba56c8011312279f2ade79d9e54a1a017e02051798748a142b8c8c092f7662b0`.

## Boundary

E1 accepts synthetic accounting infrastructure only. E2 must implement a structurally independent
oracle that consumes canonical fixture/event JSON and shares no kernel code, dataclasses, ledger,
execution helper or metrics implementation. Historical reconciliation remains prohibited until
E2 and E3 pass.
