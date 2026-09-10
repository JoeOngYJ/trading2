# Rejected E0-v5 component-boundary design

Experiment ID: `btc-unified-backtest-engine-e0-v5-component-boundaries`  
Disposition: **rejected after freeze; no component implementation permitted**

The exact frozen contract, plan, matrix, specifications, validator and tests are preserved here.
The structural preflight and ten focused tests passed, but two independent reviewers rejected the
design. Blocking defects were inconsistent failure ownership, a missing target-to-order producer
edge, false universal timestamp requirements, missing exact interface field/type schemas, no
machine E0-v1-v3 obligation-to-component compatibility registry, incomplete C6 dependencies on
future control extensions, weak mutation validation, incomplete forbidden-path matching and an
incomplete reviewed-bundle manifest design.

Frozen contract SHA-256:
`91fcec0a130db665185162c280c0c4f11439cb329fac43c7ad72ae4976e9c32e`.

No pass review artifact was created. No engine, oracle answer, historical row, strategy result,
2026 data, partial OB0 data, external service or protected soak was accessed. The only actionable
arm remains `no_trade`. This bundle must not be repaired or promoted under the same ID.
