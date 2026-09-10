# Rejected E0-v7 C0 authority boundary

Experiment ID: `btc-unified-backtest-engine-e0-v7-c0-authority-boundary`  
Disposition: **rejected after freeze; no implementation permitted**

The exact frozen seven-file design bundle and its pre-review manifest are preserved here.
Preflight passed eight checks, seventeen focused mutation tests passed, and eight inherited E0
tests passed. Two independent reviewers nevertheless rejected the design.

Blocking defects were: no exact selected scenario identity or allowed compatibility tuples;
undefined self-excluding digest domains; a UTC type inconsistent with inherited six-digit UTC and
calendar validity; ownership of a coarse `/data_contract` pointer that accidentally included
deferred economics; ambiguous aggregate consumers; incomplete future-component path detection;
swappable bundle path-role mappings; self-certifiable combined review metadata; no C0-only
component-manifest constraint; and digest-first mutation tests that did not prove the intended
semantic checks.

Frozen contract SHA-256:
`18e507523f0b5a39083e66a394e4d02be14840038b37c8922a1d3a34a9886fd9`.

No pass review artifact was created. No implementation, oracle answer, historical row, strategy
result, 2026 data, partial OB0 data, credential, external service, or protected soak was accessed.
The only actionable arm remains `no_trade`. This bundle must not be repaired or promoted under the
same ID.
