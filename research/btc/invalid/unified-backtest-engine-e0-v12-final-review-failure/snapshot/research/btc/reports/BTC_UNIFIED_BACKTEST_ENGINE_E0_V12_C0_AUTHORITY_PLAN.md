# BTC unified backtest engine E0-v12: final exact C0 authority boundary

Experiment ID: `btc-unified-backtest-engine-e0-v12-c0-authority-boundary`  
Stage: design qualification only  
Actionable arm: `no_trade`

## Falsifiable claim

Through one supported offline-Python entry point, C0 can resolve a repository-owned frozen
`run_spec_id` into an immutable identity-and-lineage `RunContext`. The caller supplies no economic
value. C0 rejects malformed input, unsafe or changed authorities, unknown identities, invalid UTC,
incompatible selections, incomplete C0 lineage, and any premature C0-C6 implementation.

The claim is deterministic behaviour through the supported public API, not security against
hostile Python code, filesystem access, reflection, monkey-patching, or interpreter modification.

## Exact C0 scope

C0 owns duplicate/non-finite JSON rejection; canonical JSON; safe relative paths; exact file
path/role/size/SHA-256 bindings; selected RunSpec, mandate, adapter, execution mode and scenario
identity; a closed compatibility table; C0-only implementation-manifest identity; and construction
of `RunContext`. Its manifest cannot identify or accept dependencies from C1-C6.

The future C0 implementation contract must bind one `RunSpecRegistry` file by exact path, size and
file digest. The registry has unique RunSpec IDs and a self-excluding content digest; each RunSpec
also has a self-excluding digest. RunContext preserves the registry authority and digest, selected
RunSpec digest, every selected AuthorityRef, exact scenario-row digest and C0 manifest digest.

`C0Manifest.authorities` must equal the interface's five exact path/role/size/hash tuples: this
v12 design contract and E0-v1 through E0-v4. `C0AuthorityRef` is consumed only inside C0;
`ContextAuthorityRef` is produced by C0 for explicit C0-C6 consumption. Retyping preserves all
four authority values exactly.

`C0Manifest.manifest_digest` is SHA-256 of canonical JSON after removing only
`manifest_digest`. `RunContext.run_context_digest` uses the same rule after removing only
`run_context_digest`. Returned records and nested lists/mappings must be recursively immutable.
UTC is a real calendar timestamp encoded with `Z` and exactly six fractional digits.

## Public boundary

`build_run_context(run_spec_id: NonEmptyIdentifier) -> RunContext` is the only supported future
entry point. RunSpec includes exact `scenario_id`, scenario-row digest, scenario authority, mandate ID, adapter ID,
execution mode, latency rule, partition bounds, and authority records. Allowed mandate/adapter/mode
tuples, mandate paths/hashes, scenario authority and scenario-row hashes are machine enumerated in
the interface specification. Bound candle latency is exactly `0`, matching the authority rows.
The interface also enumerates every RunSpec/registry/manifest source for every RunContext output;
an extra, missing or differently sourced output is invalid.

## Not owned or closed

All market rows and economic event timestamps, targets, orders, fills, accounting, residuals,
fees/taxes, funding, collateral, margin/liquidation, gaps, candle/L2/pair execution, controls,
reports, and strategy logic remain binding but unresolved work for separately frozen C1-C6
contracts. E0-v12 owns only precise nested inherited pointers that apply to C0; it does not claim a
coarse object containing downstream economics.

## Review and gates

The pre-review manifest freezes the exact path-to-role-to-size-to-hash map. Semantic mutation tests
run without digest pinning; on-disk preflight additionally pins exact canonical documents. The
future-path predicate scans the whole repository, excluding only immutable invalid evidence,
tool/cache directories and the exact v12 design paths. It rejects BTC C0-C6, E1-v15 and E2 paths
regardless of directory or component noun.

Two reviewers must independently write separate, checksummed review artifacts with different
reviewer IDs and roles. Qualification binds both reviews and the frozen bundle. No combined
self-authored review can satisfy the gate.

## Stop/go

On pass, only a new synthetic-only `btc-backtest-authorities-c0-v1` implementation contract may be
frozen. On failure, archive v12 and stop this custom C0 architecture line. No implementation occurs
in E0-v12. E1-v15, E2,
historical or sealed data, strategy evaluation, partial OB0, credentials, network, protected
services, paper trading and live trading remain prohibited.
