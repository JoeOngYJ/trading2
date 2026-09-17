| Requirement | Result |
|---|---|
| All tests | **PASS — 389/389**, zero failures, errors, or required skips (386 inherited + 3 focused admission/two-process tests) |
| Clock pre-admission | **PASS** — one fresh PASS on each process; no socket attempt preceded the proof or frozen active start |
| Process 1 four feeds | **PASS** — all four connected and initialized; one real ticker disconnect/reconnect was retained |
| Process 1 normal rotation | **PASS** — two normal 15-minute rotations; eight source/health segments archived including final seals |
| Compression/backup/restore | **PASS** — all 12 segments verified through gzip, independent SSD readback, and exact restore |
| Redundant originals retired | **PASS** — no sealed raw original or restore-test copy remains after archival |
| Clean process stop | **PASS** — process 1 exited 0 with no pending segment or failed transaction |
| Process 2 archive reconstruction | **PASS** — fresh PID/process UUID reconstructed sequences 0–7 from compressed-only history |
| Process 2 source reconnect | **PASS** — all four feeds reconnected and reinitialized |
| Global segment chain continued | **PASS** — process 2 appended sequences 8–11; final digest `19756f3129b36f1c43e2b23039ffb0c9ab074f3d4ad2d922c764bbde05558775` |
| Compressed-only historical restart | **PASS** — historical raw/restore files stayed absent and no archived artifact was rewritten |
| Live compression ratio | **14.1283×** (273,244,849 journal bytes to 19,340,295 canonical gzip bytes) |
| Persistent primary GB/day | **0.650 GB/day measured logical growth**; compressed journals alone 0.593 GB/day |
| Persistent backup GB/day | **0.622 GB/day measured logical growth** |
| Transient peak storage | 72.4 MB maximum queued sealed original measured; exact subsecond filesystem high-water was not instrumented; 2 GiB working allowance retained |
| Central year projection | **319.81 GB required; fits by 51.29 GB**, including 64 GiB reserve and 2 GiB working allowance |
| 2× year projection | **547.91 GB required; 176.81 GB deficit** on primary |
| High-rate projection | **492.57 GB required; 121.47 GB deficit** on primary |
| Primary free capacity | ~371 GB |
| Backup free capacity | ~3.0 TB; central/2×/high requirements 549.74/837.67/742.69 GB, all fit |
| Capacity guard | **PASS** — 100 GiB warning, 64 GiB clean stop, latched failure, no automatic deletion |
| Joint operational pilot coverage | **97.03% bounded-clock** (2,747/2,831 complete UTC seconds); monthly 95% gate was not inferred from this short pilot |
| Alpha/outcome computation | **NO** |

# Prospective liquidation integrated live qualification

Run ID: `prospective-liquidation-integrated-live-qualification-20260913-v1`  
Evidence root: `research/btc/review_runs/prospective-liquidation-integrated-live-qualification-20260913-v1/`  
Repository/worktree identity: `/data/Trading`; Git commit and dirty status are **UNKNOWN** because this directory is not a discoverable Git worktree.

## Conclusion

**Yes.** The collector has now demonstrated the complete compact lifecycle required for a year-long prospective evidence collection: admission before sockets, four live feeds, normal rotation, exact compression, independent SSD backup and restore, retirement, a clean stop, reconstruction by a genuinely new process, and continuation of one global evidence chain.

This qualifies data collection infrastructure only. It establishes no liquidation event, price response, return, strategy result, or alpha. The pilot namespace is permanently excluded from the prospective research population. Production collection has not started.

The external Samsung T7 Shield is usable as the independent backup. It is mounted at `/media/joe/ShieldT7`, source `/dev/sda2`, exFAT UUID `EF5F-FBD3`, with approximately 3.0 TB free. The primary is NVMe-backed `/data`; the devices are physically distinct. This protects against loss of the primary disk, but is not offsite/disaster protection.

## Frozen scope and implementation

The accepted compact archive, retirement state machine, restart reconstruction, gzip settings, clock protocol v2, health reducer, capacity policy, stopping rule, and four-feed scope were preserved. The only operational additions were bounded pre-connection admission and focused tests for first-valid-proof start freezing and cross-process continuation.

