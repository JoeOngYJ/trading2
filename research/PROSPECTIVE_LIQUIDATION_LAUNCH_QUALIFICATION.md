| Launch requirement | Result |
|---|---|
| Collector synthetic qualification | **PASS: 169 final component tests; 0 failures, errors or skips.** Includes all 56 inherited collector tests. |
| UTC clock attestation | Producer implemented; fresh measurements passed, but the second pilot stopped when the conservative bound reached **102.838577 ms**, above 100 ms. Sustained qualification **FAILED**. |
| Bybit liquidation connectivity | Connection, subscription ACK and correlated transport/application heartbeats observed. Actual liquidation-market schema was **not observed**; silence is not scientific zero. |
| Bybit trade connectivity | Connection, ACK, market-message framing and heartbeats observed. |
| Bybit ticker/OI initialization | Observed successfully after the bounded snapshot-before-ACK repair. Original OI and `singleOpenInterest` retain separate identities. |
| Binance bookTicker connectivity | Connection, native best-quote message framing, initialization and transport heartbeats observed. |
| Health reducer | **35 synthetic tests pass.** Live monitoring worked; neither failed pilot reached a clean sealed segment, so canonical live coverage remains unqualified. |
| Observed data rate | Interrupted pilot 2: **2.94 GB/day**, including persisted overhead; interrupted pilot 1: approximately **11.2 GB/day**. These are short-window extrapolations, not qualified annual forecasts. |
| 12-month storage requirement | **Not qualified.** Conditional current-format illustrations, including context, 2× margin and 50 GiB reserve: approximately **2.30–8.60 TB per copy** at the two observed rates. |
| Local storage sufficient? | `/data` has approximately **371 GB free / 346 GiB**. Enough for bounded pilots; insufficient for either conditional year-long illustration in the current uncompressed format. |
| Backup/recovery plan | 25 synthetic tests pass for append-only verified backup/restore primitives. User reports an existing backup location; **path, capacity, physical independence and real recovery qualification remain pending**. |
| Exact prospective namespace | Proposed, not launched: `/data/Trading/research/btc/prospective/forced-liquidation/prospective-forced-liquidation-v1/`. |
| Proposed collection start | **NOT SET — launch blockers remain.** |
| Proposed population start | **NOT SET.** Reviewed month-boundary/context rule preserved. |
| Proposed population end | **NOT SET.** Twelve complete UTC months after the eventual population start. |
| Alpha/outcome computation performed? | **NO** |

The collector is **not ready for a clean future-data launch**. The highest-priority blocker is sustained clock attestation: the stop gate worked, but the second bounded pilot could not finish within the unchanged clock policy. Storage and independent backup also remain unresolved. No third pilot, clock-limit relaxation or long-running collection followed the failure.

Run: `prospective-liquidation-launch-qualification-20260912-v1`. Detailed evidence is under `research/btc/review_runs/prospective-liquidation-launch-qualification-20260912-v1/`. Repository location is `/data/Trading`; Git commit, worktree and dirty identity remain **UNKNOWN**, with exact byte identities used instead. The five reviewed research/collection reports and prior collector evidence are preserved. The accepted Phase 2 conclusion remains **NO FREE/CHEAP HISTORICAL HYPOTHESIS IS CURRENTLY STRONG ENOUGH**.

## Clock qualification and the failed pilots

Read-only host inspection found positive kernel synchronization status, but the initial kernel maximum-error estimate was 1,001 ms. Configuration, timezone and clock resolution were not treated as accuracy evidence. The new attestation producer independently queries `ntp.ubuntu.com` and `time.cloudflare.com`, requires valid replies from both and agreeing error intervals, and checks synchronized kernel state before and after measurement. It records UTC and monotonic clocks, boot ID, actual observations, offset/bound components, method, source/runtime identities, measurement age and PASS/FAIL.

The absolute bound includes network asymmetry allowance, reported upstream uncertainty, local capture allowance and conservative aging. A 60-second dual-clock lease includes 500-ppm aging. The refresh loop waits 30 seconds between measurements; DNS/NTP work adds to the actual publication interval, which was approximately 30–35 seconds in the observed passing sequence. This is stricter than the reviewed maximum five-minute age and preserves the **100-ms ceiling**, same-boot requirement and positive synchronization requirement. A failed new measurement stops capture even if a preceding PASS has not expired. These ordinary public NTP references are not authenticated NTS evidence; the operational bound depends on honest reference clocks and their error declarations. No time service, kernel clock setting or soak service was changed.

