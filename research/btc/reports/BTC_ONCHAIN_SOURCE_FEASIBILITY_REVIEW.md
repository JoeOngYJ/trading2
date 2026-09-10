# BTC point-in-time on-chain source feasibility review

Review ID: `btc-onchain-source-feasibility-review-v1`  
Reviewed: 2026-08-31  
Status: **no historical strategy input approved; one bounded free-pilot candidate**

## Boundary

This was a public-document, source-only review. It did not acquire an API key, call a paid or
authenticated endpoint, deserialize an on-chain metric value, choose a trading rule, calculate a
return or PnL, inspect a 2026 strategy partition, access partial OB0 data or touch a protected
service. There is still no active strategy experiment, no accepted strategy arm and every
actionable route remains `no_trade`.

The review asked whether an individual researcher can obtain BTC exchange-balance, BTC exchange-
flow and stablecoin-to-exchange data with all of the following properties before a strategy
hypothesis is frozen:

- immutable point-in-time labels and values rather than today's reconstruction of history;
- an explicit observation interval and a separately identifiable availability time;
- enough pre-2026 history for chronological development and stability analysis;
- permitted API/CSV export and durable private-research reproduction;
- a disclosed retail-access path and bounded cost.

## Findings

### Glassnode

Glassnode documents immutable append-only point-in-time variants for exchange balance, exchange
inflow/outflow, net flow and deposit-count metrics. Relevant endpoints support daily and, for
several fields, hourly or ten-minute intervals. Its timestamp documentation says interval
timestamps denote the interval start, so a causal ledger would have to delay a daily observation
until the interval is complete and the row is actually published.

This is the best documented source semantics, but it does not provide the required long historical
point-in-time boundary. Glassnode states that it began recording `computed_at` in September 2024,
that most point-in-time metrics have limited history, and that broad point-in-time coverage began
in July 2025. Rows before the tracked point-in-time era cannot prove what exchange labels or values
were available on the historical decision date merely because an endpoint returns an earlier
timestamp today.

The public plan comparison places point-in-time metrics outside the lower personal tier and does
not publish a fixed Professional price. The May 2026 terms grant a temporary personal license and
state that service access ceases on subscription expiry, but do not expressly grant permanent
post-termination use of exported provider data. A written price, exact BTC metric coverage and
retention clarification would therefore be required before purchase.

Disposition: suitable for prospective capture from a verified publication timestamp, but not
approved as a causal 2017-2025 historical strategy input.

Official sources:

- <https://docs.glassnode.com/data/point-in-time-metrics>
- <https://docs.glassnode.com/basic-api/endpoints/pit>
- <https://docs.glassnode.com/data/general-information/timestamps-and-resolutions>
- <https://studio.glassnode.com/pricing>
- <https://studio.glassnode.com/terms-and-conditions>

### CryptoQuant

CryptoQuant offers the economically relevant BTC reserve, inflow, outflow, net-flow, transaction-
count and address-count endpoints. Its current retail pricing lists Professional at USD 99 per
month with on-chain API access, while the public comparison limits that API tier to one year of
historical data even though the platform advertises full chart history.

CryptoQuant explicitly states that these exchange-flow endpoints are **not point-in-time
accurate**. Wallet clustering is updated periodically and historical values may change when new
exchange wallets are discovered and validated. Its terms also prohibit scraping and permit only
the supplied internal-use access path, so web scraping cannot repair the missing point-in-time
lineage.

Disposition: rejected for causal historical strategy evaluation. Do not buy CryptoQuant for this
specific experiment and do not freeze a signal from its reconstructed history.

Official sources:

- <https://userguide.cryptoquant.com/api/btc-exchange-flows>
- <https://cryptoquant.com/en/pricing>
- <https://cryptoquant.com/terms-of-service>

### Nansen

Nansen announced point-in-time backtesting endpoints in June 2026 and says they reconstruct
holders, flows, prices and labels as they appeared on a requested past date. Its current public
API page lists a free plan with trial credits, a USD 49 monthly Pro plan and pay-per-query access.

The public materials do not yet bind that general claim to an exact aggregate BTC exchange-flow
endpoint. The documented token-flow endpoint's supported-chain list omits Bitcoin, while some
address-profiler endpoints accept Bitcoin. The documentation also does not establish the exact
BTC history start, row-level availability timestamp, cost in credits, complete exchange universe
or post-subscription retention rights for the desired series.

Disposition: not approved, but it is the only bounded low-cost candidate worth a technical source
pilot before abandoning historical on-chain strategy research. The pilot must use a new data-only
contract, the free allowance only, fixed pre-2026 windows and no strategy metrics.

Official sources:

- <https://release.nansen.ai/changelog/backtesting-api-endpoints-now-available>
- <https://docs.nansen.ai/api/token-god-mode/flows>
- <https://docs.nansen.ai/api/profiler/address-historical-balances>
- <https://nansen.ai/api>

### Coin Metrics and free reconstruction

Coin Metrics Network Data Pro documents BTC exchange-deposit metrics and added hourly exchange
flows in 2026. Its public documentation does not establish immutable historical entity-label
versions, an observation-to-publication ledger, retail pricing or durable-use terms for those
metrics. It therefore remains a contact-required alternative, not an approved source.

The Bitcoin blockchain can reproduce transfers to known addresses, but it does not identify which
addresses belonged to which exchange at each historical decision time. A current free address
list would reproduce blockchain arithmetic while still leaking future entity knowledge. A
self-built historical exchange-flow series is therefore not a free substitute unless it includes
an independently archived, contemporaneous label history.

Official source:

- <https://docs.coinmetrics.io/asset-metrics/exchange/flowinexusd>

## Decision

No existing on-chain dataset is approved for strategy evaluation, and no purchase is justified
now. CryptoQuant fails the core point-in-time gate. Glassnode passes the semantic design but lacks
the required long verified point-in-time history. Coin Metrics remains insufficiently specified.

The next permitted action for this family is a separately frozen Nansen free-tier technical pilot
or written vendor clarification. It must prove an exact BTC exchange-flow/balance endpoint,
historical label-as-of semantics, history start, publication timestamp, stable pagination,
export/retention rights and bounded credit cost before any numeric series is accepted. Failure of
that pilot closes retrospective on-chain exchange-flow research; the repository should then move
to another materially distinct strategy family rather than backtest mutable history or wait for a
multi-year prospective sample.

This review does not change the secondary HAR data-gap task, accept a risk detector, or authorize
orders, credentials, a subscription or live capital.
