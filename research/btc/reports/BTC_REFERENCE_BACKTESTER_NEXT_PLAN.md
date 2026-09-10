# Minimal BTC reference backtester: next implementation plan

Status: proposed scope, not an accepted engine or strategy. Recorded 2026-09-08 after E0-v12
triggered its final-attempt stop rule. Keep the rejected bundle and all previous negative evidence.

The immediate objective is to establish cash, inventory and return correctness with a small
auditable implementation. The repeated C0 failures show that broad authority machinery and
tests copied from design declarations have delayed that objective without proving it.

1. Freeze a new synthetic qualification identity, `btc-reference-backtester-r0-v1`, before
   implementation. Initial scope is BTC spot, long/flat, one position, explicit synthetic
   timestamps and next eligible open fills. Use Decimal cash and inventory, fixed fee/slippage
   inputs, documented rounding, entry rejection and terminal valuation. Explicitly enumerate
   which applicable E0 accounting obligations it covers; deferred obligations stay unresolved.
2. Write hand-calculated cases before code: flat, buy/hold/sell, loss, fees, insufficient cash,
   rounding remainder, delayed execution, duplicate/reversed timestamps, missing next open,
   gaps and an open terminal position. State expected balances and exact failure outcomes.
3. Implement one small offline ledger and one independent cash-flow calculation. Compare cash,
   inventory, marked equity and costs after every event, not just the final return. Include
   causality checks and conservation identities. Avoid generic routing, registries and L2.
4. Have an independent reviewer check economic conventions and discrepancies. Acceptance needs
   exact fixture reconciliation and documented limitations. Fix ordinary implementation bugs
   before freezing the candidate; preserve frozen failures and assign successors when required.
5. Only after synthetic acceptance, propose a separately frozen reconciliation of one existing
   BTC spot control on checksummed development inputs. It reproduces existing evidence and
   does not supply new promotion evidence. Perpetual funding, margin and matched carry require
   their own later synthetic extensions before those strategies can use this reference.

Use an acyclic evidence layout: inputs and specification first, code and expected fixtures next,
results next, and an external manifest last. Nothing referenced by that manifest embeds its hash.
No contract embeds the hash of an object that itself hashes that contract.

Exit gate for R0: every hand-calculated case and independent reconciliation passes; invalid
inputs fail explicitly; reviewer findings are resolved; evidence records exact inputs and code.
If these fail, report the numerical discrepancy without opening historical strategy results.

The next permitted action is to freeze the bounded R0 synthetic contract and fixture expectations.
This document does not authorize historical data access, tuning, new strategy results, derivatives
execution, protected services or trading. No accepted strategy exists; `no_trade` remains actionable.
