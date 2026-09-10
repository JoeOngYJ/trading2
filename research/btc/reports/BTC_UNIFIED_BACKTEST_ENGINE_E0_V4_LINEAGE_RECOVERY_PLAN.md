# BTC unified backtest engine E0-v4 lineage-recovery plan

Stage: `E0-v4`
Scope: lineage repair only
Actionable arm: `no_trade`

## Purpose

E0-v4 repairs a reproducibility failure without changing any economic, accounting, event-order,
cost, failure, pair-close or safety choice frozen by E0-v1, E0-v2 and E0-v3. E0-v3 bound a
paused module and test at mutable active paths. Those bytes were later overwritten before being
archived, so their expected hashes can no longer be reverified. The E0-v3 paused-evidence gate is
therefore irreproducible. This contract never asserts that the missing bytes or hashes verify.

The incident tombstone and all three invalid E1 attempts are retained as negative evidence. The
functionally tested E1-v3 attempt remains unqualified: its former PASS is revoked, it must not be
imported, executed, copied, repaired or used by an oracle or downstream stage.

## Frozen inheritance and boundaries

- E0-v1, E0-v2 and E0-v3 plans and contracts are inherited byte-for-byte by their SHA-256
  digests. If their semantics conflict, the later inherited clarification controls only the issue
  it explicitly clarified.
- E0-v4 adds no economic semantics. It cannot waive, reinterpret or replace an inherited gate.
- The execution-scenario authority and the three mandate authorities remain exact-file bound.
- Work is offline, synthetic and zero-capital. Historical market rows, strategy results, sealed
  2026 data, partial OB0 data, credentials, network/exchange/database/NATS/Freqtrade access and
  production integration remain prohibited.
- Every actionable decision remains `no_trade`.

## Negative-evidence record

The machine contract binds every file in:

1. `unified-backtest-engine-e1-v1-ambiguous-draft`;
2. `unified-backtest-engine-e1-v2-clean-room-violation`;
3. `unified-backtest-engine-e1-v3-stale-v3-lineage`.

It also binds the incident tombstone whose digest is
`2c3e5c7c65ef5b2323689693ed0c1a2e8d7a1fd52566857f04257cb4bee9ae26`.
The tombstone records the two unavailable expected hashes. Their bytes are unknown; absence is not
verification, recovery or evidence of their content.

## Next clean E1 identity

Only after independent E0-v4 acceptance may a new implementation begin under experiment ID
`btc-unified-backtest-engine-e1-v4-clean-lineage` at these new active paths:

- `src/trading_platform/btc_unified_accounting_e1_v4.py`;
- `research/btc/tests/test_btc_unified_accounting_e1_v4.py`.

The implementer must start from the accepted contracts, plans and exact authorities only. The
implementer must not open, read, execute, import, copy, diff, summarize or repair any file under
`research/btc/invalid/`, the tombstoned missing paths, or any prior E1 result or qualification
artifact. Prior terminal values and tests are not implementation inputs.

Before independent E1 review, freeze an immutable candidate snapshot under
`research/btc/candidates/unified-backtest-engine-e1-v4-clean-lineage/`. It must contain exact copies
of the candidate module and tests plus canonical `candidate-manifest.json` binding their hashes,
the E0-v1/v2/v3/v4 contract hashes, authority hashes, experiment ID and creation timestamp. Review
must fail closed if active bytes differ from the snapshot, the snapshot changes, its file set is
incomplete, or provenance cannot be established.

The independent reviewer, not the implementer, may compare the snapshot with invalid attempts.
Qualification requires semantic conformance, independent synthetic oracle reconciliation,
prohibited-import scanning, and no material source reuse. A failure creates another append-only
invalid archive and a new experiment ID; it is never repaired in place.

## E0-v4 gate

E0-v4 passes only when an independent reviewer verifies canonical serialization, every available
bound digest and file set, exact inheritance, the honest missing-evidence disposition, unique clean
E1 paths, snapshot-before-review requirements and all offline/`no_trade` boundaries. Until then,
no E1 implementation, test execution, oracle or downstream work is permitted.
