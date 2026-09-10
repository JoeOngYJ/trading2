# BTC safe delta-neutral funding carry risk v2 result

Experiment ID: `btc-safe-delta-neutral-funding-carry-v2`  
Decision: **risk implementation passed; timing alpha rejected**  
Actionable arm: `no_trade`

## Result

The frozen 25%-per-leg implementation repaired the margin-safety failure of rejected carry v1,
but the unchanged 60/30 bps funding-timing rule again failed against same-exposure always-on
carry. This closes the timing rule without accepting a strategy arm.

The evaluation uses already-consumed 2024–2025 evidence and is not promotion evidence.

| Implementation | Net return | CAGR | Max drawdown | Return/exposed day | Trades |
|---|---:|---:|---:|---:|---:|
| Funding-gated, 30 bps | 2.95% | 1.46% | 0.21% | 0.00679% | 6 |
| Funding-gated, 80 bps | 1.33% | 0.66% | 0.75% | 0.00307% | 6 |
| Always-on, 30 bps | 7.75% | 3.81% | 0.14% | 0.01061% | 1 |

Primary gated annual returns were 2.75% in 2024 and 0.27% in 2025. Severe-cost 2025 was negative
at -0.39%, although the complete severe evaluation remained positive.

## Risk implementation

Every frozen risk gate passed for the gated strategy:

- zero observed planning-margin breaches;
- zero 20%-up-shocked margin breaches;
- zero entry margin-ratio rejections;
- zero risk exits;
- minimum shocked margin-equity/maintenance ratio: 9.5117 versus the frozen 2.0 minimum;
- both evaluation calendar years positive at primary cost;
- funding cashflow positive;
- concentration gates passed.

The same-exposure always-on control also had zero observed and shocked breaches. Its minimum
shocked ratio was 2.0719, only modestly above the frozen 2.0 boundary. This remains planning-model
evidence, not a claim about historical exchange liquidation rules.

## Attribution

At primary cost, the gated strategy's 29.47 USDT net profit on 1,000 USDT decomposed into:

- funding cashflow: +38.59 USDT;
- spot price PnL: +180.05 USDT;
- perpetual price PnL: -179.48 USDT;
- net basis convergence: +0.57 USDT;
- explicit fees: -6.46 USDT;
- implicit costs: -3.23 USDT.

The exact signal windows without funding lost 0.89%; funding-only after the same costs returned
2.89%. The intended funding mechanism therefore remains real in this development sample.

## Sizing is not alpha

The rejected 49%-per-leg v1 returned 5.83%; v2 at 25% returned 2.95%. Normalized by leg fraction,
the returns were 0.118944 for v1 and 0.117892 for v2. The small difference is execution rounding
and compounding. Lower exposure repaired collateral safety and approximately scaled return down;
it did not improve the signal.

## Why the strategy remains rejected

The frozen gated strategy earned 0.00679% per exposed day, while same-exposure always-on carry
earned 0.01061%. Its incremental timing value was therefore negative by 0.00382 percentage points
per exposed day. The entry gate caused more turnover and missed funding without improving economic
efficiency.

This is the second independent failure of the unchanged timing claim. Do not tune the 60/30 bps
thresholds, select a different lookback, raise exposure, relax the shock or add a regime filter.
Close the funding-timing hypothesis.

Always-on carry is not accepted either: its evidence contains one continuous evaluation trade,
the period was previously consumed, collateral opportunity cost is not modeled, its shocked
margin ratio approached the planning boundary, and effective-dated fees, margin, liquidation,
ADL, venue and account evidence remain promotion blockers. It may remain a structural benchmark
or enter a separately frozen prospective observer, but it cannot be promoted from this backtest.

## Reproduction and evidence

The isolated replay reproduced the report and primary trade ledger byte-for-byte. The independent
audit passed all checks.

- contract: `bbc26048579c5078ac4e2eeb6262ffc80489a5688b8cd6714ba7f4aad56c9ec8`;
- report: `b894aec7a10675a6ace2169f73e8797aeaf51ba235c14eaff34d311f4d56b254`;
- primary trades: `3820c0cad386259be388c0164fd57c97b21a24e58a9b9ad3f988e253797bd6aa`;
- evidence manifest: `4fbfc4be0e91768a92717a84ad4470c619ed674f2463fdc429cc998eac938e1b`;
- audit report: `9426d413900cf100d840e69aa1893bf57287e71fa168ff595f5a96784f8b7d81`;
- audit manifest: `ec562ee8342b3a55ba57247bc58f94b8da6659298bdea595cc3812aa1214fb72`.

```bash
PYTHONPATH=src:. .venv/bin/pytest -q tests/test_btc_carry.py tests/test_btc_carry_risk_v2.py
REPLAY=artifacts/agent-level-experiment/btc-focused/safe-delta-neutral-funding-carry-v2-replay-<new-empty-id>
PYTHONPATH=src:. .venv/bin/python scripts/backtest_btc_safe_funding_carry_risk_v2.py \
  --output "$REPLAY"
.venv/bin/python scripts/validate_btc_focused_context.py
```

## Next permitted action

Preserve safe 25%-per-leg always-on carry as an unaccepted structural benchmark. For new alpha
research, freeze one materially different BTC strategy under a new experiment ID—preferably a
continuous, causal long/short trend hypothesis rather than another funding threshold, sparse event
catalogue or regime rescue. No strategy arm is accepted and `actionable_arm_id` remains
`no_trade`.
