# Rejected E0-v6 over-broad downstream contract

Experiment ID: `btc-unified-backtest-engine-e0-v6-exact-component-contracts`  
Disposition: **rejected after freeze; no component implementation permitted**

The exact frozen contract, plan, failure matrix, interface and inherited-obligation
specifications, validator, tests, and pre-review bundle are preserved in this directory.
Mechanical validation passed eight preflight checks, seventeen focused tests, and the inherited
E0 tests. Two independent reviewers nevertheless rejected the design.

Blocking defects included incomplete type expansion and consumer ownership, missing account and
pair-plan fields and edges, non-exhaustive timestamp rules, an incomplete and sometimes incorrectly
owned inherited-obligation registry, placeholder C6 pair-control dependencies, incomplete
forbidden-path matching, and insufficient reviewed-bundle role binding. More fundamentally, the
attempt tried to freeze downstream accounting, candle, L2, pair, control, and reporting semantics
in one component-design stage. That repeated the monolithic-boundary failure rather than producing
independently qualifiable components.

Frozen contract SHA-256:
`a9dde626861f434772f85ce11c6470ed8bb59b6e56d54c328308be176c3f9ae8`.

Pre-review bundle-manifest SHA-256:
`17a0010d6ec00fbd84e8321eebdbc7d9b5e12afbccc6c9a971a70a997ee5a6da`.

No pass review artifact was created. No engine, oracle answer, historical row, strategy result,
2026 data, partial OB0 data, external service, credential, or protected soak was accessed. The
only actionable arm remains `no_trade`. This bundle must not be repaired or promoted under the
same ID.