| Pilot | Frozen specification SHA-256 | Result |
|---|---|---|
| `pilot/health-pilot-1` | `e93f5f058ecbb711f4ef04019e2a0213f3c6135b597a0f20397500ef7ef0b98c` | Exit 2 after 44.167155426 seconds: Ubuntu NTP refresh timed out. Ticker startup ordering also left OI uninitialized. |
| `attempt2/pilot/health-pilot-2` | `b20e6fa88d19a7cfdadada62060789d1df3052e1684a02ca32f10337fc33273a` | Exit 2 after 264.795604157 seconds: `ClockFailure`, conservative UTC bound **102.838577 ms**. Initial bound was **61.738430 ms**. |

Both pilots were frozen for 600 active seconds, a 630-second internal limit and 650-second outer process timeout, with a 1-GiB logical-file cap. Four separate public connections were the only market connections. Planned connection and file rotation at 300 seconds was **not reached**. Consequently live reconnect/rotation qualification remains incomplete, although synthetic cases passed. There was no automatic third attempt.

The 102.84-ms result is an **uncertainty-bound failure**, not proof that the machine's actual UTC offset was 102.84 ms. Exact observations and the failure's component explanation are preserved under `attempt2/clock/`. It would be incorrect to relabel this as an alpha result or to round it down to a passing clock check.

In the failing measurement, the Ubuntu-derived offset estimate was **−5.991233 ms**. Half the observed network round trip contributed **43.244225 ms** and upstream uncertainty contributed **22.552552 ms**. Together with capture/query aging, these produced a **72.838577-ms** measurement bound; the frozen full-lease aging allowance added **30 ms**. Both references agreed and kernel synchronization remained positive. A preceding PASS had already approached the ceiling at 98.798129 ms with a wider Cloudflare path. Selecting the narrower source or retrying a valid wide-bound reply would change the qualification method and was not done.

Pilot 1 remains unchanged. The second candidate adds only timeout retries to at most two advertised IPv4 addresses of each of the same two clock authorities. Invalid or unsynchronized replies are not retried in search of a favorable answer. Source agreement, bound arithmetic and limits remain unchanged. Both timeouts and subsequent replies are retained.

## Source health, timestamps and startup state

The exact feeds were Bybit `allLiquidation.BTCUSDT`, `publicTrade.BTCUSDT`, `tickers.BTCUSDT` at `wss://stream.bybit.com/v5/public/linear`, and Binance spot `btcusdt@bookTicker` at `wss://stream.binance.com:9443/ws/btcusdt@bookTicker`. No L2, account, extra instrument or historical endpoint was used.

The pilot records application-message bytes losslessly in base64 with their SHA-256, source numeric spellings, source timestamps where supplied, UTC/monotonic ingress clocks, separate dispatch clocks, transport-chunk identity, connection ID and reconnect generation. Receipt is the userspace transport callback for the final frame's chunk; it is not claimed to be exchange emission or NIC arrival time. Source schema summaries contain field names and JSON types, not market values. Binance native bookTicker in the observed schema has its update ID and bid/ask fields but no supplied exchange timestamp; no timestamp was invented. Bybit trade/ticker native clock and sequence fields are retained separately from receipt time.

The first pilot demonstrated that Bybit can deliver a valid ticker snapshot and deltas before their matching subscription ACK. The repair retains a tentative validated anchor, then activates OI only when the actual matching ACK is dispatched. Exact snapshot, intervening-chain and ACK record hashes establish that transition. Earlier records, flags and receipt clocks are not rewritten or backdated. Invalid data, wrong ACKs and reconnects invalidate tentative state. Only the proven startup faults clear; unrelated faults remain latched. The second pilot demonstrated initialized OI and healthy transport after this repair.

No native liquidation market report occurred in these short pilots. ACKs and pongs establish observed transport health, not a complete liquidation publisher or a scientifically certified zero. The live liquidation-event schema and its timestamp fields therefore remain unobserved in this qualification. The collector retains both OI fields if supplied; the reviewed `Decimal(both_sided_openInterest) / Decimal(2)` accounting definition remains separate and was not used to calculate an event or ratio.

The second pilot observed 3,337 Binance source messages, 1,042 ticker source messages, 75 trade-stream source messages and 13 liquidation-stream source messages. These counts include control/ACK/pong messages where applicable and are **not qualifying-event counts**. Each connection completed 12 correlated transport heartbeat checks. Operational metadata preserves duplicate indicators, timestamp/sequence flags and source-schema evidence without inspecting price responses.

The retained source prefix contains 4,718 complete, hash-chain-verified envelope records and no torn suffix. The bounded duplicate detector flagged no raw/native duplicates; no non-startup source fault was recorded. These observations do not prove complete delivery or turn nonconsecutive exchange-wide update IDs into evidence of packet loss. Startup lineage verifies snapshot record 12, last pre-ACK delta 14, ACK 15 and activation 16 in one connection/generation, with activation after ACK dispatch. The three observed ticker startup records remain flagged. This retained-prefix check does not change the file's unsealed status.

