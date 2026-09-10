# Project Status and Parallel-Session Handoff

**Updated:** 2026-08-28  
**Scope:** TradingAgents research → reliable signal platform → Freqtrade execution  
**Safety state:** synthetic/dry-run; real-money execution is not approved.

## Current status

The infrastructure design and automated failure matrix are implemented. Two NATS restart defects
found by earlier soaks are fixed: durable consumers are explicitly rebound after reconnect, and
JetStream management readiness is retried with bounded backoff while bridge health remains
unhealthy. The hardened candidate passed **100/100 immutable matrices: 16,100 executions, zero
failures, errors, or skips**. Its production candidate digest is
`0801ee59fd52a8ab7c2b80012078854419e704dcb09baf91233943f20aa3a42f`.

A clean session-bound soak reached **598/598 passing matrices and 96,278 executions** before its
process was externally terminated. A user-systemd replacement completed 23 passing matrices but
also ended with the user session. The first Docker-supervised run passed 17 matrices, then the
host suspended for about 11 hours during matrix 18; its 30-minute test signal correctly expired,
so that run is retained as invalid infrastructure evidence rather than a product failure.

The fresh formal run uses Docker restart protection plus a persistent systemd sleep inhibitor,
non-root execution, a 30-second heartbeat, master log, exit status, and explicit completion
marker. Its guarded supervisor validation passed **1/1 matrix: 200 executions, zero failures,
errors, or skips**. The new 24-hour run started on 2026-08-25 and its first two matrices passed.

Check it with:

```bash
ops/chaos_soak_status.sh artifacts/chaos/soak-24h-docker-supervised-v2
```

Accepted evidence is in `artifacts/chaos/acceptance-100-js-readiness/`:

- 100 passed matrices;
- 0 failed matrices;
- 16,100 total test executions;
- immutable candidate manifest: `release-manifest.json`;
- aggregate metrics: `summary.json`.

Earlier attempts remain under `artifacts/chaos/` for audit history.

## Completed

- Durable PostgreSQL-backed signal and audit data contract.
- Immutable execution snapshots, artifacts, source observations, and evidence manifests.
- Strict source allowlist and timestamp-aware deterministic source policy.
- Signed v2 signals with HMAC verification, expiry, route identity, and monotonic sequence.
- Fenced worker attempts, renewable leases, stale-worker rejection, and lease recovery.
- Signed revocation tombstones; revocation is not represented as a fabricated `Hold`.
- Transactional signal/revocation plus outbox publication.
- Leased multi-relay outbox claims and live JetStream delivery.
- Durable bridge cursors, idempotent delivery receipts, atomic snapshot replacement, and DLQ.
- Freqtrade fail-closed loading for unhealthy, expired, malformed, revoked, or wrongly routed
  snapshots.
- Final entry gate requires `Buy` for long entry; `Hold` cannot authorize entry.
- Automated W1–W8 worker, O1–O5 outbox, B1–B8 bridge, D1–D3 PostgreSQL, and F1–F2 Freqtrade
  failure scenarios.
- Fail-fast repeated-run/soak harness with logs, JUnit, and p50/p95/p99 scenario durations:
  `ops/run_chaos_matrix.sh` and `ops/summarize_chaos_results.py`.
- Release manifest with separate production-candidate, test-harness, aggregate, configuration,
  migration, strategy, and container-image digests.
- Docker-supervised soak launcher that is independent of the interactive Codex/user session.
- Research-only retail mandate `retail-btc-spot-v2` and a shared Decimal execution model
  covering conservative candle taker fills, L2 depth walking, maker queue/non-fill,
  partial fills, price protection, commissions, exchange rules, and unknown-state
  reconciliation. See `docs/EXECUTION_COST_MODEL.md`; no live trading is authorized.
