# Prospective forced-liquidation collection plan

Run: `prospective-and-alpha-phase2-20260912-v1`.

**Collection has not started.** This is an isolated implementation and proposed stopping-rule review. There is no launch authorization, first observation, event count or outcome result. The $22,800–$26,400/year historical routes will not be purchased.

The purpose is to preserve future public evidence capable of testing the existing forced-long-closure question later. Collection is not a trading strategy, paper observer or alpha dashboard. Workstream B proceeds separately in [Alpha Discovery Phase 2](ALPHA_DISCOVERY_PHASE2.md).

## Authority and scope

Preserve [Phase 1](ALPHA_DISCOVERY_PHASE1.md), [free-data feasibility](BYBIT_FREE_DATA_FEASIBILITY.md), and the [acquisition-route report](FORCED_LIQUIDATION_DATA_ACQUISITION_ROUTE.md) byte-for-byte. The information hypothesis, 0.5% accounting formulation and original historical failures are not revised here. The historical experiment has not been executed; the future dataset has a new identity and boundary.

Only these four public source connections are designed:

| Source / instrument | Endpoint | Subscription |
|---|---|---|
| Bybit BTCUSDT linear perpetual | `wss://stream.bybit.com/v5/public/linear` | `allLiquidation.BTCUSDT` |
| Bybit BTCUSDT linear perpetual | Same public endpoint, **separate connection** | `publicTrade.BTCUSDT` |
| Bybit BTCUSDT linear perpetual | Same public endpoint, **separate connection** | **`tickers.BTCUSDT`** |
| Binance BTCUSDT spot | `wss://stream.binance.com:9443/ws/btcusdt@bookTicker` | Native `btcusdt@bookTicker` |

