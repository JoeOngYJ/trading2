# BTC Order-Book Tardis Raw Pilot Plan

Frozen: 2026-08-29  
Audit ID: `btc-order-book-tardis-raw-pilot-v1`  
State: **contract frozen; execution and purchase blocked**

## Decision

Tardis remains the only paid historical source currently plausible for the OB1 native replay
contract. Do not buy a subscription or normalized CSV history. The next data action, after final
OB0 acceptance, is a bounded exchange-native raw replay pilot for exactly three mechanically
selected Binance spot BTCUSDT days: 2019-12-01, 2022-12-01, and 2025-12-01.

The dates are first-of-month observations spaced three years apart, beginning with the provider's
documented BTCUSDT sample date. They were not selected from price returns, volatility, feature
behavior, or strategy performance. The pilot is source qualification only and cannot provide
OB0, OB1, alpha, or promotion evidence.

## Why only raw replay qualifies

Tardis documents that its Binance raw historical feed preserves the exchange-native WebSocket
message format with an added local arrival timestamp. It records `depth@100ms`, generates
top-1000-level `depthSnapshot` messages, checks native `U/u` sequence ranges, and restarts the
collector after a missed message. Raw replay can also expose disconnect markers.

The downloadable normalized `incremental_book_L2` CSV is useful for generic adapters but omits
native `U/u` fields and does not include disconnect events. It therefore cannot satisfy the
frozen provider contract and must not be purchased as a substitute.

Official references reviewed on 2026-08-29:

- Binance source and collection details: `https://docs.tardis.dev/historical-data-details/binance`;
- raw HTTP API: `https://docs.tardis.dev/api/http`;
- CSV limitations: `https://docs.tardis.dev/downloadable-csv-files/api`;
- data FAQ: `https://docs.tardis.dev/faq/data`;
- billing: `https://docs.tardis.dev/faq/billing-and-subscriptions`;
- terms: `https://docs.tardis.dev/legal/terms-of-service`;
- public pricing/order surface: `https://tardis.dev/`.

## Dated public pricing observation

The public pricing surface observed on 2026-08-29 listed Binance and other spot exchanges at
USD 450/month equivalent for Academic, USD 900 for Solo, USD 1,350 for Professional, and
USD 3,500 for Business. The feature table showed raw replay for Professional and Business, not
Academic or Solo. Academic spot was shown with quarterly or yearly billing, and the order surface
stated a USD 300 minimum for one-off purchases.

These are public list prices, not a usable quote. They do not authorize payment and may change.
Before purchasing, obtain a written total for a one-off Binance spot BTCUSDT-only raw pilot and
explicitly confirm there is no renewal.

## Exact quote request

Use this text after OB0 is formally accepted:

> Please quote a one-off, non-renewing research purchase for exchange-native raw replay data for
> Binance Spot BTCUSDT only, for UTC dates 2019-12-01, 2022-12-01, and 2025-12-01. It must include
> native `depth`, generated `depthSnapshot`, and `aggTrade` messages, Tardis local arrival
> timestamps, and disconnect markers or equivalent incident boundaries. Please state the total
> price including taxes, quote expiry, download/access window, whether an API key is required,
> and whether we may retain the raw files and non-reversible derived research artifacts for
> internal use after access ends. Please also confirm whether provider incident metadata is
> available for those exact dates.

Do not submit an order, payment, subscription, or quote form without the user's explicit approval
of the dated total. Never place credentials in the repository or its artifacts.

## Frozen acceptance boundary

Every declared date must independently contain:

- raw Binance `depth` messages with `U`, `u`, `E`, bids and asks;
- generated initial and reconnect snapshots with `lastUpdateId`;
- raw aggregate trades with native IDs and aggressor metadata;
- local arrival timestamps and exact disconnect boundaries;
- a mechanically reconstructable, positive and uncrossed order book;
- rejected or segmented sequence/snapshot failures rather than silent repair;
- immutable compressed raw partitions, byte counts, SHA-256 hashes and a manifest; and
- provider incident metadata plus acceptable internal-use and retention terms.

One failed date rejects the pilot. A passing pilot proves only adapter and replay compatibility;
OB1 still requires 60 accepted development days, a later contiguous unread 30-day partition,
and every other gate in `docs/BTC_ORDER_BOOK_OB1_IMPLEMENTATION_READINESS.md`.

## Current blocker and verification

The replacement seven-day OB0 run is expected to finish around 2026-09-01 19:47 UTC. Do not
inspect its partial data to accelerate this decision. After its frozen final acceptance report
passes, request the quote above or use an authorized normal-browser/API-key route for the exact
pilot only. Do not bypass Cloudflare or another access control.

Validate the offline contract now with:

```bash
.venv/bin/python scripts/validate_btc_order_book_tardis_pilot_contract.py
.venv/bin/python -m pytest -q tests/test_btc_order_book_tardis_pilot_contract.py
```
