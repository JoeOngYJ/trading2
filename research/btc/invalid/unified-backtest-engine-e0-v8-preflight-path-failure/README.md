# Rejected E0-v8 C0 authority boundary

Experiment ID: `btc-unified-backtest-engine-e0-v8-c0-authority-boundary`  
Disposition: **rejected during frozen preflight; no implementation permitted**

The exact frozen bundle is preserved here. Nine structural preflight checks passed, but one of
seventeen focused tests correctly failed: the premature path
`research/btc/contracts/btc-unified-backtest-engine-c1-v1.json` escaped the future-component
predicate. Eight inherited E0 tests passed. No independent pass review was requested or created.

Frozen contract SHA-256:
`c790778d6534b9b2ad3fb23cc9550cc396f845510b089aa2d1c0bdd64c27c784`.

No implementation, oracle answer, historical row, strategy result, 2026 data, partial OB0,
credential, external service, or protected soak was accessed. `no_trade` remains the only
actionable arm. This identity must not be repaired or promoted.
