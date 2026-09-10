# Personal BTC Research and Execution System

The repository's primary purpose is now reproducible BTC alpha research for one personal
account. The immediate objective is to falsify one economically motivated hypothesis at a
time on checksummed point-in-time data, preserve negative results, and promote nothing until
it survives realistic costs and genuinely unseen evidence. Exchange, quote currency, live
credentials, and unattended execution remain later decisions; the current live allocation is
zero.

The existing TradingAgents/Freqtrade platform is retained as a tested safety and execution
boundary, not as the research priority. Start with
[`docs/RESEARCH_TRACKER.md`](docs/RESEARCH_TRACKER.md), the frozen
[`research mandate`](docs/RETAIL_TRADING_MANDATE.md), and the mandatory
[`research standard`](docs/STRATEGY_RESEARCH_STANDARD.md). The active L2 capture is a separate
data-engineering workstream and its partial output must not be inspected.

## Existing reliability platform

This repository implements a durable infrastructure boundary between Tauric Research's
TradingAgents and Freqtrade. TradingAgents produces signed research signals;
Freqtrade remains the only component allowed to place exchange orders.

The default configuration is intentionally safe:

- research mode is synthetic;
- every synthetic decision is `Hold`;
- Freqtrade is configured for dry-run;
- the reference strategy creates no entries;
- missing, stale, corrupt, future-dated, or unhealthy signals fail closed.

## Architecture

```text
Exchange → completed-candle collector → immutable artifacts + PostgreSQL snapshots
                                            ↓
Scheduler → snapshot-backed jobs → evidence-capturing research workers
                                  ↓ atomic transaction
                      sealed manifest + signed signal ledger
                                  ↓ outbox relay
                         NATS JetStream (at least once)
                                  ↓ explicit ack
                     validator / per-bot signal bridge
                                  ↓ fsync + atomic rename
                        read-only Freqtrade snapshot

Freqtrade webhooks ───────────────→ audit API ─────→ PostgreSQL
Freqtrade REST API ───────────────→ reconciler ────→ PostgreSQL
```

PostgreSQL is the source of truth. JetStream is replaceable transport, and the JSON
snapshot is only a local materialized cache. Delivery is at least once with idempotent
effects; the system deliberately does not claim distributed exactly-once execution.

## First safe start

1. Copy `.env.example` to `.env` and replace every `replace-*` or `change-me` value.
   Generate independent secrets with a password manager or `openssl rand -hex 32`.
2. Keep `PLATFORM_RESEARCH_MODE=synthetic` and `WORKER_TARGET=platform` for the first run.
3. Validate and start the infrastructure:

   ```bash
   docker compose config -q
   docker compose up -d --build postgres nats market-collector scheduler worker outbox bridge audit-api monitor
   docker compose logs -f market-collector scheduler worker outbox bridge
   ```

4. Confirm `outbox` returns to zero and delivery receipts are materialized:

   ```bash
   docker compose exec -T postgres psql -U platform -d platform -c \
     "select disposition,count(*) from delivery_receipts group by disposition"
   ```

5. Start Freqtrade only after the synthetic path is healthy:

   ```bash
   docker compose up -d freqtrade reconciler
   ```

The reference strategy will still make no trades. It exists to verify safe data loading
and the final entry gate.

## Enabling TradingAgents

Pin and test a specific upstream tag, then set:

```dotenv
TRADINGAGENTS_REF=01477f9afb7a47b849ed4c9259d3a9a4738d9fda
WORKER_TARGET=worker-tradingagents
PLATFORM_RESEARCH_MODE=tradingagents
PLATFORM_CODE_REVISION=<your-deployment-revision>
```

The live-capture worker now records every permitted upstream response as immutable evidence,
runs deterministic source policy, and gates publication on the signed policy digest. Enable
this only for shadow validation first. Signed revocation is implemented, but actionable
Freqtrade use remains blocked until the complete hard-crash/concurrency matrix is verified;
adding an API key alone is not sufficient. See
[`docs/REAL_DATA_CONTRACT.md`](docs/REAL_DATA_CONTRACT.md).

For shadow validation, add the selected LLM provider key and run:

