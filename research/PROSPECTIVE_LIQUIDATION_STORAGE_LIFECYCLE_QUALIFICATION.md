| Requirement | Result |
|---|---|
| All collector tests | **386/386 PASS**, zero failures/errors/skips; all 296 prior tests including the original 56 retained |
| Compact metadata layout | Immutable dataset/process headers; one chained commit and bounded receipts per segment |
| Manifest growth complexity | O(segments); no full-prefix copies in final startup/shutdown receipts |
| Bytes/segment metadata | Observed synthetic commit 4,191–4,194 B; modeled 34-clock-reference commit 13,508 B; complete primary logical per-segment metadata 30,712 B |
| Projected year metadata | 146,685 central planning segments over 381 days, including extra size seals: **4.50 GB logical primary segment metadata**; clocks and allocation counted separately |
| Compression exact | PASS on 8 deterministic synthetic segments using unchanged gzip settings |
| Backup exact | PASS on the actual independent SSD, with readback and fresh exact restores |
| Safe retirement qualified | PASS in synthetic fault tests and actual-SSD fixture run; live-load qualification remains incomplete |
| Restart from compressed archive | PASS across two actual OS processes; earlier raw originals and restore copies absent |
| Crash recovery qualified | 21 injected software failure positions plus corruption/missing/head tests; no claim of hardware power-loss testing |
| Integrated live rotations | **0 — initial clock admission blocked before any feed connection** |
| Integrated live restart | **NOT RUN**; second live process was never started |
| Persistent compressed GB/day | New live rate **UNMEASURED**; prior completed-pilot proxy 0.460129641 GB/day |
| Primary central projection | **273.68 GB**, provisional, including working space/reserve |
| Primary 2× projection | **452.80 GB**; **81.65 GB deficit** |
| Primary high-rate projection | **498.89 GB** at 1× high; **903.20 GB** at retained 2× high; deficits **127.74 / 532.05 GB** |
| Primary free capacity | **371.15 GB** at the recorded snapshot |
| Backup projection | **485.77 / 709.46 / 743.54 / 1,224.75 GB**, central / 2× / high / 2× high |
| Backup free capacity | **2,998.29 GB** at the recorded snapshot |
| Primary capacity decision | Central planning case fits with reserve; final adequacy is **NOT QUALIFIED** because the required new live measurements are missing |
| Alpha/outcome calculation | **NO** |

The compact archive removes the identified quadratic manifest design without weakening the verified-copy rules in the tests performed. It does **not yet remove the launch blocker**: the required integrated live pilot could not begin, so its real feed-load rotation, retirement, restart, transient-space and coverage checks remain unqualified. This is an operationally blocked result, not an alpha result.

Run: `prospective-liquidation-storage-lifecycle-20260913-v1`. Repository: `/data/Trading`; isolated source/evidence: `/data/Trading/research/btc/review_runs/prospective-liquidation-storage-lifecycle-20260913-v1`. Git commit, worktree and dirty identity remain **UNKNOWN**; exact byte identities are used. Final required-test log: `logs/full-required-qualification-2.log`; exact argv/interpreter/environment/exit/source hashes: its matching JSON. No production dataset or long-running collector started.

## What changed and why

`candidate/lifecycle_journal.py` appends unchanged source/health envelopes and one immutable local descriptor per seal. It never reads a full preceding manifest to construct a new descriptor. Fresh process directories prevent retired raw files from being reopened. Descriptor hashes bind journal identity, local sequence, original bytes, receipt boundaries and exact clock references.

`durability/compact_archive.py` creates one immutable dataset header and linked process headers. Each segment commit binds the preceding global chain digest, current descriptor, original SHA/size, gzip SHA/size/settings, verified independent-backup facts and exact restore proof. Transaction and retirement receipts contain only that transaction. Primary/SSD heads are bounded indexes, not sole evidence; the measured head is **236 bytes**. Source and health commits share a consecutive global chain.

`candidate/lifecycle_storage.py` runs a serial bounded archive queue. A descriptor hash, rather than raw-content hash, identifies each pending job, so two empty journals cannot collapse into one backup job. Queue and missing-clock-reference failures latch. Final startup/shutdown reconciliation receipts retain only the verified head, fixed state counts and a digest of the ordered verification table. A receipt measured **989 bytes for 10 segments and 1,016 bytes for 10,000**. The detailed table is regenerated from immutable segment records when needed.