## One-second health and durable evidence

The reducer requires every feed's current connection, appropriate ACK/initialization, recent correlated transport heartbeat, Bybit application heartbeat, ticker OI state and qualified same-boot clock. Unresolved parsing, storage, queue or recovery faults invalidate health. It preserves each feed's coverage and their logical intersection. It never averages feed percentages into joint coverage. A snapshot gap over two seconds is unknown; no sorting, interpolation over missing evidence or tail extension repairs it.

Output distinguishes disconnected/unknown from collector-observed healthy silence. Scientific zero remains `NOT_ESTABLISHED`. The reviewed monthly 95% intersection rule is unchanged; it is not repurposed as an unplanned ten-minute pilot acceptance threshold.

The second pilot's fixed 600-second interval contains **599 complete UTC seconds** because its start is fractional. It ended before the first scheduled seal. The retained `.open` files and empty committed segment manifests are preserved exactly. The conservative canonical reduction therefore reports **0 qualified committed seconds and 599 unknown seconds**. This is a persistence/qualification limit: it does **not** mean all four connections were disconnected throughout. Separate, explicitly unsealed operational snapshots show good connection, ACK, heartbeat and OI states before the clock failure. No failed tail was silently upgraded to a clean segment.

The read-only summarizer verifies the frozen specification, source/runtime identities and exact pilot inventory. It admits only committed manifest-bound segments for canonical health. Standard outer-envelope JSON parsing is used where necessary for record-hash verification; raw source payloads are not decoded for analysis and source numeric values are not analyzed. All unclean tails, clock FAIL records and failed test/harness logs remain available.

## Storage findings and the user's `/data` check

Direct `df`/filesystem metadata verifies approximately **371 GB available** on `/dev/nvme0n1p3`, mounted at `/data`. Total filesystem capacity is approximately 720 GB. `/tmp` is another partition of the same physical NVMe disk; it is not an independent backup.

Pilot 2 retained **8,997,554 logical bytes**, including source/health journals, clock evidence, identity, result and inventory sidecars, over 264.795604157 seconds. This gives **0.1223 GB/hour / 2.9358 GB/day** as a provisional linear extrapolation. The journal's largest observed one-second bin was 540,187 bytes; the raw-payload peak was 36,226 bytes. Mean journal append latency was 0.1254 ms, maximum 3.8137 ms; mean fsync latency was 1.0734 ms, maximum 3.9639 ms. Average CPU was 2.18% of one core and maximum RSS 67,012 KiB. These are short pilot observations, not sustained-performance guarantees. No completed segment-manifest overhead was measurable because no seal was reached.

| Stream | Raw source bytes | Serialized source-record bytes | Metadata excluding encoded raw payload |
|---|---:|---:|---:|
| Binance bookTicker | 360,396 | 5,437,058 | 4,956,530 |
| Bybit tickers | 180,282 | 1,797,306 | 1,555,306 |
| Bybit publicTrade | 34,804 | 168,878 | 122,374 |
| Bybit allLiquidation, including control responses | 1,665 | 19,315 | 17,079 |

The current uncompressed evidence envelope dominates storage. Counting only the 577,147 raw source bytes would substantially understate retention needs. The first interrupted pilot's roughly 11.2-GB/day persisted rate was materially higher and remains visible; the quieter second pilot is not selected as a reliable annual workload.

For a **capacity illustration only**, a reference start of 2026-09-14T00:00:00Z would imply 17 context days, population 2026-10-01 through 2027-10-01 exclusive, and 382 total days. This is **not a proposed or authorized launch date**. Applying the predeclared 2× storage allowance and 50-GiB reserve to the observed interrupted-window rates yields approximately 2.30 TB and 8.60 TB **per retained copy**. Existing free space does not meet either current-format illustration. Neither pilot is a completed rate qualification, and source storms, complete manifest overhead and future activity remain unmeasured. The final qualified capacity requirement stays **UNKNOWN**.

A single fixed gzip-level-6 byte-preservation probe compressed pilot-1 journals from 5,682,878 bytes to 530,224 bytes, a **10.718×** reduction, with exact decompression equality and originals unchanged. This is evidence that a compact format could materially reduce storage. It is not an implemented or qualified primary retention, journal recovery or backup format. No compression saving is assumed in the current-format capacity gate, and no originals were deleted.

Do not buy a large disk from these incomplete extrapolations. The economical next storage step is to qualify lossless sealed-segment compression/recovery and measure a completed operational pilot, then compare the required usable capacity with the existing backup location. Without a format change, even the quieter illustration needs roughly 2.30 TB usable for each copy; the more active short window needs roughly 8.60 TB. A defensible final purchase size has not been established. No purchase, transfer, rolling eviction or automatic deletion occurred.