The request's singular `ticker.BTCUSDT` is corrected to the exchange's documented **plural `tickers.BTCUSDT`**. This is an API-name correction, not a different information source or hypothesis. [Bybit ticker specification](https://bybit-exchange.github.io/docs/v5/websocket/public/ticker), [connection specification](https://bybit-exchange.github.io/docs/v5/ws/connect), [Binance streams](https://developers.binance.com/docs/binance-spot-api-docs/web-socket-streams).

Dedicated Bybit connections allow their acknowledgements, pings, failures and reconnects to be attributed separately. Ticker activity on a different connection cannot certify a quiet liquidation stream. No L2, REST polling, additional symbols, credentials, account API, NATS, PostgreSQL, Freqtrade, existing capture service or protected source is part of this collector.

## Dataset start and isolation

Proposed namespace: `research/btc/prospective/forced-liquidation/<reviewed-dataset-id>/`. It is distinct from existing 2026 partitions, OB0/L2 and consumed development evidence. It has not been created as an active collection dataset.

Before a launch, the reviewed authorization must pin the final collection specification, stopping rule, collector source, runtime/dependency identity, clock qualification, reliability qualification, exact namespace and UTC start/end. The freeze must precede the start. No launch authorization is supplied in this packet. The CLI fails closed without one; importing the module does not connect anywhere.

`collection_start_utc`, `first_successfully_qualified_message` and actual source-stream start times are **NOT_STARTED / null**, not this report's preparation timestamp. At a later authorized launch, record requested start, actual process/connection starts, first received record and the first format/clock/subscription-qualified record for every stream separately. First format qualification is not a whole-period completeness certificate.

The admission boundary is **our newly generated receipt time**, at or after the reviewed start and strictly before the reviewed end. Source messages actually received afterward may contain older source timestamps or a snapshot of existing state; preserve that fact as pre-start source context, not as an eligible earlier event or a recovered pre-start dataset. Do not backfill, query older archives or merge preexisting protected observations. Context is never a way to claim observations before the prospective boundary.

New observations may chronologically fall in 2026; that does not grant access to preexisting sealed 2026 evidence. The authorization is for newly captured messages after a future approved boundary only.

## Raw bytes, clocks and source identity

The prototype preserves complete WebSocket **application-message bytes** losslessly in base64, with byte count and SHA-256. Raw means the original JSON application message, including whitespace, number spelling and batched records; it does not mean TLS packets or a kernel packet capture. No normalized row replaces the raw message.

For each message preserve:

- UTC wall-clock nanoseconds and ISO UTC rendering; high-resolution monotonic nanoseconds and the measured clock-read span.
- Primary receipt is sampled at entry to `data_received`, before parsing the transport chunk containing the final WebSocket frame of the message. `dispatch_clock` separately records subsequent message dispatch. This is local userspace transport receipt, **not** an exchange timestamp, NIC arrival or reconstructed timestamp. Multiple messages/fragments can share a chunk and receipt clock; protocol parsing and dispatch occur later.
- Native system/generation and event/trade timestamps, with their original values and documented units. Missing values remain absent; local time is not inserted into an exchange-labelled field.
- Stream, endpoint, connection UUID, reconnect generation, process session, boot identity, collector version and source/runtime hashes.
- Native sequence/update/trade IDs, message type and batched item membership, plus schema/clock/duplicate flags.

Clock regressions and inconsistencies are recorded, not repaired by sorting or replacing timestamps. Native `cs` and Binance BBO `u` are not assumed to increase by exactly one per observed symbol update. Without a documented consecutive sequence, a jump alone is not a counted packet loss. Fragmentation and control frames are handled explicitly; incomplete messages at disconnect remain incomplete evidence rather than a fabricated complete report.

Source numeric strings survive raw round trips exactly. Metadata extraction must not discard raw strings through float conversion. Decimal is used only for bounded validity checks; no liquidation/OI ratio, sell-flow feature, return or strategy calculation is part of collection.

## OI state and semantic separation

Record original `openInterest`, original `singleOpenInterest` if supplied, field-presence information, snapshot/delta type, native clocks and sequence IDs. Define separately:

```text
derived_single_side_oi = Decimal(native_both_sided_openInterest) / Decimal(2)
```

This is a **definition only** in the collector, not a generated event feature. The newer native single-side field is a separate source variable. It does not overwrite the original or become an alternative denominator. Preserve disagreement rather than forcing equality.

A fresh connection needs a valid OI snapshot anchor before carried deltas can be considered initialized. Invalid snapshots, sequence/clock regressions, reconnects and uncertain tails must not silently preserve qualification. Missing field updates can mean unchanged state only under the documented delta semantics and an intact qualified state chain. The earlier July 2025 rollback is a synthetic regression case, not an input read by this collector. [Native ticker rules](https://bybit-exchange.github.io/docs/v5/websocket/public/ticker).

## Connection health and zero observations

The journal records process start/stop, boot identity, connection attempt/open/end, DNS/connect errors, close codes/reasons, subscription commands and acknowledgements, WebSocket control frames, ping/pong evidence, application pings/responses, reconnect generation/delay, planned connection rotation, message counts, native duplicates, clock/sequence regressions and persistence failures.

Duplicates are retained with flags; they are not silently deleted. Bounded in-memory duplicate detection is not a claim of global uniqueness across the year or a restart. A later approved source qualification can reconcile IDs and raw hashes from the retained bytes. Liquidation tuples without an exchange ID must not be treated as invented unique executions.

Health monitoring may expose only message/control counts, connection status, last receipt times, acknowledgement/ping state, clock flags, file identities, write latency, disk usage and source availability. It must not display prices/quantities, liquidation/OI intensity, qualifying X counts, matching, returns or favorable periods. Raw messages remain retained evidence, not dashboard content.

Use three distinct concepts:

1. **Unknown/disconnected:** no valid subscription, missed acknowledgements/pongs, process downtime, clock uncertainty, storage failure or unqualified recovery interval. Silence here is unknown.
2. **Collector-observed healthy silence:** a dedicated connection remains subscribed with timely heartbeat evidence and no observed local failure. This is a recording/transport statement.
3. **Scientifically qualified zero reports:** requires separately reviewed source-health semantics supporting that the publisher/reporting channel was functioning. Transport pongs alone cannot prove the exchange omitted no reports. The collector does **not** emit this classification automatically.

If exchange-side completeness cannot be established, retain the limitation. Stronger transport logging improves evidence; it does not manufacture proof of publisher completeness. No per-connection gap may be filled using another feed's activity. Known source loss is an exclusion/identification issue to be handled before future outcome access, never selected using profitability.

## Storage, rotation and recovery

The review prototype uses append-only, hash-chained JSONL and unique session/segment names. It rotates at its pinned byte threshold, writes segment manifests and verifies recovered identities. It must preserve partial tails and orphaned sealed files after interrupted writes/renames; no prior raw evidence is overwritten or silently truncated. Disk-full, short-write and fsync failures stop capture rather than pretending data was saved.

Group commit is bounded by its configured interval under normal scheduling. A power loss or stalled host can lose an uncommitted suffix; this is an explicit uncertainty interval, not a zero-loss claim. Unclean tails remain unqualified until recovery inspection. Boot/process identities distinguish restarts; downtime between sessions remains missing.

No evidence-retention deletion policy is authorized. No external storage or host is purchased. On the current host, read-only preflight observed approximately **345.83 GiB available**. This is not a reservation or proof that a year will fit. Existing source-record counts cannot determine future batched-message/metadata volume, especially Binance native L1.

Planning scenarios, **not measured forecasts**: at 0.25, 1 or 3 GiB/day, twelve months require approximately 91, 365 or 1,095 GiB before reserve/extra copies. With a 50-GiB planning reserve, the current free space lasts roughly 1,183, 296 or 99 days respectively. Actual byte rate, peak throughput and growth must be measured in an outcome-blind pilot before unattended collection is approved. Do not assume compression savings without qualifying a lossless archival path. No automatic eviction, recompression migration or paid storage is configured.

The implementation's emergency disk floor is a last-resort guard, not the year's retention budget. A later launch review must set an explicit operational reserve, monitoring and durable retention arrangement compatible with the observed pilot rate. If that cannot be supplied economically, stop collection design rather than discard inconvenient records or pretend the intended sample can be completed.

## Runtime and clock qualification

The synthetic target environment is local CPython **3.13.14**, with the installed WebSocket dependency pinned by version and source hashes in the qualification evidence. The exact binary path/hash, platform and actual test commands belong to the generated runtime manifest, not an invented historical environment.

`host_preflight_metadata.json` records read-only static clock configuration, clock API properties, boot-file identity and disk metadata. **Current UTC synchronization is UNVERIFIED.** A configuration file or fine clock resolution is not proof of correct UTC offset. No NTP/system service was queried or changed for this preflight.

A production launch needs a separately qualified clock-attestation producer. The immutable approval pins that producer and policy; fresh append-only measurements are selected through a hash-bound pointer in the separate prospective `_clock_health` namespace. Each measurement must report verified synchronization, the current boot ID, age at most five minutes and an absolute UTC offset bound at most 100 ms. The collector checks before sockets and every ten seconds, stopping on missing, stale or failed evidence. This producer is **not implemented or qualified here**, and its absence blocks launch. Pinning one expiring measurement instead would prevent legitimate later restarts.

The prototype's wall-versus-monotonic checks detect steps/divergence; they cannot detect every slowly growing absolute UTC error. They are not continuous external UTC certification. Any clock producer must be qualified with the collector before launch without interacting with the protected soak stack. The local authorization file and its pinned evidence are a trusted-operator review gate, not a cryptographic signature or adversarial filesystem sandbox; no valid launch file is included.

## Proposed stopping rule — review before any observation

**Recommendation: one fixed calendar collection period, no sequential alpha peeking.** These are proposed resource/identification limits, not a power calculation or a change to the historical contract.

- Start only after a reviewed freeze and launch. Initialization/context ends at the earliest UTC month boundary `b` satisfying both `b > collection_start` and `b - collection_start >= 24 hours`. The inference population begins at `b`. A launch exactly at a month boundary therefore excludes that first context month; a launch less than 24 hours before a boundary waits until the following boundary.
- Collect **12 complete UTC calendar months** of population, then stop automatically at `b + 12 calendar months`, the exclusive endpoint. This means roughly **12–13 months from launch**, and can exceed 13 months by up to about a day for a late-month launch. It is not “until enough good results.” For illustration only, most September 2026 launches would finish at October 1, 2027; a late-September launch with less than 24 hours before October can finish at November 1, 2027. Actual dates remain unset until review.
- During collection inspect no X counts, intensity distribution, targets or outcome statistics. Monthly reviews are health/storage only. No event-count-based early stop and no reaction to apparent rebounds.
- Proposed operational goal: **≥95% joint collector-health coverage in each complete month**, over all four feeds, with all gaps/reasons retained. This is a collection-quality target, **not** an automatically qualified X/label fraction. The source/publisher-health interpretation must be reviewed separately.
- At the single fixed endpoint, after the stopping rule and count-only procedure have been approved, an isolated **outcome-blind source/X feasibility audit** may ask whether there are **at least 100 qualified X events on at least 60 distinct UTC dates across at least six population months**. No such counter exists or is executed now. This audit does not read future returns or choose a threshold.
- The endpoint count is for **qualified raw X events**, not a claim that the eventual matched/label-observable sample meets the historical 100/60 floors. Future matching, target coverage, independence and uncertainty remain separate review gates. Eligibility must not use Y.
- If health or counts fail, stop and report insufficient evidence. **No automatic extension, threshold relaxation, merging old history, favorable-month selection or extra symbol.** Any extension is a new prospective resource/sample decision made without Y access and requires review. A failed fixed collection period remains in the ledger.
- If they pass, **still do not read Y**. Return for a separately frozen prospective matching/target/uncertainty contract and independent-evidence eligibility review. Collection readiness is not test authorization.

Why not simply reuse the old ten-month condition? Its required event rate is unknown. Without calculating any actual qualifying counts, 60 distinct dates alone would take about 30, 12 or 6 months at hypothetical rates of 2, 5 or 10 qualifying dates/month. One episode can generate many hourly events, so total count is not a substitute for calendar/date diversity. Twelve full months is a resource cap with seasonal breadth, not a promise of adequate power. Even 100 events could leave a wide interval for a heavy-tailed response; no true effect size or variance is assumed from the rejected breakout.

The proposed 95% health target is stricter operationally than the historical 80% monthly source floor, but neither is an economic optimization parameter. It must not be used to erase a low-coverage month or silently roll the window forward. Preserve the full fixed calendar and review any resulting unidentified sample.

For review, define operational coverage on complete UTC one-second bins. Count a bin only when all four connections remain open and appropriately acknowledged throughout, a correlated successful transport heartbeat is no more than 40 seconds old, Bybit application heartbeat evidence is also no more than 40 seconds old, OI state is initialized, clock attestation remains within the stated limits, and no unresolved local clock, parsing, queue, storage or recovery fault spans the bin. Binance's direct stream has no subscription acknowledgement; its first valid BBO plus transport heartbeat initializes it. Startup before the first successful heartbeat is unqualified. Known fault intervals remain unqualified until explicit recovery/reinitialization. Missing logs or uncertain tails are unqualified. Monthly denominator is every second in that fixed UTC month; numerator is the intersection across feeds, not the mean of four coverages. This proposed health reduction uses connection evidence only and is not implemented as an X counter or publisher-completeness classifier.

## Review implementation and reliability tests

Implementation: `research/btc/review_runs/prospective-and-alpha-phase2-20260912-v1/collector/collector.py`; synthetic tests and logs are adjacent. This is an isolated research collector prototype, with no deployment/service unit installed.

Required synthetic qualification covers UTC/monotonic capture, raw strings and message bytes, fragmentation/control frames, reconnect and acknowledgement state, duplicates, OI snapshot/delta reset, exclusive boundaries, rotation, crash recovery, corrupted/partial writes, low-disk failure and absence of outcome computation. Independent review also examines false first-message qualification and recovery/launch guards. Actual counts, failures/fixes, hashes and limitations are reported in the completed qualification evidence; no historical payload is used as a fixture.

Live endpoint connectivity, production throughput, year-long storage sufficiency and continuous UTC synchronization have **NOT** been demonstrated in this stage. No long-running process, live connectivity test or prospective dataset is started. A later reviewed health-only pilot must use a separate namespace or be explicitly included in the frozen prospective specification; it cannot silently provide pre-freeze evidence for the final dataset. No pilot is authorized or launched by this document.

Existing Binance spot price infrastructure may later provide a separately qualified future outcome series. This task does not inspect/connect to that infrastructure, consume its protected data, substitute BBO for the frozen price target or calculate any future return. Exact prospective outcome source lineage is a later pre-outcome review prerequisite.

## Current review disposition

The isolated collector passed **56/56 synthetic tests**, with **0 failures, 0 errors and 0 skips**, under CPython 3.13.14 / websockets 15.0.1. The independent review and regression probes are in `collector_review.md` and its manifest. Earlier incremental test logs, the pre-heartbeat-fix evidence and its known limitation remain preserved; the final qualification alone binds the final source.

Exact command: `/data/Trading/.venv/bin/python -B -m unittest -v test_collector`, working directory `/data/Trading/research/btc/review_runs/prospective-and-alpha-phase2-20260912-v1/collector`; final exit **0**. See `collector/command_log.json` and the final log for all recorded attempts, including an initial invalid interpreter path (exit 127, no tests started).

| Qualified identity | SHA-256 |
|---|---|
| Collector source | `08c8c11d1da56e30c940284a6eb1a2113f151ae9bdd021684b2cbb50390219e0` |
| Synthetic tests | `1d74626c75b1303823e341c71092cc0463551b1dfff27a8c2525007090fb46cc` |
| Interpreter binary | `b200d6c7ae464af64f81808ba246a856b1a1cdf3b2ae7088d37d87d31aebe9ff` |
| Proposed stopping rule | `949c321208f0e98699b8dd22f430906696ab312d44c44f00dff093545511e358` |

The runtime manifest pins the resolved executable, build/platform and dependency source files. Machine-readable proposals are `proposed_collection_specification.json` and `proposed_stopping_rule.json` in the run. They are **not launch authorization**.

This disposition means the implementation, limitations and stopping rule are concrete enough for review. Production collection remains blocked pending reviewed scope/start/end, clock-producer qualification, outcome-blind connectivity/resource qualification, durable storage/backup and launch authority. No external clock proof, live throughput result, first observation, qualifying-event count or alpha result is claimed. The 40-second heartbeat health-reduction rule is proposed, not an implemented inference classifier.

**READY_FOR_PROSPECTIVE_COLLECTION_REVIEW**
