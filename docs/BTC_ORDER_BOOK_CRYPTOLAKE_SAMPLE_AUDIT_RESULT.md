# BTC Order-Book Crypto Lake Public-Sample Audit Result

Audit ID: `btc-order-book-cryptolake-sample-audit-v1`  
Frozen: 2026-08-29  
Decision: **reject; not an accepted adapter fixture or raw replay source**

## Scope

This was a source-qualification audit only. It downloaded exactly three explicitly public
Crypto Lake sample objects: one Binance spot BTC-USDT 20-level book day and matching trade
day from 2022-10-01, plus one `book_delta_v2` day from 2024-04-01. It did not request any
2026 object, inspect the active or partial OB0 capture, compute a market feature or label,
fit a model, calculate PnL, or connect to PostgreSQL, NATS, Freqtrade, an exchange account,
or a running service.

The frozen contract separated two decisions:

1. whether the files satisfy their documented schema closely enough to be accepted as
   bounded adapter/data-quality fixtures; and
2. whether they satisfy the exchange-native replay contract required for OB1 provider data.

## Evidence acquired

All three objects matched the byte counts and multipart ETags observed before the contract
was frozen. The immutable local SHA-256 values are:

| Dataset | Partition | Bytes | SHA-256 |
|---|---|---:|---|
| `book` | 2022-10-01 | 267,304,100 | `a41f0c3a3769a1e198dade55f05cdefaf82b955a5acccd5fc19c8d6dd97e1319` |
| `trades` | 2022-10-01 | 63,447,788 | `7bebfd324a534681c9cc12416d7d1bb3e9bdb12a561cab36a2bc094ab024d270` |
| `book_delta_v2` | 2024-04-01 | 169,813,154 | `fe02470320b75d03dfe241bb14b305205fa97e0dedb02df443bc707214e1fc23` |

Parquet metadata reports 863,465 book rows, 2,190,208 trade rows, and 21,513,277 delta
rows. These counts describe file structure only; row values were not used for predictive
or economic analysis.

## Why the frozen audit rejected the sample

The real public files do not match the provider's currently documented normalized schema:

- book and delta files use `timestamp` and `receipt_timestamp`, not `origin_time` and
  `received_time`;
- the trade file uses `amount` and `id`, not `quantity` and `trade_id`;
- exchange and symbol identity are present only in Parquet schema metadata/path
  partitioning, not as required columns; and
- every downloaded file declares `contains_gaps=Yes` in its schema metadata.

The delta sample also lacks the information required by the frozen native replay contract:

- no Binance first/final message range (`U/u`), only one normalized `sequence_number`;
- no exchange-native message boundary or snapshot/update event type;
- no exchange timestamp on the delta rows under the documented field contract;
- no same-partition bundle containing snapshot, delta, and trades;
- no locations for the declared gaps; and
- no reconnect, resubscribe, snapshot, parse, clock, or dropped-message incident ledger.

The audit therefore returned `adapter_fixture_accepted=false`,
`raw_replay_contract_accepted=false`, and `decision=reject`. Renaming columns after seeing
the files would create a new source contract, but it would not repair the declared,
unlocated gaps or the missing native message semantics. Do not create a post-result v2
merely to make these samples pass.

## Disposition

- Do not use these files for OB0, OB1, feature research, or strategy evidence.
- Do not purchase Crypto Lake history on the strength of this sample.
- Retain the files and rejection as provenance evidence; provider terms prohibit
  redistribution.
- Reconsider the provider only if it supplies a separately frozen raw sample with native
  `U/u`, matching snapshots and trades, both clocks, explicit gap/incident intervals, and
  deterministic replay evidence.
- The preferred next provider action remains a raw Tardis sample and dated quote after the
  replacement OB0 engineering decision. Forward collection remains the fallback.

## Reproduction and verification

Initial bounded acquisition and audit:

```bash
uv pip install --python .venv/bin/python -r requirements-research.txt
.venv/bin/python scripts/audit_btc_order_book_cryptolake_sample.py download
.venv/bin/python scripts/audit_btc_order_book_cryptolake_sample.py audit
```

The artifact tree is intentionally write-once. Verify the preserved result with:

```bash
.venv/bin/python scripts/audit_btc_order_book_cryptolake_sample.py verify
.venv/bin/python -m pytest -q tests/test_btc_order_book_cryptolake_sample_audit.py
```

Evidence:

- contract: `config/experiments/btc-order-book-cryptolake-sample-audit-v1.json`;
- source manifest: `artifacts/agent-level-experiment/btc-order-book/provider-audits/cryptolake-sample-v1/source-manifest.json`;
- audit report: `artifacts/agent-level-experiment/btc-order-book/provider-audits/cryptolake-sample-v1/audit-report.json`;
- evidence manifest SHA-256:
  `af711e298fd8972a40b376a0617a7621a49da8ceeb8f573c3419fa3e8649b3b0`.
