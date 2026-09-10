# Historical Multi-Asset Universe Source Decision

**Decision date:** 2026-08-26  
**Decision:** do not purchase data to repair the legacy fixed-seven experiment; defer that
family and use a new contemporaneous universe rule if cross-sectional research is reopened

## Question

Can the historical BTC/ETH/SOL/XRP/BNB/DOGE/ADA universe be made point-in-time defensible
cheaply enough to rescue the R0 top-two result from survivor and candidate-selection bias?

## Source findings

### Binance public archive

Binance's official public-data repository provides daily and monthly spot klines, trades
and aggregate trades for symbols in its archive, with adjacent checksum files. This is the
preferred free source for price/volume reconstruction. However, its documented helper for
symbol discovery fetches the **current** trading-pair list; the archive does not publish a
historical `exchangeInfo` snapshot for every decision date. [Binance public-data
documentation](https://github.com/binance/binance-public-data/blob/master/README.md)

The live `exchangeInfo` endpoint exposes current symbol status, permissions and filters.
It is necessary for forward operation but does not reproduce the historical candidate set
or historical filters by itself. [Official Binance Spot API
documentation](https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md)

Therefore, first/last candle presence can prove that price observations exist, but it
cannot alone prove why an asset belonged in the candidate universe, whether another asset
was silently omitted, or the exact venue rules in force at that time.

### Tardis metadata

Tardis publishes public Binance metadata with symbol coverage dates and documents high-cap
coverage from 2019-03-30 and all-pair coverage from 2021-03-05. It also offers no-key sample
days. This is useful independent evidence for a future exchange-wide rule, but
`availableSince` is the provider's capture boundary—not automatically an exchange listing
decision or a frozen inclusion methodology. [Tardis Binance coverage
documentation](https://docs.tardis.dev/historical-data-details/binance)

A new experiment could start after March 2021 and define the candidate set as every USDT
spot pair present in the provider metadata with a minimum lookback, then rank only on
trailing Binance venue volume. That would require downloading and validating data for the
entire contemporaneous set. It would be a new strategy and universe, not a repair of the
post-hoc seven.

### Historical market rankings

CoinMarketCap provides the exact type of historical ranked market snapshot needed for a
market-cap universe, but its official documentation states that the
`listings/historical` endpoint requires a paid plan and history depth depends on the tier.
[CoinMarketCap historical-ranking documentation](https://coinmarketcap.com/api/resources/how-to-retrieve-historical-cryptocurrency-rankings/)

CoinGecko's historical endpoint provides market cap, price and volume for one already-known
coin ID at a requested date. It does not by itself solve enumeration of the full historical
candidate population; starting from today's ID list could reintroduce survivor bias.
[CoinGecko historical coin endpoint](https://docs.coingecko.com/reference/coins-id-history)

Paid historical-symbol products such as CoinAPI can retain delisted instruments, but
exchange availability still does not explain the legacy fixed-seven selection rule.
[CoinAPI historical-symbol documentation](https://www.coinapi.io/products/market-data-api/docs/rest-api/metadata/symbols/exchange_id/history/get)

## Decision

Do **not** buy CoinMarketCap, CoinAPI, Kaiko or another dataset merely to rehabilitate
`multi-asset-top2-causal-v1`.

Even perfect listing and market-cap histories cannot undo the fact that this exact family,
asset set and historical interval were selected after results were inspected. Purchasing
data would improve a new experiment's universe construction, but it would not turn R0 into
independent promotion evidence.

The legacy top-two route remains a rejected development benchmark. If cross-sectional
research is reopened later, create a new experiment with:

1. an exchange-wide, contemporaneous inclusion rule rather than a named survivor list;
2. a start no earlier than the provider's complete all-symbol coverage plus the required
   liquidity lookback;
3. checksummed venue data for every eligible and known-ineligible candidate;
4. explicit stablecoin, leveraged-token, wrapped-asset and listing-age treatment;
5. point-in-time market rules and delisting/suspension handling; and
6. a clean prospective partition that the family has not influenced.

## Immediate research direction

Proceed to R2 as a **BTC-only traded action with ETH used only as context**. BTC and ETH
have long, liquid venue histories and do not require a cross-sectional survivor universe.
The existing exploratory report already warns that simple fixed lead/lag correlations are
near zero, consistent with published work finding time-varying co-movement and little
reliably exploitable hourly/daily price discovery. R2 must therefore test one conditional
residual-displacement mechanism rather than a broad lead/lag search. [BTC/ETH lead-lag
study](https://doi.org/10.1016/j.ribaf.2019.06.012)

No purchase is recommended for R2. Existing checksummed BTC/ETH 15-minute archives and the
frozen 30/40/80 bps execution scenarios are sufficient for a development rejection test.

## R2 outcome

R2 was subsequently frozen and executed as `btc-eth-relative-catchup-r2-v1`. It was
decisively rejected: the primary-cost shared account returned -22.71%, the paired event
mean was -34.89 bps with a wholly negative month-block 95% interval, and all six frozen
sensitivities lost money. No data purchase is justified to continue this exact mechanism.
See `docs/BTC_ETH_RELATIVE_CATCHUP_R2_RESULT.md`.
