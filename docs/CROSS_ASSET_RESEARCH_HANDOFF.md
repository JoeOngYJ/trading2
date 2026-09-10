# Cross-Asset Research Session Handoff

Updated: 2026-08-30 17:05 UTC  
Program: `retail-cross-asset-multi-strategy-v1`  
Current stage: `A3` — **rejected; no later stage active**  
Mandate: `retail-cross-asset-research-v7` — offline research only; zero execution authority  
Accepted strategy arms: **0**  
Approved execution instruments: **0**  
Actionable route: `no_trade`

## Latest A3 result

The timestamp-only prerequisite passed and created 30
checksummed development/validation files without deserializing market values, computing economics
or including prospective rows. `cross-asset-a3-overnight-gap-reversion-v2` preserved the mechanism
frozen before A2 results. It lost 11.97% in development and 3.64% in validation at spread plus 5
bps. Development was negative before added slippage; only 2022 and the two US indices were
positive; every robustness and leave-one-instrument-out result lost. Twelve of 17 gates failed.
The ID is rejected and closed. No prospective price was accessed.

Primary contracts:

- `config/experiments/cross-asset-a3-timestamp-prepartition-v1.json`
- `artifacts/agent-level-experiment/cross-asset/a3-timestamp-prepartition-v1/evidence-manifest.json`
- `config/experiments/cross-asset-a3-overnight-gap-reversion-v2.json`
- `artifacts/agent-level-experiment/cross-asset/a3-overnight-gap-reversion-v2/evidence-manifest.json`
- `docs/CROSS_ASSET_A3_GAP_REVERSION_RESULT.md`

## Latest completed strategy evidence

A2 tested one predeclared session-breakout continuation family over all seven A1-qualified markets.
At spread plus 5 bps, development returned -11.99% and validation -5.35%; profit factor was 0.83,
Sharpe -1.37 and only two instruments were positive in validation. Ten of thirteen gates failed.
The ID is rejected and closed. No 2024–2025 economic result was computed.

The integrity review found that the JSONL loaders decoded one cutoff row before breaking. The v1
evidence's no-final-access claim is therefore invalid and the final partition is not clean for A2,
even though no boundary row entered a signal, trade or metric. The A3 hypothesis was frozen before
A2 results, but its partition rule is blocked pending a new experiment ID and source-only
prepartitioning.

The conversion-only GBP_USD source passed with 101,056 H1 rows. It cannot be a strategy instrument.

Primary evidence:

- `docs/CROSS_ASSET_A2_SESSION_BREAKOUT_RESULT.md`
- `artifacts/agent-level-experiment/cross-asset/a2-session-breakout-continuation-v1/evidence-manifest.json`
- `artifacts/agent-level-experiment/cross-asset/a2-session-breakout-integrity-review-v1/evidence-manifest.json`
- `config/experiments/cross-asset-a3-overnight-gap-reversion-v1.json`

## Preceding A1 evidence

The hourly v1 contract archived 224 immutable OANDA H1 bid/ask responses for SPX500_USD,
NAS100_USD, DE30_EUR, UK100_GBP, XAU_USD, EUR_USD and USD_JPY over 2010–2025. V1 rejected five
candidates because a two-percent gate misclassified Sunday-local fragments, holidays and early
closes as corrupt source days. V1 remains rejected.

The separately frozen, no-download v2 successor changes no price and fills no bar. It emits an
explicit availability mask: complete local session windows are eligible and every incomplete
window is permanently `no_trade`. All seven candidates exceed 3,995 complete windows, reach both
history edges, contain valid uncrossed bid/ask and have no gap above 168 hours. A1 therefore passes
for intraday research data only. Zero instruments are approved for execution and zero strategies
are accepted. Oil and bond CFDs remain excluded.

Primary evidence:

- `config/experiments/cross-asset-a1-oanda-hourly-history-v2.json`
- `artifacts/agent-level-experiment/cross-asset/a1-oanda-hourly-history-v2/evidence-manifest.json`
- `docs/CROSS_ASSET_A1_OANDA_HOURLY_HISTORY_RESULT.md`

## Reproduce and verify

From `/data/Trading`, without database or message-bus integration variables:

```bash
.venv/bin/pytest -q tests/test_cross_asset_prepartition.py tests/test_cross_asset_gap_reversion.py tests/test_cross_asset_program.py
.venv/bin/python scripts/validate_cross_asset_research_context.py
env -u TEST_POSTGRES_URL -u TEST_POSTGRES_CONTAINER \
  -u TEST_NATS_URL -u TEST_NATS_CONTAINER .venv/bin/pytest -q
```

Do not rerun or rewrite any OANDA source, hourly, conversion or A2 result artifact root.

## Next permitted action

Do not activate A4 or A5: both require accepted strategy arms and there are none. Do not rerun or
tune A2/A3, select their positive instruments, add leverage, or apply a regime rescue. A materially
new strategy family requires a new program amendment, frozen hypothesis and separate user
authorization before price evaluation.

Do not tune A2, use oil or bonds, claim 2024–2025 as its holdout, inspect partial OB0, access private
broker state, place orders or touch the soak.
