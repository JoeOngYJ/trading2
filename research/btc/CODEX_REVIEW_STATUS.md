# 2026-09-13 — prospective integrated live qualification

Status: **STOP_FOR_CHATGPT_REVIEW**.
Run: `prospective-liquidation-integrated-live-qualification-20260913-v1`.
Disposition: **A. FULL OPERATIONAL QUALIFICATION PASSED — prospective collection is ready for final launch authorization.**

Repository `/data/Trading`; Git commit/dirty identity **UNKNOWN** because it is not a discoverable worktree. Isolated implementation/evidence: `/data/Trading/research/btc/review_runs/prospective-liquidation-integrated-live-qualification-20260913-v1/`. Report: `research/PROSPECTIVE_LIQUIDATION_INTEGRATED_LIVE_QUALIFICATION.md`, SHA-256 `0e1bd6294fe41c68094dfa707decd5d8dcb128110b2bd77f72d45515a6e305ad`.

Final regression: **389/389 PASS**, zero failures/errors/skips (386 inherited plus three focused tests). Exact argv, runtime, source/test hashes and exit 0: `logs/full-required-qualification-attempt4.json`. Interpreter CPython 3.13.14, executable SHA `b200d6c7ae464af64f81808ba246a856b1a1cdf3b2ae7088d37d87d31aebe9ff`. Successful pilot specification SHA `bab6ba2ada54413826a30555b656f6c1daee9b8c6a5b6d0c5c3b87a00f83d300`.

Two fresh OS processes both passed bounded clock admission before any socket. Process 1 completed two normal 15-minute rotations and archived eight source/health segments. Process 2 reconstructed sequences 0–7 from compressed-only history, reconnected all four feeds, completed another rotation and extended the same dataset chain through sequence 11, final digest `19756f3129b36f1c43e2b23039ffb0c9ab074f3d4ad2d922c764bbde05558775`. All 12 primary/SSD archive trees match byte-for-byte. Exact compression, backup readback, restore and retirement passed; no historical raw/restore/open files remain. The Samsung T7 at `/media/joe/ShieldT7` is independent USB device `/dev/sda2`, exFAT `EF5F-FBD3`, approximately 3.0 TB free.

Operational measurements: 273,244,849 journal bytes -> 19,340,295 gzip bytes, 14.1283x; compressed rate 0.593 GB/day; bounded-clock joint health 2,747/2,831 seconds = 97.0329%; separate 100-ms diagnostic 232/2,831 = 8.1950%. Primary central 381-day projection 319.81 GB including 64-GiB reserve and 2-GiB working allowance, fitting current ~371 GB by 51.29 GB. Disclosed primary deficits: 176.81 GB at 2x measured traffic and 121.47 GB under the preserved earlier high-rate case. The 100-GiB warning and 64-GiB clean-stop guard are therefore mandatory. SSD backup projections all fit.

Preserved failed attempts: attempt1 stopped before sockets on activation ordering; attempt2 stopped before child creation on exclusive-log collision; attempt3 archived operational evidence but failed on a stale duration safety boundary; attempt4 passed. Two analysis-only failures and the corrected derived Boolean are retained in `material_command_ledger.json` and `analysis/derived_operational_summary.json`. No evidence was overwritten.

Files inspected/changed: three accepted authority reports, stopping rule and prior qualification evidence; isolated operational collector/lifecycle/clock/health sources; added bounded clock admission and focused tests; created operational analyses, report, manifests and proposed launch package. Rationale: prove the last live rotation/retirement/restart gate without changing research rules. Full source and artifact identities are in the test receipt and stage manifest.

Proposed launch package: `launch/prospective_collection_specification.json`, SHA `beddfe3ed7c06644dd0a163927605cb4c8851ae39c342a2c7490fd9bc102295c`; status `PROPOSED_NOT_AUTHORIZED_NOT_LAUNCHED`. Proposed namespace `/data/Trading/research/btc/prospective/forced-liquidation/forced-liquidation-prospective-v1/`; start `2026-09-16T00:00:00Z`; population `[2026-10-01T00:00:00Z, 2027-10-01T00:00:00Z)`. If review misses the proposed start, a new pre-start package identity is required.

No alpha, liquidation ratio/threshold membership/count, market return, matching, profitability, protected preexisting 2026 evidence, soak/account/service interaction, paper/live trading, or production collection occurred. The pilot is permanently excluded. Recommended next step: ChatGPT reviews the frozen proposal and separately authorizes or rejects launch.

---

# Prospective integrated live qualification — 2026-09-13

Status: **IN_PROGRESS**.
Run: `prospective-liquidation-integrated-live-qualification-20260913-v1`.
Scope: one permanently excluded, outcome-blind, two-process four-feed operational pilot. The accepted compact lifecycle, timing-v2, health reducer, capacity policy, source feeds, hypothesis and stopping rule remain frozen. Only bounded pre-connection clock admission and its focused tests may be added before the inherited full regression.

Repository: `/data/Trading`; Git identity is UNKNOWN because this directory is not a discoverable Git worktree. Isolated candidate/evidence: `/data/Trading/research/btc/review_runs/prospective-liquidation-integrated-live-qualification-20260913-v1`. The three reviewed authority reports and the sealed prior run manifest/receipt have been copied into the new evidence directory; the prior run remains unchanged.

Planned qualification: at most 20 fresh clock attempts at 30-second intervals before every market socket, then process 1 for two normal 15-minute rotations and process 2 for another normal rotation in a genuinely new OS process. No alpha/OI ratio/X-event/return/matching/profitability computation, protected historical access, production collection or trading/soak interaction is permitted.

---

# 2026-09-13T00:08:03.944051+00:00 — prospective storage lifecycle qualification

Status: **STOP_FOR_CHATGPT_REVIEW**.
Run: `prospective-liquidation-storage-lifecycle-20260913-v1`.
Disposition: **B. STORAGE/LIFECYCLE BLOCKER REMAINS — do not launch.**

Repository: `/data/Trading`; Git commit, worktree and dirty identity UNKNOWN. Isolated candidate/evidence: `/data/Trading/research/btc/review_runs/prospective-liquidation-storage-lifecycle-20260913-v1`. Report: `research/PROSPECTIVE_LIQUIDATION_STORAGE_LIFECYCLE_QUALIFICATION.md`, SHA-256 `50e381cdaaf5834fbb56f90881b17bebde0afbd23925a890521d382ba867805a`.

Final synthetic qualification: **386/386 PASS**, zero failures/errors/skips. All 296 inherited tests, including the original 56, remain passing. All 31 inherited Python files and 451 prior qualification artifacts were verified unchanged. Compact segment records, bounded heads and bounded restart receipts eliminate repeated prefixes. Retirement and compressed-only reconstruction fail closed on missing or corrupt lineage. A reconciliation receipt is 989 bytes for 10 segments and 1,016 bytes for 10,000.

The first 376-test/source revision and failed live preflight remain preserved under `source_revisions/pre-live-attempt-v1/`. The final receipt revision received its own complete regression run. Actual-SSD synthetic verification passed: eight segments, 8,113,480 original bytes to 3,843,446 gzip bytes; exact independent readback/restores, safe removal of redundant originals/restores, and a second OS process restarting from compressed-only history. This was synthetic storage evidence, not a completed live pilot.

The live launcher exited 2 before connecting feeds. The latest timesyncd message had `ignored_spike=true`; the unchanged clock producer returned UNAVAILABLE despite optional `NTPSynchronized=true`. No clock rule was changed or retried. No market observations were received. Required live rotation, retirement, restart, throughput, working-space and coverage qualification remains missing.

Provisional allocation-aware primary requirements: 273.68 GB central, 452.80 GB at twice the prior completed rate (81.65 GB deficit), and 498.89 / 903.20 GB using retained 1× / 2× higher-rate proxies, versus 371.15 GB free. Backup requirements: 485.77 / 709.46 / 743.54 / 1,224.75 GB versus approximately 3 TB free. The final model includes extra size-triggered seals under the unchanged 64-MiB cap; normal central metadata remains linear at about 4.50 GB logical. These include SSD allocation overhead, clock sidecars, working space, bounded operational metadata and reserves. There is no new live rate or final PRIMARY ADEQUATE claim.

Inspected and changed: reviewed instructions/reports; new isolated journal/archive/queue/capacity/metrics/receipt code, focused tests, operational evidence and review documentation. Rationale: linear storage growth, byte-exact recovery, safe retirement, honest restart lineage and bounded reporting. Exact commands, interpreter/environment, exit codes and logs are recorded in the two full-qualification JSONs, the frozen pilot/integrated result, synthetic child command/results and `root_material_commands.json`. Final source/config/output hashes are in `source_provenance_final.json`, the frozen specifications and `stage_manifest.json`.

Unresolved: a successful bounded four-feed live rotation/retirement/restart pilot under fresh usable clock evidence, including live resource and coverage measurements. Recommended next step: ChatGPT review, then separately reviewed bounded live qualification without changing timing-v2. No production start, protected-data access, alpha/event/return calculations, purchase, trading/soak service interaction or research-rule change occurred. Stopping-rule SHA-256 remains `949c321208f0e98699b8dd22f430906696ab312d44c44f00dff093545511e358`.

---

# Storage lifecycle qualification

Status: **IN_PROGRESS**
Run: `prospective-liquidation-storage-lifecycle-20260913-v1`.
Scope: compact linear metadata, exact archive continuity, safe redundant-copy retirement and compressed-only restart. Prior B and all qualification evidence preserved. Timing v2, hypothesis and stopping rule unchanged. Synthetic qualification precedes excluded live pilot; no alpha/protected data/production launch.

---

# 2026-09-12T23:02:55.075495+00:00 — final prospective launch qualification

Status: **STOP_FOR_CHATGPT_REVIEW**
Run/stage: `prospective-liquidation-final-launch-20260912-v1` / final operational qualification only.
Disposition: **B. OPERATIONAL BLOCKER REMAINS — do not launch.**
Repository: `/data/Trading`; Git commit/worktree/dirty identity UNKNOWN. Isolated new candidate/evidence only.
Report: `research/PROSPECTIVE_LIQUIDATION_FINAL_LAUNCH_REVIEW.md`, SHA-256 `8fa52e5b64fd2776475d969c03f6595d8fdfbf3703d05b8005ae8e6fcf64a9e0`.

