# Invalid E1 v2 clean-room attempt

Status: **rejected, unqualified and prohibited from use**

The E1-v2 module and tests in this directory are preserved exactly as they existed when an
adversarial review stopped the attempt. Although they used new active filenames and did not
literally import or reference the earlier invalid archive, the reviewer measured 373 exact ordered
lines shared with that prohibited draft and a `SequenceMatcher` ratio of 0.472. This violates the
E0-v2 requirement to implement E1 from scratch without copying the invalid draft.

The attempt was removed from active `src/` and `tests/` paths and must not be imported, repaired or
used as the starting point for a successor.

Test history before the stop message arrived:

1. First focused run: 4 passed, 21 failed. A UTC-offset type comparison defect caused 20 failures;
   one additional failure remained.
2. After correcting only that UTC defect, second focused run: 24 passed, 1 failed. The remaining
   test expected 999.60 USDT despite specifying 0.20 explicit plus 0.40 implicit total costs, for
   which the implementation returned 999.40. This assertion was not changed after the stop.

No historical data, strategy result, metric, oracle implementation, external service, production
integration or executable action was accessed. No E1 qualification passed.

