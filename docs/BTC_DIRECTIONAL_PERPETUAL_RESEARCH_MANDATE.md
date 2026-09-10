# BTC directional perpetual research mandate

Mandate ID: `retail-btc-directional-perpetual-research-v1`  
Effective: 2026-09-05  
Status: frozen for offline, zero-capital research only  
Machine-readable source: `config/mandates/retail-btc-directional-perpetual-research-v1.json`

## Authority boundary

This mandate permits historical simulation of one BTCUSDT USD-M perpetual position that may be
long, short or flat. It does not supersede the spot or delta-neutral mandates and grants no
authority to connect an account, read credentials, submit an exchange paper order, transfer
funds, integrate with production or allocate live capital. Maximum live allocation is zero.

## Frozen research limits

- One instrument: BTCUSDT USD-M perpetual; public archived Binance data only.
- Isolated, single-asset USDT planning model; no cross or portfolio margin.
- Normalized equity 1,000 USDT and maximum absolute notional 25% of equity.
- Decisions use completed hourly observations; the earliest fill is the next eligible hourly
  open after the declared decision time.
- Long and short are symmetric research directions. No simultaneous legs, pyramiding, averaging
  down, borrowing, options or liquidation-as-a-stop assumption.
- Every experiment must include exact archived funding cashflows, 30/40/80-bps cost scenarios,
  an adverse-mark stress, conservative maintenance planning and a fail-closed risk exit.
- Missing hours, funding events, ambiguous rules or segment changes force flat or make the
  affected interval ineligible.

Historical margin brackets are incomplete. Results using a conservative planning maintenance
fraction are development diagnostics only and cannot be promotion evidence. A future paper or
live review requires effective-dated rules, exact account costs, venue/jurisdiction eligibility,
prospective observations and a separate explicit mandate.

## Relationship to strategy families

This mandate changes the research instrument and allowable direction, not the evidentiary
standard. A long/short trend forecast remains in the `btc_directional_trend` family and is not
independent diversification from breakout or moving-average variants. Exposure or leverage may
not be presented as alpha. Every actionable output remains `no_trade`.