Final integrated synthetic qualification:296/296 PASS, zero failures/errors/skips; all169 prior tests including original56 preserved. Exact argv/interpreter/PYTHONPATH/exit0 and source hashes: `logs/full-integrated-qualification-1.json` in the run. Bounded960-second excluded live pilot completed exit0, including four feeds, controlled reconnect, normal900-second seal, four exact gzip→independent SSD→fresh original restores and complete session reconciliation. Actual pilot argv/cwd/exit/log: `logs/health-pilot-v2-1-command.json`; spec SHA `3f19d3f818ce04773daf2c10d63e791b198153b0cf0c46f693097e9829dc94bc`.

User-approved timing v2 uses bounded-clock monthly95%,100ms diagnostic.32/32 clock proofs PASS; bound median255.279ms, worst receipt1,054.083ms; these are conservative uncertainty, not actual UTC errors. Bounded clock959/959 seconds; joint operational898/959=93.6392% including forced reconnect/startup,100ms joint156/959=16.2669%. No month of95% is claimed.

Connected ShieldT7: `/media/joe/ShieldT7`, exFAT UUID EF5F-FBD3, separateUSB sda versus primaryNVMe nvme0n1; approximately3TB free. Four sealed segments72,482,033bytes→5,156,416bytes (14.0567×). Compressed journal0.46013GB/day, uncompressed6.46789GB/day.95 metadata files also backed up/restored exactly. Raw originals/restore copies preserved; no deletion.

Remaining blocker: unchanged continuous-process full-manifest-prefix storage grows quadratically, about390.65GB of prefixes over381days. Current-layout primary632GB central/816GB at2× compressed traffic versus371GB free; backup813GB fitsSSD. A bounded index plus redundant-copy retirement/restart remains unqualified; even hypothetical bounded-index2× case425GB exceeds current primary byabout54GB. Prefer bounded storage repair then capacity decision, not buying a disk to hide quadratic metadata. No launch dates set.

Inspected/changed: reviewed instructions/reports; read-only clock/disk metadata; new excluded source/health envelopes; isolated timing/receipt hooks, health reducer, sealed compression/backup, pilot orchestration and focused tests. Rationale: capture through ordinary timing uncertainty with explicit intervals, preserve exact raw bytes, prove independent recovery and account for storage honestly. Root material commands and component evidence are retained. Three authorities/stopping rule and202 prior qualification files verified unchanged. Earlier failed pilots and partial compression/rates remain visible.

No alpha/X membership/count, returns, matching, profitability, protected2026/OB0/L2, soak/account interaction, purchase or production launch. Phase2 B and all rejected hypotheses remain closed. Recommended next step: review bounded manifest/retirement/restart repair and primary-capacity requirements; no research hypothesis change. **STOP_FOR_CHATGPT_REVIEW**.

---

# Codex persistent review status

## 2026-09-13 — prospective boot auto-start preparation

Current stage/run: boot-persistent prospective collector enablement; `prospective-liquidation-production-service-20260913-v1`. Status: **BLOCKED** before persistent registration. Repository/worktree: `/data/Trading`, Git identity **UNKNOWN**. No market socket, prospective namespace, alpha calculation, protected-data access, paper/live trading action, or soak-stack interaction occurred.

Inspected the accepted prospective launch, lifecycle and integrated-live evidence, the exact 389-test qualified sources, user-systemd persistence state, and the Samsung T7 mount. Created an isolated production release with a continuous fail-closed wrapper, exact production path admission, designated-UUID mount preflight, two unit files, focused tests, authorization record, full test log, and `research/PROSPECTIVE_LIQUIDATION_BOOT_AUTOSTART.md`. The wrapper preserves the four feeds, clock protocol v2, 15-minute compact archive, verified compression/backup/restore/retirement, capacity policy, stopping rule and prospective dates; it has no outcome/event/strategy functions.

Commands executed: source/report reads and searches (exit 0); synthetic focused suite (5/5, exit 0); complete suite outside the filesystem/network sandbox because CPython 3.13 `asyncio.to_thread` shutdown hung inside that sandbox (394/394, exit 0, zero failures/errors/skips); qualification-only launch (exit 0, no network); `systemd-analyze verify` (exit 0, unrelated host-unit warnings); `systemctl --user link <service> <timer>` was attempted once and rejected before execution by automatic approval review. No unit was linked or enabled.

Key hashes: authorization `39ee3c1690ac6225288359010283de668e4d720c2525bfcacac722d8612c3686`; runner `83de062733d88114c6ac5072170c76f29fe027f472bd53a4bef65c3039c30621`; mount preflight `6f5d7bf7eb7556572079b064e25b110abcfb92549159145f6aa7210514fe816b`; service `8c64bfc1c9c9778886343a78488cf36e41fa4948281b7e1b99ca58f31d6225ed`; timer `37b34f81f1e89100f22a55e3e617bcf17545d1a48b89b158336f8983d392bb17`; regression log `20dc9f55d3422162d517c8a14608633ed72af11a7631adc6c5a0b8374b0e4305`.

Unresolved blockers: automatic approval review requires the user to explicitly approve persistent launch after being told that the units will start the year-long public-feed collector at `2026-09-16T00:00:00Z`; the designated exFAT SSD UUID `EF5F-FBD3` is mounted read-only (`errors=remount-ro`) and needs administrator filesystem repair plus an `rw` verification. The prepared service fails closed on that condition.

Recommended next step: obtain the explicit post-disclosure authorization required by automatic review; then register/enable the service and timer. Separately repair and verify the SSD before the frozen boundary. Do not start early or weaken any gate.

---

Status: **IN_PROGRESS**
Stage: final prospective launch operational qualification.
Run: `prospective-liquidation-final-launch-20260912-v1`.
Prior accepted B report and source evidence preserved. User approved bounded-clock monthly coverage with100ms diagnostic. IndependentUSBSSD /media/joe/ShieldT7 (exFAT EF5F-FBD3) has approximately3.0TB free. Synthetic integrated qualification296/296 PASS (zero failures/errors/skips), exact logs/source/runtime hashes in logs/full-integrated-qualification-1.json. Frozen excluded960s pilot spec SHA3f19d3f818ce04773daf2c10d63e791b198153b0cf0c46f693097e9829dc94bc. Actual command /data/Trading/.venv/bin/python -B execute_pilot.py (run cwd via full path), publicfourfeeds plus boundednewSSDnamespace only; exit pending. No alpha, protecteddata, production launch, source evidence overwrites or purchases. GitidentityUNKNOWN. Finalpilotbackup/storage/healthreview pending.

---

# Codex persistent review status

Updated UTC: 2026-09-12T21:17:38.475740+00:00
Status: **STOP_FOR_CHATGPT_REVIEW**
Stage: prospective forced-liquidation launch qualification; outcome-blind operational work only.
Run: `prospective-liquidation-launch-qualification-20260912-v1`.
Disposition: **B. OPERATIONAL BLOCKER REMAINS — do not start collection.**
Repository: `/data/Trading`; Git commit/worktree/dirty identity UNKNOWN. Isolated new candidate/evidence; exact hashes retained.

Report: `research/PROSPECTIVE_LIQUIDATION_LAUNCH_QUALIFICATION.md`, SHA-256 `54d278193da3caaf1ba37c03d5240a2ec3a01e12fb66605f32d9bec63e4a0df1`.
Evidence: `research/btc/review_runs/prospective-liquidation-launch-qualification-20260912-v1/`; final disposition, source/runtime/specification hashes, commands, test logs, both failed pilots and all retained tails preserved.

Final component tests: **169 passed, 0 failed/errors/skipped** (56 inherited +9 wrapper +16 startup +28 clock +35 health +25 durability). Nine targeted existing checks also passed independent review; not counted twice. Earlier sandbox/harness/script failures remain recorded. All five reviewed authority reports and original collector bytes unchanged.

Pilot1 exit2 after44.167s: NTP timeout and ticker snapshot-before-ACK initialization issue. Isolated bounded repair retains tentative state until real ACK; same-authority transport-only retries preserve clock limits. Pilot2 exit2 after264.796s: conservative UTC bound102.838577ms exceeded100ms; actual Ubuntu offset estimate−5.991233ms, not102.84ms. Initial connectivity/ACK/heartbeats and OI initialization worked, but planned300s reconnect/rotation never ran. Both pilots permanently excluded; no third attempt. Unsealed canonical health stays unknown, despite positive operational monitoring before failure.

`/data` approximately371GB/346GiB free. Interrupted persisted rates11.1887 and2.93581GB/day; conditional382day/context+2x+50GiB illustrations8.602/2.297TB per copy exceed current capacity. Annual usage remains UNKNOWN. Gzip6 preserves bytes at10.718x on pilot1, but production compression/recovery is unqualified and unchanged. Existing backup location reported by user; path/capacity/independence pending. No purchase or actual backup transfer.

Inspected: reviewed instructions, five authority reports, original collector/stopping/source/runtime evidence; clock/host/disk metadata; explicitly authorized new pilot envelopes/health only. Changed: isolated clock producer, health reducer, pilot wrapper/startup repair, durability primitives, required tests and evidence; new launch report, status/tracker. Rationale: resolve operational launch gates without alpha analysis. Original collector patch is only an optional pilot connection lifetime; full diffs retained.

Actual pilot command for each candidate: `timeout 650 /data/Trading/.venv/bin/python -B launch_runtime.py --pilot-spec ../pilot_specification.json`, isolated cwd and log, both exit 2. Collector final test command `timeout 40 /data/Trading/.venv/bin/python -B -m unittest -v test_collector test_launch_runtime test_startup_order`, exit 0; component commands and actual exit codes are in their logs/manifests. Read-only health summarizer and capacity assessment exited 0. `root_material_commands.json` retains known argv without inventing compacted details.

No alpha/event threshold/count/ratio, return, matching, profitability, protected2026/OB0/L2, soak/account service, production launch, strategy search or bridge action. Phase2 B stands; breakout remains closed. The delayed cap-label clarification was recorded only, with no rerun.

