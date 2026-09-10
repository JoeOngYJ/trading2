# Rejected E1-v8 candidate

Experiment `btc-unified-backtest-engine-e1-v8` is immutable negative evidence and must never be
imported, executed, repaired, or used as an implementation input.

The frozen candidate passed byte-provenance and its own focused tests, but failed independent
structural review. Its probes were self-referential: they asserted candidate-local behavior instead
of the inherited E0 authorities. Material failures included no direct atomic-pair entry operation,
non-executing same-exposure controls, caller-forgeable implementation and semantic bindings,
unenforced authoritative costs/caps/pair neutrality, caller-declared depth outcome domains,
incomplete pair and gap recovery, and ledger/lineage mismatch against E0.

The `active`, `identity`, and `snapshot` directories preserve the exact rejected bytes. V9 must be
implemented clean-room from accepted E0-v1 through E0-v4 and its independently accepted V9
contract only. It may not inspect this directory.
