# Typed Source-Policy Research

**Status:** Research, capture prerequisites, pure evaluation, and durable persistence are complete. Structural
capture hardening, fenced session identity, source-specific temporal metadata, the strict
BTC/ETH ingress allowlist, deterministic rule evaluation, verdict/rating constraints, and
reproducible input/configuration/result digests, immutable normalized rule rows, and atomic
policy-bound seal/reject transitions and the fenced publication rating gate are implemented.
Worker orchestration is next.

## Objective

Decide deterministically whether one completed TradingAgents input ledger permits:

- any typed research rating;
- only an original typed `Hold`; or
- no signal publication.

The evaluator must use immutable typed records and verified artifacts. It must never infer
source quality by reading LLM reports.

## Main conclusion

The current ledger is not yet expressive enough for a trustworthy policy evaluator. Writing
policy rules directly against it would create false passes. The next implementation step is
therefore **capture-contract hardening**, followed by the evaluator itself.

Implementation update: migration `006_semantic_invocations.sql` and the capture adapter now
separate graph-level invocations from ordered vendor attempts, persist exact router returns,
reject error-shaped strings before artifact creation, and freeze evidence in `evaluating`.
Capture session creation and every close/seal/reject transition now verify the exact live
job, worker, attempt, fencing token, run, session, manifest, and unexpired lease. The enabled
method allowlist now validates exact BTC/ETH instrument identity, method/category/consumer,
research symbol, frozen per-method vendor chains, and observed fallback order. Typed metadata records
requested/resolved symbols, source windows, item counts and times, daily-bar closure,
information cutoff, timestamp completeness, and stable quality flags. Yahoo news and Reddit
timestamps are captured through pre-render hooks; incomplete chronology never becomes a
silent success.

### Gaps that must be closed first

| Gap | Consequence |
|---|---|
| Vendor calls and semantic graph returns share one `source_calls` model | The ledger cannot distinguish a failed primary, successful fallback, and final value delivered to the graph |
| `fallback_ordinal` is always zero and there is no invocation/group ID | Configured fallback order cannot be proven |
| Router-generated `NO_DATA_AVAILABLE` and `DATA_UNAVAILABLE` values are outside the current wrappers | The exact value consumed by an analyst may be absent from the ledger |
| Several vendors catch exceptions and return ordinary strings such as `Error fetching...` | Failures can be recorded as `available`; exception text may also contain secrets |
| Observation `event_at` and `published_at` are currently empty for adapter calls | Future news, social timing, daily-bar closure, and `data_as_of` cannot be verified mechanically |
| Normalized artifacts contain rendered strings without structured source metadata | Symbol, resolved symbol, item times, bar time, item count, and result kind require fragile prose parsing |
| `consumer` is unset | We cannot prove which analyst received a value |
| Capture sessions have job/attempt/fence columns, but session creation does not populate them | Policy evidence is not yet bound to the fenced worker attempt |
| The current seal function uses configured requirements rather than evaluated results | A manifest can be sealed without a persisted policy decision |
| Current-day Yahoo daily data can be incomplete | A live run can mix a closed Binance 5-minute candle with an unfinished Yahoo daily bar |

The pinned-source audit makes method-specific adapters safe to maintain, but broad string
matching is not an acceptable substitute for typed metadata.

## Required capture model

Separate a **semantic invocation** from its **vendor attempts**.

### Semantic invocation

One record for each value requested by or prefetched for the graph:

- invocation/session/run IDs and a contiguous invocation ordinal;
- method, category, consumer, and stable policy subject;
- canonical typed arguments and argument digest;
- started, first-seen, completed, and information-cutoff timestamps;
- final typed outcome;
- exact normalized artifact delivered to the graph;
- typed metadata artifact or JSON and observation ID;
- replay-safety classification.

The final outcome taxonomy is closed and versioned:

```text
available | no_data | unavailable | timeout | rate_limited | auth_error
vendor_error | invalid_response | policy_rejected
```

An upstream error-looking value that is not recognized by the pinned method adapter is
`invalid_response` and aborts the run. It must not be stored as a successful observation.

### Vendor attempt

Zero or more ordered attempts under one semantic invocation:

- vendor and contiguous `fallback_ordinal`;
- configured-chain position;
- timestamps, typed outcome, and sanitized error code;
- raw artifact when safely accessible;
- vendor-normalized artifact and observation reference when available.

The final semantic value is stored separately even when it is generated by the router after
all vendor attempts fail. This proves exactly what reached the graph.

### Typed metadata

Pinned method adapters must emit metadata without asking the policy layer to parse prose:

