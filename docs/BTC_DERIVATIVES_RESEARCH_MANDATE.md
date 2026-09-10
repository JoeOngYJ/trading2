# BTC delta-neutral derivatives research mandate

Mandate ID: `retail-btc-delta-neutral-research-v1`  
Effective: 2026-08-30  
Status: frozen for offline data qualification and research only  
Machine-readable source: `config/mandates/retail-btc-delta-neutral-research-v1.json`

## Authority boundary

This mandate adds a research-only BTC spot/perpetual lane. It does not supersede the existing
spot mandate for legacy experiments and does not authorize an account connection, credential,
order, transfer, paper order routed to an exchange, or live funds. Maximum live allocation is
zero. Venue availability and jurisdiction/account eligibility must be reviewed again before any
future execution proposal.

## Permitted first research structure

- Instrument pair: BTC/USDT spot plus BTCUSDT USD-M perpetual.
- Economic position: long spot and a simultaneously matched short perpetual.
- Direction: approximately delta-neutral only; no naked short or directional perpetual position.
- Margin model: isolated, single-asset USDT planning model with 1x perpetual leverage.
- Normalized equity: 1,000 USDT; at most 500 USDT spot notional and matched 500 USDT perpetual
  short notional, with the remaining capital reserved as derivative collateral.
- Maximum absolute notional mismatch: 1% after rounding; a larger mismatch fails closed.
- No cross-margin, portfolio-margin, multi-asset collateral, borrowing, rehypothecation or options.

The spot and futures legs must be treated as one atomic research intention. A missing, rejected,
expired or partially filled leg requires immediate simulated neutralization under the severe-cost
assumption. Position sizing must remain separate from any later carry forecast.

## Risk and liquidation policy

No historical simulation may assume liquidation is impossible. It must reconstruct maintenance
margin from effective-dated rules or fail the applicable interval closed. Current brackets may
not be projected backward. A future strategy contract must predeclare margin buffers, adverse
mark-price stress, funding-payment stress, exchange/ADL failure, depeg, transfer lock and
leg-dislocation handling.

The research engine must attribute spot PnL, perpetual PnL, funding, basis convergence, explicit
fees, spread, slippage, hedge error, collateral cost, liquidation/ADL loss and missed-leg cost
separately. None of those calculations is authorized by the B2 data qualification itself.

## Promotion blockers

Before strategy research, official/public data must pass the separate B2 contract. Before any
paper or live review, exact account fees, effective margin brackets, venue eligibility, custody,
tax, operational controls and prospective evidence must be resolved. Passing a backtest cannot
authorize execution.
