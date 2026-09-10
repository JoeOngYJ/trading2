# BTC spot/perpetual continuation D1-v3 endpoint-label successor

Experiment: `btc-spot-perp-continuation-information-d1-v3`  
Candidate: `btc-spot-perp-continuation-information-v1`  
Status: frozen design before any D1-v3 target return or model result  
Actionable arm: `no_trade`

## Reason for one successor

D1-v2 is immutable and rejected at its 2021 label-coverage gate. It required the exact start and
end opens of a raw 72-hour return to share one five-minute source segment. That was a conservative
path-continuity rule inherited from the taker-flow ledger. It is necessary for path-dependent
outcomes such as first passage, stop hits or intrahorizon drawdown, but the frozen D1 target uses
only two endpoints.

The label-blind source review established that all 21 excluded 2021 candidates have exact 00:05
UTC start and end rows with positive traded volume. Seven preserved interior gaps, ranging from 5
to 285 missing minutes, caused those exclusions. No D1-v2 model was fitted, so this correction was
not selected from coefficient, forecast or PnL results.

D1-v3 is the only permitted successor. It changes exactly one conceptual rule: an endpoint-return
label requires two authenticated exact endpoint rows, not an uninterrupted interior path. D1-v2
remains rejected and is never rewritten.

## Frozen inputs and phases

The exact D1-v2 feature ledger is reused byte-for-byte. No feature is recomputed or changed. The
authoritative label source is the already-downloaded official Binance BTCUSDT spot monthly 5-minute
kline archive from December 2019 through December 2025. Every archive must match the official
SHA-256 recorded by the frozen raw source manifest. No network request, alternate venue,
interpolation or cross-venue stitching is allowed.

Execution is gated:

1. `endpoints`: authenticate all 73 official monthly archives and verify every requested pre-2026
   endpoint directly from the raw row. Require exact 5-minute alignment, unique timestamps,
   positive finite open and positive base/quote volume. Compare the exact open with the preserved
   S1 ledger endpoint. Open no target return.
2. `labels`: only if the endpoint audit passes, calculate
   `log(open_at_t_plus_72h / open_at_t)`. Interior gaps are recorded diagnostically but do not make
   this endpoint-only target ineligible. An exact endpoint missing or invalid still fails closed.
3. `model`: only if every label gate passes, run the unchanged frozen B0/M0/M1 monthly expanding
   walk-forward test from D1-v1/v2.

Features, target horizon, decision time, evaluation years, minimum training count, target-availability
purge, OLS specifications, bootstrap seed/blocks/replications, coefficient signs, annual robustness,
concentration checks and every model acceptance gate remain exact. There is no new parameter,
interaction, transformation or model search.

## Endpoint and label gates

The endpoint phase requires:

- 73 official monthly archives, December 2019 through December 2025;
- all archive hashes equal their official manifest hashes;
- exactly 2,209 unique requested pre-2026 endpoint timestamps;
- every endpoint present exactly once in the official raw archive and preserved S1 ledger;
- exact official/S1 open-price equality;
- positive finite official open, base volume and quote volume;
- no raw row at or after 2026 read;
- no target return, forecast, model, strategy or PnL created.

The label phase preserves the v2 count and coverage gates: at least 300 training labels before the
first 2021 fit; at least 1,700 evaluation labels; at least 340 in each 2021–2025 year; at least 98%
overall and 95% within each year; zero invalid serialized labels. Missing endpoints are excluded,
never imputed. Interior-gap crossings are reported by year, boundary and missing duration.

## Stop rule

If the endpoint or label phase fails, stop and close the candidate. If the unchanged M1 model
fails any frozen information gate, close the basis/relative-turnover hypothesis without another
successor. If it passes, the result is incremental forecast information only; any strategy,
execution, risk or PnL experiment requires a new contract and experiment ID.

No phase may access 2026, partial OB0, credentials, protected services, database, NATS, Freqtrade,
positions or orders. No strategy arm is accepted and every actionable route remains `no_trade`.
