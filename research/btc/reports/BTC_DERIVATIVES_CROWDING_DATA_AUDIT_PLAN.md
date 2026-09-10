# BTC derivatives-crowding data audit

The first focused BTC task is data qualification, not a backtest. It audits BTCUSDT perpetual
funding, basis, open interest and weekly CME participant positioning over the frozen 2020–2023
development boundary. The 2024–2025 validation interval remains numerically locked and 2026 is
excluded.

The audit must preserve raw public responses, timestamps, pagination, contract identity and
checksums. Binance publicly documents funding history, while its basis and open-interest history
interfaces advertise only a recent rolling window. CFTC positioning is weekly and must be treated
as available only after its official publication time.

No return, forward label, feature threshold, strategy result or trade may be calculated. If free
history cannot supply funding plus one independent positioning/leverage series, the audit must
report the exact missing coverage before any paid-data decision.