Next step: ChatGPT reviews clock reliability, remaining live rotation/schema qualification, compact durable storage and actual backup destination. All prospective dates remainnull; reviewed12-complete-month rule unchanged. **STOP_FOR_CHATGPT_REVIEW**. Prior progress/history below is preserved.

---

# Codex persistent review status

Status: **IN_PROGRESS**
Stage: prospective forced-liquidation launch qualification; no alpha research.
Run: `prospective-liquidation-launch-qualification-20260912-v1`.
Five reviewed reports and prior collector preserved byte-for-byte. Isolated operational candidate only. Clock gate precedes any bounded pilot; pilot is excluded from the future dataset. No long-running launch authorized.

2026-09-12 launch-qualification progress: pilot 1 stopped after 44.167 seconds on a failed NTP refresh (exit2); its raw/health tails and failure evidence remain unchanged. It separately exposed a valid ticker snapshot before its subscription ACK. Bounded startup-order and timeout-only same-authority clock retries are isolated in `attempt2/`; no clock limit or research rule changed. Final component suites: 81 collector/wrapper/startup +28 clock +35 health +25 durability =169 passing tests, zero failures/errors/skips in those final runs. An additional nine existing targeted checks passed independent review; earlier sandbox/harness failures remain preserved.

Second health pilot frozen SHA `b20e6fa88d19a7cfdadada62060789d1df3052e1684a02ca32f10337fc33273a`; actual command `timeout 650 /data/Trading/.venv/bin/python -B launch_runtime.py --pilot-spec ../pilot_specification.json`, cwd `research/btc/review_runs/prospective-liquidation-launch-qualification-20260912-v1/attempt2/candidate`, log `../logs/health-pilot-2.log`; exit pending. Fresh initial clock PASS61.73843ms preceded public connections. Exact runtime/source hashes and all component commands/exits are in the run evidence. Git identity remains UNKNOWN. `/data` direct check found about371GB free; annual sufficiency awaits measured rate. Existing independent backup location reported by user, path/capacity pending. No alpha, threshold count, future return, protected-data read or production launch. Next: complete this bounded operational pilot and return launch gates for review.

---

# Codex persistent review status

Updated UTC: 2026-09-12T20:14:07.725190+00:00
Status: **STOP_FOR_CHATGPT_REVIEW**
Stage: prospective forced-liquidation collector implementation/review and separate Alpha Discovery Phase 2.
Run: `prospective-and-alpha-phase2-20260912-v1`.
Repository: `/data/Trading`; Git commit/worktree/dirty status **UNKNOWN** (git status exit128; no repository metadata available). Isolated new evidence; no Git changes, service interaction, bridge or ZIP.

Workstream A: **READY_FOR_PROSPECTIVE_COLLECTION_REVIEW**. Collector source `08c8c11d1da56e30c940284a6eb1a2113f151ae9bdd021684b2cbb50390219e0`. Final synthetic qualification **56/56 passed, 0 failed/errors/skipped**; exact Python3.13.14 binary and websockets15.0.1 identities preserved. Review fixes covered receipt timing, invalid initialization, crash states, persistence failures, boundaries, and unique ping/pong correlation. Qualification is computational, not market evidence. No collection has started. Proposed fixed calendar rule: 12 complete UTC months after >=24h context at a later month boundary; >=95% joint monthly operational health; single later-approved endpoint feasibility audit 100 raw X /60 dates/6 months. No X counter or outcome exists. Fresh clock-attestation producer, pilot/resource/storage/backup qualification and launch review remain required.

Workstream B: **B. NO FREE/CHEAP HISTORICAL HYPOTHESIS IS CURRENTLY STRONG ENOUGH**. Three screens: public CFTC positioning, signed expiry hedge unwind, delayed CPI forecast-error response. Selected NONE; zero outcome trials. The first lacks distinct activity/sign beyond closed crowding; the second lacks signed remaining demand; the third lacks a sufficiently defensible post-delay capture mechanism and qualified vintages. No closed family reopened. CFTC exceptional-release caveat recorded without changing its REJECTED result.

Reports and hashes:
- `research/PROSPECTIVE_LIQUIDATION_COLLECTION_PLAN.md`: `96d762799b9627b5128e7d8405b01264ff365113bd0212112a2b32d15c4a0c59`.
- `research/ALPHA_DISCOVERY_PHASE2.md`: `74dde8d3134a40cfa1e2a676762a374647cf0c016a2093b0c6c33f4ca84a4138`.
Detailed evidence: `research/btc/review_runs/prospective-and-alpha-phase2-20260912-v1/`, including code, tests/logs, runtime/source manifests, proposals, independent reviews, source registers and research ledger.

Inspected: repository instructions/standards/mandate/cost model; three reviewed authority reports and frozen Phase1 proposal; tracker/status; relevant source/evaluator definitions; official exchange/CFTC/settlement/macro documentation and primary literature; read-only static host clock/disk metadata. Changed: only new isolated collector/evidence and two reports plus this status/tracker. Rationale: pursue prospective measurement within an economic data budget, and screen cheap mechanisms without manufacturing a backtest.

Actual test command: `/data/Trading/.venv/bin/python -B -m unittest -v test_collector`, cwd `.../prospective-and-alpha-phase2-20260912-v1/collector`, exit0; full attempts in `collector/command_log.json`, including initial invalid path exit127. Documentation-only macro archive command: `.venv/bin/python -B research/btc/review_runs/prospective-and-alpha-phase2-20260912-v1/documents/archive_macro_docs.py`, exit0: four archived responses and one HTTP403 retained. BLS documentation was separately read with web tooling. Final evidence script/verification commands and exit records accompany this run. Intermediate unpinned code identities remain UNKNOWN; final source/test identity is exact.

Commercial routes $22,800-$26,400/year declined as instructed. No purchase, quote submission/contact, live endpoint test, service/account operation, protected2026/OB0/L2, threshold count, future return, matching, bootstrap, empirical trial or strategy implementation. Public documentation examples/current macro tables were not repository empirical inputs. Current NTP synchronization UNVERIFIED, available disk about345.83GiB is not a year-long capacity proof.

Recommended next step: review the collection implementation, stopping rule and explicit launch prerequisites. No historical candidate is nominated for an outcome experiment. Do not launch collection or empirical work automatically. Prior records below remain historical.

---

# Codex persistent review status

Updated UTC: 2026-09-12T19:42:10.461984+00:00
Status: **STOP_FOR_CHATGPT_REVIEW**
Stage: minimum defensible data-acquisition route for the unchanged forced-liquidation study.
Run: `forced-liquidation-data-route-20260912-v1`.
Disposition: **C. QUOTE REQUIRED BEFORE DECISION**.

Report: `research/FORCED_LIQUIDATION_DATA_ACQUISITION_ROUTE.md`.
Report SHA-256: `f575e00caeaf6201a530f8ad1c5b5beefab11c767cf6cdd0f135fd2d754dfb09`.
Evidence: `research/btc/review_runs/forced-liquidation-data-route-20260912-v1/`; `QUOTE_SCOPE_NOT_SENT.md` is unsent.
Repository: `/data/Trading`; Git commit/worktree/dirty identity **UNKNOWN**. Isolated documentation/evidence run; authoritative source documents/proposal hashes unchanged.

Tardis has the strongest documented route: Bybit BTCUSDT linear perpetual allLiquidation/tickers/publicTrade, Binance BTCUSDT spot native bookTicker. Scope remains 307 UTC dates, 2025-02-28 through 2025-12-31. Historical OI derivation remains Decimal(both-sided openInterest)/2. Free OI values and spot candles remain reusable; free trade archive lacks a qualified receipt bridge. No duplicate candles, standalone OI purchase or L2 is justified.

Current public standard Tardis route: All Exchanges Professional yearly, $26,400 before tax. Conditional Perpetuals Professional + Spot Solo route: $22,800/year, pending native-L1 source/health evidence and entitlement. Narrow two-instrument price/offer remains QUOTE REQUIRED; hidden site code is not an offer. Monthly/quarterly standard lookbacks cannot reach the full envelope now. Terms 9.4 document perpetual internal retention of lawfully downloaded data. Kaiko/Amberdata exact native historical clocks remain unproven and standard termination terms require negotiated retention changes.

Metadata preserves four Bybit incidents (August 14, September 22, October 10, November 21) and one Binance context-day incident (February 28). Three Bybit losses are activity-related; missingness is not presumed benign. Full BTCUSDT continuity, per-connection liquidation health and OI reset/rollback qualification remain unresolved. Purchase cannot repair recorded source loss.

Inspected: required repository instructions/standards/mandates/costs, Phase1 and free-feasibility reports/proposal/status/tracker, provider schemas/source/coverage/pricing/terms. Changed: this status and tracker; added report, quote scope, provider notes, source snapshots, document collectors/validator, ledger, runtime and manifests. Rationale: establish source and commercial feasibility before buying evidence or evaluating outcomes.

Actual material commands: `.venv/bin/python .../documents/archive_tardis_commercial_docs.py` (initial DNS exit1; approved documentation fetch exit0); `.venv/bin/python -B .../collect_tardis_technical_docs.py` (initial DNS exit1; approved metadata/source fetch exit0); `.venv/bin/python -B .../documents/verify_documentation.py` (exit0). Exact argv, paths and errors are in command_records.json and provider logs. Fifteen documentation/source/metadata responses were archived, not market payloads. Integrated documentation checks 11 passed, 0 failed, 0 skipped; technical source assertions 10 passed; two independent report reviews PASS. Strategy/alpha tests 0 run.

No acquisition/quote/payment/contact submission, market archive request, 0.5%-OI event, future return, matching, bootstrap or new alpha outcome trial. No protected2026/OB0/L2, service, account, bridge or ZIP activity. Incidental public-page examples were not used as empirical inputs. No hypothesis change or reopening of rejected families.

Recommended next step: ChatGPT reviews the unsent exact scope and decides whether to seek a current supported entitlement/rights confirmation. No purchase, collector or outcome stage begins automatically. Prior historical records below remain unchanged.

