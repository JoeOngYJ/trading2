# Real Data Contract for TradingAgents → Freqtrade

**Status:** Foundation, source policy, publication gating, worker orchestration, signed revocation, and hard-crash lease recovery implemented; exhaustive failure validation remains before actionable use  
**Pinned upstream:** TauricResearch/TradingAgents `v0.3.1`  
**Initial assets:** Binance spot `BTC/USDT` and `ETH/USDT`

## Decision

The first real contract will support **live collection only**. Historical TradingAgents
runs are not replay-safe unless every input was previously captured with its first-seen
time. Freqtrade execution must use completed exchange candles; TradingAgents' daily Yahoo
context must remain a separate research input and must never be presented as a 5-minute candle.

The contract boundary is:

```text
completed exchange candle
        +
immutable, timestamped research evidence manifest
        ↓
TradingAgents run
        ↓
typed decision + exact input manifest reference
        ↓
signed signal available to Freqtrade
```

## Upstream findings

1. TradingAgents accepts only `trade_date: YYYY-MM-DD`; Yahoo OHLCV and technical
   indicators are daily and filtered by date, not by an intraday candle timestamp.
2. Graph state contains rendered reports and decisions, not raw source payloads, source
   IDs, retrieval times, or a complete evidence manifest.
3. Yahoo news filters publication dates, but returned reports do not preserve complete metadata.
4. StockTwits always returns the most recent live messages; it has no `trade_date` cutoff.
5. Reddit fetches current RSS results and is not anchored to a historical timestamp.
6. Polymarket deliberately returns current live probabilities using `datetime.now()`.
7. FRED limits observation dates but does not request point-in-time vintages, so revised
   historical values may differ from what was known on the original date.
8. TradingAgents internally uses typed Pydantic decisions but renders them back to
   Markdown in graph state and `propagate()` output.
9. Freqtrade supplies only completed exchange candles. This is the correct execution
   clock and must be the source of the signal's candle identity.

Primary references:

