# Rejected E0-v11 C0 authority boundary

Experiment ID: `btc-unified-backtest-engine-e0-v11-c0-authority-boundary`  
Disposition: **rejected after independent review; no implementation permitted**

Preflight passed nine checks, twenty-one focused tests passed, and eight inherited E0 tests
passed. Both independent reviewers rejected the frozen bundle. Improvements from v10 were present:
a RunSpec registry, exact mandate/scenario-row mappings, exact scenario latency, typed authority
roles, self-excluding registry/spec/context/manifest digests, preserved RunSpec authority records,
and exact inherited-obligation tuples.

Remaining blockers were incomplete on-disk scanning outside a fixed directory list; C0 manifest
authority closure specified by role rather than exact authority bytes; inconsistent nested
AuthorityRef consumers; an ambiguous `scenario` versus `scenario_registry` role rule; a prose-only
RunContext projection rather than an enumerated source/output map; and missing semantic pins for
contract status/schema/subsequent boundary, obligation scope/deferred topics/schema, interface
schema/unsupported caller fields, and authority/design role maps.

Frozen contract SHA-256:
`5d25213af8817dd9a22d3304bbf3c23b61a0e3e97f2326db720269b9051ebe9d`.

Frozen bundle-manifest SHA-256:
`57cf238a5a6b1d70148f0b295643bbc64be86ccab5080b96493437f7738537b8`.

No pass review artifact, implementation, market row, strategy result, sealed data, partial OB0,
credential, service, or trading action occurred. `no_trade` remains the only actionable arm.