---

# Codex persistent review status

Updated UTC: 2026-09-12T19:21:10.949458+00:00
Status: **STOP_FOR_CHATGPT_REVIEW**
Stage: authorized free-data feasibility and source qualification.
Run: `bybit-free-data-feasibility-20260912-v1`.
Disposition: **NEED PAID DATA** for the currently identified historical source route; no purchase authorized or made.

Report: `research/BYBIT_FREE_DATA_FEASIBILITY.md`; SHA-256 `0bd8e54f961573a659ea6ddb41708373e1bd38c3800e8bab7c985a15f16a6b7f`.
Evidence: `research/btc/review_runs/bybit-free-data-feasibility-20260912-v1/`.
Repository `/data/Trading`; Git commit/worktree/dirty identity UNKNOWN. New isolated evidence;
all authoritative Phase1 bytes/source proposal and earlier rejected strategy results preserved.

145boundedmarket-sourceHTTPrequests:95GET200,10officialHEAD200,40TardisHEAD404. GETs successfully
downloaded496350908bytes withoutkeys/payment. TardisHEAD404didnotmeanarchiveabsent. Initial
sandboxDNSfailure(exit1) and source-doccurlDNSfailure(exit6) preserved; authorizednetworkthenworked.
No API/account/live/paper services, protected2026/OB0/L2, forwardcollector, bridge orZIP activity.

Actualsourcefindings:OI2880/2880five-minuterows across10firstmonth2025dates, no gaps/duplicates;
10liqdays26971rows;10tickerday2340280rows;3officialtradedays6204866rows;3Tardistradedays6204883rows;
3quote days6335889rows. All29gzipfilesCRCpass. Forty native minute slices697liquidationrecords
matchnormalizedexactly. Six native ticker minutes1326anchoredOIcomparisonsmatch; oneJuly
snapshotcrosssequencerollback/generationtimestampdifference199ms remainsunresolved.
FulltradeIDreconciliation6204834matcheswithside/price/qtyexact;March3officialonlyatdayend,
July29officialonlyintraday+1Tardisprior-day,December48Tardisonlyintraday. No silentlyequalizedsources.

Historicalofficialdocsprove2025openInterest both-sidedBTC;2026singleOpenInterestadditivefield.
Documentedhalfderivation isaccountinginference forproposedsingle-sideddenominator,notserverproof;
usingrawbothsideatunchanged.5%wouldchangethehypothesis. No conversion/Xwasimplemented. Current
RESTnewfieldnonidentity1506/2880,maxresidual.00100001BTC,relative2.213e−8; causeunproved,notforced.
CurrenthistoricalresponsefieldconstructionbackfillversusrequesttimecomputationUNKNOWN.

Free10datescannotmeet60eventdatesor80%monthlycoverage. Minimumfullcalendar307dayswithcontext;
297non-free-sampledaysremain. Neednativeclosure/OIreceiptstate, Bybittradeavailabilitybridge or
receipttradehistory,andseparateBinancespotL1. BybitquotesarenotBinancecontrol. Approx307dayCSV
sizeextrapolations:liq9.3MB,ticker.89GB,officialtrades22.46GB; notmeasuredfullhistoryorpricing.

Inspected requiredstandards/costs/mandates,Phase1proposal/status/tracker, officialdatedGitHub
docs/normalizer code,andonlynewauthorized2025sourcefiles. Changedthisstatus/tracker andadded
newreport/scripts/scope/sourcehashes/HTTPlogs/rawarchives/qualification/storage/ledgerartifacts.
Rationale:resolvefreeavailability,countingandreceiptquality beforeanyspend oroutcometest.

Seven sourcequalification executions exit0; eighthistoricaldocument assertionspass.
Strategy/synthetic tests0run; no qualifyingevent,matching,Y,return,bootstrap,optimizationornewalpha.
Exactargv,source/interpreterhashes,HTTPstatus/headers,exitsandlogsretained. A long-runningHEAD
process loadeddownloader v1 but loggedondisksource v2atcompletion; botharchivedsourcesandexplicit
executed-source reconciliation arein acquisition_execution_lineage.json. No logwasrewritten.

Recommendednextstep:ChatGPTreviewsourcereceipt/reset/precisionbindings, intradaymismatches,
BinanceL1gap andactualscope/retentionprice beforechoosingpaid10monthhistoryversusseparately
frozenforwardcapture. No automaticpurchase/collector/parallelalpha/outcomeexecution.

Prior entries below remain historical.

---

# Codex persistent review status

Updated UTC: 2026-09-12T17:30:32.787155+00:00
Status: **STOP_FOR_CHATGPT_REVIEW**
Stage: alpha discovery Phase 1, mechanism/source review and conditional test design.
Run: `alpha-discovery-phase1-20260912-v1`.
Disposition: **B. DATA REQUIRED TO TEST THE BEST MECHANISM IS MISSING**.

Report: `research/ALPHA_DISCOVERY_PHASE1.md` (SHA-256 `8c7d009b91d059516c18e26667e98d326a0fd40b19945cd5e13e49ea95d7a6fa`).
Evidence: `research/btc/review_runs/alpha-discovery-phase1-20260912-v1/`.
Proposal: `btc-reported-liquidation-spot-information-v1-proposed` (SHA-256 `330b872d09f718339e49fbb36b6d680c56d61a19bfa725697121d6e26ec8d747`).
Repository `/data/Trading`; Git commit/worktree/dirty identity UNKNOWN (Git query exit128).
Isolated evidence directory; no changes to strategy source, frozen contracts or market inputs.

Two candidate mechanisms considered; direct Bybit forced-long closure reports selected only for
bounded source qualification. Actual residual leveraged-ETF rebalancing demand lacks public PIT
observations and is not selected. No hypothesis currently justifies outcome testing with qualified
local data. The one conditional proposal freezes 0.5% qualified single-sided OI/hour, decisionu+5m,
Binance spot targetu+10m to u+70m, same-month/hour/source matching, one own-date joint7day bootstrap,
10000draws/seed20260912, 80bps absolute AND incremental screen. No event counts, labels or draws
were generated. Choices are prospective judgments, not known optimal settings or empirical alpha.

Inspected authoritative reset/integrity/parent/path reports, required mandates/standards/costs,
tracker and reconciled ledger; source/schema/history metadata and primary literature. Detailed
inventory covers14data categories; history metadata audit263documents. Ledger30grouped rows,
75contracts/183decisions,10registry entries with incomplete history; effective search countUNKNOWN.
These are metadata counts, not independent experiments. Exact inspected files/pins are retained.

Prior numerical evidence preserved: fixed14day incremental−307.49bps; independent adaptive
incremental−183.38bps; sequentialcomparison+215.16bps. Breakout remains closed/REJECTED. Funding
timing, flow/reversal and other rejected families unchanged. HAR/top-two remain unaccepted.

Changed this status/tracker; added required report, source/design notes, bibliography, conditional
proposal and a retrospective research-ledger entry in the new evidence directory. Changes record
the missing pre-outcome information and prevent a new narrative from rescuing rejected predictors.
No alpha code, acquisition, experiment, service/account, paper/live, protected2026/OB0/L2 access,
ZIP or bridge activity. Public current API mechanics were read; incidental public2026BITX product
snippets from a literature search are disclosed and were not used as empirical evidence.

Validation: metadata/document consistency checks and unchanged authority/source hashes only.
Strategy/synthetic tests:0run,0passes,0failures,0skips (not applicable); outcome trials0.
Actual metadata argv/exits/runtime are in `notes/*command*.json`, `commands.jsonl`, and logs;
inspection-command records are representative, not a claimed syscall-complete access trace.
Git probe exit128 confirms UNKNOWN; one earlier inventory shell 'python' command exited127 and
was completed using the explicit interpreter. No research run failed or was repeated. Packaging
uses `/data/Trading/.venv/bin/python -I -S -B`; exact runtime/binary and validation counts in the run metadata.

Unresolved: historical2025OI units, closure-source semantics/gaps/receipt, public trades/L1
coverage, quote/archival publication clocks, sample/common support, plausible effect magnitude,
retail capture advantage, archive price/license. No new economic result exists.
Recommended next step: review bounded source metadata/schema qualification, no outcome access
or purchase without a separately reviewed scope. No next stage is automatically authorized.

Prior entries below remain historical.

---

# Codex persistent review status

Updated UTC: 2026-09-12T16:57:31.624848+00:00
Status: **STOP_FOR_CHATGPT_REVIEW**
Current task: exploratory breakout path-dependence decomposition on consumed development data.
Run: `btc-breakout-path-dependence-diagnosis-v1`; completed engineering continuation `btc-breakout-path-dependence-diagnosis-v1-runtime-init-1`.
Final diagnosis: **B. ADVANTAGE APPEARS ONLY AFTER SEQUENTIAL STRATEGY CONSTRUCTION**.
The authoritative parent frozen breakout-continuation claim remains **REJECTED**, unchanged.

Repository `/data/Trading`; Git commit/worktree/dirty identity **UNKNOWN**. Unchanged isolated source candidate:
`/data/Trading/trading2_codex_handoff/review_runs/btc-breakout-corrected-claim-resolution-v1/candidate`.
Evidence is in `research/btc/review_runs/btc-breakout-path-dependence-diagnosis-v1-runtime-init-1/`; required report:
`research/BREAKOUT_PATH_DEPENDENCE_DIAGNOSIS.md` (SHA `bb37c87ac9d319a9ff3adf7222fd2a87d6ca527dc8ebf9751a7b779f4bbc4f84`).

One completed label pass evaluated all11,700 existing M=true opportunities independently, using the
unchanged source/120-entry channel/60-exit channel/4% stop/14-day maximum hold/primary costs.
No busy state, cash depletion, cadence or previous positions were used. All238 breakout events
retain original matching;4,047 nonbreakouts have positive matching weight totaling238. Original
10,000 bootstrap starts were reused without new draws. No sequential strategy was rerun.

