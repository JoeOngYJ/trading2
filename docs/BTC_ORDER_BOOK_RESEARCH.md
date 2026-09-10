# BTC Spot Order-Book Research

Last reviewed: 2026-08-29

**OB0 implementation status:** recorder and deterministic replayer implemented; synthetic
tests and a 15-second live smoke capture passed. The first seven-day attempt was rejected
after host suspension created an 11-hour gap. Replacement capture
`btc-l2-20260825T194700Z-c924306b` started as a persistent, sleep-inhibited user service at
2026-08-25 19:47:00 UTC and is scheduled to finish around 2026-09-01 19:47:00 UTC. Do not
analyze its partial data.

## Decision

The next focused experiment is **BTCUSDT spot L2 order-flow imbalance (OFI)**. It asks
one question only:

> After the book state and book events known at a decision timestamp, is there stable,
> out-of-sample information about the next 1–10 seconds of executable BTC price movement
> beyond signed trades, spread, and trailing return?

This is not another candle-indicator strategy. The existing kline taker-buy fields and
Binance `aggTrades` describe executed trade flow; they cannot reveal resting liquidity,
new limit orders, cancellations, queue depletion, or a reconstructable historical book.
They are controls for the L2 experiment, not substitutes for L2 data.

For a retail trader, any detected signal should first be evaluated as an entry/exit
timing and adverse-selection filter for a slower strategy. A standalone 1–10 second
taker strategy is unlikely to survive unless its executable move exceeds fees, spread,
slippage, latency, and missed fills.

## Evidence behind the choice

Cont, Kukanov, and Stoikov define OFI from changes at the best bid and ask and report a
more robust short-horizon relationship with price changes than raw trade volume, with
impact related to market depth. Gould and Bonart find queue imbalance informative for
the next mid-price move, especially in large-tick instruments. Stoikov's micro-price
formalizes an imbalance-aware estimate of the future price. These results motivate the
features, but do not establish a tradable BTC edge.

A recent BTCUSDT L2 replication is an especially important warning: its out-of-sample
OFI result reversed twice as the capture grew from roughly 7 to 17 days. We therefore
predeclare a long, day-blocked evaluation and prohibit conclusions from a one-week
pilot.

Primary references:

- [The Price Impact of Order Book Events](https://arxiv.org/abs/1011.6402)
- [Queue Imbalance as a One-Tick-Ahead Price Predictor](https://arxiv.org/abs/1512.03492)
- [The Micro-Price](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2970694)
- [BTCUSDT OFI result-instability replication](https://papers.ssrn.com/sol3/Delivery.cfm/7227998.pdf?abstractid=7227998&mirid=1)

## Data feasibility

### What is free from Binance

Binance publishes checksummed spot `trades`, `aggTrades`, and klines. Its public market
WebSocket also exposes live partial-depth and diff-depth streams, and the REST depth
endpoint provides a current snapshot. Binance documents the required live-book procedure:
buffer depth events, obtain a snapshot, align update IDs, then apply events in order.

This supports a **free forward capture**, not a historical spot L2 backfill. The public
archive does not list historical spot diff-depth files. The older Binance historical L2
download documentation found in the public-data repository concerns futures, notes gaps
and limited snapshot coverage, and is not an acceptable substitute for spot execution
research.

Official references:

- [Binance public archive and schemas](https://github.com/binance/binance-public-data)
- [Binance spot market-data streams and local-book reconstruction](https://github.com/binance/binance-spot-api-docs/blob/master/web-socket-streams.md)
- [Binance spot depth and aggregate-trade endpoints](https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md)

### Historical L2 options

| Source | Fit for this experiment | Material limitation | Decision |
|---|---|---|---|
| Free Binance forward capture | Native BTCUSDT spot diff-depth and trades; update IDs permit validation | Starts now; cannot recreate past book state; local disconnects create gaps | **Preferred free path** |
| Tardis.dev | Exchange-native raw Binance spot replay preserves depth messages, generated snapshots, local arrival time and disconnect markers | Raw access is paid; every reconnect and sequence gap must be measured; normalized CSV is insufficient | **Three-date raw pilot frozen but blocked under `btc-order-book-tardis-raw-pilot-v1`** |
| Crypto Lake public sample | Public Binance spot book/trade samples from 2022 and deltas from 2024 | Frozen audit found schema drift, every file declared unlocated gaps, and native `U/u`, incident metadata, and a same-period replay bundle were absent | **Rejected under `btc-order-book-cryptolake-sample-audit-v1`** |
| CryptoHFTData free archive | Public zero-auth Binance spot hourly order-book and trade files from June 2025; receipt time plus native update/trade IDs | The exact documented example hour had contiguous updates/trades but zero snapshots and null `last_update_id`, contrary to the documented hourly snapshot-plus-update contract; replay could not initialize | **Rejected under `btc-order-book-cryptohftdata-hour-day-audit-v2`; remaining day not downloaded** |
| Kaiko | Institutional L2 tick data and useful exchange/collection timestamp fields | Full spot order-book cloud history is more recent and access is quote-based | Secondary paid option |
| Binance public `aggTrades` | Free, checksummed, long history, exact aggressor-side trade sequence | No resting orders, cancellations, depth, or queue imbalance | Control dataset only |
| Binance futures `bookDepth` | Free futures snapshots/metrics for some products | Different venue/instrument; reported archive quality concerns; not spot L2 | Reject for primary test |

Do not purchase a full history yet. The frozen `btc-order-book-tardis-raw-pilot-v1` contract
selects exactly 2019-12-01, 2022-12-01 and 2025-12-01 mechanically, requires native `depth`,
`depthSnapshot` and `aggTrade`, and blocks execution until final OB0 acceptance. It also requires
the user's approval of a dated one-off quote before payment. The public pricing surface observed
on 2026-08-29 listed spot plans from USD 450/month equivalent and a USD 300 minimum one-off
order, but raw replay was shown only for Professional and Business tiers. Those values are a
dated list-price observation, not a quote or purchase authorization. See
`docs/BTC_ORDER_BOOK_TARDIS_RAW_PILOT_PLAN.md`.

Provider references:

- [Tardis historical-data overview](https://docs.tardis.dev/historical-data-details/overview)
- [Tardis data FAQ](https://docs.tardis.dev/faq/data)
- [Tardis billing and subscriptions](https://docs.tardis.dev/faq/billing-and-subscriptions)
- [Kaiko data dictionary](https://docs.kaiko.com/explore-our-data/data-dictionary)
- [Kaiko L2 bids and asks](https://docs.kaiko.com/stream/data-feeds/level-1-and-level-2-data/level-2-tick-level/bids-and-asks)

Tardis officially allows downloadable CSV datasets for the first day of each month
without an API key. The documented Binance BTCUSDT sample URLs are:

- `https://datasets.tardis.dev/v1/binance/incremental_book_L2/2019/12/01/BTCUSDT.csv.gz`
- `https://datasets.tardis.dev/v1/binance/trades/2019/12/01/BTCUSDT.csv.gz`

The normalized L2 CSV contains exchange timestamp, local timestamp, snapshot flag, side,
price, and absolute amount. It preserves original row order but does not expose Binance
`U/u` update IDs. It can validate an adapter and feature equivalence, but it cannot alone
satisfy the raw sequence-integrity contract. Before purchasing history, require a small
exchange-native raw replay sample containing `U/u`, generated snapshots, local timestamps,
and incident metadata.

The frozen Tardis pilot uses only exchange-native raw replay. Normalized CSV cannot substitute.
It is currently `blocked_pending_final_ob0_acceptance_and_provider_access`; no sample, API key,
quote form, order, or payment has been requested or submitted.

Automated sample probing from this host was blocked by the provider's Cloudflare policy
(HTTP 403 on a ranged GET); this is not evidence that the documented sample is absent.
Use a normal browser download or an authorized API key rather than bypassing that control.

Crypto Lake's explicitly public S3 sample was separately audited under the frozen,
data-only ID `btc-order-book-cryptolake-sample-audit-v1`. The three declared files matched
their remote sizes and ETags, but the actual schemas differed from current documentation,
all three declared `contains_gaps=Yes`, and the delta file did not preserve native Binance
`U/u`, message/snapshot typing, incident locations, or matching same-partition trades. The
sample is rejected for both adapter acceptance and raw replay. Preserve the result at
`docs/BTC_ORDER_BOOK_CRYPTOLAKE_SAMPLE_AUDIT_RESULT.md`; do not rename fields and relabel
the consumed sample as accepted evidence.

CryptoHFTData's free archive was then checked under two preserved data-only IDs. V1 rejected
the exact 2025-08-01 20:00 UTC example hour because its initial contract incorrectly required
exchange time and receipt time to occupy the same hour. V2 retained the immutable files and
corrected only that convention: receipt time owns availability and the partition. The source
still failed decisively. All 1,674,190 order-book rows were `update` events, while snapshots were
absent and `last_update_id` was null throughout. The 35,991 update groups and 170,806 trades had
contiguous IDs, but deltas cannot establish absolute resting depth without an initial snapshot.
The predeclared gate therefore blocked the remaining 23 hours. Preserve the result at
`docs/BTC_ORDER_BOOK_CRYPTOHFTDATA_AUDIT_RESULT.md`; reconsider the provider only if it supplies
a same-period snapshot and explicit incident boundaries before a new audit is frozen.

## Required data contract

The experiment must not begin until a forward capture or paid sample provides:

- venue `binance`, market `spot`, symbol `BTCUSDT`, and an explicit symbol-mapping record;
- raw diff-depth messages at the documented 100 ms stream cadence;
- initial and reconnect snapshots deep enough to initialize the local book;
- first/final update IDs and deterministic rules for detecting missing or crossed updates;
- exchange event timestamp and local UTC receipt timestamp with microsecond-capable storage;
- raw aggregate trades with aggressor side and trade/aggregate-trade IDs;
- reconnect, resubscribe, snapshot, parse, clock-offset, and dropped-message audit events;
- immutable compressed raw partitions, SHA-256 checksums, byte/row counts, and a manifest;
- provider/exchange license terms permitting internal research and retained derived data.

Reject or segment, never silently repair, any interval containing an update-ID gap,
snapshot-alignment failure, crossed book, non-positive price/quantity, timestamp reversal,
clock anomaly, or unbounded reconnect. The manifest must distinguish exchange gaps from
collector gaps where the source permits that distinction.

## Frozen pilot and research stages

### Stage OB0 — Acquisition validation

Use seven consecutive development days only to verify capture and reconstruction. This
stage may debug parsers and quality checks but may not select a predictive threshold.
Acceptance requires:

- every raw partition has a checksum and source/capture metadata;
- all update-ID discontinuities are detected and represented as segment boundaries;
- reconstructed best bid is always below best ask in accepted segments;
- replay produces byte-identical feature partitions and manifests;
- accepted coverage, gap duration, reconnect count, message rate, timestamp latency, and
  book depth are reported by UTC hour.

Seven days can accept the pipeline, never the strategy.

### Stage OB1 — Descriptive development analysis

Use at least 60 accepted calendar days spanning weekdays, weekends, low/high volatility,
and more than one market regime. Preserve a later contiguous period as a sealed test.
No 2026 kline holdout may be joined or inspected; this L2 study receives its own sealed
time boundary.

Compute only these predeclared features:

1. top-of-book queue imbalance;
2. depth-weighted imbalance over levels 1, 5, and 10;
3. Cont-style best-level OFI from quote/size changes;
4. micro-price minus mid-price, normalized by spread;
5. additions, cancellations, and depletion intensity by side;
6. signed aggregate-trade flow as the required non-L2 control;
7. spread, total depth, event rate, short realized volatility, and stale-book age as
   state/control variables.

Primary labels are future mid-price changes at 1, 2, 5, and 10 seconds after a decision
latency. Report next-tick direction only as a diagnostic because it does not represent an
executable return.

### Stage OB2 — Frozen out-of-sample test

Start with regularized logistic/linear models and monotonic bins. Compare:

- null/training-mean forecast;
- signed trades plus spread and trailing return;
- L2 features plus the same controls.

Use chronological walk-forward folds, UTC-day blocks, purge/embargo at boundaries,
HAC-aware inference, and moving-block bootstrap intervals. Report calibration, log loss,
direction accuracy, out-of-sample R-squared, and stability by day/regime. A nonlinear
model is allowed only after this baseline is frozen.

### Stage OB3 — Economic simulation

Apply a decision-to-arrival latency grid of 100, 250, 500, and 1,000 ms. For taker
execution, cross the contemporaneous ask/bid and include fees, depth-walk slippage, and
outages. For maker execution, model queue uncertainty, non-fill probability, timeout,
cancel latency, and adverse selection; do not assume a touch quote filled.

Promotion requires incremental performance over the signed-trade control after all
costs, confidence intervals that do not depend on one day/regime, and acceptable turnover
and drawdown. Statistical significance or next-tick accuracy alone is a failure.

## Immediate implementation order

1. **Complete:** Build an isolated Binance spot forward recorder and deterministic replay validator;
   do not connect it to PostgreSQL, NATS, Freqtrade, or soak containers.
2. **Running:** Run only the seven-day OB0 acquisition pilot.
3. In parallel with elapsed capture time, request a **sample and quote**, not a purchase,
   from Tardis for Binance spot BTCUSDT raw depth plus trades on development dates.
4. Compare the paid sample against the same reconstruction contract.
5. Choose forward-only collection or a small historical pilot based on completeness,
   reproducibility, timestamp quality, and written cost/license—not model performance.

The recorder/replayer and its validation tests are complete, and the seven-day acquisition
is running. Model tuning, news joins, ETH cross-impact, deeper neural
networks, and cross-venue books remain deferred until OB0 passes.

## Decision after the replacement OB0 run

The local seven-day run answers only whether the capture/replay pipeline works. It would
be inefficient to hold this workstation awake for another 90 days before the first
information test. If replacement OB0 passes:

1. validate the free normalized Tardis day as an adapter/storage test only;
2. request a raw Binance spot BTCUSDT depth-plus-trades sample and dated quote;
3. buy no data unless raw sequence IDs, snapshots, local timestamps, incidents, license,
   and deterministic replay all pass;
4. if the raw pilot passes and the quote is acceptable, obtain a predeclared 60-day
   development block plus a separately sealed 30-day block;
5. otherwise move forward collection to an always-on host rather than preventing a
   personal workstation from sleeping for 90 days.

Do not start another strategy family during this decision. A provider-format adapter,
cost/latency model, and source-contract validation are permitted because they test the
same frozen L2 hypothesis without inspecting predictive outcomes.

## Implemented pipeline and smoke evidence

`scripts/btc_order_book_pipeline.py` provides two isolated commands:

```bash
uv pip install --python .venv/bin/python -r requirements-research.txt

.venv/bin/python scripts/btc_order_book_pipeline.py capture --duration-seconds 604800

.venv/bin/python scripts/btc_order_book_pipeline.py replay \
  --capture-dir artifacts/agent-level-experiment/btc-order-book/captures/<capture-id> \
  --output-dir artifacts/agent-level-experiment/btc-order-book/replays/<capture-id>
```

Capture uses only Binance's public market-data WebSocket and REST endpoints. It records
exact source JSON inside canonical envelopes, exchange and local timestamps, update IDs,
initial/reconnect snapshots, clock samples, and audit events. Hourly raw partitions are
fsynced, deterministically compressed, atomically renamed, and checksummed.

Replay verifies the capture manifest and every raw checksum. It discards snapshot-overlap
events, requires the first usable depth event to bridge `lastUpdateId + 1`, fails closed
on later update gaps or crossed books, validates consecutive aggregate-trade IDs, and
emits deterministic feature/trade CSV files plus an accepted/rejected segment manifest.
It streams output to disk rather than retaining a multi-day dataset in memory.

The 2026-08-25 smoke run produced:

- 165 raw records in one checksummed partition;
- 123 accepted depth events and 13 expected stale snapshot-overlap events;
- 24 consecutive aggregate trades;
- one accepted segment with zero gaps or rejected intervals;
- byte-identical output checksums on a second replay;
- observed event receipt latency of approximately 125 ms to 1.93 s, including buffered
  initialization traffic;
- one clock sample with approximately 1.04 s HTTP round-trip time.

Evidence is under
`artifacts/agent-level-experiment/btc-order-book/captures/btc-l2-20260824T234254Z-4a508f0a/`
and `artifacts/agent-level-experiment/btc-order-book/smoke-replay-final/`.

The smoke volume extrapolates to roughly 2.4 GB of compressed raw data for seven days,
but BTC activity varies substantially. Reserve at least 10 GB and monitor hourly growth.
Current workspace free space was 361 GB at the smoke decision point.

### Active seven-day capture

Capture ID: `btc-l2-20260825T194700Z-c924306b`

Running manifest:
`artifacts/agent-level-experiment/btc-order-book/captures/btc-l2-20260825T194700Z-c924306b/capture-manifest.json`

The running manifest deliberately includes only finalized hourly partitions in
`record_count`, while `active_record_count` includes the current `.part` file. It is
atomically checkpointed every 60 seconds. Normal completion finalizes the last partial
hour and changes `status` to `complete`. Do not invoke replay or feature analysis until
that status is present.

Initial replacement health confirmation: 6,428 active records, approximately 7.0 MB
uncompressed, one connection, zero reconnects, and 358 GiB free workspace storage.

The collector runs in user systemd unit `btc-l2-ob0-retry.service` under a blocking sleep
inhibitor. The watcher runs in `btc-l2-ob0-retry-watch.service`. This prevents terminal
session cleanup and normal host suspension from silently invalidating the replacement.

The automatic watcher is running with:

```bash
.venv/bin/python scripts/monitor_btc_order_book_capture.py watch \
  --capture-dir artifacts/agent-level-experiment/btc-order-book/captures/btc-l2-20260825T194700Z-c924306b \
  --output-dir artifacts/agent-level-experiment/btc-order-book/acceptance/btc-l2-20260825T194700Z-c924306b \
  --poll-seconds 60
```

It fails closed on a stale checkpoint, inactive partial file, less than 10 GB free disk,
or any finalized-partition checksum error. Once capture status becomes `complete`, it
runs replay twice, compares output checksums, applies the 99.5% accepted-depth and hourly
coverage gates, and writes `ob0-acceptance-report.json`.

On 2026-08-28 the capture service was confirmed active with zero process restarts, but the
documented transient watcher unit was absent. A metadata-only health check passed, and the
watcher was restored without restarting or modifying the capture. The idempotent recovery
command is now:

```bash
ops/start_btc_ob0_watcher.sh btc-l2-20260825T194700Z-c924306b
```

The script refuses an invalid capture ID, missing manifest, inactive capture service, or
missing research environment. If the watcher is already active, it only prints service
state. It does not read predictive features or submit traffic to the capture, soak stack,
database, broker, or exchange.

### Rejected first attempt

Capture `btc-l2-20260825T000755Z-c17faa24` collected nine checksummed partitions before
the host slept. Its last pre-suspend message was at 08:23:58 UTC; the timeout was observed
at 19:34:27 UTC, a 40,228.881-second gap. It reconnected correctly with a new snapshot,
but continuous OB0 coverage was already impossible. The raw evidence was preserved and
the rejection is recorded in its `ob0-failure-report.json`; it will not be joined to the
replacement or used for predictive analysis.

## Safety boundary

All files must live under the isolated research artifact tree. Do not connect to or
restart soak PostgreSQL, NATS, Freqtrade, or their volumes. Captured data are research
inputs only and authorize no live orders.