```bash
docker compose build --no-cache worker
docker compose up -d worker
```

TradingAgents validates structured Pydantic outputs internally but its public
`propagate()` API currently returns the deterministic Markdown renderer. The adapter
accepts only those exact headings and immediately revalidates the result against this
platform's strict contract. Free-form output is rejected.

Before using live capital, replace `ReliableSignalStrategy.populate_entry_trend()` with
an independently reviewed strategy. Any entry must set `enter_tag` to
`llm:<signal_id>` and retain `confirm_trade_entry()` unchanged.

## Core invariants

- A signal and its outbox record commit in one database transaction.
- Every analysis job references a completed, gap-free execution candle snapshot.
- Every v2 signal references that snapshot and a sealed evidence manifest.
- Raw inputs are stored by SHA-256 digest and verified when read.
- Sequence numbers are monotonic per environment/bot/exchange/pair/timeframe.
- `event_id` deduplicates broker publication and consumer receipt.
- The bridge acknowledges only after validation, receipt persistence, and snapshot replacement.
- Freqtrade performs no LLM, broker, database, or remote HTTP call in order-critical callbacks.
- New entries stop when the bridge heartbeat or signal expires; exits remain available.
- Freqtrade's database is never modified by integration services.
- Webhooks accelerate feedback; REST reconciliation recovers missing events.

## Operations

- Metrics: `http://127.0.0.1:9100/metrics`
- Optional Prometheus: `docker compose --profile observability up -d prometheus`
- Global entry stop: `ops/kill_switch.sh enable global "reason"`
- Re-enable: `ops/kill_switch.sh disable global "reason"`
- Readiness check: `ops/check_readiness.sh`
- Off-host backup: configure Restic, then schedule `ops/backup.sh` at least every five minutes.

See [operations runbook](docs/OPERATIONS.md) and [recovery runbook](docs/RECOVERY.md)
before enabling a non-synthetic worker or exchange credentials.

## Research and strategy hand-off

Strategy research is tracked separately from the reliability soak. The mandate and
cost/execution model are frozen, and the first slower candidate was specified as
`btc-volatility-expansion-continuation-v1`: 4h volatility compression followed by a
positive 1h price/range/volume/taker-flow expansion. Moving averages, RSI, MACD, and ADX
are controls rather than required entry signals. BTC/ETH, news, and L2 joins are deferred.
The candidate was rejected on development data: its pooled raw 24h mean was negative, its
30 bps executable result lost 6.31%, and none of ten frozen perturbations had a positive
net mean. It is not approved trading logic. No live orders are enabled.

All new experiments must follow the repository-wide causal validation, alpha-attribution,
matched-control, and portfolio-construction rules in
[`docs/STRATEGY_RESEARCH_STANDARD.md`](docs/STRATEGY_RESEARCH_STANDARD.md). The root
[`AGENTS.md`](AGENTS.md) makes these rules mandatory for future agent sessions.
The audit of reusable regime, routing, risk, execution, and portfolio components from the
previous crypto and OANDA repositories—and the implementation dependency order for this
repository—is in
[`docs/PREVIOUS_REPO_STRATEGY_PLATFORM_AUDIT.md`](docs/PREVIOUS_REPO_STRATEGY_PLATFORM_AUDIT.md).

An isolated reconstruction of the earlier multi-asset top-two experiment subsequently
found a profitable development candidate after enforcing real shared-capital accounting.
The simpler hold-only variants remain positive under 30/40/80 bps costs, while the
12-hour reduction is dominated. This does not change the BTC-only mandate or authorize
trading: the family is historically selected, concentrated, incompatible with the frozen
pair scope, and lacks a genuinely unseen holdout. See
[`docs/MULTI_ASSET_TOP2_DEVELOPMENT_RESULT.md`](docs/MULTI_ASSET_TOP2_DEVELOPMENT_RESULT.md).