`candidate/bounded_metrics.py` preserves the original operational summary while retaining at most two second bins. `candidate/capacity_guard.py` implements the frozen warning/stop rules below. The inherited collector, timestamp/clock-v2 implementation, health-v2 implementation and compression helpers remain unchanged; all **31 inherited Python files** and **451 prior qualification artifacts** were byte-verified unchanged. The hypothesis and stopping-rule SHA remain unchanged: `949c321208f0e98699b8dd22f430906696ab312d44c44f00dff093545511e358`.

The first 376-test pass, failed live preflight and actual-SSD synthetic benchmark used the first source revision. A final audit then removed the restart-report full-table growth described above. Its exact earlier 42 source/test files are retained under `source_revisions/pre-live-attempt-v1/`. The final implementation passed all 386 tests. The failed attempt was not rerun or relabeled. `RECONCILIATION_RECEIPT_REVISION.md` and both source-provenance JSONs make this distinction explicit.

## Canonical archive and retirement

The lifecycle is OPEN → SEALED_UNCOMPRESSED → COMPRESSED_VERIFIED → BACKUP_VERIFIED → RESTORE_VERIFIED → ARCHIVED. Active `.open` files and torn/unqualified tails are never retired. Sealed gzip plus immutable manifest/receipts is the canonical archived representation; the original uncompressed hash remains its semantic byte identity.

Before retirement, the code verifies and records the original hash/size; creates/fsyncs the complete gzip; verifies exact decompression; verifies the designated independent SSD and backup readback; restores to a fresh destination and checks exact original bytes; commits matching immutable chain records to both disks; reconciles the current archive; and persists an authorized retirement intent. Only then may the exact descriptor-bound original and restore-test copy be unlinked. Canonical gzip files and provenance metadata are never cleanup targets. Directory fsync follows publication and removal.

Gzip remains level 6, mtime 0 and empty filename under CPython 3.13.14 / zlib 1.3.2. The qualified executable remains `b200d6c7ae464af64f81808ba246a856b1a1cdf3b2ae7088d37d87d31aebe9ff`. Complete runtime, source, settings and test identities are preserved in the frozen specifications and final manifests.

Restart verifies both immutable chains, consecutive global/local sequences, process/boot/OS-start identities, clock references, compressed and decompressed identities, retirement receipts and heads. Missing originals without authorized retirement evidence fail. Corrupt/missing/forked commits and incorrect original or gzip hashes fail. Default stale-head handling fails closed; an explicit recovery operation may advance only a verified stale prefix. It never automatically deletes interrupted leftovers or makes a partial transaction ARCHIVED. A failed reconciliation disables further admission until a complete successful verification. Boot identity is actual evidence; a clean process restart does not invent a new host boot.

The 21 injected positions cover partial compression, pre-verification gzip/backup/restore, commit/head publication and each retirement boundary. Separate tests cover interruption during reconciliation with unchanged canonical bytes, duplicate/missing segments and wrong original identity. These are software ordering and error tests, not physical power-cut tests. Detailed state/recovery rules: `durability/COMPACT_LIFECYCLE_QUALIFICATION.md`.

## Live attempt: exact unresolved gate

The frozen live specification SHA was `d3a9cc9f4a53d4b13f24a139e66e1afce5aab5ff40c21dab4d199ac78a38c9ea`. It proposed two separate 960-second active processes, normal 900-second rotations, all four original feeds and no connection-lifetime override. The bounded launcher exited **2**, preserving `pilot/lifecycle-pilot-1/integrated_result.json` and `logs/integrated-live-process-1.log`.

At **2026-09-12T23:42:15.470332+00:00**, the unchanged clock producer returned **UNAVAILABLE**, not catastrophic failure. The native timesyncd message had `ignored_spike=true`. Optional `NTPSynchronized=true` and kernel `clock_state=0` were preserved, but they did not override the reviewed requirement for a usable source message. The recorded failure was `ClockUnavailable: source unsynchronized, leap-pending, ignored or uninitialized`.

