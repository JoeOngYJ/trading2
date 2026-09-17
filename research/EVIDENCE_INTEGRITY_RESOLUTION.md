# Evidence integrity resolution

Run: `evidence-integrity-resolution-20260912-v1`, 2026-09-12. Status:
**STOP_FOR_CHATGPT_REVIEW**. Repository `/data/Trading`; Git commit and dirty state
**UNKNOWN** (`git rev-parse` exited128). This is evidence repair, not an alpha experiment.

Authority: [EDGE_RESEARCH_RESET.md](EDGE_RESEARCH_RESET.md), unchanged SHA-256
`12b17c04a92aa05820811c62593ca6ff3a801309334bf5c7e0cd153846f23820`.
Its reviewed disposition C, research-history reconstruction and contamination boundaries stand.
Funding timing remains closed; HAR remains a useful conditional forecast with failed coverage;
top-two remains favorable but unaccepted; aggregate flow/reversal variants remain closed.
No new hypothesis is selected and no historical performance is rerun.

## Executive conclusion

**The breakout discrepancy is an identified producer/runtime difference, not byte-only
compression nondeterminism.** The exact same source sums volumes differently under the two
available Python runtimes. Those different numerical values enter the archived candle records,
then every forecast's lineage hash. The forecast decisions themselves, features, legacy trades
and legacy summary report agree exactly across the existing artifacts.

This narrows the blocker considerably, but does not pass it. Stage 3A's output differs from
the authoritative archive and its required second build remains unrun. The original archive
is traceable: its retained replay matches all ten core files. The next scientifically justified
action to propose for separate review is a runtime-bound **legacy reproduction repair**, with
the existing byte and numeric requirements preserved. Corrected breakout performance is still
UNKNOWN and unauthorized; the historical coverage policy also still needs reviewer approval.

Other blockers are now better bounded: HAR coverage is fully explained by the frozen source
gaps and window/reset rules; top-two membership cannot be reconstructed from the current
evidence; ridge and cash-ETF remain unqualified diagnostics. Stale summaries are qualified,
and a retrospective experiment ledger records known exposure without claiming completeness.

## Breakout canonical-identity investigation

### Expected and observed artifacts

Expected directory:
`artifacts/agent-level-experiment/btc-regime-routing/s1-ledger-v1/`.
Retained original replay:
`artifacts/agent-level-experiment/btc-regime-routing/replays/s1-replay-Ilirmk4u/`.
Observed Stage 3A directory:
`trading2_codex_handoff/review_runs/stage3a-20260912-v1/candidate/artifacts/agent-level-experiment/btc-regime-routing/stage3a-20260912-v1/build-1/`.
These are existing consumed-development artifacts, not the copied review packet's execution roots.

| Forecast identity | Authoritative archive | Stage 3A build1 |
| --- | --- | --- |
| Filename | `breakout-forecasts.jsonl.gz` | Same |
| Compressed size | 1,453,464 bytes | 1,453,708 bytes |
| Compressed SHA-256 | `c6dda69d4f0ddae3dd13a57e39a49278bbebc3f8def72d29cac79812664511e7` | `a5d634b17d8010587ff0071cee4489d6e5512f184a15b3eaecba7ee26c39db5b` |
| Decompressed size | 7,056,778 bytes | 7,056,778 bytes |
| Decompressed SHA-256 | `3c8adeeca2a30636bfdf29f2ae1a4eae9f6df4ac58a2163469c8e25baf757241` | `bbbaa94893c7a71b5f8606884f68a6deafcd9b5f0ac82fc30662a6c211fcd576` |
| Records | 15,303 | 15,303 |

The original manifest and retained replay both support the expected hash; it is neither a
mistyped expectation nor an untraceable artifact. All ten original core files match the replay
byte for byte. Six of ten Stage 3A core files match the archive: five-minute candles, both feature
files, trades, reproduction report and evidence-boundary audit. The differences are four-hour
candles, daily candles, forecasts and the manifest that records those three identities.
Full hashes, sizes and filesystem modification timestamps are in the
[artifact comparison](btc/review_runs/evidence-integrity-resolution-20260912-v1/breakout_artifact_comparison.json).
Filesystem timestamps are observations, not authenticated historical build dates.

