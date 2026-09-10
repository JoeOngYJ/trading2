# Rejected E1-v11 frozen candidate

Experiment `btc-unified-backtest-engine-e1-v11` passed preimplementation review but failed the
independent post-snapshot economic and structural audit. The submitted active and snapshot suites
passed all 56 candidate-authored probes and the simple independent Decimal fixture outcomes, but
the monolithic implementation did not satisfy the frozen architecture.

Material failures included an exposed construction token and internal mutator; phase, timestamp
and failure-side-effect escapes; fabricated candle partials and misleading order quantities;
incomplete and unemitted Cartesian depth preflight; mutable post-construction severe-cost input;
hardcoded fee assets and incomplete mandate checks; caller-driven gap resolution; non-economic
control tags; incomplete liquidation, episode and artifact lineage; absent MAE/MFE and UTC-day
reset behavior; and canonical string-key collisions.

Every frozen V11 identity, active, snapshot, support and manifest byte is preserved below as
immutable negative evidence. These files must not be imported, executed, repaired, diffed, or
used as clean-room implementation input. The successor is modular and restates all requirements
and probes by value.