- Isolated `btc-online-regime-breakout-v1` development evaluation with a causal daily BOCPD
  state, fixed 4h breakout control, 30/40/80 bps costs, 12 frozen sensitivities, deterministic
  evidence, and an unopened 2026 holdout. The regime gate was rejected; see
  `docs/BTC_ONLINE_REGIME_BREAKOUT_DEVELOPMENT_RESULT.md`.

## In progress

### Reliability acceptance

1. Complete the active Docker-supervised 24-hour soak.
2. Review failure count, resource growth, and final convergence percentiles.
3. Approve or reject the recovery/convergence SLOs.

The runner now writes `release-manifest.json` and verifies the aggregate executable-file and
container-image fingerprint before every matrix. It fails if the release candidate changes.

## Not completed

- 24-hour accelerated chaos soak.
- Recovery/convergence SLO approval using soak p95/p99 results.
- Git or equivalent immutable source provenance.
- Off-host backup plus clean-host restore proof.
- Production monitoring dashboards and alert routing.
- Security review, secret rotation, restricted exchange permissions, and incident drills.
- Real timestamp-safe BTC/ETH data shadow run.
- End-to-end Freqtrade dry-run using real research signals.
- Independently frozen chronological validation and attribution of the retained BTC breakout
  development control; no strategy is approved for trading.
- Extended paper trading and limited-capital live rollout.

## Recommended separate Codex sessions

### Session 1 — Reliability gate

**Objective:** Fix test isolation, freeze a candidate, achieve 100 consecutive passes, then run
the 24-hour soak.

**Owns:** `tests/*chaos*`, PostgreSQL recovery integration tests, `ops/run_chaos_matrix.sh`,
`ops/summarize_chaos_results.py`, and `docs/HARD_CRASH_CONCURRENCY_PLAN.md`.

**First evidence:** `artifacts/chaos/acceptance-100/logs/run-0030.log`.

### Session 2 — Release provenance

**Objective:** Establish Git/versioning and generate an immutable release manifest containing
source, strategy, migration, configuration, and container-image digests.

**Must not:** modify the candidate while Session 1 is running an acceptance gate.

### Session 3 — Disaster recovery

**Objective:** Complete backup automation and restore onto a clean isolated stack; verify jobs,
signals, revocations, outbox events, cursors, receipts, and artifacts.

**Owns:** `ops/backup.sh`, recovery tooling, and `docs/RECOVERY.md`.

### Session 4 — Observability and security

**Objective:** Define SLOs and alerts for leases, outbox lag, DLQ, bridge health, sequence lag,
clock skew, resource growth, and kill switches; harden secrets, networking, and exchange access.

### Session 5 — Real-data shadow pipeline

**Objective:** Integrate timestamp-safe BTC/ETH sources and run TradingAgents through the real
contract with all Freqtrade entries disabled.

**Must not:** use the chaos database, chaos NATS, production funds, or shared snapshot directory.

### Session 6 — Strategy specification

**Objective:** Document `Buy`/`Hold`/`Sell` semantics, deterministic risk limits, entry/exit
ownership, expiry, sizing, and LLM responsibilities. Do not optimize or enable live trading yet.

## Parallel-work isolation rules

Every session must use a separate repository copy or branch and unique:

- Docker Compose project name;
- PostgreSQL container, database, and volume;
- NATS container and storage volume;
- artifact and snapshot directories;
- bot, consumer, and test identifiers.

Never edit the same files from two sessions. Never point disaster-recovery, shadow, or security
tests at the active chaos stack. Any code merged after acceptance changes the release candidate
and requires the relevant reliability gates to be rerun.

## Required order to production

```text
Fix repeatability → immutable release manifest → 100 consecutive matrices
→ 24-hour soak → clean-host restore → real-data shadow
→ Freqtrade dry-run → strategy validation → paper trading
→ tightly limited live capital
```

Infrastructure reliability does not imply profitability. No real funds should be enabled until
all infrastructure, recovery, security, dry-run, and strategy-validation gates pass.