Principal frozen identities:

| Item | SHA-256 |
|---|---|
| `collector.py` | `769543334f1790a8c5bfb78a13d9cdb05c80137e1866fdce0fe1bab8fcf8f7a6` |
| `lifecycle_pilot.py` | `ae4a9414dc4909bc30b7b1b11335652e3022b6fbe8cba3618188ffd9b64437e7` |
| `lifecycle_storage.py` | `1f7cdef950faffc33099c547a0f06b71d41b5a46388dfd9bbe4076462255303e` |
| `compact_archive.py` | `f065437b1a83edc3229a064f63d09f5da06ce7518cdcb18be441c902c099bc1d` |
| `capacity_guard.py` | `a05c6f8c2eaf0325bd0f0bc2f0881c0179144fd2f484d57f3a5f66b1fa88cc45` |
| `clock_v2.py` | `b4713a917381e96ea60d6c7edf9d9a4bb6936ced129b313fc295e8a46fe6aa9b` |
| `health_v2.py` | `e186b617a686612a0b45d707092fd6be93059f390fcf00596b1663a8c8337d08` |
| Successful pilot specification | `bab6ba2ada54413826a30555b656f6c1daee9b8c6a5b6d0c5c3b87a00f83d300` |
| Existing stopping rule | `949c321208f0e98699b8dd22f430906696ab312d44c44f00dff093545511e358` |

Runtime: `/data/Trading/.venv/bin/python`, CPython 3.13.14, resolved executable `/home/joe/.local/share/uv/python/cpython-3.13.14-linux-x86_64-gnu/bin/python3.13`, executable SHA-256 `b200d6c7ae464af64f81808ba246a856b1a1cdf3b2ae7088d37d87d31aebe9ff`, Linux 6.5.0-45/glibc 2.35, `websockets` 15.0.1, zlib build/runtime 1.3.2.

The feeds remained exactly:

- Bybit `wss://stream.bybit.com/v5/public/linear`: `allLiquidation.BTCUSDT`, `publicTrade.BTCUSDT`, `tickers.BTCUSDT`.
- Binance `wss://stream.binance.com:9443/ws/btcusdt@bookTicker`: `btcusdt@bookTicker`.

## Regression and pre-admission

The exact regression command was:

```text
/data/Trading/.venv/bin/python -B -m unittest -v test_collector test_launch_runtime test_startup_order test_receipt_runtime_v2 test_final_pilot_v2 test_pilot_storage_v2 test_clock_attestation test_clock_v2 test_pilot_clock_summary test_health_reducer test_health_v2 test_sealed_backup test_sealed_compression test_lifecycle_journal test_compact_archive test_capacity_guard test_bounded_metrics test_lifecycle_integration test_compact_reconciliation_receipts
```

It ran from the isolated candidate directory and passed 389/389 with exit 0. The test result and log hashes are `18984df74ce0b0ad13b9a5e50e1e70056bedcfcd51339001a892f47c6fd075ed` and `8cb5a93d4f80d00c4910f7deeac4f62560aa41a3986568005073e48827942030`. Source identity was verified unchanged across the run.

Both live processes obtained a valid protocol-v2 proof on their first admission attempt. Process 1 froze active start at `2026-09-13T01:00:09.973488Z`; its first connection attempt followed 32.10 ms later. Process 2 froze active start at `2026-09-13T01:31:21.541514Z`; its first connection attempt followed 26.83 ms later. Every admission attempt and reason is retained. No socket opened while awaiting proof.

The initial analysis output incorrectly marked the start-freeze Boolean false because it looked for a nonexistent `admission_status` key instead of the preserved `classification` key. `analysis/derived_operational_summary.json` records this analysis-only defect, the corrected value, and the direct timestamps. No collector, pilot, archive, or source byte was changed.

## Two-process live lifecycle

