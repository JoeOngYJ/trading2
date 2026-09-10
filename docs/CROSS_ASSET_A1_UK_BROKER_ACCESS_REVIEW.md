# Cross-Asset A1 UK Broker and Instrument Access Review

Reviewed: 2026-08-29 18:45 UTC  
Experiment: `cross-asset-a1-uk-broker-access-review-v1`  
Disposition: **A1 remains blocked; defer data purchase**

## Decision

XLON is not an investment thesis and the four tickers are not sacred. They are one candidate
cash-product mapping for four frozen economic roles: global equity, defensive bonds, gold and
broad commodities. The research must use instruments that the intended retail account can
actually buy, and its price history must refer to those same trading lines.

The public-document review establishes that Trading 212 has Invest pages for all four candidate
LSE products. It does not establish that the user's particular account can trade them or approve
them for execution. IBKR documents LSE ETF execution generally, but exact-symbol availability and
permissions remain account-specific. Ordinary access to US company shares at either broker does
not establish UK-retail cash access to US-domiciled ETFs.

Neither broker currently replaces the independent A1 data source. Trading 212's documented API
covers account, order and transaction history rather than a qualified historical OHLCV archive.
IBKR's historical API requires authenticated access, permissions and relevant level-one data
subscriptions, and its documented filtering and archival semantics do not satisfy the frozen
source contract without a separate pilot.

Therefore:

- do not buy Twelve Data yet;
- do not start A2 or evaluate a strategy;
- first select the intended broker and exact cash execution universe;
- only then freeze a source pilot for those same listings;
- if the LSE universe remains, test the lowest-throughput LSE-capable tier before considering a
  higher-throughput plan.

## Frozen scope and safety boundary

The audit was frozen before reviewing exact mappings. It used current public FCA, broker and data-
vendor documentation only. It used no account login, broker credential, quote download, historical
price row, order, PnL, strategy output or protected service. Prices incidentally displayed by
public product pages were discarded and are not evidence.

## Candidate cash products

| Role | Candidate | Product | Exact identity | Trading 212 public result | IBKR public result |
| --- | --- | --- | --- | --- | --- |
| Global equity | SWDA, XLON | UCITS ETF | ISIN `IE00B4L5Y983` | Exact Invest page found | LSEETF venue supported; exact contract unverified |
| Defensive bonds | VAGS, XLON | UCITS ETF | ISIN `IE00BG47K971` | Exact Invest page found | LSEETF venue supported; exact contract unverified |
| Gold | SGLN, XLON | ETC | ISIN `IE00B4ND3602` | Exact Invest page found | Exact contract unverified |
| Broad commodities | COMM, XLON | UCITS ETF | ISIN `IE00BDFL4P12` | Exact Invest page found | LSEETF venue supported; exact contract unverified |

“Exact Invest page found” is catalog evidence, not execution approval. Account eligibility,
available order types, minimum size, spread, fills, tax wrapper eligibility and current trading
permission still require a later read-only account check under a separately authorized mandate.

The exact Trading 212 product pages are:

- <https://www.trading212.com/trading-instruments/invest/SWDA.GB>
- <https://www.trading212.com/trading-instruments/invest/VAGS.GB>
- <https://www.trading212.com/trading-instruments/invest/SGLN.GB>
- <https://www.trading212.com/trading-instruments/invest/COMM.GB>

## Why US market access does not remove XLON automatically

US shares and US-domiciled funds are different access questions. IBKR states that it must block a
UK retail client's purchase of a PRIIP when no compliant KID is available and notes that US ETF
issuers generally do not create one. FCA material also says an overseas fund marketed to UK retail
investors must be a recognised scheme and that, at the review date, no US funds were recognised in
the UK.

That does not mean every US security is unavailable. It means the proposed free-US-data shortcut
fails its frozen gate: direct cash purchase of every exact US fund required for all four roles has
not been established. CFDs, option assignment and professional reclassification are explicitly
outside this cash-product audit. A different US-instrument program could be researched later under
a new hypothesis, but US individual shares alone would not supply the bond, gold and broad-
commodity roles of this program.

