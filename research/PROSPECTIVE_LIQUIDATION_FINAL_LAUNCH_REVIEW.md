| Requirement | Result |
|---|---|
| Collector tests | **296/296 PASS**, zero failures/errors/skips; all 169 prior tests retained, including original 56 |
| Clock synchronization source | Existing systemd-timesyncd 249.11 + read-only accepted NTP message/kernel status; no service changes |
| Typical UTC error bound | Median published bound **255.279 ms**; this is uncertainty, not measured actual clock error |
| Worst pilot UTC error bound | **1054.083 ms** at receipt; all 32 clock measurements qualified under v2 |
| Timing ambiguity policy | Fresh trustworthy complete interval; later pre-cutoff availability requires `receipt_latest < T`; overlap/equality remains ambiguous |
| Collector continues through non-catastrophic clock uncertainty? | YES; live capture continued above 100 ms; absent/stale cases passed synthetic tests |
| Four live feeds | PASS: all four connected, native market schema observed, intentional reconnect completed |
| Complete segment sealed | PASS: normal 15-minute rotation, then clean stop; four sealed source/health segments |
| Compression exact recovery | PASS: every primary gzip → independent SSD → fresh restore matched original bytes/hash |
| Measured compression ratio | **14.0567×**;72,482,033 uncompressed bytes →5,156,416 gzip bytes |
| Compressed GB/day | **0.4601** journal GB/day, plus clock/manifest/receipt metadata |
| Projected primary storage | **631.74 GB central; 815.66 GB with2× compressed traffic** under current layout |
| Projected backup storage | **813.38 GB** with2× compressed traffic; high-rate scenario about1.26TB |
| Local storage adequate | **NO**: 371.16 GB free; current manifest layout and retention are not year-scale qualified |
| Independent backup adequate | YES for stated scenarios: approximately3.0TB free on separate4TB USB SSD |
| Backup restore verified | PASS: four segment restores, complete archive reconciliation,95 metadata files restored exactly |
| Operational health coverage | **898/959 =93.6392%** joint pilot coverage; bounded clock959/959; strict100 ms joint diagnostic156/959 =16.2669% |
| Alpha/outcome computation | **NO** |
| Proposed collection start | **NOT SET — launch blocked** |
| Proposed population start | **NOT SET — launch blocked** |
| Proposed population end | **NOT SET — launch blocked** |

The completed pilot resolves the former clock hard-stop and the actual-SSD backup/recovery qualification. **The collector is still not ready for a year-long launch.** The main remaining defect is storage layout: preserving a growing full session-manifest prefix at every seal creates quadratic metadata growth. In addition, the demonstrated pilot retains both raw originals and fresh restored copies; a reviewed, qualified redundant-copy retirement/restart path is required before compressed-only capacity can be claimed. Buying historical data or changing the alpha hypothesis would not address these defects.

Run: `prospective-liquidation-final-launch-20260912-v1`. [Detailed evidence](btc/review_runs/prospective-liquidation-final-launch-20260912-v1/), [frozen operational protocol](btc/review_runs/prospective-liquidation-final-launch-20260912-v1/OPERATIONAL_PROTOCOL_V2.md), [pilot specification](btc/review_runs/prospective-liquidation-final-launch-20260912-v1/pilot_specification_v2.json), [measured storage calculation](btc/review_runs/prospective-liquidation-final-launch-20260912-v1/analysis/storage_projection.json). This is operational qualification only. All pilot observations are permanently excluded from the prospective population.

## Preservation and scope

The three reviewed authority reports, stopping rule and all 202 prior qualification files remain byte-identical. Their exact checks are in `metadata/authority_preservation.json`. The prior B disposition, both failed pilots,102.838577-ms bound failure and earlier compression probe remain unchanged. The Alpha Discovery Phase 2 B disposition and all rejected hypotheses stand. No protected preexisting 2026/OB0/L2 evidence, active soak, account/service, trade, purchase or production launch was accessed or initiated. No liquidation/OI event membership, qualifying-event count, target, return, matching, profitability or favorable-period calculation occurred.

The raw collector necessarily preserves source values. Operational schema/count/hash/clock summaries do not display prices or liquidation quantities. The four observed liquidation market messages are **feed-message counts only**, not qualifying X events or individual liquidation totals. Source completeness and scientifically certified zero reports remain **NOT_ESTABLISHED**.

Repository path `/data/Trading`; Git commit/worktree/dirty identity **UNKNOWN**. Implementation changes are isolated in this new run. No Git provenance is invented and no original research source/report was rewritten.