### Producer and input lineage

The [original reproduction instructions](../docs/BTC_REGIME_ROUTING_S1_RESULT.md:81) specify
`.venv/bin/python scripts/build_btc_regime_research_ledger.py`. Stage 3A actually used
`/usr/bin/python3 -I -S -B .../tools/run_legacy.py build-1`; its preserved log records the
unchanged runner and legacy imports. The current `.venv/bin/python` is CPython 3.13.14;
Stage 3A and current `/usr/bin/python3` are CPython 3.10.12. The project declaration
`requires-python = ">=3.10"` does not freeze arithmetic behavior across those versions.

The original S1 manifest pins agree with both current root and isolated Stage 3A bytes:

| File | SHA-256 |
| --- | --- |
| `scripts/build_btc_regime_research_ledger.py` | `510baf32d82195694132035d66dbea43ee68f888c72e6b0ff1fee7c001347242` |
| `src/trading_platform/research_ledger.py` | `6b36311efa28c8f58dec1459df0ee146a9a51efd5ff6504fe5531ea0de00e75e` |
| `src/trading_platform/research_breakout.py` | `973280749d3316a055be4b5e99d0234a5cd1b1eff39ca61c0bfb2d2b320bbf61` |
| Frozen S1 contract | `9a2000c6f2685a9ae878a024fb3105e7dac8ae968a9d1216b66d8cf3b7122f1d` |
| Authorized development CSV.gz, compressed bytes | `316e5789d4b49f79a0adfdd90f0e98c26dd2658060c49fe2366c91dffa2024e8` |
| Authorized development manifest | `506b8839a42fd3c44687020e85e995181a4033e5dbacedfcdc382801d8da18ae` |

All 22 explicit source/config/input comparisons pass; both manifests' input and implementation
maps agree. Additional `research_evidence.py` and `research_program.py` root/candidate hashes
agree, but neither was individually pinned in the original S1 manifest. That historical
dependency gap remains disclosed. See [producer/input verification](btc/review_runs/evidence-integrity-resolution-20260912-v1/producer_input_verification.json).

**The exact original executable checksum and full historical environment are UNKNOWN.**
The recorded original command and exact arithmetic replication support the runtime explanation;
they do not prove that today's 3.13.14 executable is the identical binary used in August.
This task records current executable and standard-library identities under both runtimes.

### Byte, serialization and semantic comparison

All three differing gzip files have the same ten-byte header
`1f8b08000000000002ff`: mtime0, no filename/optional fields, compression marker2, OS255.
Their payload CRCs differ. Decompression preserves the discrepancy. Parsing and reserializing
each existing record with the frozen JSON settings reproduces its own payload exactly.
Repacking each existing payload in memory with the original writer settings reproduces its
own full gzip bytes under both Python environments, despite zlib 1.2.11 versus 1.3.2.
No repacked file replaced any evidence. Compression, newline and key-order differences are
therefore not needed to explain any of these mismatches.

| Comparison of existing records | Exact finding |
| --- | --- |
| Four-hour candles | 18,282 rows; 16,353 differing rows. Only `base_volume` (12,500 fields) and `quote_volume` (12,351 fields) differ. |
| Daily candles | 3,024 rows; 2,968 differing rows. Only `base_volume` (2,604 fields) and `quote_volume` (2,629 fields) differ. |
| Forecasts | All 15,303 rows differ only in `lineage_digest` and `forecast_digest`. Every score, abstention, clock, index, horizon, version and confidence value agrees exactly. |
| Structure | Same field names/types, record counts and corresponding keys; source-row/forecast-index and timestamp sequences strictly increase without duplicates. |
| Numerical scale | Four-hour volume differences at most 5 binary64 ULPs; daily base/quote differences at most 13/12 ULPs. Maximum relative difference is below 1.83e-15. No tolerance was used to declare identity. |