Independent adaptive net effect **−183.38bps**,95%[−333.93,−36.59], against the unchanged matched
nonbreakouts: breakout334.26bps versus matched517.63bps. Only2023 has a positive entry-year paired
effect; allseven leave-one-year-out effects are negative. Stop53.78% versus36.62%; channel3.36%
versus11.94%; meanwinner1342.51 versus1392.56bps.100of101 profitable breakout labels hold to day14;
onlyone profitable channel exit precedes terminal reversal. This does not support the proposed
early-profitable-channel explanation. The saved sequential comparison remains+215.16bps, but the
change in populations, matching and position state prevents causal attribution to cadence alone.
The raw−307.49bps/[−513.71,−128.80] result reconciles unchanged. This is exploratory evidence,
not independent validation or accepted alpha. B supports closing the broader direction absent a
separately justified mechanism; no research to rescue this specification is authorized.

Completed runtime: exact qualified CPython3.13.14 `/data/Trading/.venv/bin/python -I -S -B`, binary
SHA b200d6c7ae464af64f81808ba246a856b1a1cdf3b2ae7088d37d87d31aebe9ff.
cwd `/data/Trading`; clean environment PATH=/usr/bin:/bin,LC_ALL=C,TZ=UTC. Specification SHA
c799044a68ef5b2f800587834c1dd16bca7ee1867a730ae11ced12b5ef0c5858. Parent contract SHA
f9a32cdd2affe259795df86d0c89c9ff4c675b7fe4407e3a02c1126b03a69035. Input gzip SHA
316e5789d4b49f79a0adfdd90f0e98c26dd2658060c49fe2366c91dffa2024e8; input manifest SHA
506b8839a42fd3c44687020e85e995181a4033e5dbacedfcdc382801d8da18ae. All source/config/runtime/design
and exported output hashes/sizes are retained in qualification and diagnostic_manifest.json.

Verification:813 identities;32 focused synthetic tests,0failures/0errors/0skips; full production
import graph;9fresh guard probes with8explicit intentional denials and0unclassified denials;
25,709 saved primary legs (including57candidate M legs) exactly match entry/exit references,
rows/reasons/timestamps. Largest net arithmetic difference4.440892098500626e−16 is within the
pre-frozen1e−12 normalization tolerance. Final saved-evidence checks919/919 pass. Historical guard
and source-only loader remain active withzero denials/rejections; runtime random state unchanged.
Actual commands/argv/timestamps/interpreter/env/cwd/exits/loghashes are in commands.jsonl. All
completed continuation execution, qualification and verification commands exited0.

An initial diagnostic invocation failed before prices/labels because the new launcher omitted
the accepted parent's standard-library random initialization before guard installation. Its
original32passing tests,8probes, failed exit1/log and import-only `/dev/urandom` denial evidence
are sealed unchanged separately (failure manifestSHA ab83b9ba7a067fc733f339a33595626dc0dc1474474555eacfb391d0f4232724).
The separate continuation restores the parent initialization, qualifies the actual import graph
and explicitly checks entropy remains denied under the unchanged guard. No economic source,
statistical choice or retained design byte changed. This was engineering continuation before any
new label, not a repeated economic trial. The original failed process lacked a denial snapshot;
that cause is supported by the later import-only reproduction and source trace.

Inspected authoritative research state, parent results, exact contracts/source/runtime/input
identities and saved completed diagnostics. Added isolated labeling/statistics/tests, runtime
qualification, evidence verification and reporting tools to answer the bounded decomposition.
Changed only this status, tracker and new required report outside evidence directories. Original
source, frozen strategies/contracts/data and parent evidence remain intact. No2026/OB0/L2,
independent source, service/account/live/paper, optimization, new strategy, ZIP or bridge activity.

Remaining limits: overlapping event labels and repeated historical research; descriptive
unadjusted bootstrap; conditional M coverage; observational matching; OHLC path/time ambiguity.
The hypothetical entry-cap convention was disclosed before labels. One of11,700 labels is
cap-ineligible; none of the matched event/control support is cap-ineligible. This assumption
therefore does not affect the reported matched comparison; no alternative result was evaluated.

Recommended next step: **ChatGPT review only.**
**B. ADVANTAGE APPEARS ONLY AFTER SEQUENTIAL STRATEGY CONSTRUCTION. STOP_FOR_CHATGPT_REVIEW.**

Prior entries below remain historical.

---

# Codex persistent review status

Status: **IN_PROGRESS**
Run: `btc-breakout-path-dependence-diagnosis-v1`; engineering continuation `btc-breakout-path-dependence-diagnosis-v1-runtime-init-1`.
The parent frozen claim remains **REJECTED**. The exploratory independent-entry decomposition is authorized on consumed development data only.
The first diagnostic invocation failed its initial guard checkpoint before any development-input open or new label. Its 32 passing tests, eight probes, failed command and import-only entropy-denial diagnosis are sealed unchanged in the original run. The separate continuation restores the accepted parent's standard-library random initialization before project-source loading; the active guard, source loader, specification, payoff/statistical code and frozen design bytes remain identical.
Continuation qualification passed:813 identities,32 focused tests (zero failures/errors/skips),full production import graph,nine fresh-process probes (eight intentional denials;zero unclassified denials). Qualification SHA fc7d1a666fcd1c5c2c9b51d0754b76af7ffabd418a2635f80fcafb38569ff4b7. All continuation commands so far exit0. One label pass now running under the guard; no sequential strategy replay, new RNG design, protected data or strategy change. Final outcome pending. Exact argv/runtime/source/design identities and logs are retained in the continuation directory.

Prior entries below remain historical.

---

# Codex persistent review status

Status: **IN_PROGRESS**
Stage/run: bounded exploratory path-dependence diagnosis / `btc-breakout-path-dependence-diagnosis-v1`.
Prior frozen breakout-continuation claim remains **REJECTED**. User authorized independent-entry payoff decomposition on existing consumed M=true opportunities only. Pre-outcome specification and qualification in preparation; no new diagnostic labels calculated. Original source, costs, matching, bootstrap and evidence boundaries preserved.

Prior entries below remain historical.

---

# Codex persistent review status

Updated UTC: 2026-09-12T14:32:48.648903+00:00
Status: **STOP_FOR_CHATGPT_REVIEW**
Stage: completed frozen corrected breakout historical claim resolution.
Experiment: `btc-breakout-corrected-claim-resolution-v1`; continuation `btc-breakout-corrected-claim-resolution-v1-guard-repair-1`.
Principal disposition: **REJECTED**. Evidence class: consumed-development historical claim resolution, not independent evidence.
Repository `/data/Trading`; Git commit/worktree/dirty identity UNKNOWN. Exact isolated candidate `/data/Trading/trading2_codex_handoff/review_runs/btc-breakout-corrected-claim-resolution-v1/candidate`.

The [completed report](../BREAKOUT_CORRECTED_CLAIM_RESOLUTION_V1_RESULT.md) and [run evidence](review_runs/btc-breakout-corrected-claim-resolution-v1-guard-repair-1/claim_resolution_manifest.json) preserve the result. Repaired source-only qualification passed:454 identity checks;44 original plus6 import tests;14 fresh-process probes; zero positive-run failures/errors/skips/denials/rejections. Original BLOCKED evidence, its five denied cache probes and its44 passed tests remain unchanged. Accepted ten-file archive/both legacy builds reconfirmed, not rerun; old35/7 logs retained honestly.

Exactly one historical execution exited0 after qualification PASS. All600 strategy arms,13,800 strategy cohorts,69 passive cohorts and10,000 original bootstrap draws completed. Source-only loading, guard hooks and final saved-export verification passed. No strategy/inference rerun followed. Full argv/interpreter/cwd/env/times/exits/log hashes are in commands.jsonl. All named qualification, probe, historical, verification and reporting commands exited0; final sealing exit is recorded in the tool transcript.

Raw matched14-day effect: **−307.49bps**,95%[−513.71,−128.80],238/238events matched. Its negative upper confidence limit is the decisive predeclared rejection gate; adequacy passes (57primary M fills,7entry years,12cohorts; every primary control≥109M fills). Primary mean net allocated expectancy **232.04bps**,95%[−3.43,484.71],also fails positive-lower SURVIVES gate. Stress221.81bps; severe181.01bps. Candidate-minus-participation215.16bps,[31.88,422.38],rank.005 is favorable but cannot override the raw rejection. Stability/concentration positives are retained.

Execution corrections preserved common-entry apparent profitability:57common M entries,zero gross reference difference,net mean difference−3.895519384649672e−18 fraction. Same67entry identities;10Mfalse entries include5unresolved gap positions and5known losses. M opportunity coverage11,700/13,002=89.99%;entry budget coverage85.31%. Primary all-entry conservative bounds−580.86bps equal-leg/−571.13bps budget-weighted. Fullcontinuous2019–2025 profitability remains UNKNOWN/UNIDENTIFIABLE. Corrected conditional positive point estimates are not accepted alpha. Practical reference-price executability remains unconfirmed.

Contract SHA f9a32cdd2affe259795df86d0c89c9ff4c675b7fe4407e3a02c1126b03a69035; development bytes316e5789d4b49f79a0adfdd90f0e98c26dd2658060c49fe2366c91dffa2024e8; manifest506b8839a42fd3c44687020e85e995181a4033e5dbacedfcdc382801d8da18ae; S1config9a2000c6f2685a9ae878a024fb3105e7dac8ae968a9d1216b66d8cf3b7122f1d; scenarioa020cb07780e88b60fffd4c6e1b205922f0b815f033a4676dd422a7038538f36. All source/runtime/design/output pins in the sealed manifest. CPython3.13.14 executable SHA b200d6c7ae464af64f81808ba246a856b1a1cdf3b2ae7088d37d87d31aebe9ff; qualified PASS SHA3b8acbe2e891283c42cca9e4c7001e70afd499da25551dddbc26463a73d78c09.

Inspected authoritative research reset/integrity/legacy repair/contracts, pinned source and old evidence, qualification telemetry and complete saved outcomes. Changed only continuation import/guard/qualification/orchestration/evidence/reporting tools and review documents/status/tracker. Frozen strategy/statistics/design bytes unchanged; rationale: avoid optional cache probes without weakening protection, execute the already-reviewed question once, and preserve exact evidence. Known runtime provenance, missing paths, fill realism and consumed-data limitations remain explicit.