## Backup, recovery and final specification

`PRESERVATION_AND_LAUNCH_GATES.md` defines the proposed primary namespace, immutable metadata retention and bounded backup cadence. The tested helper verifies exact sealed segment/manifest/record identities, copies without replacement, fsyncs and reads back, and publishes immutable receipts. Recovery restores only into a new directory and retains damaged originals. Corruption, disk-full or storage faults fail closed; an unclean process/host restart requires a new session, recovery qualification, fresh same-boot clock and source reinitialization. The 1-GiB emergency floor is distinct from the 50-GiB capacity reserve.

The proposed operational arrangement seals and backs up at least every 15 minutes, reports overdue backup immediately, and stops capture after 60 minutes without verified backup progress. Daily manifest reconciliation and weekly full hash verification are proposed. These scheduling/ownership choices and complete metadata transfer still require implementation and qualification against the actual destination; the tested primitive alone does not provide them. The user has reported an existing backup location and will provide its path. No inference of absent backup or physical independence is made before that inspection.

No final production authorization package is issued because the gates did not pass. `collection_start_utc`, `population_start_utc` and `population_end_utc` remain **null**. The reviewed rule is preserved: collection begins only after authorization; context runs until the earliest later UTC month boundary at least 24 hours after actual start; twelve complete UTC calendar months follow with a fixed endpoint. No event-count early stop or rolling alpha inspection is implemented. No pilot observation belongs to that future sample.

## Reproducibility and review boundary

| Final component suite | Passed | Failed/errors/skipped |
|---|---:|---:|
| Inherited collector | 56 | 0 |
| Existing operational wrapper | 9 | 0 |
| Startup ordering/failure reporting | 16 | 0 |
| Clock attestation | 28 | 0 |
| One-second health | 35 | 0 |
| Durability/storage/recovery | 25 | 0 |
| **Total** | **169** | **0** |

Nine existing targeted checks also passed independent review; these are reruns, not nine extra implementation tests. Earlier incomplete sandbox runs and the review-only `uname -p` guard failure remain preserved. The sandbox denied asyncio's self-pipe wakeup; the identical mocked collector suite passed under the qualified runtime outside the sandbox. These harness failures are not relabelled as completed passes. The inherited ResourceWarning remains visible.

Interpreter: `/data/Trading/.venv/bin/python`, CPython **3.13.14**, executable SHA-256 `b200d6c7ae464af64f81808ba246a856b1a1cdf3b2ae7088d37d87d31aebe9ff`; websockets **15.0.1**. Exact build, platform, dependencies and source identities are in the runtime/specification manifests. Final collector hash is `79287ee6b17a1f363c27761757ea0e1241cb06e3d5ff6228ceb1ef9d6bffe475`; wrapper `d761169af300ed2b4b39928fcb3eaeddfd0166bbc4f3bac432cca2ddad6d33dd`; clock producer `d2c125faa543e89c66d9081c83269685814f3ebd89b90c1c49f5716529a9156d`; health reducer `974887748e0b0d25261ceb092ce7be90dfea742e868d699987acf045a4ddfd82`; durability helper `d0bb5aae40db7d68ee12bbf30af07bd3fb0cab5c5d7f6276db26f5669e25edfd`. The original reviewed collector is preserved; its isolated copy differs only by an optional bounded connection-lifetime argument used by the pilot. Full diffs and source ancestry are retained.

Actual final test commands include `python -B -m unittest -v test_collector test_launch_runtime test_startup_order`, the clock and health unittest suites and the durability suite, with exact interpreter paths, working directories, argv, exit codes and complete logs in their evidence directories. Each pilot used `timeout 650 /data/Trading/.venv/bin/python -B launch_runtime.py --pilot-spec ../pilot_specification.json` from its own candidate directory, with separate frozen specifications and logs. Both pilot exits were **2**. `summarize_pilot_health.py` exited **0** and preserved the failed qualification rather than manufacturing completed coverage.

No liquidation/OI threshold, qualifying-event count, future return, matching, profitability, research hypothesis or strategy result was calculated or changed. Protected preexisting 2026/OB0/L2 data and soak/account services were not accessed. The delayed independent-entry cap clarification was recorded only; no rejected breakout work was reopened. No long-running collector, production service, purchase, bridge publication or new alpha search was started.

The next review should address sustained clock qualification without relaxing 100 ms, a completed health/reconnect/rotation pilot, compact durable storage qualification and the actual backup destination. This is operational evidence repair only; no continuation is automatic.

**B. OPERATIONAL BLOCKER REMAINS — do not start collection.**
