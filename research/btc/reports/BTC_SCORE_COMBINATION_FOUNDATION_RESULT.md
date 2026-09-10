# BTC score-combination foundation result

Experiment ID: `btc-score-combination-foundation-v1`  
Decision: **passed — synthetic infrastructure only**  
Forecast or strategy evidence: **none**  
Actionable arm: `no_trade`

## Result

The repository now has immutable, checksummed contracts for target-aware score catalogues, causal
within-score percentile calibration and fixed same-target convex ensembles. This is not MCS4 and
does not create a universal market score.

`ScoreCatalogueEntry` binds score identity and version to its axis, exact forecast target,
horizon, kind, units, evidence status, permitted uses and evidence digest. Development and rejected
entries can be retained only as diagnostics or controls. `ScoreCatalogue` rejects duplicate
identities and serializes in a deterministic order.

`calibrate_empirical_percentile` computes a deterministic empirical midrank percentile using only
history whose availability timestamp is no later than the raw score's fit cutoff. It preserves the
raw score, catalogue and sample lineage and returns explicit unknown output for insufficient
history, stale raw scores or unknown raw scores. A percentile remains display/model-input metadata;
it is not a probability that the market is favorable and creates no action authority.

`combine_same_target` accepts only a frozen non-negative weight map summing to one. Every member
must have `benchmark` or `accepted` evidence, explicitly permit same-target ensemble use, be known
and current, and match the exact instrument, axis, target, horizon, score kind and units. The
resulting ensemble is always `development`, keeps `actionable_arm_id = no_trade`, and cannot create
a strategy action. Weights are not fitted or revised by this packet.

The existing `DownwardOnlyRiskFusionPolicy` remains authoritative for fusing separately usable
risk caps by their minimum. It was not duplicated or changed. With current evidence, EWMA remains
the only actionable risk benchmark; HAR, semivariance, persistence, reversion and jump outputs
remain rejected diagnostics and carry remains blocked.

## Verification

- 9 focused score-combination tests pass.
- 40 focused plus adjacent market-condition, condition-score, risk and routing tests pass.
- The synthetic qualification report and evidence manifest replay byte-identically.
- Contract and outputs use canonical JSON and SHA-256 lineage.
- No BTC or other market value, outcome, strategy, PnL, 2026 row, partial OB0 data, protected
  service, signal, position or order was accessed or created.

## Disposition

This packet proves only that future eligible forecasts can be represented and combined without
mixing meanings or crossing the action boundary. It does not make any current rejected score
usable and does not activate MCS4. The next strategy step remains selection and pre-result freeze
of one materially new BTC strategy hypothesis; a strategy-specific expected-utility adapter must
wait for that decision.