Recommended next step: **ChatGPT review only; close this exact frozen specification under its accepted decision rule.** No tuning, new alpha, protected2026/OB0/L2, services/accounts, independent confirmation, paper/live, merge/push/deploy, ZIP or bridge activity.

**REJECTED. STOP_FOR_CHATGPT_REVIEW.**

Prior entries below remain historical.

---

# Codex persistent review status

Status: **IN_PROGRESS**
Experiment: `btc-breakout-corrected-claim-resolution-v1`
Continuation: `btc-breakout-corrected-claim-resolution-v1-guard-repair-1`
User authorized one source-only import/guard repair, then exact requalification. Qualification PASS recorded at 2026-09-12T14:13:25Z: original44+import6 synthetic tests pass, zero failures/errors/skips/unclassified denials;14 fresh-process probes pass;454 identity checks and all retained design objects match. Qualification SHA `3b8acbe2e891283c42cca9e4c7001e70afd499da25551dddbc26463a73d78c09`. All qualification commands exit0. Existing BLOCKED attempt remains immutable. Economic contract and frozen design unchanged. Continuing the same already-authorized historical execution once; no new hypothesis or trial. No outcomes accessed before PASS. Exact candidate, source/runtime/design identities, commands and logs are under the continuation evidence directory.

---

# Codex persistent review status

Updated UTC: 2026-09-12T13:47:39.530525+00:00  
Status: **STOP_FOR_CHATGPT_REVIEW**  
Stage/run: `Corrected breakout claim-resolution qualification / btc-breakout-corrected-claim-resolution-v1`  
Principal disposition: **BLOCKED — pre-outcome guard qualification**.  
Repository `/data/Trading`; Git commit/worktree/dirty identity UNKNOWN.
Isolated candidate `/data/Trading/trading2_codex_handoff/review_runs/btc-breakout-corrected-claim-resolution-v1/candidate`.

User authorized one execution under exact contract SHA
`f9a32cdd2affe259795df86d0c89c9ff4c675b7fe4407e3a02c1126b03a69035`, frozen unchanged in this run.
Historical execution NOT_RUN. Reviewed research disposition C and accepted legacy reproduction stand.

[Required report](../BREAKOUT_CORRECTED_CLAIM_RESOLUTION_V1.md),
[final disposition](review_runs/btc-breakout-corrected-claim-resolution-v1/final_disposition.json),
[manifest](review_runs/btc-breakout-corrected-claim-resolution-v1/claim_resolution_manifest.json).
Pre-outcome source/runtime/identity/time-topology freeze exit0; synthetic qualification exit1 after
44/44 tests passed (6design+22accounting+16statistics;0failures/errors/skips). The subsequent
no-denials guard assertion failed on5 CPython optional project `.pyc` read attempts. All were denied;
the same profile hook remained active. No protected access or historical outcome was computed.
Raw test JSON PASS describes unittest results only; overall gate is BLOCKED. No gate was relaxed.

Verified878,985authorizedrows,34segments,23cohorts; froze13,002opportunities/11,700Mtrue and199
schedules plus10,000bootstrap draws. Exact schedule re-verification and8separate guard probes
remain NOT_RUN because they follow the failure. Prior35/35 and7/7 suites are retained, not rerun.
Actual argv/interpreter/cwd/env/exits/loghashes in commands.jsonl; failure preserved in BLOCKED.json.

Changed only new isolated copied candidate, cohort/statistics/design/guard tools, synthetic tests,
new evidence/docs, this status and tracker. Original frozen source/config/data/legacy/failed stages
remain intact. Before outcomes, static review identified mutation-capable os.open flags; guard was
hardened before formal qualification. That is distinct from the later bytecode-probe failure.
Implementation hashes, runtime/library versions, input/scenario/contract pins and output hashes
are in the manifest and qualification files. No economic numerical result exists.

Recommended next review: bounded synthetic guard/import repair using pinned source-only loading,
then qualification before reviewed resumption of the one historical execution. No repair or rerun
was performed after failure. M, control seeds, bootstrap, costs and thresholds remain frozen.
No2026/OB0/L2, live/paper/services, newsource, tuning, strategysearch, ZIP or bridge activity.
**CORRECTED_PERFORMANCE_NOT_RUN. BLOCKED. STOP_FOR_CHATGPT_REVIEW.**

Prior entries below remain historical.

---

# Codex persistent review status

Updated UTC: 2026-09-12T13:14:52.585003+00:00  
Status: **STOP_FOR_CHATGPT_REVIEW**  
Current task/run: `Legacy runtime reproduction repair / breakout-legacy-repair-20260912-v1`  
Repository: `/data/Trading`; commit/worktree/dirty identity **UNKNOWN** (Git metadata unavailable).  
Isolated byte-copy candidate: `/data/Trading/trading2_codex_handoff/review_runs/breakout-legacy-repair-20260912-v1/candidate`. This is not a claimed Git worktree.  
Reproduction disposition: **A. LEGACY REPRODUCTION REPAIRED**.  
Research disposition **C — current evidence does not support an edge** remains unchanged.

[Required report](../BREAKOUT_LEGACY_REPRODUCTION_REPAIR.md) and
[evidence manifest](review_runs/breakout-legacy-repair-20260912-v1/legacy_repair_manifest.json) record the completed stage.
Two fresh processes built new empty `legacy-repair-build-1` and `legacy-repair-build-2` directories.
Each matches all ten authoritative artifacts byte for byte; all ten mutual comparisons pass:
30 exact comparisons, no tolerance or post-processing. Forecast SHA-256 remains
`c6dda69d4f0ddae3dd13a57e39a49278bbebc3f8def72d29cac79812664511e7`.
Frozen unrounded legacy assertions, control/parity fields and aggregate counts pass in both.

Archive-compatible environment: `/data/Trading/.venv/bin/python`, CPython3.13.14, `-I -S -B`,
zlib1.3.2, exact clean environment PATH=/usr/bin:/bin, LC_ALL=C, TZ=UTC. Executable SHA-256
`b200d6c7ae464af64f81808ba246a856b1a1cdf3b2ae7088d37d87d31aebe9ff`.
Runtime addendum SHA-256 `be2ed72f0f6272ebf422826d6e75bafce41e3432aa8fd3ceac869669e9b9f259`.
This defines an archive-compatible reproduction environment. It does NOT claim that the exact
historical August interpreter binary has been recovered. The reviewed arithmetic diagnosis is
confirmed by the complete canonical reproductions; built-in sum and all frozen semantics remain.

New runtime results: integration35/35, inherited7/7, separate guard probes7/7; zero failures,
errors or skips. Both actual historical guards persisted, corrected historical calls0.
Final saved-evidence checks131/131 are separate from strategy tests. Later draft-only valuation,
distribution and deterministic-ranking clarifications have document/link checks and a retained
revision record. All named execution commands exit0; commands.jsonl includes exact argv,
interpreter, cwd, clean environment, timestamps, exit codes and log hashes. Two earlier setup
commands are in bootstrap_commands.json; read/review observations and exceptions are retained.

Frozen S1 config SHA `9a2000c6f2685a9ae878a024fb3105e7dac8ae968a9d1216b66d8cf3b7122f1d`;
authorized compressed development input SHA
`316e5789d4b49f79a0adfdd90f0e98c26dd2658060c49fe2366c91dffa2024e8`;
input manifest SHA `506b8839a42fd3c44687020e85e995181a4033e5dbacedfcdc382801d8da18ae`.
All42 explicit candidate and original pins remain unchanged. Actual imported project and
runtime sources, including originally unpinned dependencies, are recorded in the addendum/result.

**REPRODUCED LEGACY DEVELOPMENT EVIDENCE ONLY:** 67 trades in each cost case; primary/stress/severe
net return fractions 0.1693554713741534 / 0.16139102227246216 / 0.13014101538893663;
mean trade bps 239.3878505970865 / 229.15354919428668 / 188.31827885602323.
These are computational reproductions of consumed evidence, not independent confirmation or
corrected expectancy. Full exact exposure, drawdown, control and trade identities are in the report.

Inspected authoritative reset/integrity documents, required policies, frozen S1/correction
contracts, retained archive manifests, explicit source dependencies and permitted development
input. Changed only new isolated candidate/output copies, audit harness/logs/docs, this status
and tracker. Frozen source/config/data and original archive/failed Stage3A evidence are preserved.
Earlier Stage3A canonical failure is resolved by qualifying the runtime, not by changing its gate.

[Proposed corrected contract](contracts/btc-breakout-corrected-claim-resolution-proposed-v1.md)
SHA-256 `f9a32cdd2affe259795df86d0c89c9ff4c675b7fe4407e3a02c1126b03a69035` is **PROPOSED ONLY; NOT AUTHORIZED OR EXECUTED**.
It freezes chronology/costs and proposes separate observed-source cohorts, analysis-only complete
14-day windows, raw/control attribution and explicit expectancy/uncertainty gates. Its conditional
claim cannot establish full continuous-history profitability across gaps. Coverage policy, control
design, gates and any required corrected reporting implementation await coordinating approval.
Exact historical August runtime and execution inside unobserved gaps remain UNKNOWN.

**CORRECTED_PERFORMANCE_NOT_RUN.** No new alpha, tuning, unrelated family investigation, sealed2026,
protected OB0/L2, live/paper service interaction, merge/push/deployment, ZIP or bridge publication.
Bridge work remains deferred under the user's earlier steering. Detailed local evidence is retained.

**RETURN FOR CHATGPT REVIEW — corrected breakout claim-resolution is now technically ready for separate authorization.**

Earlier status entries below are historical and superseded only for the legacy reproduction blocker.

---

# Codex persistent review status

Updated UTC: 2026-09-12T12:39:47.839706+00:00  
Status: **STOP_FOR_CHATGPT_REVIEW**  
Current task/run: `Evidence integrity resolution / evidence-integrity-resolution-20260912-v1`  
Repository: `/data/Trading`; isolated audit output: `research/btc/review_runs/evidence-integrity-resolution-20260912-v1/`.  
Git commit/worktree/dirty identity: **UNKNOWN**, metadata command exit128.  
Research disposition: **C — current evidence does not support an edge**, preserved.  
Historical gate: **BLOCKED — Stage 3A canonical legacy output identity**.

