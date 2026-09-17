| Question | Result |
|---|---|
| Raw breakout continuation exists? | UNKNOWN — historical target not computed |
| Primary net expectancy/trade | NOT_RUN |
| 95% interval | NOT_RUN |
| Stress net expectancy | NOT_RUN |
| Severe net expectancy | NOT_RUN |
| Candidate vs random participation | NOT_RUN |
| Random-control rank | NOT_RUN |
| M coverage | 11,700 / 13,002 opportunities (89.986156%); metadata only |
| Number of usable breakout trades | UNKNOWN — candidate not executed |
| Positive entry years | NOT_RUN |
| Best-trade removed expectancy | NOT_RUN |
| Best-month removed expectancy | NOT_RUN |
| Profit concentration | NOT_RUN |
| Worst-five mean | NOT_RUN |
| Observed drawdown | NOT_RUN |
| Legacy vs corrected difference | UNKNOWN — corrected execution not started |
| Final disposition | **BLOCKED — pre-outcome guard qualification failed** |


**We cannot yet determine whether fixing execution preserves or destroys the apparent breakout
profitability. No historical corrected outcome was calculated.** All 44 synthetic tests passed,
but the required guard-integrity check failed before schedule re-verification or historical
execution. This is an engineering BLOCKED result, neither REJECTED nor AMBIGUOUS economic evidence.
The accepted legacy reproduction remains intact.

## Authorized specification and stop boundary

Run/experiment: `btc-breakout-corrected-claim-resolution-v1`.
The user's current authorization accepts exactly one historical claim-resolution execution on
consumed development data. The exact reviewed proposal was copied before any work to
[authorized_contract.md](btc/review_runs/btc-breakout-corrected-claim-resolution-v1/authorized_contract.md), SHA-256
`f9a32cdd2affe259795df86d0c89c9ff4c675b7fe4407e3a02c1126b03a69035`.
Its historical “PROPOSED” wording is preserved byte-for-byte; the separate
[authorization record](btc/review_runs/btc-breakout-corrected-claim-resolution-v1/authorization.json) records the subsequent user approval.
No contract threshold, M definition, seed, cost, signal parameter or evaluation boundary changed.

The authorization explicitly says: “If a required engineering, identity or guard check fails:
BLOCKED. Stop before economic interpretation.” Execution therefore stopped at the first failing
process. No guard exemption, source fix, qualification rerun, economic result or alternative
comparator followed. The one historical execution has not started; it is not resumed automatically.

## Exact failed gate

Command (cwd `/data/Trading`, environment replaced with `PATH=/usr/bin:/bin`, `LC_ALL=C`, `TZ=UTC`):

```text
/data/Trading/.venv/bin/python -I -S -B /data/Trading/research/btc/review_runs/btc-breakout-corrected-claim-resolution-v1/tools/qualify_implementation.py
```

Exit code **1**. All44 unittest cases passed, with0 failures,0 errors and0 skips. The assertion at
[qualify_implementation.py:21](btc/review_runs/btc-breakout-corrected-claim-resolution-v1/tools/qualify_implementation.py:21) then required
44 tests, no skips, the same active profile hook, and an empty denial list. The first three
conditions passed. The denial list contained five rejected optional bytecode-cache read probes:

```text
candidate/src/trading_platform/__pycache__/__init__.cpython-313.pyc
candidate/src/trading_platform/__pycache__/research_ledger.cpython-313.pyc
candidate/src/trading_platform/__pycache__/research_routing.cpython-313.pyc
candidate/src/trading_platform/__pycache__/research_breakout.cpython-313.pyc
candidate/src/trading_platform/__pycache__/research_breakout_v2.cpython-313.pyc
```

These paths are under this run's isolated candidate. All five are absent at documentation time
(existence metadata only). The audit hook denied each attempt before its file operation. Python
continued loading the allowlisted `.py` sources and the tests completed. **The profile hook did
not disappear**, and this is not evidence that protected market data was read. It is a mismatch
between ordinary import cache probing and the new guard's exact-source/no-denials qualification.
`-B` disables writing bytecode; it does not by itself prohibit import cache read attempts.
The [independent blocker review](btc/review_runs/btc-breakout-corrected-claim-resolution-v1/reviews/qualification_blocker_review.md)
records the matching qualified CPython importlib source and its exact hash: the optional cache
read catches `OSError` (including `PermissionError`) and then reads/compiles source.