Process 1 used PID 871940 and process UUID `c98e63661f0d43f0a439bc61dc77e9e8`. It collected for 1,860 planned active seconds, completed two normal 900-second rotations, committed eight source/health segments, and exited 0. A natural Bybit ticker disconnect occurred and was retained as unhealthy/reconnect evidence; the feed reconnected and reinitialized. Final process-1 chain sequence was 7 with digest `ad05d29dd0c546cba6ae852eac701fef3191735420c3fb24beaa5e5569a0b2a4`.

Process 2 used fresh PID 909103 and process UUID `73f573c879cf4b58ad8faa2189c4191f`. It started after an 11.568-second stop/restart interval. Startup reconciliation verified all eight prior segments from the immutable chain and compressed objects; prior raw and restore files were absent. It reconnected and initialized all four sources, ran for 960 active seconds, completed another normal rotation, appended sequences 8–11, archived every final segment, and exited 0.

The complete primary archive and the T7 backup have identical relative file sets and byte hashes. All 12 commit records form a continuous chain from dataset header SHA-256 `3e5b9e24b24cf89fc3e8a6bcfba9fb150291d44d8f97b0c6f6e96b4ea66e612d` through the final digest. Each retirement receipt proves both the sealed original and temporary restore were removed only after compression, backup readback, exact decompression, restore verification, and immutable commit. No `.open`, `.sealed`, or restore-test payload remains from completed segments.

Actual native liquidation schema was observed naturally and accepted by the production parser. Only schema and operational message counts were inspected; liquidation numeric strings and quantities were not decoded or reported. A future quiet interval still means `collector-observed healthy silence`, never scientifically qualified zero by itself.

## Clocks and operational health

All 94 live clock proofs were PASS with bounded evidence. The median conservative uncertainty bound was 381.912 ms and the worst was 1,035.369 ms. Ten proof observations met the separate 100-ms preferred-precision diagnostic. This does not change protocol v2: each record retains the estimate, bound, boot/proof identity, and receipt interval; later availability is established only by `receipt_latest < cutoff`.

On the complete common UTC grid from process-1 start through process-2 active end, bounded-clock joint operational health was 2,747/2,831 seconds, or 97.0329%. The 100-ms diagnostic joint rate was 232/2,831 seconds, or 8.1950%. Startup, the real reconnect, the clean process restart, heartbeat aging, and health-evidence gaps remained excluded with explicit reasons. The eventual 95% criterion applies independently to each complete prospective population month; this short pilot is not a monthly research-quality result.

## Measured storage and latency

Across 2,820 active seconds, the collector retained 17,123,076 raw source bytes inside 273,244,849 bytes of source/health journals. The observed rates were:

- raw source: 21.859 MB/hour;
- complete journals: 348.823 MB/hour;
- compressed canonical journals: 24.690 MB/hour, or 0.593 GB/day;
- clock evidence: 1.901 MB/hour, counting the local evidence and canonical archive copy;
- immutable lifecycle plus local descriptor metadata: 19,965.6 logical bytes per sealed segment;
- other permanent operational metadata: 0.187 MB/hour in this bounded run.

The measured permanent logical growth was 27.084 MB/hour on primary and 25.917 MB/hour on backup. The primary figure includes duplicated clock proof evidence and bounded process records. Compression plus independent backup averaged 189.82 ms per segment and peaked at 579.34 ms. Post-commit retirement averaged 163.54 ms and peaked at 394.38 ms. Maximum observed queued uncompressed evidence was 72,375,051 bytes. The exact subsecond filesystem-occupancy peak was not sampled, so the capacity model retains a conservative 2 GiB working allowance for active journals, original/compression/restore overlap, and filesystem effects. This limitation is disclosed rather than replaced with a fabricated exact peak.

Process-1/process-2 mean CPU use was 4.64%/4.11% of one core; peak RSS was 345,416/265,232 KiB. Mean fsync latency was 1.088/1.126 ms; maxima were 94.21/50.69 ms. No pending archive transaction, backup overdue state, or capacity fault remained at either clean stop.

## Capacity decision

The projection covers the conservative 381-day envelope used in the reviewed planning evidence. It preserves the 64 GiB free-space reserve, 2 GiB working allowance, 2 MiB/day bounded operational allowance, observed clock-proof duplication, filesystem allocation, 192 time-triggered seals/day, and an additional `ceil(uncompressed bytes/day / 32 MiB)` size-seal allowance. Time/size overlap is deliberately double-counted.

