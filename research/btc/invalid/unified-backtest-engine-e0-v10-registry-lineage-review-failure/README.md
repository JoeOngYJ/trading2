# Rejected E0-v10 C0 authority boundary

Experiment ID: `btc-unified-backtest-engine-e0-v10-c0-authority-boundary`  
Disposition: **rejected after independent review; no implementation permitted**

Preflight passed nine checks, seventeen semantic tests passed, and eight inherited E0 tests
passed. Both independent reviewers rejected the frozen bundle. It lacked a checksummed
`RunSpecRegistry`, exact mandate/scenario authority mappings, exact scenario-row selection,
RunSpec byte lineage and an exact RunContext projection. Candle latency also conflicted with the
bound scenario row. The C0 manifest did not require complete lineage. Adversarial review also found
unvalidated contract scope/prohibition mutations, coordinated obligation-pointer drift, and
additional future-path naming evasions.

Frozen contract SHA-256:
`e15f7f461b93104a4d92ce28a65f68ac049d4d01510075af804602fccf3fdb5c`.

No pass review artifact, implementation, market row, strategy result, sealed data, partial OB0,
credential, service, or trading action occurred. `no_trade` remains actionable.
