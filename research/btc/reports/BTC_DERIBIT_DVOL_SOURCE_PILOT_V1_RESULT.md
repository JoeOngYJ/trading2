# BTC Deribit DVOL source pilot v1 result

Experiment ID: `btc-deribit-dvol-source-pilot-v1`  
Decision: **rejected before data requests — frozen official documentation path returned HTTP 404**

The contract was serialized canonically and the auditor started without credentials. Its first
frozen request, the official API-reference URL
`https://docs.deribit.com/api-reference/market-data/public-get-volatility-index-data`, returned
HTTP 404. The auditor failed closed before requesting any DVOL observations, and no raw dataset,
feature, label, strategy, return, PnL, regime model, risk model, 2026 row, partial OB0 data, order,
position, account or protected service was accessed.

Deribit's official `llms.txt` index currently points to the same endpoint documentation with the
resource name `public-get_volatility_index_data.md`. A successor must use a new experiment ID and
may change only that documentation URL. The three pre-2026 data windows, technical gates,
historical-use blockers and `no_trade` boundary must remain unchanged.
