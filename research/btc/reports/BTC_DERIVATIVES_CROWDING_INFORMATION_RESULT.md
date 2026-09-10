# BTC derivatives-crowding information result

Decision: **information gate rejected; exact mechanism closed**  
Experiment: `btc-derivatives-crowding-information-v1`  
Evidence: 2020–2023 development only  
Actionable arm: `no_trade`

## What was tested

The frozen hypothesis was deliberately non-directional. Extreme funding, perpetual basis and
CME leveraged-money positioning can represent fragile long or short crowding, so their mean
absolute past-only z-score was tested as a predictor of BTC next-seven-day realized variance and
downside path loss. The incremental comparison was against a causal price-only control containing
the frozen 0.94-decay EWMA variance and absolute seven-day momentum.

Funding and basis were delayed by one completed UTC day. CFTC Tuesday observations were delayed
until Saturday UTC. The two holiday-week CFTC rows dated Monday (`2020-12-21` and `2023-07-03`)
failed closed because the contract did not define their publication timing; the previous valid
Tuesday report was retained. No numeric BTC row after 2023 was deserialized.

## Frozen gate result

| Test | Result | Gate |
|---|---:|---:|
| Complete feature observations | 1,263 | at least 1,000 — pass |
| Walk-forward forecasts / months | 892 / 30 | at least 600 / 24 — pass |
| High-crowding occupancy | 29.37% | 15%–25% — fail |
| Control OOS log-variance MSE | 1.09430 | comparison only |
| Expanded OOS log-variance MSE | 1.09575 | worse than control |
| Relative MSE improvement | -0.1325% | at least +2% — fail |
| Paired monthly error-improvement 95% interval | [-0.00567, +0.00179] | lower bound above zero — fail |
| High-minus-low seven-day variance 95% interval | [-0.00155, +0.00156] | lower bound above zero — fail |
| High-minus-low seven-day downside-loss 95% interval | [-2.269%, +0.395%] | lower bound above zero — fail |

The point estimates do not merely miss a close economic threshold. Adding crowding made the
chronological forecast slightly worse, and high crowding had *lower* average variance and downside
loss than low crowding in the months where both groups existed. Both separation intervals span
zero. The expanding quintiles also classified too many later observations as high and too few as
low, evidence that the crowding-score distribution drifted rather than remaining calibrated.

Yearly incremental forecast improvement was +0.336% in the partial 2021 evaluation, -0.312% in
2022 and +0.012% in 2023. The largest three positive months supplied 44.19% of positive monthly
error improvement. The composite's Spearman association was -0.029 with seven-day downside loss
and -0.029 with seven-day realized variance. These diagnostics are attribution, not permission to
select a signed feature, a different percentile or a favorable year after observing the result.

## Interpretation and next boundary

This exact claim is rejected: absolute extremes across these three series do not provide stable,
incremental BTC seven-day risk information over the frozen sample. Do not tune its windows,
weights, quintiles, target or threshold under the same ID, and do not turn the diagnostics into a
trading rule. The data remain valid as checksummed research inputs and controls; the result does
not establish that every economically different funding/basis mechanism is false.

No data purchase is justified by this result. A next experiment must be separately frozen and
materially different—for example, an explicitly approved delta-neutral carry mechanism with a
new derivatives mandate and full cost/margin data, or another BTC strategy family not selected
from these post-result correlations. The existing fixed breakout, EWMA overlay, BOCPD, HMM and
aggregate-flow studies retain their prior dispositions. No router is permitted because there are
still zero independently accepted arms.

## Safety and reproduction

No order, position, PnL, execution cost, partial OB0 observation, protected service or production
path was accessed. The only route remains `no_trade`.

```bash
.venv/bin/python -m unittest research/btc/tests/test_derivatives_crowding_information.py
.venv/bin/python -m py_compile research/btc/evaluators/evaluate_derivatives_crowding_information.py
.venv/bin/python research/btc/evaluators/evaluate_derivatives_crowding_information.py
```

The evaluator was rerun and reproduced the report and manifest byte-for-byte.

- contract: `caef13a4cf7d5a9023759446feca91d13a5c0f87711f4cf01410799472ae2ea9`;
- evaluator: `0b7474040be30954e90c79ce3130e2ed769cd269baf33436c3facd5d9709b2e5`;
- feature/label ledger: `1eb7a1f423cc1548e15b4284248c9848cc355080fa2e28f791603c16114f6476`;
- predictions: `a37a4ad872b547247f06d98acdba764cadfd9d13679e0d8c0890d3fa92849b35`;
- report: `512a024e3db57a427b265d825d1c6502747191eaab7e8ddcbb838ddc0067e4f3`;
- manifest: `bbb678573a7c0bae1184aad316d93028a1b4d56b57164245479425e4e30fd61b`.
