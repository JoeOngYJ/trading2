# BTC spot/perpetual continuation D1-v2 result

Experiment: `btc-spot-perp-continuation-information-d1-v2`  
Candidate: `btc-spot-perp-continuation-information-v1`  
Disposition: **rejected at the frozen label-coverage gate; no model fitted**  
Actionable arm: `no_trade`

## Outcome

The feature-only phase passed every frozen gate. It produced 2,209 point-in-time daily rows from
the checksum-bound direct spot/perpetual sources, including 383 pre-2021 training rows and complete
2021–2025 evaluation coverage. There was one continuous daily source segment and no invalid row
after the 90-day causal warm-up.

The conditional label phase then scanned all 878,985 checksum-bound five-minute BTC spot rows and
found every requested exact 00:05 UTC entry/exit open. It serialized 2,158 valid same-segment
72-hour labels. The evaluation cohort contained 1,799 labels from 1,823 eligible features, so the
98% overall coverage and every frozen count gate passed. The experiment nevertheless failed its
95% minimum within each evaluation year:

| Year | Valid labels | Eligible features | Coverage | Gate |
|---|---:|---:|---:|---|
| 2021 | 344 | 365 | 94.2466% | fail |
| 2022 | 365 | 365 | 100.0000% | pass |
| 2023 | 362 | 365 | 99.1781% | pass |
| 2024 | 366 | 366 | 100.0000% | pass |
| 2025 | 362 | 362 | 100.0000% | pass |

The 2021 gate needed at least 347 labels; the result was three labels short. Across all years, all
48 lost candidates crossed a declared segment boundary. There were zero missing requested exact
opens and zero invalid serialized labels. Three otherwise feature-ready decisions were separately
excluded because their 72-hour target ended at or after 2026.

This is a source-boundary sufficiency rejection, not evidence that the hypothesized basis/turnover
information is positive or negative. The B0 mean, M0 price controls and M1 candidate model were not
fitted, so no forecast-quality, coefficient or profitability conclusion exists.

## Why the near miss is not tuned

Changing the 95% annual gate, treating distinct five-minute segments as continuous, substituting a
different source, shortening the 72-hour horizon or moving the decision clock after seeing the
three-row shortfall would change the frozen experiment. It would require a new hypothesis ID and a
substantive pre-outcome justification. Interpolating across the source gaps is prohibited.

A successor is not automatically warranted. The available evidence cannot show whether the
candidate features add information because the model gate was never opened. Before reserving a new
ID, the next review should determine whether an independently qualified exact-open source can
legitimately restore the 2021 windows without imputation or cross-venue stitching. If not, close
this candidate and select a materially different regular-clock BTC hypothesis.

## Reproducibility and safety

Nine D1 tests and 17 adjacent D0 tests pass. They cover causal robust scaling, exact-open and
same-segment labels, invalid/future chronology, monthly expanding-fit leakage, deterministic OLS,
seeded block bootstrap, canonical gzip output and offline import isolation. A fresh replay produced
byte-identical ledgers:

- feature ledger: `2181b5df0a20bc0b545634971ebe1b2d6a2313a22fccfe1a04e73b642070a1fa`;
- label ledger: `c3f121be03447c0138424607897d4c87abe09959f168a8b20e307a0b9e1a1a7d`.

The independent closing audit passed all 16 checks, including exact semantic-report replay and the
absence of a model directory. Its report is
`artifacts/agent-level-experiment/btc-focused/spot-perp-continuation-d1-v2/audit/audit-report.json`
with SHA-256 `aa9fbae11b6691ff967df895e97f60de910f9079713b3562bde69e06869f25ae`.
The rejection evidence manifest is
`artifacts/agent-level-experiment/btc-focused/spot-perp-continuation-d1-v2/evidence-manifest.json`
with SHA-256 `bb41f2806c49683364d730ade5cfd3a714d76770af1b00d1b222c8070823871f`.

No strategy, PnL, cost, forecast, position, order, partial OB0 row, protected service, credential or
2026 market row was accessed or created. An explicit model-phase attempt failed closed before
creating a model directory. `actionable_arm_id` remains `no_trade`, and no strategy arm is
accepted.

## Exact commands

Completed primary qualification:

```bash
PYTHONPATH=src:. .venv/bin/python -m unittest -v \
  research/btc/tests/test_spot_perp_continuation_data.py \
  research/btc/tests/test_spot_perp_continuation_data_v2.py \
  research/btc/tests/test_spot_perp_continuation_data_v3.py \
  research/btc/tests/test_spot_perp_continuation_information.py
PYTHONPATH=src:. .venv/bin/python \
  scripts/run_btc_spot_perp_continuation_information.py --phase features
PYTHONPATH=src:. .venv/bin/python \
  scripts/run_btc_spot_perp_continuation_information.py --phase labels
PYTHONPATH=src:. .venv/bin/python \
  scripts/audit_btc_spot_perp_continuation_information.py
```

Reproduce into a new empty directory; never overwrite the preserved primary or first replay:

```bash
REPLAY=artifacts/agent-level-experiment/btc-focused/spot-perp-continuation-d1-v2-replay-<new-id>
PYTHONPATH=src:. .venv/bin/python \
  scripts/run_btc_spot_perp_continuation_information.py --phase features --output "$REPLAY"
PYTHONPATH=src:. .venv/bin/python \
  scripts/run_btc_spot_perp_continuation_information.py --phase labels --output "$REPLAY"
sha256sum "$REPLAY/features/features.jsonl.gz" "$REPLAY/labels/labels.jsonl.gz"
```

Do not run `--phase model` for this experiment. The label report sets
`label_gate_passed=false`, and the runner refuses model fitting.
