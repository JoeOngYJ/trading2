# Invalid E1-v6 candidate — structural and semantic failure

E1-v6 is frozen unchanged and rejected. Active and snapshot bytes matched, the manifest payload
hashes verified, compilation passed, 38 synthetic tests passed, prohibited-import checks passed and
source similarity to earlier invalid attempts was low. Those facts do not qualify it.

Independent review found that the manifest used the wrong creation-time field; protective-phase
and terminal guards were bypassable; some failed transitions mutated state without a fill record;
pair-entry recovery was not fully preflighted; true partition controls and gap boundaries were not
implemented; partial-depth Cartesian completeness and severe-price ownership were not proven;
mandate, cost, rule and source bindings were incomplete; delayed state was caller-controlled; and
liquidation/episode rows could not be independently reconciled. Risk thresholds and canonical
Decimal/tick/key handling passed structurally.

The candidate must not be imported, executed, copied, repaired or used downstream. A successor
must use a new experiment ID and must not read this archive. No historical market data, strategy
result, sealed 2026 data, partial OB0 data, credential, external service or executable action was
involved.
