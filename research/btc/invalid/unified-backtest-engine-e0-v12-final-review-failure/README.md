# E0-v12 rejected; custom C0 architecture closed

Reviewed 2026-09-08. Experiment: `btc-unified-backtest-engine-e0-v12-c0-authority-boundary`.
The intact frozen bundle passed nine preflight checks, 25 focused tests and eight inherited
tests. Fresh independent agents `/root/v12_boundary` and `/root/v12_validator` both rejected it.
The earlier Jason/Harvey review sessions were unavailable; no required pass review exists.

The future implementation contract must hash the RunSpecRegistry, which embeds RunSpecs,
which embed the implementation manifest, which hashes the `c0_contract`. If that is the
implementation contract, this is a cross-document checksum cycle. If it means another
contract, that identity is unspecified. Self-excluding individual digest fields do not solve it.

The validator also exempts arbitrary `invalid` directories without checking archive membership.
Both `src/invalid/btc-c1.py` and `research/btc/invalid/new-unregistered/btc-c0.py` evade its
predicate. A nonexistent projection source passes structural interface validation and is caught
only by snapshot pinning, contradicting the plan's claim of semantic tests without pinning.
Both issues were independently reproduced by the primary agent in memory before archiving.

The seven original files are preserved byte-for-byte under `snapshot/` at their original
repository-relative paths. The original manifest is `candidate/pre-review-bundle-manifest.json`;
SHA-256 `82abf80c66c49bb780bf764f17a9c1313bb611002ad6815c642386b2910c1516`.
The context validator verifies every archived byte against this manifest and checks that the
original active files are absent. Historical commands were:

```sh
python3 scripts/validate_btc_unified_engine_e0_v12.py
python3 -m unittest -q research.btc.tests.test_unified_engine_e0_v12 research.btc.tests.test_unified_engine_e0 research.btc.tests.test_unified_engine_e0_v2
```

These commands refer to pre-archive paths; do not restore rejected files to active locations.
Current archive verification: `python3 scripts/validate_btc_focused_context.py`.

Apply the frozen stop rule: no E0-v13 repair or C0 implementation. Next is planning a small
reference backtester. No historical market data, strategy evaluation, sealed 2026, partial OB0,
credentials, network or protected services were accessed. Action remains `no_trade`.