| Case | Primary required | Primary fit/deficit | Backup required | Backup fit |
|---|---:|---:|---:|---|
| Measured central live | 319.81 GB | **fits; 51.29 GB headroom** | 549.74 GB | Yes; 2.448 TB headroom |
| 2× measured traffic | 547.91 GB | **176.81 GB deficit** | 837.67 GB | Yes; 2.161 TB headroom |
| Preserved earlier high rate | 492.57 GB | **121.47 GB deficit** | 742.69 GB | Yes; 2.256 TB headroom |

The primary is therefore adequate for the measured central planning case, including reserve. It is not adequate for the disclosed 2× or earlier high-rate cases. Launch remains operationally defensible under the reviewed capacity policy because the central case fits, effective free space warns at 100 GiB, capture stops cleanly at 64 GiB, the stop latches, and no evidence is automatically deleted. Capacity expansion can be reviewed later without changing the research hypothesis. The SSD is ample for all three modeled backup cases.

## Preserved qualification attempts

No failed evidence was overwritten:

1. Attempt 1 (`18effd6f...`) stopped before every socket because the wrapper captured active time before activating an otherwise valid clock proof.
2. Attempt 2 (`60acae73...`) stopped before spawning a collector because its exclusive log filename collided with the preserved attempt-1 log.
3. Attempt 3 (`0df2226e...`) connected and archived operational evidence but ended BLOCKED when a stale 1,030-second recorder safety boundary contradicted the extended process-1 interval.
4. Attempt 4 (`bab6ba2...`) fixed only that duration binding, passed all 389 tests, and completed the required two-process pilot.

All attempts are excluded operational qualification evidence. None belongs to the future alpha sample.

## Proposed immutable launch package

The proposed package is `research/btc/review_runs/prospective-liquidation-integrated-live-qualification-20260913-v1/launch/prospective_collection_specification.json`, SHA-256 `beddfe3ed7c06644dd0a163927605cb4c8851ae39c342a2c7490fd9bc102295c`. It pins the collector/component/runtime/test hashes, feeds, clock and health rules, archive/retirement settings, capacity policy, stopping-rule identity, paths, and boundaries. Its status is `PROPOSED_NOT_AUTHORIZED_NOT_LAUNCHED`.

- prospective namespace: `/data/Trading/research/btc/prospective/forced-liquidation/forced-liquidation-prospective-v1/`;
- independent backup namespace: `/media/joe/ShieldT7/trading2-prospective/forced-liquidation-prospective-v1/`;
- proposed `collection_start_utc`: `2026-09-16T00:00:00Z`;
- proposed `population_start_utc`: `2026-10-01T00:00:00Z`;
- proposed `population_end_utc`: `2027-10-01T00:00:00Z` (exclusive).

The proposed start is valid only if final authorization occurs before it. If review misses that boundary, the timestamps require a new pre-start package identity; no old observation may be admitted retroactively. The first successfully qualified message and actual process/connection timestamps will be recorded at launch. Pilot data remains excluded.

## Evidence and limitations

Machine-readable results are under the run's `analysis/`, `logs/`, `pilot/`, and `launch/` directories. The health analysis decompressed only health objects. A second operational-envelope audit decompressed source containers but never decoded `raw_base64`, inspected market numeric values, or computed an event/outcome. The backup tree was verified byte-for-byte. No protected preexisting 2026 evidence, research outcome, account, soak service, paper/live trading service, or alpha code was accessed.

The external SSD is a single local USB backup and does not protect against site-wide loss or simultaneous host/device damage. The primary central projection has 51.29 GB of modeled headroom after reserve, so rate and capacity monitoring are operational requirements. The short pilot does not prove exchange publisher completeness, scientifically certify zero liquidation reports, or guarantee a future complete month will exceed 95% coverage.

**A. FULL OPERATIONAL QUALIFICATION PASSED — prospective collection is ready for final launch authorization.**

`STOP_FOR_CHATGPT_REVIEW`
