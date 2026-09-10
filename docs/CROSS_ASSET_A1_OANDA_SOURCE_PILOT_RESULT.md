# A1 OANDA Source Pilot Result

Successor experiment: `cross-asset-a1-oanda-source-pilot-v2`  
Predecessor: `cross-asset-a1-oanda-source-pilot-v1` — rejected and preserved  
Decision: **daily bid/ask source pilot passed; A1 remains active**  
Actionable disposition: `no_trade`

## Result

The authenticated live-account API was used only for one instrument-catalogue `GET` and bounded
historical-candle `GET`s. The account identifier is represented only by a SHA-256 digest. No
token, balance, summary, position, trade, transaction, order preview or order was serialized or
accessed. All requested candles end before 2026.

| Instrument | Type | Accepted daily rows | Usable start | End | Decision |
|---|---|---:|---|---|---|
| SPX500_USD | Index CFD | 5,479 | 2005-01-02 22:00 UTC | 2025-12-30 22:00 UTC | Pass |
| XAU_USD | Spot metal | 5,476 | 2006-03-19 22:00 UTC | 2025-12-30 22:00 UTC | Pass |
| WTICO_USD | Commodity CFD | post-gap segment | 2005-11-27 22:00 UTC | 2025-12-30 22:00 UTC | Pass in v2 segment |
| EUR_USD | Spot FX | 6,117 | 2005-01-01 22:00 UTC | 2025-12-30 22:00 UTC | Pass |
| USB10Y_USD | Bond CFD | 5,417 | 2005-01-02 22:00 UTC | 2025-12-30 22:00 UTC | Pass |

V1 rejected WTICO_USD because of one 120-hour gap from 2005-11-22 22:00 UTC to
2005-11-27 22:00 UTC. V2 made no new request and starts the oil segment at the first post-gap
candle. No price was filled or rewritten. Three daily-alignment overlaps were byte-identical and
were counted once by the audit without changing the raw files.

## What this does and does not solve

The source is sufficient for daily context and for freezing a later hourly bid/ask pilot. It does
not yet authorize an overnight backtest. OANDA states that FX, metals and indices incur daily
financing, while commodity and bond CFD financing is continuous and derived from the underlying
futures curve. The public page exposes current and recent rates, not a complete historical rate
series. OANDA also applies cash dividend adjustments to index-CFD positions. See
[OANDA financing costs](https://www.oanda.com/uk-en/trading/financing-costs/) and
[OANDA pricing methodology](https://www.oanda.com/uk-en/trading/our-pricing/).

Accordingly:

- `WTICO_USD` and `USB10Y_USD` cannot enter economic evaluation until historical continuous
  financing is qualified.
- A separately frozen intraday pilot may use FX, spot metals and index CFDs only when every
  position is flat before 17:00 America/New_York, avoiding the daily financing boundary.
- Historical bid/ask candles must price entry and exit directly; additional slippage remains a
  separate stress.
- OANDA broker-native CFD history may not be described as CME futures history.

The CME and exact-XLON paths remain preserved but deferred. No further data purchase is justified
for the next intraday source pilot.

## Reproduce

```bash
.venv/bin/pytest -q tests/test_cross_asset_oanda_audit.py
.venv/bin/python scripts/validate_cross_asset_research_context.py
```

Do not rerun or rewrite either immutable source-pilot artifact root.