The frozen aggregator uses built-in `sum` for both volumes at
[research_ledger.py:244](../src/trading_platform/research_ledger.py:244).
A diagnostic read only the existing development five-minute ledger's volumes and recorded
aggregate row spans. It did not load new market inputs or calculate price signals or returns.
Across 42,612 aggregate volume fields:

| Arithmetic applied to identical archived source volumes | Matches original archive | Matches Stage 3A |
| --- | ---: | ---: |
| CPython 3.10.12 built-in `sum` | 12,528 | 42,612 |
| Current CPython 3.13.14 built-in `sum` | 42,612 | 12,528 |
| `math.fsum` on either inspected runtime | 42,612 | 12,528 |

The same standalone diagnostic under both runtimes explains all 30,084 differing volume
fields, with zero residual mismatches against the corresponding artifact. A synthetic
`sum([1e16,1.0,1.0,-1e16])` returns 0.0 under 3.10 and 2.0 under 3.13, independently demonstrating
different arithmetic behavior without market evidence. This is a diagnosis, not a proposal
to replace `sum` with `fsum` in frozen source.

The forecast producer hashes the current complete candle dictionary and preceding 120 candle
dictionaries into `lineage_digest`, including volumes that it does not use for the breakout
decision ([research_breakout.py:47](../src/trading_platform/research_breakout.py:47)). It then
hashes the forecast record including that lineage. Independently rehashing these **existing**
records validates all 15,303 lineage hashes and all 15,303 forecast hashes for each build under
both runtimes. No breakout signal, exit or simulation function was imported or called.
This proves the chain: runtime-sensitive volume sums → different serialized volumes →
different lineage hashes → different forecast-file and manifest bytes.

Evidence: [3.10 arithmetic](btc/review_runs/evidence-integrity-resolution-20260912-v1/volume_arithmetic_python310.json),
[3.13 arithmetic](btc/review_runs/evidence-integrity-resolution-20260912-v1/volume_arithmetic_python313.json),
[3.10 lineage/compression](btc/review_runs/evidence-integrity-resolution-20260912-v1/existing_lineage_python310.json),
[3.13 lineage/compression](btc/review_runs/evidence-integrity-resolution-20260912-v1/existing_lineage_python313.json).

### What can now be trusted

The expected original artifact identities and retained replay are verified. The original and
Stage 3A **stored legacy** decision fields, feature files, trade file and report are identical.
Existing numerical parity is therefore consistent with the identified discrepancy; it was not
sufficient to detect it. This is **REPRODUCED LEGACY DEVELOPMENT EVIDENCE**, not corrected
evidence, independent confirmation or accepted alpha. No new performance number is needed.

Full semantic identity is false: numerical candle fields and provenance values differ.
Decision-equivalent content is narrower than evidence-equivalent content. Discarding digest
fields, rounding volumes or accepting approximate equality would weaken the frozen contract.
The canonical requirement remains useful and was not changed.

## Breakout authorization decision

**B. PRODUCER OR INPUT DIFFERENCE IDENTIFIED.** Specifically, producer/runtime arithmetic
differs; no difference was found in the pinned source/config/development input bytes.
The difference is material to exact evidence identity even though no difference is present
in the stored legacy decision/trade/report outputs. It is not classified as byte-only
nondeterminism. The original expected archive is traceable, and the immediate mismatch cause
is identified rather than UNKNOWN.

Stop the historical comparison. The original Stage 3A gate remains failed, not retrospectively
passed by this diagnostic. Its required second build remains unrun. No corrected historical
caller has become authorized.

Proposed minimum repair for separate review, **not executed or activated here**:

1. Record a runtime addendum alongside the frozen contract, binding a qualified interpreter,
   flags, platform, relevant standard-library/compression dependencies and complete imported
   project source. Start from the documented `.venv` command and demonstrated archive-compatible
   arithmetic; do not claim an unknown historical binary identity has been recovered.
2. Keep original source, data, parameters, costs, numeric assertions and all ten expected
   canonical hashes unchanged. Preserve failed build1. A separately authorized isolated
   legacy-only reconciliation must produce two new empty-directory builds with exact archived
   and mutual byte equality. A diagnostic rehash or retained August replay is not a substitute
   for those required Stage 3A executions.
