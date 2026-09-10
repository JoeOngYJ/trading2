# Rejected E1-v14 candidate

Experiment ID: `btc-unified-backtest-engine-e1-v14`  
Disposition: **rejected; E1 remains blocked**

This directory preserves the exact frozen modular candidate, its authorities, tests and candidate
snapshot as negative infrastructure evidence. The candidate compiled, its snapshot manifest
verified, and 87 focused tests (95 with the inherited E0 contract tests) passed. Those checks do
not qualify the implementation.

Two independent reviews rejected it because supported construction and facade boundaries could be
bypassed, valid L2 fills emitted a non-zero accounting residual, implementation lineage did not
bind the complete source/run specification, required L2 30/40/80-bps comparison reports were not
emitted, several L2 paths silently used candle execution, fee/tax effects were not integrated into
fills, and pair preflight/recovery was neither complete nor safely atomic. Additional blockers
included incorrect pair direction labels, severe-scenario relabelling, incomplete funding-time
causality, and incorrect sell-side price bounds.

Frozen identity digests:

- plan: `ed3f0c7d26fcbd0aa4c343c1e2e3ee923c7fba76acdabb0be303c2c8f1f1ae1f`
- contract: `d9deacb388f46daa77fda6470b82feba13093b2bb2c4895be9c32b0caa0d1259`
- candidate manifest: `33af0cdb2eea21ce54d16786f17632a51fdbaebd4fdf598b9cfa3e1bf9e2268b`

No historical market row, strategy return, 2026 partition, partial OB0 data, credential, network,
database, NATS, exchange client or protected soak service was accessed. No strategy arm is
accepted and `actionable_arm_id` remains `no_trade`.

The candidate must not be repaired or promoted under this experiment ID. A new implementation ID
may be created only after a bounded design review resolves the supported public API boundary and
splits candle accounting, L2 execution and atomic pair accounting into independently qualifiable
components. E2 and historical reconciliation remain prohibited.
