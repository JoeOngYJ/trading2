# Invalid E1-v4 candidate — structural underimplementation

The candidate is frozen unchanged and rejected. It must not be imported, executed, copied,
repaired or used downstream. Active and snapshot bytes matched; 23 synthetic tests and compilation
passed; clean-room and prohibited-import checks passed. Those facts do not qualify it.

Independent review found structural omissions: incomplete candidate-manifest schema, no enforced
nine-phase engine clock, caller-supplied funding membership, optional margin checkpoints, missing
closed-form fixtures and episodes, no atomic-pair entry, incomplete Cartesian pair-close failure
semantics, unenforced mandate/cost/cap rules, weak terminal handling, caller-supplied implementation
digest, incorrect daily-loss threshold, missing price-tick/key-collision checks and incomplete
liquidation lineage.

Frozen hashes:

- active/snapshot module: `faf1c244311e90e68f803d62a032a38080b8f1a54f0b33d991037086b1e5424e`;
- active/snapshot tests: `1b0c2cf568f47cbf0d646f64038e187e83a57dcdd39f35ebf9ba0f5046b58d15`;
- candidate manifest: `306c452f84c6781f7629838d7e69efa8b560b2d3b3ac2ffda8ed96bd1c294120`.

Disposition: use a new experiment ID and new active/snapshot paths. Never repair this candidate in
place. No historical market data, strategy result, 2026, partial OB0, credential, external service
or executable action was involved.