## Current evidence-integrity resolution

[EVIDENCE_INTEGRITY_RESOLUTION](../EVIDENCE_INTEGRITY_RESOLUTION.md) is complete.
Breakout investigation decision **B: producer/runtime difference identified**. Final next-stage
recommendation **B: breakout provenance remains broken; do not run corrected performance**.

The original archived replay matches all 10 core files. Stage3A differs in aggregated candle
volumes and resulting forecast lineage hashes: 30,084 of 42,612 volume fields differ. Identical
source volumes reproduce every Stage3A sum under CPython 3.10.12 and every archived sum under
current CPython 3.13.14. Every one of 15,303 forecast rows differs only in its two digest fields.
Stored legacy decision fields, features, trades and report are exact matches. Both runtimes
repack each original payload to its own exact gzip bytes. This is not gzip metadata and is not
full semantic identity. The exact August executable binary remains UNKNOWN. All 22 source/config/
permitted-development input pin comparisons pass; no tolerances or canonical hashes changed.

HAR 34 invalid days and downstream coverage match the frozen metadata/window rules exactly;
outage versus ingestion origin UNKNOWN. Top-two has zero membership evidence sources and seven
UNKNOWN histories; current dataset cannot confirm its historical universe claim. Ridge/C2 exact
producer/input bindings remain incomplete; stale summaries are qualified. Reconciled ledger:
30 grouped history rows, 75 contracts, 183 decision records, 185 inspected source identities. All
three recorded decision chains validate internally; total trials/external freeze timing UNKNOWN.

Inspected required AGENTS/standards/mandate/cost docs, unchanged reset, frozen S1/correction
contracts, retained S1/replay/Stage3A artifacts, exact permitted input bytes, relevant producers,
runtime libraries, old aggregate diagnostic reports, HAR/top-two metadata and research registries.
Changed only new audit documentation/diagnostic scripts, this status, tracker, three qualified
cash summaries and supplemental cash audit-status metadata. Frozen sources/configs/results remain.
Old cash context pins are preserved and intentionally fail against annotated docs; original
bodies/before copies and diffs are retained, with no implicit context requalification.

Validation: resolution 20/20; blast-radius documentation 40/40; HAR exact calendar/coverage
comparisons pass; 3 decision chains pass. Strategy suite tests run 0 (passed/failed/skipped 0/0/0),
all historical strategy runs 0. Prior 35/35 and 7/7 synthetic suites are not rerun. Actual command/
interpreter/argv/cwd/exits and hashes are in the run. Preserved exceptions: missing lookup paths
(exit1), unavailable Git (exit128), a diagnostic syntax error (exit1) fixed before artifact access.
No failed identity requirement was relaxed. Main source/output hashes and review checks are in
the run manifest and resolution_verification.json. No new performance metrics calculated.

Recommended next action for separate ChatGPT review: bind archive-compatible runtime/dependencies
and authorize a legacy-only two-build exact reconciliation, with synthetic/guard qualification
under that runtime. Neither those builds nor corrected performance were run now. Corrected
coverage policy must also be frozen before a later historical claim-resolution authorization.
No sealed 2026, protected OB0/L2, service, live/paper, merge/push/deploy, ZIP or bridge publication.
**CORRECTED_PERFORMANCE_NOT_RUN. STOP_FOR_CHATGPT_REVIEW.**

---

# Codex persistent review status

Updated UTC: 2026-09-12T01:00:09.156364+00:00  
Status: **STOP_FOR_CHATGPT_REVIEW**  
Research gate: **BLOCKED — Stage 3A canonical legacy output identity**  
Current task/run: `Repository edge audit / edge-research-reset-20260912-v1`  
Historical execution checkpoint remains: `Stage 3A / stage3a-20260912-v1`  
Latest material task: `edge-research-reset-20260912-v1` — completed source/report audit; outcome C, no market execution.

## Repository edge research reset — completed, outcome C

[EDGE_RESEARCH_RESET](../EDGE_RESEARCH_RESET.md) reconstructs the actual research history,
ranks limitations, separates prediction/execution/sizing, audits contamination, scores three
mechanisms and selects no new strategy hypothesis. The concrete carry example reuses an
already completed falsification; MCS3-C already answers the current net-economics readiness
question negatively. No new test or acquisition is justified by repeating that evidence.

**C. CURRENT EVIDENCE DOES NOT SUPPORT AN EDGE — stop strategy engineering and identify what
information would be required to continue.** This means no independently confirmed capturable
incremental trading decision, not that every forecast contains no information.

Important preserved positives: HAR one-day QLIKE improvement interval[.06253,.12323] with
coverage rejection; carry101 threshold-qualified/nonqualifying weekly observations (43/58)
and future28day funding difference60.8811bps; top-two ranking+181.98bps/event but interval
crosses0 and universe/confirmation invalid; EWMA favorable risk benchmark, not accepted alpha.
These are stored consumed-development values, not new strategy results.

New static findings qualify the old ridge forecast clock/horizon/purge, cash-ETF entry/equity
and falsely named month-block intervals, and legacy carry same-hour liquidation chronology.
No source-to-output corrected impact is claimed. Carry no-funding is a fresh simulation, not
a verified fixed-fill intervention; equal notional is not equal tail/margin risk. Cash2019–23
had numeric data-engineering exposure despite nominal locked labels. Three cash development
arms exist; prior tracker summaries are stale. Prior claims of universal no-information or
independent repeated carry failure were too broad. Source/code was not repaired in this audit.

Inspected mandatory documents, contracts, reports, registries, representative source/tests and
selected aggregate artifacts. Three bounded specialist audits and skeptical draft reviews are
preserved, with correction decisions. Tests run0 (passed/failed/skipped0/0/0), market runs0;
only document identity/link checks performed. Three selected BTC summary reports match INDEX
hashes. Git requests fail (exit128); exact root/data identity remains /data/Trading, commit and
dirty state UNKNOWN. No raw market, sealed2026, partialOB0, services, credentials, ZIP or bridge.

Changed only the new reset/evidence documentation, this status and a tracker audit note. Prior
status/tracker snapshots and diffs, source/output hashes, actual command observations, runtime,
machine-readable history/contamination/candidates and final local review are in
`research/btc/review_runs/edge-research-reset-20260912-v1/`. Existing archived evidence is intact.
The historical Stage3A canonical output identity remains BLOCKED; corrected performance NOT_RUN.

Recommended next step: coordinating review of outcome C and the exact missing information,
not another strategy, parameter search, automatic acquisition or blocked historical rerun.
Actual user capital/time/risk constraints and a practical capture advantage remain UNKNOWN.

## Alpha discovery discussion — no experiment activated

User requested a better way to discover alpha rather than continued online strategy searches.
[Method note](review_runs/alpha-discovery-method-20260912-v1/ALPHA_DISCOVERY_METHOD.md)
proposes observable market mechanisms, a feasible personal advantage, explicit falsifiers,
small predeclared tests and separate discovery/confirmation. A mechanism is not proof, and
compensation for risk is not automatically alpha. No specific new family or benchmark selected.
Next proposed deliverable is one mechanism page for review, before code or performance access.

Only this status and the new advisory evidence changed; prior status and diff preserved.
Inspected this status; referenced the previously read policy/diagnosis and retrieved two primary
methodological abstracts (direct opens returned 403). Numerical results unchanged. Tests run 0
(passed/failed/skipped 0/0/0), historical runs 0. No source/config/input changes or new hashes of
market data. Git identity remains UNKNOWN. Details/byte hashes in the new run manifest.
Current advisory status: STOP_FOR_CHATGPT_REVIEW. Stage 3A remains BLOCKED; corrected historical
performance remains NOT_RUN. Prior proposed effort cap is not an approved execution budget.

## Current direction proposal — awaiting review

The user asked whether to stop or change direction. Recommendation: stop expanding the broad
strategy search; retain the evidence and propose one bounded closure decision. A proposed cap
of 10 engineering hours over two weeks is an effort limit, not a validation horizon or approval.
Dependable near-term income is not supported by any accepted strategy. Personal goal, capital,
tolerable drawdown and weekly time remain unanswered; a text clarification was requested.

[Direction plan](review_runs/project-direction-decision-20260912-v1/PROJECT_DIRECTION_PLAN.md)
sets conditional stopping rules. Narrow provenance reconciliation requires coordinating review;
any corrected historical comparison still requires the existing gates and frozen coverage.
Failure or inconclusive economic evidence closes the line without an automatic new search.
No benchmark, alpha family, parameter, allocation, cost or mandate is changed or accepted.

Inspected AGENTS, retail mandate, execution costs, research standard, tracker, program review,
prior diagnosis and this status. Changed only planning evidence, this status and a tracker note
to preserve the user's requested direction decision. Read commands exited 0. Tests run: 0
(passed/failed/skipped 0/0/0); strategy simulations: 0. Source/output hashes, actual commands,
interpreter information and diffs are in the new run. Stored numerical results are unchanged;
no new discrepancy found. Git identity remains UNKNOWN. Bridge work stays deferred.

Recommended next step: review the stop/continue proposal and personal usefulness before
authorizing further work. Historical status remains Stage 3A BLOCKED; current planning task
is STOP_FOR_CHATGPT_REVIEW. Corrected historical performance remains NOT_RUN.

## Latest user steering and diagnosis

The user explicitly set bridge/operator work aside and requested an assessment of the
repository's effectiveness for individual trading. Bridge publication is deferred and is
not a dependency for this evidence review. Earlier bridge status remains below as history.

[Current diagnosis](review_runs/retail-research-diagnosis-20260912-v1/RETAIL_RESEARCH_DIAGNOSIS.md):
profitable legacy backtests exist, but durable incremental trading value is unproven. Several
added timing/model rules failed simpler controls; low allocation/participation limits account
returns separately from alpha; sparse/reused evidence limits confidence; infrastructure work
has exceeded what the strategy evidence warrants. These are interpretations of stored results,
not new tests or corrected performance. Keep causal/cost/negative-result safeguards.