- requested and resolved symbol;
- requested start/end date;
- earliest/latest item or bar time;
- publication times and item count;
- quote/venue where known;
- whether a market bar is closed;
- explicit result kind such as `data`, `no_data`, or `upstream_error`;
- source-specific quality flags.

For Yahoo news, this requires capturing article timestamps before rendering because the
current rendered result does not retain them. For swallowed exceptions, the adapter must
raise a sanitized platform error or use a pinned upstream hook; arbitrary exception text
must never enter artifacts, policy details, or logs.

## Policy execution model

```text
execution preflight
    -> session collecting
    -> graph and all semantic invocations complete
    -> capture adapter uninstalled
    -> session evaluating (ledger becomes immutable)
    -> artifact loader verifies every digest and builds PolicyInput
    -> pure versioned evaluator returns PolicyResult
       -> pass      : all typed ratings permitted
       -> hold_only : only an original typed Hold permitted
       -> reject    : no signal permitted
    -> persist result and seal/reject manifest
    -> fenced publication gate checks result digest and permitted rating
```

Add `evaluating` as a nonterminal capture state. The transition from `collecting` closes the
ledger before filesystem verification begins. A crash in `evaluating` is recovered as an
abandoned attempt. No source call may be inserted once evaluation starts.

The manifest must remain collecting while the graph makes dynamic calls. It closes after
the graph and before publication—not before the LLM starts.

## Policy result contract

One immutable result per capture session:

```json
{
  "policy_version": "source-policy/1.0.0",
  "policy_configuration_hash": "sha256:...",
  "session_id": "...",
  "input_digest": "sha256:...",
  "verdict": "pass | hold_only | reject",
  "permitted_ratings": ["Buy", "Overweight", "Hold", "Underweight", "Sell"],
  "data_as_of": "UTC timestamp",
  "quality_flags": [],
  "rules": [
    {
      "rule_id": "market.verified_snapshot.available",
      "outcome": "pass | warn | degrade | fail",
      "code": "stable_machine_code",
      "evidence_refs": ["invocation or observation ID"]
    }
  ],
  "result_digest": "sha256:..."
}
```

`evaluated_at` may be stored for operations but is excluded from the deterministic result
digest. Re-evaluating identical input with the same policy version and configuration must
produce the same verdict, rules, flags, `data_as_of`, and digest.

Store the summary in `source_policy_evaluations` and normalized rule rows in
`source_policy_rule_results`. The manifest references the policy evaluation and digest.
Database constraints enforce one evaluation per session, valid verdict/rating combinations,
and identity consistency with the run, job, snapshot, and manifest.

## Initial BTC/ETH policy matrix

| Subject | Required evidence | Unavailable or invalid |
|---|---|---|
| Fenced attempt identity | Job, run, session, manifest, attempt, and fence match | Reject |
| Execution snapshot | Exact enabled instrument/exchange/pair/type/timeframe; closed; gap-free; clock-safe; artifact verified | Reject |
| Instrument resolution | Exact registry research symbol and allowed Yahoo resolution | Reject |
| `get_stock_data` | At least one valid invocation for the exact symbol/date window; latest daily bar closed | Reject |
| Verified market snapshot | At least one valid exact-symbol/date invocation | Reject |
| Indicators | Every consumed invocation typed and temporally valid | Missing/failure makes result `hold_only`; unsafe/unknown response rejects |
| Ticker news | Exact symbol/window and typed article metadata | `hold_only`; unsafe/unknown response rejects |
| Global news | Correct live window and typed article metadata | `hold_only`; unsafe/unknown response rejects |
| StockTwits | Exact resolved crypto symbol and typed first-seen/item times | `hold_only`; unsafe/unknown response rejects |
| Reddit | Exact crypto base/query and typed first-seen/item times | `hold_only`; unsafe/unknown response rejects |
| FRED macro | Allowed optional enrichment with explicit live-vintage limitation | Warn only when absent |
| Polymarket | Allowed optional live-at-fetch enrichment | Warn only when absent |
| Fundamentals | Disabled | Reject any invocation |
| Insider transactions | Disabled for initial crypto scope | Reject any invocation |
| Unknown method/category/vendor | Not allowed | Reject |

Repeated calls are allowed only when every invocation is independently valid. At least one
valid invocation does not hide another consumed invalid value.

Fallback succeeds only when attempts form a contiguous prefix of the configured vendor chain,
stop after the first success, and the semantic result is consistent with that success. An
unconfigured or reordered vendor rejects the run. A valid fallback may pass with a quality
flag; it is not silently treated as the primary.

## Temporal rules