- [TradingAgents v0.3.1 graph state](https://github.com/TauricResearch/TradingAgents/blob/v0.3.1/tradingagents/agents/utils/agent_states.py)
- [TradingAgents data routing](https://github.com/TauricResearch/TradingAgents/blob/v0.3.1/tradingagents/dataflows/interface.py)
- [TradingAgents structured schemas](https://github.com/TauricResearch/TradingAgents/blob/v0.3.1/tradingagents/agents/schemas.py)
- [TradingAgents sentiment analyst](https://github.com/TauricResearch/TradingAgents/blob/v0.3.1/tradingagents/agents/analysts/sentiment_analyst.py)
- [TradingAgents FRED vendor](https://github.com/TauricResearch/TradingAgents/blob/v0.3.1/tradingagents/dataflows/fred.py)
- [TradingAgents Polymarket vendor](https://github.com/TauricResearch/TradingAgents/blob/v0.3.1/tradingagents/dataflows/polymarket.py)
- [Freqtrade completed-candle behavior](https://www.freqtrade.io/en/latest/strategy-customization/)
- [CCXT OHLCV warning](https://github.com/ccxt/ccxt/wiki/Manual#ohlcv-candlestick-charts)

## Contract records

### Instrument identity

```json
{
  "instrument_id": "crypto:binance:spot:BTC-USDT",
  "research_symbol": "BTC-USD",
  "execution_exchange": "binance",
  "execution_pair": "BTC/USDT",
  "market_type": "spot",
  "base": "BTC",
  "quote": "USDT",
  "research_quote": "USD",
  "timezone": "UTC",
  "enabled": true
}
```

No symbol may be inferred with string replacement. Research and execution prices are
different quote/venue observations and must never be silently substituted.

### Execution market snapshot

Captured from the execution exchange or Freqtrade before scheduling research:

- snapshot and instrument IDs, exchange and CCXT versions;
- timeframe, candle type, UTC open/close timestamps, and decimal-string OHLCV;
- retrieval time, exchange server time, local clock offset, and gap status;
- `is_closed=true`, raw response hash, and immutable artifact location.

The current incomplete candle is always discarded. The snapshot ID—not an inferred
date—is the execution-time anchor for the research job.

### Source observation

Every news, social, macro, prediction-market, or Yahoo market input records:

- observation ID, source category, configured vendor, symbol/query, external ID or URL;
- source `event_at`/`published_at`, plus platform `first_seen_at` and `retrieved_at`;
- content hash, media type, byte length, and immutable artifact location;
- parse status, error classification, quality flags, and sanitized request parameters;
- `replay_safe` and the reason when false.

`first_seen_at` is authoritative for replay. A publisher's backdated timestamp never
proves that the platform knew the item earlier.

### Evidence manifest

One immutable manifest per attempt contains:

- manifest ID and SHA-256 digest;
- run/instrument/execution-snapshot IDs and collection start/end times;
- exact vendor chain and any fallback;
- ordered observation IDs grouped by source;
- required-source results, missing/degraded inputs, and quality flags;
- earliest/latest source event and first-seen times;
- explicit `mode: live` or `captured_replay` and overall replay safety.

The manifest remains collecting while the graph makes dynamic source calls. It transitions
to an immutable evaluating state after the graph finishes, then seals only after source-policy
validation and before publication. Evidence collected after collection closes requires a new run.

### Research result and signed signal

The result references the manifest and preserves typed Research Manager, Trader,
Portfolio Manager, and Sentiment objects; rendered reports; TradingAgents tag/commit and
container digest; graph configuration; LLM model controls; and all timing/quality data.

The signed signal also carries `instrument_id`, `manifest_id`, `execution_snapshot_id`,
and `signal_available_at`. Freqtrade may act only after `signal_available_at`; it must
not attach the result retrospectively to the candle close.

## Live v1 source policy

| Source | Live use | Historical replay | Required policy |
|---|---|---|---|
| Binance completed OHLCV | Allowed | From captured/raw exchange data | Required; exact candle and no gaps |
| Yahoo daily OHLCV | Slow context only | Captured response only | Reject stale/no-data; record USD/USDT basis |
| Yahoo news | Allowed | Captured observations only | Require timestamp or flag undated |
| StockTwits | Allowed | Captured observations only | Record every message and first-seen time |
| Reddit RSS | Allowed with limits | Captured observations only | Flag missing scores/comments |
| Polymarket | Optional live enrichment | Captured snapshots only | Mark live-at-fetch |
| FRED | Optional live enrichment | Unsafe without vintages | Record series, observation, and retrieval vintage |
| Fundamentals | Not required for crypto | Captured point-in-time data only | Absence must not fail crypto runs |

The execution candle and Yahoo daily context are initially required. News/sentiment may
degrade only to a flagged HOLD/no-entry outcome. Optional macro and prediction data may be absent.

## Validation rules

Reject the run or signal when:

- the exchange candle is incomplete, duplicated, out of order, or has unexplained gaps;
- exchange/local clock difference exceeds tolerance;
- instrument, venue, market type, pair, or timeframe does not match;
- an observation was first seen after the manifest closed;
- an input lacks an immutable hash or stored content fails verification;
- configured and recorded vendors differ without explicit fallback;
- Yahoo and execution identity is mismatched, or a comparison claims price equivalence without
  timestamp-aligned observations;
- required inputs are stale, absent, or `NO_DATA_AVAILABLE`;
- typed output fails validation or only free-form decision text is available;
- manifest, result, and signal hashes do not link exactly.

Fail closed means no actionable signal. A degraded valid run may publish only an explicit
HOLD/no-entry result with quality flags and may never silently reuse an old signal.

## Required implementation sequence

The refined evaluator design and capture prerequisites are documented in
[`SOURCE_POLICY_RESEARCH.md`](SOURCE_POLICY_RESEARCH.md).

1. Add instrument, execution snapshot, source observation, evidence manifest, and
   immutable artifact tables.
2. Add a completed-candle collector for the same exchange, pair, and timeframe as Freqtrade.
3. Maintain a minimal pinned TradingAgents patch that records raw vendor requests/results
   and exposes typed decisions before Markdown rendering.
4. Make the worker close and validate the evidence manifest before invoking the LLM.
5. Extend signed signals with manifest and execution-snapshot references.
6. Add BTC/ETH fixtures and opt-in live smoke tests.
7. Run shadow comparisons of Yahoo `BTC-USD`/`ETH-USD` against Binance
   `BTC/USDT`/`ETH/USDT` completed candles.

## Acceptance criteria

The contract is established when, for BTC and ETH:

- a run can be reconstructed byte-for-byte from stored artifacts;
- every result has immutable input lineage;
- every signal identifies one completed exchange candle and its actual availability time;
- future, live-only, stale, missing, corrupt, and wrong-symbol fixtures fail closed;
- replay uses only observations first seen before simulated decision time;
- transport replay cannot duplicate a signal or execution intent;
- no historical TradingAgents call reaches a live-only source.