The required R0 alpha-attribution audit is now implemented and frozen. The ranking beat the
matched seven-asset basket and 98.94% of seeded random selections in development, but the
month-block confidence interval crosses zero, profit is concentrated, only 48 primary
cohorts filled, the regime gate was not significant, and point-in-time universe membership
is unavailable. Its predeclared decision is therefore `selection_alpha_reject`; it remains
an unpromoted benchmark and must not be tuned or routed. See
[`docs/MULTI_ASSET_TOP2_ALPHA_ATTRIBUTION_R0_RESULT.md`](docs/MULTI_ASSET_TOP2_ALPHA_ATTRIBUTION_R0_RESULT.md).

P1 now also enforces point-in-time universe and unseen-evidence boundaries. It distinguishes
known ineligibility from missing evidence, verifies source checksums and gap-free timelines,
tracks strategy-family inspections, requires label embargoes, and separates locked
prospective collection from analysis. The current top-two contract intentionally fails
closed because historical membership evidence and a clean forward partition are absent;
inspected 2026 data cannot be renamed as a holdout. See
[`docs/RESEARCH_EVIDENCE_CONTRACT.md`](docs/RESEARCH_EVIDENCE_CONTRACT.md).

The first BTC/ETH-relative R2 mechanism is now closed. The frozen BTC-only catch-up rule
used ETH as context and tested completed 4-hour residual displacement over a 24-hour hold.
It lost 22.71% at the primary 30 bps cost, had a wholly negative month-block confidence
interval, underperformed its BTC-only control, and lost under all six frozen sensitivities.
It is `development_mechanism_reject`, is not trading logic, and must not be tuned. See
[`docs/BTC_ETH_RELATIVE_CATCHUP_R2_RESULT.md`](docs/BTC_ETH_RELATIVE_CATCHUP_R2_RESULT.md).

The first focused breakout/regime experiment is also complete. A fixed causal 20-day
upside-breakout control returned 16.94% from 2019–2025 at 10% account allocation and 30 bps
round-trip cost, with 5.02% maximum drawdown. Requiring a positive daily BOCPD drift state
reduced return to 6.72% and Calmar from 0.450 to 0.241; the state also had a negative
next-seven-day information difference. The BOCPD gate is rejected, 2026 remains sealed, and
the breakout is retained only as a development control pending independently frozen
walk-forward attribution. See
[`docs/BTC_ONLINE_REGIME_BREAKOUT_DEVELOPMENT_RESULT.md`](docs/BTC_ONLINE_REGIME_BREAKOUT_DEVELOPMENT_RESULT.md).
An LLM is not part of the base signal and remains deferred to a timestamp-safe event-risk
veto after a deterministic strategy independently passes.
The follow-up review of academic models and public systematic-firm practices is in
[`docs/BTC_REGIME_MODEL_INDUSTRY_RESEARCH.md`](docs/BTC_REGIME_MODEL_INDUSTRY_RESEARCH.md).
It records the revised order: validate the breakout control, benchmark continuous volatility
scaling, then consider a small heavy-tailed persistent risk-state model; do not build another
hard directional regime gate.

For the individual-trader priority order, start with
[`docs/RETAIL_TRADER_CHECKLIST.md`](docs/RETAIL_TRADER_CHECKLIST.md). Paid historical L2
data is not currently required. The research-only mandate is frozen in
[`docs/RETAIL_TRADING_MANDATE.md`](docs/RETAIL_TRADING_MANDATE.md); it authorizes no live
capital. Execution-model v1 is described in
[`docs/EXECUTION_COST_MODEL.md`](docs/EXECUTION_COST_MODEL.md). Account-specific fee and
forward-fill calibration remain pending while reliability and L2 acquisition continue in
the background. The exact candidate, rejection gates, and sealed-holdout boundary are in
[`docs/BTC_VOLATILITY_EXPANSION_HYPOTHESIS.md`](docs/BTC_VOLATILITY_EXPANSION_HYPOTHESIS.md).
The rejection evidence is in
[`docs/BTC_VOLATILITY_EXPANSION_DEVELOPMENT_RESULT.md`](docs/BTC_VOLATILITY_EXPANSION_DEVELOPMENT_RESULT.md);
the 2026 holdout remains sealed.

