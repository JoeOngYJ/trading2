# Breakout legacy reproduction repair

Run: `breakout-legacy-repair-20260912-v1`, 2026-09-12. Status: **STOP_FOR_CHATGPT_REVIEW**.

Both new clean legacy builds reproduce every authoritative core artifact exactly and match
each other exactly. The qualified environment resolves the runtime-arithmetic reproducibility
blocker without modifying the frozen implementation, data, costs, parameters or output bytes.

Authoritative reviewed research state remains
[EDGE_RESEARCH_RESET.md](EDGE_RESEARCH_RESET.md) and
[EVIDENCE_INTEGRITY_RESOLUTION.md](EVIDENCE_INTEGRITY_RESOLUTION.md), unchanged. Their prior
disposition C regarding trading edge is preserved. This report resolves the legacy canonical
blocker; it does not replace their research conclusions or contamination assessment.

## Runtime addendum

**This defines an archive-compatible reproduction environment. It does NOT claim that the exact historical August interpreter binary has been recovered.**

The [runtime addendum](btc/review_runs/breakout-legacy-repair-20260912-v1/RUNTIME_ADDENDUM.md) and binding
[runtime_addendum.json](btc/review_runs/breakout-legacy-repair-20260912-v1/runtime_addendum.json) were frozen before the new suites and builds.
Addendum SHA-256: `be2ed72f0f6272ebf422826d6e75bafce41e3432aa8fd3ceac869669e9b9f259`.

| Property | Qualified value |
| --- | --- |
| Interpreter invocation | `/data/Trading/.venv/bin/python` |
| Resolved executable | `/home/joe/.local/share/uv/python/cpython-3.13.14-linux-x86_64-gnu/bin/python3.13` |
| Python | `3.13.14 (main, Jun 23 2026, 15:18:27) [Clang 22.1.3 ]` |
| Executable SHA-256 | `b200d6c7ae464af64f81808ba246a856b1a1cdf3b2ae7088d37d87d31aebe9ff` |
| Platform | `Linux-6.5.0-45-generic-x86_64-with-glibc2.35` |
| Flags | `-I -S -B`: isolated, no site initialization, no bytecode writes |
| Exact child environment | `PATH=/usr/bin:/bin`, `LC_ALL=C`, `TZ=UTC`; no inherited environment |
| zlib compile/runtime | `1.3.2` / `1.3.2` |
| External packages | None; selected paths use the standard library only |
| Historical August binary identity | UNKNOWN; not claimed recovered |

The JSON also records executable size, compiler/build/configuration, float/platform properties,
relevant standard-library source hashes, OpenSSL version, and all 42 copied source/config/input
identities. Actual imported project and runtime module identities are recorded in both build
logs and [legacy_reproduction_result.json](btc/review_runs/breakout-legacy-repair-20260912-v1/legacy_reproduction_result.json); the two imported
inventories match. The runner and dynamically loaded inherited-test source are pinned explicitly,
even when `runpy`/`exec_module` does not retain them in `sys.modules`.

All historically pinned execution sources retain their original identities. The originally
omitted imported dependencies are now explicitly bound:

| Additional dependency | SHA-256 |
| --- | --- |
| `src/trading_platform/research_evidence.py` | `ffbf532eb70caaaee30ffa65f2f07c7f611f50c34079c703aa7708765420837d` |
| `src/trading_platform/research_program.py` | `005ff30148db48d15fb1883e06725248e775866511afe4c0bd85ab3859cc1e55` |

Frozen S1 contract SHA-256:
`9a2000c6f2685a9ae878a024fb3105e7dac8ae968a9d1216b66d8cf3b7122f1d`.
Authorized development input, **original compressed bytes**:
`316e5789d4b49f79a0adfdd90f0e98c26dd2658060c49fe2366c91dffa2024e8`.
Development manifest, original JSON bytes:
`506b8839a42fd3c44687020e85e995181a4033e5dbacedfcdc382801d8da18ae`.
Exact paths and every copied checksum are in [candidate provenance](btc/review_runs/breakout-legacy-repair-20260912-v1/candidate_provenance.json).
Both runners recheck source/input pins and the unchanged loader verifies 878,985 five-minute
rows, 34 source segments, row validity and segment continuity. Aggregation is 18,282 complete
four-hour and 3,024 daily bars, as frozen. No recompression or normalization of source input.