3. Preserve the no-corrected-path guard. Qualify it and the reviewed synthetic 35/inherited 7
   suites under the proposed runtime before relying on a changed execution environment; the
   earlier passing suites were run under 3.10 and are reused evidence only in this task.
4. Return those results for review. Only after provenance passes and the reviewer freezes
   corrected coverage, gap/reset and attribution rules may a corrected historical
   claim-resolution specification be considered for separate authorization.

If archive equality still fails, stop at the first failed gate and preserve it. This proposal
does not relax hashes or convert known development history into independent evidence.

## Ridge blast radius

The two associated reports are `artifacts/agent-level-experiment/backtests/btc_causal_1h.json`
and `btc_causal_4h.json`. Their input hashes, exact dates, decision clock, runtime and original
producer hashes are absent. Association with the current script is supported by schema and
configuration, not an authenticated source-to-run binding.

[walkforward_btc_causal_model.py:34](../scripts/walkforward_btc_causal_model.py:34) labels one
return several rows ahead rather than a cumulative horizon. Horizon4 training can include
`r[i+3]` at a natural row-i decision cutoff; horizon1's leakage status depends on the unspecified
clock. Inner joins/dropna compress gaps, and log targets are compounded as simple returns.
Consequently neither report is a clean predictive or economic test. This does not invalidate
later separately specified and purged forecast studies.

The reset already qualifies these reports correctly. The tracker row now explicitly labels
the diagnostic implementation-limited, rather than treating it as a reliable rejection of
BTC/ETH/volume information. No executable repair or rerun was needed. Exact claims, hashes
and line references are in the [blast-radius report](btc/review_runs/evidence-integrity-resolution-20260912-v1/defect_blast_radius/findings.md).

## Cash-ETF blast radius

The affected archived C2 reports are `cash-etf/c2-proxy-evaluation-v2/report.json` through
`v8/report.json` under `artifacts/agent-level-experiment/`. All seven inspected directories
contain only that report, without local producer/runtime/input manifests. Current source points
to v8 but exact producer-to-result binding for each version is **UNKNOWN**. Three named arms
were exposed; seven output versions are not seven independent strategy hypotheses.

The current evaluator has invalid month-block interval labels, a TOM entry window that differs
from the frozen contract, inconsistent next-open versus daily-account timing and costs,
summed annual returns, the wrong concentration period, fee-only quarterly trade items and
missing required controls. These qualify return, uncertainty, trade and rejection claims.
For example, the negative TOM artifact does not reliably reject the exact frozen calendar
window. It also supplies no evidence of an edge and gives no authority to reopen that family.
The reset's provisional/unreliable labels remain correct; no historical impact was recomputed.

Current audit notices were added to:

- [CASH_ETF_C2_PROXY_EVALUATION_RESULT.md](../docs/CASH_ETF_C2_PROXY_EVALUATION_RESULT.md), whose
  old corrected/active wording and v3 attribution were stale;
- [CASH_ETF_RESEARCH_PROGRAM.md](../docs/CASH_ETF_RESEARCH_PROGRAM.md), which still implied no
  numeric ledger existed;
- [CASH_ETF_RESEARCH_HANDOFF.md](../docs/CASH_ETF_RESEARCH_HANDOFF.md), which combined not-run
  and completed-run claims and obsolete continuation instructions.

The old bodies and complete before copies are preserved. A separate
[current audit-status record](../config/research/cash-etf-evidence-audit-status-20260912-v1.json)
supersedes the operational interpretation of the old pinned `active` status. Its old registry
and decision-chain bytes remain unchanged. The program/handoff annotations intentionally no
longer match their old historical context pins; the historical validator would fail closed.
Those pins were not silently refreshed, and that validator was not run against raw ledgers.
Before copies support reconstruction of the old context; this is not a newly qualified context.

Recorded C1 numerical ledger processing includes 2019–2023, notwithstanding old locked wording.
That is prior data-engineering exposure, not established strategy-outcome evaluation; independence
is UNKNOWN. No cash ledger or protected partition was read here. See the
[seven-report inventory](btc/review_runs/evidence-integrity-resolution-20260912-v1/defect_blast_radius/cash_report_inventory.json)
and preserved document diffs. No executable code changed.

