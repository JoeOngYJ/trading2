# BTC Upside Compression Breakout BEX1-v5 Result

Status: event-catalogue engineering passed; BEX2 blocked by frozen sample gates  
Experiment: `btc-upside-compression-breakout-v1-bex1-v5`  
Evidence: development-only, non-PnL, not strategy acceptance

## Outcome

The causal catalogue completed successfully on the checksummed 2017–2025 BTCUSDT source,
but the exact frozen compression-confirmation mechanism is too rare for the planned nested
competing-risk model comparison.

| Count | Observed | BEX2 minimum |
|---|---:|---:|
| Model-ready confirmed episodes | 36 | 200 |
| Continuation events | 12 | 60 |
| Range re-entry events | 24 | 60 |

Therefore BEX2 did not fit M0, M1, histogram gradient boosting or XGBoost. The count gate is
price-blind and was frozen before source access; it may not be relaxed under this experiment ID.

## Catalogue attribution

The run found 92 non-overlapping compressed-range setups:

- 36 confirmed upside;
- 46 terminated first by a complete one-hour close below the frozen lower boundary;
- 9 reached the seven-day setup deadline without confirmation;
- 1 reached a source-segment boundary.

All 36 confirmed episodes were model-ready and activity-diagnostic-ready. Within the frozen
seven-day competing-outcome labels, 12 reached the one-sigma continuation threshold first and
24 closed back at or below the frozen range high first. These are event labels, not trades or
profitability results.

The confirmed sample is also chronologically sparse. Model-ready continuation/re-entry counts
were: 2018 `0/1`, 2019 `0/1`, 2020 `1/1`, 2021 `0/0`, 2022 `2/6`, 2023 `1/4`, 2024 `4/5`, and
2025 `4/6`. That cannot support the frozen five outer years plus inner expanding folds or the
per-cause fold gates.

## Safety and interpretation

- No strategy entry/exit simulation, position, return, PnL, fee, cost, leverage or alpha claim
  was computed.
- The final 2025 raw bar was accepted under the frozen raw-close/causal-availability boundary;
  activation decisions at or after 2026 were excluded.
- No 2026 numeric row, partial OB0, network, database, NATS, Freqtrade, exchange or soak service
  was accessed.
- Zero strategy arms are accepted and `actionable_arm_id` remains `no_trade`.

This does not prove that compression breakouts lack economic value. It shows that this exact,
strict, non-overlapping definition does not supply enough independent events for the planned
model complexity on the available development history. Changing the range, quantile,
confirmation, suppression or label requires a new hypothesis and experiment ID; it cannot be
presented as tuning BEX1-v5.

## Reproduction

```bash
.venv/bin/python -m pytest -q tests/test_btc_breakout_events.py tests/test_btc_breakout_models.py tests/test_btc_breakout_drivers.py
.venv/bin/python scripts/run_btc_breakout_event_catalogue.py \
  --contract research/btc/contracts/btc-breakout-event-catalogue-v5.json \
  --experiment-id btc-upside-compression-breakout-v1-bex1-v5
```

The second command is no-clobber by design and now refuses to overwrite the preserved evidence.

## Evidence

- Event catalogue: `artifacts/agent-level-experiment/btc-focused/upside-compression-breakout-v1/bex1-v5/events.jsonl.gz`
- Preflight report: `artifacts/agent-level-experiment/btc-focused/upside-compression-breakout-v1/bex1-v5/event-preflight-report.json`
- Evidence manifest: `artifacts/agent-level-experiment/btc-focused/upside-compression-breakout-v1/bex1-v5/evidence-manifest.json`
- Contract: `research/btc/contracts/btc-breakout-event-catalogue-v5.json`