Inspected the program review, breakout mechanism report, perpetual trend rejection, safe carry
v2 report, EWMA report and prior status. Changed only this status plus the new diagnosis/evidence
files to record the requested economic focus. Source hashes, read/search commands and exit codes,
external methodological source, preserved prior status and status diff are in the new run.
No tests executed (passed/failed/skipped: not applicable; zero tests run), no market rows,
sealed data, strategy code changes, ZIPs or bridge calls for this task.

Important stored results: breakout +16.94% legacy total at 10% allocation over 2019–2025;
entry timing diagnostic at random-control percentile 54.31 (seven-day diagnostic only);
trend blend −6.41% in consumed 2024–2025; funding gate +2.95% versus same-exposure always-on
+7.75%; EWMA incremental-return confidence intervals include zero. Earlier exact tables and
hashes are retained below. No new contradiction or mismatch was discovered by this review.

Recommended next decision: keep research focused on one economically motivated rule, verified
execution and predeclared full-system controls, with usefulness evaluated at frozen risk and
realistic maintenance effort. Do not activate another model family or increase size. The
existing canonical identity and unapproved coverage policy still block corrected historical
performance; they do not block reviewing already recorded strategy evidence.

## Authority and persistent workflow

ChatGPT coordinates review and decides stage transitions. Gate A acceptance was reported by the user and authorizes only the bounded Stage 3A continuation already attempted. It does not approve the current blocked result or a corrected historical performance run. Continue within approved scope only; do not infer new approval. Preserve negative results, frozen legacy S1 and sealed 2026 partitions.

After each material task, update this file and write exact manifests, command logs, results, diffs and reproducibility details to `research/btc/review_runs/<run-id>/`. Use the approved bridge snapshot/artifact mechanism at decision points. Do not create another ZIP unless requested. Bridge failure must retain local evidence and the exact blocker.

Stop for ChatGPT review before hypothesis or parameter changes, a new alpha family, higher allocation/leverage, cost changes motivated by weak performance, post-result benchmark selection, sealed-data access, out-of-sample relabelling, live promotion, or unauthorized strategy merge/push/deployment. Keep execution/accounting, signal quality, sizing and infrastructure separate. Do not optimize for a headline return.

## Repository and working copies

- Repository root: `/data/Trading`.
- Commit and dirty-versus-committed status: **UNKNOWN**; last recorded `git status --short` exited 128 because usable Git metadata was unavailable. Not rerun for this administrative task.
- Original correction working copy: `/data/Trading/trading2_codex_handoff/review_runs/execution-corrections-20260912-v1/candidate`.
- Original Stage 3A working copy: `/data/Trading/trading2_codex_handoff/review_runs/stage3a-20260912-v1/candidate`.
- New `research/btc/review_runs/` directories are verified copies of review evidence, **not** replacement execution roots. Archived commands keep their actual original cwd and timestamps.
- All 28 selected original files and nine reviewed candidate files matched their recorded identities at the Stage 3A stop. Original code, datasets and archived results were not modified by this administrative task.

## Evidence locations

- [Correction review](review_runs/execution-corrections-20260912-v1/REVIEW_PACKET.md) and [manifest](review_runs/execution-corrections-20260912-v1/review_manifest.json).
- [Stage 3A report](review_runs/stage3a-20260912-v1/STAGE3A_REVIEW_PACKET.md), [manifest](review_runs/stage3a-20260912-v1/stage3a_manifest.json), [topology](review_runs/stage3a-20260912-v1/segment_topology.md), and [legacy reproduction](review_runs/stage3a-20260912-v1/legacy_s1_reproduction.json).
- [Administrative evidence](review_runs/persistent-review-state-20260912-v1/evidence_relocation.json): exact copied-file hashes and original locations.

## Files inspected and changed; rationale

Inspected AGENTS.md, existing reviewed manifests/reports, source-provenance records, topology, legacy failure results, command logs, handoff bridge instructions and current bridge metadata. This task copied only manifest-listed review files and verified their hashes/sizes. No historical payload or sealed partition was opened.

Added this status file to persist stage/authority/evidence context. Added the two historical review directories as byte-identical copies so review evidence follows the requested layout. Added the administrative receipt, bridge responses, publication request and status diff. No strategy source, frozen contract, archived outcome, research threshold or cost was changed.

Historical correction changes are separately documented in the correction package: new versioned execution ordering, timestamp/gap handling and period-return reporting. They remain explicitly separate from legacy S1.

## Commands and observed results

Historical Stage 3A commands below were executed previously, not rerun now. [Full argv/cwd/times/log hashes](review_runs/stage3a-20260912-v1/evidence/commands.json).

| Actual command label | Exit | Tests passed/failed/skipped |
| --- | ---: | --- |
| synthetic-integration | 0 | 35/0/0 (errors 0) |
| synthetic-inherited | 0 | 7/0/0 (errors 0) |
| input-byte-verification | 0 | Not a test suite |
| development-validation-topology | 0 | Not a test suite |
| legacy-source-verification | 0 | Not a test suite |
| legacy-build-1 | 0 | Not a test suite |
| legacy-build-1-verification | 1 | Not a test suite |

Current administrative command: `python3 research/btc/review_runs/persistent-review-state-20260912-v1/maintain_review_state.py`; actual completion/exit and subsequent integrity checks are recorded in this administrative run's commands.json. Read-only bridge calls: bridge_status, repo_context(trading2), repo_files(the snapshot below). Their exact responses are preserved. No strategy run or test rerun was executed for this task.

## Exact identities and important numbers

- Reviewed Gate A ZIP: `01d5acf7c2bd5ed4457f22f31cca9ce4cbafda2fb04c14dbfc1b0b3ad94e722b` (previous identity; no new ZIP created).
- Corrected breakout: `6d2e796cc61b41ef0311a13327d1bdd63694cc4ce4a2a57fb72cc99ff3c322fc`.
- Corrected reporting: `b490b00b1b6c9cb24ad05a09547a9a36b66bae102dfa8e6561e630f9cad49524`.
- Correction contract: `9f22365f9a5b96e0eec157cb8b183631f98a5f1978462af13e065dfd56687737`.
- Development gzip byte hash: `316e5789d4b49f79a0adfdd90f0e98c26dd2658060c49fe2366c91dffa2024e8`.
- Development manifest byte hash: `506b8839a42fd3c44687020e85e995181a4033e5dbacedfcdc382801d8da18ae`.
- Frozen S1 contract: `9a2000c6f2685a9ae878a024fb3105e7dac8ae968a9d1216b66d8cf3b7122f1d`.
- Frozen execution scenarios: `a020cb07780e88b60fffd4c6e1b205922f0b815f033a4676dd422a7038538f36`.
- Validated development input: 878,985 five-minute rows and 34 source segments. Evaluation: 23 overlapping segments, 735,593 rows, 68 hours 35 minutes missing, 99.888242515% calendar coverage.
- Reviewed synthetic suites rerun in Stage 3A: 35/35 integration and 7/7 inherited, zero failures/errors/skips. No new test counts are claimed for this administrative task.

Observed **legacy development only** numerical values, copied from saved results:

| Cost scenario | Legacy net return fraction | Exposure fraction | Trades |
| --- | ---: | ---: | ---: |
| candle-primary-30bps-rt-v1 | 0.1693554713741534 | 0.18716464131659763 | 67 |
| candle-severe-80bps-rt-v1 | 0.13014101538893663 | 0.18716464131659763 | 67 |
| candle-stress-40bps-rt-v1 | 0.16139102227246216 | 0.18716464131659763 | 67 |

Exact numerical parity is insufficient: the full canonical S1 reproduction gate failed. These are not corrected results or strategy acceptance. Full input/config/output inventories remain in the linked manifests and legacy_s1_reproduction.json.

## Discrepancy and unresolved assumptions

- Failed file: `breakout-forecasts.jsonl.gz`.
- Archived expected SHA-256: `c6dda69d4f0ddae3dd13a57e39a49278bbebc3f8def72d29cac79812664511e7`; 1,453,464 bytes.
- Observed SHA-256: `a5d634b17d8010587ff0071cee4489d6e5512f184a15b3eaecba7ee26c39db5b`; 1,453,708 bytes.
- The first legacy build exited 0; its subsequent canonical check exited 1. The required second build was not run. No compression-only diagnosis, normalization, substitution or relaxed check is justified.
- The precise source of this mismatch remains unresolved. Git provenance and some older individual dependency hashes are unavailable.
- Corrected historical coverage/restart/attribution policy is not frozen or accepted. Corrected historical PnL, trades, return and drawdown remain **NOT_RUN**. No new benchmarks, controls, EWMA, trend, funding or parameter experiments are authorized.

## Bridge publication blocker — historical, work deferred by user

Publication status: **BLOCKED; no new snapshot or artifact ID**. The live connector returned only `snapshot_08adb66dc4f64931a094fe829feefeb5`, created 2026-09-11T22:49:50.039Z, containing eight older policy/project documents. Neither this status file nor the new review directories is included. The repository has zero artifact IDs.

Exposed actions provide approved snapshot reads and bridge-owned tasks, but no snapshot publication/refresh or host artifact-upload operation. repo_context explicitly cannot refresh/grant access. bridge_status reports backend=mock, native_tools_disabled and a locally attested connection; this is not proof of real execution or newly published evidence. No task was created to bypass those limits.

Exact responses: [bridge_publication_evidence.json](review_runs/persistent-review-state-20260912-v1/bridge_publication_evidence.json). A file-and-hash [publication request](review_runs/persistent-review-state-20260912-v1/publication_request.json) is prepared for an authorized local snapshot operation. It is a requested file set, **not** proof of publication. Local evidence and originals are preserved.

## Recommended next step / stop

Bridge work is deferred at the user's direction. Review the current economic/process diagnosis
and decide the next bounded research question. A corrected historical profitability comparison
still requires exact legacy/provenance reconciliation and a frozen coverage/attribution policy;
none is authorized or executed by this review. Preserve the existing rejected experiments.

**STOP_FOR_CHATGPT_REVIEW**