Working directory for both builds:
`/data/Trading/trading2_codex_handoff/review_runs/breakout-legacy-repair-20260912-v1/candidate`.
This is an isolated byte copy, not a claimed Git worktree. Original checkout, failed Stage3A
build, original archive and retained August replay remain intact. Git commit/dirty identity
is UNKNOWN; no Git identity is invented. No merge, push, deployment, service or bridge action.

## Build 1

`legacy-repair-build-1` started in a fresh process with a previously nonexistent output directory:
`/data/Trading/trading2_codex_handoff/review_runs/breakout-legacy-repair-20260912-v1/candidate/artifacts/agent-level-experiment/btc-regime-routing/legacy-repair-build-1`.

Actual wrapper command (with the cwd and clean environment above):

```text
/data/Trading/.venv/bin/python -I -S -B /data/Trading/research/btc/review_runs/breakout-legacy-repair-20260912-v1/tools/run_legacy_repair.py legacy-repair-build-1
```

The wrapper invokes the unchanged `scripts/build_btc_regime_research_ledger.py` through
`runpy`, with only `--output-dir` set to the new path. Full actual runner argv is preserved.
Build exit 0; canonical verifier exit 0; 10/10 archived artifacts match by SHA-256 **and actual
byte comparison**. Exact unrounded scenario, control, aggregation and condition assertions pass.

[Build1 command/runtime/guard log](btc/review_runs/breakout-legacy-repair-20260912-v1/legacy-repair-build-1.log),
[canonical result](btc/review_runs/breakout-legacy-repair-20260912-v1/legacy-repair-build-1-verification.json).

## Build 2

`legacy-repair-build-2` started only after build1's exact canonical gate passed. It used another
fresh process and a previously nonexistent output directory:
`/data/Trading/trading2_codex_handoff/review_runs/breakout-legacy-repair-20260912-v1/candidate/artifacts/agent-level-experiment/btc-regime-routing/legacy-repair-build-2`.

```text
/data/Trading/.venv/bin/python -I -S -B /data/Trading/research/btc/review_runs/breakout-legacy-repair-20260912-v1/tools/run_legacy_repair.py legacy-repair-build-2
```

Only the build ID and corresponding output-directory argument differ. Interpreter, flags,
environment, cwd, wrapper, frozen source and authorized input are identical. Build2 may read
build1's verification status before admission; its guarded producer cannot read build1's
generated artifacts. All candles, features, forecasts, trades and reports are rebuilt from
the frozen input, with no generated-artifact reuse.

Build exit 0; canonical verifier exit 0; 10/10 archive and 10/10 build-to-build byte comparisons
pass, with all exact numerical/control assertions. These are two computational reproductions
of the same consumed history, **not independent market evidence**.

[Build2 command/runtime/guard log](btc/review_runs/breakout-legacy-repair-20260912-v1/legacy-repair-build-2.log),
[canonical result](btc/review_runs/breakout-legacy-repair-20260912-v1/legacy-repair-build-2-verification.json).

## Canonical comparison

Authoritative root:
`artifacts/agent-level-experiment/btc-regime-routing/s1-ledger-v1/`.
Expected identities come unchanged from its retained determinism record. File-set equality,
size, SHA-256 and full byte chunks through EOF are checked. No numeric tolerance, ignored
field, rewritten digest, removed volume or post-processing is used.

Each hash below is identical in **archive, build1 and build2**. Three PASS columns refer to
separate exact comparisons; 30/30 required file comparisons pass.