Official references:

- FCA PS25/20: <https://www.fca.org.uk/publication/policy/ps25-20.pdf>
- FCA recognised-fund guidance: <https://www.fca.org.uk/firms/authorised-recognised-funds>
- IBKR overseas-trading/KID guidance:
  <https://www.interactivebrokers.com/campus/trading-lessons/trading-overseas-with-ibkr/>

## Broker comparison for this research program

| Question | Trading 212 UK | Interactive Brokers UK |
| --- | --- | --- |
| Public evidence for exact four products | Yes, all four have Invest pages | No public exact-contract proof; account contract search needed |
| Public evidence for LSE cash ETF execution | Yes | Yes, LSEETF appears in commission schedule |
| Published broker commission | Invest trading commission and custody fee are free | UK tiered/fixed commission schedules apply |
| Published UK-order minimum | No broker commission minimum; market and tax charges can still apply | Tiered minimum GBP 1; SmartRouted fixed minimum GBP 3 at review date |
| Currency conversion | 0.15% when conversion is required | Separate FX and commission schedules apply; not frozen here |
| Historical-price research source | Not accepted; public API documentation reviewed does not expose a qualified historical-bar archive | Not accepted; authenticated API, permissions and subscriptions required, with documented filtering |
| Current disposition | Executable-universe candidate, account access unapproved | Executable-universe candidate, exact access unapproved |

These displayed fees are planning inputs only, not a frozen execution-cost model. The eventual
backtest must still include bid/ask spread, slippage, market impact, FX where applicable, taxes,
rejections, partial fills and broker-specific minimum charges. London-listed ETFs are exempt from
UK Stamp Duty Reserve Tax according to Trading 212's current fee page, but that must be rechecked
at the execution-contract freeze.

Official broker references:

- Trading 212 instruments and fees:
  <https://helpcentre.trading212.com/hc/en-us/articles/11717160183197-What-trading-instruments-does-Trading-212-offer>,
  <https://helpcentre.trading212.com/hc/en-us/articles/11471996799517-What-are-the-fees-in-the-Invest-ISAs-and-SIPP> and
  <https://helpcentre.trading212.com/hc/en-us/articles/360018909758-What-is-the-FX-fee-Invest-Stocks-ISA>
- Trading 212 public API: <https://docs.trading212.com/api>
- IBKR commissions: <https://www.interactivebrokers.co.uk/en/pricing/commissions-stocks.php>
- IBKR historical-data requirements:
  <https://interactivebrokers.github.io/tws-api/historical_data.html> and
  <https://interactivebrokers.github.io/tws-api/historical_bars.html>

## Data-purchase implication

Twelve Data Basic's current exchange list covers the United States but not XLON. Grow covers XLON.
The USD 29 and USD 79 monthly options are throughput levels within Grow, not different exchange-
coverage products. Consequently, if the execution universe remains these LSE listings, the USD 29
Grow level is the logical pilot ceiling; the USD 79 level has no research justification until a
frozen request budget proves that 55 credits per minute is insufficient.

This is not purchase approval. A separately frozen pilot must first settle exact symbol/ISIN/MIC
binding, GBP-versus-GBX units, raw versus adjusted fields, corporate actions, complete daily
history, bar availability, corrections, retention and permitted private archival use.

Official vendor references:

- Basic exchanges: <https://twelvedata.com/exchanges?level=basic>
- Grow exchanges: <https://twelvedata.com/exchanges?level=grow>
- Pricing: <https://twelvedata.com/pricing>

## Next permitted action

The next decision is an execution-universe decision, not a strategy decision: choose Trading 212
or IBKR as the intended cash broker and confirm the exact four instruments in that account through
a later read-only, no-order check. Until that choice is made, A1 stays blocked, zero instruments
are approved, zero strategies are accepted and `actionable_arm_id` remains `no_trade`.