The collector returned `INITIAL_CLOCK_UNQUALIFIED` before creating source/health journals, connecting feeds or launching the second process. There were **zero live observations in this stage**. This does not show local UTC was wrong by more than 100 ms. No clock policy, host time service or precision threshold was changed, and no clock retry was performed. Timing-v2 bounded coverage, earliest/latest intervals, strict cutoff ambiguity, the 100-ms diagnostic and catastrophic-failure rules remain intact. Exact proof: `metadata/live_admission_failure.json` and its hash-linked clock record.

Consequently new live compressed/metadata/backup rates, peak/transient working space, feed coverage, clock-qualified coverage, live CPU/RAM and latency are **NOT MEASURED**. The prior completed pilot and earlier interrupted higher-rate observations remain preserved; none were discarded to select a quieter period.

## Actual-SSD synthetic check

The separate `pilot/storage-synthetic-only/` benchmark used deterministic fixture bytes and a socket-denying audit hook. It did not query a clock or connect feeds. Its specification SHA is `557269932e55962b89804a0e8af330df15c377772d04e5421c74ef3d28e741a5`. Two real child processes, PIDs **791120** and **791205**, wrote eight segments. All **8,113,480 original bytes** were verified through gzip → independent SSD → fresh restore → exact original hash. Compressed objects totaled **3,843,446 bytes**. Both redundant originals and temporary restores were then retired; process two reconstructed the earlier chain from compressed-only history.

This ran with the actual device guard at `/media/joe/ShieldT7`, exFAT UUID `EF5F-FBD3`, USB `sda` versus primary NVMe `nvme0n1`. The synthetic namespace bypass admitted fixture paths only; the independent-device/UUID/read-write assertions still ran for real. Backup files occupied 8,912,896 allocated bytes versus 3,914,623 logical bytes in the captured inventory. The SSD protects against primary-disk loss; no offsite or disaster protection is claimed.

Measured synthetic compression CPU was **0.302 s**, compression wall time **0.323 s**, verified backup interval **0.081 s**, total bounded benchmark **1.796 s**. These are fixture measurements, not sustained market-feed throughput or hardware power-loss guarantees. The fixture compression ratio is **not used** for annual market storage. Exact commands/exit codes, all per-segment identities, actual mount evidence and inventories are in `pilot/storage-synthetic-only/result.json` and child command/result files.

## Linear metadata and capacity arithmetic

At 15-minute rotation there are 96 source plus 96 health segments/day: **73,152 segments over the unchanged illustrative 381-day collection envelope** (16 context +365 population days). These planning dates are not launch authorization. These are nominal time seals only. The final model also allows for the existing 64-MiB size cap: additional seals/day = ceil(uncompressed bytes/day ÷32 MiB), added to all 192 time seals. The 32-MiB average filled-size assumption is conservative planning, not a new rotation rule or a guaranteed future bound. It deliberately double-counts possible overlap. Central / doubled / high / doubled-high cases therefore allow **385 / 578 / 526 / 859 seals/day**, or **146,685 / 220,218 / 200,406 / 327,279** total segments. The retained doubled-high factor from prior planning is not discarded.

Actual synthetic commits were 4,191–4,194 bytes without clock references. A directly serialized 34-reference model gives commit **13,508**, transaction intent **11,600**, retirement intent **687**, completion **773**, and local descriptor **4,144 bytes** per segment. That is about **1.94 GB logical canonical segment metadata per copy**, plus **0.30 GB primary local descriptors**, before small width allowances. A separately reported 128-reference bound remains linear. No old full-prefix formula is reused. With the added central size-seal allowance, the same serialized records total **4,504,989,720 bytes** of logical primary metadata (30,712 ×146,685), before allocation and width allowances.

The final allocation-aware model includes compressed source/health journals, original and canonical primary clock files, canonical backup clock files, immutable records, append-only local descriptors, bounded heads, session metadata, directory entries and per-file allocation. It adds a **2 MiB per-process operational-metadata allowance for 381 possible processes**, which covers bounded reconciliation/runtime/capacity summaries; this is a storage allowance, not a new reconnect schedule.

The actual allocation units are **4 KiB primary** and **128 KiB SSD**. Prior authorized clock-proof file-size metadata was 7,899–7,911 bytes; 30-second refresh implies 1,097,280 proofs over 381 days. Their two primary copies require approximately **17.98 GB allocated**, while the backup clock copies require approximately **143.82 GB allocated**. Logical bytes alone would significantly understate SSD needs.