- All timestamps are UTC and bounded by configured clock skew.
- Analysis starts after the execution candle closes.
- The execution candle is closed according to exchange time, not local receipt time.
- Snapshot age at analysis start and age at publication have explicit, versioned limits.
  Recommended initial limits for a 5-minute shadow deployment are two timeframe widths at
  start and three at publication; soak results should be reviewed before changing them.
- Every invocation completes before the collection cutoff and every observation is first seen
  no later than that cutoff.
- News/social publication time cannot exceed platform first-seen time plus clock skew.
- Market bar close cannot exceed first-seen time and the bar must be complete.
- Live collection may use information first seen after the execution candle; it acts only at
  `signal_available_at` and is never attached retrospectively. Historical mode remains blocked.
- `data_as_of` is the latest verified information timestamp consumed by the graph, not the
  execution candle time and not merely the analysis completion time.

Yahoo USD context and Binance USDT execution data remain distinct observations. Do not reject
on a raw price-difference threshold unless observations are aligned to a comparable timestamp;
otherwise legitimate market movement is indistinguishable from quote basis. Record the basis
diagnostic and provenance without claiming the prices are interchangeable.

## Deterministic rule precedence

Evaluate every rule and retain every failure. Select the terminal rejection code by fixed
priority:

1. contract, artifact-integrity, and unknown-ingress failures;
2. fenced identity and symbol/venue mismatches;
3. temporal or future-data failures;
4. missing required market evidence;
5. degraded news/social evidence;
6. optional-source warnings.

The policy result is independent of the LLM decision. A separate publication gate intersects
`permitted_ratings` with the already validated typed decision. It must never transform `Buy`
or `Sell` into `Hold`.

## Acceptance tests required before publication

- complete pass fixture for BTC and ETH;
- missing, no-data, stale, open, future, wrong-symbol, wrong-date, and corrupt market inputs;
- current incomplete Yahoo daily bar;
- news/social no-data and outage paths yielding `hold_only`;
- degraded inputs plus `Buy` yielding no created signal;
- degraded inputs plus original `Hold` yielding a quality-flagged signal;
- absent optional macro/prediction sources yielding warnings only;
- fundamentals, insider, unknown method, category, or vendor rejection;
- configured primary failure followed by valid fallback and malformed fallback chains;
- router-generated sentinel captured as the exact semantic result;
- swallowed exception strings classified as failure without secret persistence;
- missing/duplicate invocation ordinals and late writes after `evaluating`;
- artifact deletion, length mismatch, and digest corruption;
- policy-version/configuration mismatch;
- repeat evaluation producing the same result digest;
- crash at collection close, evaluation persistence, manifest seal, and publication gate;
- stale worker unable to evaluate, seal, reject, or publish.

## Recommended implementation order

1. Add semantic invocations, vendor attempts, typed metadata, and `evaluating` state.
2. Populate fenced job/attempt/session links at session creation.
3. Capture router final values and replace swallowed-error strings with typed failures.
4. Add source-specific metadata hooks, including news timestamps and daily-bar closure.
5. Disable insider tools for the crypto graph and audit the enabled method allowlist. **Done.**
6. Implement the pure policy models and evaluator with fixtures only. **Done.**
7. Persist immutable evaluations and bind their digest into manifest sealing. **Done.**
8. Add the fenced publication rating gate. **Done.**
9. Perform live shadow validation; revocation remains the next separate transport slice.

## External basis

- [TradingAgents pinned routing source](https://github.com/TauricResearch/TradingAgents/blob/01477f9afb7a47b849ed4c9259d3a9a4738d9fda/tradingagents/dataflows/interface.py)
  defines configured fallback chains and router-generated unavailable values.
- [TradingAgents pinned Yahoo news source](https://github.com/TauricResearch/TradingAgents/blob/01477f9afb7a47b849ed4c9259d3a9a4738d9fda/tradingagents/dataflows/yfinance_news.py)
  shows rendered no-data/error values and why article metadata must be captured before rendering.
- [CCXT OHLCV documentation](https://github.com/ccxt/ccxt/wiki/Manual) warns that the current
  candle can be incomplete and that missing candle periods can occur.
- [Freqtrade strategy customization](https://www.freqtrade.io/en/latest/strategy-customization/)
  confirms strategies receive completed candles and signals are generated at candle close.
- [OWASP logging guidance](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
  recommends removing, masking, hashing, or encrypting secrets rather than recording them.
- [PostgreSQL constraints](https://www.postgresql.org/docs/17/ddl.html) provide the database
  enforcement layer for unique evaluations, foreign-key identity, and valid state combinations.