## HAR coverage diagnosis

The source, runner, contract and relevant dependency pins agree with HAR's archived manifest.
A pre-specified metadata-only diagnostic uses Stage 3A's 34 source segments and the existing
aggregate report, with no prices, realized variance, forecast rows or new forecast evaluation.
It exactly reproduces 3,024 valid / 3,058 possible daily observations, every annual coverage value,
2,011/1,921 common-row eligibility counts and 83 eligible monthly refit cutoffs per horizon.
No model was fitted.

Of 34 excluded days, two have no midnight source start and 32 contain fewer than 288 five-minute
bars. All 33 intersegment gaps contain positive missing duration: administrative segment splits
without missing time are not needed to explain the coverage loss. Gaps are intrinsic to the
frozen dataset; exchange outage versus publication/ingestion loss remains **UNKNOWN**.

| Ordered eligibility exclusion, evaluation 2019–2025 | One-day target | Seven-day target |
| --- | ---: | ---: |
| Current day or 22-day same-segment history missing | 418 | 418 |
| Future target incomplete after history passes | 16 | 100 |
| Further RV-EWMA initialization unavailable | 112 | 112 |
| Total excluded / possible decisions | 546 / 2,557 | 630 / 2,551 |

These counts depend on filter order and are not independent causal contributions. The frozen
22-day HAR history and 30-day EWMA state rebuild deliberately propagate missingness. They match
the contract; no harmless reset bug was demonstrated. The minimum 250 matured training samples
does not bind these exclusions. The diagnosis reuses recorded absence of value/control
exclusions; it does not re-evaluate those values.

The common sample is conditioned on future target observability. This is retrospective
availability selection, not proof that errors or returns were chosen favorably. Missingness
could correlate with stress; metadata cannot establish missing-at-random. HAR's useful result
remains conditional on observed common rows and fails annual coverage.

Window/initialization changes or bridging gaps would change the frozen protocol. Actual
source recovery could preserve the predictive hypothesis, but would change input identity and
need separate source qualification and review; consumed data would remain consumed. No retuning,
new source acquisition or forecast rerun is justified here. The
[coverage report and specification](btc/review_runs/evidence-integrity-resolution-20260912-v1/coverage_universe/FINDINGS.md)
include all34 dates, ordered attribution and exact count reconciliation.

## Top-two historical-universe feasibility

**A legitimate point-in-time investable universe cannot be reconstructed from the current
evidence.** The timeline contains zero evidence sources, seven entire-history UNKNOWN
intervals and `point_in_time_defensible:false`. Price-file hashes establish price lineage,
not the complete historical candidate population, omitted/delisted assets, suspension/rule
history or an inclusion method available at each decision date. Proving that the selected
seven happened to be listed would not repair their post-hoc selection from a missing population.

The archived P1 report and declaration/validator pins agree with current bytes and already
report `evidence_not_ready_fail_closed`. The current general `research_evidence.py` differs
from its archived P1 pin; no exact replay using today's module is claimed. Direct declaration
contents independently establish the missing-evidence blocker.

The existing boundary already treats 2021–2025 as consumed and 2026 as excluded. Preparation
metadata records 22,685 excluded >=2026 rows per original source file; current preparation code
decodes full source files before filtering and subsequently hashes each complete source.
Original producer binding is absent,
so this is a prior processing-exposure concern, not proof that those outcomes were evaluated.
No such mixed-period source was opened or hashed in this audit.

The favorable historical alpha claim remains **unresolved/unconfirmable using the current
dataset**. Required evidence includes the full contemporaneous candidate population,
eligible/ineligible intervals with available-at/effective timestamps, omitted/delisted assets,
market-rule histories and a defensible inclusion methodology. A different universe would be
a new design, not independent validation of R0. No additional top-two outcomes were evaluated.

## Experiment-ledger reconciliation

