# Invalid E1-v5 identity — preimplementation oracle leak

E1-v5 failed independent preflight before implementation. Its implementer-readable plan and
contract disclosed the exact terminal outputs of fixtures that were also required to remain blind
until the immutable candidate snapshot. This contradiction defeated independent qualification.

The exact frozen authorities are preserved here as negative evidence and must not be used as
implementation input, copied, repaired or treated as a passed contract:

- `BTC_UNIFIED_BACKTEST_ENGINE_E1_V5_IDENTITY_PLAN.md`: SHA-256
  `445e59f665eb57e8bdf5b3cea461fed01ce36992314348ef6a9ddd2933fa29d5`, 6491 bytes,
  semantic role `rejected_preimplementation_plan_with_oracle_leak`;
- `btc-unified-backtest-engine-e1-v5-identity.json`: SHA-256
  `75ed8939415b968c181948a7fc607a65c45e4bf35f844e59f229ef69f9162ab3`, 13163 bytes,
  semantic role `rejected_preimplementation_contract_with_oracle_leak`.

No E1-v5 module, test, snapshot, historical data access, strategy result, executable action or
external-system access occurred. Recovery requires a new experiment ID whose implementer-readable
authorities name fixture semantics without revealing expected terminal outputs.