| Core artifact | SHA-256 shared by all three | Archive/build1 | Archive/build2 | Build1/build2 |
| --- | --- | --- | --- | --- |
| `breakout-forecasts.jsonl.gz` | `c6dda69d4f0ddae3dd13a57e39a49278bbebc3f8def72d29cac79812664511e7` | PASS | PASS | PASS |
| `breakout-reproduction-report.json` | `e4d631998153f2841e54f2d36ee7008a9c5874201f65ad3b8e19bb9bca2a9b61` | PASS | PASS | PASS |
| `breakout-trades.jsonl.gz` | `22d68c6174edc18b055041ba3a32c03c1f8945d9e532b7169bcb370507629809` | PASS | PASS | PASS |
| `candles-1d.jsonl.gz` | `690252f80851a24c3b1f6874af96e4434b1d4978b896144822555e00d0adf5d1` | PASS | PASS | PASS |
| `candles-4h.jsonl.gz` | `df23c3ecccf3945080f52e3103f1335cf0fea03f0b26c19ce50dbb5000f50707` | PASS | PASS | PASS |
| `candles-5m.jsonl.gz` | `3d37dadf416469cef7ce57fb009a1796658b7cf098c1e451045f85436eab46ab` | PASS | PASS | PASS |
| `evidence-boundary-audit.json` | `b0647fcac692f31265b01246317f831c7ff9ab26b838550ac8affa78709696c9` | PASS | PASS | PASS |
| `features-1d.jsonl.gz` | `e68936724c0cfc5a73222ff03da6701f4ba1670b5e5f1970b8edbc94aefd7b1b` | PASS | PASS | PASS |
| `features-4h.jsonl.gz` | `09085d9dc0201e17e964cd9fa16093248dd8bbb98da303e863c7f1eff2dce2a9` | PASS | PASS | PASS |
| `manifest.json` | `5a99488be5dd8fac7b5d1628a3335fc9fb3548745cdb0269604e1d9d860af435` | PASS | PASS | PASS |

Machine-readable full three-way identities and sizes:
[canonical_comparison.json](btc/review_runs/breakout-legacy-repair-20260912-v1/canonical_comparison.json).
The forecast artifact is exactly 1,453,464 bytes and has the required
`c6dda69d4f0ddae3dd13a57e39a49278bbebc3f8def72d29cac79812664511e7` hash in both builds.

## Test results

| Required check under CPython 3.13.14 | New result |
| --- | --- |
| Reviewed synthetic integration suite | 35 passed ; 0 failed/errors/skipped |
| Inherited synthetic suite | 7 passed ; 0 failed/errors/skipped |
| Fresh-process historical guard probes | 7 passed ; 0 failed |
| Legacy runner frozen assertions |Both builds pass exactly, all 3 cost scenarios and controls |
| Canonical archive comparisons | 20/20 exact file comparisons |
| New build mutual comparison | 10/10 exact file comparisons |

These are new executions under the qualified runtime, not relabeled 3.10 results. Logs and
actual argv, interpreter, cwd, environment, timestamps and exit codes are preserved in
[commands.jsonl](btc/review_runs/breakout-legacy-repair-20260912-v1/commands.jsonl), [qualification.json](btc/review_runs/breakout-legacy-repair-20260912-v1/qualification.json),
[integration log](btc/review_runs/breakout-legacy-repair-20260912-v1/synthetic-integration.log) and [inherited log](btc/review_runs/breakout-legacy-repair-20260912-v1/synthetic-inherited.log).
No unrelated suite was added.

The historical guard is copied unchanged. A separate repair-wrapper hook closes the explicit
`os.posix_spawn` gap without modifying the guard or frozen strategy. Synthetic canaries verify
denied corrected import/call, unapproved read/write, network and spawn events, plus permitted
synthetic I/O. They never use protected data paths or actual network traffic. Each probe is a
fresh process because an exception from a Python profile hook can disable that hook.

Both real legacy build logs assert that the same profile hook remains installed before and
after the runner. Each records 1 legacy forecast construction, 1 exit schedule, 3 legacy scenario
simulations, 201 legacy resolver calls and 1 frozen buy/hold control; corrected historical calls 0.
This is a Python audit/profile guard with pinned trusted source, not a claim of an OS network
namespace. Reviewed corrected code is exercised only on the required synthetic fixtures.

