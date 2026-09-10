# Cash-ETF-First Research Program

Program ID: `retail-cash-etf-multi-strategy-v1`  
Current stage: `C1` — **blocked before numeric ledger construction**  
Actionable disposition: `no_trade`

## Decision

The prior cross-asset A2 session breakout and A3 overnight-gap reversion remain rejected. This
successor does not tune them and does not use a risk overlay to rescue them. It removes direct
futures contracts and futures-data acquisition from the research path.

The initial research instruments are unlevered cash ETFs or listed ETPs, long or flat. The
existing checksummed SPY, EFA, IEF, TLT, GLD, DBC and BIL histories are non-executable mechanism
proxies. GBP/USD is conversion-only. None is approved for execution by this program.

The precommitted exact UK candidates are SWDA, IGLT, SGLN and AGCP plus zero-yield GBP cash.
AGCP is a listed, unlevered collateralised ETC rather than a futures contract, although its
wrapper references a commodity-futures total-return index. Exact-line research is prohibited
until a proxy mechanism passes and a later source-only qualification is separately approved.

## Frozen hypotheses

Both families were frozen before any ETF return or strategy result was calculated:

1. `cash-etf-slow-trend-proxy-v1`: monthly 252-session GBP total-return trend, fixed one-sixth
   slots, next-open execution and no redistribution of unused weight.
2. `cash-etf-turn-of-month-proxy-v1`: equal SPY/EFA exposure from the final US session open to
   the fourth session of the next month open, otherwise GBP cash.

Both use 10/25/50 bps round-trip-equivalent cost scenarios, fixed controls, chronological
partitions, uncertainty and concentration gates. A passing proxy can establish only that a
mechanism deserves exact-line validation. It can never approve an instrument or strategy.

## Evidence boundary

- Development: 2009-01-02 through 2018-12-31.
- Validation: 2019-01-01 through 2023-12-31, initially locked.
- Historical confirmation: 2024-01-01 through 2025-12-31, initially locked.
- 2026: excluded from economics.

Timestamp-only prepartitioning must occur before numeric decoding. C1 must reconcile source
identity, sessions, raw prices, actions, availability and GBP conversion before any return is
computed. Existing incomplete issuer-action reconciliation is not silently waived.

The timestamp-only prerequisite has now passed for 22 sources and 66 outputs. C1 is blocked by
that preserved incomplete action reconciliation, so no ledger or strategy economics were built.

## Stage gates

`C1` builds the causal ledger. `C2` evaluates the two proxy mechanisms independently. `C3`
qualifies exact London histories only after a proxy passes. `C4` validates unchanged mechanisms
on exact lines. `C5` evaluates downward-only EWMA, covariance and liquidity risk controls only
for accepted base strategies. `C6` requires two economically distinct accepted arms before
counterfactual routing. `C7` requires a separate paper mandate.

Direct futures, automatic data purchases, broker-private state, production signals, orders,
positions, database access, message-bus access, partial OB0 inspection and soak access are all
prohibited. The 50% annualized aspiration is not an acceptance or leverage gate.
