# BTC evaluators

Evaluators consume archived/checksummed inputs only and remain disconnected from exchanges,
brokers, databases, NATS, Freqtrade, production signals, orders, positions and active soak
services. They report negative results and keep actionable routing at `no_trade`.