## Timing protocol v2

The user approved **“Use bounded-clock coverage; keep100 ms diagnostic.”** The ≥95% monthly requirement now counts only connected, acknowledged/initialized, heartbeat-qualified, durably recorded feeds with fresh trustworthy finite UTC intervals.100 ms remains a separate precision diagnostic; no larger arbitrary ceiling replaced it. The 16-minute pilot cannot certify a month of95% coverage, and its intentionally frequent reconnects/startup are retained in the denominator.

Every source/control receipt retains unchanged local disciplined UTC, monotonic receipt, actual clock-read span, boot identity, activated attestation hash, finite bound or null, earliest/latest UTC and separate qualification/precision flags. Source timestamp and receipt time remain separate. Actual clock-read span expands the bound. Attestation publication and actual activation are recorded separately; neither a later measurement nor delayed activation can backfill earlier receipts. The kernel remaining phase estimate is retained but not applied twice to the disciplined wall clock.

The producer reads accepted `systemd-timesyncd` NTP metadata and kernel synchronization status without changing the host. It includes network/upstream uncertainty, phase-correction envelope and conservative500 ppm aging. The native accepted update expires after one hour; the local proof after five minutes. A transient missing/stale/unsynchronized proof yields timing-unqualified capture. Corrupt producer/proof, boot mismatch, invalid UTC/order, or a qualified abrupt wall/monotonic discontinuity stops capture. Exact formula, source assumptions and raw read-only commands are in [clock policy](btc/review_runs/prospective-liquidation-final-launch-20260912-v1/clock/CLOCK_POLICY_V2.md).

All 32 pilot attestations passed bounded qualification, 6 also met100 ms at measurement. Published bounds ranged21.279–1,038.987 ms. All 23,402 received source/control messages had trustworthy intervals; worst receipt bound1054.083ms. These are operational clock counts, not research events. The bound is not evidence that true local UTC was wrong by that amount. Native source packet age and uncertainty remain visible.

