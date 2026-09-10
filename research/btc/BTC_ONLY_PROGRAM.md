# BTC-only research program

Program ID: `btc-only-research-v1`  
Status: active offline research infrastructure  
Actionable arm: `no_trade`

## Focus and boundaries

BTC is the only active research market. ETH, cash-ETF and cross-asset work remain preserved but
archived for this program. Nothing is moved or deleted because existing contracts and evidence
depend on their paths and checksums.

One new strategy hypothesis may be active at a time. A data qualification or infrastructure audit
may precede that hypothesis, but it cannot calculate returns, choose strategy parameters or create
an executable output. Existing negative results remain immutable and may not be reopened through
threshold or window changes.

The passed close-only EWMA volatility estimate is the mandatory simple risk benchmark for later
BTC strategies. It is not alpha and cannot rescue a rejected entry mechanism. The fixed breakout,
buy-and-hold, flat and timestamp/exposure-matched positions remain controls only.

BTC L2 remains a separate background data-engineering lane. Mutable or partial capture data may
not be inspected, catalogued as accepted evidence, used for feature construction, or used to
support a strategy. OB1 remains blocked until its separately frozen 60-development-day plus
30-unread-day data boundary exists.

## Current strategic state

There are zero accepted BTC strategy arms. Breakout timing, BOCPD gating, the Student-t HMM,
aggregate taker-flow threshold families, volatility-expansion continuation, BTC/ETH residual
catch-up and absolute derivatives-crowding risk have all failed their frozen gates. The EWMA
benchmark passed as risk infrastructure only.

The completed candidate `btc-spot-perp-continuation-information-v1` was a materially different,
regular-clock cross-market information hypothesis rather than another sparse breakout catalogue.
Its D0 v3 source audit passed on 2,307 continuous common daily spot/perpetual observations through
2025 after two preserved failed source designs. D1-v1 was rejected in preflight. D1-v2 then passed
features but rejected at 344/365 eligible 2021 labels because it inherited a path-continuity rule
for an endpoint-only return. The one permitted D1-v3 successor authenticated all 2,209 exact
endpoints from 73 official Binance archives and restored 100% evaluation coverage without
interpolation. On 1,823 walk-forward forecasts, however, the added spot/perpetual variables
worsened MSE by 0.532107% relative to the price-only control, improved only two of five years,
produced uncertainty intervals crossing zero and had coefficient signs opposite the frozen
continuation theory. The independently replayed information test is rejected and the hypothesis
is closed. No strategy or profitability test was run. Do not tune, invert or create another
successor; select a materially different BTC hypothesis under a new ID.

The B3 BTC spot long/flat backtest core has passed engineering qualification. It standardizes
causal candle execution, Decimal cash/inventory accounting, mandate risk stops, gap rejection,
mark-to-market metrics and deterministic results. Its checks against the consumed SMA and breakout
reports are regression tests only; B3 accepts no strategy and adds no regime model.

The first checksummed carry-data qualification remains rejected at its strict data gate. Its
separately frozen official REST successor recovered all 192 missing mark-price hours, all 288
missing index-price hours and 168 of 169 missing premium-index hours. The sole exact request for
2020-12-01 23:00 UTC premium index returned HTTP 200 with an empty list, so the successor also
failed its all-series continuity gate. That raw negative response is retained; no value was
interpolated or substituted. Effective-dated fee/margin economics remain incomplete. No carry
strategy or PnL has been evaluated. Any successor that treats the one unavailable hour as a hard
segment boundary requires a new frozen contract, and any later strategy still requires a
separately frozen falsifiable hypothesis and predeclared historical economics.

The first such strategy hypothesis, `btc-positive-funding-carry-v1`, avoided premium index and
used only exact spot/perpetual opens, mark prices and completed funding payments. It was profitable
at all frozen costs on 2024–2025 chronology, and attribution confirms funding rather than BTC
direction produced the return. It is nevertheless rejected: its 49%-per-leg isolated collateral
failed the additional 20% mark-shock buffer during 260 exposed hours, while its funding timing did
not improve return per exposed day over the always-on control. The experiment is closed without
tuning.

The separately frozen `btc-safe-delta-neutral-funding-carry-v2` then changed risk implementation
only: 25% per matched leg, 75% planning collateral and a causal 2.0 minimum shocked-margin ratio.
It passed every risk gate with zero observed or shocked breaches and returned 2.95% at primary and
1.33% at severe costs over the consumed 2024–2025 evaluation. This is sizing/risk evidence, not
new alpha. The unchanged funding gate again lost to same-exposure always-on carry in return per
exposed day; always-on returned 7.75% but has only one continuous evaluation trade and no clean
promotion evidence. Close the 60/30 bps funding-timing rule. Preserve safe always-on carry only as
an unaccepted structural benchmark or prospective-observer candidate. For new alpha research,
select a materially different BTC family rather than another funding threshold or regime rescue.
Zero arms remain accepted.
