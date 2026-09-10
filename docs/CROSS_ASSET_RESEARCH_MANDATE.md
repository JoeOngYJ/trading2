# Retail Cross-Asset Research Mandate

Mandate ID: `retail-cross-asset-research-v7`  
Stage: `A2`  
Status: **offline strategy research only; execution prohibited**  
Live allocation: **GBP 0**

## Objective and authority

This mandate supersedes `retail-cross-asset-research-v6` to authorize separately frozen offline
long/short strategy evaluation and one conversion-only GBP_USD input. It changes no capital, risk,
jurisdiction or execution authority and authorizes no trading. It records the user's
GBP 20,000 research capital, 20% absolute drawdown ceiling, willingness to consider a broader
asset universe, and 50% annualized stretch objective. The stretch return is not an acceptance
gate and may not determine leverage, exposure, model choice, or data selection.

No generic credential, orders, positions, paper account, live venue, live funds, or execution
product are authorized. Environment-held `OANDA_API_TOKEN`, `OANDA_ACCOUNT_ID` and
`OANDA_API_URL` were usable only by the frozen, GET-only A1 hourly and A2 conversion-source
downloaders for historical candles. The downloaders bound the account by digest and could not access
balances, summaries, positions, trades, transactions, previews or orders. Credentials may not be
stored in artifacts, printed, logged, or used by runtime, execution, database or message-bus code.
No paid source may be purchased automatically. Existing BTC mandates and negative results remain
unchanged.

## Capital and risk boundary

| Item | Frozen A0 value |
|---|---:|
| Research accounting equity | GBP 20,000 |
| Soft drawdown stop | 12%, at GBP 17,600 |
| Absolute drawdown ceiling | 20%, at GBP 16,000 |
| Daily loss stop | 1% |
| Planned position-risk range | 0.25%–0.50% |
| Maximum one-strategy share of portfolio risk | One third |
| A1 gross exposure | 0% |
| Maximum live allocation | GBP 0 |

The soft stop disables new research risk in a later simulator and requires attribution review.
The absolute ceiling is an emergency boundary, not a normal operating target. Protective exits
must remain possible after any entry or risk stop.

These limits do not imply that a strategy can achieve 50% annualized return. Returns must be
reported at frozen risk, with leverage and exposure attribution shown separately.

## Jurisdiction and instrument boundary

`UK_retail` is the conservative planning default. `Malaysia_retail` is an alternative scenario,
not a route around UK or Malaysian rules. The actual execution jurisdiction must reflect lawful
residency, client classification, venue onboarding and product eligibility at the time of any
future paper or live review.

A1 approves no execution instrument. It qualifies broker-native intraday research history for
SPX500_USD, NAS100_USD, DE30_EUR, UK100_GBP, XAU_USD, EUR_USD and USD_JPY. The rejected exact-XLON
histories and unresolved CME futures candidates remain preserved but deferred. WTICO_USD and
USB10Y_USD remain excluded from economic evaluation. OANDA CFD history may not be relabelled as
listed-futures history. CFD execution, spread betting, live shorting, margin and leverage remain
blocked.

Public derivatives data may later be qualified for research without implying that the product
is executable. Research access and lawful account access are separate facts.

## Strategy boundary

A1 performed no strategy evaluation. A2 evaluated and rejected one trend family. The remaining
program order is:

1. qualify exact instruments and point-in-time data;
2. test one diversified cross-asset trend family;
3. test one economically distinct non-trend family under a pre-result access branch;
4. add simple continuous risk scaling only to accepted forecasts;
5. research routing only after two distinct arms pass; and
6. prospectively paper-observe before any execution mandate.

Several trend speeds remain one trend family. Risk forecasts are not alpha. A regime layer may
reduce exposure or abstain; it may not rescue a rejected strategy or create directional claims
without separate evidence.

## Change control

An operating jurisdiction, client classification, venue, instrument universe, direction,
margin/leverage permission, capital/risk limit, execution policy or live authority change
requires a new mandate ID. No configuration can silently broaden this document.

Machine-readable source:
`config/mandates/retail-cross-asset-research-v7.json`. Superseded mandates remain immutable
history.