NTS was not configured or claimed. It could add source/packet authentication, but authentication does not eliminate delay uncertainty or guarantee better precision. Changing to an NTS-capable daemon would require separate host qualification; no daemon was installed or changed. [RFC8915](https://www.rfc-editor.org/rfc/rfc8915.html).

## Completed health pilot

Frozen specification SHA-256: `3f19d3f818ce04773daf2c10d63e791b198153b0cf0c46f693097e9829dc94bc`. Freeze preceded sockets. Actual collection began `2026-09-12T22:38:19.672877+00:00`; the frozen active end was `2026-09-12T22:54:19.672877+00:00`. The active duration was 960 seconds; orderly socket shutdown extended operational accounting to968.237seconds. Rates below use that complete measured operational duration. The 1200-second total cap and 1 GiB journal cap were respected. This is not the prospective research start.

Each of the four feeds opened twice and performed one controlled 500-second connection rotation. All Bybit acknowledgements and application heartbeats worked; Binance's direct stream initialized from valid BBO data and transport heartbeat. Ticker's pre-ACK snapshot/delta chains were retained and activated only at the actual ACK, on both connections. The 10 pre-ACK ticker rows retain their original unacknowledged/uninitialized flags. No unplanned connection failure, parsing fault, queue/storage failure or catastrophic clock event occurred.

| Stream | Raw source bytes | Uncompressed source-envelope bytes | Joint-requirement qualified seconds for feed |
|---|---:|---:|---:|
| bybit_liquidation | 6,752 | 130,530 | 913/959 |
| bybit_trades | 394,682 | 2,376,846 | 914/959 |
| bybit_ticker | 802,587 | 12,612,017 | 914/959 |
| binance_bbo | 1,923,923 | 46,931,642 | 908/959 |

These source-envelope contributions exclude common health/clock/control overhead. Compressed source segments mix streams, so no fictitious exact compressed-byte allocation by stream is claimed. Raw source rate was11.630MB/hour (0.279GB/day). Uncompressed journals were269.495MB/hour (6.468GB/day). Compressed sealed journals were19.172MB/hour. Separately retained clock evidence contributes about22.603MB/day at this refresh cadence.

Peak one-second source/write totals were41,832/949,382bytes. Process CPU was33.836seconds (3.495% of one core); maximum RSS283.02MiB. Mean/max append latency0.137/3.853ms; mean/max fsync latency1.095/134.725ms. These are measurements, not hard latency guarantees; CPU excludes separate short-lived metadata subprocess usage. Compression reported0.369s CPU/0.373s wall. Verified backup throughput was9.246MB/s including readback/decompression work, not an SSD benchmark. Maximum serial backup queue delay1.799s; final backlog zero.

The fixed 959 complete-second denominator contains 898 qualified intersection seconds. All 959 had bounded clock/storage evidence.61 intersection seconds were unqualified; overlapping reasons include 58 transport-heartbeat seconds, 43 Bybit application-heartbeat seconds and 15 disconnected/unknown seconds around startup/planned reconnect/closure. They were not removed. [Per-second accounting and attribution](btc/review_runs/prospective-liquidation-final-launch-20260912-v1/analysis/coverage_gap_attribution.json) preserves individual-feed and intersection coverage.93.64% in this deliberately interrupted short pilot does not prove or disprove future monthly95%; that monthly standard remains unchanged.

## Compression, backup and recovery

The active journal remains uncompressed. At 15 minutes it sealed normally, then both journals sealed again at clean stop. For all four segments: original hash/size → gzip level 6 with mtime 0/empty filename → fsync → exact decompression verification → atomic primary publication → independent SSD copy/readback → new-directory restore → exact original hash. Full ordered primary/backup manifests reconciled. Original and restore copies are still present. No `.open` tails were silently compressed, truncated or promoted.

The backup mount is `/media/joe/ShieldT7`, `/dev/sda2`, USB physical device `sda`, exFAT UUID `EF5F-FBD3`, st_dev 2050. It is separate from primary `nvme0n1` and can survive primary-disk loss if its committed data and the SSD remain intact. At qualification it had approximately2,998.29 GB free of4,000.65 GB. UUID, actual read-write mount, device and free-space checks ran before/after backup. Existing SSD contents were not inspected or changed.

Linux no-replace rename and file/directory fsync worked on this filesystem. exFAT does not supply POSIX mode immutability or a general power-loss journal guarantee. Hash/readback/restore qualification is software evidence, not a destructive hardware-power-loss test. Same-host/power/location backup is independent of the primary disk, not an offsite disaster copy.

In addition to segment evidence,95 metadata files (2,026,518bytes) were backed up and freshly restored exactly. Published proofs bind source/config/test/clock identities and session manifests. The final review manifest is separately retained with its hash. Daily manifest reconciliation, weekly complete verification and15/60-minute backup scheduling have focused synthetic tests; the pilot exercised immediate per-seal verification and final full reconciliation. No unattended production scheduler or deletion service was launched.

## Storage blocker and smallest justified next work

The planning example has 16 context days and 365 population days: an illustrative September 15 start, October 1, 2026 population start and October 1, 2027 endpoint. These dates are **not authorization or a proposed launch while blocked**. Actual dates remain null and must be frozen later using the reviewed 24-hour/context rule.

At the observed compressed rate, the 381-day journal payload alone is175.31 GB. The current uninterrupted-session layout produces 36,576 scheduled seals per journal and retains every full manifest prefix. With actual observed 261/259-byte maximum entry lengths plus an explicit 32-byte growth allowance, source+health prefixes alone consume **390.65 GB per copy**. Even without that allowance, approximately347.84GB of prefix metadata would remain. Connection rotations do not bound it; assuming unplanned reboots is not an acceptable capacity policy.

| 381-day planning item|Estimate|
|---|---:|
|Compressed journal payload, observed rate|175.31 GB|
|Retained full manifest prefixes, current uninterrupted layout|390.65 GB|
|Working segments/recovery space allowance|2.28 GB|
|Safety floor| 50 GiB (53.69 GB)|
|Primary total, central traffic plus clock/receipts|631.74 GB|
|Primary total,2× compressed traffic plus metadata/reserve|815.66 GB|
|Backup total, same 2× traffic case|813.38 GB|
|Plausible higher-rate primary scenario|1,260.52 GB|
|Current primary available|371.16 GB|

The earlier interrupted 44.167 s and 264.796 s runs remain in the comparison: 11.1887 and 2.93581 GB/day all-persisted rates. This completed run measured 6.4679 GB/day uncompressed journals and 0.4601 GB/day compressed journals. The higher-rate scenario explicitly uses the earlier 11.1887 GB/day observation and that separate partial probe's 10.7179× ratio; it is not substituted for this run's 14.0567× measurement. All are short observations/scenarios, not year-long demand guarantees. The SSD is sufficient for these compressed-backup scenarios; `/data` need not store that independent copy.

Compressed-only projections also assume a future qualified policy to retire redundant raw/restore copies after recovery proofs. Scaling the current keep-everything pilot behavior instead would require approximately5,560.27 GB on primary. No removal has occurred. The archive-byte resolver is tested, but compacted restart admission, pending-age preservation, bounded metadata layout and redundant-copy retirement need an integrated reviewed production path.

**Recommendation:** first bound manifest/index growth and qualify the exact restart/retirement path using synthetic/sealed evidence. Do not purchase a disk simply to accommodate quadratic metadata. Even a hypothetical bounded-index layout at 2× this pilot's compressed rate would need about425.03 GB, roughly 54 GB above current free primary capacity; it is not yet qualified. After layout qualification, an additional 128 GB of durable primary headroom is a modest practical allowance for that scenario, while the preserved higher-rate scenario may demand more. No capacity expansion, deletion or purchase is performed or authorized here.

## Tests, exact identities and commands

Final integrated result: 296/296 PASS, zero failures/errors/skips. Breakdown: 56 inherited core + 9 wrapper + 16 startup + 27 receipt-v2 + 5 pilot guards + 13 storage integration + 28 inherited clock + 26 clock-v2 + 3 clock summaries + 35 inherited health + 26 health-v2 + 25 inherited durability + 27 compression/recovery. Earlier sandbox asyncio hangs and intermediate fixture failures remain separate evidence; they are not relabelled as passes. Source/health integration fixes were completed before the final test and pilot freeze.

Interpreter `/data/Trading/.venv/bin/python`, resolved `/home/joe/.local/share/uv/python/cpython-3.13.14-linux-x86_64-gnu/bin/python3.13`; CPython 3.13.14, websockets 15.0.1, zlib 1.3.2. Executable SHA-256 `b200d6c7ae464af64f81808ba246a856b1a1cdf3b2ae7088d37d87d31aebe9ff`. Platform `Linux-6.5.0-45-generic-x86_64-with-glibc2.35`. Exact build, boot, package-source hashes and busctl/timesyncd/findmnt binary pins are in the frozen specification; source/runtime pins were rechecked on every 30-second refresh.

|Used component|SHA-256|
|---|---|
| `collector.py` | `769543334f1790a8c5bfb78a13d9cdb05c80137e1866fdce0fe1bab8fcf8f7a6` |
| `receipt_runtime_v2.py` | `e4189bbdb782f4d0495a915f03aa03460c3455d1ecefb5e5a4b22b98514567d2` |
| `clock_v2.py` | `b4713a917381e96ea60d6c7edf9d9a4bb6936ced129b313fc295e8a46fe6aa9b` |
| `health_v2.py` | `e186b617a686612a0b45d707092fd6be93059f390fcf00596b1663a8c8337d08` |
| `sealed_compression.py` | `e5f9b18936c8418c1813fb94c3a27c40bff58630d1687206fa19616bcf09389d` |
| `pilot_storage_v2.py` | `fb2787c251f1e22bbe43870c23a1a9e4ddc4e543db9ff7880858c6c89f894bba` |
| `final_pilot_v2.py` | `9173d06c4886bd7e957e0c241891211e33c36687e906916b22abdf06ee80a922` |

Actual synthetic argv/cwd/PYTHONPATH/exit 0: `logs/full-integrated-qualification-1.json`. Actual pilot argv/cwd/exit 0: `logs/health-pilot-v2-1-command.json`, with full health-only stdout log. The pilot command was `/data/Trading/.venv/bin/python -B final_pilot_v2.py --pilot-spec /data/Trading/research/btc/review_runs/prospective-liquidation-final-launch-20260912-v1/pilot_specification_v2.json`, cwd `/data/Trading/research/btc/review_runs/prospective-liquidation-final-launch-20260912-v1/candidate`. Post-pilot sealed verification, storage projection and metadata backup all exited0; scripts and material command receipts are preserved. No unreviewed source change followed the freeze.

## Launch hold and next review

No final production authorization package or executable start file is issued while capacity/lifecycle remains unqualified. The reserved prospective namespace is `research/btc/prospective/forced-liquidation/forced-liquidation-prospective-v1/`; it has not become an active dataset. `collection_start_utc`, `population_start_utc`, `population_end_utc` are null. The unchanged stopping rule remains 12 complete UTC population months following the earliest month boundary at least 24 hours after actual authorized start, with no X-count early stopping, peeking or automatic extension.

The remaining review is **bounded storage layout/retention/restart qualification**, not alpha research, clock precision relaxation or another historical search. Keep 95% monthly bounded-clock coverage,100 ms diagnostic, the frozen hypothesis and all contamination boundaries unchanged.

**B. OPERATIONAL BLOCKER REMAINS — do not launch.**