The guard's `opened_files` field records allowed **audit attempts**, not proof that each file
existed or was successfully read. Its denied accesses remain separately preserved. Module imports
such as standard-library socket/subprocess helpers are not network/process operations; the guard
blocked such operations, and none were attempted in this stage.

The raw test JSON retains its original `status: PASS`, describing unittest success only. The
separate [qualification outcome](btc/review_runs/btc-breakout-corrected-claim-resolution-v1/qualification/qualification_outcome.json)
and [final disposition](btc/review_runs/btc-breakout-corrected-claim-resolution-v1/final_disposition.json) explicitly classify the
overall gate as **BLOCKED**. The original JSON and failure log are not rewritten.

## Work completed before the failure

- Qualified CPython3.13.14 executable/version/flags/platform/zlib/OpenSSL and imported runtime
  identities match the accepted legacy addendum. Executable SHA-256:
  `b200d6c7ae464af64f81808ba246a856b1a1cdf3b2ae7088d37d87d31aebe9ff`.
- Copied42 explicitly pinned source/config/input files into a new isolated candidate; all pins
  passed. Both prior clean legacy builds still match all10 archived outputs exactly. No legacy
  build was rerun or overwritten. The archived forecast hash remains unchanged.
- Verified authorized compressed input
  `316e5789d4b49f79a0adfdd90f0e98c26dd2658060c49fe2366c91dffa2024e8`
  and development manifest
  `506b8839a42fd3c44687020e85e995181a4033e5dbacedfcdc382801d8da18ae`.
- Read only identity/time/segment fields for new topology verification:878,985rows,34segments,
  18,282complete four-hour bars,23evaluation cohorts. Structure agrees with retained Stage3A topology.
  Evaluation stays `[2019-01-01,2026-01-01)`; no2026 row is permitted.
- Froze13,002 opportunities,11,700 M=true and1,302 M=false; froze all199 signal-blind schedules
  and10,000 bootstrap start-index draws before outcomes. Their independent exact regeneration
  check was after the failed assertion and **was not run**. No control returns were evaluated.
- Added isolated cohort/reporting and statistical modules. Their44 synthetic tests passed:
  6clock/channel/M tests,22accounting/chronology tests and16statistics/decision tests. These are
  synthetic results, not market evidence. Separate8 fresh-process guard probes were prepared but
  **not executed** after the stop. The prior35/35 and7/7 suites are attached as accepted historical
  qualification, not represented as freshly rerun here.

Source/runtime/input identities, opportunity/M grids, schedules, seeds, bootstrap specification,
test source hashes and the preserved guard state are in the
[evidence manifest](btc/review_runs/btc-breakout-corrected-claim-resolution-v1/claim_resolution_manifest.json).
The isolated candidate is
`/data/Trading/trading2_codex_handoff/review_runs/btc-breakout-corrected-claim-resolution-v1/candidate`.
Git commit/worktree/dirty identity remains **UNKNOWN**; this is a byte-copy candidate.

## Missing economic evidence

No historical forecasts/signals, raw14-day targets, candidate/control trades, attempted entries,
cash events, valuations, unresolved positions, attribution or outcome bootstrap files exist for
this run. Numerical calls in the synthetic guard record use literal artificial candles/returns
only. M opportunity coverage is structural; actual M entry counts/budgets and year/segment trade
coverage are UNKNOWN until an authorized execution passes qualification.

Full continuous2019–2025 strategy performance remains **UNKNOWN / UNIDENTIFIABLE**. The reviewed
research disposition C remains unchanged. No independent confirmation, alpha acceptance, allocation
or practical execution claim follows. Five-minute OHLC execution limitations and the precise
30-bps screening interpretation remain unchanged in the authorized contract and user authorization.

## Proposed repair for review only

The minimal next work is a synthetic-only guard/import qualification repair. Prefer loading
the explicitly pinned project `.py` sources directly without trying or accepting unpinned cache
bytes. Preserve exact source hashes, denied-access evidence and strict protection of all other
paths. Then qualify that import path, guard probes and the required unchanged implementation
tests under the same runtime. This repair is **not implemented or executed** in this stopped run.
Do not merely erase denials, allow arbitrary `.pyc` files, or relabel the failed gate as passed.
No economic contract revision is proposed. Any continuation must preserve this failed attempt and
the already frozen schedule bytes, and receive coordinating review before historical execution.

**BLOCKED — STOP_FOR_CHATGPT_REVIEW.**