| Preserved rate scenario | Primary incl. 2 GiB working +64 GiB reserve | Primary deficit | Backup incl. 64 GiB reserve |
|---|---:|---:|---:|
| Prior completed-pilot proxy, 0.460129641 compressed GB/day | 273.68 GB | 0 GB | 485.77 GB |
| 2× that compressed journal rate | 452.80 GB | 81.65 GB | 709.46 GB |
| Earlier 11.1887264 uncompressed GB/day / separate 10.7178815× compression probe | 498.89 GB | 127.74 GB | 743.54 GB |
| Retained 2× earlier high-rate planning case | 903.20 GB | 532.05 GB | 1,224.75 GB |

The central geometry leaves **97.47 GB** beyond the included reserve and working allowance. The separate SSD fits all displayed cases. The higher partial observation and its separate compression probe are a conservative proxy, not a newly measured combined run. Final arithmetic and all component amounts are in `analysis/storage_projection_final_complete.json`; all earlier producers/results remain unchanged for reconciliation. The 128-clock-reference model raises primary totals to **281.82 / 465.01 / 510.00 / 921.34 GB**, respectively. Backup totals are unchanged because each modeled record fits the same SSD allocation unit.



Central planning storage separates persistent and transient evidence:

| Component | Primary | Independent SSD backup |
|---|---:|---:|
| Compressed source/health journals, allocation included | 175.91 GB | 194.54 GB |
| Clock proofs, allocation included | 17.98 GB | 143.82 GB |
| Immutable records, backup/retirement receipts, descriptors, session/head/operational metadata and directory allowances | 8.93 GB | 78.69 GB |
| Total persistent | 202.82 GB | 417.05 GB |
| Transient working allowance | 2 GiB | Not a permanent restore copy |
| Safety reserve | 64 GiB | 64 GiB |

The 2-GiB transient allowance covers active tails, queued just-sealed originals, one serial compression temporary and one fresh restore temporary; it is a planning allowance pending live peak measurement. Routine originals/restores are not year-scale persistent copies. Failed/torn transactions are never automatically retired; guards stop accumulation before exhausting reserve. All numbers use decimal GB except explicitly stated GiB.

This supports a **provisional central-capacity fit**, not PRIMARY ADEQUATE launch qualification. A completed pilot still must measure the compact lifecycle under all four live feeds, including working-space peaks and retirement latency. The 2× deficit is disclosed rather than treated as an automatic purchase requirement; the reviewed guarded-capacity policy could address a future excess-growth scenario, subject to final review.

## Capacity and backup operating rules

Warn immediately at **100 GiB effective free**. At **64 GiB**, latch a clean capture stop before reaching the **50 GiB minimum reserve**. Effective free subtracts pending archive bytes and four 64-MiB working objects. Missing/read-only/changed devices and stale capacity evidence also stop. A restart cannot clear a latched stop merely because free space recovered. No deletion, feed reduction, alternative compression or silent relocation is allowed. If traffic outgrows the plan, preserve evidence and return capacity expansion for review; do not alter the population endpoint to hide missing coverage.

The preserved backup policy requires seals/backup at least every 15 minutes, immediate overdue warnings and a protected stop after 60 minutes without verified progress; daily reconciliation and weekly complete verification remain required. Active tails and failed transactions stay preserved. Temporary restore removal is separate from backup retention. Full verification is proportional to retained data; only its persisted receipt is compact. Future production bindings, periodic scheduling and final namespace authorization are not silently inferred from this bounded pilot.

## Decision and next review

All storage code, tests, failed attempts, source revisions, byte identities, fixture results and projections are retained in this run. The final report, ledger and status point to final source/test hashes; earlier evidence is not relabeled. No liquidation/OI ratio, X membership/count, market return, matching, profitability or favorable-period calculation occurred. No protected preexisting 2026/OB0/L2 evidence, trading/soak service, account or payment was accessed.

Return for review with the storage changes and the exact remaining gate: **a successful integrated live rotation/retirement/restart pilot under a fresh qualified clock**. Do not relax clock-v2 or declare the synthetic fixture to be that pilot. No final launch package or collection/population/start dates are authorized by this blocked stage. The prospective stopping rule and Phase 2 research disposition remain unchanged.

**B. STORAGE/LIFECYCLE BLOCKER REMAINS — do not launch.**