Start with [`docs/RESEARCH_TRACKER.md`](docs/RESEARCH_TRACKER.md). It records the open
problems, evidence, experiment matrix, cost assumptions, and promotion gates. Key data
manifests and exploratory outputs live under
[`artifacts/agent-level-experiment/`](artifacts/agent-level-experiment/). Timestamp and
source-contract work is documented in [`docs/REAL_DATA_CONTRACT.md`](docs/REAL_DATA_CONTRACT.md)
and [`docs/REAL_DATA_SOURCE_RESEARCH.md`](docs/REAL_DATA_SOURCE_RESEARCH.md).
The implementation sequence for the focused strategy and deferred alternatives is in
[`docs/STRATEGY_RESEARCH_PLAN.md`](docs/STRATEGY_RESEARCH_PLAN.md).
BTC taker-trade-flow recovery, the first event study, and historical expansion are
complete. The standalone imbalance effect and both frozen aggregate-flow conditional
mechanisms are below costs. The latest seller-absorption test produced only 6.78 bps mean
gross movement and lost 23.22 bps per filled trade after the primary 30 bps model; all 12
frozen perturbations lost. It was rejected without opening 2026 and closes further threshold
variants of aggregate five-minute taker flow. See
[`docs/BTC_SELL_FLOW_ABSORPTION_RESULT.md`](docs/BTC_SELL_FLOW_ABSORPTION_RESULT.md).

The single active new-information workstream is now the isolated BTCUSDT spot L2 order-book
acquisition and reconstruction pilot. Aggregate trades remain a control, not a substitute
for the order book; the sealed 2026 holdout remains unopened. The L2 data contract, provider
decision, frozen features, and stage gates are defined in
[`docs/BTC_ORDER_BOOK_RESEARCH.md`](docs/BTC_ORDER_BOOK_RESEARCH.md). Earlier bar-level trade-flow stages remain in
[`docs/BTC_ORDER_FLOW_RESEARCH_PLAN.md`](docs/BTC_ORDER_FLOW_RESEARCH_PLAN.md).
The isolated recorder/replayer is `scripts/btc_order_book_pipeline.py`; its short live
schema smoke test passed. The first seven-day attempt was rejected after an 11-hour host
suspension gap. Replacement capture `btc-l2-20260825T194700Z-c924306b` runs as a persistent
sleep-inhibited user service from 2026-08-25 19:47 UTC. Partial data must not be analyzed.
Health monitoring and deterministic final acceptance are implemented in
`scripts/monitor_btc_order_book_capture.py`; the predeclared post-OB0 experiment is in
[`docs/BTC_ORDER_BOOK_OB1_FROZEN_PROTOCOL.md`](docs/BTC_ORDER_BOOK_OB1_FROZEN_PROTOCOL.md).
Its causal one-second receipt-time sampling, delayed-label, segment, fold, and locked
60+30-day collection-contract foundation is implemented against synthetic fixtures; it
does not make the seven-day OB0 pilot predictive evidence. See
[`docs/BTC_ORDER_BOOK_OB1_IMPLEMENTATION_READINESS.md`](docs/BTC_ORDER_BOOK_OB1_IMPLEMENTATION_READINESS.md).
The completed exploratory result and its limitations are summarized in
[`docs/BTC_TAKER_FLOW_EVENT_STUDY.md`](docs/BTC_TAKER_FLOW_EVENT_STUDY.md).
Historical coverage and holdout controls are recorded in
[`docs/BTC_TAKER_HISTORY_EXPANSION.md`](docs/BTC_TAKER_HISTORY_EXPANSION.md).
The rejected conditional candidate is documented in
[`docs/BTC_CONDITIONAL_REVERSAL_HYPOTHESIS.md`](docs/BTC_CONDITIONAL_REVERSAL_HYPOTHESIS.md).
The corrected long-history trend benchmark is documented in
[`docs/BTC_4H_TREND_ROBUSTNESS.md`](docs/BTC_4H_TREND_ROBUSTNESS.md).

When another session is running a soak or a 100-hour/24-hour test, research work must use
the archived data and isolated scripts only; do not connect to or restart soak PostgreSQL,
NATS, or Freqtrade containers.

## Development verification

```bash
python -m pip install -e '.[dev]'
pytest -q
docker compose config -q
docker build --target platform -t tauric-freqtrade-platform:test .
```
