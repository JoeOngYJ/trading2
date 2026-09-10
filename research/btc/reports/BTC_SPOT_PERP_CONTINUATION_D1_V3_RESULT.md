# BTC spot/perpetual continuation D1-v3 result

Experiment: `btc-spot-perp-continuation-information-d1-v3`  
Disposition: **rejected and closed after the information gate**  
Actionable arm: `no_trade`

## Conclusion

D1-v3 resolved the D1-v2 label-definition defect, but it did not rescue the economic
hypothesis. The independently authenticated endpoint-only labels achieved 100% coverage in every
evaluation year. On those labels, however, the two frozen spot/perpetual variables made the
price-only model worse, not better. This candidate is closed without tuning and without another
successor.

This is an information-model result, not a strategy backtest. No entry/exit rule, costs, PnL,
position, order, 2026 data, partial OB0 data, protected service or credential was used.

## What D1-v3 changed—and did not change

D1-v2 required every five-minute bar inside a 72-hour target window to belong to one source
segment. That path-continuity rule was inherited from a path-sensitive taker-flow ledger, even
though the frozen target was only `log(open[t+72h] / open[t])`. D1-v3 therefore changed one rule:
both exact endpoints must be independently authenticated, while interior gaps are counted and
reported rather than used as endpoint-return exclusions.

Everything else was inherited unchanged: the 2,209-row feature ledger, daily decision clock,
72-hour target, price controls, two candidate features, monthly expanding OLS refits, purge,
10,000-replication month-block bootstrap, coefficient-sign theory and rejection gates.

## Source and label gates

- 73 official Binance monthly BTCUSDT spot five-minute archives, December 2019–December 2025;
- all archive hashes, official URLs and archive inventories passed;
- all 2,209 unique requested endpoints existed exactly once and before 2026;
- every official endpoint open matched the S1 exact-open ledger and had positive volume;
- 2,206 total endpoint-return labels were serialized;
- 1,823/1,823 evaluation-eligible labels were present;
- yearly counts were 365, 365, 365, 366 and 362 for 2021–2025, each at 100% coverage;
- 48 candidates crossing interior gaps remain explicit diagnostics: 24 in 2020, 21 in 2021 and
  3 in 2023; no price was interpolated and no venue was stitched.

Thus, the earlier 344/365 result was caused by an overstrict eligibility rule, not by missing
return endpoints.

## Frozen model result

| Model | Aggregate MSE |
|---|---:|
| B0 historical-mean control | 0.002760098760 |
| M0 price-only control | 0.002778148523 |
| M1 price plus spot/perpetual features | 0.002792931256 |

M1 worsened MSE by 0.532107% relative to M0 and was also worse than B0. Its relative MSE change
was negative in 2021, 2023 and 2024, and positive only in 2022 and 2025.

The frozen uncertainty tests did not support incremental information:

- squared-error improvement 95% interval: `[-0.000041790232, 0.000004589668]`;
- incremental rank-IC 95% interval: `[-0.037203375262, 0.050539409890]`;
- top-minus-bottom M0-residual 95% interval: `[-0.007048966567, 0.007835335274]`;
- improvement after excluding the best three months: `-0.000024985579`.

The refit signs also contradict the predeclared continuation theory. Median coefficients were
`-0.001900380525` for basis impulse and `-0.003278469447` for relative turnover; their positive
refit fractions were 0% and 1.6667%.

## Root-cause decision

There were two separate issues:

1. D1-v2 had a measurement-eligibility defect. D1-v3 corrected it with exact official endpoints
   and restored full coverage.
2. After that correction, the frozen feature hypothesis failed broadly: worse aggregate error,
   weak year stability, zero-crossing uncertainty intervals, failure after removing the best
   months and coefficient signs opposite the theory.

The first issue justified one bounded successor. The second means further threshold, horizon,
sign, window or model tuning would be a new search over a rejected hypothesis. Per the frozen
stopping rule, abandon this candidate as a continuation signal. Preserve it only as negative
evidence or a future control.

## Determinism and evidence

An isolated replay reproduced the endpoint, label, forecast and model-snapshot ledgers
byte-for-byte. The independent closing audit passed every check.

- contract: `2fd5da347538e8ff87fa852d26e822148b3110f944cad124a52e7c380151ab47`;
- endpoint ledger: `f9f840f968401f5537a8d627da3761e6ccf62d668a2a31223b0f7fe7b12a8694`;
- label ledger: `6c3bff77c0af80553312d8135640f93879a6148d21112f99525659cf26bf7f09`;
- forecast ledger: `69778b8edc633657b6fbe2fe8d039db33218c5b68e7550c3c7e25cb33311d2da`;
- model snapshots: `f445b29a873952d39f7b155c061bb9eaed2d0a79baa6bde0b5517ac752cba5f3`;
- model report: `a89f1bf3ebab91cb40c99b69faf4e60382d3610376fbcd8843c688d35c64b1ba`;
- top evidence manifest: `c695eae28edbc065d7e06c4cda0542a9c8f163d9fe58bde2497eaef279672852`;
- independent audit report: `20672beffd1b27956c7f2654073b33d2f4dd8a2f572974b877efc8c0b9ce1452`;
- audit manifest: `cf305d56ce0a5841b48018c1829df1ff335af454a216281a360dd18cd60da9d1`.

Reproduce into a new empty directory:

```bash
REPLAY=artifacts/agent-level-experiment/btc-focused/spot-perp-continuation-d1-v3-replay-<new-empty-id>
PYTHONPATH=src:. .venv/bin/python scripts/run_btc_spot_perp_continuation_information_v3.py \
  --phase endpoints --output "$REPLAY"
PYTHONPATH=src:. .venv/bin/python scripts/run_btc_spot_perp_continuation_information_v3.py \
  --phase labels --output "$REPLAY"
PYTHONPATH=src:. .venv/bin/python scripts/run_btc_spot_perp_continuation_information_v3.py \
  --phase model --output "$REPLAY"
PYTHONPATH=src:. .venv/bin/python -m unittest -v \
  research/btc/tests/test_spot_perp_continuation_information.py \
  research/btc/tests/test_spot_perp_continuation_information_v3.py
.venv/bin/python scripts/validate_btc_focused_context.py
```

## Next permitted action

Freeze a materially different BTC hypothesis under a new experiment ID. Do not create a D1-v4,
flip the rejected coefficient signs, tune the target horizon, or use this model as a strategy or
regime gate. EWMA remains the mandatory risk benchmark; zero strategy arms are accepted and the
only actionable arm remains `no_trade`.
