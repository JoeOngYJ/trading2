# BTC unified backtest engine E0-v7: C0 authority boundary

Experiment ID: `btc-unified-backtest-engine-e0-v7-c0-authority-boundary`  
Stage: design qualification only  
Actionable arm: `no_trade`

## Falsifiable claim

A small C0 boundary can deterministically resolve one frozen `run_spec_id` into an immutable,
checksummed `RunContext`, while rejecting malformed JSON, unsafe paths, changed authority bytes,
incompatible mandate/adapter/scenario selections, and incomplete component lineage. The supported
public caller supplies only `run_spec_id`; it cannot submit a price, timestamp, fill, target,
balance, order, or accounting result.

This is an ordinary offline-Python API contract. It does not claim security against hostile code
with filesystem access, monkey-patching, reflection, process injection, or modified interpreter
state. Qualification proves deterministic fail-closed behaviour through the documented public
entry point and frozen files.

## Narrow scope

C0 owns canonical JSON parsing and serialization, safe repository-relative path resolution,
SHA-256 and byte-size verification, unique role binding, RunSpec selection, compatibility checks,
accepted dependency-manifest identity, and construction of `RunContext`.

C0 does **not** own market rows, timestamps of economic events, targets, orders, fills, fees,
funding, collateral, liquidation, candle execution, L2 execution, paired execution, controls,
reports, or strategy logic. Those are future C1-C6 contracts. Existing E0-v1-v4 economic
requirements remain binding source requirements for the future components, but E0-v7 neither
assigns nor closes them.

## Frozen public boundary

The future implementation may expose exactly one supported entry point:
`build_run_context(run_spec_id: NonEmptyIdentifier) -> RunContext`.

Run specifications and their referenced files are repository-owned frozen inputs. Direct
construction of internal records is unsupported. The returned record contains identity and
lineage only; it is not a trading instruction and cannot be converted into a production signal or
order.

## Qualification gates

1. The interface specification fully defines every nested type and every field's type,
   nullability, producer, and consumers.
2. The exact C0-owned inherited obligations match their source JSON pointers and value digests.
3. Every failure finding has one owner, one independent probe, and one fail-closed disposition.
4. The complete design bundle is bound by exact path, role, size, and digest.
5. Mutation tests reject type, nullability, producer, consumer, obligation-owner, probe,
   qualification-gate, bundle-role, and future-boundary changes.
6. Hyphenated and underscored premature C1-C6 implementation paths are rejected.
7. Two independent reviewers accept the frozen bundle before any pass record is created.

## Explicitly unresolved downstream work

Accounting phase order and residuals; fee/tax assets; funding availability and settlement;
margin, liquidation and gaps; order/target construction; candle fill semantics; L2 latency and
depth; atomic pair preflight/recovery; controls; execution reports; and row-kind economic
timestamps are unresolved here. No downstream implementation may begin from this design pass.

## Stop/go boundary

On pass, the only permitted next work is a separately frozen synthetic-only C0 implementation
experiment. On failure, archive this exact identity and replace it. E1-v15, E2, historical market
data, strategy evaluation, sealed 2026 data, partial OB0 data, network access, credentials, and
protected services remain prohibited.

