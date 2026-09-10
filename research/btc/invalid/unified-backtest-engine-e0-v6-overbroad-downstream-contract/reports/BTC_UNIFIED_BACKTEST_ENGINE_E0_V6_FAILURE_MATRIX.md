# E0-v6 failure-to-requirement matrix

This matrix preserves the negative E0-v5 and E1-v4-v14 evidence and assigns each failure to one future
component and one independent probe family. It changes no historical candidate.

| Failure | Root cause | E0-v6 requirement | Owner | Independent probe |
|---|---|---|---|---|
| V4 incomplete phases, oracle and pair coverage | Candidate scope exceeded explicit contract coverage | Every semantic obligation has one component owner and one probe | C0 | `M01_contract_coverage` |
| V5 oracle leak | Implementer could see qualification answers | Oracle values created only after candidate snapshot | Q0 | `M02_oracle_absence_before_snapshot` |
| V6 structural bypasses | Arithmetic examples substituted for state-machine guarantees | Public transition invariants and mutation tests are mandatory | C1 | `M03_transition_mutations` |
| V7 missing probes | Preflight did not require a complete probe inventory | Exact unique probe IDs and owners are frozen | C0 | `M04_probe_bijection` |
| V8 self-referential probes | Tests derived truth from implementation | Closed-form external oracle after snapshot | Q0 | `M05_external_oracle` |
| V8 non-atomic entry | Pair mutation began before feasibility was known | Complete bound-outcome pair preflight before mutation, then final fills and compensation without rollback | C4 | `M06_pair_preflight` |
| V9 phase contradictions | One monolith owned incompatible timing paths | C1 owns accounting phases; adapters return facts only | C1 | `M07_phase_ownership` |
| V10 opaque inherited probes | Requirements were referenced without stating observable behavior | Every probe states input, observable and rejection condition | C0 | `M08_probe_observability` |
| V11 forgeable monolith/private test mutation | Security and supported API boundaries were conflated | Supported public API only; hostile reflection explicitly unsupported; tests cannot mutate private state | C0 | `M09_public_API_only` |
| V11 incomplete candle partial behavior | Candle and depth capabilities were conflated | C2 candle facts are all-or-none; partial fills exist only in C3 | C2 | `M10_adapter_capability_separation` |
| V11 invalid controls | Controls were labels/placeholders rather than full economic runs | C5 creates independent control intentions and executes them through the accepted adapter and ledger | C5 | `M11_control_economics` |
| V12 unfrozen RunSpecs | Runtime identity could change after design review | RunSpec bytes and complete implementation manifest are C0 authorities | C0 | `M12_runspec_lineage` |
| V12 overlapping probe ownership | Integration assertions duplicated semantic ownership | Exactly one primary owner per probe | C6 | `M24_integration_probe_ownership` |
| V13 L2 scenario mismatch | Fixture execution mode disagreed with scenario authority | Adapter/scenario compatibility is frozen and verified before execution | C0 | `M13_scenario_compatibility` |
| V14 facade/factory bypass claims | Python was treated as a hostile-code security boundary | No unforgeability claim; qualification covers documented supported calls | C0 | `M25_no_hostile_Python_claim` |
| V14 `-0.1` valid L2 residual | Economic reconciliation was diagnostic instead of a commit gate | Closed-form fixtures require exact zero; runtime requires absolute residual at most 0.00000001 USDT | C1 | `M14_residual_gate` |
| V14 incomplete implementation lineage | Rows bound one module rather than the complete implementation | Merkle-style manifest digest covers every accepted component and authority | C0 | `M15_complete_lineage` |
| V14 missing L2 30/40/80 reports | Required reporting grid was not emitted | The separately frozen C5 L2 extension emits all comparisons from identical L2 fill facts | C5 | `M16_cost_grid_completeness` |
| V14 candle substitution in L2 controls | Control layer selected a different adapter/source | C5 cannot create fills; execution-mode/source digests must remain identical | C5 | `M17_no_adapter_substitution` |
| V14 L2 safety/terminal bypass | Exceptional paths bypassed depth and latency | Every L2 fill reason uses C3, including protection/liquidation/recovery/terminal | C3 | `M18_exceptional_L2_paths` |
| V14 standalone fee/tax helper | Fee calculations did not mutate actual balances | Fees and taxes are C1 economic events with asset-specific balance effects | C1 | `M19_fee_asset_balance` |
| V14 incomplete pair outcome preflight | Validation continued after leg-one commit | C4 enumerates currently bound feasibility before final fills and uses compensating recovery without rollback | C4 | `M26_pair_recovery_preflight` |
| V14 incorrect pair direction | Directional schema was reused for a pair episode | Pair episode direction is exactly `delta_neutral_pair` | C4 | `M20_pair_episode_identity` |
| V14 severe L2 relabelled candle | Cost budget and fill mode were conflated | C5 scenario overlays cannot change execution metadata | C5 | `M21_scenario_label_integrity` |
| V14 incomplete funding timestamps | Funding ownership lacked a complete causal time tuple | Decision, availability, funding-effective and execution timestamps are mandatory | C1 | `M22_funding_causality` |
| V14 incorrect sell bounds | Side-aware protected price inequality was incomplete | Buy and sell bounds have separate explicit assertions | C3 | `M23_side_aware_bounds` |

| E0-v5 missing target-to-order edge | No owner converted the public authorized target into adapter input | C1 emits a typed bound `OrderIntention` during its phase clock | C1 | `M27_target_to_order_edge` |
| E0-v5 false universal timestamps | Non-order rows would need placeholder decision/execution times | Row-kind schemas define exact required and forbidden timestamps | C0 | `M28_row_kind_lineage` |
| E0-v5 nominal interfaces | Interface lists omitted field types and nullability | Seven exact type schemas are frozen | C0 | `M29_exact_type_schemas` |
| E0-v5 missing inherited coverage | Only residual and rollback clauses were structurally checked | Exact E0-v1-v3 JSON-pointer obligation registry is complete | C0 | `M30_inherited_obligation_registry` |
| E0-v5 incomplete integration dependencies | C6 could omit L2 and pair control extensions | C6 requires named accepted base and extension artifacts | C6 | `M31_complete_integration_dependencies` |
| E0-v5 weak bundle binding | Review bound only the contract | Pre-review manifest binds all seven frozen design files | Q0 | `M32_complete_review_bundle` |

The matrix is closed for E0-v6. Adding, removing or reassigning a failure, owner or probe requires a
new E0 experiment ID.