All 49 new synthetic/guard tests and all 30 canonical comparisons pass. No new execution or
identity gate failed. Static guard/harness/verifier review is preserved under `guard_review/`.

The following values are **REPRODUCED LEGACY DEVELOPMENT EVIDENCE** only; both runners and
verifiers assert their exact unrounded frozen values. They are not corrected performance:

| Cost case | Trades | Account net return fraction | Mean net trade bps | Maximum drawdown fraction |
| --- | ---: | ---: | ---: | ---: |
| `candle-primary-30bps-rt-v1` | 67 | 0.1693554713741534 | 239.3878505970865 | 0.05024784472933819 |
| `candle-severe-80bps-rt-v1` | 67 | 0.13014101538893663 | 188.31827885602323 | 0.05622661168651377 |
| `candle-stress-40bps-rt-v1` | 67 | 0.16139102227246216 | 229.15354919428668 | 0.05144877565494432 |

Legacy time-in-position exposure is 0.18716464131659763 for each case; entry allocation remains
10%. Those are different quantities. All frozen flat/buy-hold control fields also pass; full
unrounded values are in the result JSON and original contract. No sizing/benchmark was changed.

## Root-cause confirmation

The earlier Python runtime diagnosis is fully supported by the two clean canonical builds.
Current CPython 3.13.14 produces the exact archived aggregate volumes, serialization, lineage,
forecasts and every other core byte. Built-in `sum`, source, JSON and gzip settings were left
untouched. There is no residual mismatch needing a different input, tolerance or code change.
The failed 3.10 Stage3A output remains preserved as failure evidence.

The exact August interpreter binary remains UNKNOWN. What is newly established is a fully
specified current environment that reproduces the archived evidence deterministically.
Archive compatibility and historical binary recovery are different claims.

## Reproduction disposition

**A. LEGACY REPRODUCTION REPAIRED**

This establishes the frozen baseline, not trading alpha. Consumed 2017–2025 development remains
consumed; no sealed 2026 or protected OB0/L2 was accessed. Corrected breakout performance remains
UNKNOWN and **NOT_RUN**. No further HAR/top-two/ridge/cash/funding research or parameter search
occurred. The current research verdict remains C until a separately authorized claim-resolution
exercise produces evidence warranting a reviewed change.

## Proposed corrected breakout contract

Because both legacy builds passed, a proposed specification is now supplied:
[btc-breakout-corrected-claim-resolution-proposed-v1.md](btc/contracts/btc-breakout-corrected-claim-resolution-proposed-v1.md).
It is **PROPOSED — NOT AUTHORIZED — NOT EXECUTED**. It preserves the original ungated 120/60
completed-four-hour-bar breakout, 14-day hold, 4% fixed stop, 10% allocation, cadence and 30/40/80-bps
cases with their original entry caps. No new indicators, filters, model or risk overlay.

The key review choice is the explicit coverage/estimand convention. A continuous 2019–2025
corrected account cannot be recovered through missing intervals under the reviewed strict
gap semantics. The proposal treats existing source segments as separate, declared counterfactual
cohorts and does not stitch their account returns. Boundary entries and unresolved inventory
remain visible. Any coverage-conditioned expectancy result must carry that qualification;
closed-trades-only selection cannot silently establish the full-history claim.

The proposed document fixes signal/entry clocks, warm-up and reset rules, stop/open/scheduled
exit precedence, gap versus observed opening-jump handling, terminal valuation, costs,
attribution, controls, uncertainty, required outputs and SURVIVES/AMBIGUOUS/REJECTED criteria
before corrected results. New coverage/analysis conventions require reviewer acceptance; they
are not smuggled in as previously accepted S1 semantics. A historical caller and its boundary
tests have not been implemented or executed in this repair stage.

## Next recommendation

The provenance prerequisite is satisfied. Review the proposed corrected coverage/attribution
contract before any corrected historical caller or profitability result. No automatic stage
transition, independent-confirmation claim, protected-data unlock or live/paper action follows.

**RETURN FOR CHATGPT REVIEW — corrected breakout claim-resolution is now technically ready for separate authorization.**