The [reconciled ledger](btc/review_runs/evidence-integrity-resolution-20260912-v1/ledger_reconciliation/reconciled_ledger.json)
retains the reset's 30 grouped research-history rows, adds known experiment IDs, contracts,
declared dates, data/result exposure, dispositions, independence and producer/hash references,
and separates registry/decision/contract inventories (75 contracts, 183 decision records,
185 inspected source identities in the ledger subtask). It is a **retrospective metadata
reconciliation**, not a reconstructed preregistration or complete search count.

Known limits remain explicit: the BTC trial registry has 10 entries, all with
`family_history_complete:false`; later studies appear in the 119 BTC decisions without complete
trial registration. The 12 cash and 52 cross-asset decision records are also reconciled.
All three recorded digest chains verify under their documented algorithms. BTC timestamps
regress at lines 14 and 109, so append order is not strict chronological order; this is not proof
of fabrication, and a self-consistent hash chain does not prove a pre-result external freeze.
The total number of attempted or abandoned trials remains **UNKNOWN**.

Contract dates are declarations, not verified execution dates. Current source hashes are
distinguished from source identities actually bound by historical manifests. Run versions and
engineering successors are not independent alpha trials. Missing IDs, missing producer/input
bindings and unobserved access remain UNKNOWN; no record certifies reused development history
as independent confirmation. Frozen registries are preserved, with this supplemental ledger
linked from the tracker and persistent review status.

## Remaining unresolved information

1. A reviewed executable/runtime/source addendum and two passing isolated legacy reproduction
   builds against the unchanged archive. Exact August runtime binary provenance remains unknown.
2. A reviewer-frozen corrected breakout coverage/gap/reset/warm-up/attribution policy before any
   corrected historical performance. Existing topology is evidence for that decision, not the policy.
3. Ridge/C2 original argv, input and producer bindings if their historical claims are ever to
   be interpreted beyond unqualified diagnostics. Repairing code alone cannot recover those facts.
4. HAR missing-interval origin and genuinely qualified source recovery evidence, if coverage
   qualification is later authorized. Current metadata cannot infer unobserved prices or errors.
5. Historical full-universe membership/availability evidence for top-two. The present files do
   not supply it; no survivor proxy is acceptable.
6. Complete experiment/result-access registration and external chronology evidence where absent.
   No current ledger can establish that undocumented experiments or exposures did not happen.

## Reproducibility and CORRECTED_PERFORMANCE_NOT_RUN

Detailed scripts, actual argv/cwd/interpreter/exit records, source/input/output identities,
diagnostic results and before/diffs are in
`research/btc/review_runs/evidence-integrity-resolution-20260912-v1/`.
The export manifest covers the evidence and changed documentation; no ZIP or bridge publication
was created. `CODEX_REVIEW_STATUS.md` and `RESEARCH_TRACKER.md` record the review stop.

**CORRECTED_PERFORMANCE_NOT_RUN:** no corrected or legacy historical strategy runner, signal
test, control simulation, forecast refit or profitability calculation ran in this task.
The breakout diagnostics read existing authorized development artifacts, compare/re-hash stored
records and sum only existing source volumes. HAR used time/segment metadata only. No sealed 2026
market partition, protected partial OB0/L2, live/paper service or active reliability stack was
accessed. Strategy test-suite executions 0; the prior 35/35 and 7/7 remain prior evidence, not new
passes. New checks are evidence diagnostics and document/metadata verification only: 20/20
resolution checks, 40/40 blast-radius document/identity checks, exact HAR calendar/coverage
reconciliation and three internally consistent decision chains.

Preserved command exceptions include one incorrect correction-contract path (exit1), Git
unavailability (exit128), and one diagnostic syntax error (exit1), corrected before that
diagnostic read any artifacts. No canonical mismatch was hidden or tolerance relaxed.
Other scoped lookup/metadata exceptions are recorded in the specialist command logs.

## Next-stage recommendation

Return this identified runtime/lineage break and the proposed **legacy-only** repair to ChatGPT
for review. Preserve disposition C and every closed family. No corrected performance run or
protected-data unlock follows automatically.

**B. BREAKOUT PROVENANCE REMAINS BROKEN — do not run corrected performance.**
